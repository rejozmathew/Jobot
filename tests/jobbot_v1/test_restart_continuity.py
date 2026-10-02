"""Restart acknowledgement can lag the close request; it is not an outcome."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from job_applier import workspace_host as wh
from job_applier.application_runtime import handle
from job_applier.managed_shared import ProtocolError
from tests.jobbot_v1.test_existing_browser import fixture_host
from tests.jobbot_v1.test_local_sessions import connect, own


def recovering_fixture(tmp_path, monkeypatch):
    host, service, session = fixture_host(tmp_path)
    session = connect(service, session, 'application')
    deadline = {'started_at': service.now(), 'limit_seconds': 3600,
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    with service.tx() as db:
        meta = json.loads(session['metadata_json'])
        meta.update(application_deadline=deadline, unrelated='retained',
                    browser_attachment={'browser_id': 'ws://browser/one', 'target_ids': ['application']})
        db.execute('UPDATE application_sessions SET metadata_json=? WHERE id=?', (json.dumps(meta), session['id']))
    state = {'closed': False, 'launches': 0, 'closes': 0, 'threads': []}
    monkeypatch.setattr(wh, 'endpoint_info', lambda _: {'webSocketDebuggerUrl': 'ws://browser/one'})

    async def command(endpoint, method, params=None):
        if method == 'Target.getTargets':
            return {'targetInfos': [{'targetId': 'mail', 'type': 'page'}] + (
                [] if state['closed'] else [{'targetId': 'application', 'type': 'page'}])}
        assert method == 'Target.closeTarget' and params == {'targetId': 'application'}
        state['closes'] += 1
        return {'success': True}  # Receipt precedes actual target destruction.

    class DeferredThread:
        def __init__(self, target, args=(), **kwargs): self.target, self.args = target, args
        def start(self): state['threads'].append(self)

    def start_browser(): state['launches'] += 1
    async def prepare_target(current): return 'replacement', {'synthetic': True}
    monkeypatch.setattr(wh, 'browser_command', command)
    monkeypatch.setattr(wh.threading, 'Thread', DeferredThread)
    monkeypatch.setattr(host, 'start_browser', start_browser)
    monkeypatch.setattr(host, 'prepare_target', prepare_target)
    request = {'instance_id': service.instance_id, 'session_id': session['id'],
               'driver_id': session['driver_id'], 'operation': 'restart', 'parameters': {}}
    return host, service, session, state, request, deadline


def test_delayed_close_remains_preparing_and_resumes_same_attempt(tmp_path, monkeypatch):
    host, service, session, state, request, deadline = recovering_fixture(tmp_path, monkeypatch)
    service.submission_intent(**own(service, session), evidence='Synthetic uncertain dispatch', fixture=True)
    before = service.attempt(session['attempt_id'])
    result = host.dispatch(request)
    assert result['state'] == 'preparing'
    pending = state['threads'].pop()
    pending.target(*pending.args)
    status = handle(service, session['id'], include_context=False)
    assert status['state'] == 'preparing' and status['ended_at'] is None
    assert status['recovery']['phase'] == 'closing'
    assert status['recovery']['last_error'] == 'application_tab_close_unconfirmed'
    assert state['launches'] == 0 and state['closes'] == 1
    # A repeated executor call cannot begin a second restart while cleanup waits.
    assert host.dispatch(request)['state'] == 'preparing'
    assert not state['threads']
    # The expected old tab then disappears. The ordinary prepare retry owns it.
    state['closed'] = True
    host.preparing.add(session['id'])
    host.prepare(service.session(session['id']))
    after = service.session(session['id'])
    assert after['state'] == 'connected' and after['target_id'] == 'replacement'
    assert after['attempt_id'] == session['attempt_id'] and after['driver_id'] == session['driver_id']
    meta = json.loads(after['metadata_json'])
    assert meta['application_deadline'] == deadline and meta['unrelated'] == 'retained'
    assert 'browser_restart' not in meta
    attempt = service.attempt(session['attempt_id'])
    assert attempt['submit_intent_at'] == before['submit_intent_at']
    assert attempt['completed_at'] is None and attempt['outcome'] is None
    assert state['launches'] == 1


@pytest.mark.parametrize('control', ['pause', 'stop'])
def test_operator_control_during_restart_never_reopens_target(tmp_path, monkeypatch, control):
    host, service, session, state, request, _ = recovering_fixture(tmp_path, monkeypatch)
    host.dispatch(request)
    service.control(session['run_id'], command=control)
    state['closed'] = True
    pending = state['threads'].pop()
    pending.target(*pending.args)
    result = service.session(session['id'])
    assert result['state'] == ('paused' if control == 'pause' else 'stopped')
    assert state['launches'] == 0


def test_failed_reopen_retains_recovery_for_next_prepare_slice(tmp_path, monkeypatch):
    host, service, session, state, request, _ = recovering_fixture(tmp_path, monkeypatch)
    state['closed'] = True
    async def unavailable(current): raise OSError('Synthetic endpoint unavailable')
    monkeypatch.setattr(host, 'prepare_target', unavailable)
    host.dispatch(request)
    pending = state['threads'].pop()
    pending.target(*pending.args)
    result = handle(service, session['id'], include_context=False)
    assert result['state'] == 'preparing' and result['ended_at'] is None
    assert result['recovery']['phase'] == 'opening'
    assert result['recovery']['last_error'] == 'OSError'
    assert service.attempt(session['attempt_id'])['outcome'] is None


def test_restart_cannot_change_driver_or_ignore_expired_deadline(tmp_path, monkeypatch):
    host, service, session, state, request, _ = recovering_fixture(tmp_path, monkeypatch)
    with pytest.raises(ProtocolError, match='driver_owned_elsewhere'):
        host.dispatch(dict(request, driver_id='foreign'))
    monkeypatch.setattr(host, 'session_deadline', lambda _: type('Expired', (), {'expired': lambda _: True})())
    with pytest.raises(ProtocolError, match='application_time_limit'): host.dispatch(request)
    assert not state['threads'] and state['launches'] == 0


def test_pending_restart_survives_host_reconstruction(tmp_path, monkeypatch):
    host, service, session, state, request, deadline = recovering_fixture(tmp_path, monkeypatch)
    host.dispatch(request)
    pending = state['threads'].pop()
    pending.target(*pending.args)
    replacement = wh.WorkspaceHost(host.config, host.workspace_id, host.host_id)
    monkeypatch.setattr(replacement, 'start_browser', host.start_browser)
    monkeypatch.setattr(replacement, 'prepare_target', host.prepare_target)
    state['closed'] = True
    replacement.prepare(service.session(session['id']))
    result = service.session(session['id'])
    assert result['state'] == 'connected' and result['attempt_id'] == session['attempt_id']
    assert json.loads(result['metadata_json'])['application_deadline'] == deadline


def test_deadline_during_pending_restart_cleans_up_without_reopening(tmp_path, monkeypatch):
    host, service, session, state, request, _ = recovering_fixture(tmp_path, monkeypatch)
    host.dispatch(request)
    monkeypatch.setattr(host, 'session_deadline', lambda _: type('Expired', (), {'expired': lambda _: True})())
    state['closed'] = True
    pending = state['threads'].pop()
    pending.target(*pending.args)
    result = service.session(session['id'])
    assert result['ended_at'] and 'application_time_limit' in result['reason']
    assert service.attempt(session['attempt_id'])['outcome'] == 'interrupted'
    assert state['launches'] == 0


def test_stop_during_reopen_cleans_up_instead_of_connecting(tmp_path, monkeypatch):
    host, service, session, state, request, _ = recovering_fixture(tmp_path, monkeypatch)
    async def stopped_during_launch(current):
        service.control(session['run_id'], command='stop')
        return 'replacement', {'synthetic': True}
    monkeypatch.setattr(host, 'prepare_target', stopped_during_launch)
    state['closed'] = True
    host.dispatch(request)
    pending = state['threads'].pop()
    pending.target(*pending.args)
    result = service.session(session['id'])
    assert result['state'] == 'stopped' and result['target_id'] is None
