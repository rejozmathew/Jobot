"""Authentication continuations use observed navigation, not host allowlists."""
import asyncio
import json

import pytest

from job_applier.application_runtime import browser_action
from job_applier.managed_client import LocalClient
from job_applier.browser_controls import FORM
from test_owned_route_history import SOURCE, owned_page, gate


LOGIN = 'https://login.example.test/u/login/password'
RETURN = SOURCE.rsplit('/', 1)[0] + '/application'


def auth_html(url):
    if url == SOURCE:
        return '''<html><body><form><h1>Sign in</h1>
          <label>Email<input type="email" value="candidate@example.test" required></label>
          <button type="button" onclick='setTimeout(()=>location.href=''' + json.dumps(LOGIN) + ''',180)'>Next</button>
          </form></body></html>'''
    if url == LOGIN:
        return '''<html><body><form><h1>Sign in</h1><label>Password<input type="password"></label>
          <button type="button" onclick='location.href=''' + json.dumps(RETURN) + ''''>Log In</button></form></body></html>'''
    return '<html><body><h1>Application review</h1><input name="name" value="Synthetic Candidate"><button>Submit application</button></body></html>'


@pytest.mark.parametrize('caller', ['browser', 'icims'])
def test_delayed_authentication_handoff_keeps_employer_account_and_allows_next_action(tmp_path, caller):
    from job_applier.icims_fast import IcimsRunner
    async def run():
        async with owned_page(tmp_path, auth_html) as (page, service, session, owner):
            package = service.application_context(owner['attempt_id'])
            original_namespace = package['namespace']
            service.record_account_event(**owner, namespace=original_namespace, state='confirmed',
                credential_ref='credential:profile/accounts/default', request_id='fixture-account',
                evidence='Synthetic retained employer account')
            client = LocalClient({'instance_id': service.instance_id}, service=service)
            config = {'cdp_url': page.fixture_endpoint, 'browser_mode': 'headless'}
            if caller == 'browser':
                result = await asyncio.to_thread(browser_action, config, client, owner, package, page.target_id,
                    {'method': 'click', 'selector': 'button'})
                assert result.get('target_handoff'), result
            else:
                runner = IcimsRunner(page, client.call, package, owner, config, page.target_id)
                result = await runner.run(seconds=8)
                # There is intentionally no private fixture credential file.
                assert await page.evaluate('location.href') == LOGIN, result
            current = service.application_context(owner['attempt_id'])
            assert current['job']['url'] == LOGIN
            assert current['namespace'] == original_namespace
            assert current['account']['credential_ref'] == 'credential:profile/accounts/default'
            assert (await gate(page, service, owner))['native_takeover_authorized']
            assert service.job(session['job_id'])['url'] == SOURCE
            # Exact current-route native entry works; a login alone isn't success.
            result = await asyncio.to_thread(browser_action, config, client, owner, current, page.target_id,
                {'method': 'click', 'selector': 'button'})
            assert result.get('target_handoff') and await page.evaluate('location.href') == RETURN
            assert (await gate(page, service, owner))['identity']['status'] == 'same_job'
            assert service.application_context(owner['attempt_id'])['namespace'] == original_namespace
            assert not service.attempt(owner['attempt_id'])['submit_intent_at']
    asyncio.run(run())


def test_unobserved_login_hostname_is_still_outside_owned_route(tmp_path):
    async def run():
        async with owned_page(tmp_path, auth_html) as (page, service, session, owner):
            original = service.application_context(owner['attempt_id'])
            await page.goto(LOGIN)  # No supported action/navigation trace.
            assert (await gate(page, service, owner))['identity']['status'] != 'same_job'
            assert service.application_context(owner['attempt_id'])['namespace'] == original['namespace']
            assert service.application_context(owner['attempt_id'])['job']['url'] == SOURCE
    asyncio.run(run())
