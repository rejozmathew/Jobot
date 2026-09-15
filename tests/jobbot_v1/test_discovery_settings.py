"""Configurable discovery cadence with a fake executor and clock; no live jobs."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from job_applier.harvest_runtime import run_harvest
from job_applier.managed import Service, ProtocolError
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


@pytest.mark.parametrize('changes', [
    {'discovery_batch_size': 0}, {'discovery_batch_size': 2.5},
    {'discovery_interval_hours': 0}, {'discovery_interval_hours': float('inf')},
])
def test_discovery_settings_validate_user_input(tmp_path, changes):
    s, _, _, _, _ = runtime_fixture(tmp_path)
    with pytest.raises(ProtocolError):
        s.configure(changes, expected_version=s.settings_view()['version'])
