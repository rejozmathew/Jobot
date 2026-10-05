"""Observed aliases and factual retry context; no production history rewrites."""
import json

from test_local_sessions import setup, reserve, connect, own


def test_observed_employer_posting_links_different_intake_records(tmp_path):
    from job_applier.managed_identity import linked_jobs
    service,asset,jobs,_,_=setup(tmp_path)
    posting='https://job-boards.greenhouse.io/fixture/jobs/123456'
    for i in range(2):
        session=connect(service,reserve(service,asset,jobs,index=i),f'target-{i}')
        service.handoff_target(**own(service,session),current_target_id=f'target-{i}',new_target_id=f'target-{i}',
            url=posting,expected_url=posting,evidence='Synthetic observed exact Apply link')
    with service.tx() as db:
        assert set(linked_jobs(db,jobs[0]['id']))=={jobs[0]['id'],jobs[1]['id']}
    assert service.job(jobs[0]['id'])['url']==jobs[0]['url']
    assert service.job(jobs[1]['id'])['url']==jobs[1]['url']


def test_new_ukg_intake_reuses_observed_posting_alias(tmp_path):
    service,asset,jobs,_,_=setup(tmp_path)
    posting='https://recruiting.ultipro.com/EXA1000/JobBoard/1/OpportunityDetail?opportunityId=11111111-1111-4111-8111-111111111111'
    session=connect(service,reserve(service,asset,jobs),'target-0')
    service.handoff_target(**own(service,session),current_target_id='target-0',new_target_id='target-0',
        url=posting,expected_url=posting,evidence='Synthetic observed employer route')
    assert service.intake(url=posting.replace('/JobBoard/1/','/JobBoard/2/'))['id']==jobs[0]['id']
    assert service.job(jobs[0]['id'])['url']==jobs[0]['url']


def test_stats_distinguish_explicit_already_applied_evidence_and_aliases(tmp_path):
    service,asset,jobs,_,_=setup(tmp_path)
    service.now=lambda:'2026-10-05T02:00:00+00:00'
    with service.tx() as db:
        for job in jobs[:2]:db.execute('INSERT INTO job_identity_keys VALUES (?,?,?)',('same-observed-posting',job['id'],'Synthetic observed posting'))
        for i,(job,outcome,evidence) in enumerate([
            (jobs[0],'applied','employer: Thank you for applying'),
            (jobs[1],'applied',"employer: You've already applied to this position"),
            (jobs[2],'blocked','Not previously applied; required question unresolved')]):
            db.execute('INSERT INTO application_attempts(id,job_id,platform,started_at,completed_at,outcome,evidence) VALUES (?,?,\'fixture\',?,?,?,?)',
                (700+i,job['id'],'2026-10-05T00:00:00+00:00','2026-10-05T01:00:00+00:00',outcome,evidence))
    result=service.activity_stats(period='1d')
    assert result['attempts']==3 and result['jobs']==2 and result['recorded_jobs']==3
    assert result['submitted_jobs']==1
    assert result['outcomes']=={'applied':1,'already_applied':1,'blocked':1}
    assert result['recorded_outcomes']=={'applied':2,'blocked':1}
    assert result['submission_rate_per_attempt']==100/3
    assert result['submission_rate_per_job']==50
    with service.tx() as db:
        assert db.execute('SELECT outcome FROM application_attempts WHERE id=701').fetchone()[0]=='applied'


def test_retry_retains_older_obstacle_and_current_answer_after_interruptions(tmp_path):
    service,asset,jobs,_,_=setup(tmp_path)
    session=connect(service,reserve(service,asset,jobs))
    owner=own(service,session)
    question=service.request_question(**owner,field='eligible',question='Are you eligible for this shift?',
        kind='radio',options=[{'value':'yes','label':'Yes'},{'value':'no','label':'No'}],required=True)
    service.answer_questions(answers=[{'question_id':question['id'],'expected_revision':question['revision'],'answer':'Yes'}])
    with service.tx() as db:
        db.execute("UPDATE application_attempts SET outcome='blocked',completed_at=?,evidence='Needs an approved answer for shift eligibility' WHERE id=?",(service.now(),session['attempt_id']))
        for _ in range(4):
            db.execute("INSERT INTO application_attempts(job_id,identity_id,platform,started_at,completed_at,outcome,evidence) VALUES (?,?,'fixture',?,?,'interrupted','Previous host died')",
                (jobs[0]['id'],'candidate',service.now(),service.now()))
    prior=service.prior_application_history(jobs[0]['id'],'candidate')
    assert len(prior['attempts'])==3 and prior['total_prior_attempts']==5
    assert prior['last_obstacle']['attempt_id']==session['attempt_id']
    assert prior['questions'][0]['answer']=={'value':'yes','label':'Yes'}
    assert prior['questions'][0]['revision']==question['revision']+1
    assert 'historical' in prior['instruction'].lower()


def test_retained_verified_ukg_routes_link_without_guessing_titles(tmp_path):
    from job_applier.managed_identity import retain_observed_posting_aliases,linked_jobs
    service,asset,jobs,_,_=setup(tmp_path)
    routes=['https://recruiting.ultipro.com/EXA1000/JobBoard/1/OpportunityDetail?opportunityId=11111111-1111-4111-8111-111111111111',
            'https://recruiting.ultipro.com/EXA1000/JobBoard/2/OpportunityDetail?opportunityId=11111111-1111-4111-8111-111111111111']
    for i,route in enumerate(routes):
        session=connect(service,reserve(service,asset,jobs,index=i),f'target-{i}')
        service.handoff_target(**own(service,session),current_target_id=f'target-{i}',new_target_id=f'target-{i}',
            url=route,expected_url=route,evidence='Synthetic observed employer route')
    with service.tx() as db:
        # Simulate a pre-upgrade ledger with retained verified route metadata.
        db.execute("DELETE FROM job_identity_keys WHERE evidence='observed_posting_identity'")
        retain_observed_posting_aliases(db)
        assert set(linked_jobs(db,jobs[0]['id']))=={jobs[0]['id'],jobs[1]['id']}
