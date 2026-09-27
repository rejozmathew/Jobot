"""Retry memory is advisory, candidate scoped, and contains no stale controls."""
import json
from datetime import datetime,timedelta
from test_apply_target_handoff import connected
from test_dispatch_queue import runtime_fixture,enqueue
from job_applier.application_answers import save_answer_history


def test_history_is_scoped_and_current_attempt_is_excluded(tmp_path):
    service,session,owner,_=connected(tmp_path)
    assert service.prior_application_history(session['job_id'],session['identity_id'],exclude_attempt=owner['attempt_id'])['attempts']==[]
    service.finish(**owner,outcome='blocked',evidence='Synthetic required control unavailable',quiescent=False)
    memory=service.prior_application_history(session['job_id'],session['identity_id'])
    assert memory['attempts'][0]['outcome']=='blocked'
    assert 'Synthetic required control unavailable' in memory['attempts'][0]['evidence']
    assert service.prior_application_history(session['job_id'],'another-candidate')['attempts']==[]


def test_verified_answers_reuse_exact_profile_and_authorized_attempts(tmp_path):
    from job_applier.application_answers import reusable_answers
    cfg={'spool_dir':str(tmp_path)}
    package={'job':{'id':'job','url':'https://example.test/jobs/1'},
        'attempt':{'identity_id':'candidate','profile_hash':'same'},'profile_hash':'same'}
    row={'field':'question','question':'Eligible?','answer':'Yes','answer_value':True,
         'question_key':'exact','verified':True,'answer_basis':'approved_profile'}
    save_answer_history(cfg,package,1,[row],page='form',source='greenhouse_fast')
    package['prior_attempts']={'attempts':[{'attempt_id':1,'job_id':'job','profile_hash':'same'}]}
    assert reusable_answers(cfg,package,2,source='greenhouse_fast')['exact']['answer_value'] is True
    package['profile_hash']='changed'
    assert reusable_answers(cfg,package,2,source='greenhouse_fast')=={}
    package['profile_hash']='same';package['attempt']['identity_id']='another'
    assert reusable_answers(cfg,package,2,source='greenhouse_fast')=={}


def test_legacy_verified_journal_uses_authoritative_attempt_provenance(tmp_path):
    from job_applier.application_answers import reusable_answers
    folder=tmp_path/'answers';folder.mkdir()
    (folder/'attempt-1.json').write_text(json.dumps({'attempt_id':1,'job_id':'job','job_url':'https://example.test/jobs/1',
        'answers':[{'source':'greenhouse_fast','verified':True,'question_key':'exact','answer_value':True,'answer_basis':'approved_profile'}]}))
    package={'job':{'id':'job','url':'https://example.test/jobs/1'},'attempt':{'identity_id':'candidate'},'profile_hash':'same',
        'prior_attempts':{'attempts':[{'attempt_id':1,'job_id':'job','profile_hash':'same'}]}}
    assert reusable_answers({'spool_dir':str(tmp_path)},package,2,source='greenhouse_fast')['exact']['answer_value'] is True
    package['prior_attempts']['attempts']=[]
    assert reusable_answers({'spool_dir':str(tmp_path)},package,2,source='greenhouse_fast')=={}


def test_answer_journal_survives_verified_route_change(tmp_path):
    package={'job':{'id':'job','url':'https://example.test/jobs/1'},'attempt':{'identity_id':'candidate'}}
    cfg={'spool_dir':str(tmp_path)}
    row={'field':'eligible','question':'Eligible?','answer':'Yes'}
    save_answer_history(cfg,package,1,[row],page='form',source='employer_form')
    package['job'].update(posting_url=package['job']['url'],url='https://ats.example.test/apply/1')
    result=save_answer_history(cfg,package,1,[dict(row,answer='No')],page='form',source='employer_form')
    assert result['answers_added']==1


def test_fresh_jobs_precede_due_automatic_retries_without_suppressing_retry(tmp_path):
    s,asset,jobs,_,_=runtime_fixture(tmp_path)
    old=enqueue(s,asset,[jobs[0]])['items'][0];s.queue_take()
    s.queue_complete(old['id'],outcome='blocked',detail='Synthetic failure')
    s.queue_reconcile(identity_id='candidate',resume_asset_id=asset['id'])
    later=(datetime.fromisoformat(s.now())+timedelta(hours=3)).isoformat();s.now=lambda:later
    first=s.queue_take();assert first['job_id']==jobs[1]['id']
    s.queue_complete(first['id'],outcome='ready_for_review')
    second=s.queue_take();assert second['job_id']==jobs[2]['id']
    s.queue_complete(second['id'],outcome='ready_for_review')
    assert s.queue_take()['job_id']==jobs[0]['id']
