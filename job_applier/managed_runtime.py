"""Fenced runtime budgets and tab ownership records; no browser/process operations."""
from datetime import datetime
import json
import re
from urllib.parse import urlsplit,urlunsplit
from .managed_shared import ProtocolError,uid
from .managed_redaction import safe_text
from .managed_identity import canonical_url,job_key,RELATED,is_same_application_scope,is_workday_candidate_home,is_workday_application_scope,same_job_url,application_match


class RuntimeServices:
    def _field_context(self,db,a):
        rows=db.execute('SELECT event_type,payload_json FROM managed_events WHERE attempt_id=? AND stale=0 ORDER BY julianday(observed_at) DESC,rowid DESC',(a['id'],))
        legacy=None
        for row in rows:
            payload=json.loads(row['payload_json'])
            if row['event_type'] in ('navigation_verified','field_verified'):return {}
            if row['event_type']=='field_context':
                return {k:payload[k] for k in ('page','field','category','field_label','stage_id','task_id','parent_id','activity','source')
                        if k in payload} if payload.get('field') or payload.get('task_id') else {}
            if payload.get('stage_id') and payload.get('task_id') and row['event_type'] in ('checkpoint','phase_changed'):
                if payload.get('task_state') in ('completed','unsuccessful'):return {}
                return {k:payload[k] for k in ('page','field','category','field_label','stage_id','task_id','parent_id','activity','source') if k in payload}
            # Completion describes action-start attribution, never current scope.
            # Keep legacy manual event support only when no semantic marker exists.
            if legacy is None and row['event_type']=='tool_finished' and payload.get('field'):
                legacy={k:payload.get(k,'') for k in ('page','field','category')}
        return legacy or {}

    def _strategy_check(self,db,a,tool_name):
        from .managed_sessions import local_session
        cfg=json.loads(a['settings_json'])
        events=db.execute('SELECT * FROM managed_events WHERE attempt_id=? AND stale=0 ORDER BY julianday(observed_at) DESC,rowid DESC',(a['id'],)).fetchall()
        payloads=[(row,json.loads(row['payload_json'])) for row in events]
        phase=next((p.get('phase') for row,p in payloads if row['event_type']=='phase_changed' and p.get('phase')),None)
        if cfg.get('allowed_fallback')=='block' and phase in ('residual_fields','native_fallback'):
            raise ProtocolError('fallback_not_allowed')
        if local_session(db,a['id']):
            return self._field_context(db,a)
        extra=db.execute('SELECT COALESCE(SUM(seconds),0) FROM budget_extensions WHERE attempt_id=?',(a['id'],)).fetchone()[0]
        context=self._field_context(db,a)
        if context:
            matched=[row for row,p in payloads if row['event_type']=='tool_finished' and all(p.get(k,'')==v for k,v in context.items())]
            if any(row['duration_seconds'] is None for row in matched):raise ProtocolError('semantic_field_timing_unknown')
            spent=sum(row['duration_seconds'] for row in matched)
            if spent>cfg.get('field_seconds',60)+extra:raise ProtocolError('semantic_field_budget_exceeded')
        return context

    def _budget_check(self,db,a):
        from .managed_sessions import local_session
        if local_session(db,a['id']):
            # Reasoning gaps are visible telemetry. An optional hard maximum is
            # enforced by the host terminating its owned browser before release.
            return
        cfg=json.loads(a['settings_json']);now=datetime.fromisoformat(self.now())
        extra=db.execute('SELECT COALESCE(SUM(seconds),0) FROM budget_extensions WHERE attempt_id=?',(a['id'],)).fetchone()[0]
        if (now-datetime.fromisoformat(a['started_at'])).total_seconds()>cfg.get('attempt_seconds',300)+extra:raise ProtocolError('attempt_budget_exceeded')
        if (now-datetime.fromisoformat(a['progress_at'])).total_seconds()>cfg.get('no_progress_seconds',45)+extra:raise ProtocolError('no_progress_budget_exceeded')

    def extend_budget(self,attempt_id,*,worker_id,fence,seconds,reason):
        if type(seconds) not in (int,float) or not 0<seconds<=120 or not isinstance(reason,str) or not reason.strip():raise ProtocolError('invalid_budget_extension')
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence)
            if self._get(db,'runs',a['run_id'])['control'] in ('stopped','stop_requested'):raise ProtocolError('run_stopping')
            if db.execute('SELECT COUNT(*) FROM budget_extensions WHERE attempt_id=?',(attempt_id,)).fetchone()[0]>=2:raise ProtocolError('budget_extension_limit')
            eid=uid();db.execute('INSERT INTO budget_extensions VALUES (?,?,?,?,?)',(eid,attempt_id,seconds,safe_text(reason),self.now()))
            return dict(self._get(db,'budget_extensions',eid))

    def bind_target(self,attempt_id,*,worker_id,fence,target_id,url):
        if not isinstance(target_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,250}',target_id):raise ProtocolError('invalid_target_id')
        canonical=canonical_url(url);parsed=urlsplit(canonical);display=urlunsplit(parsed._replace(query='',fragment=''))
        identity=job_key(canonical)
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence)
            from .managed_sessions import application_job
            job=application_job(db,a,self._get(db,'jobs',a['job_id']));expected=urlsplit(canonical_url(job['url']))
            from .managed_sessions import local_session
            session=local_session(db,attempt_id)
            if session and session['target_id']!=target_id:raise ProtocolError('target_not_owned')
            verified=db.execute(RELATED+'SELECT 1 FROM related r JOIN job_identity_keys k ON k.job_id=r.id WHERE k.identity_key=?',(job['id'],identity)).fetchone()
            # An account alias proves credential scope, NOT requisition/tab ownership.
            # Alternate URLs need the same verified job identity. Known ATS
            # requisitions retain identity across their normal application steps.
            apply_child=(bool(expected.path) and parsed.scheme==expected.scheme and parsed.netloc==expected.netloc
                and parsed.path==expected.path+'/apply' and parsed.query==expected.query)
            if (expected.hostname or '').endswith(('.myworkdayjobs.com','.icims.com')):
                apply_child=is_same_application_scope(job['url'],canonical)
            accepted_route=job.get('posting_url') and is_same_application_scope(job['url'],canonical)
            if not verified and not apply_child and not accepted_route:raise ProtocolError('target_job_mismatch')
            old=db.execute('SELECT * FROM owned_targets WHERE profile=? AND target_id=? AND state!=?',(a['browser_profile'],target_id,'closed')).fetchone()
            if old:
                if old['attempt_id']!=attempt_id or (old['identity_key']!=identity and not same_job_url(old['url'],canonical)):raise ProtocolError('target_owned_elsewhere')
                return dict(old)
            prior=db.execute('SELECT * FROM owned_targets WHERE attempt_id=? AND target_id=?',(attempt_id,target_id)).fetchone()
            if prior:raise ProtocolError('closed_target_cannot_rebind')
            from .managed_context import platform_for_url
            detected_platform = platform_for_url(canonical)
            if detected_platform != 'unknown' and a['platform'] == 'unknown':
                db.execute('UPDATE application_attempts SET platform=? WHERE id=?', (detected_platform, attempt_id))
            rid=uid();db.execute('INSERT INTO owned_targets(id,attempt_id,profile,target_id,url,state,evidence,created_at,updated_at,identity_key) VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,attempt_id,a['browser_profile'],target_id,display,'open','Explicit worker target binding',self.now(),self.now(),identity))
            return dict(self._get(db,'owned_targets',rid))

    def target_state(self,attempt_id,*,worker_id,fence,target_id,state,evidence):
        if state not in ('open','preserved','closed') or not isinstance(evidence,str) or not evidence.strip():raise ProtocolError('invalid_target_state')
        with self.tx() as db:
            self._owner(db,attempt_id,worker_id,fence)
            target=db.execute('SELECT * FROM owned_targets WHERE attempt_id=? AND target_id=?',(attempt_id,target_id)).fetchone()
            if target is None:raise ProtocolError('target_not_owned')
            if target['state']=='closed' and state!='closed':raise ProtocolError('closed_target_immutable')
            if state==target['state']:return dict(target)
            evidence=safe_text(evidence)
            db.execute('UPDATE owned_targets SET state=?,evidence=?,updated_at=? WHERE id=?',(state,evidence,self.now(),target['id']))
            db.execute('INSERT INTO target_history VALUES (?,?,?,?,?)',(uid(),target['id'],state,evidence,self.now()))
            return dict(self._get(db,'owned_targets',target['id']))

    def browser_observe(self,attempt_id,*,worker_id,fence,target_id=None,cdp_url=None,expected_url=None):
        from .managed_sessions import local_session
        with self.tx() as db:
            session=local_session(db,attempt_id)
            if session:
                workspace=json.loads(self._get(db,'browser_workspaces',session['workspace_id'])['config_json'])
                if cdp_url and cdp_url!=workspace['cdp_url']:raise ProtocolError('workspace_endpoint_mismatch')
                cdp_url=workspace['cdp_url']
                if target_id and target_id!=session['target_id']:raise ProtocolError('target_not_owned')
                target_id=session['target_id']
        endpoint_url=cdp_url or "http://127.0.0.1:9222"
        endpoint=urlsplit(endpoint_url)
        if (endpoint.scheme!="http" or endpoint.hostname not in ("127.0.0.1","localhost","::1")
                or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
                or endpoint.path):
            raise ProtocolError('owned_target_requires_loopback_cdp')
        action_id=uid()
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence)
            job=self._get(db,'jobs',a['job_id'])
            if target_id is not None:
                target=db.execute('SELECT * FROM owned_targets WHERE attempt_id=? AND target_id=? AND state!=?',(attempt_id,target_id,'closed')).fetchone()
            else:
                target=db.execute('SELECT * FROM owned_targets WHERE attempt_id=? AND state!=? ORDER BY created_at DESC, id DESC LIMIT 1',(attempt_id,'closed')).fetchone()
            if target is None:raise ProtocolError('target_not_owned')
            if expected_url is not None:
                expected_canonical=canonical_url(expected_url)
                if not same_job_url(expected_canonical,target['url']) and not same_job_url(expected_canonical,job['url']):
                    raise ProtocolError('target_job_mismatch')
        settings=json.loads(a['settings_json'])
        anchor=(json.loads(session['metadata_json']).get('application_identity_url') if session else None) or job['url']
        def verify_url(url):
            try:
                identity=job_key(canonical_url(url))
            except ProtocolError:
                identity=None
            with self.tx() as db:
                self._owner(db,attempt_id,worker_id,fence)
                related=db.execute(RELATED+'SELECT 1 FROM related r JOIN job_identity_keys k ON k.job_id=r.id WHERE k.identity_key=?',(job['id'],identity)).fetchone() if identity else None
                if identity!=target['identity_key'] and not related:
                    if urlsplit(anchor)[:2]==urlsplit(url)[:2] and application_match(anchor,url)['status']=='different_job':return False
                    if not is_same_application_scope(job['url'], url) and not is_same_application_scope(anchor,url) and not is_same_application_scope(target['url'], url) and not is_workday_candidate_home(job['url'], url):
                        return False
                return True
        async def read_bound_browser():
            import asyncio
            from .cdp_client import CDPBrowser
            browser=await CDPBrowser.connect(endpoint_url,target_id=target['target_id'],expected_mode=settings.get('browser_mode','headed'))
            try:
                page=await browser.get_current_page()
                before_url=await page.evaluate('location.href')
                before_scope=verify_url(before_url)
                from .browser_controls import observe_writers
                async def read_writers():return await observe_writers(page,{'job':dict(job,url=before_url) if before_scope else dict(job),'attempt':dict(a)})
                before=await read_writers()
                # Only a native exact-requisition confirmation can settle a submit
                # after the extension disappears. This is read-only and server-owned.
                from .workday_fast import WORKDAY_OBSERVE
                async def native_confirmation():
                    live_url=await page.evaluate('location.href')
                    if not a['submit_intent_at'] or not is_workday_candidate_home(job['url'],live_url):
                        return False
                    from .managed_identity import job_requisition
                    result=await page.evaluate_function(WORKDAY_OBSERVE,{'requisition':job_requisition(dict(job))})
                    return isinstance(result,dict) and result.get('submitted') is True
                confirmed_before=await native_confirmation() if not before.get('panel') else False
                await asyncio.sleep(0.15)
                after=await read_writers()
                # The observer deliberately omits query parameters from its public
                # URL. Workday login ownership depends on the full job redirect.
                after_url=await page.evaluate('location.href')
                after_scope=verify_url(after_url)
                # Read-only audit remains available even when a writer prevents repair.
                audit_observation=None
                if not after.get('workday') and not after.get('greenhouse') and after.get('status') in ('complete','needs_review','unknown','missing','unsupported'):
                    try:
                        from .browser_controls import observe
                        audit_observation=await observe(page,{'job':dict(job,url=after_url) if after_scope else dict(job),'attempt':dict(a)})
                    except Exception:pass
                if after_scope and before_url==after_url:
                    try:
                        from .browser_controls import FORM
                        metadata=await page.evaluate_function(FORM,{'method':'metadata'})
                        self.observe_job_metadata(attempt_id,worker_id=worker_id,fence=fence,metadata=metadata)
                    except Exception:pass  # Discovery does not affect writer/ownership evidence.
                if settings.get('mode')=='pilot' and after.get('source')=='fixture':
                    raise ProtocolError('official_extension_observation_required')
                stable=before_url==after_url and all(before.get(k)==after.get(k) for k in ('url','fingerprint','page_ref','page_signature','status'))
                stable=stable and before.get('application_frames')==after.get('application_frames')
                confirmed=confirmed_before and not after.get('panel') and await native_confirmation()
                match={'status':'same_job'} if before_scope and after_scope else application_match(job['url'],after_url)
                return after,stable,browser.observed_mode,confirmed,match,after_url,audit_observation
            finally:
                await browser.close()
        self.action_start(attempt_id,worker_id=worker_id,fence=fence,action_id=action_id,tool_name='browser_observe',writes_browser=False)
        try:
            import asyncio
            obs,stable,observed_mode,native_confirmed,match,live_url,audit_observation=asyncio.run(read_bound_browser())
            from .managed_context import platform_for_url
            obs_url=obs.get('url') or target['url']
            detected_platform=platform_for_url(obs_url)
            status=obs.get('status','unknown')
            with self.tx() as db:
                a=self._owner(db,attempt_id,worker_id,fence)
                other_actions=db.execute('SELECT 1 FROM managed_actions WHERE attempt_id=? AND ended_at IS NULL AND id!=?',(attempt_id,action_id)).fetchone()
                unended_writer=db.execute('SELECT 1 FROM managed_actions WHERE attempt_id=? AND ended_at IS NULL AND writes_browser=1 AND id!=?',(attempt_id,action_id)).fetchone()
                prior_writer=a['writer_state']
                has_active_autofill=(prior_writer in ('active','unknown') or bool(unended_writer))
                documents=obs.get('writer_documents') or ([{'document_id':obs['writer_document_id'],
                    'pending':bool(obs.get('writer_pending'))}] if obs.get('writer_document_id') else [])
                previous=db.execute("SELECT payload_json FROM managed_events WHERE attempt_id=? AND json_extract(payload_json,'$.operation')='writer_documents' ORDER BY rowid DESC LIMIT 1",(attempt_id,)).fetchone()
                prior_documents=json.loads(previous[0]).get('writer_documents',[]) if previous else []
                old_ids={d.get('document_id') for d in prior_documents if d.get('pending')} or {d.get('document_id') for d in prior_documents}
                new_ids={d.get('document_id') for d in documents}
                document_cancelled=bool(old_ids and new_ids and None not in old_ids|new_ids and not old_ids&new_ids and
                    not obs.get('frame_diagnostics') and not obs.get('writer_pending'))

                if unended_writer:
                    new_writer='active'
                    quiescent=False
                elif status=='active' or obs.get('writer_pending'):
                    new_writer='active'
                    quiescent=False
                elif stable and native_confirmed and a['submit_intent_at'] and not other_actions:
                    new_writer='idle'
                    quiescent=True
                elif has_active_autofill:
                    known_account_ready=(status=='login_required' and any(
                        (obs.get('controls') or {}).get(k,{}).get('enabled')
                        for k in ('create_account_autofill','create_account','sign_in')))
                    explicit_settlement=status=='unsupported' and obs.get('writer_safe') and not any(
                        obs.get('activity',{}).get(k) for k in ('busy_indicator','explicit_writer'))
                    if stable and (document_cancelled or obs.get('settled_evidence') or obs.get('panel') and (status in ('complete','needs_review','ready') or known_account_ready or explicit_settlement)):
                        new_writer='idle'
                        quiescent=True
                    else:
                        new_writer='unknown'
                        quiescent=False
                else:
                    if stable:
                        new_writer='idle'
                        quiescent=True
                    else:
                        new_writer='unknown'
                        quiescent=False

                quiescent=quiescent and not bool(other_actions)
                db.execute('UPDATE application_attempts SET writer_state=? WHERE id=?',(new_writer,attempt_id))
                run=self._get(db,'runs',a['run_id']);caps=json.loads(run['capabilities_json'] or '{}')
                caps['observed_browser_mode']=observed_mode
                db.execute('UPDATE runs SET capabilities_json=? WHERE id=?',(json.dumps(caps),a['run_id']))
                if detected_platform != 'unknown':
                    db.execute('UPDATE application_attempts SET platform=? WHERE id=?',(detected_platform,attempt_id))
            self.action_end(attempt_id,worker_id=worker_id,fence=fence,action_id=action_id,status='success')
            if documents and documents!=prior_documents:
                self.event(attempt_id,worker_id=worker_id,fence=fence,event_id=uid(),event_type='checkpoint',observed_at=self.now(),
                    payload={'operation':'writer_documents','writer_documents':documents,'prior_document_cancelled':document_cancelled})
            if quiescent and match['status']=='same_job' and obs.get('status') in ('complete','needs_review'):
                with self.tx() as db:semantic=self._field_context(db,self._get(db,'application_attempts',attempt_id))
                if semantic.get('stage_id')=='fill_application':
                    self.event(attempt_id,worker_id=worker_id,fence=fence,event_id=uid(),event_type='checkpoint',observed_at=self.now(),
                        payload=dict(semantic,task_state='completed',evidence='Simplify settled on the current page; remaining questions can be reviewed'))
            from .browser_controls import next_operation
            permitted=quiescent and match['status']=='same_job' and not (
                obs.get('activity',{}).get('busy_indicator') and obs.get('activity',{}).get('waiting_for_input'))
            guidance=next_operation(detected_platform,obs,identity=match,quiescent=permitted)
            compact={}
            if audit_observation is not None:
                from .form_audit import audit
                compact['audit']=audit(audit_observation,writer={'ui_status':status,'state':new_writer,
                    'native_takeover_authorized':permitted,'terminal_evidence':obs.get('settled_evidence',False)})
            from .managed_identity import public_url,form_route_identity
            requisition=form_route_identity(live_url)
            return {
                'operation':'browser_observe',
                **compact,
                'status':status,
                'writer_state':new_writer,
                'quiescent':quiescent,
                'identity':match,
                'native_takeover_authorized':permitted,
                'observed_browser_mode':observed_mode,
                'platform':detected_platform,
                'company':self.job(job['id'])['company'],
                'next_operation':guidance,
                'target_id':target['target_id'],
                'url':public_url(live_url),
                'assigned_url':public_url(job['url']),
                'application_url':public_url(anchor),
                'identity_evidence':{'observed_requisition':requisition[3] if requisition else None},
                'observation':obs,
                'action_id':action_id,
                'instruction':'Observe ongoing work or use its enabled Stop/Cancel. Before submission, a broken page or missing Simplify panel can be recovered with browser reload or session restart even when writer settlement is unknown. Inspect the new page and continue; this observation is not an application outcome.',
            }
        except Exception:
            self.action_end(attempt_id,worker_id=worker_id,fence=fence,action_id=action_id,status='failed')
            raise
