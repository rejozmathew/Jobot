"""Compatibility acceptance tests for legacy components against managed databases.

Primary owns production architecture and implementation logic.
These tests define and assert contracts for legacy compatibility:
1) Legacy JobQueue.add_url on an explicitly managed DB routes to SAME Service.intake:
   adding tracking variant of prior managed URL results in same id and additional
   source/provenance, no duplicate canonical job. Verify .get can read new ready_for_review status.
2) Legacy direct JobQueue.claim_next and update_status must refuse writing a managed instance
   with ProtocolError('managed_worker_required') and preserve active owner. They must not
   clear history or turn running into failed.
3) JobQueue.cleanup_stuck_jobs on managed DB must return 0 without modifying active job/attempt.
4) JobRunner constructed with managed db_path must fail closed ('managed_worker_required')
   before legacy agent initialization or cleanup. Import must not require browser_use (now lazy in main).
5) ApplicationTracker.start_attempt against managed db_path must reject managed_worker_required
   instead of creating a parallel attempt; use actual source signature. Other legacy tracking writers
   finish_attempt/transition_phase for a managed attempt must reject. Existing read-only history
   need not be rejected.
"""
from pathlib import Path
import subprocess
import sys
import pytest

from job_applier.database import JobStatus
from job_applier.db_queue import JobQueue, AddJobRequest
from job_applier.application_tracker import ApplicationTracker
from job_applier.runner import JobRunner
from job_applier.managed import Service, ProtocolError

try:
    from test_ownership import ready, accept
except ImportError:
    from tests.jobbot_v1.test_ownership import ready, accept


def test_legacy_job_queue_add_url_routes_to_managed_intake_and_get_reads_ready_for_review(tmp_path):
    """Legacy JobQueue.add_url on managed DB routes to Service.intake.

    Adding tracking variant of prior managed URL results in same id and additional
    source/provenance, no duplicate canonical job. Verify .get can read new ready_for_review status.
    """
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')
    s.finish(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        outcome='ready_for_review',
        evidence='fixture review',
        quiescent=True,
    )
    queue = JobQueue(db_path=str(s.db_path))

    # Verify .get can read new ready_for_review status
    job_record = queue.get(ids[0])
    assert job_record is not None
    assert job_record.status == 'ready_for_review'

    # Adding tracking variant of prior managed URL results in same id and additional source/provenance
    prior_url = 'https://careers.example.test/jobs/0'
    tracking_variant = 'https://careers.example.test/jobs/0?utm_source=linkedin&utm_medium=feed'
    added = queue.add(AddJobRequest(url=tracking_variant))

    added_id = getattr(added, 'id', None) or (added.get('id') if isinstance(added, dict) else None)
    assert added_id == ids[0]

    sources = s.sources(ids[0])
    assert len(sources) >= 2
    assert any(src['original_url'] == tracking_variant for src in sources)

    # No duplicate canonical job
    with s.tx() as db:
        canonical_count = db.execute(
            "SELECT COUNT(*) FROM jobs WHERE url=?", (prior_url,)
        ).fetchone()[0]
        assert canonical_count == 1


def test_legacy_job_queue_claim_next_and_update_status_refuse_managed_instance(tmp_path):
    """Legacy direct JobQueue.claim_next and update_status must refuse writing a managed instance

    with ProtocolError('managed_worker_required') and preserve active owner.
    They must not clear history or turn running into failed.
    """
    s, r, ids = ready(tmp_path)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')
    queue = JobQueue(db_path=str(s.db_path))

    # Direct claim_next must refuse writing managed instance
    with pytest.raises(ProtocolError, match='managed_worker_required'):
        queue.claim_next()

    # update_status must refuse writing managed instance
    with pytest.raises(ProtocolError, match='managed_worker_required'):
        queue.update_status(ids[0], JobStatus.FAILED, error='legacy overwrite attempt')

    # Preserve active owner: must not clear history or turn running into failed
    job = s.job(ids[0])
    assert job['status'] == 'running'

    attempt = s.attempt(a['id'])
    assert attempt['worker_id'] == 'worker'
    assert attempt['fence'] == a['fence']
    assert attempt['completed_at'] is None

    # Heartbeat still succeeds for active owner
    hb = s.heartbeat(a['id'], worker_id='worker', fence=a['fence'])
    assert hb['control'] == 'running'


def test_job_queue_cleanup_stuck_jobs_on_managed_db_returns_zero_and_preserves_active(tmp_path):
    """JobQueue.cleanup_stuck_jobs on managed DB must return 0 without modifying active job/attempt."""
    s, r, ids = ready(tmp_path)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')
    queue = JobQueue(db_path=str(s.db_path))

    count = queue.cleanup_stuck_jobs()
    assert count == 0

    job = s.job(ids[0])
    assert job['status'] == 'running'
    assert job['error'] == ''

    attempt = s.attempt(a['id'])
    assert attempt['completed_at'] is None


def test_job_runner_constructed_with_managed_db_path_fails_closed(tmp_path):
    """JobRunner constructed with managed db_path must fail closed ('managed_worker_required')

    before legacy agent initialization or cleanup.
    """
    s, r, ids = ready(tmp_path)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    with pytest.raises(ProtocolError, match='managed_worker_required'):
        JobRunner(db_path=str(s.db_path))

    # Must fail closed before legacy agent initialization or cleanup
    assert s.job(ids[0])['status'] == 'running'
    assert s.attempt(a['id'])['completed_at'] is None


def test_job_runner_import_does_not_require_browser_use():
    """JobRunner import must not require browser_use (now lazy in main)."""
    repo_root = str(Path(__file__).parents[2])
    script = (
        "import sys\n"
        "from job_applier.runner import JobRunner\n"
        "leaked = [m for m in sys.modules if 'browser_use' in m]\n"
        "if leaked:\n"
        "    print(f'Leaked modules: {leaked}', file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "sys.exit(0)\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert res.returncode == 0, f"Importing JobRunner required or leaked browser_use:\n{res.stderr}"


def test_application_tracker_writers_reject_managed_and_allow_read_only(tmp_path):
    """ApplicationTracker.start_attempt against managed db_path must reject managed_worker_required

    instead of creating a parallel attempt; other legacy tracking writers finish_attempt/transition_phase
    for a managed attempt must reject. Existing read-only history need not be rejected.
    """
    s, r, ids = ready(tmp_path)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')
    tracker = ApplicationTracker(db_path=str(s.db_path))

    # start_attempt must reject managed_worker_required instead of creating parallel attempt
    with pytest.raises(ProtocolError, match='managed_worker_required'):
        tracker.start_attempt(
            url='https://careers.example.test/jobs/0',
            company='ExampleCorp',
            title='Software Engineer',
            platform='generic',
        )

    # Verify no parallel attempt created
    with s.tx() as db:
        attempts = db.execute(
            "SELECT * FROM application_attempts WHERE job_id=?", (ids[0],)
        ).fetchall()
        assert len(attempts) == 1
        assert attempts[0]['id'] == a['id']

    # transition_phase for a managed attempt must reject
    with pytest.raises(ProtocolError, match='managed_worker_required'):
        tracker.transition_phase(a['id'], 'form_filling', note='attempting form fill')

    # finish_attempt for a managed attempt must reject
    with pytest.raises(ProtocolError, match='managed_worker_required'):
        tracker.finish_attempt(
            a['id'], outcome='ready_for_review', evidence='done', note='finished'
        )

    # Read-only reports on managed data may remain
    history = tracker.job_history()
    assert isinstance(history, list)
    assert len(history) == 2
    assert any(h['job_id'] == ids[0] for h in history)

    company_history = tracker.company_history()
    assert isinstance(company_history, list)
