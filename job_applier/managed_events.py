"""Immutable events and cooperative controls over the shared service transactions."""
import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from .managed_shared import ProtocolError, dumps
from .managed_redaction import safe_payload, safe_text
from .managed_sessions import local_session

EVENT_TYPES = frozenset({'tool_started','tool_finished','model_finished','navigation_verified',
    'field_verified','field_context','phase_changed','account_verified','checkpoint','recovery','control','outcome'})
PROGRESS_TYPES = frozenset({'navigation_verified','field_verified','account_verified'})


def field_task_context(question,*,page='form',document=''):
    """Question labels are semantic context; selected/candidate values are excluded."""
    question=safe_text(question).strip().rstrip('*').strip()
    if not question or question=='[REDACTED]':return {}
    key=hashlib.sha256(dumps([page,document,question]).encode()).hexdigest()[:20]
    page=re.sub(r'[^A-Za-z0-9_.:/-]','_',str(page))[:120] or 'form'
    return {'page':page,'field':key,'category':'required_question','field_label':question,
            'stage_id':'remaining_questions','task_id':'field:'+key,'parent_id':'remaining_questions',
            'activity':'Review and fill “'+question+'”' if '?' in question else 'Fill '+question[:1].lower()+question[1:],
            'task_state':'in_progress','source':'shared_form'}


def seconds(end, start):
    return (datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()


class EventServices:
    def progress(self,attempt_id,*,worker_id,fence,stage,activity,task_id=None,state='in_progress',
                 evidence=None,next_step=None,source='executor',action_id=None):
        """Convenience for executor intent; strict external event timestamps are unchanged."""
        from .managed_reports import STAGE_TITLES
        from .managed_shared import uid
        if stage not in STAGE_TITLES or state not in ('in_progress','completed','recovering','awaiting_input','unsuccessful'):
            raise ProtocolError('invalid_application_progress')
        if not isinstance(activity,str) or not activity.strip():raise ProtocolError('progress_activity_required')
        if state=='completed' and (not isinstance(evidence,str) or not safe_text(evidence).strip() or safe_text(evidence)=='[REDACTED]'):
            raise ProtocolError('progress_completion_evidence_required')
        task_id=task_id or 'activity:'+hashlib.sha256(activity.encode()).hexdigest()[:20]
        if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}',task_id):raise ProtocolError('invalid_progress_task_id')
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence)
            return self._append_event(db,a,worker_id=worker_id,fence=fence,event_id=uid(),action_id=action_id,
                event_type='checkpoint',observed_at=self.now(),duration_seconds=None,payload={
                    'stage_id':stage,'parent_id':stage,'task_id':task_id,'task_state':state,'phase':stage,
                    'activity':activity,'evidence':evidence,'next_step':next_step,'source':source})

    def _submission_state(self, db, attempt):
        from .managed_shared import submission_state
        rows=db.execute('SELECT payload_json,stale,observed_at FROM managed_events WHERE attempt_id=? ORDER BY rowid',(attempt['id'],)).fetchall()
        return submission_state(attempt,rows)

    def _submission_pending(self, db, attempt):
        return self._submission_state(db,attempt)['state'] in ('pending','accepted')

    def record_submission_rejection(self,attempt_id,*,worker_id,fence,proof):
        """Resolve only the fresh employer response for the current captured click."""
        from .managed_shared import submission_state
        if not isinstance(proof,dict):raise ProtocolError('submission_rejection_unproven')
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence)
            rows=db.execute('SELECT * FROM managed_events WHERE attempt_id=? ORDER BY rowid',(attempt_id,)).fetchall()
            current=submission_state(a,rows);dispatch=current['dispatch']
            if current['state']=='rejected' and all(current['resolution'].get(k)==proof.get(k) for k in ('dispatch_id','document_id','frame_id')):
                return {'state':'rejected','submission_pending':False}
            valid=(current['state']=='pending' and dispatch and proof.get('source')=='employer' and
                proof.get('fresh_after_dispatch') is True and proof.get('reason_code') in ('invalid_security_code','expired_security_code','required_fields') and
                all(dispatch.get(k) and proof.get(k)==dispatch[k] for k in ('dispatch_id','document_id','frame_id')))
            try:
                observed=datetime.fromisoformat(proof['observed_at'].replace('Z','+00:00'))
                sent=datetime.fromisoformat(dispatch['observed_at'].replace('Z','+00:00'))
                valid=valid and observed.tzinfo is not None and sent<=observed<=datetime.fromisoformat(self.now())
            except (KeyError,TypeError,ValueError):valid=False
            action=db.execute('SELECT * FROM managed_actions WHERE id=? AND attempt_id=?',(proof.get('dispatch_id'),attempt_id)).fetchone()
            if not valid or not action or action['tool_name']!='browser.submit' or not action['ended_at']:
                raise ProtocolError('submission_rejection_unproven')
            payload={k:proof[k] for k in ('dispatch_id','document_id','frame_id','source','reason_code')}
            payload.update(operation='submission_resolution',status='rejected',phase='submission',resolution='fresh_employer_rejection',
                stage_id='submission',task_id='submit',parent_id='submission',task_state='recovering',
                evidence='Current employer form explicitly rejected this captured submission',
                activity='Application needs correction before submission',next_step='Correct the rejected field or request a fresh email code, then submit once.')
            self._append_event(db,a,worker_id=worker_id,fence=fence,event_id='submission-rejection:'+proof['dispatch_id'],
                action_id=proof['dispatch_id'],event_type='checkpoint',observed_at=proof['observed_at'],duration_seconds=None,payload=payload)
            return {'state':'rejected','submission_pending':False,'dispatch_id':proof['dispatch_id']}

    def _append_event(self, db, a, *, worker_id, fence, event_id, action_id, event_type,
                      observed_at, duration_seconds, payload):
        if event_type not in EVENT_TYPES or not event_id: raise ProtocolError('invalid_event')
        if a['worker_id']!=worker_id or a['fence']!=fence: raise ProtocolError('stale_owner')
        try:
            stamp=datetime.fromisoformat(observed_at)
            if stamp.tzinfo is None: raise ValueError()
        except (TypeError,ValueError): raise ProtocolError('invalid_timestamp')
        if duration_seconds is not None and (not isinstance(duration_seconds,(int,float)) or not math.isfinite(duration_seconds) or duration_seconds<0):
            raise ProtocolError('invalid_duration')
        payload=safe_payload(payload)
        if event_type=='field_context' and payload:
            import re
            if any(not isinstance(payload.get(k),str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}',payload[k]) for k in ('page','field','category')):raise ProtocolError('invalid_semantic_context')
        key=hashlib.sha256(dumps([a['id'],worker_id,fence,action_id,event_type,observed_at,duration_seconds,payload]).encode()).hexdigest()
        old=db.execute('SELECT * FROM managed_events WHERE id=?',(event_id,)).fetchone()
        if old:
            if old['request_hash']!=key: raise ProtocolError('idempotency_conflict')
            return dict(old)
        lease=db.execute('SELECT * FROM browser_leases WHERE profile=?',(a['browser_profile'],)).fetchone()
        now=self.now()
        session=local_session(db,a['id'])
        if session:
            stale=bool(a['completed_at'] or session['ended_at'] or session['state'] not in ('connected','waiting'))
        else:
            stale=bool(a['completed_at'] or not lease or lease['attempt_id']!=a['id'] or lease['generation']!=fence or lease['state']!='active' or lease['expires_at']<=now)
        db.execute('INSERT INTO managed_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (event_id,a['id'],a['run_id'],action_id,worker_id,event_type,observed_at,now,duration_seconds,int(stale),dumps(payload),key))
        if not stale and event_type in PROGRESS_TYPES and payload.get('evidence'):
            # Arrival time cannot turn an old observation into fresh progress.
            progress=min(stamp,datetime.fromisoformat(now)).astimezone(timezone.utc)
            if progress>datetime.fromisoformat(a['progress_at']):
                db.execute('UPDATE application_attempts SET progress_at=? WHERE id=?',(progress.isoformat(),a['id']))
        return dict(db.execute('SELECT * FROM managed_events WHERE id=?',(event_id,)).fetchone())

    def event(self, attempt_id, *, worker_id, fence, event_id, action_id=None, event_type,
              observed_at, duration_seconds=None, payload=None):
        with self.tx() as db:
            a=self._get(db,'application_attempts',attempt_id)
            return self._append_event(db,a,worker_id=worker_id,fence=fence,event_id=event_id,
                action_id=action_id,event_type=event_type,observed_at=observed_at,
                duration_seconds=duration_seconds,payload=payload or {})

    def events(self, attempt_id):
        with self.tx() as db:
            self._get(db,'application_attempts',attempt_id)
            return [dict(x) for x in db.execute('SELECT * FROM managed_events WHERE attempt_id=? ORDER BY rowid',(attempt_id,))]

    def action_start(self, attempt_id, *, worker_id, fence, action_id, tool_name, writes_browser=True):
        if type(writes_browser) is not bool:raise ProtocolError('invalid_writer_flag')
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence)
            if writes_browser:self._budget_check(db,a)
            local=bool(local_session(db,attempt_id))
            stopping=tool_name=='local_browser.simplify_stop' and local
            recovering=tool_name=='local_browser.reload' and local
            cancelling=stopping or recovering
            semantic=self._strategy_check(db,a,tool_name) if writes_browser and not cancelling else self._field_context(db,a)
            run=self._get(db,'runs',a['run_id'])
            if run['control']!='running':
                if writes_browser or tool_name != 'browser_observe' or run['control'] not in ('pause_requested','stop_requested'):
                    raise ProtocolError(run['control'])
            old=db.execute('SELECT * FROM managed_actions WHERE id=?',(action_id,)).fetchone()
            if old:
                if old['attempt_id']!=attempt_id or old['tool_name']!=tool_name or old['writes_browser']!=int(writes_browser): raise ProtocolError('idempotency_conflict')
                if old['ended_at']: raise ProtocolError('action_already_finished')
                return dict(old)
            if writes_browser and ((a['writer_state']!='idle' and not cancelling) or db.execute('SELECT 1 FROM managed_actions WHERE attempt_id=? AND ended_at IS NULL AND writes_browser=1',(attempt_id,)).fetchone()):
                raise ProtocolError('browser_writer_busy')
            db.execute('INSERT INTO managed_actions(id,attempt_id,tool_name,started_at,writes_browser,semantic_context_json) VALUES (?,?,?,?,?,?)',(action_id,attempt_id,safe_text(tool_name),self.now(),int(writes_browser),dumps(semantic)))
            if not hasattr(self,'_action_clocks'):self._action_clocks={}
            self._action_clocks[action_id]=time.monotonic()
            return dict(db.execute('SELECT * FROM managed_actions WHERE id=?',(action_id,)).fetchone(),field_budget_status='measured_context' if semantic else 'coarse_only')

    def action_end(self, attempt_id, *, worker_id, fence, action_id, status, duration_seconds=None, observed_at=None):
        if status not in ('success','failed','aborted'):raise ProtocolError('invalid_action_status')
        if duration_seconds is not None and (type(duration_seconds) not in (int,float) or not math.isfinite(duration_seconds) or duration_seconds<0):
            raise ProtocolError('invalid_duration')
        if observed_at is not None:
            try:
                if datetime.fromisoformat(observed_at).tzinfo is None:raise ValueError()
            except (TypeError,ValueError):raise ProtocolError('timestamp_requires_timezone')
        with self.tx() as db:
            a=self._get(db,'application_attempts',attempt_id)
            if a['worker_id']!=worker_id or a['fence']!=fence:raise ProtocolError('stale_owner')
            action=self._get(db,'managed_actions',action_id)
            if action['attempt_id']!=attempt_id:raise ProtocolError('wrong_attempt')
            if action['ended_at']:
                if action['status']!=status:raise ProtocolError('idempotency_conflict')
                return dict(action)
            start=getattr(self,'_action_clocks',{}).pop(action_id,None)
            duration=duration_seconds if duration_seconds is not None else (time.monotonic()-start if start is not None else None)
            completed_at=observed_at or self.now()
            db.execute('UPDATE managed_actions SET ended_at=?,status=?,duration_seconds=?,uncertainty=? WHERE id=?',(completed_at,status,duration,int(duration is None),action_id))
            self._append_event(db,a,worker_id=worker_id,fence=fence,event_id='action-end:'+action_id,
                action_id=action_id,event_type='tool_finished',observed_at=completed_at,
                duration_seconds=duration,payload={**json.loads(action['semantic_context_json']),'tool_name':action['tool_name'],'status':status})
            return dict(self._get(db,'managed_actions',action_id))

    def writer_state(self, attempt_id, *, worker_id, fence, state):
        if state not in ('idle','active','unknown'):raise ProtocolError('invalid_writer_state')
        with self.tx() as db:
            self._owner(db,attempt_id,worker_id,fence)
            db.execute('UPDATE application_attempts SET writer_state=? WHERE id=?',(state,attempt_id))
            return {'writer_state':state}

    def control(self, run_id, *, command):
        if command not in ('pause','stop','resume'): raise ProtocolError('invalid_control')
        with self.tx() as db:
            run=self._get(db,'runs',run_id)
            return self._control(db,run,command=command)

    def _control(self, db, run, *, command):
        if run['state']=='completed' or run['control']=='stopped':raise ProtocolError('run_terminal')
        if command=='resume':
            if run['control']!='paused':raise ProtocolError('not_paused')
            control='running'
        elif command=='pause':
            if run['control'] in ('stop_requested','stopped'):raise ProtocolError('stop_pending')
            control='paused' if run['control']=='paused' else 'pause_requested'
        else:control='stop_requested'
        db.execute('UPDATE runs SET control=? WHERE id=?',(control,run['id']))
        return dict(self._get(db,'runs',run['id']))

    def _is_quiescent(self, db, a):
        return a['writer_state']=='idle' and not db.execute('SELECT 1 FROM managed_actions WHERE attempt_id=? AND ended_at IS NULL',(a['id'],)).fetchone()

    def ack_control(self, attempt_id, *, worker_id, fence, quiescent):
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence)
            if local_session(db,attempt_id):raise ProtocolError('local_host_must_stop_browser')
            if not quiescent or not self._is_quiescent(db,a):raise ProtocolError('writers_not_quiescent')
            run=self._get(db,'runs',a['run_id'])
            if run['control'] not in ('pause_requested','stop_requested'):raise ProtocolError('no_control_request')
            control='paused' if run['control']=='pause_requested' else 'stopped'
            db.execute('UPDATE runs SET control=? WHERE id=?',(control,a['run_id']))
            return dict(self._get(db,'runs',a['run_id']))

    def ack_run_control(self, run_id, *, worker_id, quiescent):
        """Acknowledge an idle run only after its worker verifies the profile is quiescent."""
        with self.tx() as db:
            run=self._get(db,'runs',run_id)
            if run['worker_id']!=worker_id:raise ProtocolError('owned_elsewhere')
            if not quiescent:raise ProtocolError('writers_not_quiescent')
            if db.execute("SELECT 1 FROM browser_leases WHERE profile=? AND state!='released'",(run['browser_profile'],)).fetchone():raise ProtocolError('writers_not_quiescent')
            if db.execute('SELECT 1 FROM application_attempts WHERE run_id=? AND completed_at IS NULL',(run_id,)).fetchone():raise ProtocolError('writers_not_quiescent')
            if run['control'] in ('paused','stopped'):return dict(run)
            if run['control'] not in ('pause_requested','stop_requested'):raise ProtocolError('no_control_request')
            control='paused' if run['control']=='pause_requested' else 'stopped'
            db.execute('UPDATE runs SET control=? WHERE id=?',(control,run_id))
            if control=='stopped':
                db.execute('UPDATE runs SET ended_at=? WHERE id=?',(self.now(),run_id))
                db.execute('UPDATE run_sessions SET ended_at=? WHERE run_id=? AND ended_at IS NULL',(self.now(),run_id))
            return dict(self._get(db,'runs',run_id))

    def attempt_status(self, attempt_id):
        now=self.now()
        from .managed_views import attempt_timing_state
        with self.tx() as db:a=attempt_timing_state(db,self._get(db,'application_attempts',attempt_id),datetime.fromisoformat(now))
        settings=json.loads(a['settings_json'])
        elapsed=seconds(a['completed_at'] or now,a['started_at'])
        # Explicit clock uncertainty beats a fabricated negative/exact duration.
        if a.get('local_session_id'):
            s=self.session_status(a['local_session_id'])
            return {**a,'elapsed_seconds':max(0,elapsed),'alive':s['host_alive'],
                    'host_alive':s['host_alive'],'driver_recently_active':s['driver_recently_active'],
                    'stalled':not a['completed_at'] and seconds(now,a['progress_at'])>settings.get('no_progress_seconds',45)}
        return {**a,'elapsed_seconds':max(0,elapsed),'uncertain_duration':bool(a['uncertain_duration'] or elapsed<0),
            'stalled':not a['completed_at'] and seconds(now,a['progress_at'])>settings.get('no_progress_seconds',45),
            'alive':not a['completed_at'] and 'ownership_lost_or_expired' not in a['timing_uncertainty_reasons'] and seconds(now,a['heartbeat_at'])<settings.get('lease_seconds',60)}
