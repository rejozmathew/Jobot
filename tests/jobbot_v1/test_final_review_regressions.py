"""Narrowly scoped regression tests from primary decision brief.

Targeted regressions:
1) Intake metadata raw secret keys (reset_token, auth_token, id_token, nested session_token).
   Require rejection before persistence or no raw sentinel across DB snapshot / intake response.
   Core should reject structured keys ending in token/secret, while ordinary counts (token_count)
   are not overblocked.
2) Outcome applied/already_applied: ready(...) run with >1 jobs, claim first.
   For applied, do submission_intent fixture=True first, finish with quiescent=False and observed
   evidence. Assert lease quarantine; reconcile same outcome with new browser_quiescent=True
   evidence MUST release the exact lease without changing applied outcome, completed_at,
   elapsed_seconds or submission ledger count. Repeated reconcile idempotent; next job can be claimed.
   Historical terminal success must remain immutable.
3) Synthetic legacy DB via DatabaseManager: job status failed with earlier completed
   ApplicationAttempt outcome applied (and already_applied) and nonempty confirmation_evidence,
   later completed failed attempt. Original hash snapshot. migrate_copy verified source hash into
   NEW path; approve eligibility, register fixture identity and request/claim MUST be suppressed.
   Migration preserves all legacy rows, original source hash and current failed status;
   suppression must use historical successful attempt instead of resurrecting.
"""
from datetime import datetime
import hashlib
import json
import sqlite3

import pytest

from job_applier.database import ApplicationAttempt, DatabaseManager, Job
from job_applier.managed import ProtocolError, Service
from job_applier.managed_data import migrate_copy
from job_applier.managed_shared import dumps, uid
from test_ownership import accept, ready


def assert_sentinel_absent_from_db(db, sentinel):
    """Inspect all text fields across all tables to guarantee sentinel does not appear in ordinary DB fields."""
    cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cursor.fetchall()]
    for table in tables:
        tbl_cursor = db.execute(f'SELECT * FROM "{table}"')
        rows = tbl_cursor.fetchall()
        for row in rows:
            for idx, col_name in enumerate(row.keys()):
                val = row[idx]
                if isinstance(val, str):
                    assert sentinel not in val, (
                        f"Secret sentinel '{sentinel}' leaked into table '{table}', column '{col_name}': {val}"
                    )


# ---------------------------------------------------------------------------
# 1) Intake metadata raw secret keys (reset_token, auth_token, id_token, nested session_token)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    'metadata,sentinel',
    [
        ({'reset_token': 'SYNTHETIC_SENTINEL_RESET_TOKEN_84719'}, 'SYNTHETIC_SENTINEL_RESET_TOKEN_84719'),
        ({'auth_token': 'SYNTHETIC_SENTINEL_AUTH_TOKEN_39201'}, 'SYNTHETIC_SENTINEL_AUTH_TOKEN_39201'),
        ({'id_token': 'SYNTHETIC_SENTINEL_ID_TOKEN_65128'}, 'SYNTHETIC_SENTINEL_ID_TOKEN_65128'),
        ({'auth': {'session_token': 'SYNTHETIC_SENTINEL_SESSION_TOKEN_90432'}}, 'SYNTHETIC_SENTINEL_SESSION_TOKEN_90432'),
    ],
    ids=['reset_token', 'auth_token', 'id_token', 'nested_session_token'],
)
def test_intake_metadata_raw_secret_keys_rejected_or_absent(tmp_path, metadata, sentinel):
    """Intake metadata bearing secret keys ending in token must reject before persistence or redact sentinel."""
    s = Service.create(tmp_path / 'sec_intake.db', instance_id='inst-sec-intake')
    try:
        job = s.intake(
            url='https://careers.example.test/jobs/engineer-sec-intake',
            source_id='sec-intake-1',
            **metadata,
        )
    except ProtocolError:
        # A rejection must also leave no sentinel behind in committed storage.
        with s.tx() as db:
            assert_sentinel_absent_from_db(db, sentinel)
        return

    # If intake did not reject before persistence, verify sentinel is absent from intake response
    assert sentinel not in json.dumps(job), f"Sentinel leaked into intake response dict: {job}"

    # And verify sentinel is absent across DB snapshot
    with s.tx() as db:
        job_row = db.execute("SELECT metadata_json, notes, error FROM jobs WHERE id=?", (job['id'],)).fetchone()
        assert job_row is not None
        assert sentinel not in (job_row['metadata_json'] or ''), (
            f"Sentinel leaked into jobs.metadata_json: {job_row['metadata_json']}"
        )
        assert sentinel not in (job_row['notes'] or ''), f"Sentinel leaked into jobs.notes: {job_row['notes']}"
        assert sentinel not in (job_row['error'] or ''), f"Sentinel leaked into jobs.error: {job_row['error']}"
        assert_sentinel_absent_from_db(db, sentinel)


def test_intake_metadata_token_count_not_overblocked(tmp_path):
    """Metadata token_count is an ordinary count metric, not a credential; must not be rejected."""
    s = Service.create(tmp_path / 'sec_intake_allowed.db', instance_id='inst-sec-allowed')
    job = s.intake(
        url='https://careers.example.test/jobs/engineer-token-count',
        source_id='token-count-1',
        token_count=1024,
    )
    assert job is not None
    assert job['id'] is not None
    with s.tx() as db:
        job_row = db.execute("SELECT metadata_json FROM jobs WHERE id=?", (job['id'],)).fetchone()
        assert job_row is not None
        assert json.loads(job_row['metadata_json']).get('token_count') == 1024


# ---------------------------------------------------------------------------
# 2) Parametrize outcome applied/already_applied: quarantined lease reconciliation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('outcome', ['applied', 'already_applied'])
def test_quarantined_lease_reconciliation_and_immutable_history(tmp_path, outcome):
    """Quarantined lease reconciliation with browser_quiescent=True must release lease and allow next claim."""
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')
    assert a['job_id'] == ids[0]
    fence = a['fence']

    if outcome == 'applied':
        s.submission_intent(
            a['id'],
            worker_id='worker',
            fence=fence,
            evidence='fixture submission intent evidence',
            fixture=True,
        )

    finish_result = s.finish(
        a['id'],
        worker_id='worker',
        fence=fence,
        outcome=outcome,
        evidence='fixture observed finish evidence',
        quiescent=False,
    )
    assert finish_result['outcome'] == outcome

    # Assert lease quarantine
    with s.tx() as db:
        lease_q = db.execute("SELECT * FROM browser_leases WHERE profile=?", (r['browser_profile'],)).fetchone()
        assert lease_q is not None
        assert lease_q['state'] == 'quarantined'
        assert lease_q['attempt_id'] == a['id']
        ledger_count_before = db.execute("SELECT count(*) FROM submission_ledger").fetchone()[0]

    attempt_before = s.attempt(a['id'])
    completed_at_before = attempt_before['completed_at']
    elapsed_before = attempt_before['duration_seconds']

    # Reconcile same outcome with new browser_quiescent=True evidence MUST release the exact lease
    # without changing applied outcome, completed_at, elapsed_seconds or submission ledger count
    reconcile_result = s.reconcile(
        a['id'],
        outcome=outcome,
        evidence='fixture observed reconciled browser quiescent evidence',
        browser_quiescent=True,
    )
    assert reconcile_result['outcome'] == outcome
    assert reconcile_result['completed_at'] == completed_at_before
    assert reconcile_result['duration_seconds'] == elapsed_before

    with s.tx() as db:
        ledger_count_after = db.execute("SELECT count(*) FROM submission_ledger").fetchone()[0]
        assert ledger_count_after == ledger_count_before
        lease_after = db.execute("SELECT * FROM browser_leases WHERE profile=?", (r['browser_profile'],)).fetchone()
        assert lease_after is not None
        assert lease_after['attempt_id'] == a['id']
        assert lease_after['state'] == 'released'

    # Repeated reconcile idempotent
    reconcile_repeat = s.reconcile(
        a['id'],
        outcome=outcome,
        evidence='fixture observed reconciled browser quiescent evidence',
        browser_quiescent=True,
    )
    assert reconcile_repeat['outcome'] == outcome
    assert reconcile_repeat['completed_at'] == completed_at_before
    assert reconcile_repeat['duration_seconds'] == elapsed_before

    # Next job can be claimed
    b = s.claim(r['id'], worker_id='worker')
    assert b is not None
    assert b['job_id'] == ids[1]

    # Historical terminal success must remain immutable
    attempt_final = s.attempt(a['id'])
    assert attempt_final['outcome'] == outcome
    assert attempt_final['completed_at'] == completed_at_before
    assert attempt_final['duration_seconds'] == elapsed_before

    with s.tx() as db:
        job_0 = db.execute("SELECT status FROM jobs WHERE id=?", (ids[0],)).fetchone()
        assert job_0['status'] == outcome

    # Reconciling with conflicting outcome must be rejected and not mutate historical success
    with pytest.raises(ProtocolError, match='already_applied'):
        s.reconcile(
            a['id'],
            outcome='interrupted',
            evidence='conflicting evidence',
            browser_quiescent=True,
        )


# ---------------------------------------------------------------------------
# 3) Build entirely synthetic legacy DB via DatabaseManager: suppression of historical success
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('historical_outcome', ['applied', 'already_applied'])
def test_legacy_db_migration_suppresses_via_historical_success(tmp_path, historical_outcome):
    """Legacy DB migration preserves failed status and suppresses request/claim via historical success."""
    source_path = tmp_path / "legacy_source.db"
    mgr = DatabaseManager(str(source_path))
    session = mgr.get_session()

    job_id = f"legacy-job-{historical_outcome}"
    job_url = f"https://careers.example.test/jobs/legacy-{historical_outcome}"

    # 1. Job status failed with earlier completed ApplicationAttempt outcome applied / already_applied
    job = Job(
        id=job_id,
        url=job_url,
        title="Software Engineer",
        company="LegacyCorp",
        status="failed",
        notes="legacy job currently failed",
        error="subsequent attempt crashed",
        created_at=datetime(2025, 1, 1, 9, 0, 0),
        started_at=datetime(2025, 1, 1, 10, 0, 0),
        completed_at=datetime(2025, 1, 2, 11, 0, 0),
        updated_at=datetime(2025, 1, 2, 11, 0, 0),
    )
    session.add(job)

    # 2. Earlier completed ApplicationAttempt with outcome applied / already_applied and nonempty confirmation_evidence
    attempt_earlier = ApplicationAttempt(
        job_id=job_id,
        platform="greenhouse",
        workflow="standard",
        outcome=historical_outcome,
        evidence="legacy_confirmation_receipt_xyz_789",
        notes="earlier successful application",
        started_at=datetime(2025, 1, 1, 10, 0, 0),
        completed_at=datetime(2025, 1, 1, 10, 25, 0),
        duration_seconds=1500.0,
        meets_target=True,
    )
    session.add(attempt_earlier)

    # 3. Later completed failed attempt
    attempt_later = ApplicationAttempt(
        job_id=job_id,
        platform="greenhouse",
        workflow="standard",
        outcome="failed",
        evidence="network_timeout_during_retry",
        notes="subsequent failed attempt",
        started_at=datetime(2025, 1, 2, 10, 30, 0),
        completed_at=datetime(2025, 1, 2, 11, 0, 0),
        duration_seconds=1800.0,
        meets_target=False,
    )
    session.add(attempt_later)

    session.commit()
    session.close()
    mgr.close()

    # Original hash snapshot
    source_bytes = source_path.read_bytes()
    expected_source_hash = hashlib.sha256(source_bytes).hexdigest()

    # migrate_copy verified source hash into NEW path
    dest_path = tmp_path / "migrated_dest.db"
    migrate_copy(
        source_path,
        dest_path,
        instance_id="inst-migrated",
        expected_source_sha256=expected_source_hash,
    )

    # Verification 1: source hash untouched
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == expected_source_hash

    # Verification 2: migration preserves all legacy rows, original source hash, and current failed status
    # (suppression must use historical successful attempt instead of resurrecting)
    s = Service(dest_path, instance_id="inst-migrated")
    with s.tx() as db:
        migrated_job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        assert migrated_job is not None
        assert migrated_job['status'] == 'failed', (
            f"Job status must remain 'failed' (preserved without resurrection), but got: {migrated_job['status']}"
        )

        attempts = db.execute(
            "SELECT * FROM application_attempts WHERE job_id=? ORDER BY id ASC",
            (job_id,),
        ).fetchall()
        assert len(attempts) == 2
        assert attempts[0]['outcome'] == historical_outcome
        assert attempts[0]['evidence'] == "legacy_confirmation_receipt_xyz_789"
        assert attempts[1]['outcome'] == 'failed'

    # Verification 3: approve eligibility, register fixture identity, and request/claim MUST be suppressed
    s.identity(
        identity_id="candidate-fixture",
        person_key="person-fixture",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "fixture"}, "resume_ref": "asset:fixture-v1"},
    )
    s.eligibility(job_id, 'ready', reason='synthetic operator approval')

    # request_run MUST be suppressed because of historical successful attempt
    with pytest.raises(ProtocolError, match="already_applied"):
        s.request_run(
            request_id=f"req-{job_id}",
            job_ids=[job_id],
            identity_id="candidate-fixture",
            browser_profile="fixture-browser",
        )

    # retry MUST also be suppressed
    with pytest.raises(ProtocolError, match="already_applied"):
        s.retry(job_id)

    # claim MUST also be suppressed if a run had the job pending
    with s.tx() as db:
        run_id = uid()
        db.execute(
            "INSERT INTO runs(id, request_id, request_key, identity_id, browser_profile, state, control, requested_at, settings_json) VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, f"req-claim-{historical_outcome}", "key", "candidate-fixture", "fixture-browser", "awaiting_worker", "running", s.now(), dumps(s.settings)),
        )
        db.execute(
            "INSERT INTO run_jobs(run_id, job_id, position, state) VALUES (?,?,?,?)",
            (run_id, job_id, 0, 'pending'),
        )
    accept(s, {"id": run_id})  # Genuine ownership, so this cannot pass on wrong_worker.
    with pytest.raises(ProtocolError, match="already_applied"):
        s.claim(run_id, worker_id="worker")
