"""Synthetic contention must not destroy an owned executor or its deadline."""
from contextlib import contextmanager
import json
import sqlite3

import pytest

from job_applier import managed, queue_runtime as qr
from test_dispatch_queue import enqueue, runtime_fixture
from test_existing_browser import fixture_host


@pytest.mark.parametrize('projection', ['health', 'settings_view', 'view', 'queue_status', 'sessions_view'])
def test_operator_reads_do_not_request_writer_lock(tmp_path, monkeypatch, projection):
    host, service, session = fixture_host(tmp_path)
    original = managed.connect
    def impatient(*args, **kwargs):
        db = original(*args, **kwargs)
        db.execute('PRAGMA busy_timeout=0')
        return db
    monkeypatch.setattr(managed, 'connect', impatient)
    with original(service.db_path) as writer:
        writer.execute('BEGIN IMMEDIATE')
        result = getattr(service, projection)()
        assert result is not None
        # Constructing a per-call service must be a reader as well.
        assert managed.Service(service.db_path).instance_id == service.instance_id
        writer.rollback()


def test_read_snapshot_cannot_accidentally_write(tmp_path):
    _, service, _ = fixture_host(tmp_path)
    with service.read() as db:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            db.execute("UPDATE instance SET settings_json='{}'")


@pytest.mark.parametrize('table,column', [
    ('managed_events', 'attempt_id'), ('managed_actions', 'attempt_id'),
    ('dispatch_queue', 'job_id'), ('application_sessions', 'job_id')])
def test_hot_history_lookup_is_indexed(tmp_path, table, column):
    _, service, _ = fixture_host(tmp_path)
    with service.tx() as db:
        plan = ' '.join(str(tuple(r)) for r in db.execute(
            f'EXPLAIN QUERY PLAN SELECT * FROM {table} WHERE {column}=?', ('synthetic',)))
    assert 'SEARCH' in plan and 'SCAN ' not in plan


def test_watch_recovers_busy_without_exiting(tmp_path, monkeypatch):
    service, asset, jobs, ws, cfg = runtime_fixture(tmp_path)
    service.queue_control(command='pause_all')
    heartbeat = service.queue_heartbeat
    calls = []
    def busy_once(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError('database is locked')
        return heartbeat(*args, **kwargs)
    monkeypatch.setattr(service, 'queue_heartbeat', busy_once)
    monkeypatch.setattr(qr.time, 'sleep', lambda _: None)
    assert qr.watch(cfg, service, once=True)['state'] == 'paused'
    assert len(calls) > 1


def test_launched_executor_survives_identity_write_contention(tmp_path, monkeypatch):
    service, asset, jobs, ws, cfg = runtime_fixture(tmp_path)
    enqueue(service, asset, [jobs[0]])
    transaction = service.tx
    process = type('Executor', (), {'pid': 987654321, 'poll': lambda self: None})()
    state = {'launched': False, 'blocked': False}
    @contextmanager
    def busy_after_launch():
        if state['launched'] and not state['blocked']:
            state['blocked'] = True
            raise sqlite3.OperationalError('database is locked')
        with transaction() as db:
            yield db
    def launch(*args, **kwargs):
        assert not state['launched']
        state['launched'] = True
        return process
    monkeypatch.setattr(service, 'tx', busy_after_launch)
    monkeypatch.setattr(qr, 'process_identity', lambda pid: {'pid': pid})
    result = qr.dispatch_one(cfg, service, launcher=launch, wait=False)
    item_id = result['item_id']
    clock = service.dispatch_clocks[item_id]
    assert service.dispatch_processes[item_id] is process
    assert qr.recover_dispatch(service) is False
    assert service.dispatch_clocks[item_id] is clock
    with transaction() as db:
        item = dict(db.execute('SELECT * FROM dispatch_queue WHERE id=?', (item_id,)).fetchone())
    assert json.loads(item['executor_identity_json']) == {'pid': process.pid}
    assert item['state'] == 'dispatched'


def test_deadline_cleanup_starts_even_when_run_read_is_busy(tmp_path, monkeypatch):
    from job_applier import workspace_host as wh
    host, service, session = fixture_host(tmp_path)
    host.session_deadline = lambda _: type('Clock', (), {'expired': lambda self: True})()
    @contextmanager
    def busy():
        raise sqlite3.OperationalError('database is locked')
        yield
    monkeypatch.setattr(host.service, 'tx', busy)
    monkeypatch.setattr(host.service, 'read', busy, raising=False)
    started = []
    class Thread:
        def __init__(self, target, args, **kwargs): self.args = args
        def start(self): started.append(self.args[0]['id'])
    monkeypatch.setattr(wh.threading, 'Thread', Thread)
    host.supervise_session(session)
    assert started == [session['id']]


def test_deadline_cancels_driver_despite_busy_stop_record(tmp_path, monkeypatch):
    from job_applier import application_deadline, hermes_desktop
    host, service, session = fixture_host(tmp_path)
    monkeypatch.setattr(application_deadline, 'request_stop', lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError('database is locked')))
    cancelled = []
    monkeypatch.setattr(hermes_desktop, 'cancel_driver', lambda *a: cancelled.append(a) or True)
    closed = []
    async def close(s): closed.append(s['id'])
    monkeypatch.setattr(host, 'close_application_tabs', close)
    host.deadline_cleanups.add(session['id'])
    host.expire_session(session)
    assert cancelled and closed == [session['id']]
    assert session['id'] not in host.deadline_cleanups


def test_host_monitor_survives_busy_heartbeat(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from job_applier import workspace_host as wh
    host, service, session = fixture_host(tmp_path)
    active_calls=[]
    def active():
        active_calls.append(1)
        return [] if len(active_calls)==1 else [session]
    monkeypatch.setattr(host,'active_sessions',active)
    beats=[]
    def heartbeat(*a):
        beats.append(1)
        if len(beats)==1:raise sqlite3.OperationalError('database is locked')
    monkeypatch.setattr(host.service,'host_seen',heartbeat)
    supervised=[]
    monkeypatch.setattr(host,'supervise_session',lambda s:supervised.append(s['id']))
    stops=[]
    monkeypatch.setattr(host,'stop_session',lambda *a,**k:stops.append(a))
    waits=[]
    def wait(_):
        waits.append(1)
        assert not stops  # Only explicit host exit may enter shutdown cleanup.
        return len(waits)>2
    monkeypatch.setattr(host.exit,'wait',wait)
    monkeypatch.setattr(host,'serve_requests',lambda _:None)
    monkeypatch.setattr(wh,'Listener',lambda *a,**k:nullcontext())
    monkeypatch.setattr('job_applier.workspace_linux.create_linux_listener',lambda *a:nullcontext())
    monkeypatch.setattr('job_applier.workspace_linux.cleanup_linux_socket',lambda *a:None)
    host.run()
    assert supervised == [session['id']]
    assert len(stops)==1 and host.exit.is_set()


def test_sql_errors_are_not_misclassified_as_transient_contention(tmp_path, monkeypatch):
    service, asset, jobs, ws, cfg = runtime_fixture(tmp_path)
    monkeypatch.setattr(service,'queue_heartbeat',lambda *a:(_ for _ in ()).throw(sqlite3.OperationalError('no such table: broken')))
    with pytest.raises(sqlite3.OperationalError, match='no such table'):
        qr.watch(cfg, service, once=True)


def test_expired_dispatch_cancels_even_if_database_bookkeeping_is_busy(tmp_path, monkeypatch):
    from pathlib import Path
    from job_applier import application_deadline as budget
    service,asset,jobs,ws,cfg=runtime_fixture(tmp_path)
    item=enqueue(service,asset,[jobs[0]])['items'][0]
    root=Path(cfg['spool_dir'])/'dispatch'/item['id'];root.mkdir(parents=True)
    (root/'runtime.json').write_text(json.dumps(budget.freeze({}, {'application_time_limit_minutes':30},'2020-01-01T00:00:00+00:00')))
    service.desktop_dispatch_spool=cfg['spool_dir']
    monkeypatch.setattr(qr,'find_sessions',lambda *a:(_ for _ in ()).throw(sqlite3.OperationalError('database is locked')))
    stopped=[]
    monkeypatch.setattr(budget,'stop_process',lambda identity:stopped.append(identity) or True)
    item=dict(item,executor_identity_json=json.dumps({'pid':123,'created':456}))
    assert budget.dispatch_expired(service,item)
    assert stopped==[{'pid':123,'created':456}]
    assert json.loads((root/'deadline.json').read_text())['reason']==budget.REASON


@pytest.mark.parametrize('path', ['/comm/jobs/view/123456/', '/comm/jobs/view/example-engineer-123456/'])
def test_linkedin_notification_route_retains_explicit_posting(path):
    from job_applier.managed_identity import linkedin_identity, same_job_url
    assert linkedin_identity('https://www.linkedin.com'+path) == linkedin_identity('https://www.linkedin.com/jobs/view/123456')
    assert same_job_url('https://www.linkedin.com'+path, 'https://www.linkedin.com/jobs/view/123456')
    assert not same_job_url('https://www.linkedin.com'+path, 'https://www.linkedin.com/jobs/view/999999')


def test_prelaunch_contention_resumes_the_same_reservation(tmp_path, monkeypatch):
    service, asset, jobs, ws, cfg = runtime_fixture(tmp_path)
    enqueue(service, asset, [jobs[0]])
    brief=qr.application_brief
    calls=[]
    def busy_once(*args):
        calls.append(1)
        if len(calls)==1:raise sqlite3.OperationalError('database is locked')
        return brief(*args)
    monkeypatch.setattr(qr,'application_brief',busy_once)
    with pytest.raises(sqlite3.OperationalError):qr.dispatch_one(cfg,service,wait=False)
    with service.read() as db:
        reserved=dict(db.execute("SELECT * FROM dispatch_queue WHERE state='dispatched'").fetchone())
    launched=[]
    process=type('Executor',(),{'pid':987654321,'poll':lambda self:None})()
    def launch(*a,**k):launched.append(1);return process
    result=qr.dispatch_one(cfg,service,launcher=launch,wait=False)
    assert result['state']=='dispatched' and result['item_id']==reserved['id']
    assert launched==[1]


def test_pending_identity_write_cannot_starve_cached_deadline(tmp_path, monkeypatch):
    service,asset,jobs,ws,cfg=runtime_fixture(tmp_path)
    enqueue(service,asset,[jobs[0]])
    process=type('Executor',(),{'pid':987654321,'poll':lambda self:None})()
    result=qr.dispatch_one(cfg,service,launcher=lambda *a,**k:process,wait=False)
    service.dispatch_identity_pending={result['item_id']:{'pid':process.pid}}
    @contextmanager
    def busy():
        raise sqlite3.OperationalError('database is locked')
        yield
    monkeypatch.setattr(service,'tx',busy)
    checked=[]
    monkeypatch.setattr('job_applier.application_deadline.dispatch_expired',lambda service,item,**kw:checked.append(item['id']))
    with pytest.raises(sqlite3.OperationalError):qr.recover_dispatch(service)
    assert checked==[result['item_id']]


def test_preparation_busy_retries_owned_cleanup_without_ending_attempt(tmp_path, monkeypatch):
    host,service,session=fixture_host(tmp_path)
    monkeypatch.setattr(host,'start_browser',lambda:None)
    prepared=[];closed=[]
    async def prepare(s):
        prepared.append(s['id'])
        return 'target-'+str(len(prepared)),{'profile_verified':True,'endpoint_verified':True,'target_operable':True,
            'browser_mode':'headed','simplify':'unverified','observed_at':service.now()}
    async def close(s):closed.append(s['id'])
    monkeypatch.setattr(host,'prepare_target',prepare)
    monkeypatch.setattr(host,'close_application_tabs',close)
    connected=host.service.session_connected
    calls=[]
    def busy_once(*a,**kw):
        calls.append(1)
        if len(calls)==1:raise sqlite3.OperationalError('database is locked')
        return connected(*a,**kw)
    monkeypatch.setattr(host.service,'session_connected',busy_once)
    host.prepare(session)
    assert not service.session(session['id'])['ended_at']
    host.prepare(session)
    current=service.session(session['id'])
    assert current['state']=='connected' and current['id']==session['id'] and current['attempt_id'] is not None
    with service.read() as db:
        assert db.execute('SELECT COUNT(*) FROM application_attempts').fetchone()[0]==1
    assert closed==[session['id']] and len(prepared)==2


def test_slow_transaction_identifies_calling_operation_without_sql(tmp_path, monkeypatch, caplog):
    from types import SimpleNamespace
    _,service,_=fixture_host(tmp_path)
    ticks=iter([0.0,0.5,2.0])
    monkeypatch.setattr(managed,'time',SimpleNamespace(monotonic=lambda:next(ticks)))
    with service.tx() as db:db.execute('SELECT 123456789')
    assert 'operation=test_slow_transaction_identifies_calling_operation_without_sql' in caplog.text
    assert 'elapsed_seconds=2.000' in caplog.text and '123456789' not in caplog.text

