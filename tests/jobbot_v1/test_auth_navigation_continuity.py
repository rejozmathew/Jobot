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


@pytest.mark.parametrize('privacy', [False, True])
@pytest.mark.parametrize('caller', ['browser', 'icims'])
def test_authentication_with_privacy_choices_fills_private_credential_and_submits(tmp_path, privacy, caller):
    from job_applier.icims_fast import IcimsRunner
    from job_applier.workspace_host import WorkspaceHost
    choices = '''<label>Privacy acknowledgement<select required><option value="ack" selected>Acknowledge</option></select></label>
      <label><input type="checkbox" checked required>I accept the privacy notice</label>''' if privacy else ''
    def html_for(url):
        if url == SOURCE:
            return auth_html(url).replace('<button', choices + '<button', 1)
        if url == LOGIN:
            return auth_html(url).replace('type="password"', 'type="password" id="password" required').replace(
                "onclick='location.href=", "onclick='if(document.querySelector(\"#password\").value===\"synthetic-selected-password\")location.href=")
        return '''<html><body><h1>Application review</h1><button type="button"
          onclick="document.body.innerHTML='<h1>Thank you for applying</h1>'">Submit application</button></body></html>'''
    async def run():
        async with owned_page(tmp_path, html_for, settings={'mode': 'pilot', 'submission_mode': 'submit'}) as (page, service, session, owner):
            package = service.application_context(owner['attempt_id'])
            namespace = package['namespace']
            service.record_account_event(**owner, namespace=namespace, state='confirmed',
                credential_ref='credential:fixture/employer', request_id='fixture-selected-account',
                evidence='Synthetic selected employer credential')
            secret = tmp_path / 'synthetic-credentials.json'
            secret.write_text(json.dumps({'accounts': {
                'default': {'email': 'candidate@example.test', 'password': 'wrong-default'},
                'employer': {'email': 'candidate@example.test', 'password': 'synthetic-selected-password'}}}))
            config = {'instance_id': service.instance_id, 'db_path': str(service.db_path), 'transport': 'local',
                'cdp_url': page.fixture_endpoint, 'browser_mode': 'headless', 'spool_dir': str(tmp_path / 'spool'),
                'credential_profile_path': str(secret),
                'credential_account_keys': {'credential:fixture/employer': 'employer'}}
            client = LocalClient(config, service=service)
            package = service.application_context(owner['attempt_id'])
            initial = await page.evaluate_function(FORM, {'method': 'observe'})
            assert initial['stage']['name'] == ('unknown' if privacy else 'email_entry')
            if caller == 'browser':
                result = await asyncio.to_thread(browser_action, config, client, owner, package, page.target_id,
                    {'method': 'click', 'selector': 'button'})
                assert result.get('target_handoff'), result
            else:
                runner = IcimsRunner(page, client.call, package, owner, config, page.target_id)
                result = await runner.run(seconds=8)
                assert service.application_context(owner['attempt_id'])['job']['url'] != SOURCE, result
            current = service.application_context(owner['attempt_id'])
            assert current['namespace'] == namespace
            assert current['account']['credential_ref'] == 'credential:fixture/employer'
            # If the runner has already continued, its private fill is checked by
            # the fixture's login control below; otherwise use the normal host call.
            if await page.evaluate('location.href') == LOGIN:
                host = object.__new__(WorkspaceHost)
                host.service, host.config = service, config
                host.workspace_id, host.host_id = session['workspace_id'], 'host-' + session['workspace_id']
                host.workspace = {'cdp_url': page.fixture_endpoint, 'mode': 'headless'}
                result = await asyncio.to_thread(host.dispatch, {'instance_id': service.instance_id,
                    'session_id': session['id'], 'driver_id': session['driver_id'], 'operation': 'credentials',
                    'parameters': {'password_ref': '#password'}})
                assert result.get('values_committed'), result
                assert await page.evaluate("document.querySelector('#password').value") == 'synthetic-selected-password'
                current = service.application_context(owner['attempt_id'])
                await asyncio.to_thread(browser_action, config, client, owner, current, page.target_id,
                    {'method': 'click', 'selector': 'button'})
            assert await page.evaluate('location.href') == RETURN
            if service.attempt(owner['attempt_id'])['outcome'] != 'applied':
                assert (await gate(page, service, owner))['identity']['status'] == 'same_job'
                current = service.application_context(owner['attempt_id'])
                result = await asyncio.to_thread(browser_action, config, client, owner, current, page.target_id,
                    {'method': 'submit', 'selector': 'button'})
            assert result.get('status') == 'applied', result
            assert service.attempt(owner['attempt_id'])['outcome'] == 'applied'
            assert service.job(session['job_id'])['url'] == SOURCE
            assert 'synthetic-selected-password' not in json.dumps(result)
    asyncio.run(run())
