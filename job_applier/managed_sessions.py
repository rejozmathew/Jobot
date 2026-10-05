"""Local session records in the existing managed database, shared by both transports.

Browser I/O belongs to the workspace host, outside these short transactions.
Legacy leases remain for explicit compatibility runs, never for local sessions.
"""
import hashlib
import json
import re
from datetime import datetime

from .managed_identity import RELATED
from .managed_redaction import reject_secrets, safe_text
from .managed_shared import ProtocolError, dumps, uid


def local_session(db, attempt_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='application_sessions'").fetchone():
        return None
    return db.execute('SELECT * FROM application_sessions WHERE attempt_id=?', (attempt_id,)).fetchone()


def application_job(db, attempt, job):
    """Project the host-verified route for every helper without rewriting intake."""
    session=local_session(db,attempt['id'])
    if not session:return dict(job)
    metadata=json.loads(session['metadata_json']);route=metadata.get('application_route_url')
    if not route:return dict(job)
    from .managed_identity import job_key
    owned=db.execute("SELECT identity_key FROM owned_targets WHERE attempt_id=? AND target_id=? AND state='open'",
                     (attempt['id'],session['target_id'])).fetchone()
    if not owned or owned['identity_key']!=job_key(route):return dict(job)
    return dict(job,posting_url=job['url'],url=route,account_url=metadata.get('application_account_url') or route)


class SessionServices:
    @staticmethod
    def _has_local_schema(db):
        return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='application_sessions'").fetchone())

    def configure_workspaces(self, workspaces):
        """Called from the selected private config; identities/paths are immutable while occupied."""
        from .application_runtime import validate_workspaces
        workspaces=validate_workspaces(workspaces)
        with self.tx() as db:
            for workspace in workspaces:
                encoded=dumps(workspace)
                old=db.execute('SELECT * FROM browser_workspaces WHERE id=?',(workspace['id'],)).fetchone()
                if old and old['config_json']!=encoded:
                    if old['state']!='offline' or db.execute('SELECT 1 FROM application_sessions WHERE workspace_id=? AND ended_at IS NULL',(workspace['id'],)).fetchone():
                        raise ProtocolError('workspace_configuration_in_use')
                db.execute('''INSERT INTO browser_workspaces(id,config_json,updated_at) VALUES (?,?,?)
                    ON CONFLICT(id) DO UPDATE SET config_json=excluded.config_json,updated_at=excluded.updated_at''',
                    (workspace['id'],encoded,self.now()))
                for profile in [workspace['id'],*workspace.get('legacy_profiles',[])]:
                    alias=db.execute('SELECT workspace_id FROM workspace_profile_aliases WHERE profile=?',(profile,)).fetchone()
                    if alias and alias[0]!=workspace['id']:raise ProtocolError('workspace_alias_conflict')
                    db.execute('INSERT OR IGNORE INTO workspace_profile_aliases VALUES (?,?)',(profile,workspace['id']))
        return workspaces

    def reserve_session(self, *, request_id, job_id, identity_id, driver_id, workspace_ids,
                        concurrency_limit, metadata=None, resume_asset_id=None):
        if not request_id or not driver_id or not workspace_ids:
            raise ProtocolError('local_request_context_required')
        reject_secrets(metadata or {})
        key=dumps([job_id,identity_id,driver_id,resume_asset_id])
        with self.tx() as db:
            old=db.execute('SELECT * FROM application_sessions WHERE request_id=?',(request_id,)).fetchone()
            if old:
                if old['request_key']!=key:raise ProtocolError('idempotency_conflict')
                if old['state']!='capacity_wait':return dict(old)
            settings=self._settings_record(db)['values']
            self._eligible(db,job_id,settings,old['id'] if old else None)
            candidate=self._get(db,'candidates',identity_id)
            if candidate['state']!='active':raise ProtocolError('identity_inactive')
            if not resume_asset_id:raise ProtocolError('configured_resume_required')
            asset=self._get(db,'document_assets',resume_asset_id)
            if asset['identity_id']!=identity_id or asset['kind']!='resume' or asset['status']!='available':
                raise ProtocolError('asset_identity_mismatch')
            occupied=db.execute('SELECT workspace_id FROM application_sessions WHERE workspace_id IS NOT NULL AND ended_at IS NULL').fetchall()
            taken={x[0] for x in occupied}
            selected=None
            if len(occupied)<concurrency_limit:
                for wid in workspace_ids:
                    w=self._get(db,'browser_workspaces',wid)
                    shared=json.loads(w['config_json']).get('connection_mode')=='existing'
                    if (shared or wid not in taken) and w['state'] not in ('failed','isolating'):
                        lease=db.execute("SELECT 1 FROM browser_leases l JOIN workspace_profile_aliases a ON a.profile=l.profile WHERE a.workspace_id=? AND l.state!='released'",(wid,)).fetchone()
                        if not lease:selected=wid;break
            now=self.now();sid=old['id'] if old else uid()
            state='preparing' if selected else 'capacity_wait'
            reason=None if selected else 'Configured workspaces are occupied or unavailable'
            if old:
                db.execute('UPDATE application_sessions SET workspace_id=?,state=?,reason=?,preparing_at=? WHERE id=?',
                           (selected,state,reason,now if selected else None,sid))
            else:
                session_metadata=dict(metadata or {})
                # A new conversation/request can retry the same job without using
                # the retry command. Derive cleanup from history, not driver IDs.
                session_metadata['fresh_employer_storage']=bool(db.execute(RELATED+'''SELECT 1 FROM related r
                    WHERE EXISTS (SELECT 1 FROM application_attempts a WHERE a.job_id=r.id)
                       OR EXISTS (SELECT 1 FROM application_sessions s WHERE s.job_id=r.id)
                    LIMIT 1''',(job_id,)).fetchone())
                session_metadata['application_kind']='reattempt' if session_metadata['fresh_employer_storage'] else 'first_attempt'
                db.execute('''INSERT INTO application_sessions(id,request_id,request_key,job_id,identity_id,
                    driver_id,workspace_id,state,reason,requested_at,preparing_at,driver_seen_at,metadata_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (sid,request_id,key,job_id,identity_id,driver_id,selected,state,reason,now,now if selected else None,now,dumps(session_metadata)))
            if selected:
                run_id=uid();snapshot=dict(settings)
                # Startup/model gaps are telemetry, not an authorization expiry.
                # The host and dispatcher enforce the frozen application deadline.
                snapshot['ownership_mode']='local-session-v1'
                snapshot['browser_mode']=json.loads(self._get(db,'browser_workspaces',selected)['config_json']).get('mode','headed')
                versions=dict(metadata or {},protocol=2,transport='local',browser_profile=selected)
                db.execute('''INSERT INTO runs(id,request_id,request_key,identity_id,browser_profile,state,
                    requested_at,worker_id,session_id,settings_json,capabilities_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                    (run_id,'local:'+sid,key,identity_id,selected,'preparing',now,'local:'+sid,driver_id,dumps(snapshot),dumps(versions)))
                db.execute('INSERT INTO run_jobs(run_id,job_id,position) VALUES (?,?,0)',(run_id,job_id))
                db.execute('UPDATE application_sessions SET run_id=? WHERE id=?',(run_id,sid))
                # Freeze the explicitly approved asset for this request. No file hunting.
                db.execute('INSERT INTO document_selections VALUES (?,?,?,?,?,?)',
                           (uid(),resume_asset_id,job_id,None,'selected',now))
            return dict(self._get(db,'application_sessions',sid))

    def session(self, session_id):
        with self.read() as db:return dict(self._get(db,'application_sessions',session_id))

    def session_human_input(self,session_id,driver_id,capabilities):
        """Record the attached harness's observed messaging availability, not browser authority."""
        from .managed_questions import human_input_capabilities
        normalized=human_input_capabilities({'human_input':capabilities})
        with self.tx() as db:
            session=self._get(db,'application_sessions',session_id)
            if session['driver_id']!=driver_id or session['ended_at']:raise ProtocolError('driver_owned_elsewhere')
            metadata=json.loads(session['metadata_json'])
            if metadata.get('human_input')!=normalized:
                metadata['human_input']=normalized
                db.execute('UPDATE application_sessions SET metadata_json=? WHERE id=?',(dumps(metadata),session_id))
        return normalized

    def session_status(self, session_id):
        with self.read() as db:
            s=dict(self._get(db,'application_sessions',session_id))
            workspace=dict(self._get(db,'browser_workspaces',s['workspace_id'])) if s['workspace_id'] else None
            attempt=dict(self._get(db,'application_attempts',s['attempt_id'])) if s['attempt_id'] else None
            events=[dict(row) for row in db.execute('SELECT * FROM managed_events WHERE attempt_id=? ORDER BY rowid',(s['attempt_id'],))] if attempt else []
            actions=[dict(row) for row in db.execute('SELECT * FROM managed_actions WHERE attempt_id=?',(s['attempt_id'],))] if attempt else []
        return self._session_status_record(s,workspace,attempt,events,actions)

    def _session_status_record(self,s,workspace,attempt,events,actions):
        """Build projections after releasing the read snapshot; no browser/DB I/O."""
        recent=sorted((e for e in events if not e['stale'] and e['event_type'] in
            ('phase_changed','navigation_verified','account_verified','recovery','outcome')),
            key=lambda e:(e['recorded_at'],e['id']),reverse=True)[:12]
        steps=[{k:e[k] for k in ('event_type','observed_at')}|{'payload':json.loads(e['payload_json'])} for e in recent]
        from .managed_reports import application_progress
        progress=application_progress(events,actions=actions,now=self.now(),ended_at=s['ended_at'])
        autofill_times=[event['observed_at'] for event in events if not event['stale'] and
            (payload:=json.loads(event['payload_json'])).get('operation')=='autofill_dispatch' and payload.get('status')=='executed']
        first_autofill=min(autofill_times) if autofill_times else None
        from .workspace_process import process_matches
        host_alive=bool(workspace and workspace['host_identity_json'] and process_matches(json.loads(workspace['host_identity_json'])))
        now=datetime.fromisoformat(self.now())
        def age(value):return max(0,(now-datetime.fromisoformat(value)).total_seconds()) if value else None
        cfg=json.loads(workspace['config_json']) if workspace else None
        return {**s,'transport':'local','workspace':cfg,'host_alive':host_alive,
                'progress':progress,
                'first_autofill_at':first_autofill,
                'ready_to_autofill_seconds':max(0,(datetime.fromisoformat(first_autofill)-datetime.fromisoformat(s['connected_at'])).total_seconds()) if first_autofill and s['connected_at'] else None,
                'activity':steps[0] if steps else None,'steps':list(reversed(steps)),
                'host_seen_at':workspace['host_seen_at'] if workspace else None,
                'driver_age_seconds':age(s['driver_seen_at']),
                'driver_recently_active':age(s['driver_seen_at']) is not None and age(s['driver_seen_at'])<120,
                'last_verified_progress_at':attempt['progress_at'] if attempt else None,
                'writer_state':attempt['writer_state'] if attempt else 'unknown',
                'elapsed_seconds':age(s['requested_at']) if not s['ended_at'] else max(0,(datetime.fromisoformat(s['ended_at'])-datetime.fromisoformat(s['requested_at'])).total_seconds()),
                'queue_seconds':max(0,(datetime.fromisoformat(s['preparing_at'] or self.now())-datetime.fromisoformat(s['requested_at'])).total_seconds()),
                'startup_seconds':max(0,(datetime.fromisoformat(s['connected_at'] or s['ended_at'] or self.now())-datetime.fromisoformat(s['preparing_at'])).total_seconds()) if s['preparing_at'] else None,
                'metadata':json.loads(s['metadata_json'])}

    def _local_owner(self, db, session):
        """Only the assigned host executing for the attached driver can write."""
        authority=getattr(self,'session_authority',None)
        w=self._get(db,'browser_workspaces',session['workspace_id'])
        if authority!=(session['id'],session['driver_id'],w['host_id']):
            raise ProtocolError('local_session_transport_required')
        if session['ended_at'] or session['state'] not in ('connected','waiting'):
            raise ProtocolError('local_session_not_connected')

    def _legacy_workspace_guard(self,db,profile):
        if self._has_local_schema(db) and db.execute('SELECT 1 FROM workspace_profile_aliases WHERE profile=?',(profile,)).fetchone():
            raise ProtocolError('local_workspace_requires_session')

    def host_registered(self, workspace_id, host_id, identity):
        with self.tx() as db:
            self._get(db,'browser_workspaces',workspace_id)
            db.execute("UPDATE browser_workspaces SET host_id=?,host_identity_json=?,host_seen_at=?,state='ready',reason=NULL,updated_at=? WHERE id=?",
                       (host_id,dumps(identity),self.now(),self.now(),workspace_id))

    def host_seen(self, workspace_id, host_id, browser_identity=None):
        with self.tx() as db:
            if self._get(db,'browser_workspaces',workspace_id)['host_id']!=host_id:raise ProtocolError('stale_host')
            db.execute('UPDATE browser_workspaces SET host_seen_at=?,browser_identity_json=?,updated_at=? WHERE id=?',
                       (self.now(),dumps(browser_identity) if browser_identity else None,self.now(),workspace_id))

    def session_connected(self, session_id, host_id, target_id, readiness):
        """Readiness is produced by the host. Claim happens only AFTER real browser I/O."""
        with self.tx() as db:
            s=self._get(db,'application_sessions',session_id)
            if s['state']!='preparing' or s['ended_at']:raise ProtocolError('session_not_preparing')
            w=self._get(db,'browser_workspaces',s['workspace_id'])
            if w['host_id']!=host_id:raise ProtocolError('stale_host')
            run=self._get(db,'runs',s['run_id'])
            if s['attempt_id']:
                self._assert_not_suppressed(db,s['job_id']);job=self._get(db,'jobs',s['job_id'])
            else:
                job=self._eligible(db,s['job_id'],json.loads(run['settings_json']),s['id'])
            candidate=self._get(db,'candidates',s['identity_id'])
            now=self.now()
            fence=db.execute('SELECT COALESCE(MAX(fence),0)+1 FROM application_attempts WHERE browser_profile=?',(s['workspace_id'],)).fetchone()[0]
            if s['attempt_id']:
                # Explicit paused-session attach: stopped browser; fresh target, same attempt.
                attempt=self._get(db,'application_attempts',s['attempt_id'])
                attempt_id=attempt['id'];fence=attempt['fence']
            else:
                attempt_id=self._create_attempt(db,run,job,candidate,fence,now,'local-session-v1')
                asset_id=json.loads(s['request_key'])[3]
                db.execute('INSERT INTO document_selections VALUES (?,?,?,?,?,?)',(uid(),asset_id,job['id'],attempt_id,'selected',now))
            meta=json.loads(s['metadata_json']);meta['readiness']=readiness
            meta.pop('browser_restart',None)
            db.execute("UPDATE application_sessions SET attempt_id=?,target_id=?,state='connected',reason=NULL,connected_at=COALESCE(connected_at,?),driver_seen_at=?,metadata_json=? WHERE id=?",
                       (attempt_id,target_id,now,now,dumps(meta),s['id']))
            db.execute("UPDATE jobs SET status='running',started_at=COALESCE(started_at,?),updated_at=? WHERE id=?",(now,now,job['id']))
            db.execute("UPDATE runs SET state='active',control='running',accepted_at=COALESCE(accepted_at,?),started_at=COALESCE(started_at,?) WHERE id=?",(now,now,run['id']))
            db.execute("UPDATE run_jobs SET state='active' WHERE run_id=? AND job_id=?",(run['id'],job['id']))
            db.execute('INSERT INTO run_sessions(run_id,worker_id,session_id,started_at) VALUES (?,?,?,?)',(run['id'],run['worker_id'],s['driver_id'],now))
            if self._has_question_schema(db):
                db.execute("UPDATE answer_retry_requests SET state='started',session_id=?,started_at=? WHERE job_id=? AND identity_id=? AND state='queued'",
                    (session_id,now,s['job_id'],s['identity_id']))
        # Existing target identity enforcement is reused after the atomic transition.
        self.session_authority=(session_id,s['driver_id'],host_id)
        self.bind_target(attempt_id,worker_id=run['worker_id'],fence=fence,target_id=target_id,url=job['url'])
        navigation=readiness.get('application_navigation')
        if navigation:
            self.handoff_target(attempt_id,worker_id=run['worker_id'],fence=fence,
                current_target_id=target_id,new_target_id=target_id,url=navigation['url'],
                source_url=job['url'],navigation_chain=navigation['chain'],
                evidence='Host observed initial navigation and redirect in the owned application tab')
        return self.session(session_id)

    def session_browser_attachment(self, session_id, host_id, attachment, target_id=None):
        """Durable tab ownership, including the interval before readiness/claim."""
        with self.tx() as db:
            s=self._get(db,'application_sessions',session_id)
            w=self._get(db,'browser_workspaces',s['workspace_id'])
            if w['host_id']!=host_id:raise ProtocolError('stale_host')
            meta=json.loads(s['metadata_json']);previous=meta.get('browser_attachment') or {}
            if previous.get('browser_id') and previous['browser_id']==attachment.get('browser_id'):
                # Refreshing attachment metadata must not lose an earlier owned
                # page. Cleanup retains every target in this browser incarnation.
                targets=set(previous.get('target_ids',[]))|set(attachment.get('target_ids',[]))
                if s['target_id']:targets.add(s['target_id'])
                attachment=dict(attachment,target_ids=sorted(targets))
            meta['browser_attachment']=attachment
            db.execute('UPDATE application_sessions SET metadata_json=?,target_id=COALESCE(?,target_id) WHERE id=?',
                       (dumps(meta),target_id,session_id))

    def request_session_restart(self, session_id, host_id):
        """Persist host-owned replacement before requesting asynchronous closure."""
        with self.tx() as db:
            s=self._get(db,'application_sessions',session_id)
            if self._get(db,'browser_workspaces',s['workspace_id'])['host_id']!=host_id:raise ProtocolError('stale_host')
            meta=json.loads(s['metadata_json'])
            if s['ended_at'] or self._get(db,'runs',s['run_id'])['control']!='running':return dict(s)
            if meta.get('browser_restart'):return dict(s)
            meta['browser_restart']={'phase':'closing','requested_at':self.now()}
            db.execute("UPDATE application_sessions SET state='preparing',reason='Replacing owned application target',metadata_json=? WHERE id=?",
                       (dumps(meta),session_id))
            return dict(self._get(db,'application_sessions',session_id))

    def session_restart_closed(self, session_id, host_id):
        """Host calls only after verified tab/process closure; keep the same attempt."""
        with self.tx() as db:
            s=self._get(db,'application_sessions',session_id)
            if self._get(db,'browser_workspaces',s['workspace_id'])['host_id']!=host_id:raise ProtocolError('stale_host')
            meta=json.loads(s['metadata_json'])
            if s['ended_at'] or self._get(db,'runs',s['run_id'])['control']!='running':return False
            if not meta.get('browser_restart'):return False
            now=self.now()
            db.execute("UPDATE managed_actions SET ended_at=?,status='aborted',uncertainty=1 WHERE attempt_id=? AND ended_at IS NULL",(now,s['attempt_id']))
            db.execute("UPDATE application_attempts SET writer_state='idle' WHERE id=?",(s['attempt_id'],))
            db.execute("UPDATE owned_targets SET state='closed',evidence='Owned target closed for restart',updated_at=? WHERE attempt_id=? AND state!='closed'",(now,s['attempt_id']))
            db.execute('DELETE FROM account_coordination WHERE session_id=?',(session_id,))
            meta['browser_restart']={'phase':'opening','requested_at':meta['browser_restart']['requested_at']}
            db.execute("UPDATE application_sessions SET target_id=NULL,reason='Reopening owned application target',metadata_json=? WHERE id=?",(dumps(meta),session_id))
            return True

    def handoff_target(self, attempt_id, *, worker_id, fence, current_target_id,
                       new_target_id, url, evidence, expected_url=None, source_url=None, navigation_chain=None,
                       authentication=False, _history_proof=None):
        """Atomically move one local session to a correlated application target."""
        from .managed_identity import canonical_url,job_key,RELATED,is_same_application_scope
        from urllib.parse import urlsplit,urlunsplit
        if any(not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,250}',value)
               for value in (current_target_id,new_target_id)):
            raise ProtocolError('invalid_target_id')
        if not isinstance(evidence,str) or not evidence.strip():raise ProtocolError('evidence_required')
        canonical=canonical_url(url);identity=job_key(canonical)
        display=urlunsplit(urlsplit(canonical)._replace(query='',fragment=''))
        with self.tx() as db:
            attempt=self._owner(db,attempt_id,worker_id,fence)
            session=local_session(db,attempt_id)
            if not session or session['target_id']!=current_target_id:raise ProtocolError('target_not_owned')
            current=db.execute("SELECT * FROM owned_targets WHERE attempt_id=? AND target_id=? AND state!='closed'",
                               (attempt_id,current_target_id)).fetchone()
            if current is None:raise ProtocolError('target_not_owned')
            job=self._get(db,'jobs',attempt['job_id'])
            meta=json.loads(session['metadata_json'])
            anchor=meta.get('application_identity_url') or job['url']
            if _history_proof is not None:
                # Internal browser-history observer: compare and promote in the
                # same transaction so a newer route/anchor cannot be overwritten.
                replacement=_history_proof['replacement']
                binding={'session_id':session['id'],'attempt_id':attempt_id,'fence':fence,
                         'target_id':current_target_id,
                         'browser_id':(meta.get('browser_attachment') or {}).get('browser_id')}
                if (current_target_id!=new_target_id or
                        meta.get('route_history_anchor')!=_history_proof['expected'] or
                        current['identity_key']!=_history_proof['target_identity'] or
                        anchor!=_history_proof['identity_url'] or
                        any(replacement.get(k)!=v for k,v in binding.items())):
                    return None  # Fresh ordinary observation can retry its proof.
            alias=db.execute(RELATED+'SELECT 1 FROM related r JOIN job_identity_keys k ON k.job_id=r.id WHERE k.identity_key=?',
                             (job['id'],identity)).fetchone()
            correlated=False
            if expected_url is not None:
                correlated=canonical_url(expected_url)==canonical
            if source_url is not None and current_target_id==new_target_id:
                from .managed_identity import application_match
                source=canonical_url(source_url)
                verified_source=(job_key(source)==current['identity_key'] or is_same_application_scope(job['url'],source)
                                 or is_same_application_scope(current['url'],source))
                same_origin=urlsplit(source)[:2]==urlsplit(canonical)[:2]
                no_conflict=all(application_match(base,canonical)['status']!='different_job'
                                for base in (source,current['url']))
                if urlsplit(anchor)[:2]==urlsplit(canonical)[:2]:
                    no_conflict=no_conflict and application_match(anchor,canonical)['status']!='different_job'
                # Only host-observed navigation from the owned verified document
                # establishes continuity for an intermediate page without an ID.
                correlated=verified_source and same_origin and no_conflict
            if navigation_chain and source_url:
                from .managed_identity import explicit_job_conflict
                from .cdp_client import _public_destination
                chain=[canonical_url(item) for item in navigation_chain]
                source=canonical_url(source_url)
                verified_source=(job_key(source)==current['identity_key'] or is_same_application_scope(job['url'],source)
                                 or is_same_application_scope(current['url'],source))
                correlated=(verified_source and chain[0]==source and chain[-1]==canonical
                    and all(_public_destination(item) for item in chain)
                    and not explicit_job_conflict(anchor,canonical)
                    and not explicit_job_conflict(source,canonical))
            if not alias and not is_same_application_scope(job['url'],canonical) and not correlated:
                raise ProtocolError('target_job_mismatch')
            from .managed_identity import observed_posting_key
            posting_key=observed_posting_key(canonical)
            if posting_key:
                db.execute('INSERT OR IGNORE INTO job_identity_keys VALUES (?,?,?)',
                    (posting_key,job['id'],'observed_posting_identity'))
            occupied=db.execute("SELECT * FROM owned_targets WHERE profile=? AND target_id=? AND state!='closed'",
                                (attempt['browser_profile'],new_target_id)).fetchone()
            if occupied and occupied['attempt_id']!=attempt_id:raise ProtocolError('target_owned_elsewhere')
            now=self.now();safe=safe_text(evidence)
            if new_target_id==current_target_id:
                db.execute('UPDATE owned_targets SET url=?,identity_key=?,evidence=?,updated_at=? WHERE id=?',
                           (display,identity,safe,now,current['id']))
            elif not occupied:
                db.execute('INSERT INTO owned_targets(id,attempt_id,profile,target_id,url,state,evidence,created_at,updated_at,identity_key) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (uid(),attempt_id,attempt['browser_profile'],new_target_id,display,'open',safe,now,now,identity))
                db.execute("UPDATE owned_targets SET state='preserved',evidence=?,updated_at=? WHERE id=?",
                           (safe,now,current['id']))
                db.execute('INSERT INTO target_history VALUES (?,?,?,?,?)',(uid(),current['id'],'preserved',safe,now))
            meta=json.loads(session['metadata_json']);attachment=meta.get('browser_attachment')
            if authentication and correlated:
                meta.setdefault('application_account_url',meta.get('application_route_url') or job['url'])
            elif source_url is None or (navigation_chain and urlsplit(anchor).netloc!=urlsplit(canonical).netloc):
                meta.pop('application_account_url',None)
            meta['application_route_url']=canonical
            if _history_proof is not None:meta['route_history_anchor']=_history_proof['replacement']
            if source_url is None or (navigation_chain and urlsplit(anchor).netloc!=urlsplit(canonical).netloc):
                meta['application_identity_url']=canonical
            if source_url is not None:
                meta['last_application_transition']={'source':source_url.split('?')[0],
                    'destination':display,'observed_at':now,'evidence':safe}
            if isinstance(attachment,dict):
                attachment['target_ids']=sorted(set(attachment.get('target_ids',[]))|{current_target_id,new_target_id})
                meta['browser_attachment']=attachment
            db.execute('UPDATE application_sessions SET target_id=?,metadata_json=? WHERE id=?',
                       (new_target_id,dumps(meta),session['id']))
            return {'session_id':session['id'],'attempt_id':attempt_id,'job_id':attempt['job_id'],
                    'target_id':new_target_id,'previous_target_id':current_target_id,'url':display}

    def session_stopped(self, session_id, *, reason, paused=False, browser_stopped=False, tabs_closed=False):
        if browser_stopped is not True and tabs_closed is not True:raise ProtocolError('owned_browser_stop_evidence_required')
        with self.tx() as db:
            s=self._get(db,'application_sessions',session_id)
            if s['ended_at']:return dict(s)
            now=self.now();reason=safe_text(reason)
            if s['attempt_id']:
                a=self._get(db,'application_attempts',s['attempt_id'])
                # Owned process termination or confirmed application-tab closure
                # establishes document quiescence, including after a host crash.
                db.execute("UPDATE managed_actions SET ended_at=?,status='aborted',uncertainty=1 WHERE attempt_id=? AND ended_at IS NULL",(now,a['id']))
                db.execute("UPDATE application_attempts SET writer_state='idle' WHERE id=?",(a['id'],))
                db.execute("UPDATE owned_targets SET state='closed',evidence=?,updated_at=? WHERE attempt_id=? AND state!='closed'",(reason,now,a['id']))
                pending=self._submission_pending(db,a)
                if not paused and not a['completed_at']:
                    outcome='submission_unknown' if pending else 'interrupted'
                    self._complete(db,a,outcome,reason,quiescent=True,finish_key=hashlib.sha256(dumps([outcome,reason]).encode()).hexdigest(),reconciled=True)
                if a['completed_at']:paused=False
            state='paused' if paused else 'finished' if s['state']=='finishing' else 'failed' if not s['attempt_id'] else 'stopped'
            meta=json.loads(s['metadata_json']);meta.pop('browser_restart',None)
            db.execute('UPDATE application_sessions SET state=?,reason=?,ended_at=?,target_id=NULL,metadata_json=? WHERE id=?',(state,reason,None if paused else now,dumps(meta),s['id']))
            db.execute('DELETE FROM account_coordination WHERE session_id=?',(s['id'],))
            if s['run_id']:
                db.execute('UPDATE runs SET control=?,state=?,ended_at=? WHERE id=?',('paused' if paused else 'stopped','active' if paused else 'completed',None if paused else now,s['run_id']))
                db.execute('UPDATE run_sessions SET ended_at=? WHERE run_id=? AND ended_at IS NULL',(now,s['run_id']))
            return dict(self._get(db,'application_sessions',s['id']))

    def attach_session(self, session_id, driver_id):
        if not driver_id:raise ProtocolError('driver_required')
        with self.tx() as db:
            s=self._get(db,'application_sessions',session_id)
            if s['driver_id']==driver_id and s['state'] in ('connected','waiting','preparing'):return dict(s)
            if s['state']!='paused' or s['ended_at']:raise ProtocolError('stop_previous_driver_before_attach')
            a=self._get(db,'application_attempts',s['attempt_id']) if s['attempt_id'] else None
            db.execute("UPDATE application_sessions SET driver_id=?,state='preparing',reason='Explicit attach after owned browser stopped' WHERE id=?",(driver_id,session_id))
            if a:db.execute('UPDATE application_attempts SET session_id=? WHERE id=?',(driver_id,a['id']))
            db.execute("UPDATE runs SET session_id=?,control='running',state='preparing' WHERE id=?",(driver_id,s['run_id']))
            return dict(self._get(db,'application_sessions',session_id))

    def coordinate_account(self, session_id, *, release=False):
        with self.tx() as db:
            s=self._get(db,'application_sessions',session_id);self._local_owner(db,s)
            job=self._get(db,'jobs',s['job_id'])
            if s['attempt_id']:job=application_job(db,self._get(db,'application_attempts',s['attempt_id']),job)
            namespace=self._job_account_namespace(db,job)
            # Credentials remain tied to candidate/portal. Another browser using
            # that account is not a reason to prevent this session from signing in.
            return {'namespace':namespace,'state':'released' if release else 'available','session_id':session_id}

    def sessions_view(self):
        from collections import defaultdict
        with self.read() as db:
            if not self._has_local_schema(db):return {'sessions':[],'workspaces':[]}
            sessions=[dict(r) for r in db.execute('SELECT * FROM application_sessions ORDER BY requested_at DESC LIMIT 100')]
            workspaces={r['id']:dict(r) for r in db.execute('SELECT * FROM browser_workspaces')}
            ids=[s['attempt_id'] for s in sessions if s['attempt_id'] is not None]
            attempts={};events=defaultdict(list);actions=defaultdict(list)
            if ids:
                placeholders=','.join('?' for _ in ids)
                attempts={r['id']:dict(r) for r in db.execute(f'SELECT * FROM application_attempts WHERE id IN ({placeholders})',ids)}
                for row in db.execute(f'SELECT * FROM managed_events WHERE attempt_id IN ({placeholders}) ORDER BY rowid',ids):
                    events[row['attempt_id']].append(dict(row))
                for row in db.execute(f'SELECT * FROM managed_actions WHERE attempt_id IN ({placeholders})',ids):
                    actions[row['attempt_id']].append(dict(row))
        public_workspaces=[{k:w[k] for k in ('id','state','reason','host_seen_at','config_json')}|
            {'config':json.loads(w['config_json'])} for w in workspaces.values()]
        return {'sessions':[self._session_status_record(s,workspaces.get(s['workspace_id']),attempts.get(s['attempt_id']),
                    events[s['attempt_id']],actions[s['attempt_id']]) for s in sessions],
                'workspaces':public_workspaces}
