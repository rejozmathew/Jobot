"""Desktop queue transport contracts; synthetic sessions and local sockets only."""
import json
import sys
from contextlib import contextmanager

import pytest

from test_dispatch_queue import runtime_fixture, enqueue


def test_brief_supplies_exact_selected_email_not_profile_guess(tmp_path):
    from job_applier.application_brief import application_brief
    s, asset, jobs, _, cfg = runtime_fixture(tmp_path)
    email = s.candidate('candidate')['email']
    item = enqueue(s, asset, jobs)['items'][0]
    brief = application_brief(cfg, s, item)
    assert '"application_email": ' + json.dumps(email) in brief
    assert 'copy the observed address exactly' in brief


def test_desktop_command_uses_native_backend_when_selected(tmp_path):
    from job_applier.queue_runtime import executor_command
    prompt = tmp_path/'one job.md'
    command = executor_command({'hermes_desktop': {}}, prompt)
    assert command == [sys.executable, '-m', 'job_applier.hermes_desktop', str(prompt)]


def test_native_session_is_visible_preserves_id_and_waits_through_user_input(tmp_path):
    from job_applier.hermes_desktop import run_session
    calls = []
    states = iter(['working', 'waiting', 'working', 'idle'])
    class RPC:
        def call(self, method, params):
            calls.append((method, params))
            if method == 'session.create':
                return {'session_id': 'live', 'stored_session_id': 'stored'}
            if method == 'prompt.submit':
                return {'status': 'streaming'}
            if method == 'session.active_list':
                return {'sessions': [{'id': 'live', 'session_key': 'stored', 'status': next(states)}]}
            return {}
    receipt = tmp_path/'receipt.json'
    run_session(RPC(), 'Application task', {'hermes_desktop': {}}, receipt, sleep=lambda _: None)
    create = calls[0][1]
    assert create['source'] == 'desktop' and create['hidden'] is False
    assert create['close_on_disconnect'] is False
    prompt = next(p for m,p in calls if m == 'prompt.submit')['text']
    assert 'stored' in prompt and '--driver-id' in prompt
    assert [m for m,p in calls].count('prompt.submit') == 1
    assert [m for m,p in calls].count('session.active_list') == 4
    assert json.loads(receipt.read_text())['state'] == 'finished'


def test_existing_receipt_monitors_without_replaying_prompt(tmp_path):
    from job_applier.hermes_desktop import run_session
    from job_applier.queue_runtime import private_write
    receipt = tmp_path/'receipt.json'
    private_write(receipt, json.dumps({'session_id':'live','stored_session_id':'stored','state':'submitted'}))
    class RPC:
        def call(self, method, params):
            assert method == 'session.active_list'
            return {'sessions':[{'id':'live','status':'idle'}]}
    run_session(RPC(), 'Do not replay', {'hermes_desktop':{}}, receipt, sleep=lambda _:None)


def test_rpc_consumes_notifications_and_preserves_multiline_prompt():
    from job_applier.hermes_desktop import RPC
    class Socket:
        def send(self, value):
            self.sent = json.loads(value)
        def recv(self, timeout=None):
            return '\n'.join([json.dumps({'method':'gateway.ready','params':{}}),
                json.dumps({'jsonrpc':'2.0','id':self.sent['id'],'result':{'status':'streaming'}})])
    socket = Socket()
    assert RPC(socket).call('prompt.submit', {'text':'one\ntwo'}) == {'status':'streaming'}
    assert socket.sent['params']['text'] == 'one\ntwo'


def test_orphaned_monitor_keeps_native_turn_alive(tmp_path, monkeypatch):
    from job_applier import hermes_desktop as desktop
    s, asset, jobs, _, cfg = runtime_fixture(tmp_path)
    item=enqueue(s,asset,jobs)['items'][0]
    s.desktop_dispatch_spool=cfg['spool_dir']
    root=tmp_path/'private-spool'/'dispatch'/item['id']
    root.mkdir(parents=True)
    (root/'desktop-session.json').write_text(json.dumps({'state':'submitted','session_id':'live'}))
    (root/'runtime.json').write_text(json.dumps({'hermes_desktop':{}}))
    class RPC:
        def call(self, method, params):
            return {'sessions':[{'id':'live','status':'working'}]}
    @contextmanager
    def connection(_):yield RPC(),None
    monkeypatch.setattr(desktop,'connection',connection)
    assert desktop.orphan_is_active(s,item) is True
    @contextmanager
    def unavailable(_):
        raise OSError('temporary connection problem')
        yield
    monkeypatch.setattr(desktop,'connection',unavailable)
    assert desktop.orphan_is_active(s,item) is True


def test_backend_discovery_filters_profile_and_uses_owned_listening_socket(tmp_path,monkeypatch):
    from job_applier import hermes_desktop as desktop
    if sys.platform=='win32':pytest.skip('Linux proc discovery; exercised on the Ubuntu VM')
    proc=tmp_path/'proc'; proc.mkdir()
    home=tmp_path/'hermes-home'
    for pid,profile in [('101',tmp_path/'other'),('102',home)]:
        directory=proc/pid; directory.mkdir()
        (directory/'cmdline').write_bytes(b'python\0-m\0hermes_cli.main\0serve\0')
        (directory/'environ').write_bytes(('HERMES_HOME='+str(profile)+'\0').encode())
        (directory/'fd').mkdir()
        (directory/'fd'/'9').symlink_to('socket:[1234]')
    (proc/'net').mkdir()
    (proc/'net'/'tcp').write_text('header\n0: 0100007F:938F 00000000:0000 0A 0 0 0 0 0 1234\n')
    monkeypatch.setattr(desktop,'process_identity',lambda pid:{'pid':pid})
    assert desktop.discover_backend({'profile_home':str(home)},proc=proc)==('http://127.0.0.1:37775',{'pid':102})


def test_rpc_reports_server_error_without_echoing_private_payload():
    from job_applier.hermes_desktop import RPC
    class Socket:
        def send(self, value):self.sent=json.loads(value)
        def recv(self, timeout=None):
            return json.dumps({'id':self.sent['id'],'error':{'code':4090,'message':'private-prompt-secret'}})
    with pytest.raises(ValueError,match='4090') as failure:
        RPC(Socket()).call('prompt.submit',{'text':'private-prompt-secret'})
    assert 'private-prompt-secret' not in str(failure.value)
