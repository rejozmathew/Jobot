"""Focused lifecycle contracts. Synthetic records only; no employer/browser fixtures."""
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from job_applier.managed import Service, ProtocolError
from job_applier.managed_api import create_app
from job_applier.managed_client import LocalClient
from job_applier.workspace_process import process_identity


def setup(tmp_path):
    service=Service.create(tmp_path/'managed.db',instance_id='local-fixture')
    service.identity(identity_id='candidate',person_key='same-person',email='candidate@example.test',profile={'identity':{'email':'candidate@example.test'}})
    resume=tmp_path/'approved.pdf';resume.write_bytes(b'synthetic document, no extraction')
    asset=service.register_asset(identity_id='candidate',kind='resume',version='1',storage_ref=resume.as_uri(),sha256=hashlib.sha256(resume.read_bytes()).hexdigest(),provenance={'source':'synthetic'})
    workspaces=[{'id':f'workspace-{i}','user_data_dir':str(tmp_path/f'profile-{i}'),'browser_executable':sys.executable,'cdp_url':f'http://127.0.0.1:{19600+i}','mode':'headed'} for i in range(2)]
    service.configure_workspaces(workspaces)
    jobs=[]
    for i in range(3):
        j=service.intake(url=f'https://employer{i}.example.test/job/{i}',required_documents=['resume'])
        service.eligibility(j['id'],'ready',reason='synthetic eligibility');jobs.append(j)
    cfg={'instance_id':service.instance_id,'db_path':str(service.db_path),'transport':'local'}
    return service,asset,jobs,workspaces,cfg


def reserve(s,asset,jobs,index=0,driver=None,request=None):
    return s.reserve_session(request_id=request or f'request-{index}',job_id=jobs[index]['id'],identity_id='candidate',driver_id=driver or f'driver-{index}',workspace_ids=['workspace-0','workspace-1'],concurrency_limit=2,resume_asset_id=asset['id'])


def connect(s,session,target='new-target'):
    s.host_registered(session['workspace_id'],'host-'+session['workspace_id'],process_identity(os.getpid()))
    return s.session_connected(session['id'],'host-'+session['workspace_id'],target,{'synthetic':True})


def own(s,session):
    a=s.attempt(session['attempt_id'])
    return {'attempt_id':a['id'],'worker_id':a['worker_id'],'fence':a['fence']}


def test_local_transport_needs_no_http_or_token(tmp_path,monkeypatch):
    s,asset,jobs,ws,cfg=setup(tmp_path)
    monkeypatch.setattr('httpx.Client',lambda *a,**k:pytest.fail('Local operation opened HTTP'))
    with LocalClient(cfg) as client:
        assert client.call('health')['transport']=='local'
        assert client.call('job',job_id=jobs[0]['id'])['id']==jobs[0]['id']


def test_session_exposes_executor_steps_without_faking_form_progress(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path)
    session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    before=s.session_status(session['id'])['last_verified_progress_at']
    s.event(**owner,event_id='model-step',event_type='phase_changed',observed_at=s.now(),
            payload={'phase':'authentication','activity':'Signing into the employer account',
                     'next_step':'Start Simplify after sign-in','source':'Hermes executor','model':'test-model'})
    s.event(**owner,event_id='raw-tool',event_type='tool_finished',observed_at=s.now(),
            payload={'tool_name':'browser_observe','status':'success'})
    status=s.session_status(session['id'])
    assert status['activity']['payload']['activity']=='Signing into the employer account'
    assert status['activity']['payload']['next_step']=='Start Simplify after sign-in'
    assert status['steps'][0]['payload']['source']=='Hermes executor'
    assert status['last_verified_progress_at']==before
    assert s.attempt_report(session['attempt_id'])['timeline'][0]['payload']['activity']=='Signing into the employer account'


def test_host_records_helper_error_without_closing_session(tmp_path,monkeypatch):
    from job_applier.workspace_host import WorkspaceHost
    s,asset,jobs,ws,cfg=setup(tmp_path);session=connect(s,reserve(s,asset,jobs))
    host=object.__new__(WorkspaceHost);host.service=s;host.config=cfg;host.workspace_id=session['workspace_id']
    def fail(request):raise ProtocolError('observed_control_changed','Refresh the actual employer controls')
    monkeypatch.setattr(host,'_dispatch',fail)
    request={'instance_id':s.instance_id,'session_id':session['id'],'driver_id':session['driver_id'],'operation':'browser'}
    with pytest.raises(ProtocolError,match='observed_control_changed'):host.dispatch(request)
    status=s.session_status(session['id'])
    assert status['state']=='connected' and status['ended_at'] is None
    assert status['activity']['payload']['error_type']=='observed_control_changed'
    assert 'Refresh the actual employer controls' in status['activity']['payload']['evidence']
    assert status['activity']['payload']['source']=='Workspace host'
    assert not s.attempt(session['attempt_id'])['completed_at']
    request['driver_id']='foreign'
    with pytest.raises(ProtocolError):host.dispatch(request)
    assert len(s.session_status(session['id'])['steps'])==1


def test_finished_session_report_remains_readable_without_browser_host(tmp_path,monkeypatch):
    from job_applier.application_runtime import session_call
    s,asset,jobs,ws,cfg=setup(tmp_path);session=connect(s,reserve(s,asset,jobs))
    s.finish(**own(s,session),outcome='blocked',evidence='Synthetic required fact is unknown',quiescent=True)
    s.session_stopped(session['id'],reason='blocked',browser_stopped=True)
    monkeypatch.setattr('job_applier.workspace_host.call_host',lambda *a,**k:pytest.fail('Finished report tried to contact stopped host'))
    assert session_call(cfg,session['id'],'report')['attempt']['outcome']=='blocked'


def test_existing_legacy_alias_reservation_is_not_bypassed(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path)
    with s.tx() as db:
        db.execute("INSERT INTO browser_leases VALUES ('old-profile',NULL,'old-worker',1,NULL,'active')")
    ws[0]['legacy_profiles']=['old-profile'];s.configure_workspaces(ws)
    assert reserve(s,asset,jobs)['workspace_id']=='workspace-1'


def test_failed_host_launch_releases_unstarted_reservation(tmp_path,monkeypatch):
    from job_applier import application_runtime,workspace_host
    s,asset,jobs,ws,cfg=setup(tmp_path)
    cfg.update(config_path=str(tmp_path/'config.json'),workspaces=ws,identity_id='candidate',resume_asset_id=asset['id'])
    def fail(*args):raise ProtocolError('host_start_failed','synthetic process launch failure')
    monkeypatch.setattr(workspace_host,'ensure_host',fail)
    result=application_runtime.start(cfg,job_id=jobs[0]['id'],driver_id='driver')
    assert result['state']=='failed' and result['attempt_id'] is None
    assert result['ended_at'] and 'synthetic process launch failure' in result['reason']


def test_pause_during_start_can_attach_without_an_attempt(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path)
    initial=reserve(s,asset,jobs)
    s.session_stopped(initial['id'],reason='paused before browser readiness',paused=True,browser_stopped=True)
    attached=s.attach_session(initial['id'],'replacement')
    assert attached['state']=='preparing' and attached['attempt_id'] is None
    assert connect(s,attached)['attempt_id'] is not None


def test_start_reservation_is_idempotent_and_not_running_before_readiness(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path)
    session=reserve(s,asset,jobs)
    assert session['state']=='preparing' and session['attempt_id'] is None
    assert s.job(jobs[0]['id'])['status']=='queued'
    assert reserve(s,asset,jobs)['id']==session['id']
    with s.tx() as db:assert db.execute('SELECT COUNT(*) FROM application_attempts').fetchone()[0]==0
    active=connect(s,session)
    assert reserve(s,asset,jobs)['attempt_id']==active['attempt_id']
    with s.tx() as db:
        assert db.execute('SELECT COUNT(*) FROM application_attempts').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM browser_leases').fetchone()[0]==0


def test_two_sessions_capacity_and_late_reasoning_gap(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path)
    a=connect(s,reserve(s,asset,jobs,0),'target-a')
    b=connect(s,reserve(s,asset,jobs,1),'target-b')
    c=reserve(s,asset,jobs,2)
    assert a['workspace_id']!=b['workspace_id'] and c['state']=='capacity_wait'
    later=datetime.now(timezone.utc)+timedelta(seconds=180)
    s.now=lambda:later.isoformat()
    s.session_authority=(a['id'],a['driver_id'],'host-'+a['workspace_id'])
    assert s.heartbeat(**own(s,a))['control']=='running'
    action=s.action_start(**own(s,a),action_id='after-model-gap',tool_name='fixture-write')
    s.action_end(**own(s,a),action_id=action['id'],status='success')
    assert s.session_status(a['id'])['last_verified_progress_at']!=s.now()


def test_http_worker_cannot_take_local_session_or_profile(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path)
    session=connect(s,reserve(s,asset,jobs))
    app=create_app(Service(s.db_path),operator_token='synthetic-operator-'+'o'*24,worker_tokens={'synthetic-worker-'+'w'*24:own(s,session)['worker_id']})
    client=TestClient(app,base_url='http://127.0.0.1')
    headers={'Authorization':'Bearer synthetic-worker-'+'w'*24,'X-JobBot-Instance':s.instance_id}
    r=client.post('/v1/heartbeat',json=own(s,session),headers=headers)
    assert r.json()['error']=='local_session_transport_required'
    assert client.get('/v1/health').status_code==401


def test_stop_a_preserves_b_and_submission_history(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path)
    a=connect(s,reserve(s,asset,jobs,0),'target-a')
    b=connect(s,reserve(s,asset,jobs,1),'target-b')
    s.session_authority=(a['id'],a['driver_id'],'host-'+a['workspace_id'])
    s.submission_intent(**own(s,a),evidence='synthetic uncertain click',fixture=True)
    s.session_stopped(a['id'],reason='Synthetic owned process confirmed stopped',browser_stopped=True)
    assert s.attempt(a['attempt_id'])['outcome']=='submission_unknown'
    s.session_authority=(b['id'],b['driver_id'],'host-'+b['workspace_id'])
    assert s.heartbeat(**own(s,b))['control']=='running'
    assert reserve(s,asset,jobs,2)['workspace_id']==a['workspace_id']


def test_attach_requires_stopped_browser_and_uses_fresh_target(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path)
    a=connect(s,reserve(s,asset,jobs),'old-target')
    with pytest.raises(ProtocolError,match='stop_previous_driver'):s.attach_session(a['id'],'second-driver')
    s.control(a['run_id'],command='pause')
    with pytest.raises(ProtocolError,match='local_host_must_stop_browser'):s.ack_control(**own(s,a),quiescent=True)
    s.session_stopped(a['id'],reason='Synthetic process tree terminated',paused=True,browser_stopped=True)
    paused=s.attach_session(a['id'],'second-driver')
    with s.tx() as db:assert s._get(db,'runs',a['run_id'])['control']=='running'
    resumed=connect(s,paused,'fresh-target')
    assert resumed['attempt_id']==a['attempt_id'] and resumed['target_id']=='fresh-target'
    with s.tx() as db:assert db.execute('SELECT state FROM owned_targets WHERE target_id=?',('old-target',)).fetchone()[0]=='closed'


def test_account_survives_failed_attempt_and_coordination_is_per_portal(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path)
    a=connect(s,reserve(s,asset,jobs,0),'target-a')
    b=connect(s,reserve(s,asset,jobs,1),'target-b')
    for session,index in ((a,0),(b,1)):
        s.session_authority=(session['id'],session['driver_id'],'host-'+session['workspace_id'])
        assert s.coordinate_account(session['id'])['state']=='available'
    s.session_authority=(a['id'],a['driver_id'],'host-'+a['workspace_id'])
    s.record_account_event(**own(s,a),namespace='employer0.example.test',state='confirmed',credential_ref='credential:configured',request_id='account-created',evidence='Synthetic portal account confirmation')
    s.session_stopped(a['id'],reason='Synthetic failure after account creation',browser_stopped=True)
    assert s.account_strategy(namespace='employer0.example.test',identity_id='candidate')['action']=='sign_in'
