import multiprocessing
import pytest
from job_applier.managed import Service, ProtocolError


def ready(tmp_path, count=2, settings=None):
    s=Service.create(tmp_path/'jobs.db',instance_id='test',settings=settings)
    s.identity(identity_id='candidate',person_key='person',email='candidate@example.test',profile={'facts':{'work_authorization':'fixture'},'resume_ref':'asset:fixture-v1'})
    ids=[]
    for i in range(count):
        job=s.intake(url=f'https://careers.example.test/jobs/{i}',source_id=str(i))
        s.eligibility(job['id'],'ready',reason='synthetic operator approval')
        ids.append(job['id'])
    r=s.request_run(request_id='request-1',job_ids=ids,identity_id='candidate',browser_profile='fixture-browser')
    return s,r,ids


def accept(s,r,worker='worker'):
    return s.accept_run(r['id'],worker_id=worker,session_id='session-1',capabilities={'protocol':1,'skill_version':'test-skill','browser_profile':'fixture-browser','provider':'fixture','model':'fixture','telemetry':True})


def test_Q5_Q6_Q7_fixed_batch_awaits_worker_and_requires_policy(tmp_path):
    s,r,ids=ready(tmp_path)
    assert r['state']=='awaiting_worker'
    assert s.request_run(request_id='request-1',job_ids=ids,identity_id='candidate',browser_profile='fixture-browser')['id']==r['id']
    with pytest.raises(ProtocolError,match='awaiting_worker'): s.claim(r['id'],worker_id='worker')
    held=s.intake(url='https://careers.example.test/new')
    with pytest.raises(ProtocolError,match='not_ready'): s.request_run(request_id='bad',job_ids=[held['id']],identity_id='candidate',browser_profile='fixture-browser')
    accept(s,r)
    a=s.claim(r['id'],worker_id='worker')
    assert a['job_id']==ids[0]
    with pytest.raises(ProtocolError,match='owned_elsewhere'): s.claim(r['id'],worker_id='worker')
    s.finish(a['id'],worker_id='worker',fence=a['fence'],outcome='ready_for_review',evidence='fixture review',quiescent=True)
    b=s.claim(r['id'],worker_id='worker')
    assert b['job_id']==ids[1]
    assert b['session_id']=='session-1'


def claim_process(path,run,worker,go,results):
    try:
        s=Service(path)
        go.wait(10)
        try: results.put(('claimed',s.claim(run,worker_id=worker)['id']))
        except ProtocolError as e: results.put(('rejected',e.code))
    except Exception as e:
        results.put(('error', repr(e)))


def test_Q4_real_processes_cannot_share_browser_or_job(tmp_path):
    s,r,ids=ready(tmp_path)
    accept(s,r)
    ctx=multiprocessing.get_context('spawn');go=ctx.Event();results=ctx.Queue()
    ps=[ctx.Process(target=claim_process,args=(str(s.db_path),r['id'],'worker',go,results)) for _ in range(2)]
    try:
        for p in ps:p.start()
        go.set()
        got=[results.get(timeout=20) for _ in ps]
        for p in ps:p.join(20);assert p.exitcode==0
        assert sorted(x[0] for x in got)==['claimed','rejected'], got
    finally:
        for p in ps:
            if p.pid is not None:
                if p.is_alive():
                    p.terminate()
                p.join(5)
        results.close()
        results.join_thread()


def test_R1_R2_R3_restart_expiry_fences_and_idempotence(tmp_path):
    s,r,ids=ready(tmp_path);accept(s,r)
    a=s.claim(r['id'],worker_id='worker')
    reloaded=Service(s.db_path)
    assert reloaded.attempt(a['id'])['outcome'] is None
    with s.tx() as db:db.execute("UPDATE browser_leases SET expires_at='2000-01-01T00:00:00+00:00'")
    with pytest.raises(ProtocolError,match='reconciliation_required'): s.heartbeat(a['id'],worker_id='worker',fence=a['fence'])
    with pytest.raises(ProtocolError,match='reconciliation_required'): s.claim(r['id'],worker_id='worker')
    s.reconcile(a['id'],outcome='interrupted',evidence='fixture process stopped',browser_quiescent=True)
    b=s.claim(r['id'],worker_id='worker')
    with pytest.raises(ProtocolError):s.finish(a['id'],worker_id='worker',fence=a['fence'],outcome='applied',evidence='stale',quiescent=True)
    result=s.finish(b['id'],worker_id='worker',fence=b['fence'],outcome='ready_for_review',evidence='review',quiescent=True)
    assert s.finish(b['id'],worker_id='worker',fence=b['fence'],outcome='ready_for_review',evidence='review',quiescent=True)==result
    with pytest.raises(ProtocolError,match='conflicting_finish'):s.finish(b['id'],worker_id='worker',fence=b['fence'],outcome='failed',evidence='different',quiescent=True)


def test_Q3_R4_R7_prior_submissions_survive_identity_and_retries(tmp_path):
    s,r,ids=ready(tmp_path);accept(s,r)
    a=s.claim(r['id'],worker_id='worker')
    # Offline fixtures may model a post-click crash without performing a click.
    s.submission_intent(a['id'],worker_id='worker',fence=a['fence'],evidence='fixture action',fixture=True)
    result=s.finish(a['id'],worker_id='worker',fence=a['fence'],outcome='failed',evidence='timeout',quiescent=True)
    assert result['outcome']=='submission_unknown'
    with pytest.raises(ProtocolError,match='reconciliation_required'):s.retry(ids[0])
    s.reconcile(a['id'],outcome='applied',evidence='fixture confirmation ledger',browser_quiescent=True)
    s.identity(identity_id='new-email',person_key='person',email='other@example.test',profile={})
    assert s.intake(url='https://careers.example.test/jobs/0?utm_source=new',source_id='new')['id']==ids[0]
    with pytest.raises(ProtocolError,match='already_applied'):s.retry(ids[0])
    with pytest.raises(ProtocolError,match='already_applied'):s.request_run(request_id='reapply',job_ids=[ids[0]],identity_id='new-email',browser_profile='fixture-browser')
