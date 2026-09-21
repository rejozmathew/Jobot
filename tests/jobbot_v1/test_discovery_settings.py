"""Configurable discovery cadence with a fake executor and clock; no live jobs."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from job_applier.harvest_runtime import run_harvest
from job_applier.managed import Service, ProtocolError
from job_applier.queue_runtime import executor_command
from test_dispatch_queue import runtime_fixture


def test_saved_discovery_settings_control_next_run_without_restarting(tmp_path):
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    s.now = lambda: now.isoformat()
    calls = []
    cfg['hermes_command'] = ['fixture', '{prompt_file}']
    cfg['harvest_batch_size'] = 99  # Old private config must not override the UI.
    def launch(command, **kwargs):
        calls.append(Path(command[-1]).read_text(encoding='utf-8'))
        Path(command[-1]).with_name('records.json').write_text('[]', encoding='utf-8')
        return type('Done', (), {'returncode': 0})()
    assert s.settings_view()['values']['discovery_batch_size'] == 5
    assert s.settings_view()['values']['discovery_interval_hours'] == 4
    assert run_harvest(cfg, s, scheduled=True, launcher=launch)['executor_exit_code'] == 0
    assert 'Find up to 5' in calls[-1]
    assert s.discovery_status()['next_due_at'] == (now+timedelta(hours=4)).isoformat()
    now += timedelta(hours=3)
    assert run_harvest(cfg, s, scheduled=True, launcher=launch)['state'] == 'not_due'
    assert len(calls) == 1
    # Another process saves changes; the already-created scheduler Service must see them.
    other = Service(s.db_path, instance_id=s.instance_id)
    other.configure({'discovery_interval_hours': 3, 'discovery_batch_size': 2},
                    expected_version=other.settings_view()['version'])
    run_harvest(cfg, s, scheduled=True, launcher=launch)
    assert len(calls) == 2 and 'Find up to 2' in calls[-1]
    status = s.discovery_status()
    assert status['last_run']['state'] == 'completed'
    assert status['scheduler_last_checked_at'] == now.isoformat()
    assert status['next_due_at'] == (now+timedelta(hours=3)).isoformat()
    assert s.view()['discovery']['batch_size'] == 2
    # Manual discovery bypasses the due check and still uses the selected settings.
    run_harvest(cfg, s, launcher=launch)
    assert len(calls) == 3


def test_discovery_failure_and_dead_process_are_visible(tmp_path):
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    def broken(*args, **kwargs):
        raise FileNotFoundError('private launch details must not be displayed')
    with pytest.raises(FileNotFoundError):
        run_harvest(cfg, s, scheduled=True, launcher=broken)
    status = s.discovery_status()
    assert status['last_run']['state'] == 'failed'
    assert status['last_run']['error'] == 'FileNotFoundError'
    assert 'private launch details' not in str(status)
    with s.tx() as db:
        db.execute('UPDATE discovery_runs SET ended_at=NULL,process_identity_json=?', ('{}',))
    assert s.discovery_status()['last_run']['state'] == 'interrupted'


def test_discovery_exit_zero_without_records_is_not_completed(tmp_path):
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    run_harvest(cfg, s, launcher=lambda *a, **kw: type('Done', (), {'returncode': 0})())
    last = s.discovery_status()['last_run']
    assert last['executor_exit_code'] == 0
    assert last['state'] == 'incomplete'


@pytest.mark.parametrize('exit_code,records,state,cli_exit', [
    (0, False, 'incomplete', 1),
    (0, True, 'completed', 0),
    (1, False, 'failed', 1),
    (1, True, 'failed', 1),
])
def test_discovery_cli_reports_actual_completion(tmp_path, monkeypatch, capsys,
                                                 exit_code, records, state, cli_exit):
    import json
    from job_applier import harvest_runtime
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    cfg['hermes_command'] = ['fixture', '{prompt_file}']
    def launch(command, **kwargs):
        if records:
            Path(command[-1]).with_name('records.json').write_text('[]', encoding='utf-8')
        return type('Done', (), {'returncode': exit_code})()
    actual_run = run_harvest
    monkeypatch.setattr(harvest_runtime, 'resolve_config', lambda _: cfg)
    monkeypatch.setattr(harvest_runtime, 'prepare_local', lambda _: s)
    monkeypatch.setattr(harvest_runtime, 'run_harvest',
                        lambda *args, **kwargs: actual_run(*args, **kwargs, launcher=launch))
    assert harvest_runtime.main([]) == cli_exit
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == state == s.discovery_status()['last_run']['state']
    assert result['executor_exit_code'] == exit_code


def test_discovery_cli_not_due_is_success(monkeypatch, capsys):
    import json
    from job_applier import harvest_runtime
    monkeypatch.setattr(harvest_runtime, 'resolve_config', lambda _: {})
    monkeypatch.setattr(harvest_runtime, 'prepare_local', lambda _: object())
    monkeypatch.setattr(harvest_runtime, 'run_harvest', lambda *a, **kw: {'state': 'not_due'})
    assert harvest_runtime.main(['--scheduled']) == 0
    assert json.loads(capsys.readouterr().out)['state'] == 'not_due'


def test_discovery_uses_its_own_executor_without_changing_applications(tmp_path):
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    cfg['hermes_command'] = ['hermes', 'chat', '--query-file', '{prompt_file}']
    cfg['harvest_hermes_command'] = ['hermes', '--profile', 'jobbot-discovery',
                                    'chat', '--query-file', '{prompt_file}']
    launched = []
    def launch(command, **kwargs):
        launched.append(command)
        return type('Done', (), {'returncode': 0})()
    run_harvest(cfg, s, launcher=launch)
    assert launched[0][:3] == ['hermes', '--profile', 'jobbot-discovery']
    assert executor_command(cfg, 'application.md') == ['hermes', 'chat', '--query-file', 'application.md']
    assert cfg['hermes_command'][1] == 'chat'


@pytest.mark.parametrize('command', [[], None, 'hermes chat'])
def test_invalid_discovery_command_does_not_fall_back_to_application_executor(tmp_path, command):
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    cfg['harvest_hermes_command'] = command
    with pytest.raises(ProtocolError, match='invalid_hermes_command'):
        run_harvest(cfg, s, launcher=lambda *a, **kw: pytest.fail('must not launch'))


def test_next_discovery_receives_unfinished_checkpoint(tmp_path):
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    cfg['hermes_command'] = ['fixture', '{prompt_file}']
    checkpoint = []
    def interrupted(command, **kwargs):
        path = Path(command[-1]).with_name('checkpoint.json')
        path.write_text('[]', encoding='utf-8')
        checkpoint.append(path)
        return type('Done', (), {'returncode': 0})()
    run_harvest(cfg, s, launcher=interrupted)
    assert s.discovery_status()['last_run']['state'] == 'incomplete'
    def resumed(command, **kwargs):
        brief = Path(command[-1]).read_text(encoding='utf-8')
        assert str(checkpoint[0]) in brief
        Path(command[-1]).with_name('records.json').write_text('[]', encoding='utf-8')
        return type('Done', (), {'returncode': 0})()
    run_harvest(cfg, s, launcher=resumed)
    assert s.discovery_status()['last_run']['state'] == 'completed'


@pytest.mark.parametrize('changes', [
    {'discovery_batch_size': 0}, {'discovery_batch_size': 2.5},
    {'discovery_interval_hours': 0}, {'discovery_interval_hours': float('inf')},
])
def test_discovery_settings_validate_user_input(tmp_path, changes):
    s, _, _, _, _ = runtime_fixture(tmp_path)
    with pytest.raises(ProtocolError):
        s.configure(changes, expected_version=s.settings_view()['version'])
