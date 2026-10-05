"""Real popup document redirects, with all traffic served by a synthetic local server."""
import asyncio
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from urllib.parse import urlsplit

import pytest

from job_applier.application_runtime import browser_action
from job_applier.cdp_client import CDPBrowser
from job_applier.managed_client import LocalClient
from test_embedded_forms import fixture_browser
from test_local_sessions import setup, connect


@asynccontextmanager
async def popup_fixture(tmp_path, *, redirect=True, conflict=False, hosts=('jobs.example.test', 'forms.example.test')):
    receipts = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/jobs/123':
                body = '<h1>Synthetic role</h1><a target="_blank" href="'+entry+'">Apply</a>'
            elif path == '/apply/123' and redirect:
                # A new target advertises this URL before its document commits.
                # Keep it provisional long enough to reproduce the early handoff.
                time.sleep(.8)
                self.send_response(302)
                self.send_header('Location', final)
                self.end_headers()
                return
            else:
                body = ('<h1>Application review</h1><label>Full name<input id="name" required></label>'
                        '<button onclick="if(!event.isTrusted)return;'
                        "fetch('/submitted',{method:'POST'});document.body.innerHTML='<h1>Thank you for applying</h1>'"
                        '">Submit application</button>')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(('<html><body>'+body+'</body></html>').encode())

        def do_POST(self):
            receipts.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    base = f'http://{hosts[0]}:{server.server_port}'
    other = f'http://{hosts[1]}:{server.server_port}'
    source, entry = base+'/jobs/123', base+'/apply/123'
    final = base+'/jobs/999' if conflict else other+'/candidate'
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        async with fixture_browser(tmp_path, 'top', entry_url=source, browser_args=[
            '--host-resolver-rules=MAP *.example.test 127.0.0.1',
            '--unsafely-treat-insecure-origin-as-secure='+base+','+other,
        ]) as (page, _, __):
            service, asset, _, workspaces, config = setup(tmp_path/'ledger')
            workspaces[0].update(cdp_url=page.fixture_endpoint, mode='headless')
            service.configure_workspaces(workspaces)
            service.configure({'mode':'pilot', 'autofill':'native', 'browser_mode':'headless',
                               'submission_mode':'submit'}, expected_version=service.settings_view()['version'])
            job = service.intake(url=source)
            service.eligibility(job['id'], 'ready', reason='Synthetic approved application')
            session = connect(service, service.reserve_session(request_id='popup', job_id=job['id'],
                identity_id='candidate', driver_id='fixture', workspace_ids=['workspace-0'],
                concurrency_limit=1, resume_asset_id=asset['id']), page.target_id)
            service.session_authority = (session['id'], 'fixture', 'host-workspace-0')
            attempt = service.attempt(session['attempt_id'])
            owner = {k:attempt[k] for k in ('worker_id','fence')}
            owner['attempt_id'] = attempt['id']
            client = LocalClient({'instance_id':service.instance_id}, service=service)
            config = {'cdp_url':page.fixture_endpoint, 'browser_mode':'headless', 'spool_dir':str(tmp_path/'spool')}
            yield page, service, session, owner, client, config, entry, final, receipts
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize('hosts', [
    ('jobs.example.test','forms.example.test'),
    ('vacancies.example.test','accounts.example.test'),
])
def test_popup_redirect_finishes_in_owned_application_and_submits(tmp_path, hosts):
    async def run():
        async with popup_fixture(tmp_path, hosts=hosts) as (page,s,session,own,client,cfg,entry,final,receipts):
            before = s.attempt(own['attempt_id'])
            result = await asyncio.to_thread(browser_action,cfg,client,own,s.application_context(own['attempt_id']),
                                             page.target_id,{'method':'click','selector':'a'})
            target = result['target_handoff']['target_id']
            child = await CDPBrowser.connect(page.fixture_endpoint,target_id=target,expected_mode='headless')
            try:
                cp = await child.get_current_page()
                for _ in range(100):
                    if await cp.evaluate('location.href') == final: break
                    await asyncio.sleep(.03)
                assert await cp.evaluate('location.href') == final
                gate = await asyncio.to_thread(s.browser_observe,**own,target_id=target,cdp_url=page.fixture_endpoint)
                assert gate['native_takeover_authorized'], gate
                package = s.application_context(own['attempt_id'])
                assert package['job']['url'] == final
                filled = await asyncio.to_thread(browser_action,cfg,client,own,package,target,
                                                 {'method':'fill','selector':'#name','value':'Synthetic Candidate'})
                assert filled['committed']
                submitted = await asyncio.to_thread(browser_action,cfg,client,own,package,target,
                                                     {'method':'submit','selector':'button'})
                assert submitted['status'] == 'applied', submitted
                assert receipts == ['/submitted']
                assert s.attempt(own['attempt_id'])['started_at'] == before['started_at']
                assert s.job(session['job_id'])['url'].endswith('/jobs/123')
            finally:
                await child.close()
    asyncio.run(run())


def test_normal_popup_still_submits_without_a_redirect_wait(tmp_path):
    async def run():
        async with popup_fixture(tmp_path,redirect=False) as (page,s,session,own,client,cfg,entry,final,receipts):
            result = await asyncio.to_thread(browser_action,cfg,client,own,s.application_context(own['attempt_id']),
                                             page.target_id,{'method':'click','selector':'a'})
            target = result['target_handoff']['target_id']
            package = s.application_context(own['attempt_id'])
            assert package['job']['url'] == entry
            filled = await asyncio.to_thread(browser_action,cfg,client,own,package,target,
                                             {'method':'fill','selector':'#name','value':'Synthetic Candidate'})
            assert filled['committed']
            submitted = await asyncio.to_thread(browser_action,cfg,client,own,package,target,
                                                 {'method':'submit','selector':'button'})
            assert submitted['status'] == 'applied' and receipts == ['/submitted']
    asyncio.run(run())
