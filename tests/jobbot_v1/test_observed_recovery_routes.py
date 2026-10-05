"""Observed reset, board and assessment links on synthetic owned pages."""
import asyncio
import json

import pytest

from job_applier.application_runtime import browser_action
from job_applier.managed_client import LocalClient
from test_owned_route_history import SOURCE, owned_page, gate


RESET='https://login.example.test/u/reset-password/request/hs-123'
LOGIN='https://login.example.test/u/login/password'
RETURN=SOURCE.rsplit('/',1)[0]+'/application'


def test_observed_reset_request_can_continue_and_return_to_application(tmp_path):
    def html(url):
        if url==SOURCE:
            return '<h1>Sign in</h1><input type="email"><button onclick='+json.dumps("location.href='"+LOGIN+"'")+'>Next</button>'
        if url==LOGIN:
            return '<h1>Sign in</h1><input type="password"><a href="'+RESET+'">Reset your password</a>'
        if url==RESET:
            return '<h1>Reset your password</h1><label>Email<input type="email" value="candidate@example.test"></label><button onclick='+json.dumps("location.href='"+RETURN+"'")+'>Continue</button>'
        return '<h1>Application review</h1><button onclick="document.body.innerHTML=\'<h1>Thank you for applying</h1>\'">Submit application</button>'
    async def run():
        async with owned_page(tmp_path,html,settings={'mode':'pilot','submission_mode':'submit'}) as (page,service,session,owner):
            client=LocalClient({'instance_id':service.instance_id},service=service)
            config={'cdp_url':page.fixture_endpoint,'browser_mode':'headless','spool_dir':str(tmp_path/'spool')}
            namespace=service.application_context(owner['attempt_id'])['namespace']
            for selector,url in [('button',LOGIN),('a',RESET),('button',RETURN)]:
                package=service.application_context(owner['attempt_id'])
                await asyncio.to_thread(browser_action,config,client,owner,package,page.target_id,{'method':'click','selector':selector})
                assert await page.evaluate('location.href')==url
                observed_gate=await gate(page,service,owner)
                assert observed_gate['native_takeover_authorized'],(url,observed_gate)
                assert service.application_context(owner['attempt_id'])['namespace']==namespace
            result=await asyncio.to_thread(browser_action,config,client,owner,service.application_context(owner['attempt_id']),page.target_id,{'method':'submit','selector':'button'})
            assert result['status']=='applied'
            assert service.job(session['job_id'])['url']==SOURCE
    asyncio.run(run())


@pytest.mark.parametrize('kind',['posting','assessment'])
def test_selected_embedded_link_adopts_its_observed_popup(tmp_path,kind):
    destination=('https://job-boards.greenhouse.io/fixture/jobs/123456' if kind=='posting' else
                 'https://assessment.example.test/invitation/fixture')
    label='Synthetic Director' if kind=='posting' else 'Take assessment'
    frame='https://board.example.test/list'
    def html(url):
        if url==SOURCE:return '<h1>Available roles</h1><iframe title="Job board" src="'+frame+'"></iframe>'
        if url==frame:return '<h1>Search roles</h1><a target="_blank" href="'+destination+'">'+label+'</a>'
        return '<h1>Application</h1><label>Full name<input required></label><button>Continue</button>'
    async def run():
        async with owned_page(tmp_path,html) as (page,service,session,owner):
            from job_applier.browser_controls import FORM
            from job_applier.browser_frames import router_for
            package=service.application_context(owner['attempt_id'])
            router=await router_for(page,package);await router.discover()
            frame_page=next(iter(router.frames.values()))
            observed=await frame_page.evaluate_function(FORM,{'method':'observe'})
            link=next(c for c in observed['inventory'] if c.get('tag')=='A')
            client=LocalClient({'instance_id':service.instance_id},service=service)
            result=await asyncio.to_thread(browser_action,{'cdp_url':page.fixture_endpoint,'browser_mode':'headless'},client,owner,package,page.target_id,
                {'method':'click','ref':frame_page.wrap(link['ref'])})
            assert result.get('target_handoff'),result
            target=result['target_handoff']['target_id']
            assert target!=page.target_id
            assert service.session(session['id'])['target_id']==target
            assert service.application_context(owner['attempt_id'])['job']['url']==destination
            assert service.job(session['job_id'])['url']==SOURCE
            assert not service.attempt(owner['attempt_id'])['completed_at']
    asyncio.run(run())


def test_sensitive_reset_token_urls_are_not_persisted_as_public_postings():
    from job_applier.managed_identity import canonical_url
    from job_applier.managed_shared import ProtocolError
    for url in (RESET+'?reset_token=synthetic-secret',RESET+'/synthetic-secret',
                'https://login.example.test/reset-password/synthetic-secret'):
        with pytest.raises(ProtocolError,match='sensitive_url'):canonical_url(url)
