"""Native synthetic receipt after a locale-only Rippling document transition."""
import asyncio
import json
import os
import pytest

from job_applier.application_runtime import browser_action
from test_popup_document_handoff import popup_fixture


def test_locale_transition_recovers_same_session_and_submits(tmp_path):
    if not os.environ.get('JOBBOT_BROWSER_TEST_EXE'):
        pytest.skip('Explicit isolated browser executable required')
    async def run():
        path='/en-US/synthetic/jobs/11111111-2222-4333-8444-555555555555'
        async with popup_fixture(tmp_path, hosts=('ats.rippling.com','forms.example.test'),
                                 posting_path=path,tls=True) as (page,s,session,own,client,cfg,entry,final,receipts):
            before=s.attempt(own['attempt_id'])
            current=entry.rsplit('/apply/',1)[0]+path.replace('/en-US/','/')+'/apply'
            await page.evaluate("history.replaceState({},'',"+json.dumps(current)+");document.body.innerHTML="+json.dumps(
                '<h1>Application review</h1><label>Full name<input id="name" required></label>'
                '<button onclick="if(!event.isTrusted)return;'+
                "fetch('/submitted',{method:'POST'});document.body.innerHTML='<h1>Thank you for applying</h1>'"+
                '">Submit application</button>'))
            gate=await asyncio.to_thread(s.browser_observe,**own,target_id=page.target_id,cdp_url=page.fixture_endpoint)
            assert gate['identity']['status']=='same_job',gate
            assert gate['native_takeover_authorized'],gate
            package=s.application_context(own['attempt_id'])
            filled=await asyncio.to_thread(browser_action,cfg,client,own,package,page.target_id,
                {'method':'fill','selector':'#name','value':'Synthetic Candidate'})
            assert filled['committed']
            submitted=await asyncio.to_thread(browser_action,cfg,client,own,package,page.target_id,
                {'method':'submit','selector':'button'})
            assert submitted['status']=='applied',submitted
            assert receipts==['/submitted']
            assert s.attempt(own['attempt_id'])['started_at']==before['started_at']
            assert s.session(session['id'])['attempt_id']==own['attempt_id']
            assert s.job(session['job_id'])['url'].endswith(path)
    asyncio.run(run())
