"""Synthetic agent-neutral protocol exerciser. Never navigates or fills an application."""
from datetime import datetime, timezone
from .managed_shared import ProtocolError, uid


def run(client, *, run_id, worker_id, session_id, browser_profile):
    health=client.call('health')
    if health.get('settings',{}).get('mode')!='development' or health.get('submission_mode')!='review':
        raise ProtocolError('fake_worker_requires_development_review')
    client.call('accept_run',run_id=run_id,worker_id=worker_id,session_id=session_id,capabilities={
        'protocol':1,'skill_version':'fake-worker-v1','browser_profile':browser_profile,
        'provider':'fixture','model':'fixture','telemetry':True})
    outcomes=[]
    while True:
        attempt=client.call('claim',run_id=run_id,worker_id=worker_id)
        if attempt is None:break
        context={'attempt_id':attempt['id'],'worker_id':worker_id,'fence':attempt['fence']}
        client.call('heartbeat',**context)
        action_id=uid()
        client.call('action_start',**context,action_id=action_id,tool_name='fixture_validation')
        # Real protocol validation only. No browser/model/employer transport exists in this worker.
        observed=client.call('attempt_status',attempt_id=attempt['id'])
        if observed['job_id']!=attempt['job_id']:raise ProtocolError('fixture_context_mismatch')
        client.call('action_end',**context,action_id=action_id,status='success')
        client.call('event',**context,event_id=uid(),event_type='phase_changed',observed_at=datetime.now(timezone.utc).isoformat(),payload={'evidence':'Synthetic protocol fixture assertions passed; no form filled.'})
        completed=client.call('finish',**context,outcome='ready_for_review',evidence='Synthetic fixture only; no portal visited or application submitted.',quiescent=True)
        outcomes.append({'attempt_id':completed['id'],'outcome':completed['outcome']})
    return {'run_id':run_id,'outcomes':outcomes}
