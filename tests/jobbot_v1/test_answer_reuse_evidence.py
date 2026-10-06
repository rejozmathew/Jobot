"""Company templates and evidence distinguish resolution from browser use."""
from test_answer_queue import connected, request


def test_learned_yes_no_sentence_maps_to_boolean_controls_without_losing_text():
    from job_applier.managed_answer_library import option_answer
    answer='No, I do not own shares in this employer.'
    question=dict(kind='select', options=[dict(value='1',label='Yes'),dict(value='0',label='No')])
    assert option_answer(question, answer) == dict(value='0',label='No')
    assert option_answer(dict(kind='check'), answer) is False
    assert option_answer(dict(kind='text'), answer) == answer
    assert option_answer(question, 'I have no opinion.') is None
    assert option_answer(question, 'Yes, I hold shares.') == dict(value='1',label='Yes')


def test_company_template_maps_choices_and_specific_exception_wins(tmp_path):
    service, session, owner, _, _ = connected(tmp_path)
    with service.tx() as db:
        db.execute('UPDATE jobs SET company=? WHERE id=?', ('Example & Co', session['job_id']))
    entry = service.save_library_answer(identity_id='candidate',
        question='Do you own stock in {company}?', answer='No')
    q = request(service, owner, question='Do you own stock in Example & Co?')
    assert q['answer'] == {'value':'no', 'label':'No'}
    assert q['library_entry_id'] == entry['id']
    service.save_library_answer(identity_id='candidate', question='Do you own stock in {company}?',
        answer='Yes', scope='company', scope_key='Example & Co')
    assert request(service, owner, question=q['question'])['answer']['label'] == 'Yes'
    assert request(service, owner, field='negated', question='Do you NOT own stock in Example & Co?')['answer'] is None
    assert request(service, owner, field='foreign', question='Do you own stock in Another Company?')['answer'] is None


def test_reuse_evidence_counts_questions_once_and_keeps_form_evidence_separate(tmp_path):
    from job_applier.application_answers import save_answer_history
    service, session, owner, _, _ = connected(tmp_path)
    entry = service.save_library_answer(identity_id='candidate', question='Do you own shares?', answer='No')
    q = request(service, owner, question=entry['question'])
    service.reconcile_answers()
    usage = service.answer_library()['entries'][0]['usage']
    assert usage['resolved_questions'] == 1 and usage['recorded_form_uses'] == 0
    cfg = {'spool_dir':str(tmp_path/'spool')}; service.executor_config = cfg
    job = service.job(session['job_id'])
    package = dict(job=job, attempt=dict(identity_id='candidate'))
    save_answer_history(cfg, package, owner['attempt_id'], [dict(field='shares', question=q['question'], answer='No',
        verified=True, question_key='shares', answer_value='No', answer_basis=f"answer_library:{entry['id']}:1")],
        page='form', source='greenhouse_fast')
    usage = service.answer_library()['entries'][0]['usage']
    assert usage['resolved_questions'] == 1 and usage['recorded_form_uses'] == 1
    assert usage['recent'][0]['kind'] == 'form'
    assert usage['recent'][0]['attempt_id'] == owner['attempt_id']
    assert usage['recent'][0]['library_revision'] == 1
    assert 'usage' not in service.answer_library(include_history=False)['entries'][0]


def test_semantic_template_match_learns_new_wording_as_template(tmp_path):
    service, session, owner, _, _ = connected(tmp_path)
    with service.tx() as db:
        db.execute('UPDATE jobs SET company=? WHERE id=?', ('Example', session['job_id']))
    entry = service.save_library_answer(identity_id='candidate', question='Do you own stock in {company}?', answer='No')
    q = request(service, owner, question='Do you hold shares of Example?')
    assert service.learn_question_wordings(generator=lambda _:dict(matches=[dict(question_id=q['id'], entry_id=entry['id'])]))['matched'] == 1
    current = service.answer_library()['entries'][0]
    assert 'Do you hold shares of {company}?' in current['aliases']


def test_pending_wordings_are_processed_despite_unfinished_synthesis_backlog():
    from types import SimpleNamespace
    from job_applier.answer_learning import AnswerLearner
    calls=[]
    service=SimpleNamespace(learn_answers=lambda:dict(state='learned'),
        learn_question_wordings=lambda:calls.append('matched'))
    learner=AnswerLearner(service,{})
    learner.stop.wait=lambda _:learner.stop.set()
    learner.run()
    assert calls == ['matched']


def test_answer_journal_retains_changed_library_revision_even_for_same_answer(tmp_path):
    import json
    from pathlib import Path
    from job_applier.application_answers import save_answer_history
    cfg=dict(spool_dir=str(tmp_path/'spool'))
    package=dict(job=dict(id='job',url='https://example.test/job'),attempt=dict(identity_id='candidate'))
    row=dict(field='stock',question='Do you own stock?',answer='No')
    for revision in (1,2,2):
        result=save_answer_history(cfg,package,1,[row],page='form',source='application_runtime',
            basis=f'answer_library:entry:{revision}')
    rows=json.loads(Path(result['answer_history_path']).read_text())['answers']
    assert [r['answer_basis'] for r in rows] == ['answer_library:entry:1','answer_library:entry:2']
