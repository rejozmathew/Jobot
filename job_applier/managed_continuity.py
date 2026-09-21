"""Durable run checkpoints; continuity does not require one conversation per job."""
from .managed_shared import ProtocolError, dumps
from .managed_redaction import reject_secrets, safe_text


class ContinuityServices:
    def checkpoint(self, run_id, *, worker_id, session_id, checkpoint_id, data):
        if not isinstance(data,dict) or set(data)-{'summary','next_job_id'} or not checkpoint_id:raise ProtocolError('invalid_checkpoint')
        reject_secrets(data)
        data={**data,'summary':safe_text(data.get('summary',''))}
        with self.tx() as db:
            run=self._get(db,'runs',run_id)
            if self._has_local_schema(db) and db.execute('SELECT 1 FROM application_sessions WHERE run_id=?',(run_id,)).fetchone():
                raise ProtocolError('use_local_session_handle')
            if run['worker_id']!=worker_id or run['session_id']!=session_id:raise ProtocolError('stale_session')
            existing=db.execute('SELECT * FROM run_checkpoints WHERE id=?',(checkpoint_id,)).fetchone()
            if existing:
                if existing['run_id']!=run_id or existing['worker_id']!=worker_id or existing['session_id']!=session_id or existing['data_json']!=dumps(data):raise ProtocolError('idempotency_conflict')
                return dict(existing)
            if data.get('next_job_id') and not db.execute('SELECT 1 FROM run_jobs WHERE run_id=? AND job_id=?',(run_id,data['next_job_id'])).fetchone():raise ProtocolError('outside_batch')
            lease=db.execute('SELECT * FROM browser_leases WHERE profile=?',(run['browser_profile'],)).fetchone()
            if lease and lease['state']!='released' and (lease['state']!='active' or lease['worker_id']!=worker_id or lease['expires_at']<=self.now()):raise ProtocolError('reconciliation_required')
            db.execute('INSERT INTO run_checkpoints VALUES (?,?,?,?,?,?)',(checkpoint_id,run_id,worker_id,session_id,dumps(data),self.now()))
            db.execute('UPDATE runs SET checkpoint_json=? WHERE id=?',(dumps({'checkpoint_id':checkpoint_id,**data}),run_id))
            return dict(self._get(db,'run_checkpoints',checkpoint_id))

    def resume_run(self, run_id, *, worker_id, session_id, capabilities):
        reject_secrets(capabilities)
        with self.tx() as db:
            run=self._get(db,'runs',run_id)
            if self._has_local_schema(db) and db.execute('SELECT 1 FROM application_sessions WHERE run_id=?',(run_id,)).fetchone():
                raise ProtocolError('use_local_session_attach')
            self._reasoning_matches(run,capabilities)
            if run['worker_id']!=worker_id:raise ProtocolError('owned_elsewhere')
            if run['state'] not in ('accepted','active') or run['control'] in ('stopped','stop_requested'):raise ProtocolError('run_not_resumable')
            if capabilities.get('protocol')!=1 or not all(capabilities.get(k) for k in ('skill_version','provider','model','telemetry')) or capabilities.get('browser_profile')!=run['browser_profile']:raise ProtocolError('unsupported_capability')
            if not session_id:raise ProtocolError('session_required')
            lease=db.execute('SELECT * FROM browser_leases WHERE profile=?',(run['browser_profile'],)).fetchone()
            if lease and lease['state']!='released':raise ProtocolError('reconciliation_required')
            if db.execute('SELECT 1 FROM application_attempts WHERE run_id=? AND completed_at IS NULL',(run_id,)).fetchone():raise ProtocolError('reconciliation_required')
            if run['session_id']==session_id:return dict(run)
            db.execute('UPDATE run_sessions SET ended_at=? WHERE run_id=? AND ended_at IS NULL',(self.now(),run_id))
            db.execute('INSERT INTO run_sessions(run_id,worker_id,session_id,started_at) VALUES (?,?,?,?)',(run_id,worker_id,session_id,self.now()))
            db.execute('UPDATE runs SET session_id=?,capabilities_json=? WHERE id=?',(session_id,dumps(capabilities),run_id))
            return dict(self._get(db,'runs',run_id))
