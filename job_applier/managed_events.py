"""Immutable events and cooperative controls over the shared service transactions."""
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from .managed_shared import ProtocolError, dumps
from .managed_redaction import safe_payload, safe_text

EVENT_TYPES = frozenset({'tool_started','tool_finished','model_finished','navigation_verified',
    'field_verified','phase_changed','account_verified','checkpoint','recovery','control','outcome'})
PROGRESS_TYPES = frozenset({'navigation_verified','field_verified','account_verified'})


def seconds(end, start):
    return (datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()


class EventServices:
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
        key=hashlib.sha256(dumps([a['id'],worker_id,fence,action_id,event_type,observed_at,duration_seconds,payload]).encode()).hexdigest()
        old=db.execute('SELECT * FROM managed_events WHERE id=?',(event_id,)).fetchone()
        if old:
            if old['request_hash']!=key: raise ProtocolError('idempotency_conflict')
            return dict(old)
        lease=db.execute('SELECT * FROM browser_leases WHERE profile=?',(a['browser_profile'],)).fetchone()
        now=self.now()
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
            return [dict(x) for x in db.execute('SELECT * FROM managed_events WHERE attempt_id=? ORDER BY recorded_at,id',(attempt_id,))]

    def action_start(self, attempt_id, *, worker_id, fence, action_id, tool_name):
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence)
            run=self._get(db,'runs',a['run_id'])
            if run['control']!='running': raise ProtocolError(run['control'])
            old=db.execute('SELECT * FROM managed_actions WHERE id=?',(action_id,)).fetchone()
            if old:
                if old['attempt_id']!=attempt_id or old['tool_name']!=tool_name: raise ProtocolError('idempotency_conflict')
                if old['ended_at']: raise ProtocolError('action_already_finished')
                return dict(old)
            db.execute('INSERT INTO managed_actions(id,attempt_id,tool_name,started_at) VALUES (?,?,?,?)',(action_id,attempt_id,safe_text(tool_name),self.now()))
            if not hasattr(self,'_action_clocks'):self._action_clocks={}
            self._action_clocks[action_id]=time.monotonic()
            return dict(db.execute('SELECT * FROM managed_actions WHERE id=?',(action_id,)).fetchone())

    def action_end(self, attempt_id, *, worker_id, fence, action_id, status):
        if status not in ('success','failed','aborted'):raise ProtocolError('invalid_action_status')
        with self.tx() as db:
            a=self._get(db,'application_attempts',attempt_id)
            if a['worker_id']!=worker_id or a['fence']!=fence:raise ProtocolError('stale_owner')
            action=self._get(db,'managed_actions',action_id)
            if action['attempt_id']!=attempt_id:raise ProtocolError('wrong_attempt')
            if action['ended_at']:
                if action['status']!=status:raise ProtocolError('idempotency_conflict')
                return dict(action)
            start=getattr(self,'_action_clocks',{}).pop(action_id,None)
            duration=time.monotonic()-start if start is not None else None
            db.execute('UPDATE managed_actions SET ended_at=?,status=?,duration_seconds=?,uncertainty=? WHERE id=?',(self.now(),status,duration,int(start is None),action_id))
            self._append_event(db,a,worker_id=worker_id,fence=fence,event_id='action-end:'+action_id,
                action_id=action_id,event_type='tool_finished',observed_at=self.now(),
                duration_seconds=duration,payload={'tool_name':action['tool_name'],'status':status})
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
            if run['state']=='completed' or run['control']=='stopped':raise ProtocolError('run_terminal')
            if command=='resume':
                if run['control']!='paused':raise ProtocolError('not_paused')
                control='running'
            elif command=='pause':
                if run['control'] in ('stop_requested','stopped'):raise ProtocolError('stop_pending')
                control='paused' if run['control']=='paused' else 'pause_requested'
            else:control='stop_requested'
            db.execute('UPDATE runs SET control=? WHERE id=?',(control,run_id))
            return dict(self._get(db,'runs',run_id))

    def _is_quiescent(self, db, a):
        return a['writer_state']=='idle' and not db.execute('SELECT 1 FROM managed_actions WHERE attempt_id=? AND ended_at IS NULL',(a['id'],)).fetchone()

    def ack_control(self, attempt_id, *, worker_id, fence, quiescent):
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence)
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
        a=self.attempt(attempt_id)
        now=self.now()
        settings=json.loads(a['settings_json'])
        elapsed=seconds(a['completed_at'] or now,a['started_at'])
        # Explicit clock uncertainty beats a fabricated negative/exact duration.
        return {**a,'elapsed_seconds':max(0,elapsed),'uncertain_duration':bool(a['uncertain_duration'] or elapsed<0),
            'stalled':not a['completed_at'] and seconds(now,a['progress_at'])>settings.get('no_progress_seconds',45),
            'alive':not a['completed_at'] and seconds(now,a['heartbeat_at'])<settings.get('lease_seconds',60)}
