"""Opt-in proof of visible application windows in one disposable retained profile."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import threading

import pytest

from job_applier.application_runtime import resolve_config, session_call, start
from job_applier.cdp_client import CDPBrowser
from job_applier.workspace_host import browser_command, ensure_host, lock_path, workspace_record
from job_applier.workspace_process import FileLock, process_matches
from test_dispatch_queue import runtime_fixture
from test_local_browser_lifecycle import free_port, wait_for


pytestmark = pytest.mark.skipif(not os.environ.get('JOBBOT_BROWSER_TEST_EXE'),
    reason='Explicit browser needed for disposable parallel-tab fixture')


@pytest.mark.parametrize('count', [3, 5])
def test_shared_cookies_parallel_input_restart_stop_and_host_recovery(tmp_path, count):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = b'''<title>Concurrent fixture</title><label>Answer<input id="answer"></label>
                <label>Autofill result<input id="autofill-result"></label>
                <button id="autofill" onclick="fillVisible()">Autofill</button>
                <button id="popup" onclick="window.open('/popup'+location.pathname,'_blank')">Open popup</button>
                <script>
                async function fillVisible(){
                  window.fillState='filling';
                  for(let i=0;i<4;i++){
                    await new Promise(resolve=>setTimeout(resolve,250));
                    // Simplify 3.1.8 waits for visibility before each field fill.
                    if(document.visibilityState==='hidden')await new Promise(resolve=>{
                      const resume=()=>{if(document.visibilityState!=='hidden'){
                        document.removeEventListener('visibilitychange',resume);resolve();
                      }};
                      document.addEventListener('visibilitychange',resume);
                    });
                    document.querySelector('#autofill-result').value='filled-'+i;
                  }
                  window.fillState='complete';
                }
                </script>'''
            self.send_response(200);self.send_header('Content-Type', 'text/html');self.end_headers();self.wfile.write(data)
        def log_message(self, *args):pass
    web = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{web.server_port}'
    service, asset, _, workspaces, cfg = runtime_fixture(tmp_path)
    profile = tmp_path/'shared-profile';profile.mkdir()
    workspace = dict(workspaces[0], user_data_dir=str(profile),
        browser_executable=os.environ['JOBBOT_BROWSER_TEST_EXE'],
        cdp_url=f'http://127.0.0.1:{free_port()}', connection_mode='existing')
    cfg.update(workspaces=[workspace], concurrency_limit=count, require_simplify=False,
               authorize_requested_urls=True, legacy_history_paths=[])
    Path(cfg['config_path']).write_text(json.dumps(cfg))
    cfg = resolve_config(cfg['config_path'])
    service.configure({'application_concurrency': count}, expected_version=1)
    process = subprocess.Popen([workspace['browser_executable'], '--user-data-dir='+str(profile),
        '--remote-debugging-address=127.0.0.1', '--remote-debugging-port='+workspace['cdp_url'].rsplit(':', 1)[1],
        '--no-first-run', '--no-default-browser-check', base+'/dashboard'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    endpoint = workspace['cdp_url'];sessions = []
    def command(method, params=None):return asyncio.run(browser_command(endpoint, method, params))
    def pages():return [t for t in command('Target.getTargets')['targetInfos'] if t['type'] == 'page']
    def available():
        try:return any(t['url'] == base+'/dashboard' for t in pages())
        except Exception:return False
    def evaluate(target, expression):
        async def read():
            browser = await CDPBrowser.connect(endpoint, target_id=target)
            try:return await (await browser.get_current_page()).evaluate(expression)
            finally:await browser.close()
        return asyncio.run(read())
    def call(session, operation, params=None):
        return session_call(cfg, session['id'], operation, params or {}, session['driver_id'])
    def apply(index):
        result = start(cfg, url=base+f'/jobs/{index}', driver_id=f'fixture-{index}',
                       request_id=f'request-{index}', wait_seconds=0)
        sessions.append(result['session_id'])
        return result
    try:
        wait_for(available)
        dashboard = next(t['targetId'] for t in pages() if t['url'] == base+'/dashboard')
        wait_for(lambda: evaluate(dashboard, 'document.title') == 'Concurrent fixture')
        evaluate(dashboard, "document.cookie='fixture=retained; path=/'")
        requests = [apply(i) for i in range(count)]
        wait_for(lambda: all(service.session(r['session_id'])['state'] == 'connected' for r in requests), timeout=90)
        active = [service.session(r['session_id']) for r in requests]
        assert len({s['target_id'] for s in active}) == count
        windows = [command('Browser.getWindowForTarget', {'targetId': s['target_id']})['windowId'] for s in active]
        assert len(set(windows)) == count
        assert command('Browser.getWindowForTarget', {'targetId': dashboard})['windowId'] not in windows
        assert {s['workspace_id'] for s in active} == {workspace['id']}
        assert len(pages()) == count+1 and process.poll() is None
        for session in active:
            assert evaluate(session['target_id'], 'document.cookie') == 'fixture=retained'
            assert evaluate(session['target_id'], 'navigator.webdriver') is False
        # Check after the input connection and temporary focus emulation end.
        # All applications must keep progressing between clicks in other windows.
        with ThreadPoolExecutor(max_workers=count) as pool:
            list(pool.map(lambda s: call(s, 'browser', {'method': 'click', 'selector': '#autofill'}), active))
        wait_for(lambda: all(evaluate(s['target_id'], 'window.fillState') == 'complete' for s in active), timeout=20)
        assert all(evaluate(s['target_id'], 'document.visibilityState') == 'visible' for s in active)
        assert all(evaluate(s['target_id'], 'document.querySelector("#autofill-result").value') == 'filled-3' for s in active)
        barrier = threading.Barrier(count)
        def fill(pair):
            index, session = pair;barrier.wait(timeout=10)
            assert call(session, 'browser', {'method': 'fill', 'selector': '#answer', 'value': f'answer-{index}'})['committed']
        with ThreadPoolExecutor(max_workers=count) as pool:list(pool.map(fill, enumerate(active)))
        assert [evaluate(s['target_id'], 'document.querySelector("#answer").value') for s in active] == [f'answer-{i}' for i in range(count)]
        with ThreadPoolExecutor(max_workers=count) as pool:
            clicks = list(pool.map(lambda s: call(s, 'browser', {'method': 'click', 'selector': '#popup'}), active))
        assert all(c.get('clicked') for c in clicks), clicks
        (tmp_path/'pointer-results.json').write_text(json.dumps({'results': clicks, 'tabs': pages(),
            'states': [evaluate(s['target_id'], '({visible:document.visibilityState,focus:document.hasFocus(),active:navigator.userActivation.isActive})') for s in active]}))
        wait_for(lambda: len(pages()) == 2*count+1)
        # A restart retains its attempt/deadline and touches no other application's tab.
        first = active[0]
        deadline = json.loads(first['metadata_json'])['application_deadline']
        call(first, 'restart')
        wait_for(lambda: service.session(first['id'])['state'] == 'connected' and
                 service.session(first['id'])['target_id'] != first['target_id'], timeout=60)
        replacement = service.session(first['id'])
        assert replacement['attempt_id'] == first['attempt_id']
        assert json.loads(replacement['metadata_json'])['application_deadline'] == deadline
        assert evaluate(dashboard, 'document.cookie') == 'fixture=retained'
        for i, session in enumerate(active[1:], 1):
            assert evaluate(session['target_id'], 'document.querySelector("#answer").value') == f'answer-{i}'
        # Finishing one slot leaves the browser and all peer applications alive.
        call(replacement, 'finish', {'outcome': 'ready_for_review', 'evidence': 'Synthetic form complete', 'quiescent': True})
        wait_for(lambda: service.session(first['id'])['ended_at'])
        assert all(not service.session(s['id'])['ended_at'] for s in active[1:])
        later = apply(count)
        wait_for(lambda: service.session(later['session_id'])['state'] == 'connected', timeout=60)
        assert evaluate(service.session(later['session_id'])['target_id'], 'document.cookie') == 'fixture=retained'
        # Lost host recovery cleans every abandoned owned tab, preserving the profile.
        host = json.loads(workspace_record(service, workspace['id'])['host_identity_json'])
        os.kill(host['pid'], signal.SIGTERM)
        # Linux can expose a zombie leader while its other threads are still
        # releasing shared descriptors. Recovery also requires the profile lock.
        wait_for(lambda: not process_matches(host) and not FileLock.is_locked(lock_path(workspace)))
        assert process.poll() is None
        ensure_host(cfg, workspace['id'])
        wait_for(lambda: all(service.session(sid)['ended_at'] for sid in sessions), timeout=60)
        assert [t['targetId'] for t in pages()] == [dashboard]
        assert evaluate(dashboard, 'document.cookie') == 'fixture=retained'
    finally:
        for sid in sessions:
            try:
                session = service.session(sid)
                if not session['ended_at']:call(session, 'stop')
            except Exception:pass
        # Only this test owns the disposable browser. Runtime cleanup never closes it.
        try:command('Browser.close')
        except Exception:pass
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)
        web.shutdown();web.server_close()
