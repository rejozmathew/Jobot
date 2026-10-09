import asyncio
from contextlib import nullcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from job_applier.managed_hermes_worker import select_runtime, confirmation_verified, local_asset_path


def test_requested_low_model_is_explicit():
    assert select_runtime({'reasoning_model':'gpt-5.6-luna','reasoning_provider':'openai-codex','reasoning_effort':'low'}) == ('openai-codex','gpt-5.6-luna','low')


@pytest.mark.parametrize('change',[{'reasoning_model':'gpt-6-astra'},{'reasoning_provider':'openrouter'},{'reasoning_effort':'invalid'}])
def test_worker_cannot_silently_use_an_expensive_fallback(change):
    with pytest.raises(ValueError):
        select_runtime({'reasoning_model':'gpt-5.6-luna','reasoning_provider':'openai-codex','reasoning_effort':'low'}|change)


def test_confirmation_requires_employer_origin_and_confirmation_text():
    job='https://job-boards.greenhouse.io/tebra/jobs/4713311005'
    assert confirmation_verified(job,job+'/confirmation','Thank you for applying!')
    assert not confirmation_verified(job,job,'All fields filled')
    assert not confirmation_verified(job,'https://evil.example/confirmation','Thank you for applying!')
    assert not confirmation_verified(job,job.replace('4713311005','999')+'/confirmation','Thank you for applying!')


def test_asset_requires_exact_local_file_hash(tmp_path):
    import hashlib
    p=tmp_path/'resume.pdf';p.write_bytes(b'synthetic resume')
    asset={'storage_ref':p.as_uri(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    assert local_asset_path(asset)==p
    with pytest.raises(ValueError):local_asset_path(asset|{'sha256':'0'*64})
    with pytest.raises(ValueError):local_asset_path(asset|{'storage_ref':'https://evil.example/resume.pdf'})


def test_start_accept_next_shape(monkeypatch):
    from job_applier.managed_hermes_worker import ApplicationTool
    from job_applier.managed_shared import ProtocolError

    async def _run():

        class DummyController:
            def __init__(self):
                self.handled = []
            def handle(self, req, session_id=None):
                self.handled.append(req)
                op = req['operation']
                if op == 'accept':
                    return json.dumps({'id': 'run-1', 'state': 'accepted'})
                elif op == 'next':
                    return json.dumps({
                        'id': 42,
                        'fence': 1,
                        'settings_json': json.dumps({'submission_mode': 'submit'}),
                        'context': {
                            'job': {'id': 101, 'url': 'https://example.test/jobs/1'},
                            'attempt': {'profile_json': json.dumps({'name': 'Jane Doe'})},
                            'documents': {'ready': True, 'assets': []},
                        }
                    })
                return json.dumps({})

        ctrl = DummyController()
        cfg = {'worker_id': 'worker-1', 'cdp_url': 'http://127.0.0.1:9222'}
        app = ApplicationTool(ctrl, 'session-1', 'run-1', cfg)

        # Strictly offline mocks
        monkeypatch.setattr(app, 'action', lambda name, writes=True: nullcontext())
        monkeypatch.setattr(app, 'call', lambda op, **kw: {})
        monkeypatch.setattr(app, 'event', lambda kind, payload: {})

        import urllib.request
        class DummyResp:
            def read(self): return b'{"id": "tab-1"}'
            def __enter__(self): return self
            def __exit__(self, *a): pass
        monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: DummyResp())

        class DummyPage:
            async def goto(self, url): pass
        class DummyBrowser:
            async def get_current_page(self): return DummyPage()
            async def close(self): pass
        async def dummy_connect(): return DummyBrowser()
        monkeypatch.setattr(app, 'connect', dummy_connect)
        async def no_sleep(seconds): pass
        monkeypatch.setattr(asyncio, 'sleep', no_sleep)

        shape = await app.start()
        assert shape['attempt_id'] == 42
        assert shape['job']['id'] == 101
        assert shape['profile']['name'] == 'Jane Doe'
        assert shape['documents']['ready'] is True
        assert shape['settings']['submission_mode'] == 'submit'
        assert 'instruction' in shape

        # Already started
        second = await app.start()
        assert second == {'already_started': True, 'attempt_id': 42}

        # No remaining jobs
        app_empty = ApplicationTool(ctrl, 'session-2', 'run-2', cfg)
        monkeypatch.setattr(ctrl, 'handle', lambda req, session_id=None: json.dumps(None if req['operation'] == 'next' else {}))
        empty_shape = await app_empty.start()
        assert empty_shape == {'finished': True, 'no_remaining_jobs': True}
        assert app_empty.finished is True

        # Blocker in package
        app_blocked = ApplicationTool(ctrl, 'session-3', 'run-3', cfg)
        blocked_next = {
            'id': 43, 'fence': 1, 'settings_json': '{}',
            'context': {'blocker': 'required_document_missing', 'job': {}, 'attempt': {}, 'documents': {}}
        }
        monkeypatch.setattr(ctrl, 'handle', lambda req, session_id=None: json.dumps(blocked_next if req['operation'] == 'next' else {}))
        with pytest.raises(ProtocolError, match='required_document_missing'):
            await app_blocked.start()

    asyncio.run(_run())


def test_report_upload_statuses(tmp_path):
    from job_applier.managed import Service
    from job_applier.managed_shared import ProtocolError

    s = Service.create(tmp_path / 'upload_test.db', instance_id='inst-upload')
    s.identity(identity_id='cand-1', person_key='p1', email='cand@example.test', profile={'facts': {}})
    asset = s.register_asset(
        identity_id='cand-1',
        kind='resume',
        version='v1',
        storage_ref='storage://cand-1/resume-v1.pdf',
        sha256='a' * 64,
        provenance={'source': 'manual'}
    )
    job = s.intake(url='https://jobs.example.test/1', source_id='j1')
    s.eligibility(job['id'], 'ready', reason='approved')
    s.select_asset(asset_id=asset['id'], job_id=job['id'])
    run = s.request_run(request_id='r1', job_ids=[job['id']], identity_id='cand-1', browser_profile='profile-1')
    s.accept_run(run['id'], worker_id='w1', session_id='s1', capabilities={
        'protocol': 1, 'skill_version': 'v1', 'browser_profile': 'profile-1',
        'provider': 'fixture', 'model': 'fixture', 'telemetry': True
    })
    attempt = s.claim(run['id'], worker_id='w1')
    att_id, fence = attempt['id'], attempt['fence']

    # 1. Invalid upload status rejected
    with pytest.raises(ProtocolError) as exc:
        s.report_upload(attempt_id=att_id, worker_id='w1', fence=fence, asset_id=asset['id'],
                        status='upload_success', evidence='done')
    assert exc.value.code == 'invalid_upload_event'

    # 2. Confirmed without attempted rejected
    with pytest.raises(ProtocolError) as exc:
        s.report_upload(attempt_id=att_id, worker_id='w1', fence=fence, asset_id=asset['id'],
                        status='upload_confirmed', evidence='confirmed')
    assert exc.value.code == 'upload_not_attempted'

    # 3. upload_attempted succeeds
    att = s.report_upload(attempt_id=att_id, worker_id='w1', fence=fence, asset_id=asset['id'],
                          status='upload_attempted', evidence='attempting upload')
    assert att['status'] == 'upload_attempted'

    # 4. upload_confirmed succeeds after upload_attempted
    conf = s.report_upload(attempt_id=att_id, worker_id='w1', fence=fence, asset_id=asset['id'],
                           status='upload_confirmed', evidence='confirmed on page')
    assert conf['status'] == 'upload_confirmed'

    # 5. confirmed upload is immutable
    with pytest.raises(ProtocolError) as exc:
        s.report_upload(attempt_id=att_id, worker_id='w1', fence=fence, asset_id=asset['id'],
                        status='upload_attempted', evidence='retry')
    assert exc.value.code == 'confirmed_upload_immutable'


def test_submission_permissions_and_duplicate_click_guard(monkeypatch):
    from job_applier.managed_hermes_worker import ApplicationTool

    async def _run():
        class DummyClient:
            def __init__(self):
                self.calls = []
            def call(self, op, **kw):
                self.calls.append((op, kw))
                return {'control': 'running', 'quiescent': True}

        class DummyAdapter:
            def __init__(self, client):
                self.client = client

        class DummyController:
            def __init__(self, client):
                self.adapters = {'sid-1': DummyAdapter(client)}
            def handle(self, req, session_id=None):
                return json.dumps({})

        client = DummyClient()
        ctrl = DummyController(client)
        cfg = {'worker_id': 'w1', 'cdp_url': 'http://127.0.0.1:9222'}
        app = ApplicationTool(ctrl, 'sid-1', 'run-1', cfg)
        app.context = {'attempt_id': 1, 'worker_id': 'w1', 'fence': 1}
        app.package = {'job': {'url': 'https://careers.example.test/jobs/1'}}

        evaluated = []
        class DummyPage:
            async def evaluate(self, script, args=None):
                if script == 'location.href':
                    return 'https://careers.example.test/jobs/1'
                if 'jobbot:simplify:observe' in script:
                    return {'status':'missing','controls':{},'writer_safe':True}
                evaluated.append((script, args))
                return {'url': 'https://careers.example.test/jobs/1', 'items': [
                    {'ref': 'sub-1', 'type': 'submit', 'tag': 'BUTTON', 'label': 'Submit', 'required': False}
                ], 'errors': [], 'text': 'form text'}
            async def evaluate_function(self,script,args=None):
                return {'inventory':[],'native':{'submit':{'ref':'sub-1','enabled':True}},'blocking_errors':[]}

        class DummyBrowser:
            async def get_current_page(self): return DummyPage()
            async def close(self): pass
        async def dummy_connect(): return DummyBrowser()
        monkeypatch.setattr(app, 'connect', dummy_connect)
        monkeypatch.setattr(app, 'action', lambda name, writes=True: nullcontext())
        monkeypatch.setattr(app, 'event', lambda kind, payload: {})

        # 1. Submission permissions: rejected when submission_mode != 'submit'
        app.settings = {'submission_mode': 'fill_only'}
        app.resume_uploaded = True
        with pytest.raises(ValueError, match='submission_not_authorized'):
            await app.operate({'operation': 'submit'})
        assert not any(c[0] == 'submission_intent' for c in client.calls)

        # 2. A local flag is not authority over a resume uploaded by Simplify.
        # Observe the form and current submission policy, not the historical flag.
        app.settings = {'submission_mode': 'submit'}
        app.resume_uploaded = False
        async def confirmed(page):
            app.finished=True
            return {'outcome':'fixture_confirmation'}
        monkeypatch.setattr(app,'confirm',confirmed)
        result=await app.operate({'operation':'submit'})
        assert result=={'outcome':'fixture_confirmation'}
        assert sum(c[0]=='submission_intent' for c in client.calls)==1

        # 3. A new explicit submit may continue the current form after verification.
        # Click history alone must not silently turn it into a confirmation-only call.
        app.resume_uploaded = True
        app.submit_clicked = True
        app.finished=False
        confirmations=0
        async def pending_then_confirmed(page):
            nonlocal confirmations
            confirmations+=1
            if confirmations==1:return {'outcome':'pending_confirmation'}
            return await confirmed(page)
        monkeypatch.setattr(app,'confirm',pending_then_confirmed)
        result = await app.operate({'operation': 'submit'})
        assert result == {'outcome':'fixture_confirmation'}
        assert sum(c[0]=='submission_intent' for c in client.calls)==2
        assert sum(bool(e[1] and e[1].get('operation')=='submit') for e in evaluated)==2

    asyncio.run(_run())


def test_hermes_runtime_plugin_context_and_agent_integration(tmp_path):
    hermes_root = Path(os.environ.get('JOBBOT_TEST_HERMES_ROOT',
        str(Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'hermes/hermes-agent')))
    if not hermes_root.is_dir():
        pytest.skip('Hermes source installation not found')
    # PM-managed Hermes upgrades can leave the old in-tree venv behind. Resolve
    # the committed environment before isolating the integration child's home.
    if (hermes_root / 'pm/environments.py').is_file():
        probe = subprocess.run([sys.executable, '-S', '-c',
            'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); '
            'from pm.environments import project_python; print(project_python(Path(sys.argv[1])))',
            str(hermes_root)], capture_output=True, text=True, timeout=10, check=True)
        hermes_python = Path(probe.stdout.strip())
    else:
        hermes_python = hermes_root / ('venv/Scripts/python.exe' if os.name == 'nt' else 'venv/bin/python')
    if not hermes_python.exists():
        pytest.skip('Hermes interpreter not found')

    script = tmp_path / 'verify_hermes_integration.py'
    script.write_text("""
import sys, os, json
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
from hermes_cli.plugins import PluginContext, PluginManifest, get_plugin_manager
from tools.registry import registry
from run_agent import AIAgent
from model_tools import get_tool_definitions
from job_applier.managed_hermes_worker import SCHEMA

manager = get_plugin_manager()
manifest = PluginManifest(name='jobbot-runtime', provides_tools=['application'])
ctx = PluginContext(manifest, manager)

calls = []
def mock_handle(args, **kwargs):
    calls.append(args)
    return json.dumps({'status': 'mock_ok', 'op': args.get('operation')})

handle = ctx.register_tool(name='application', toolset='jobbot_application',
                           schema=SCHEMA, handler=mock_handle, check_fn=lambda: True)
assert handle is not None, 'register_tool returned None'

agent = AIAgent(
    model='gpt-5.6-luna', provider='openai-codex',
    base_url='https://chatgpt.com/backend-api/codex', api_key='dummy-key',
    enabled_toolsets=['jobbot_application'], quiet_mode=True,
    skip_context_files=True, skip_memory=True, skip_background_review=True,
    save_trajectories=False
)
agent.tools = get_tool_definitions(enabled_toolsets=['jobbot_application'], quiet_mode=True, skip_tool_search_assembly=True)
agent.valid_tool_names = {t['function']['name'] for t in agent.tools}

assert 'application' in agent.valid_tool_names, 'application not in valid_tool_names'
assert any(t['function']['name'] == 'application' for t in agent.tools), 'application not in agent.tools'

# Invoke tool through agent runtime helper
res = agent._invoke_tool('application', {'operation': 'status'}, 'test-task')
parsed = json.loads(res)
assert parsed.get('status') == 'mock_ok'
assert parsed.get('op') == 'status'
assert len(calls) == 1

# Cleanup via dispose
handle.dispose()
assert registry.get_entry('application') is None, 'application still in registry after dispose'
print('SUCCESS_HERMES_INTEGRATION')
""", encoding='utf-8')

    child_env = dict(os.environ, HERMES_HOME=str(tmp_path / 'hermes-home'), HERMES_DISABLE_LAZY_INSTALLS='1')
    res = subprocess.run([str(hermes_python), str(script), str(hermes_root), str(Path(__file__).resolve().parents[2])],
                         # Installed Hermes discovers its optional tool modules
                         # before constructing the synthetic agent. Cold imports
                         # can exceed 30s on Windows; allow startup to complete
                         # without changing any application execution deadline.
                         env=child_env, capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, f"Hermes integration failed:\\nSTDOUT: {res.stdout}\\nSTDERR: {res.stderr}"
    assert 'SUCCESS_HERMES_INTEGRATION' in res.stdout
