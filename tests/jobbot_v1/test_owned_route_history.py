"""Delayed owned navigation after action connections close; synthetic sites only."""
import asyncio
import base64
from contextlib import asynccontextmanager
import json

import pytest

SOURCE = 'https://applications.example.test/oneclick/publication/123'
SCREENING = 'https://applications.example.test/screening'


@asynccontextmanager
async def owned_page(tmp_path, html_for=None, metadata=None, settings=None):
    from test_embedded_forms import fixture_browser
    from test_local_sessions import setup, connect
    async with fixture_browser(tmp_path, 'top') as (page, _, __):
        pending = set()
        async def fulfill(event):
            body = '<html><body><label>Full name<input required name="name"></label><button type="button">Next</button></body></html>'
            if html_for: body = html_for(event['request']['url'])
            await page._session.call('Fetch.fulfillRequest', {'requestId': event['requestId'],
                'responseCode': 200, 'responseHeaders': [{'name': 'Content-Type', 'value': 'text/html'}],
                'body': base64.b64encode(body.encode()).decode()})
        def paused(event):
            task = asyncio.create_task(fulfill(event)); pending.add(task)
            task.add_done_callback(pending.discard)
        remove = page._session.subscribe('Fetch.requestPaused', paused)
        await page._session.call('Fetch.enable', {'patterns': [{'urlPattern': '*'}]})
        try:
            await page.goto(SOURCE)
            service, asset, _, workspaces, config = setup(tmp_path / 'ledger')
            workspaces[0].update(cdp_url=page.fixture_endpoint, mode='headless')
            service.configure_workspaces(workspaces)
            service.configure({'mode': 'development', 'autofill': 'native', 'browser_mode': 'headless', **(settings or {})},
                              expected_version=service.settings_view()['version'])
            job = service.intake(url=SOURCE); service.eligibility(job['id'], 'ready', reason='Synthetic')
            session = connect(service, service.reserve_session(request_id='history', job_id=job['id'],
                identity_id='candidate', driver_id='fixture', workspace_ids=['workspace-0'],
                concurrency_limit=1, resume_asset_id=asset['id'], metadata=metadata), page.target_id)
            service.session_authority = (session['id'], 'fixture', 'host-workspace-0')
            attempt = service.attempt(session['attempt_id'])
            owner = {k: attempt[k] for k in ('worker_id', 'fence')}; owner['attempt_id'] = attempt['id']
            yield page, service, session, owner
        finally:
            if pending: await asyncio.gather(*pending)
            await page._session.call('Fetch.disable'); remove()


async def gate(page, service, owner):
    return await asyncio.to_thread(service.browser_observe, **owner, target_id=page.target_id,
                                   cdp_url=page.fixture_endpoint)


@pytest.mark.parametrize('navigation', ['document', 'pushState', 'replaceState'])
def test_delayed_same_origin_navigation_survives_action_connection(tmp_path, navigation):
    from job_applier.cdp_client import CDPBrowser
    async def run():
        async with owned_page(tmp_path) as (page, service, session, owner):
            assert (await gate(page, service, owner))['identity']['status'] == 'same_job'
            # This connection is gone before the delayed document/SPA transition.
            action = await CDPBrowser.connect(page.fixture_endpoint, target_id=page.target_id,
                                             expected_mode='headless')
            action_page = await action.get_current_page()
            change = 'location.href=' + json.dumps(SCREENING) if navigation == 'document' else (
                'history.' + navigation + '({},"",' + json.dumps(SCREENING) + ')')
            await action_page.evaluate('setTimeout(()=>{' + change + '},150)')
            await action.close()
            for _ in range(100):
                if await page.evaluate('location.href') == SCREENING: break
                await asyncio.sleep(.02)
            assert await page.evaluate('location.href') == SCREENING
            result = await gate(page, service, owner)
            assert result['identity']['status'] == 'same_job', result
            assert service.application_context(owner['attempt_id'])['job']['url'] == SCREENING
            assert service.job(session['job_id'])['url'] == SOURCE
            assert (await gate(page, service, owner))['identity']['status'] == 'same_job'
    asyncio.run(run())


def test_icims_continue_refreshes_route_before_embedded_form_in_same_call(tmp_path):
    from job_applier.icims_fast import IcimsRunner
    from job_applier.managed_client import LocalClient
    from job_applier.browser_frames import router_for
    def html_for(url):
        if url.endswith('/fields'):
            return '<html><body><h1>Application</h1><label>Full name<input name="name" value="Synthetic Candidate" required></label><button type="button">Submit application</button></body></html>'
        return '''<html><body><h1>Application</h1><button type="button" onclick="setTimeout(()=>{
          history.pushState({},'', '/screening');document.body.innerHTML='<iframe title=Application src=/fields></iframe>';
        },50)">Continue</button></body></html>'''
    async def run():
        async with owned_page(tmp_path, html_for) as (page, service, session, owner):
            package = service.application_context(owner['attempt_id'])
            client = LocalClient({'instance_id': service.instance_id}, service=service)
            runner = IcimsRunner(page, client.call, package, owner,
                                 {'cdp_url': page.fixture_endpoint}, page.target_id)
            result = await runner.run(seconds=10)
            assert result['status'] == 'ready_for_review', result
            assert result['actions']['stage_advance'] == 1
            assert runner.package['job']['url'] == SCREENING
            assert (await router_for(page)).package['job']['url'] == SCREENING
    asyncio.run(run())


@pytest.mark.parametrize('case', ['no_anchor', 'cross_origin', 'different_job', 'stale_fence', 'stale_target'])
def test_history_does_not_supply_unobserved_or_foreign_ownership(tmp_path, case):
    async def run():
        async with owned_page(tmp_path) as (page, service, session, owner):
            source = SOURCE
            if case == 'different_job':
                source = 'https://applications.example.test/jobs/123'
                service.handoff_target(**owner, current_target_id=page.target_id,
                    new_target_id=page.target_id, url=source, source_url=SOURCE, evidence='Synthetic route')
                await page.evaluate('history.replaceState({},"",' + json.dumps(source) + ')')
            if case != 'no_anchor': await gate(page, service, owner)
            if case in ('stale_fence', 'stale_target'):
                with service.tx() as db:
                    row = db.execute('SELECT metadata_json FROM application_sessions WHERE id=?', (session['id'],)).fetchone()
                    metadata = json.loads(row[0])
                    anchor = metadata.get('route_history_anchor', {})
                    anchor['fence' if case == 'stale_fence' else 'target_id'] = -1 if case == 'stale_fence' else 'another-target'
                    metadata['route_history_anchor'] = anchor
                    db.execute('UPDATE application_sessions SET metadata_json=? WHERE id=?', (json.dumps(metadata), session['id']))
            destination = ('https://another.example.test/screening' if case == 'cross_origin' else
                           'https://applications.example.test/jobs/999' if case == 'different_job' else SCREENING)
            await page.goto(destination)
            result = await gate(page, service, owner)
            assert result['identity']['status'] != 'same_job', result
            assert service.application_context(owner['attempt_id'])['job']['url'] == source
    asyncio.run(run())


def test_generic_step_does_not_erase_conflicting_intermediate_requisition(tmp_path):
    async def run():
        async with owned_page(tmp_path) as (page, service, _, owner):
            original = 'https://applications.example.test/jobs/123'
            service.handoff_target(**owner, current_target_id=page.target_id, new_target_id=page.target_id,
                url=original, expected_url=original, evidence='Synthetic verified application entry')
            await page.evaluate('history.pushState({},"",' + json.dumps(original) + ')')
            await gate(page, service, owner)
            await page.evaluate('history.pushState({},"",' + json.dumps(SCREENING) + ')')
            assert (await gate(page, service, owner))['identity']['status'] == 'same_job'
            await page.evaluate('history.pushState({},"","/jobs/999");history.pushState({},"","/next")')
            assert (await gate(page, service, owner))['identity']['status'] != 'same_job'
            assert service.application_context(owner['attempt_id'])['job']['url'] == SCREENING
    asyncio.run(run())


def test_newer_observer_anchor_is_not_overwritten_during_promotion(tmp_path, monkeypatch):
    async def run():
        async with owned_page(tmp_path) as (page, service, session, owner):
            await gate(page, service, owner)
            original = service.handoff_target
            calls = []
            def interleaved(**params):
                if not calls:
                    with service.tx() as db:
                        row = db.execute('SELECT metadata_json FROM application_sessions WHERE id=?', (session['id'],)).fetchone()
                        metadata = json.loads(row[0])
                        metadata['route_history_anchor']['entry_id'] = 100000
                        metadata['unrelated_concurrent_update'] = 'preserve'
                        db.execute('UPDATE application_sessions SET metadata_json=? WHERE id=?', (json.dumps(metadata), session['id']))
                    calls.append(True)
                return original(**params)
            monkeypatch.setattr(service, 'handoff_target', interleaved)
            await page.evaluate('history.pushState({},"",' + json.dumps(SCREENING) + ')')
            result = await gate(page, service, owner)
            assert result['identity']['status'] != 'same_job', result
            assert service.application_context(owner['attempt_id'])['job']['url'] == SOURCE
            metadata = json.loads(service.session(session['id'])['metadata_json'])
            assert metadata['route_history_anchor']['entry_id'] == 100000
            assert metadata['unrelated_concurrent_update'] == 'preserve'
    asyncio.run(run())
