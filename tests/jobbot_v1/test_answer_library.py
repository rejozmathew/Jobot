"""Reusable current knowledge is separate from immutable application responses."""
import json

import pytest

from job_applier.managed import ProtocolError
from test_answer_queue import connected, request, QUESTION


def save(service, **changes):
    defaults=dict(identity_id='candidate', question=QUESTION['question'], answer='Yes', aliases=[],
        scope='global', scope_key='', conditions={}, expected_revision=0)
    defaults.update(changes)
    return service.save_library_answer(**defaults)


def test_library_answer_resolves_question_with_different_field_context_and_choices(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    entry = save(service)
    question = request(service, owner, field='other-field', context={'page':'different'},
        options=[{'value':'1','label':'Yes'}, {'value':'2','label':'No'}])
    assert question['answer'] == {'value':'1','label':'Yes'}
    assert question['answer_source'] == 'answer_library'
    assert question['library_entry_id'] == entry['id']
    assert question['library_revision'] == 1


def test_library_edit_reconciles_current_response_and_keeps_every_revision(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    question = request(service, owner)
    entry = save(service)
    assert service.questions_for_attempt(owner['attempt_id'])['questions'][0]['answer']['label'] == 'Yes'
    updated = save(service, entry_id=entry['id'], answer='No', expected_revision=1)
    current = service.questions_for_attempt(owner['attempt_id'])['questions'][0]
    assert current['answer']['label'] == 'No' and current['library_revision'] == 2
    with service.tx() as db:
        responses = [json.loads(r[0]) for r in db.execute(
            'SELECT answer_json FROM application_question_answers WHERE question_id=? ORDER BY revision', (question['id'],))]
    assert [r['label'] for r in responses] == ['Yes', 'No']
    assert len(service.answer_library(identity_id='candidate')['entries'][0]['history']) == 2
    with pytest.raises(ProtocolError, match='answer_revision_conflict'):
        save(service, entry_id=entry['id'], expected_revision=1)
    service.set_library_answer_state(entry_id=updated['id'], state='retired', expected_revision=2)
    current = service.questions_for_attempt(owner['attempt_id'])['questions'][0]
    assert current['state'] == 'pending' and current['answer'] is None


def test_library_scopes_and_candidate_isolation(tmp_path):
    service, session, owner, _, jobs = connected(tmp_path)
    save(service, scope='job', scope_key=jobs[1]['id'])
    assert request(service, owner)['answer'] is None
    save(service, scope='job', scope_key=session['job_id'], answer='No')
    assert service.questions_for_attempt(owner['attempt_id'])['questions'][0]['answer']['label'] == 'No'
    service.identity(identity_id='other', person_key='other-person', email='other@example.test', profile={})
    assert service.answer_library(identity_id='other')['entries'] == []


def test_inbox_excludes_submitted_without_changing_pending_history(tmp_path):
    service, session, owner, _, _ = connected(tmp_path)
    question = request(service, owner)
    with service.tx() as db:
        db.execute("UPDATE jobs SET status='applied' WHERE id=?", (session['job_id'],))
    queue = service.answer_queue()
    assert queue['inbox'] == [] and queue['ready'] == []
    assert queue['history_count'] == 1
    historical = service.answer_queue_history()['groups'][0]
    assert historical['questions'][0]['id'] == question['id']
    assert historical['questions'][0]['state'] == 'pending'


def test_generalization_preserves_sponsorship_time_and_negation():
    from job_applier.managed_answer_library import question_identity
    assert question_identity('Will you require sponsorship in the future?') != question_identity('Do you currently require sponsorship?')
    assert question_identity('Do you require sponsorship?') != question_identity('Can you work without sponsorship?')


def test_duplicate_questions_are_grouped_and_one_answer_resolves_all(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    request(service, owner)
    request(service, owner, field='leadership_2', context={'page':'another'})
    queue = service.answer_queue()
    assert len(queue['clusters']) == 1 and queue['clusters'][0]['request_count'] == 2
    save(service)
    queue = service.answer_queue()
    assert queue['inbox'] == [] and len(queue['ready']) == 1
    assert queue['clusters'] == []


def test_company_scope_current_options_and_specific_override(tmp_path):
    service, session, owner, _, _ = connected(tmp_path)
    with service.tx() as db:db.execute('UPDATE jobs SET company=? WHERE id=?', ('Example Systems',session['job_id']))
    save(service, scope='company', scope_key='Other Systems')
    assert request(service, owner)['answer'] is None
    save(service, scope='company', scope_key='EXAMPLE Systems', answer='No')
    assert service.questions_for_attempt(owner['attempt_id'])['questions'][0]['answer']['label'] == 'No'
    save(service, scope='job', scope_key=session['job_id'], answer='Yes')
    assert service.questions_for_attempt(owner['attempt_id'])['questions'][0]['answer']['label'] == 'Yes'


def test_profile_changes_resolve_pending_without_creating_library_copy(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    question = request(service, owner, question='When can you start?', kind='text', options=[])
    profile = {'standard_answers':{'When can you start?':'Two weeks notice'}}
    service.identity(identity_id='candidate',person_key='same-person',email='candidate@example.test',profile=profile)
    current = service.questions_for_attempt(owner['attempt_id'])['questions'][0]
    assert current['id']==question['id'] and current['answer']=='Two weeks notice'
    assert current['answer_source']=='approved_profile'
    assert service.answer_library()['entries']==[]


def test_applicability_and_option_ambiguity_do_not_supply_wrong_answers(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    save(service, conditions={'country':'Canada'})
    assert request(service, owner)['answer'] is None
    service.save_library_answer(identity_id='candidate',question='Salary expectation?',answer='100000',
        conditions={'currency':'USD','period':'year'},aliases=['Expected annual compensation in USD?'])
    q=request(service, owner,field='salary',question='Expected annual compensation in USD?',kind='text',options=[])
    assert q['answer']=='100000'
    q=request(service, owner,field='salary_other',question='Salary expectation?',kind='text',options=[],context={'page':'other'})
    assert q['answer'] is None


def test_conflicting_human_history_proposes_review_without_automatic_promotion(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    q=request(service, owner)
    service.answer_questions(answers=[{'question_id':q['id'],'answer':'yes','expected_revision':0}])
    service.answer_questions(answers=[{'question_id':q['id'],'answer':'no','expected_revision':1}])
    library=service.answer_library()
    assert library['entries']==[]
    assert {s['source']['answer'] for s in library['suggestions']}=={'Yes','No'}
    assert all(s['state']=='pending' for s in library['suggestions'])


def test_terminal_and_canceled_requests_keep_answers_and_restore_to_inbox(tmp_path):
    service,session,owner,_,_=connected(tmp_path)
    q=request(service,owner)
    with service.tx() as db:db.execute("UPDATE jobs SET disposition='canceled' WHERE id=?",(session['job_id'],))
    save(service)
    assert service.answer_queue()['inbox']==[]
    assert service.answer_queue_history()['groups'][0]['questions'][0]['answer'] is None
    with service.tx() as db:db.execute("UPDATE jobs SET disposition='active' WHERE id=?",(session['job_id'],))
    service.reconcile_answers()
    assert service.answer_queue()['ready'][0]['questions'][0]['id']==q['id']


def test_library_api_is_operator_only(tmp_path):
    from fastapi.testclient import TestClient
    from job_applier.managed_api import create_app
    service,_,_,_,_=connected(tmp_path)
    operator='operator-'+('a'*30);worker='worker-'+('b'*30)
    with TestClient(create_app(service,operator_token=operator,worker_tokens={worker:'worker'})) as client:
        for operation in ('answer_library','save_library_answer','set_library_answer_state','reconcile_answers','answer_queue_history'):
            response=client.post('/v1/'+operation,json={},headers={'Authorization':'Bearer '+worker,'X-JobBot-Instance':service.instance_id})
            assert response.status_code==403


def test_saved_answer_uses_current_library_and_keeps_explicit_application_override(tmp_path):
    from job_applier.application_answers import saved_answer, saved_answer_basis
    service,session,owner,_,_=connected(tmp_path)
    q=request(service,owner);entry=save(service)
    observed=dict(QUESTION,ref='fresh',options=QUESTION['options'])
    package=service.application_context(owner['attempt_id'])
    assert saved_answer(observed,package)['label']=='Yes'
    assert saved_answer_basis(observed,package)==f"answer_library:{entry['id']}:1"
    service.answer_questions(answers=[{'question_id':q['id'],'answer':'no','expected_revision':1}])
    package=service.application_context(owner['attempt_id'])
    assert saved_answer(observed,package)['label']=='No'
    assert saved_answer_basis(observed,package) is None


def test_immutable_library_history_and_duplicate_creation(tmp_path):
    import sqlite3
    service,_,_,_,_=connected(tmp_path)
    entry=save(service)
    assert save(service)['id']==entry['id']
    with pytest.raises(ProtocolError,match='library_answer_exists'):save(service,answer='No')
    with pytest.raises(sqlite3.IntegrityError,match='immutable answer library history'):
        with service.tx() as db:db.execute('DELETE FROM answer_library_versions')


def test_linkedin_current_library_replaces_an_old_autofilled_value(tmp_path,monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from job_applier import linkedin_easy_apply as portal
    from job_applier import application_answers
    question=dict(QUESTION,ref='fresh',kind='check',options=[],answered=True,enabled=True)
    package={'job':{'id':'job','url':'https://www.linkedin.com/jobs/view/123456'},
        'attempt':{'profile_json':{},'settings_json':{},'identity_id':'candidate'},'saved_questions':[],
        'answer_library':[{'id':'entry','identity_id':'candidate','question':QUESTION['question'],
            'aliases':[],'scope':'global','scope_key':'','conditions':{},'state':'active','revision':1,'answer':False}]}
    observed={'page_signature':'step','status':'ready','inventory':[], 'linkedin':{'questions':[question]}}
    actions=[]
    async def policy(*args,**kwargs):return {'fields':[]}
    async def capture(*args,**kwargs):return {}
    async def action(page,params):actions.append(params);return {'committed':True}
    async def read():return observed
    monkeypatch.setattr(application_answers,'apply_policy',policy)
    monkeypatch.setattr(application_answers,'capture_answers',capture)
    monkeypatch.setattr(portal,'form_action',action)
    runner=portal.EasyApplyRunner(SimpleNamespace(),lambda *a,**k:None,package,{'attempt_id':1},
        {'spool_dir':str(tmp_path)},'target')
    runner.observe=read
    assert asyncio.run(runner.fill(observed))['committed']
    assert actions==[{'method':'check','ref':'fresh','value':False}]
    journal=json.loads((tmp_path/'answers/attempt-1.json').read_text())
    assert journal['answers'][0]['answer_basis']=='answer_library:entry:1'


def test_renamed_library_entry_does_not_restore_its_obsolete_form_journal(tmp_path):
    from job_applier.application_answers import save_answer_history,reusable_answers
    package={'job':{'id':'job','url':'https://example.test/jobs/1'},'attempt':{'identity_id':'candidate'},
        'answer_library':[{'id':'entry','question':'A different question?', 'aliases':[],
            'scope':'global','scope_key':'','conditions':{},'state':'active','revision':2,'answer':'New answer'}]}
    config={'spool_dir':str(tmp_path)}
    save_answer_history(config,package,1,[dict(field='old',question='Old question?',answer='Old answer',
        verified=True,question_key='old-key',answer_value='Old answer',answer_basis='answer_library:entry:1')],
        page='form',source='greenhouse_fast')
    assert reusable_answers(config,package,1,source='greenhouse_fast')=={}


def test_retiring_knowledge_returns_a_queued_retry_question_to_the_inbox(tmp_path):
    service,session,owner,_,_=connected(tmp_path)
    request(service,owner)
    entry=save(service)
    service.queue_answer_retries(job_ids=[session['job_id']],identity_id='candidate')
    service.set_library_answer_state(entry_id=entry['id'],state='retired',expected_revision=1)
    queue=service.answer_queue()
    assert len(queue['inbox'])==1 and queue['inbox'][0]['pending_count']==1
    assert service.answer_retries()['requests']==[]


def test_historical_suggestions_include_the_company_and_position_they_came_from(tmp_path):
    service,session,owner,_,_=connected(tmp_path)
    with service.tx() as db:
        db.execute('UPDATE jobs SET company=?,title=? WHERE id=?',('Example Systems','Engineering Manager',session['job_id']))
    q=request(service,owner,question='What interests you about this position?',kind='text',options=[])
    service.answer_questions(answers=[{'question_id':q['id'],'answer':'The team leadership scope','expected_revision':0}])
    suggestion=service.answer_library()['suggestions'][0]
    assert {key:suggestion['source'][key] for key in ('job_id','company','title','url')}==dict(job_id=session['job_id'],company='Example Systems',
        title='Engineering Manager',url=service.job(session['job_id'])['url'])
    assert suggestion['state']=='pending' and suggestion['answer'] is None


def test_application_scoped_library_projects_the_company_and_position(tmp_path):
    service,session,_,_,_=connected(tmp_path)
    with service.tx() as db:
        db.execute('UPDATE jobs SET company=?,title=? WHERE id=?',('Example Systems','Engineering Manager',session['job_id']))
    save(service,scope='job',scope_key=session['job_id'])
    entry=service.answer_library()['entries'][0]
    assert entry['application']==dict(id=session['job_id'],company='Example Systems',title='Engineering Manager',url=service.job(session['job_id'])['url'])
    assert 'application' not in service.answer_library(include_history=False)['entries'][0]
