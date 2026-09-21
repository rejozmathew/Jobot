"""Application budgets are enforced by supervision, with synthetic clocks/tasks."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from test_dispatch_queue import runtime_fixture, enqueue


def test_limit_defaults_to_30_and_can_be_saved_as_60_or_off(tmp_path):
    s, *_ = runtime_fixture(tmp_path)
    assert s.settings_view()['values']['application_time_limit_minutes'] == 30
    for minutes in (60, 0, 30):
        s.configure({'application_time_limit_minutes': minutes}, expected_version=s.settings_view()['version'])
        assert s.settings_view()['values']['application_time_limit_minutes'] == minutes
    for invalid in (-1, True, float('nan'), '60', 1.5):
        with pytest.raises(Exception):
            s.configure({'application_time_limit_minutes': invalid}, expected_version=s.settings_view()['version'])


def test_dispatch_freezes_deadline_and_next_dispatch_reads_changed_setting(tmp_path):
    from job_applier.queue_runtime import dispatch_one
    s, asset, jobs, _, cfg = runtime_fixture(tmp_path)
    enqueue(s, asset, jobs[:2])
    snapshots = []
    def launch(command, **kwargs):
        frozen = json.loads(Path(kwargs['env']['JOBBOT_CONFIG']).read_text())
        snapshots.append(frozen['application_deadline'])
        s.configure({'application_time_limit_minutes': 0}, expected_version=s.settings_view()['version'])
        return type('Done', (), {'pid': 0, 'returncode': 0, 'poll': lambda self: 0})()
    dispatch_one(cfg, s, launcher=launch)
    dispatch_one(cfg, s, launcher=launch)
    first, second = snapshots
    assert first['limit_seconds'] == 1800
    assert (datetime.fromisoformat(first['expires_at'])-datetime.fromisoformat(first['started_at'])).total_seconds() == 1800
    assert second['expires_at'] is None and second['limit_seconds'] is None
    assert 'application_deadline' not in cfg


def test_clock_survives_restart_and_backward_wall_clock_without_reset():
    from job_applier.application_deadline import Deadline, freeze
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frozen = freeze({}, {'application_time_limit_minutes': 30}, start.isoformat())['application_deadline']
    wall = [start + timedelta(minutes=29)]
    ticks = [50.0]
    clock = Deadline(frozen, now=lambda: wall[0], monotonic=lambda: ticks[0])
    assert not clock.expired()
    wall[0] -= timedelta(hours=1)
    ticks[0] += 60
    assert clock.expired()
    restarted = Deadline(frozen, now=lambda: start+timedelta(minutes=31))
    assert restarted.expired()
    assert freeze({'application_deadline': frozen}, {'application_time_limit_minutes': 60}, wall[0].isoformat())['application_deadline'] == frozen


@pytest.mark.parametrize('status', ['working', 'waiting'])
def test_expired_native_turn_is_interrupted_without_another_model_tool_call(tmp_path, status):
    from job_applier.hermes_desktop import run_session
    receipt = tmp_path/'desktop-session.json'
    receipt.write_text(json.dumps({'session_id':'owned','stored_session_id':'stored','state':'submitted'}))
    calls=[]; active=[True]
    class RPC:
        def call(self, method, params):
            calls.append((method, params))
            if method == 'session.active_list':
                return {'sessions':[{'id':'owned','session_key':'stored','status':status if active[0] else 'idle'},
                                    {'id':'unrelated','status':'working'}]}
            assert method == 'session.interrupt' and params == {'session_id':'owned'}
            active[0]=False
            return {'status':'interrupted'}
    cfg={'hermes_desktop':{},'application_deadline':{'limit_seconds':1800,
         'started_at':'2020-01-01T00:00:00+00:00','expires_at':'2020-01-01T00:30:00+00:00'}}
    def sleep(_):
        assert not active[0], 'Expired task waited without interrupting the model'
    result=run_session(RPC(), 'Do not replay', cfg, receipt, sleep=sleep)
    assert result['stop_reason']=='application_time_limit'
    assert result['state']=='finished'
    assert [m for m,p in calls].count('session.interrupt')==1


def test_expired_dispatch_does_not_create_or_submit_a_new_native_task(tmp_path):
    from job_applier.hermes_desktop import run_session
    class RPC:
        def call(self, method, params):raise AssertionError('Expired dispatch launched '+method)
    result=run_session(RPC(), 'Expired', {'hermes_desktop':{},'application_deadline':{
        'started_at':'2020-01-01T00:00:00+00:00','expires_at':'2020-01-01T00:30:00+00:00','limit_seconds':1800}},
        tmp_path/'receipt.json')
    assert result['stop_reason']=='application_time_limit'


def test_settings_ui_round_trips_duration_and_off():
    from test_dispatch_queue_ui import dashboard_check
    dashboard_check(r'''
w.drawSettings({version:1,values:{application_time_limit_minutes:30},supported:{}});
const mode=doc.getElementById('settings-time-limit-enabled'), minutes=doc.getElementById('settings-time-limit-minutes');
assert(mode.checked && minutes.value==='30','Default limit not shown');
minutes.value='60';
let payload;
w.fetch=async(url,options)=>{payload=JSON.parse(options.body);return {ok:true,json:async()=>({})};};
w.noRefresh();
await doc.getElementById('settings-form').onsubmit({preventDefault(){}});
assert(payload.changes.application_time_limit_minutes===60,'60 minutes not saved');
mode.checked=false;
await doc.getElementById('settings-form').onsubmit({preventDefault(){}});
assert(payload.changes.application_time_limit_minutes===0,'Off not saved');
w.drawSettings({version:2,values:{application_time_limit_minutes:0},supported:{}});
assert(!mode.checked && minutes.disabled,'Off not restored');
''')


@pytest.mark.parametrize('pending_submit', [False, True])
def test_restarted_supervisor_cancels_only_its_task_and_waits_for_browser_cleanup(tmp_path, monkeypatch, pending_submit):
    from contextlib import contextmanager
    from job_applier import hermes_desktop,application_deadline,queue_runtime
    from test_local_sessions import reserve,connect
    s,asset,jobs,_,cfg=runtime_fixture(tmp_path)
    enqueue(s,asset,jobs[:2]);item=s.queue_take()
    session=connect(s,reserve(s,asset,jobs,driver='stored',request='queue:'+item['id']))
    if pending_submit:
        with s.tx() as db:db.execute('UPDATE application_attempts SET submit_intent_at=? WHERE id=?',(s.now(),session['attempt_id']))
    root=Path(cfg['spool_dir'])/'dispatch'/item['id'];root.mkdir(parents=True)
    config=application_deadline.freeze({'hermes_desktop':{}},{'application_time_limit_minutes':30},'2020-01-01T00:00:00+00:00')
    (root/'runtime.json').write_text(json.dumps(config))
    (root/'desktop-session.json').write_text(json.dumps({'session_id':'owned','stored_session_id':'stored','state':'submitted'}))
    s.desktop_dispatch_spool=cfg['spool_dir'];calls=[];active=[True]
    class RPC:
        def call(self,method,params):
            if method=='session.active_list':return {'sessions':[{'id':'owned','session_key':'stored','status':'waiting' if active[0] else 'idle'},{'id':'other','status':'working'}]}
            assert method=='session.interrupt' and params['session_id']=='owned'
            calls.append(params);active[0]=False;return {'status':'interrupted'}
    @contextmanager
    def connection(_):yield RPC(),None
    monkeypatch.setattr(hermes_desktop,'connection',connection)
    monkeypatch.setattr(application_deadline,'stop_process',lambda identity:True)
    assert queue_runtime.recover_dispatch(s) is False
    assert len(calls)==1 and s.queue_take() is None
    assert s.session(session['id'])['reason']==application_deadline.REASON
    s.session_stopped(session['id'],reason=application_deadline.REASON,browser_stopped=True)
    assert queue_runtime.recover_dispatch(s) is True
    expected='submission_unknown' if pending_submit else 'interrupted'
    assert s.attempt(session['attempt_id'])['outcome']==expected
    assert s.queue_take()['job_id']==jobs[1]['id']


def test_expiry_cleanup_does_not_wait_for_browser_action_lock(tmp_path,monkeypatch):
    import threading
    from test_apply_target_handoff import connected
    from job_applier.workspace_host import WorkspaceHost
    from job_applier.application_deadline import REASON
    s,session,_,workspace=connected(tmp_path)
    host=object.__new__(WorkspaceHost);host.service=s;host.workspace_id='workspace';host.workspace=workspace
    host.config={};host.preparing=set();host.exit=threading.Event();host.busy=threading.Lock();host.busy.acquire()
    calls=[]
    monkeypatch.setattr('job_applier.hermes_desktop.cancel_driver',lambda cfg,driver,native_id=None:calls.append(driver) or True)
    def stop(current,reason):s.session_stopped(current['id'],reason=reason,browser_stopped=True)
    host.stop_session=stop
    host.expire_session(session)
    assert host.busy.locked() and host.exit.is_set()
    assert s.session(session['id'])['reason']==REASON and calls==['driver']


def test_native_backend_unavailable_retains_pending_cancellation(tmp_path,monkeypatch):
    from contextlib import contextmanager
    from job_applier import hermes_desktop
    receipt=tmp_path/'receipt.json';receipt.write_text(json.dumps({'session_id':'owned','state':'submitted'}))
    @contextmanager
    def unavailable(_):
        raise OSError('temporarily unavailable')
        yield
    monkeypatch.setattr(hermes_desktop,'connection',unavailable)
    assert hermes_desktop.cancel_dispatch({'hermes_desktop':{}},receipt) is False


def test_manual_start_freezes_off_and_repeat_start_keeps_original_budget(tmp_path,monkeypatch):
    from job_applier.application_runtime import start
    s,asset,jobs,_,cfg=runtime_fixture(tmp_path)
    s.configure({'application_time_limit_minutes':0},expected_version=s.settings_view()['version'])
    monkeypatch.setattr('job_applier.workspace_host.ensure_host',lambda *args:None)
    first=start(cfg,job_id=jobs[0]['id'],driver_id='test-driver',request_id='one-request',wait_seconds=0)
    assert first['application_deadline']['expires_at'] is None
    s.configure({'application_time_limit_minutes':60},expected_version=s.settings_view()['version'])
    again=start(cfg,job_id=jobs[0]['id'],driver_id='test-driver',request_id='one-request',wait_seconds=0)
    assert again['application_deadline']==first['application_deadline']


def test_native_timeout_before_browser_allocation_keeps_timeout_reason(tmp_path):
    from job_applier.queue_runtime import settle
    s,asset,jobs,_,cfg=runtime_fixture(tmp_path)
    enqueue(s,asset,jobs[:1]);item=s.queue_take();s.desktop_dispatch_spool=cfg['spool_dir']
    root=Path(cfg['spool_dir'])/'dispatch'/item['id'];root.mkdir(parents=True)
    (root/'desktop-session.json').write_text(json.dumps({'state':'finished','stop_reason':'application_time_limit'}))
    assert settle(s,item)
    item=s.queue_status()['items'][0]
    assert item['outcome']=='interrupted' and item['detail'].startswith('application_time_limit:')


@pytest.mark.parametrize('previous_driver',[None,'previous-driver'])
def test_manual_native_identity_survives_context_compression(tmp_path,monkeypatch,previous_driver):
    from contextlib import contextmanager
    from test_apply_target_handoff import connected
    from job_applier import hermes_desktop
    s,session,_,_=connected(tmp_path)
    if previous_driver:
        metadata=json.loads(session['metadata_json'])
        metadata.update(native_session_id='previous-native-id',native_driver_id=previous_driver)
        with s.tx() as db:db.execute('UPDATE application_sessions SET metadata_json=? WHERE id=?',
            (json.dumps(metadata),session['id']))
        session=s.session(session['id'])
        assert hermes_desktop.native_driver_id(session) is None
    key=['driver'];active=[True];calls=[]
    class RPC:
        def call(self,method,params):
            if method=='session.active_list':
                return {'sessions':[{'id':'stable-native-id','session_key':key[0],
                    'status':'working' if active[0] else 'idle'},{'id':'other','status':'working'}]}
            assert method=='session.interrupt' and params=={'session_id':'stable-native-id'}
            calls.append(params);active[0]=False;return {'status':'interrupted'}
    @contextmanager
    def connection(_):yield RPC(),None
    monkeypatch.setattr(hermes_desktop,'connection',connection)
    cfg={'hermes_desktop':{}}
    hermes_desktop.remember_driver(cfg,s,session)
    metadata=json.loads(s.session(session['id'])['metadata_json'])
    assert metadata['native_session_id']=='stable-native-id'
    assert hermes_desktop.native_driver_id(s.session(session['id']))=='stable-native-id'
    key[0]='compressed-session-key'
    assert hermes_desktop.cancel_driver(cfg,'driver',metadata['native_session_id'])
    assert len(calls)==1 and not active[0]
