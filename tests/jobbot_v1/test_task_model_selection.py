"""Model routing uses synthetic settings and executors, never live applications."""
import copy
import json
from pathlib import Path

import pytest

from job_applier.harvest_runtime import run_harvest
from job_applier.managed import Service, ProtocolError
from test_dispatch_queue import runtime_fixture


def select(service, **changes):
    service.configure(changes, expected_version=service.settings_view()['version'])


def test_discovery_inherits_fresh_application_selection_and_keeps_its_profile(tmp_path):
    service, _, _, _, config = runtime_fixture(tmp_path)
    config.update(hermes_desktop={}, harvest_hermes_command=[
        'hermes', '--profile', 'discovery', 'chat', '--query-file', '{prompt_file}'])
    original = copy.deepcopy(config)
    other = Service(service.db_path, instance_id=service.instance_id)
    select(other, application_model_override=True, reasoning_provider='openai-codex',
           reasoning_model='chosen-model', reasoning_effort='high')
    def launch(command, **kwargs):
        assert command[:3] == ['hermes', '--profile', 'discovery']
        assert command[-6:] == ['--provider', 'openai-codex', '--model', 'chosen-model', '--reasoning', 'high']
        task = Path(command[command.index('--query-file')+1])
        snapshot = json.loads(task.with_name('model-selection.json').read_text())
        assert snapshot['model'] == 'chosen-model'
        select(other, reasoning_model='later-model')
        assert json.loads(task.with_name('model-selection.json').read_text()) == snapshot
        task.with_name('records.json').write_text('[]')
        return type('Done', (), {'returncode': 0})()
    assert run_harvest(config, service, launcher=launch)['state'] == 'completed'
    assert config == original


def test_separate_discovery_selection_overrides_stale_cli_flags(tmp_path):
    from job_applier.model_settings import task_selection
    from job_applier.queue_runtime import executor_command
    service, _, _, _, config = runtime_fixture(tmp_path)
    select(service, discovery_model_mode='separate', discovery_provider='custom',
           discovery_model='separate-model', discovery_effort='medium')
    config['hermes_command'] = ['hermes', 'chat', '--model=old-model', '--provider', 'old',
                                '--reasoning', 'low', '--query-file', '{prompt_file}']
    selected = task_selection(config, service.settings_view()['values'], 'discovery')
    command = executor_command(selected, tmp_path/'task.md')
    assert 'old' not in command and '--model=old-model' not in command
    assert command.count('--reasoning') == 1
    assert command[-6:] == ['--provider', 'custom', '--model', 'separate-model', '--reasoning', 'medium']
    assert service.settings_view()['values']['reasoning_model'] is None


def test_inherited_desktop_default_is_resolved_before_switching_to_discovery_cli(tmp_path, monkeypatch):
    from job_applier import model_settings
    service, _, _, _, config = runtime_fixture(tmp_path)
    config['hermes_desktop'] = {}
    monkeypatch.setattr(model_settings, 'model_catalog', lambda c: dict(provider='configured', model='default-model'))
    result = model_settings.task_selection(config, service.settings_view()['values'], 'discovery')
    assert result['application_model'] == 'default-model'
    assert result['application_provider'] == 'configured'


def test_unavailable_desktop_default_cannot_silently_select_discovery_profile_model(monkeypatch):
    from job_applier import model_settings
    monkeypatch.setattr(model_settings, 'model_catalog', lambda c: dict(status='unavailable'))
    with pytest.raises(ProtocolError, match='application_model_unavailable'):
        model_settings.task_selection({'hermes_desktop':{}}, {}, 'discovery')
    # An explicitly selected model does not depend on catalog availability.
    result = model_settings.task_selection({'hermes_desktop':{}}, dict(
        application_model_override=True,reasoning_provider='cloud',reasoning_model='selected',reasoning_effort='low'), 'discovery')
    assert result['application_model'] == 'selected'


def test_answer_learning_uses_fresh_shared_model_for_both_inference_paths(tmp_path, monkeypatch):
    from job_applier import answer_learning
    from test_answer_learning import connected, reply, synthesis
    service, _, owner, _, _ = connected(tmp_path)
    service.executor_config = {'answer_learning': {'provider': 'custom', 'model': 'old-local'}}
    reply(service, owner)
    select(service, application_model_override=True, reasoning_provider='openai-codex',
           reasoning_model='chosen-model', reasoning_effort='high')
    seen = []
    def generate(config, instruction, payload):
        seen.append(config)
        assert config['answer_learning']['provider'] == 'openai-codex'
        assert config['answer_learning']['model'] == 'chosen-model'
        return synthesis(payload)
    monkeypatch.setattr(answer_learning, 'model_generate', generate)
    assert service.learn_answers()['state'] == 'learned'
    assert seen
    assert service.executor_config['answer_learning']['model'] == 'old-local'


@pytest.mark.parametrize('changes', [
    {'discovery_model_mode': 'typo'}, {'discovery_model_mode': 'separate'},
    {'discovery_provider': 'only-provider'}, {'learning_model_mode': 'separate'},
    {'learning_model_mode': 'separate', 'learning_provider': 'cloud', 'learning_model': 'bad model'},
])
def test_invalid_task_model_settings_are_rejected(tmp_path, changes):
    service, _, _, _, _ = runtime_fixture(tmp_path)
    with pytest.raises(ProtocolError):
        select(service, **changes)


def test_cli_application_default_uses_application_profile_and_flag_precedence(tmp_path, monkeypatch):
    from job_applier.model_settings import task_selection
    home = tmp_path/'hermes'
    profile = home/'profiles'/'applications'
    profile.mkdir(parents=True)
    (profile/'config.yaml').write_text('model:\n  provider: cloud\n  default: profile-model\n')
    monkeypatch.setenv('HERMES_HOME', str(home))
    config = {'hermes_command': ['hermes','--profile','applications','chat','--model=flag-model'],
              'harvest_hermes_command': ['hermes','--profile','discovery','chat']}
    result = task_selection(config, {}, 'discovery')
    assert result['application_model'] == 'flag-model'
    assert result['application_provider'] == 'cloud'


def test_separate_learning_keeps_launcher_and_switching_to_shared_ignores_old_model(tmp_path):
    service, _, _, _, config = runtime_fixture(tmp_path)
    config['answer_learning'] = {'hermes_launcher':'installed-hermes','model':'old-local'}
    service.executor_config = config
    select(service, learning_model_mode='separate', learning_provider='custom',
           learning_model='learning-model', learning_effort='medium',
           application_model_override=True, reasoning_provider='cloud', reasoning_model='application-model')
    assert service._learning_config()['answer_learning'] == dict(
        hermes_launcher='installed-hermes', provider='custom', model='learning-model', effort='medium')
    select(service, learning_model_mode='same_application')
    assert service._learning_config()['answer_learning']['model'] == 'application-model'
    assert service.settings_view()['values']['learning_model'] == 'learning-model'


def test_learning_child_binds_auxiliary_recovery_to_selected_runtime(monkeypatch):
    import io
    import sys
    from types import ModuleType, SimpleNamespace
    from job_applier.answer_learning_model import main
    modules = {name: ModuleType(name) for name in (
        'hermes_cli', 'hermes_cli.config', 'hermes_cli.runtime_provider', 'agent', 'agent.auxiliary_client')}
    modules['hermes_cli.config'].load_config = lambda: {'model': {'provider':'custom','default':'old-local'}}
    modules['hermes_cli.runtime_provider'].resolve_runtime_provider = lambda **kw: dict(
        provider=kw['requested'], base_url='https://synthetic.invalid', api_key='private-fixture')
    calls = []
    def call_llm(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"reusable":false}'))])
    modules['agent.auxiliary_client'].call_llm = call_llm
    for name, module in modules.items():monkeypatch.setitem(sys.modules,name,module)
    monkeypatch.setattr(sys,'stdin',io.StringIO(json.dumps(dict(
        provider='cloud',model='selected-model',effort='high',instruction='synthetic',payload={}))))
    output = io.StringIO();monkeypatch.setattr(sys,'stdout',output)
    main()
    assert calls[0]['main_runtime']['model'] == calls[0]['model'] == 'selected-model'
    assert calls[0]['main_runtime']['provider'] == 'cloud'
    assert calls[0]['reasoning_config']['effort'] == 'high'
    assert 'private-fixture' not in output.getvalue()


def test_separate_picker_round_trip_and_shared_summary():
    from test_dispatch_queue_ui import dashboard_check
    dashboard_check(r'''
w.drawSettings({version:1,values:{worker:'external',reasoning_provider:'cloud',reasoning_model:'apply-model',
 reasoning_effort:'high',application_model_override:true,discovery_model_mode:'same_application',
 learning_model_mode:'same_application'},supported:{worker:['external','hermes']}});
w.drawModelSelection({executor:'hermes_desktop',status:'available',providers:[
 {id:'cloud',name:'Cloud',models:['apply-model','search-model'],capabilities:{}}]});
assert(doc.getElementById('discovery-model-summary').textContent.includes('apply-model'),'Shared selection not visible');
const mode=doc.getElementById('discovery-model-mode');mode.value='separate';mode.onchange();
const provider=doc.getElementById('discovery-provider');provider.value='cloud';provider.onchange();
doc.getElementById('discovery-model').value='search-model';
doc.getElementById('discovery-effort').value='medium';
w.noRefresh();let changes;
w.fetch=async(path,options)=>{changes=JSON.parse(options.body).changes;return {ok:true,status:200,json:async()=>({})};};
await doc.getElementById('settings-form').onsubmit({preventDefault(){}});
assert(changes.discovery_model==='search-model'&&changes.discovery_model_mode==='separate','Separate selection not saved');
assert(changes.reasoning_model==='apply-model','Application model changed');
mode.value='same_application';mode.onchange();
await doc.getElementById('settings-form').onsubmit({preventDefault(){}});
assert(changes.discovery_model_mode==='same_application','Shared mode not saved');
assert(doc.getElementById('discovery-model-fields').hidden,'Separate fields still visible');
''')
