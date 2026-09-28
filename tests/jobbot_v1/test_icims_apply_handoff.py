"""iCIMS helper entry uses the shared owned Apply handoff; no employer traffic."""
import asyncio
import json

import pytest

from test_owned_route_history import SOURCE, owned_page

DESTINATION = 'https://careers.example.icims.com/jobs/123/login'


def entry_html(url):
    if url == SOURCE:
        return '<html><body><h1>Job posting</h1><a href="' + DESTINATION + '">Apply for this job</a></body></html>'
    return '<html><body><h1>Application</h1><label>Full name<input name="name" value="Synthetic Candidate" required></label><button type="button">Submit application</button></body></html>'


@pytest.mark.parametrize('popup', [False, True])
def test_helper_apply_preserves_correlated_target_handoff(tmp_path, monkeypatch, popup):
    from job_applier import application_runtime
    from job_applier.icims_fast import IcimsRunner
    from job_applier.managed_client import LocalClient
    async def run():
        async with owned_page(tmp_path, entry_html) as (page, service, session, owner):
            if popup:
                # Shared popup correlation has its own real/contract coverage.
                # Here exercise the helper's handoff boundary: it must never
                # keep using the old socket after the service owns a new target.
                async def correlated_popup(*args, **kwargs):
                    handoff = service.handoff_target(**owner, current_target_id=page.target_id,
                        new_target_id='synthetic-popup', url=DESTINATION, expected_url=DESTINATION,
                        evidence='Synthetic correlated popup')
                    return {'clicked': True, 'target_handoff': handoff}
                monkeypatch.setattr(application_runtime, 'click_and_follow_external_apply', correlated_popup)
            package = service.application_context(owner['attempt_id'])
            client = LocalClient({'instance_id': service.instance_id}, service=service)
            runner = IcimsRunner(page, client.call, package, owner,
                                 {'cdp_url': page.fixture_endpoint}, page.target_id)
            result = await runner.run(seconds=10)
            assert result['status'] == ('continue' if popup else 'ready_for_review'), result
            assert result['actions']['stage_advance'] == 1
            context = service.application_context(owner['attempt_id'])
            assert context['job']['url'] == DESTINATION
            assert context['namespace'] == 'careers.example.icims.com'
            if popup:
                assert result['target_handoff']['target_id'] == 'synthetic-popup'
                assert result['next_operation']['operation'] == 'browser'
                assert await page.evaluate('location.href') == SOURCE
            else:
                assert runner.package['job']['url'] == DESTINATION
            assert not service.attempt(owner['attempt_id'])['submit_intent_at']
    asyncio.run(run())


@pytest.mark.parametrize('late_submit_type', [False, True])
def test_final_apply_runs_available_autofill_before_review(tmp_path, late_submit_type):
    from job_applier.icims_fast import IcimsRunner
    from job_applier.managed_client import LocalClient
    def final_form(url):
        return '''<html><body><h1>Application review</h1>
        <form onsubmit="event.preventDefault();window.submits++">
        <label>Full name<input name="name" value="Synthetic Candidate" required></label>
        <button type="submit">Apply</button></form>
        <div class="simplify-jobs-shadow-root"></div><script>
        window.fills=0;window.submits=0;
        const panel=document.querySelector('.simplify-jobs-shadow-root').attachShadow({mode:'open'});
        panel.innerHTML='<section><h2>Simplify</h2><p>Autofill complete! 0 fields need review.</p><button type="button">Autofill this page</button></section>';
        panel.querySelector('button').onclick=()=>{
          window.fills++;panel.querySelector('p').textContent='Autofilling. Filling your application.';
          setTimeout(()=>{panel.querySelector('p').textContent='Autofill complete! 0 fields need review.'},100);
        };
        </script></body></html>'''
    async def run():
        async with owned_page(tmp_path, final_form) as (page, service, session, owner):
            package = service.application_context(owner['attempt_id'])
            package['attempt']['settings_json'] = dict(json.loads(package['attempt']['settings_json']), autofill='simplify')
            client = LocalClient({'instance_id': service.instance_id}, service=service)
            runner = IcimsRunner(page, client.call, package, owner,
                                 {'cdp_url': page.fixture_endpoint}, page.target_id)
            if late_submit_type:
                # A hydrated form can change the button after the inventory.
                # The fresh control inspection must govern the entire decision.
                await page.evaluate('document.querySelector("form button").type="button"')
                original_gate = runner.gate
                async def hydrate_at_gate():
                    result = await original_gate()
                    await page.evaluate('document.querySelector("form button").type="submit"')
                    return result
                runner.gate = hydrate_at_gate
            result = await runner.run(seconds=10)
            assert await page.evaluate('window.fills') == 1, json.dumps({'result':result,'last':runner.last,'settings':runner.settings})
            assert result['status'] == 'ready_for_review', result
            assert result['actions']['stage_advance'] == 0
            assert await page.evaluate('window.submits') == 0
            assert not service.attempt(owner['attempt_id'])['submit_intent_at']
    asyncio.run(run())


def test_same_tab_handoff_uses_refreshed_route_profile(tmp_path):
    from job_applier.icims_fast import IcimsRunner
    from job_applier.managed_client import LocalClient
    destination = 'https://job-boards.greenhouse.io/example/jobs/123'
    def html_for(url):
        if url == SOURCE:
            return '<html><body><a href="' + destination + '">Apply for this job</a></body></html>'
        return '<html><body><h1>Application</h1><label>Email<input name="email" type="email" required></label><button type="button">Submit application</button></body></html>'
    metadata = {'credential_sources': {'email_routes': {'greenhouse': {
        'application_email': 'routed@example.test', 'verification_mailbox': 'candidate@example.test'}}}}
    async def run():
        async with owned_page(tmp_path, html_for, metadata) as (page, service, session, owner):
            package = service.application_context(owner['attempt_id'])
            client = LocalClient({'instance_id': service.instance_id}, service=service)
            runner = IcimsRunner(page, client.call, package, owner,
                                 {'cdp_url': page.fixture_endpoint}, page.target_id)
            assert runner.profile['identity']['email'] == 'candidate@example.test'
            result = await runner.run(seconds=10)
            assert await page.evaluate('document.querySelector("input").value') == 'routed@example.test', result
            assert result['status'] == 'ready_for_review', result
            assert runner.profile == json.loads(runner.package['attempt']['profile_json'])
            assert service.candidate('candidate')['email'] == 'candidate@example.test'
            attempt = service.attempt(owner['attempt_id'])
            assert json.loads(attempt['profile_json'])['identity']['email'] == 'candidate@example.test'
            assert not attempt['submit_intent_at']
    asyncio.run(run())
