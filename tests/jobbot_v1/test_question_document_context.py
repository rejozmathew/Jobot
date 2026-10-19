"""Synthetic form-context isolation; no employer records or private links."""
import json

import pytest

from job_applier.managed_questions import question_data, question_key
from job_applier.managed_shared import ProtocolError


def capture(url, **changes):
    return question_data(field='experience', question='Describe your team experience',
                         kind='text', context={'page':'form','document':url}, **changes)


def test_signed_form_context_is_private_stable_and_distinct():
    url='https://forms.example.test/embed/application?tenant=example&token=synthetic-form-signature'
    first=capture(url)
    assert 'synthetic-form-signature' not in json.dumps(first)
    assert 'token=' not in first['context']['document']
    assert question_key(first)==question_key(capture(url))
    assert question_key(first)!=question_key(capture(url.replace('signature','other')))
    assert question_key(first)!=question_key(capture(url.replace('/application','/other')))
    assert question_key(first)!=question_key(capture(url.replace('forms.example','foreign.example')))
    assert question_key(first)==question_key(capture(first['context']['document']))


def test_ordinary_document_context_remains_unchanged():
    url='https://forms.example.test/jobs/123?tenant=example'
    assert capture(url)['context']['document']==url


@pytest.mark.parametrize('url',[
    'https://forms.example.test/password-reset?token=synthetic',
    'https://forms.example.test/form?reset_token=synthetic',
    'https://user:synthetic@forms.example.test/form?token=synthetic',
])
def test_private_auth_and_invalid_urls_are_still_rejected(url):
    with pytest.raises(ProtocolError):capture(url)


def test_other_secret_bearing_question_data_stays_rejected():
    with pytest.raises(ProtocolError):
        question_data(field='experience',question='password=synthetic',kind='text')


def test_signed_context_can_queue_actual_answer_without_changing_session_deadline(tmp_path):
    from datetime import datetime,timezone,timedelta
    from test_answer_queue import connected
    start=datetime.now(timezone.utc)
    deadline={'started_at':start.isoformat(),'expires_at':(start+timedelta(hours=1)).isoformat(),
              'limit_seconds':3600}
    service,session,owner,_,_=connected(tmp_path,metadata={'application_deadline':deadline})
    before=service.session(session['id'])['metadata_json']
    state=service.session(session['id'])['state']
    data=capture('https://forms.example.test/embed/application?token=synthetic-form-signature')
    first=service.request_question(**owner,**data)
    saved=service.answer_questions(answers=[{'question_id':first['id'],
        'answer':'Approved synthetic team experience','expected_revision':0}])
    again=service.request_question(**owner,**data)
    assert again['id']==first['id'] and again['answer']=='Approved synthetic team experience'
    assert service.session(session['id'])['state']==state
    assert service.session(session['id'])['metadata_json']==before


@pytest.mark.parametrize('origin',['human','library'])
def test_signed_embedded_question_recovers_in_same_browser_to_submission(tmp_path,monkeypatch,origin):
    from contextlib import asynccontextmanager
    import test_embedded_forms as fixture
    from job_applier.browser_controls import observe,click_control
    from job_applier.browser_frames import resolve_control
    from job_applier.submission import submit
    original=fixture.fixture_browser

    @asynccontextmanager
    async def signed_browser(*args,**kwargs):
        async with original(*args,**kwargs) as (page,package,submissions):
            await page.evaluate("new Promise(resolve=>{const frame=document.querySelector('iframe');frame.onload=()=>resolve(true);frame.src+='&token=synthetic-form-signature';})")
            yield page,package,submissions
            screen=await observe(page,package)
            team=next(c for c in screen['inventory'] if c['role']=='combobox')
            child,_=await resolve_control(page,{'ref':team['ref']})
            assert await child.evaluate("document.querySelector('#team').textContent")=='No'
            package['attempt']['settings_json']={'mode':'pilot','submission_mode':'submit'}
            target={'ref':screen['native']['submit']['ref']}
            ledger=fixture.SubmissionLedger()
            async def activate():return await click_control(page,target)
            result=await submit(page,ledger.call,package,{'attempt_id':1},
                {'spool_dir':str(tmp_path),'cdp_url':'fixture'},page.target_id,activate,
                seconds=1,application_control=target)
            assert result['status']=='applied' and result['source']=='employer',result
            assert submissions==['/fake-submit']

    monkeypatch.setattr(fixture,'fixture_browser',signed_browser)
    fixture.test_runtime_captures_missing_question_then_applies_exact_human_answer(tmp_path,origin)
