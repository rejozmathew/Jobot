"""Startup delays retain synthetic queue requests instead of spending attempts."""
import json
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from test_dispatch_queue import runtime_fixture, enqueue


@pytest.mark.parametrize('unavailable', ['executor', 'browser'])
def test_startup_wait_keeps_request_and_starts_deadline_only_when_ready(tmp_path, monkeypatch, unavailable):
    from job_applier import queue_runtime as queue, hermes_desktop as desktop
    from job_applier import workspace_attachment as attachment, workspace_host as host
    s, asset, jobs, ws, cfg = runtime_fixture(tmp_path)
    cfg['hermes_desktop'] = {}
    for workspace in ws:workspace['connection_mode'] = 'existing'
    now = ['2026-10-07T10:00:00+00:00']
    s.now = lambda: now[0]
    item = enqueue(s, asset, [jobs[0]], start_now=True)['items'][0]
    ready = [False]
    monkeypatch.setattr(desktop, 'backend_ready', lambda _: ready[0] or unavailable != 'executor', raising=False)
    monkeypatch.setattr(attachment, 'existing_profile_process', lambda _: 123 if ready[0] or unavailable != 'browser' else None)
    monkeypatch.setattr(attachment, 'verify_connection_process', lambda *args: 'headed')
    monkeypatch.setattr(host, 'endpoint_info', lambda _: {'webSocketDebuggerUrl': 'ws://127.0.0.1/browser'})
    launches = []
    def launch(*args, **kwargs):
        assert ready[0], 'A starting dependency must not consume a queued application'
        launches.append(json.loads(Path(kwargs['env']['JOBBOT_CONFIG']).read_text()))
        return type('Running', (), {'pid': 0, 'poll': lambda self: None})()
    for minute in ('10:01', '10:40', '11:20'):
        now[0] = '2026-10-07T'+minute+':00+00:00'
        assert queue.dispatch_one(cfg, s, launcher=launch, wait=False)['state'] == 'waiting_for_'+unavailable+'_startup'
        current = s.queue_status()['latest_by_job'][jobs[0]['id']]
        assert current['id'] == item['id'] and current['state'] == 'queued'
        assert current['attempt_number'] == 1
        assert not (Path(cfg['spool_dir'])/'dispatch'/item['id']/'runtime.json').exists()
        with s.read() as db:
            assert db.execute('SELECT started_at FROM dispatch_queue WHERE id=?', (item['id'],)).fetchone()[0] is None
    ready[0] = True
    assert queue.dispatch_one(cfg, s, launcher=launch, wait=False)['item_id'] == item['id']
    assert len(launches) == 1
    assert launches[0]['application_deadline']['started_at'] == now[0]


def test_startup_wait_preserves_wake_and_due_check_and_keeps_heartbeat(tmp_path, monkeypatch):
    from job_applier import queue_runtime as queue, hermes_desktop as desktop
    s, asset, jobs, _, cfg = runtime_fixture(tmp_path)
    cfg['hermes_desktop'] = {}
    enqueue(s, asset, [jobs[0]], start_now=True)
    before = s.queue_status()
    monkeypatch.setattr(desktop, 'backend_ready', lambda _: False, raising=False)
    monkeypatch.setattr(queue.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not launch'))
    assert queue.watch(cfg, s, once=True)['state'] == 'waiting_for_executor_startup'
    after = s.queue_status()
    assert after['wake_requested'] == before['wake_requested'] == 1
    assert after['next_automatic_at'] == before['next_automatic_at']
    assert after['worker_online'] and after['heartbeat_at']
    assert after['detail'] == 'waiting_for_executor_startup'
    assert after['active_count'] == 0 and after['ready_count'] >= 1


def test_paused_or_empty_queue_does_not_probe_startup(tmp_path, monkeypatch):
    from job_applier import queue_runtime as queue, hermes_desktop as desktop
    s, asset, jobs, _, cfg = runtime_fixture(tmp_path)
    cfg['hermes_desktop'] = {}
    monkeypatch.setattr(desktop, 'backend_ready', lambda _: pytest.fail('no ready work'), raising=False)
    assert queue.dispatch_one(cfg, s)['state'] == 'empty'
    enqueue(s, asset, [jobs[0]])
    s.queue_control(command='pause_all')
    assert queue.dispatch_one(cfg, s)['state'] == 'paused'


def test_custom_executor_does_not_depend_on_hermes_desktop(tmp_path, monkeypatch):
    from job_applier import queue_runtime as queue, hermes_desktop as desktop
    s, asset, jobs, _, cfg = runtime_fixture(tmp_path)
    cfg['hermes_command'] = ['fixture-executor', '{prompt_file}']
    enqueue(s, asset, [jobs[0]])
    monkeypatch.setattr(desktop, 'backend_ready', lambda _: pytest.fail('custom executor'), raising=False)
    done = type('Done', (), {'pid': 0, 'returncode': 0, 'poll': lambda self: 0})()
    assert queue.dispatch_one(cfg, s, launcher=lambda *a, **k: done)['state'] == 'finished'


def test_waiting_for_startup_still_supervises_existing_owned_work(tmp_path, monkeypatch):
    from job_applier import queue_runtime as queue, hermes_desktop as desktop, application_deadline
    s, asset, jobs, _, cfg = runtime_fixture(tmp_path)
    cfg['hermes_desktop'] = {}
    s.configure({'application_concurrency': 2}, expected_version=s.settings_view()['version'])
    enqueue(s, asset, jobs[:2])
    active = s.queue_take()
    with s.tx() as db:
        db.execute('UPDATE dispatch_queue SET executor_identity_json=? WHERE id=?', ('{"pid":123}', active['id']))
    observed = []
    monkeypatch.setattr(application_deadline, 'dispatch_expired', lambda service, item, **kw: observed.append(item['id']) or False)
    monkeypatch.setattr(queue, 'process_matches', lambda identity: identity.get('pid') == 123)
    monkeypatch.setattr(desktop, 'backend_ready', lambda _: False)
    assert queue.dispatch_one(cfg, s, wait=False)['state'] == 'waiting_for_executor_startup'
    assert observed == [active['id']]
    status = s.queue_status()
    assert status['active_count'] == 1 and status['ready_count'] == 1
    assert status['latest_by_job'][jobs[0]['id']]['state'] == 'dispatched'


def test_startup_rpc_uses_its_short_timeout():
    from job_applier.hermes_desktop import RPC
    observed = []
    class Socket:
        def send(self, value):pass
        def recv(self, timeout=None):
            observed.append(timeout)
            raise TimeoutError('synthetic unready backend')
    with pytest.raises(TimeoutError):RPC(Socket(), timeout=2).call('session.active_list', {})
    assert len(observed) == 1 and 0 < observed[0] <= 2


@pytest.mark.parametrize('failure', [None, OSError('starting'), ValueError('no bootstrap'), httpx.ConnectError('starting')])
def test_backend_readiness_uses_bounded_read_only_rpc(monkeypatch, failure):
    from job_applier import hermes_desktop as desktop
    calls = []
    class RPC:
        def call(self, method, params):
            calls.append((method, params))
            return {'sessions': []}
    @contextmanager
    def connection(options, **kwargs):
        assert kwargs == {'timeout': 2, 'rpc_timeout': 2}
        if failure:raise failure
        yield RPC(), None
    monkeypatch.setattr(desktop, 'connection', connection)
    assert desktop.backend_ready({}) is (failure is None)
    assert calls == ([] if failure else [('session.active_list', {})])


def test_browser_startup_accepts_any_usable_workspace_and_preserves_ownership(tmp_path, monkeypatch):
    from job_applier import queue_runtime as queue, hermes_desktop as desktop
    from job_applier import workspace_attachment as attachment, workspace_host as host
    s, _, _, ws, cfg = runtime_fixture(tmp_path)
    cfg['hermes_desktop'] = {}
    cfg['workspaces'] = [dict(ws[0], id='unready', connection_mode='existing'),
                         dict(ws[0], id='ready', connection_mode='existing')]
    monkeypatch.setattr(desktop, 'backend_ready', lambda _: True, raising=False)
    monkeypatch.setattr(attachment, 'existing_profile_process', lambda w: 123 if w['id'] == 'ready' else None)
    checked = []
    monkeypatch.setattr(attachment, 'verify_connection_process', lambda w, pid: checked.append((w['id'], pid)))
    monkeypatch.setattr(host, 'endpoint_info', lambda _: {'webSocketDebuggerUrl': 'ws://127.0.0.1/browser'})
    assert queue.dispatch_startup(cfg) is None
    assert checked == [('ready', 123)]
    monkeypatch.setattr(attachment, 'verify_connection_process', lambda *args: (_ for _ in ()).throw(ValueError('wrong profile')))
    assert queue.dispatch_startup(cfg) == 'waiting_for_browser_startup'
