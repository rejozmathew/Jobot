"""Automatic pickup and recovery use synthetic jobs, never live applications."""
import pytest
from datetime import datetime, timedelta

from test_dispatch_queue import runtime_fixture, enqueue


def sync(s, asset):
    return s.queue_reconcile(identity_id='candidate', resume_asset_id=asset['id'])


def test_active_intake_is_queued_once_without_a_manual_enqueue(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    with s.tx() as db:
        db.execute("UPDATE jobs SET eligibility='held',intervention_reason=NULL WHERE id=?", (jobs[0]['id'],))
    sync(s, asset); sync(s, asset)
    assert s.queue_status()['counts']['queued'] == 3
    assert s.job(jobs[0]['id'])['eligibility'] == 'ready'
    first = s.queue_take()
    sync(s, asset)
    assert s.queue_take() is None
    assert s.queue_status()['counts']['dispatched'] == 1
    assert first['job_id'] == jobs[0]['id']


@pytest.mark.parametrize('outcome', ['interrupted', 'failed', 'blocked', 'submission_unknown'])
def test_recovery_allows_six_attempts_but_manual_retry_is_available(tmp_path, outcome):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    s.set_job_disposition(job_ids=[j['id'] for j in jobs[1:]], disposition='canceled', reason='Fixture')
    for number in range(1, 7):
        sync(s, asset)
        if number > 1:
            later = (datetime.fromisoformat(s.now()) + timedelta(hours=25)).isoformat()
            s.now = lambda: later
        item = s.queue_take()
        assert item and item['job_id'] == jobs[0]['id']
        s.queue_complete(item['id'], outcome=outcome, detail='Synthetic executor failure')
        assert s.queue_status()['latest_by_job'][jobs[0]['id']]['attempt_number'] == number
    sync(s, asset)
    assert s.queue_take() is None
    last = s.queue_status()['latest_by_job'][jobs[0]['id']]
    assert last['automatic_limit_reached'] and last['detail'] == 'Synthetic executor failure'
    item = enqueue(s, asset, [jobs[0]], request='operator-retry', retry=True)['items'][0]
    assert item['state'] == 'queued'
    assert s.queue_status()['latest_by_job'][jobs[0]['id']]['attempt_number'] == 1


def test_finished_old_interruption_reenters_queue_and_preserves_history(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    old = enqueue(s, asset, [jobs[0]])['items'][0]
    s.queue_take(); s.queue_complete(old['id'], outcome='interrupted', detail='Old failure')
    sync(s, asset)
    rows = [q for q in s.queue_status()['items'] if q['job_id'] == jobs[0]['id']]
    assert len(rows) == 2
    assert next(q for q in rows if q['id'] == old['id'])['detail'] == 'Old failure'
    assert s.queue_status()['latest_by_job'][jobs[0]['id']]['attempt_number'] == 2


def test_canceled_submitted_and_excluded_jobs_stay_out(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    s.set_job_disposition(job_ids=[jobs[0]['id']], disposition='canceled', reason='Closed')
    with s.tx() as db:
        db.execute("UPDATE jobs SET status='applied' WHERE id=?", (jobs[1]['id'],))
        db.execute("UPDATE jobs SET eligibility='excluded' WHERE id=?", (jobs[2]['id'],))
    sync(s, asset)
    assert s.queue_status()['items'] == []


def test_explicit_hold_and_excluded_company_are_not_silently_promoted(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    with s.tx() as db:
        db.execute("UPDATE jobs SET eligibility='held',intervention_reason='Operator hold' WHERE id=?", (jobs[0]['id'],))
        db.execute("UPDATE jobs SET company='Excluded Fixture',eligibility='held',intervention_reason=NULL WHERE id=?", (jobs[1]['id'],))
    settings = s.settings_view()
    s.configure(changes={'excluded_companies': ['Excluded Fixture']}, expected_version=settings['version'])
    sync(s, asset)
    assert [q['job_id'] for q in s.queue_status()['items']] == [jobs[2]['id']]
    assert s.job(jobs[1]['id'])['eligibility'] == 'held'


def test_discovery_skip_stays_held_but_prior_operator_approval_is_preserved(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    with s.tx() as db:
        db.execute('UPDATE jobs SET metadata_json=? WHERE id IN (?,?)', ('{"verdict":"Skip"}', jobs[0]['id'], jobs[1]['id']))
        db.execute("UPDATE jobs SET eligibility='held',intervention_reason=NULL WHERE id=?", (jobs[0]['id'],))
    sync(s, asset)
    ids = {q['job_id'] for q in s.queue_status()['items']}
    assert jobs[0]['id'] not in ids and jobs[1]['id'] in ids


def test_pending_answers_do_not_spend_automatic_retries(tmp_path):
    from test_local_sessions import reserve, connect, own
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    session = connect(s, reserve(s, asset, jobs))
    s.request_question(**own(s, session), field='fixture_question', question='Synthetic required answer?', kind='text')
    s.finish(**own(s, session), outcome='blocked', evidence='Waiting for answer', quiescent=False)
    s.session_stopped(session['id'], reason='Waiting for answer', browser_stopped=True)
    sync(s, asset)
    assert jobs[0]['id'] not in {q['job_id'] for q in s.queue_status()['items']}


@pytest.mark.parametrize('outcome', ['stopped', 'ready_for_review'])
def test_user_stop_and_completed_review_are_not_automatic_retries(tmp_path, outcome):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    item = enqueue(s, asset, [jobs[0]])['items'][0]
    s.queue_complete(item['id'], outcome=outcome)
    sync(s, asset)
    assert s.queue_status()['latest_by_job'][jobs[0]['id']]['id'] == item['id']


def test_run_next_reconciles_active_jobs_with_configured_selection(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    s.dispatch_selection = dict(identity_id='candidate', resume_asset_id=asset['id'])
    q = s.queue_control(command='run_next')
    assert q['counts']['queued'] == 3 and q['wake_requested'] == 1


def test_worker_collects_active_jobs_without_dashboard_click(tmp_path, monkeypatch):
    from job_applier.queue_runtime import watch
    s, asset, jobs, _, cfg = runtime_fixture(tmp_path)
    observed = []
    def dispatch(config, service):
        observed.append(service.queue_status()['counts'].get('queued', 0))
        return {'state': 'fixture'}
    monkeypatch.setattr('job_applier.queue_runtime.dispatch_one', dispatch)
    watch(cfg, s, once=True)
    assert observed == [3]


def test_delayed_retries_allow_other_jobs_and_survive_restart(tmp_path):
    from job_applier.managed import Service
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    s.now = lambda: '2026-09-16T10:00:00+00:00'
    sync(s, asset)
    first = s.queue_take()
    s.queue_complete(first['id'], outcome='interrupted', detail='Temporary employer error')
    sync(s, asset)
    retry = s.queue_status()['latest_by_job'][jobs[0]['id']]
    assert retry['next_attempt_at'] == '2026-09-16T12:00:00+00:00'
    # Future retry must not stop another ready job from running.
    other = s.queue_take(); assert other['job_id'] == jobs[1]['id']
    s.queue_complete(other['id'], outcome='applied')
    other = s.queue_take(); assert other['job_id'] == jobs[2]['id']
    s.queue_complete(other['id'], outcome='applied')
    assert s.queue_take() is None
    fresh = Service(s.db_path, instance_id=s.instance_id)
    fresh.now = lambda: '2026-09-16T11:59:59+00:00'
    assert fresh.queue_take() is None
    fresh.now = lambda: '2026-09-16T12:00:00+00:00'
    second = fresh.queue_take(); assert second['job_id'] == jobs[0]['id']
    fresh.queue_complete(second['id'], outcome='failed', detail='Still unavailable')
    sync(fresh, asset)
    assert fresh.queue_status()['latest_by_job'][jobs[0]['id']]['next_attempt_at'] == '2026-09-16T14:00:00+00:00'
    # Run next is a wakeup, not permission to collapse scheduled retry delays.
    fresh.dispatch_selection = dict(identity_id='candidate', resume_asset_id=asset['id'])
    fresh.queue_control(command='run_next')
    assert fresh.queue_take() is None


def test_six_attempts_span_two_days_with_no_retry_burst(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    s.set_job_disposition(job_ids=[j['id'] for j in jobs[1:]], disposition='canceled', reason='Fixture')
    base = datetime.fromisoformat('2026-09-16T10:00:00+00:00')
    for hour in (0, 2, 4, 6, 24, 28):
        current = (base + timedelta(hours=hour)).isoformat()
        s.now = lambda: current
        sync(s, asset)
        row = s.queue_status()['latest_by_job'][jobs[0]['id']]
        assert row['next_attempt_at'] == current
        item = s.queue_take()
        assert item
        s.queue_complete(item['id'], outcome='failed')
    sync(s, asset)
    assert s.queue_take() is None
    assert s.queue_status()['automatic_attempt_limit'] == 6


def test_late_attempt_preserves_spacing_and_exhausted_old_series_reopens(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    s.set_job_disposition(job_ids=[j['id'] for j in jobs[1:]], disposition='canceled', reason='Fixture')
    for current in ('2026-09-16T10:00:00+00:00', '2026-09-16T12:00:00+00:00', '2026-09-17T12:00:00+00:00'):
        s.now = lambda: current
        sync(s, asset)
        item = s.queue_take()
        s.queue_complete(item['id'], outcome='failed', detail='Retained failed attempt')
    sync(s, asset)
    retry = s.queue_status()['latest_by_job'][jobs[0]['id']]
    assert retry['attempt_number'] == 4
    assert retry['next_attempt_at'] == '2026-09-17T14:00:00+00:00'
    assert s.queue_take() is None
    assert len([r for r in s.queue_status()['items'] if r['state']=='finished']) == 3


def test_restored_job_reenters_automatic_queue(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    sync(s, asset)
    s.set_job_disposition(job_ids=[jobs[0]['id']], disposition='canceled', reason='Fixture')
    s.set_job_disposition(job_ids=[jobs[0]['id']], disposition='active')
    sync(s, asset)
    last = s.queue_status()['latest_by_job'][jobs[0]['id']]
    assert last['state'] == 'queued' and last['attempt_number'] == 1
