"""Human answers are durable data, scoped to a question, candidate and job."""
import json

import pytest
from fastapi.testclient import TestClient

from job_applier.managed import Service, ProtocolError
from job_applier.managed_api import create_app
from test_local_sessions import setup, reserve, connect, own


QUESTION = dict(field='leadership', question='Have you led a technology team?', kind='select',
    options=[{'value':'yes','label':'Yes'},{'value':'no','label':'No'}], required=True,
    context={'page':'application_questions','section':'Leadership','document':'https://employer0.example.test/job/0'})


def connected(tmp_path,metadata=None):
    service,asset,jobs,workspaces,config=setup(tmp_path)
    session=service.reserve_session(request_id='answer-fixture',job_id=jobs[0]['id'],identity_id='candidate',
        driver_id='driver',workspace_ids=['workspace-0','workspace-1'],concurrency_limit=2,
        resume_asset_id=asset['id'],metadata=metadata)
    session=connect(service,session)
    return service,session,own(service,session),asset,jobs


def request(service,owner,**changes):
    return service.request_question(**owner,**dict(QUESTION,**changes))


def test_questions_survive_park_and_answers_do_not_write_browser(tmp_path,monkeypatch):
    service,session,owner,_,_=connected(tmp_path)
    question=request(service,owner)
    assert question['state']=='pending' and question['answer'] is None
    parked=service.park_questions(**owner)
    assert parked['status']=='needs_your_answer'
    service.session_stopped(session['id'],reason='Required answer saved for review',browser_stopped=True)
    service=Service(service.db_path,instance_id=service.instance_id)
    monkeypatch.setattr('job_applier.workspace_host.ensure_host',lambda *a,**k:pytest.fail('Saving an answer launched a browser'))
    saved=service.answer_questions(answers=[{'question_id':question['id'],'answer':'Yes','expected_revision':0}])
    assert saved['questions'][0]['answer']=={'value':'yes','label':'Yes'}
    assert saved['questions'][0]['answer_source']=='user_dashboard'
    assert service.job(session['job_id'])['status']=='blocked'
    assert service.answer_queue()['groups'][0]['pending_count']==0
    assert service.session(session['id'])['ended_at']


def test_optional_or_sensitive_questions_and_foreign_owner_are_rejected(tmp_path):
    service,session,owner,_,_=connected(tmp_path)
    with pytest.raises(ProtocolError,match='required_question_only'):request(service,owner,required=False)
    with pytest.raises(ProtocolError,match='private_question_prohibited'):request(service,owner,question='What is your password?')
    foreign=dict(owner,worker_id='other-driver')
    with pytest.raises(ProtocolError):request(service,foreign)
    assert service.answer_queue()['groups']==[]


def test_saved_answer_requires_exact_question_options_and_context(tmp_path):
    service,_,owner,_,_=connected(tmp_path)
    question=request(service,owner)
    service.answer_questions(answers=[{'question_id':question['id'],'answer':'no','expected_revision':0}])
    same=request(service,owner)
    assert same['id']==question['id'] and same['answer']['value']=='no'
    changed=request(service,owner,options=[{'value':'1','label':'Under 5 people'},{'value':'2','label':'5 or more people'}])
    assert changed['id']!=question['id'] and changed['answer'] is None
    changed=request(service,owner,context=dict(QUESTION['context'],section='Financial responsibility'))
    assert changed['id']!=question['id'] and changed['answer'] is None


def test_invalid_choice_and_stale_answer_revision_do_not_overwrite_user_answer(tmp_path):
    service,_,owner,_,_=connected(tmp_path)
    question=request(service,owner)
    with pytest.raises(ProtocolError,match='answer_option_unavailable'):
        service.answer_questions(answers=[{'question_id':question['id'],'answer':'Maybe','expected_revision':0}])
    service.answer_questions(answers=[{'question_id':question['id'],'answer':'yes','expected_revision':0}])
    with pytest.raises(ProtocolError,match='answer_revision_conflict'):
        service.answer_questions(answers=[{'question_id':question['id'],'answer':'no','expected_revision':0}])
    assert request(service,owner)['answer']['value']=='yes'


def test_duplicate_html_values_require_the_exact_offered_option(tmp_path):
    service,_,owner,_,_=connected(tmp_path)
    question=request(service,owner,kind='radio',options=[{'value':'on','label':'Yes'},{'value':'on','label':'No'}])
    with pytest.raises(ProtocolError,match='answer_option_unavailable'):
        service.answer_questions(answers=[{'question_id':question['id'],'answer':'on','expected_revision':0}])
    exact={'value':'on','label':'Yes'}
    saved=service.answer_questions(answers=[{'question_id':question['id'],'answer':exact,'expected_revision':0}])
    assert saved['questions'][0]['answer']==exact


def test_retry_queue_waits_for_all_answers_and_stopped_browser(tmp_path):
    service,session,owner,_,_=connected(tmp_path)
    first=request(service,owner)
    second=request(service,owner,field='start_date',question='When can you start?',kind='text',options=[])
    with pytest.raises(ProtocolError,match='unanswered_questions'):
        service.queue_answer_retries(job_ids=[session['job_id']],identity_id='candidate')
    service.answer_questions(answers=[{'question_id':first['id'],'answer':'yes','expected_revision':0},
        {'question_id':second['id'],'answer':'After two weeks notice','expected_revision':0}])
    with pytest.raises(ProtocolError):
        service.queue_answer_retries(job_ids=[session['job_id']],identity_id='candidate')
    # Park is still allowed after a quick reply; the stopped attempt can retry.
    service.finish(**owner,outcome='blocked',evidence='Synthetic answer review',quiescent=False)
    service.session_stopped(session['id'],reason='Review complete',browser_stopped=True)
    queued=service.queue_answer_retries(job_ids=[session['job_id']],identity_id='candidate')
    assert queued['requests'][0]['state']=='queued'
    assert service.answer_retries(identity_id='candidate')['requests'][0]['job_id']==session['job_id']
    again=service.queue_answer_retries(job_ids=[session['job_id']],identity_id='candidate')
    assert again['requests'][0]['id']==queued['requests'][0]['id']


def test_question_and_retry_endpoints_respect_operator_and_worker_roles(tmp_path):
    service,session,owner,_,_=connected(tmp_path)
    question=request(service,owner)
    operator='operator-'+('a'*30);worker='worker-'+('b'*30)
    app=create_app(service,operator_token=operator,worker_tokens={worker:owner['worker_id']})
    with TestClient(app,base_url='http://127.0.0.1') as client:
        worker_headers={'Authorization':'Bearer '+worker,'X-JobBot-Instance':service.instance_id}
        payload={'answers':[{'question_id':question['id'],'answer':'yes','expected_revision':0}]}
        assert client.post('/v1/answer_questions',json=payload,headers=worker_headers).status_code==403
        assert client.post('/v1/answer_queue',json={},headers=worker_headers).status_code==403
        operator_headers={'Authorization':'Bearer '+operator,'X-JobBot-Instance':service.instance_id}
        result=client.post('/v1/answer_questions',json=payload,headers=operator_headers)
        assert result.status_code==200,result.text


def test_harness_without_messaging_still_has_dashboard_path(tmp_path):
    service,session,owner,_,_=connected(tmp_path)
    request(service,owner)
    context=service.application_context(owner['attempt_id'])
    assert context['human_input']['messaging']['available'] is False
    assert context['human_input']['fallback']=='answer_queue'


def test_messaging_capability_is_session_metadata_not_a_core_discord_dependency(tmp_path):
    metadata={'human_input':{'messaging':{'available':True,'channel':'discord','tool':'send_message','reply_mode':'conversation'}}}
    service,session,owner,_,_=connected(tmp_path,metadata)
    context=service.application_context(owner['attempt_id'])
    assert context['human_input']['messaging']['available'] is True
    assert context['human_input']['messaging']['channel']=='discord'
    assert context['human_input']['fallback']=='answer_queue'


@pytest.mark.parametrize('outcome',['submission_unknown','failed'])
def test_answers_never_make_uncertain_submission_retryable(tmp_path,outcome):
    service,session,owner,asset,_=connected(tmp_path)
    question=request(service,owner)
    service.answer_questions(answers=[{'question_id':question['id'],'answer':'yes','expected_revision':0}])
    service.report_upload(**owner,asset_id=asset['id'],status='upload_attempted',evidence='Synthetic approved upload dispatch')
    service.report_upload(**owner,asset_id=asset['id'],status='upload_confirmed',evidence='Synthetic uploaded file name verified')
    service.submission_intent(**owner,fixture=True,evidence='Synthetic submission intent; no employer contacted')
    with pytest.raises(ProtocolError,match='submission_pending_read_only'):service.park_questions(**owner)
    service.finish(**owner,outcome=outcome,evidence='Synthetic uncertain dispatch',quiescent=False)
    service.session_stopped(session['id'],reason='Synthetic browser stopped',browser_stopped=True)
    with pytest.raises(ProtocolError):service.queue_answer_retries(job_ids=[session['job_id']],identity_id='candidate')
    assert service.answer_retries(identity_id='candidate')['requests']==[]


def test_answers_are_not_reused_for_another_job(tmp_path):
    service,session,owner,asset,jobs=connected(tmp_path)
    first=request(service,owner)
    service.answer_questions(answers=[{'question_id':first['id'],'answer':'yes','expected_revision':0}])
    service.finish(**owner,outcome='blocked',evidence='Synthetic fixture completed',quiescent=False)
    service.session_stopped(session['id'],reason='Synthetic browser stopped',browser_stopped=True)
    next_session=connect(service,reserve(service,asset,jobs,index=1))
    second=request(service,own(service,next_session))
    assert second['answer'] is None and second['job_id']!=first['job_id']


def test_hermes_advertises_observed_tools_and_requires_a_new_user_reply(tmp_path):
    from job_applier.hermes_plugin import PluginController
    controller=PluginController(None)
    controller.route('pre_api_request',session_id='reply-driver',turn_id='initial',platform='cli',
        user_message='Apply to the requested job',request={'body':{'tools':[]}})
    assert controller.human_input['reply-driver']['messaging']['available'] is False
    service,session,owner,_,_=connected(tmp_path)
    question=request(service,owner)
    cfg={'db_path':str(service.db_path),'instance_id':service.instance_id,'identity_id':'candidate'}
    answer={'answers':[{'question_id':question['id'],'answer':'yes','expected_revision':0}]}
    with pytest.raises(ProtocolError,match='user_reply_predates_question'):
        controller._handle_local(cfg,'answer',answer,'reply-driver')
    controller.route('pre_api_request',session_id='reply-driver',turn_id='reply',platform='discord',
        user_message='Yes, I have led a technology team.',request={'body':{'tools':[{'type':'function','function':{'name':'send_message'}}]}})
    assert controller.human_input['reply-driver']['messaging']['channel']=='discord'
    saved=controller._handle_local(cfg,'answer',answer,'reply-driver')
    assert saved['questions'][0]['answer_source']=='user_reply'
    with pytest.raises(ProtocolError,match='user_reply_predates_answer'):
        controller._handle_local(cfg,'answer',{'answers':[{'question_id':question['id'],'answer':'no','expected_revision':1}]},'reply-driver')
    # Only a hash and turn id, not the raw user's message, are persisted as evidence.
    with service.tx() as db:
        evidence=db.execute('SELECT evidence FROM application_question_answers').fetchone()[0]
    assert 'led a technology' not in evidence and 'hermes_turn:reply-driver:reply:' in evidence
