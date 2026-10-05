"""Read projection costs use synthetic history and preserve the full detail contract."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import json
import time

from test_local_sessions import setup, reserve, connect, own


def test_session_history_uses_one_snapshot_and_retains_progress(tmp_path, monkeypatch):
    service, asset, jobs, _, _ = setup(tmp_path)
    service.now=lambda:'2026-10-05T02:00:00+00:00'
    sessions=[connect(service,reserve(service,asset,jobs,index=i),f'target-{i}') for i in range(2)]
    for i,session in enumerate(sessions):
        owner=own(service,session)
        service.session_authority=(session['id'],session['driver_id'],'host-'+session['workspace_id'])
        for j in range(15):
            service.event(**owner,event_id=f'e-{i}-{j}',event_type='phase_changed',observed_at=service.now(),
                payload={'phase':'application','activity':f'Work {j}','source':'Synthetic executor'})
    expected={s['id']:service.session_status(s['id']) for s in sessions}
    reads=[];read=service.read
    @contextmanager
    def counted():
        reads.append(1)
        with read() as db:yield db
    monkeypatch.setattr(service,'read',counted)
    actual=service.sessions_view()
    assert {s['id']:s for s in actual['sessions']}==expected
    assert len(reads)==1


def test_four_writers_and_dashboard_with_large_synthetic_history(tmp_path, record_property):
    service,asset,jobs,workspaces,_=setup(tmp_path)
    workspaces[0]['connection_mode']='existing'
    service.configure_workspaces(workspaces)
    service.configure({'application_concurrency':4},expected_version=service.settings_view()['version'])
    sessions=[]
    for index in range(4):
        if index>=len(jobs):
            job=service.intake(url=f'https://fixture.example.test/job/{index}')
            service.eligibility(job['id'],'ready',reason='Synthetic capacity');jobs.append(job)
        pending=service.reserve_session(request_id=f'load-{index}',job_id=jobs[index]['id'],identity_id='candidate',
            driver_id=f'load-{index}',workspace_ids=['workspace-0'],concurrency_limit=4,resume_asset_id=asset['id'])
        sessions.append(connect(service,pending,f'target-{index}'))
    with service.tx() as db:
        db.executemany("INSERT INTO application_attempts(id,job_id,platform,started_at,completed_at,outcome) VALUES (?,?,'fixture','2020-01-01','2020-01-02','interrupted')",
            ((1000+i,jobs[i%4]['id']) for i in range(200)))
        payload=json.dumps({'phase':'application','activity':'Synthetic historical observation','padding':'x'*256})
        db.executemany("INSERT INTO managed_events(id,attempt_id,actor,event_type,observed_at,recorded_at,payload_json,request_hash) VALUES (?,?,'fixture','phase_changed','2020-01-01','2020-01-01',?,'synthetic')",
            ((f'history-{i}',1000+i%200,payload) for i in range(80000)))
        db.executemany("INSERT INTO managed_actions(id,attempt_id,tool_name,started_at,ended_at,status) VALUES (?,?,'synthetic','2020-01-01','2020-01-01','completed')",
            ((f'action-{i}',1000+i%200) for i in range(49000)))
        def query_cost():
            ticks=[];db.set_progress_handler(lambda:ticks.append(1) and 0,100)
            try:db.execute('SELECT * FROM managed_events WHERE attempt_id=?',(sessions[0]['attempt_id'],)).fetchall()
            finally:db.set_progress_handler(None,0)
            return len(ticks)
        indexed=query_cost()
        db.execute('SAVEPOINT baseline')
        db.execute('DROP INDEX events_by_attempt_time')
        scanned=query_cost()
        db.execute('ROLLBACK TO baseline');db.execute('RELEASE baseline')
        assert scanned>1000 and indexed<max(1,scanned//50)
    record_property('history_rows',129000)
    record_property('baseline_query_vm_ticks',scanned)
    record_property('candidate_query_vm_ticks',indexed)
    def write(index):
        owner=own(service,sessions[index])
        for tick in range(8):
            service.event(**owner,event_id=f'writer-{index}-{tick}',event_type='phase_changed',observed_at=service.now(),
                payload={'phase':'application','activity':f'Synthetic progress {tick}','source':'Synthetic executor'})
        return index
    def dashboard():
        for _ in range(4):
            assert len([s for s in service.view()['local_runtime']['sessions'] if not s['ended_at']])==4
    started=time.monotonic()
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures=[pool.submit(write,i) for i in range(4)]+[pool.submit(dashboard)]
        assert [future.result(timeout=60) for future in futures[:4]]==list(range(4))
        futures[-1].result(timeout=60)
    record_property('four_writer_dashboard_seconds',round(time.monotonic()-started,3))
    for session in sessions:
        assert not service.session(session['id'])['ended_at']
