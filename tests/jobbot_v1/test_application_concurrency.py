"""Parallel applications use synthetic state and the same retained browser profile."""
import json
import os
from pathlib import Path
import threading

import pytest

from test_dispatch_queue import enqueue, runtime_fixture


def shared_fixture(tmp_path, limit=3):
    service, asset, jobs, workspaces, config = runtime_fixture(tmp_path)
    workspace = dict(workspaces[0], connection_mode='existing')
    service.configure_workspaces([workspace])
    config['workspaces'] = [workspace]
    service.configure({'application_concurrency': limit}, expected_version=1)
    return service, asset, jobs, workspace, config


def reserve(service, asset, job, workspace, limit=3):
    return service.reserve_session(request_id=job['id'], job_id=job['id'],
        identity_id='candidate', driver_id='driver-'+job['id'],
        workspace_ids=[workspace['id']], concurrency_limit=limit, resume_asset_id=asset['id'])


def test_existing_profile_accepts_independent_sessions_and_counts_tabs(tmp_path):
    service, asset, jobs, workspace, _ = shared_fixture(tmp_path, 2)
    first, second, waiting = [reserve(service, asset, job, workspace, 2) for job in jobs]
    assert first['workspace_id'] == second['workspace_id'] == workspace['id']
    assert first['id'] != second['id'] and second['state'] == 'preparing'
    assert waiting['state'] == 'capacity_wait'
    assert len(service.sessions_view()['workspaces']) == 2  # No new profile created.


def test_queue_refills_independent_slots_and_lowering_does_not_cancel(tmp_path):
    service, asset, jobs, _, _ = shared_fixture(tmp_path, 2)
    enqueue(service, asset, jobs)
    first, second = service.queue_take(), service.queue_take()
    assert first and second and first['id'] != second['id']
    assert service.queue_take() is None
    service.configure({'application_concurrency': 1}, expected_version=2)
    assert service.queue_status()['active_count'] == 2
    service.queue_complete(second['id'], outcome='interrupted')
    assert service.queue_take() is None
    service.queue_complete(first['id'], outcome='interrupted')
    assert service.queue_take()['job_id'] == jobs[2]['id']


def test_dispatch_launches_two_without_waiting_for_first(tmp_path, monkeypatch):
    from job_applier import queue_runtime
    service, asset, jobs, workspace, config = shared_fixture(tmp_path, 2)
    enqueue(service, asset, jobs)
    configs = []
    class Running:
        pid = os.getpid()
        def poll(self):
            return None
    def launch(command, **kwargs):
        configs.append(json.loads(Path(kwargs['env']['JOBBOT_CONFIG']).read_text()))
        return Running()
    monkeypatch.setattr(queue_runtime.time, 'sleep', lambda *_: (_ for _ in ()).throw(AssertionError('launch waited for executor')))
    for _ in range(2):
        assert queue_runtime.dispatch_one(config, service, launcher=launch, wait=False)['state'] == 'dispatched'
    assert len(configs) == 2
    assert all(c['workspaces'] == [workspace] and c['concurrency_limit'] == 2 for c in configs)
    assert configs[0]['config_path'] != configs[1]['config_path']
    assert queue_runtime.dispatch_one(config, service, launcher=launch, wait=False)['state'] == 'waiting_for_executor_or_cleanup'


def test_recovery_visits_finished_executor_even_if_first_is_running(tmp_path, monkeypatch):
    from job_applier import queue_runtime, hermes_desktop
    service, asset, jobs, _, config = shared_fixture(tmp_path, 2)
    enqueue(service, asset, jobs)
    first, second = service.queue_take(), service.queue_take()
    with service.tx() as db:
        db.execute('UPDATE dispatch_queue SET executor_identity_json=? WHERE id=?',
                   (json.dumps({'live': True}), first['id']))
    monkeypatch.setattr(queue_runtime, 'process_matches', lambda identity: bool(identity.get('live')))
    monkeypatch.setattr(hermes_desktop, 'orphan_is_active', lambda *a, **kw: False)
    service.desktop_dispatch_spool = config['spool_dir']
    assert queue_runtime.recover_dispatch(service) is False
    assert next(i for i in service.queue_status()['items'] if i['id'] == second['id'])['state'] == 'finished'


def connected_shared(tmp_path, limit=3):
    from job_applier.workspace_host import WorkspaceHost
    from job_applier.workspace_process import process_identity
    service, asset, jobs, workspace, config = shared_fixture(tmp_path, limit)
    host = WorkspaceHost(config, workspace['id'], 'shared-host')
    service.host_registered(workspace['id'], host.host_id, process_identity(os.getpid()))
    sessions = []
    for i, job in enumerate(jobs[:limit]):
        current = reserve(service, asset, job, workspace, limit)
        current = service.session_connected(current['id'], host.host_id, 'tab-'+str(i), {'synthetic': True})
        service.session_browser_attachment(current['id'], host.host_id,
            {'browser_id': 'ws://shared', 'target_ids': [current['target_id']]})
        sessions.append(service.session(current['id']))
    return host, service, sessions


def test_capacity_reservation_is_atomic_for_shared_browser(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    service, asset, jobs, workspace, _ = shared_fixture(tmp_path, 2)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda job: reserve(service, asset, job, workspace, 2), jobs))
    assert sum(r['state'] == 'preparing' for r in results) == 2
    assert sum(r['state'] == 'capacity_wait' for r in results) == 1


def test_timeout_closes_only_its_tabs_and_keeps_other_application_running(tmp_path, monkeypatch):
    from job_applier import workspace_host
    host, service, sessions = connected_shared(tmp_path, 2)
    tabs = [{'type': 'page', 'targetId': s['target_id']} for s in sessions]
    tabs += [{'type': 'page', 'targetId': 'mail'},
             {'type': 'page', 'targetId': 'popup', 'openerId': sessions[0]['target_id']}]
    monkeypatch.setattr(workspace_host, 'endpoint_info', lambda _: {'webSocketDebuggerUrl': 'ws://shared'})
    cancelled = []
    monkeypatch.setattr('job_applier.hermes_desktop.cancel_driver', lambda cfg, driver, native_id: cancelled.append(driver) or True)
    async def command(endpoint, method, params=None):
        if method == 'Target.getTargets':
            return {'targetInfos': list(tabs)}
        assert method == 'Target.closeTarget'
        tabs[:] = [t for t in tabs if t['targetId'] != params['targetId']]
        return {'success': True}
    monkeypatch.setattr(workspace_host, 'browser_command', command)
    host.operation_lock(sessions[0]['id']).acquire()  # Simulate a stuck helper.
    host.expire_session(sessions[0])
    assert not host.exit.is_set()
    assert cancelled == [sessions[0]['driver_id']]
    assert service.session(sessions[0]['id'])['ended_at']
    assert service.session(sessions[1]['id'])['state'] == 'connected'
    assert {t['targetId'] for t in tabs} == {'mail', sessions[1]['target_id']}
    assert [s['id'] for s in host.active_sessions()] == [sessions[1]['id']]


def test_host_requests_for_different_tabs_overlap_without_sharing_authority(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    host, service, sessions = connected_shared(tmp_path, 2)
    barrier = threading.Barrier(2)
    def dispatch(request):
        barrier.wait(timeout=5)  # A browser-wide lock would deadlock this test.
        return {'session_id': request['session_id']}
    monkeypatch.setattr(host, 'dispatch', dispatch)
    class Pipe:
        def __init__(self, session):self.session, self.result = session, None
        def poll(self, timeout):return True
        def recv_bytes(self, size):return json.dumps({'session_id': self.session['id']}).encode()
        def send_bytes(self, value):self.result = json.loads(value)
        def close(self):pass
    pipes = [Pipe(s) for s in sessions]
    host.requests = 2
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(host.serve_request, pipes))
    assert [p.result for p in pipes] == [{'result': {'session_id': s['id']}} for s in sessions]
    assert host.operation_lock(sessions[0]['id']) is host.operation_lock(sessions[0]['id'])
    assert host.requests == 0


def test_foreign_target_and_driver_remain_scoped_with_same_profile(tmp_path):
    from job_applier.managed_shared import ProtocolError
    from job_applier.managed_client import LocalClient
    host, service, sessions = connected_shared(tmp_path, 2)
    first, second = sessions
    with pytest.raises(ProtocolError, match='driver_owned_elsewhere'):
        host.dispatch({'instance_id': service.instance_id, 'session_id': first['id'],
                       'driver_id': second['driver_id'], 'operation': 'context'})
    with LocalClient(host.config, authority=(first['id'], first['driver_id'], host.host_id)) as client:
        attempt = service.attempt(first['attempt_id'])
        with pytest.raises(ProtocolError, match='target_not_owned'):
            client.call('bind_target', attempt_id=attempt['id'], worker_id=attempt['worker_id'],
                        fence=attempt['fence'], target_id=second['target_id'], url=service.job(first['job_id'])['url'])


def test_helper_errors_record_against_each_session_after_other_tabs_connect(tmp_path, monkeypatch):
    from job_applier.managed_shared import ProtocolError
    host, service, sessions = connected_shared(tmp_path, 2)
    def fail(request):raise ProtocolError('control_changed')
    monkeypatch.setattr(host, '_dispatch', fail)
    for session in sessions:
        with pytest.raises(ProtocolError, match='control_changed'):
            host.dispatch({'instance_id': service.instance_id, 'session_id': session['id'],
                           'driver_id': session['driver_id'], 'operation': 'browser'})
        events = service.attempt_report(session['attempt_id'])['timeline']
        assert any(e.get('payload', {}).get('error_type') == 'control_changed' for e in events)


def test_concurrency_dropdown_round_trip_and_active_summary():
    from test_dispatch_queue_ui import dashboard_check
    dashboard_check(r'''
w.drawSettings({version:1,values:{application_concurrency:3},supported:{}});w.noRefresh();
const select=doc.getElementById('settings-concurrency');
assert(select.options.length===5&&select.value==='3','Saved concurrency/options missing');
select.value='5';let payload;
w.fetch=async(path,options)=>{payload=JSON.parse(options.body);return {ok:true,status:200,json:async()=>({})};};
await doc.getElementById('settings-form').onsubmit({preventDefault(){}});
assert(payload.changes.application_concurrency===5,'Concurrency must save as a number');
v.dispatch_queue.active_count=3;v.dispatch_queue.concurrency_limit=5;w.draw(v);
assert(doc.getElementById('dispatcher-status').textContent.includes('3 of 5 applications active'),'Missing active slot count');
w.drawSettings({version:2,values:{application_concurrency:1},supported:{}});
assert(select.value==='1','Lower limit did not restore');
''')


def test_watch_fills_slots_refills_completion_and_drains_pause(tmp_path, monkeypatch):
    from job_applier import queue_runtime, hermes_desktop
    service, asset, jobs, _, config = shared_fixture(tmp_path, 2)
    enqueue(service, asset, jobs, start_now=True)
    running = {};launches = []
    class Process:
        def __init__(self, pid):self.pid, self.done = pid, False
        def poll(self):return 0 if self.done else None
    def launch(command, **kwargs):
        proc = Process(10000+len(launches));running[proc.pid] = proc;launches.append(proc)
        assert service.queue_status()['active_count'] <= 2
        return proc
    actual = queue_runtime.dispatch_one
    monkeypatch.setattr(queue_runtime, 'dispatch_one', lambda cfg, svc, **kw: actual(cfg, svc, launcher=launch, **kw))
    monkeypatch.setattr(queue_runtime, 'process_identity', lambda pid: {'pid': pid})
    monkeypatch.setattr(queue_runtime, 'process_matches', lambda identity: identity.get('pid') in running and not running[identity['pid']].done)
    monkeypatch.setattr(hermes_desktop, 'orphan_is_active', lambda *a, **kw: False)
    sleeps = []
    class Finished(Exception):pass
    def tick(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 1:
            assert len(launches) == 2
            launches[0].done = True
        elif len(sleeps) == 2:
            assert len(launches) == 3
            service.queue_control(command='pause_all')
            for proc in launches:proc.done = True
        else:
            assert service.queue_status()['active_count'] == 0
            raise Finished
    monkeypatch.setattr(queue_runtime.time, 'sleep', tick)
    with pytest.raises(Finished):queue_runtime.watch(config, service)
    assert len(launches) == 3 and service.queue_status()['automation_paused']


def test_migration_retains_existing_sessions_and_submission_history(tmp_path):
    from job_applier.managed_migrations import migrate
    from test_local_sessions import connect, own
    service, asset, jobs, _, _ = runtime_fixture(tmp_path)
    from test_local_sessions import reserve as reserve_managed
    session = connect(service, reserve_managed(service, asset, jobs))
    service.finish(**own(service, session), outcome='ready_for_review', evidence='Synthetic review', quiescent=True)
    before = service.session(session['id'])
    attempt = service.attempt(session['attempt_id'])
    # Reconstruct only the old schema index, retaining actual synthetic history.
    with service.tx() as db:
        db.execute('DROP INDEX active_workspace_sessions')
        db.execute('CREATE UNIQUE INDEX one_workspace_session ON application_sessions(workspace_id) WHERE ended_at IS NULL AND workspace_id IS NOT NULL')
        db.execute('DELETE FROM schema_migrations WHERE version=25')
    migrate(service.db_path)
    assert service.session(session['id']) == before
    assert service.attempt(session['attempt_id']) == attempt


def test_native_input_keeps_one_foreground_target_until_mouse_release():
    import asyncio
    from job_applier.cdp_client import CDPBrowser, CDPPage
    active = [];clicks = []
    class Connection:
        def __init__(self, target):self.target = target
        async def call(self, method, params):
            if method == 'Page.bringToFront':active[:] = [self.target]
            elif method == 'Input.dispatchMouseEvent':
                assert active == [self.target], 'Another tab stole focus midway through a click'
                if params['type'] == 'mouseReleased':clicks.append(self.target)
            await asyncio.sleep(.005)
    async def run():
        pages = []
        for i in range(5):
            connection = Connection(str(i));page = CDPPage(connection, str(i), 'http://fixture')
            CDPBrowser('http://concurrent-input-fixture', connection, page, str(i))
            async def evaluate(*args):return {'pointer_ready': True, 'x': 10, 'y': 20}
            page.evaluate_function = evaluate;pages.append(page)
        result = await asyncio.gather(*(page.click_observed('fixture', {}) for page in pages))
        assert all(r['clicked'] for r in result)
    asyncio.run(run())
    assert sorted(clicks) == ['0', '1', '2', '3', '4']


@pytest.mark.parametrize('selected', [False, True])
def test_manual_request_does_not_start_unrequested_jobs_when_automatic_is_off(tmp_path, monkeypatch, selected):
    from job_applier import queue_runtime
    service, asset, jobs, _, config = shared_fixture(tmp_path, 3)
    enqueue(service, asset, jobs)
    if selected:enqueue(service, asset, jobs[1:2], request='one-immediate', start_now=True)
    else:service.queue_control(command='run_next')
    launched = []
    def dispatch(cfg, svc, **kwargs):
        item = svc.queue_take();launched.append(item)
        return {'state': 'dispatched', 'item_id': item['id']}
    monkeypatch.setattr(queue_runtime, 'dispatch_one', dispatch)
    class TickComplete(Exception):pass
    def stop(_):raise TickComplete
    monkeypatch.setattr(queue_runtime.time, 'sleep', stop)
    with pytest.raises(TickComplete):queue_runtime.watch(config, service)
    assert len(launched) == 1
    assert launched[0]['job_id'] == jobs[1 if selected else 0]['id']
