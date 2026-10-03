"""AI synthesis is separate from human application replies and current edits."""
import pytest

from test_answer_queue import connected, request


def reply(service, owner, answer='I enjoy mentoring engineers and building reliable platforms.'):
    with service.tx() as db:db.execute('UPDATE jobs SET company=?,title=? WHERE id=(SELECT job_id FROM application_attempts WHERE id=?)', ('Example','Engineering Manager',owner['attempt_id']))
    q = request(service, owner, question='Why do you want this position at Example?', kind='text', options=[])
    service.answer_questions(answers=[dict(question_id=q['id'], answer=answer, expected_revision=0)])
    return q


def synthesis(payload):
    source = payload['sources'][0]
    return dict(reusable=True, question='What motivates you professionally?',
                answer='I enjoy mentoring engineers and building reliable platforms.',
                scope='global', scope_key='', conditions={}, source_equivalent=False,
                existing_entry_id=None, evidence_quotes=[source['answer']])


def test_saving_a_reply_does_not_create_a_raw_learned_answer(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    q = reply(service, owner)
    library = service.answer_library()
    assert library['entries'] == []
    assert library['learning']['pending'] == 1
    result = service.learn_answers(generator=synthesis)
    assert result['state'] == 'learned'
    entry = service.answer_library()['entries'][0]
    assert entry['question'] == 'What motivates you professionally?'
    assert entry['origin'] == 'ai'
    assert entry['sources'][0]['question'] == q['question']
    assert entry['sources'][0]['company'] and entry['sources'][0]['title']
    assert q['question'] not in entry['aliases']  # General motivations are context, not an employer-specific reply.
    current = service.questions_for_attempt(owner['attempt_id'])['questions'][0]
    assert current['answer_source'] == 'user_dashboard'
    assert current['answer'] == entry['sources'][0]['answer']


def test_learning_failure_keeps_the_application_answer_and_can_retry(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    reply(service, owner)
    def failed(_): raise RuntimeError('private provider details')
    assert service.learn_answers(generator=failed)['state'] == 'error'
    assert service.questions_for_attempt(owner['attempt_id'])['questions'][0]['state'] == 'answered'
    assert 'private provider details' not in str(service.answer_library())
    service.retry_answer_learning()
    assert service.learn_answers(generator=synthesis)['state'] == 'learned'


def test_ai_generalizes_old_raw_library_entries_and_keeps_original_versions(tmp_path):
    service, _, _, _, _ = connected(tmp_path)
    old = service.save_library_answer(identity_id='candidate', question='Why Example?',
        answer='I enjoy mentoring engineers and building reliable platforms.')
    # A migration marks the previous implementation's entries as awaiting synthesis.
    with service.tx() as db: db.execute("UPDATE answer_library_entries SET origin='legacy' WHERE id=?", (old['id'],))
    service.learn_answers(generator=synthesis)
    entry = service.answer_library()['entries'][0]
    assert entry['id'] == old['id'] and entry['origin'] == 'ai'
    assert entry['question'] != old['question']
    assert entry['history'][-1]['question'] == old['question']


def test_learning_never_overwrites_an_answer_edited_during_the_model_call(tmp_path):
    service, _, _, _, _ = connected(tmp_path)
    old = service.save_library_answer(identity_id='candidate', question='Why Example?', answer='I enjoy mentoring engineers.')
    with service.tx() as db: db.execute("UPDATE answer_library_entries SET origin='legacy' WHERE id=?", (old['id'],))
    def concurrent(payload):
        service.save_library_answer(identity_id='candidate', question=old['question'], answer='My updated preference.',
            entry_id=old['id'], expected_revision=1)
        return synthesis(payload)
    assert service.learn_answers(generator=concurrent)['state'] == 'changed'
    assert service.answer_library()['entries'][0]['answer'] == 'My updated preference.'


def test_ai_output_needs_grounded_source_evidence(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    reply(service, owner)
    def invented(payload): return {**synthesis(payload), 'evidence_quotes':['I led 100 engineers.']}
    assert service.learn_answers(generator=invented)['state'] == 'error'
    assert service.answer_library()['entries'] == []


def test_manual_answer_is_labelled_manual_and_not_sent_for_synthesis(tmp_path):
    service, _, _, _, _ = connected(tmp_path)
    entry = service.save_library_answer(identity_id='candidate', question='Preferred work arrangement?', answer='Remote')
    assert entry['origin'] == 'manual'
    assert service.learn_answers(generator=lambda _:pytest.fail('Manual input was treated as raw response'))['state'] == 'idle'


def test_ai_can_match_new_wording_to_current_knowledge_and_cache_misses(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    entry=service.save_library_answer(identity_id='candidate',question='Preferred working arrangement?',answer='Remote')
    q=request(service,owner,question='Which workplace setup do you prefer?',kind='text',options=[])
    result=service.learn_question_wordings(generator=lambda _:dict(matches=[dict(question_id=q['id'],entry_id=entry['id'])]))
    assert result['matched']==1
    current=service.questions_for_attempt(owner['attempt_id'])['questions'][0]
    assert current['answer']=='Remote' and current['answer_source']=='answer_library'
    request(service,owner,field='unrelated',question='Do you own a car?',kind='text',options=[])
    service.learn_question_wordings(generator=lambda _:dict(matches=[]))
    service.learn_question_wordings(generator=lambda _:pytest.fail('Unchanged miss repeatedly called the model'))


def test_different_fact_goes_to_review_and_does_not_overwrite_current_edit(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    entry=service.save_library_answer(identity_id='candidate',question='What motivates you professionally?',answer='Technical design')
    reply(service,owner)
    def conflict(payload):return {**synthesis(payload),'existing_entry_id':entry['id']}
    assert service.learn_answers(generator=conflict)['state']=='conflict'
    library=service.answer_library()
    assert library['entries'][0]['answer']=='Technical design'
    assert library['suggestions'][0]['state']=='conflict'


def test_generalizing_a_legacy_reply_does_not_reopen_the_answered_application(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    q=request(service,owner,question='Why do you want this position at Example?',kind='text',options=[])
    answer='I enjoy mentoring engineers and building reliable platforms.'
    old=service.save_library_answer(identity_id='candidate',question=q['question'],answer=answer)
    with service.tx() as db:db.execute("UPDATE answer_library_entries SET origin='legacy' WHERE id=?",(old['id'],))
    assert service.learn_answers(generator=synthesis)['state']=='learned'
    current=service.questions_for_attempt(owner['attempt_id'])['questions'][0]
    assert current['state']=='answered' and current['answer']==answer
    assert current['answer_source']=='user_dashboard'


def test_semantic_match_respects_company_scope_even_if_model_suggests_other_company(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    entry=service.save_library_answer(identity_id='candidate',question='Role preference?',answer='Manager',scope='company',scope_key='Another Employer')
    q=request(service,owner,question='Which role do you prefer?',kind='text',options=[])
    result=service.learn_question_wordings(generator=lambda _:dict(matches=[dict(question_id=q['id'],entry_id=entry['id'])]))
    assert result['state']=='error'
    assert service.questions_for_attempt(owner['attempt_id'])['questions'][0]['answer'] is None


def test_boolean_legacy_answers_supply_labelled_evidence_to_the_model(tmp_path):
    service, _, _, _, _ = connected(tmp_path)
    entry=service.save_library_answer(identity_id='candidate',question='Do you require sponsorship?',answer=False)
    with service.tx() as db:db.execute("UPDATE answer_library_entries SET origin='legacy' WHERE id=?",(entry['id'],))
    def generalize(payload):
        assert payload['sources'][0]['answer']=='No'
        return dict(reusable=True,question='Is employment sponsorship currently required?',answer='No',
            scope='global',scope_key='',conditions={},source_equivalent=True,existing_entry_id=None,evidence_quotes=['No'])
    assert service.learn_answers(generator=generalize)['state']=='learned'
    assert service.answer_library()['entries'][0]['answer']=='No'


def test_context_only_legacy_knowledge_is_archived_but_its_application_reply_is_kept(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    q=request(service,owner,question='Why this employer?',kind='text',options=[])
    answer='The specific team at Example appeals to me.'
    entry=service.save_library_answer(identity_id='candidate',question=q['question'],answer=answer)
    with service.tx() as db:db.execute("UPDATE answer_library_entries SET origin='legacy' WHERE id=?",(entry['id'],))
    assert service.learn_answers(generator=lambda _:dict(reusable=False))['state']=='context_only'
    current=service.questions_for_attempt(owner['attempt_id'])['questions'][0]
    assert current['answer']==answer and current['answer_source']=='user_dashboard'
    archived=service.answer_library()['entries'][0]
    assert archived['state']=='retired' and archived['history'][-1]['answer']==answer
    restored=service.set_library_answer_state(entry_id=entry['id'],state='active',expected_revision=archived['revision'])
    assert restored['origin']=='manual'


def test_conflicting_legacy_copy_is_archived_without_changing_its_application_reply(tmp_path):
    service, _, owner, _, _ = connected(tmp_path)
    current=service.save_library_answer(identity_id='candidate',question='What motivates you professionally?',answer='Technical design')
    q=request(service,owner,question='Why this employer?',kind='text',options=[])
    answer='I enjoy mentoring engineers and building reliable platforms.'
    raw=service.save_library_answer(identity_id='candidate',question=q['question'],answer=answer)
    with service.tx() as db:db.execute("UPDATE answer_library_entries SET origin='legacy' WHERE id=?",(raw['id'],))
    assert service.learn_answers(generator=lambda payload:{**synthesis(payload),'existing_entry_id':current['id']})['state']=='conflict'
    entries={e['id']:e for e in service.answer_library()['entries']}
    assert entries[raw['id']]['state']=='retired'
    assert entries[current['id']]['answer']=='Technical design'
    reply=service.questions_for_attempt(owner['attempt_id'])['questions'][0]
    assert reply['answer']==answer and reply['answer_source']=='user_dashboard'


def test_system_archived_company_response_can_supply_new_company_knowledge(tmp_path):
    service, _, _, _, _ = connected(tmp_path)
    raw=service.save_library_answer(identity_id='candidate',question='Why Example?',
        answer='I am drawn to Example because of its infrastructure mission.',scope='company',scope_key='Example')
    with service.tx() as db:db.execute("UPDATE answer_library_entries SET origin='legacy' WHERE id=?",(raw['id'],))
    service.learn_answers(generator=lambda _:dict(reusable=False))
    def company(payload):
        source=payload['sources'][0]
        return dict(reusable=True,question='What interests you about Example as an employer?',answer=source['answer'],
            scope='company',scope_key='Example',conditions={},source_equivalent=True,existing_entry_id=None,evidence_quotes=[source['answer']])
    result=service.learn_answers(generator=company)
    assert result['state']=='learned'
    entries={e['id']:e for e in service.answer_library()['entries']}
    assert entries[raw['id']]['state']=='retired'
    learned=entries[result['entry_id']]
    assert learned['id']!=raw['id'] and learned['scope']=='company'
    from job_applier.managed_answer_library import resolve_library
    question=dict(question=learned['question'],kind='text',options=[])
    assert resolve_library(question,dict(id='other-position',company='Example'),list(entries.values()))['answer']==learned['answer']
    assert resolve_library(question,dict(id='other-company',company='Another'),list(entries.values()))['answer'] is None


def test_unprocessed_legacy_entries_are_source_material_not_current_generic_facts(tmp_path):
    service, _, _, _, _ = connected(tmp_path)
    for question in ('Why this position?', 'What do you enjoy about this role?'):
        entry=service.save_library_answer(identity_id='candidate',question=question,answer='I enjoy mentoring engineers.')
        with service.tx() as db:db.execute("UPDATE answer_library_entries SET origin='legacy' WHERE id=?",(entry['id'],))
    def generalize(payload):
        assert all(e['origin']!='legacy' for e in payload['entries'])
        return synthesis(payload)
    assert service.learn_answers(generator=generalize)['state']=='learned'
