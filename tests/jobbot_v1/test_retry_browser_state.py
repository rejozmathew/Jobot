"""Retries start with clean employer storage in the owned Simplify profile."""
import asyncio
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from job_applier import workspace_host
from job_applier.cdp_client import CDPBrowser


@pytest.mark.parametrize('previous_attempt', [False, True])
def test_retry_detection_survives_a_new_conversation_or_failed_start(tmp_path, previous_attempt):
    from test_local_sessions import setup, reserve, connect
    service, asset, jobs, _, _ = setup(tmp_path)
    initial = reserve(service, asset, jobs)
    assert not json.loads(initial['metadata_json']).get('fresh_employer_storage', False)
    if previous_attempt:
        initial = connect(service, initial)
    service.session_stopped(initial['id'], reason='Synthetic stopped browser', browser_stopped=True)
    if previous_attempt:
        service.retry(jobs[0]['id'])
    retried = reserve(service, asset, jobs, driver='new-conversation', request='new-request')
    assert json.loads(retried['metadata_json']).get('fresh_employer_storage') is True


@pytest.mark.parametrize('reset,attempt_id,fail_on', [
    (False, None, None), (True, None, None), (True, 17, None),
    (True, None, 'Storage.clearDataForOrigin'), (True, None, 'Target.closeTarget'),
])
def test_cleanup_precedes_navigation_and_does_not_clear_on_attach(tmp_path, monkeypatch, reset, attempt_id, fail_on):
    events = []
    # The host is ATS-neutral. Exercise each lifecycle condition once against a
    # custom origin, including its port, rather than repeating an ATS URL matrix.
    job_url = 'https://careers.example.test:8443/opportunities/role'
    parsed = urlsplit(job_url)
    origin = parsed.scheme + '://' + parsed.netloc

    async def command(endpoint, method, params=None):
        events.append((method, params))
        if method == fail_on:raise RuntimeError('Synthetic cleanup failure')
        if method == 'Browser.getBrowserCommandLine':
            return {'arguments': ['--user-data-dir=' + str(tmp_path), '--headless=new']}
        if method == 'Target.createTarget':return {'targetId': 'fresh'}
        if method == 'Target.getTargets':
            return {'targetInfos': [{'type': 'page', 'targetId': 'old'},
                                    {'type': 'page', 'targetId': 'fresh'},
                                    {'type': 'service_worker', 'targetId': 'simplify-worker'}]}
        if method == 'Target.closeTarget':return {'success': True}
        return {}

    class Page:
        _session = SimpleNamespace(call=lambda method, params: command(None, method, params))
        async def goto(self, url):events.append(('navigate', url))
        async def evaluate(self, expression):
            if expression == 'location.href':return job_url
            if 'readyState' in expression:return True
            return {'width': 1000, 'height': 800}

    class Browser:
        async def get_current_page(self):return Page()
        async def close(self):pass

    async def connect(*args, **kwargs):return Browser()
    monkeypatch.setattr(workspace_host, 'browser_command', command)
    monkeypatch.setattr(CDPBrowser, 'connect', connect)
    host = workspace_host.WorkspaceHost.__new__(workspace_host.WorkspaceHost)
    host.startup_timing = {}
    host.workspace = {'cdp_url': 'http://127.0.0.1:12345', 'user_data_dir': str(tmp_path), 'mode': 'headless'}
    host.config = {'require_simplify': False}
    host.service = SimpleNamespace(settings_view=lambda: {'values': {}}, job=lambda _: {'url': job_url}, now=lambda: '2026-09-09T00:00:00+00:00')
    session = {'job_id': 'job', 'attempt_id': attempt_id,
        'metadata_json': json.dumps({'fresh_employer_storage': reset})}
    if fail_on:
        with pytest.raises(Exception, match='employer_storage_cleanup_failed'):
            asyncio.run(host.prepare_target(session))
        assert not any(e[0] == 'navigate' for e in events)
        return
    _, readiness = asyncio.run(host.prepare_target(session))
    clears = [e for e in events if e[0] == 'Storage.clearDataForOrigin']
    if reset and not attempt_id:
        assert clears == [('Storage.clearDataForOrigin', {
            'origin': origin, 'storageTypes': 'all'})]
        assert events.index(('Target.closeTarget', {'targetId': 'old'})) < events.index(clears[0])
        assert events.index(clears[0]) < events.index(('navigate', job_url))
        assert [e[1]['targetId'] for e in events if e[0] == 'Target.closeTarget'] == ['old']
        assert readiness['employer_storage'] == {'status': 'cleared', 'origin': origin}
    else:
        assert not clears
        assert not any(e[0] == 'Target.closeTarget' for e in events)


def test_real_retry_clears_employer_data_but_preserves_another_origin(tmp_path, monkeypatch):
    from test_embedded_forms import fixture_browser

    async def check():
        async with fixture_browser(tmp_path, mode='top') as (page, package, _):
            url = package['job']['url']
            other = url.replace('localhost', '127.0.0.1')
            await page.goto(other)
            await page.evaluate("localStorage.setItem('simplify-login', 'keep');document.cookie='simplify_session=keep; Path=/'")
            await page.goto(url)
            await page.evaluate("localStorage.setItem('employer-login', 'stale');document.cookie='employer_session=stale; Path=/'")
            await page._session.call('Network.setCookies', {'cookies': [
                {'name': 'employer_http_only', 'value': 'stale', 'url': url, 'path': '/login', 'httpOnly': True},
                {'name': 'simplify_login', 'value': 'keep', 'url': 'https://simplify.jobs/'}]})
            await page.evaluate("""new Promise((resolve,reject)=>{const r=indexedDB.open('stale-employer');
                r.onupgradeneeded=()=>r.result.createObjectStore('session');
                r.onsuccess=()=>{r.result.close();resolve(true)};r.onerror=()=>reject(r.error)})""")
            original = workspace_host.browser_command

            async def command(endpoint, method, params=None):
                if method == 'Browser.getBrowserCommandLine':
                    return {'arguments': ['--user-data-dir=' + str(tmp_path / 'browser-top'), '--headless=new']}
                return await original(endpoint, method, params)

            monkeypatch.setattr(workspace_host, 'browser_command', command)
            host = workspace_host.WorkspaceHost.__new__(workspace_host.WorkspaceHost)
            host.startup_timing = {}
            host.workspace = {'cdp_url': page.fixture_endpoint, 'user_data_dir': str(tmp_path / 'browser-top'), 'mode': 'headless'}
            host.config = {'require_simplify': False}
            host.service = SimpleNamespace(settings_view=lambda: {'values': {}}, job=lambda _: {'url': url}, now=lambda: '2026-09-09T00:00:00+00:00')
            target, readiness = await host.prepare_target({'job_id': 'job', 'attempt_id': None,
                'metadata_json': json.dumps({'fresh_employer_storage': True})})
            browser = await CDPBrowser.connect(page.fixture_endpoint, target_id=target, expected_mode='headless')
            try:
                fresh = await browser.get_current_page()
                assert await fresh.evaluate("localStorage.getItem('employer-login')") is None
                assert await fresh.evaluate("indexedDB.databases().then(items=>items.some(x=>x.name==='stale-employer'))") is False
                cookies = (await fresh._session.call('Network.getCookies', {'urls': [url, url.split('/top')[0] + '/login', other, 'https://simplify.jobs/']}))['cookies']
                names = {c['name'] for c in cookies}
                assert 'employer_session' not in names and 'employer_http_only' not in names
                assert {'simplify_session', 'simplify_login'} <= names
                await fresh.goto(other)
                assert await fresh.evaluate("localStorage.getItem('simplify-login')") == 'keep'
                assert readiness['employer_storage']['status'] == 'cleared'
            finally:
                await browser.close()
    asyncio.run(check())
