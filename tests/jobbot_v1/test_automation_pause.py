"""Operator pause drains existing work and durably prevents new model work."""
import pytest

from job_applier.managed import Service
from job_applier import harvest_runtime, queue_runtime
from test_dispatch_queue import enqueue, runtime_fixture
from test_dispatch_queue_ui import dashboard_check
from test_local_sessions import setup


def test_status_before_upgrade_and_migration_preserve_existing_queue(tmp_path):
    from job_applier.managed_migrations import migrate
    s, asset, jobs, _, _ = setup(tmp_path)
    s.queue_control(command='resume')
    enqueue(s, asset, jobs, start_now=True)
    before=s.queue_status()['items']
    with s.tx() as db:
        db.execute('ALTER TABLE dispatch_control DROP COLUMN automation_paused')
        db.execute('DELETE FROM schema_migrations WHERE version=24')
    old=s.queue_status()
    assert old['automation_paused'] is False and old['automation_pause_supported'] is False
    assert s.discovery_status()['automation_paused'] is False
    migrate(s.db_path)
    upgraded=s.queue_status()
    assert upgraded['enabled'] and upgraded['wake_requested']
    assert upgraded['automation_paused'] is False and upgraded['automation_pause_supported'] is True
    assert upgraded['items']==before


@pytest.mark.parametrize('enabled', [False, True])
def test_pause_survives_restart_preserves_schedule_and_pending_requests(tmp_path, enabled):
    s, asset, jobs, _, cfg = setup(tmp_path)
    s.queue_control(command='resume' if enabled else 'pause')
    enqueue(s, asset, jobs, start_now=True)
    before = s.queue_status()
    paused = s.queue_control(command='pause_all')
    assert paused['automation_paused'] is True
    assert paused['enabled'] is enabled
    restarted = Service(s.db_path, instance_id=s.instance_id)
    assert restarted.queue_status()['automation_paused'] is True
    restarted.queue_control(command='run_next')
    restarted.queue_control(command='resume')  # automatic queue settings cannot unpause all
    assert restarted.queue_take() is None
    assert restarted.queue_status()['items'] == before['items']
    assert restarted.queue_status()['wake_requested']
    restarted.queue_control(command='pause' if not enabled else 'resume')
    resumed = restarted.queue_control(command='resume_all')
    assert resumed['automation_paused'] is False
    assert resumed['enabled'] is enabled
    assert restarted.queue_take()['job_id'] == jobs[0]['id']


def test_pause_all_leaves_current_application_and_evidence_untouched(tmp_path):
    s, asset, jobs, _, _ = setup(tmp_path)
    enqueue(s, asset, jobs)
    current = s.queue_take()
    before = s.queue_status()['items']
    s.queue_control(command='pause_all')
    assert s.queue_status()['counts']['dispatched'] == 1
    assert s.queue_status()['items'] == before
    s.queue_complete(current['id'], outcome='applied', detail='Synthetic confirmation')
    assert s.queue_take() is None
    assert next(item for item in s.queue_status()['items'] if item['id']==current['id'])['outcome'] == 'applied'
    s.queue_control(command='resume_all')
    assert s.queue_take()['job_id'] == jobs[1]['id']


def test_once_cannot_bypass_pause_or_consume_wake_request(tmp_path, monkeypatch):
    s, asset, jobs, _, cfg = runtime_fixture(tmp_path)
    cfg.update(identity_id='candidate', resume_asset_id=asset['id'])
    enqueue(s, asset, jobs, start_now=True)
    s.queue_control(command='pause_all')
    monkeypatch.setattr(queue_runtime, 'dispatch_one', lambda *a: pytest.fail('launched while paused'))
    assert queue_runtime.watch(cfg, s, once=True)['state'] == 'paused'
    assert s.queue_status()['wake_requested']
    assert s.queue_status()['next_automatic_at'] is None


def test_pause_while_current_dispatch_finishes_preserves_pending_wake(tmp_path, monkeypatch):
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    def finish(*args):
        s.queue_control(command='pause_all')
        s.queue_control(command='run_next')
        return {'state': 'finished'}
    monkeypatch.setattr(queue_runtime, 'dispatch_one', finish)
    queue_runtime.watch(cfg, s, once=True)
    status = s.queue_status()
    assert status['automation_paused'] and status['wake_requested']
    assert status['next_automatic_at'] is None


def test_discovery_pause_does_not_interrupt_current_work_and_resume_allows_next(tmp_path):
    from pathlib import Path
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    cfg['hermes_command'] = ['fixture', '{prompt_file}']
    def finish(command, **kwargs):
        s.queue_control(command='pause_all')
        Path(command[-1]).with_name('records.json').write_text('[]')
        return type('Done', (), {'returncode': 0})()
    assert harvest_runtime.run_harvest(cfg, s, launcher=finish)['state'] == 'completed'
    last = s.discovery_status()['last_run']
    assert harvest_runtime.run_harvest(cfg, s, launcher=finish)['state'] == 'paused'
    assert s.discovery_status()['last_run'] == last
    s.queue_control(command='resume_all')
    assert harvest_runtime.run_harvest(cfg, s, launcher=finish)['state'] == 'completed'
    assert s.discovery_status()['last_run']['id'] != last['id']


def test_paused_discovery_cli_is_successful_noop(monkeypatch, capsys):
    monkeypatch.setattr(harvest_runtime, 'resolve_config', lambda _: {})
    monkeypatch.setattr(harvest_runtime, 'prepare_local', lambda _: object())
    monkeypatch.setattr(harvest_runtime, 'run_harvest', lambda *a, **kw: {'state': 'paused'})
    assert harvest_runtime.main(['--scheduled']) == 0


@pytest.mark.parametrize('scheduled', [False, True])
def test_pause_skips_discovery_without_recording_an_attempt(tmp_path, scheduled):
    s, asset, _, _, cfg = runtime_fixture(tmp_path)
    cfg.update(identity_id='candidate', resume_asset_id=asset['id'])
    s.queue_control(command='pause_all')
    result = harvest_runtime.run_harvest(cfg, s, scheduled=scheduled,
        launcher=lambda *a, **kw: pytest.fail('discovery launched while paused'))
    assert result['state'] == 'paused'
    assert s.discovery_status()['automation_paused'] is True
    assert s.discovery_status()['last_run'] is None


def test_discovery_rechecks_pause_at_reservation_boundary(tmp_path, monkeypatch):
    s, asset, _, _, cfg = runtime_fixture(tmp_path)
    cfg.update(identity_id='candidate', resume_asset_id=asset['id'])
    original = s.discovery_status
    def stale_status():
        status = original()
        s.queue_control(command='pause_all')
        return status
    monkeypatch.setattr(s, 'discovery_status', stale_status)
    assert harvest_runtime.run_harvest(cfg, s,
        launcher=lambda *a, **kw: pytest.fail('stale status bypassed pause'))['state'] == 'paused'


def test_dashboard_pause_resume_and_draining_feedback():
    dashboard_check(r'''
w.draw(v);w.noRefresh();
const button=doc.getElementById('automation-toggle');
assert(button&&!button.hidden&&button.textContent==='Pause Jobot','Pause must be easy to find');
let calls=[];
w.fetch=async(path,options)=>{calls.push(JSON.parse(options.body));return {ok:true,status:200,json:async()=>({automation_paused:true})};};
await button.onclick();
assert(calls[0].command==='pause_all','Must pause applications and discovery together');
v.dispatch_queue.automation_paused=true;v.dispatch_queue.counts={dispatched:1};
v.discovery={installed:true,last_run:{state:'running'}};w.draw(v);
assert(button.textContent==='Resume Jobot','Resume control missing');
assert(doc.getElementById('automation-status').textContent.includes('Finishing current work'),'Draining incorrectly claims idle');
assert(!doc.getElementById('application-schedule').textContent.includes('follows after it finishes'),'Promises next job during pause');
assert(doc.getElementById('discovery-status').textContent.includes('paused'),'Discovery pause invisible');
v.dispatch_queue.counts={};v.discovery.last_run.state='completed';w.draw(v);
assert(doc.getElementById('automation-status').textContent.includes('Paused'),'Idle pause invisible');
await button.onclick();assert(calls[1].command==='resume_all','Resume lost');
await doc.getElementById('queue-run-next').onclick();
assert(doc.getElementById('notice').textContent.includes('Resume Jobot'),'Wake falsely promises work while paused');
''')
