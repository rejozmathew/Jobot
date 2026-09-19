"""Synthetic model catalog and new-application selection contracts."""
import json
from contextlib import contextmanager
from pathlib import Path

from job_applier.managed import Service
from test_dispatch_queue import runtime_fixture, enqueue


def test_catalog_uses_selected_desktop_profile_and_only_returns_public_fields(tmp_path, monkeypatch):
    from job_applier import hermes_desktop
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    cfg['hermes_desktop'] = {'profile': 'application'}
    s.executor_config = cfg
    calls = []
    class RPC:
        def call(self, method, params):
            calls.append((method, params))
            return {'provider': 'custom', 'model': 'local/model', 'providers': [
                {'slug': 'custom', 'name': 'Custom endpoint', 'base_url': 'http://192.168.1.2:1234/v1',
                 'api_key': 'never-return-this', 'models': ['local/model'],
                 'capabilities': {'local/model': {'reasoning': False}}},
                {'slug': 'openai-codex', 'name': 'Subscription', 'models': ['cloud-model']} ]}
    @contextmanager
    def connection(options):
        assert options == cfg['hermes_desktop']
        yield RPC(), None
    monkeypatch.setattr(hermes_desktop, 'connection', connection)
    result = s.model_catalog(refresh=True)
    assert calls == [('model.options', {'profile': 'application', 'explicit_only': True, 'refresh': True})]
    assert result['executor'] == 'hermes_desktop'
    assert result['providers'][0]['name'] == 'Local'
    assert result['providers'][1]['name'] == 'ChatGPT'
    assert result['providers'][0]['capabilities']['local/model']['reasoning'] is False
    assert 'never-return-this' not in json.dumps(result)
    assert '192.168.1.2' not in json.dumps(result)


def test_catalog_failure_keeps_saved_selection_and_sanitizes_error(tmp_path, monkeypatch):
    from job_applier import hermes_desktop
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    cfg['hermes_desktop'] = {}
    s.executor_config = cfg
    @contextmanager
    def unavailable(_):
        raise OSError('private endpoint credentials')
        yield
    monkeypatch.setattr(hermes_desktop, 'connection', unavailable)
    before = s.settings_view()
    result = s.model_catalog()
    assert result['status'] == 'unavailable'
    assert 'private endpoint credentials' not in json.dumps(result)
    assert s.settings_view() == before


def test_dispatch_reads_saved_model_at_launch_and_snapshots_it(tmp_path):
    from job_applier.queue_runtime import dispatch_one
    s, asset, jobs, _, cfg = runtime_fixture(tmp_path)
    cfg['hermes_desktop'] = {}
    enqueue(s, asset, [jobs[0]])
    other = Service(s.db_path, instance_id=s.instance_id)
    other.configure({'application_model_override': True, 'reasoning_provider': 'custom',
                     'reasoning_model': 'local/model', 'reasoning_effort': 'high'},
                    expected_version=other.settings_view()['version'])
    def launcher(command, **kwargs):
        snapshot = json.loads(Path(command[-1]).with_name('runtime.json').read_text())
        assert snapshot['application_provider'] == 'custom'
        assert snapshot['application_model'] == 'local/model'
        assert snapshot['application_effort'] == 'high'
        other.configure({'reasoning_model': 'next/model'}, expected_version=other.settings_view()['version'])
        assert json.loads(Path(command[-1]).with_name('runtime.json').read_text()) == snapshot
        return type('Done', (), {'pid': 0, 'returncode': 0, 'poll': lambda self: 0})()
    assert dispatch_one(cfg, s, launcher=launcher)['state'] == 'finished'
    assert 'application_model' not in cfg


def test_desktop_creation_receives_selection_without_changing_global_profile(tmp_path):
    from job_applier.hermes_desktop import run_session
    calls = []
    class RPC:
        def call(self, method, params):
            calls.append((method, params))
            if method == 'session.create':return {'session_id': 'live', 'stored_session_id': 'stored'}
            if method == 'session.active_list':return {'sessions': []}
            return {}
    run_session(RPC(), 'Synthetic task', {'hermes_desktop': {}, 'application_model': 'local/model',
                'application_provider': 'custom', 'application_effort': 'high'}, tmp_path/'receipt.json')
    create = calls[0][1]
    assert (create['provider'], create['model'], create['reasoning_effort']) == ('custom', 'local/model', 'high')
    assert not any(method == 'config.set' for method, _ in calls)


def test_old_reasoning_settings_do_not_change_executor_until_opted_in(tmp_path):
    from job_applier.model_settings import application_selection
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    s.configure({'reasoning_provider': 'openai-codex', 'reasoning_model': 'old-model'},
                expected_version=s.settings_view()['version'])
    assert application_selection(cfg, s.settings_view()['values']) == cfg


def test_cli_selection_uses_flags_and_leaves_custom_command_unchanged(tmp_path):
    from job_applier.queue_runtime import executor_command
    selected = {'application_provider': 'custom:local', 'application_model': 'local/model',
                'application_effort': 'medium'}
    expected = ['--provider', 'custom:local', '--model', 'local/model', '--reasoning', 'medium']
    assert executor_command(selected, tmp_path/'prompt.md')[-6:] == expected
    selected['hermes_command'] = ['/opt/hermes', 'chat', '--query-file', '{prompt_file}']
    assert executor_command(selected, tmp_path/'prompt.md')[-6:] == expected
    selected['hermes_command'] = ['another-worker', '{prompt_file}']
    assert executor_command(selected, tmp_path/'prompt.md') == ['another-worker', str(tmp_path/'prompt.md')]


def test_catalog_api_is_operator_only(tmp_path):
    from test_settings_views import make_api_client
    s = Service.create(tmp_path/'test.db', instance_id='fixture')
    client, operator, worker = make_api_client(s)
    assert client.post('/v1/model_catalog', json={}, headers=worker).status_code == 403
    response = client.post('/v1/model_catalog', json={}, headers=operator)
    assert response.status_code == 200 and response.json()['executor'] == 'external'


def test_provider_dropdown_saves_catalog_model_and_keeps_custom_fallback():
    from test_dispatch_queue_ui import dashboard_check
    dashboard_check(r'''
w.drawSettings({version:1,values:{worker:'external',reasoning_provider:null,reasoning_model:null,
 reasoning_effort:'low',application_model_override:false},supported:{worker:['external','hermes'],reasoning_effort:['low','medium','high','xhigh']}});
w.drawModelSelection({executor:'hermes_desktop',status:'available',provider:'custom',model:'local/model',providers:[
 {id:'openai-codex',name:'ChatGPT',models:['cloud/model'],capabilities:{}},
 {id:'custom',name:'Local',models:['local/model'],capabilities:{'local/model':{reasoning:false}}}]});
const provider=doc.getElementById('settings-provider'),model=doc.getElementById('settings-model');
assert(provider.value==='','Existing executor default changed');
provider.value='openai-codex';provider.onchange();
assert(model.options[0].value==='cloud/model','Wrong provider model catalog');
model.value='cloud/model';
w.noRefresh();let changes;
w.fetch=async(path,options)=>{changes=JSON.parse(options.body).changes;return {ok:true,status:200,json:async()=>({})};};
await doc.getElementById('settings-form').onsubmit({preventDefault(){}});
assert(changes.reasoning_provider==='openai-codex'&&changes.reasoning_model==='cloud/model'&&changes.application_model_override===true,'Selection not saved');
provider.value='custom';provider.onchange();
assert(doc.getElementById('settings-effort-label').hidden,'Unsupported reasoning control shown');
provider.value='__manual__';provider.onchange();
doc.getElementById('settings-custom-provider').value='my-provider';
doc.getElementById('settings-custom-model').value='my-model';
await doc.getElementById('settings-form').onsubmit({preventDefault(){}});
assert(changes.reasoning_provider==='my-provider'&&changes.reasoning_model==='my-model','Manual selection lost');
provider.value='';provider.onchange();
await doc.getElementById('settings-form').onsubmit({preventDefault(){}});
assert(changes.reasoning_provider===null&&changes.reasoning_model===null&&!changes.application_model_override,'Executor default not restored');
''')


def test_catalog_refresh_preserves_unsaved_custom_selection():
    from test_dispatch_queue_ui import dashboard_check
    dashboard_check(r'''
w.drawSettings({version:1,values:{worker:'external',reasoning_provider:null,reasoning_model:null,
 reasoning_effort:'low',application_model_override:false},supported:{worker:['external','hermes']}});
const provider=doc.getElementById('settings-provider');
provider.value='__manual__';provider.onchange();
doc.getElementById('settings-custom-provider').value='my-provider';
doc.getElementById('settings-custom-model').value='my-model';
doc.getElementById('settings-custom-model').oninput();
w.drawModelSelection({executor:'hermes_desktop',status:'unavailable',providers:[]});
assert(provider.value==='__manual__','Refresh replaced unsaved custom mode');
assert(doc.getElementById('settings-custom-provider').value==='my-provider','Refresh replaced provider');
assert(doc.getElementById('settings-custom-model').value==='my-model','Refresh replaced model');
''')
