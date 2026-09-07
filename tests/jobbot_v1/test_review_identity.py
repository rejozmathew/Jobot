"""Reviewer regression tests for JobBot identity deduplication and migration contracts.

Regressions covered:
L2: Intake URL A with no verified identity; record fixture applied via test helper /
    operator reconcile fixture. Enrich same A with verified namespace N + req R;
    then alternate URL B with same N/R must dedupe or global suppression reject
    executing it. Does not assert intended fix storage design.
    Preserves original applied attempt and outcome.
L3: migrate_copy legacy synthetic applied tracking-param URL; then normalized intake
    must not bypass prior suppressions. Source all hashes unchanged.
    Includes two pre-existing legacy duplicates (earlier pending, later applied)
    so choosing oldest doesn't bypass submitted history. Uses actual existing ORM fields.
"""
import hashlib
from datetime import datetime
import pytest

from job_applier.database import DatabaseManager, Job, ApplicationAttempt
from job_applier.managed import Service, ProtocolError
from job_applier.managed_data import migrate_copy


def accept(s, r, worker="worker", session_id="session-1"):
    return s.accept_run(
        r["id"],
        worker_id=worker,
        session_id=session_id,
        capabilities={
            "protocol": 1,
            "skill_version": "test-skill",
            "browser_profile": r["browser_profile"],
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )


def test_L2_enrich_identity_alternate_url_dedupe_or_global_suppression(tmp_path):
    """L2: Intake URL A no verified identity; record fixture applied via existing test

    helper or operator reconcile fixture (not real submission). Enrich same A with
    verified namespace N + req R; then alternateURL B same N/R must dedupe or
    global suppression reject executing it. Don't assert intended fix storage design.
    Preserve original applied attempt/outcome.
    """
    s = Service.create(tmp_path / "identity.db", instance_id="test-identity")
    s.identity(
        identity_id="candidate-1",
        person_key="person-1",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "fixture"}},
    )

    # 1. Intake URL A with no verified identity
    url_a = "https://careers.example.test/postings/software-engineer-101"
    job_a = s.intake(url=url_a)
    s.eligibility(job_a["id"], "ready", reason="operator initial review")

    # 2. Record fixture applied via existing test helper / reconcile fixture (not real submission)
    r_a = s.request_run(
        request_id="req-a",
        job_ids=[job_a["id"]],
        identity_id="candidate-1",
        browser_profile="fixture-browser",
    )
    accept(s, r_a)
    a = s.claim(r_a["id"], worker_id="worker")
    s.submission_intent(a["id"], worker_id="worker", fence=a["fence"], evidence="fixture intent", fixture=True)
    fin_a = s.finish(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        outcome="applied",
        evidence="fixture confirmation receipt",
        quiescent=True,
    )
    assert fin_a["outcome"] == "applied"
    assert s.job(job_a["id"])["status"] == "applied"

    # 3. Enrich same A with verified namespace N + req R
    namespace = "greenhouse:megacorp"
    req_id = "REQ-101"
    s.intake(
        url=url_a,
        namespace=namespace,
        requisition_id=req_id,
        identity_evidence="fixture-verified-portal-id",
    )

    # 4. Intake alternate URL B with same verified namespace N + req R
    url_b = "https://boards.greenhouse.io/megacorp/jobs/101"
    job_b = s.intake(
        url=url_b,
        namespace=namespace,
        requisition_id=req_id,
        identity_evidence="fixture-verified-portal-id",
    )

    # 5. Alternate URL B same N/R must dedupe OR global suppression reject executing it
    if job_b["id"] == job_a["id"]:
        # Intake deduped directly to Job A: requesting a run must reject as already applied
        with pytest.raises(ProtocolError, match="already_applied"):
            s.request_run(
                request_id="req-b-attempt",
                job_ids=[job_b["id"]],
                identity_id="candidate-1",
                browser_profile="fixture-browser",
            )
    else:
        # Separate row created: executing it must be rejected by global suppression
        s.eligibility(job_b["id"], "ready", reason="operator approval for alternate url")
        executed = False
        try:
            r_b = s.request_run(
                request_id="req-b-attempt",
                job_ids=[job_b["id"]],
                identity_id="candidate-1",
                browser_profile="fixture-browser",
            )
            accept(s, r_b)
            s.claim(r_b["id"], worker_id="worker")
            executed = True
        except ProtocolError:
            executed = False

        assert not executed, "Alternate URL B with same verified identity (namespace+req) must be rejected by global suppression"

    # 6. Preserve original applied attempt and outcome
    assert s.job(job_a["id"])["status"] == "applied"
    attempt_a = s.attempt(a["id"])
    assert attempt_a["outcome"] == "applied"
    assert attempt_a["completed_at"] is not None


def test_L3_migrate_copy_tracking_param_and_duplicate_suppression(tmp_path):
    """L3: migrate_copy legacy synthetic applied tracking-param URL;

    then normalized intake must not bypass prior suppressions. Source all hashes unchanged.
    Also include two pre-existing legacy duplicates (earlier pending, later applied)
    so choosing oldest doesn't bypass submitted history. Use actual existing ORM fields.
    """
    source_path = tmp_path / "legacy_source.db"
    mgr = DatabaseManager(str(source_path))
    session = mgr.get_session()

    # 1. Legacy synthetic applied job with tracking parameters in URL
    job_applied = Job(
        id="legacy-applied-job",
        url="https://careers.example.test/jobs/engineer?utm_source=linkedin&utm_campaign=spring2025",
        title="Software Engineer",
        company="TechCorp",
        status="applied",
        created_at=datetime(2025, 5, 1, 10, 0, 0),
        completed_at=datetime(2025, 5, 1, 10, 30, 0),
    )
    session.add(job_applied)
    attempt_applied = ApplicationAttempt(
        job_id="legacy-applied-job",
        platform="greenhouse",
        outcome="applied",
        evidence="legacy_confirmation_receipt",
        started_at=datetime(2025, 5, 1, 10, 0, 0),
        completed_at=datetime(2025, 5, 1, 10, 30, 0),
    )
    session.add(attempt_applied)

    # 2. Two pre-existing legacy duplicates (earlier pending, later applied)
    # Both canonicalize to https://careers.example.test/jobs/data-lead
    dup_earlier_pending = Job(
        id="legacy-dup-earlier",
        url="https://careers.example.test/jobs/data-lead?utm_source=indeed",
        title="Lead Data Scientist",
        company="DataCo",
        status="queued",
        created_at=datetime(2025, 5, 10, 8, 0, 0),
        updated_at=datetime(2025, 5, 10, 8, 0, 0),
    )
    session.add(dup_earlier_pending)

    dup_later_applied = Job(
        id="legacy-dup-later",
        url="https://careers.example.test/jobs/data-lead?utm_source=referral&rx_campaign=direct",
        title="Lead Data Scientist",
        company="DataCo",
        status="applied",
        created_at=datetime(2025, 5, 12, 14, 0, 0),
        completed_at=datetime(2025, 5, 12, 14, 45, 0),
        updated_at=datetime(2025, 5, 12, 14, 45, 0),
    )
    session.add(dup_later_applied)
    attempt_dup_later = ApplicationAttempt(
        job_id="legacy-dup-later",
        platform="greenhouse",
        outcome="applied",
        evidence="legacy_referral_confirmation",
        started_at=datetime(2025, 5, 12, 14, 0, 0),
        completed_at=datetime(2025, 5, 12, 14, 45, 0),
    )
    session.add(attempt_dup_later)

    session.commit()
    session.close()
    mgr.close()

    source_bytes = source_path.read_bytes()
    expected_source_hash = hashlib.sha256(source_bytes).hexdigest()

    dest_path = tmp_path / "migrated_dest.db"
    migrate_copy(
        source_path,
        dest_path,
        instance_id="instance-migrated",
        expected_source_sha256=expected_source_hash,
    )

    # Source hash must remain completely unchanged
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == expected_source_hash

    s = Service(dest_path, instance_id="instance-migrated")
    s.identity(
        identity_id="candidate-1",
        person_key="person-1",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "fixture"}},
    )

    # 3. Normalized intake of tracking-param URL must not bypass prior suppressions
    norm_job_1 = s.intake(url="https://careers.example.test/jobs/engineer")
    with pytest.raises(ProtocolError, match="already_applied"):
        s.retry(norm_job_1["id"])

    with pytest.raises(ProtocolError, match="already_applied"):
        s.request_run(
            request_id="req-norm-1",
            job_ids=[norm_job_1["id"]],
            identity_id="candidate-1",
            browser_profile="fixture-browser",
        )

    # 4. Normalized intake of duplicate job must not bypass submitted history
    norm_dup_job = s.intake(url="https://careers.example.test/jobs/data-lead")

    # Retry must reject as already applied
    with pytest.raises(ProtocolError, match="already_applied"):
        s.retry(norm_dup_job["id"])

    # Executing the duplicate via request_run / claim must be rejected as already applied
    suppressed = True
    try:
        s.eligibility(norm_dup_job["id"], "ready", reason="operator approval")
        r = s.request_run(
            request_id="req-dup-test",
            job_ids=[norm_dup_job["id"]],
            identity_id="candidate-1",
            browser_profile="fixture-browser",
        )
        accept(s, r)
        s.claim(r["id"], worker_id="worker")
        suppressed = False
    except ProtocolError:
        suppressed = True

    assert suppressed, (
        "Normalized intake of duplicate job bypassed submitted history of the later applied duplicate"
    )
