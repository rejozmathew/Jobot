"""Calendar-day reports and delivery receipts, using synthetic application history."""
import json
from datetime import datetime,timezone,timedelta

from test_submission_notifications import fixture,complete


def config_daily(config):
    config['submission_notifications']['daily_summary']={'enabled':True,'time':'08:00','timezone':'America/Chicago'}
    return config


def test_daily_summary_counts_attempts_and_new_submissions_separately(tmp_path):
    from job_applier.daily_summary import application_day
    service,asset,jobs,config,clock=fixture(tmp_path)
    clock[0]=datetime(2026,10,7,15,tzinfo=timezone.utc)
    complete(service,asset,jobs)
    complete(service,asset,jobs,index=1,outcome='blocked')
    complete(service,asset,jobs,index=2,outcome='already_applied')
    report=application_day(service,'2026-10-07',timezone_name='America/Chicago')
    assert report['submitted_jobs']==1
    assert report['attempts']==3 and report['attempted_jobs']==3
    assert report['already_applied_jobs']==1 and report['without_submission_jobs']==1
    assert report['attempts_for_submitted_jobs']==1


def test_summary_uses_completion_day_and_excludes_prior_application_evidence(tmp_path):
    from job_applier.daily_summary import application_day
    service,asset,jobs,config,clock=fixture(tmp_path)
    clock[0]=datetime(2026,10,7,4,59,tzinfo=timezone.utc)
    result=complete(service,asset,jobs)
    with service.tx() as db:
        db.execute('UPDATE application_attempts SET completed_at=? WHERE id=?',('2026-10-07T05:02:00+00:00',result['id']))
        db.execute('UPDATE submission_ledger SET recorded_at=? WHERE job_id=?',('2026-10-07T05:02:00+00:00',jobs[0]['id']))
    report=application_day(service,'2026-10-07',timezone_name='America/Chicago')
    assert report['submitted_jobs']==1 and report['attempts']==0
    with service.tx() as db:
        db.execute("UPDATE application_attempts SET evidence=? WHERE id=?",("Simplify: You've already applied to this job",result['id']))
    assert application_day(service,'2026-10-07',timezone_name='America/Chicago')['submitted_jobs']==0


def test_daily_summary_delivered_at_eight_once_across_restart(tmp_path):
    from job_applier.hermes_notifications import poll
    service,asset,jobs,config,clock=fixture(tmp_path);config_daily(config)
    clock[0]=datetime(2026,10,7,15,tzinfo=timezone.utc)
    poll(config,service,sender=lambda c,t:{})
    complete(service,asset,jobs)
    sent=[];send=lambda c,t:sent.append(t) or {'message_id':'daily-1'}
    poll(config,service,sender=send);sent.clear()
    clock[0]=datetime(2026,10,8,12,59,tzinfo=timezone.utc)
    poll(config,service,sender=send)
    assert sent==[]
    clock[0]+=timedelta(minutes=1)
    poll(config,service,sender=send)
    assert len(sent)==1 and '2026-10-07' in sent[0]
    assert 'Jobs submitted: 1' in sent[0] and 'Application attempts: 1' in sent[0]
    poll(config,service,sender=send)
    assert len(sent)==1


def test_daily_failure_retries_frozen_counts_without_replaying_submission_alerts(tmp_path):
    from job_applier.hermes_notifications import poll
    service,asset,jobs,config,clock=fixture(tmp_path);config_daily(config)
    clock[0]=datetime(2026,10,7,15,tzinfo=timezone.utc)
    poll(config,service,sender=lambda c,t:{})
    clock[0]=datetime(2026,10,8,13,tzinfo=timezone.utc)
    def unavailable(c,t):raise TimeoutError('secret must not appear')
    poll(config,service,sender=unavailable)
    state=json.loads((tmp_path/'private/notifications/submissions.json').read_text())
    assert 'secret must not appear' not in json.dumps(state)
    clock[0]+=timedelta(minutes=6)
    sent=[]
    poll(config,service,sender=lambda c,t:sent.append(t) or {})
    assert len(sent)==1 and 'Jobs submitted: 0' in sent[0]


def test_daylight_saving_day_boundaries(tmp_path):
    from job_applier.daily_summary import application_day
    service,asset,jobs,config,clock=fixture(tmp_path)
    clock[0]=datetime(2026,11,1,6,30,tzinfo=timezone.utc)
    complete(service,asset,jobs)
    clock[0]=datetime(2026,11,1,7,30,tzinfo=timezone.utc)
    complete(service,asset,jobs,index=1,outcome='blocked')
    report=application_day(service,'2026-11-01',timezone_name='America/Chicago')
    assert report['attempts']==2
    assert report['start_at']=='2026-11-01T05:00:00+00:00'
    assert report['end_at']=='2026-11-02T06:00:00+00:00'


def test_counts_duplicate_skips_once_and_six_attempt_milestone(tmp_path):
    from job_applier.daily_summary import application_day
    service,asset,jobs,config,clock=fixture(tmp_path)
    clock[0]=datetime(2026,10,7,15,tzinfo=timezone.utc)
    complete(service,asset,jobs)
    import pytest
    from job_applier.managed import ProtocolError
    for request in ('again','again2'):
        with pytest.raises(ProtocolError,match='already_applied'):
            service.queue_enqueue(job_ids=[jobs[0]['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id=request)
    with service.tx() as db:
        for i in range(6):
            request='first-series' if i==0 else 'automatic-retry:dispatch-'+str(i-1)
            db.execute('''INSERT INTO dispatch_queue(id,request_id,job_id,identity_id,resume_asset_id,state,created_at,started_at,ended_at,outcome)
                VALUES (?,?,?,?,?,'finished',?,?,?,'blocked')''',('dispatch-'+str(i),request,jobs[1]['id'],'candidate',asset['id'],service.now(),service.now(),service.now()))
    report=application_day(service,'2026-10-07',timezone_name='America/Chicago')
    assert report['duplicate_jobs_skipped']==1 and report['automatic_limit_jobs']==1


def test_successful_posting_is_counted_once_across_linked_source_records(tmp_path):
    from job_applier.daily_summary import application_day
    from test_job_duplicates import enable,pair
    service,asset,jobs,config,clock=fixture(tmp_path);enable(service,'shadow')
    first,second=pair(service,first_title='Director, Analytics',second_title='Director, Analytics')
    for job in (first,second):service.eligibility(job['id'],'ready',reason='synthetic ready')
    clock[0]=datetime(2026,10,7,15,tzinfo=timezone.utc)
    complete(service,asset,[first,second],index=0)
    complete(service,asset,[first,second],index=1)
    enable(service,'enforce')
    report=application_day(service,'2026-10-07',timezone_name='America/Chicago')
    assert report['submitted_jobs']==1 and report['attempted_jobs']==1 and report['attempts']==2
