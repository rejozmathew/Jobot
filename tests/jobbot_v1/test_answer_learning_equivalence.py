"""Equivalent wording adds provenance without replacing current candidate facts."""
import pytest
from test_answer_queue import connected, request


def compare(service, owner, current, incoming, *, equivalent=True, quotes=None, scope='global', conditions=None):
    q=request(service,owner,question='New wording of the application question?',kind='text',options=[])
    service.answer_questions(answers=[dict(question_id=q['id'],answer=incoming,expected_revision=0)])
    entry=service.save_library_answer(identity_id='candidate',question='Existing reusable fact?',answer=current)
    def generate(payload):
        assert any(e['id']==entry['id'] for e in payload['entries'])
        return dict(reusable=True,question=entry['question'],answer=incoming,
            scope=scope,scope_key='Example' if scope=='company' else '',conditions=conditions or {},
            source_equivalent=True,existing_entry_id=entry['id'],evidence_quotes=[incoming],
            existing_answer_equivalent=equivalent,existing_evidence_quotes=[current] if quotes is None else quotes)
    return service.learn_answers(generator=generate),entry,q


@pytest.mark.parametrize('current,incoming',[
    ('No, I have not worked for Example.','No'),
    ('I prefer working remotely.','Remote work is my preference.'),
    ('$225,000 per year','USD 225000 annually'),
    ('Available in 2 weeks.','I can start in 14 days.'),
])
def test_equivalent_answers_keep_current_value_and_add_source(tmp_path,current,incoming):
    service,_,owner,_,_=connected(tmp_path)
    result,entry,q=compare(service,owner,current,incoming)
    assert result['state']=='learned' and result['entry_id']==entry['id']
    library=service.answer_library()['entries']
    assert len(library)==1 and library[0]['answer']==current and library[0]['origin']=='manual'
    assert q['question'] in library[0]['aliases']
    assert library[0]['sources'][0]['answer']==incoming
    assert service.questions_for_attempt(owner['attempt_id'])['questions'][0]['answer']==incoming


@pytest.mark.parametrize('current,incoming,overrides',[
    ('No, I have not worked for Example.','Yes, I have worked for Example.',{}),
    ('$225,000 per year','$250,000 per year',{}),
    ('$225,000 per year','EUR 225000 annually',{}),
    ('$100 per hour','$100 per year',{}),
    ('No, I do not need sponsorship now.','No, I will never need sponsorship.',{'equivalent':False}),
    ('No, I have not worked for Example.','No',{'quotes':['Invented existing evidence']}),
    ('No, I have not worked for Example.','No',{'scope':'company'}),
    ('No, I have not worked for Example.','No',{'conditions':{'country':'ca'}}),
    ('No, I have not worked for Example.','No',{'equivalent':'true'}),
])
def test_uncertain_or_materially_different_answers_remain_conflicts(tmp_path,current,incoming,overrides):
    service,_,owner,_,_=connected(tmp_path)
    result,entry,_=compare(service,owner,current,incoming,**overrides)
    assert result['state']=='conflict'
    saved=service.answer_library()['entries'][0]
    assert saved['answer']==current and saved['revision']==entry['revision']
