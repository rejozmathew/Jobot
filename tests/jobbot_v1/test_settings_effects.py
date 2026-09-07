"""Regressions for actual operational effects of settings changes.

Covers:
1. Configured reasoning_provider and reasoning_model on a new run rejects mismatching
   worker capabilities upon accept_run; matching declared capabilities are accepted.
   Previously-requested run snapshots remain unchanged without inference or credential access.
2. excluded_companies policy blocks reserving an explicitly ready matching-company
   job while retaining the job record and its intake history; another company is allowed.
3. A second Service instance created before configure sees updated values when requesting
   a new run (single effective source of truth, no stale-cache snapshot).
4. Updating lease_seconds after claim does not alter that active attempt's frozen lease
   duration on heartbeat under frozen now.
"""
from datetime import datetime
import json
import pytest

from job_applier.managed import Service, ProtocolError


def test_configured_reasoning_provider_model_enforced_on_worker_capabilities_preserving_prior_runs(tmp_path):
    """1. New run requested after reasoning_provider/model configured rejects mismatching worker capabilities.

    Matching declared capabilities are accepted. Existing previously-requested run snapshots
    remain unchanged. No inference or real credential access.
    """
    s = Service.create(tmp_path / "jobs.db", instance_id="test-instance")
    s.identity(
        identity_id="candidate",
        person_key="person",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "fixture"}, "resume_ref": "asset:fixture-v1"},
    )

    # 1. Job and run requested prior to reasoning configuration
    job0 = s.intake(url="https://careers.example.test/jobs/0", source_id="0")
    s.eligibility(job0["id"], "ready", reason="synthetic approval")
    r0 = s.request_run(
        request_id="req-0",
        job_ids=[job0["id"]],
        identity_id="candidate",
        browser_profile="fixture-browser",
    )
    r0_settings = json.loads(r0["settings_json"])
    assert r0_settings.get("reasoning_provider") is None
    assert r0_settings.get("reasoning_model") is None

    # 2. Configure reasoning_provider and reasoning_model
    cur = s.settings_view()
    s.configure(
        {"reasoning_provider": "openai-codex", "reasoning_model": "gpt-6-astra"},
        expected_version=cur["version"],
    )

    # Previously-requested run snapshot remains unchanged
    with s.tx() as db:
        r0_db = dict(db.execute("SELECT * FROM runs WHERE id=?", (r0["id"],)).fetchone())
    assert r0_db["settings_json"] == r0["settings_json"]
    assert json.loads(r0_db["settings_json"]).get("reasoning_provider") is None

    # Previously-requested run accepts worker with default/fixture capabilities matching its snapshot
    acc0 = s.accept_run(
        r0["id"],
        worker_id="worker-0",
        session_id="session-0",
        capabilities={
            "protocol": 1,
            "skill_version": "test-skill",
            "browser_profile": r0["browser_profile"],
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )
    assert acc0["state"] == "accepted"

    # 3. New run requested after reasoning configuration
    job1 = s.intake(url="https://careers.example.test/jobs/1", source_id="1")
    s.eligibility(job1["id"], "ready", reason="synthetic approval")
    r1 = s.request_run(
        request_id="req-1",
        job_ids=[job1["id"]],
        identity_id="candidate",
        browser_profile="fixture-browser",
    )
    r1_settings = json.loads(r1["settings_json"])
    assert r1_settings.get("reasoning_provider") == "openai-codex"
    assert r1_settings.get("reasoning_model") == "gpt-6-astra"

    # Mismatching worker capabilities must be rejected
    with pytest.raises(ProtocolError):
        s.accept_run(
            r1["id"],
            worker_id="worker-1",
            session_id="session-1",
            capabilities={
                "protocol": 1,
                "skill_version": "test-skill",
                "browser_profile": r1["browser_profile"],
                "provider": "fixture",
                "model": "fixture",
                "telemetry": True,
            },
        )

    with pytest.raises(ProtocolError):
        s.accept_run(
            r1["id"],
            worker_id="worker-1",
            session_id="session-1",
            capabilities={
                "protocol": 1,
                "skill_version": "test-skill",
                "browser_profile": r1["browser_profile"],
                "provider": "openai-codex",
                "model": "gpt-6-wrong",
                "telemetry": True,
            },
        )

    # Matching declared capabilities are accepted
    acc1 = s.accept_run(
        r1["id"],
        worker_id="worker-1",
        session_id="session-1",
        capabilities={
            "protocol": 1,
            "skill_version": "test-skill",
            "browser_profile": r1["browser_profile"],
            "provider": "openai-codex",
            "model": "gpt-6-astra",
            "telemetry": True,
        },
    )
    assert acc1["state"] == "accepted"
    assert acc1["worker_id"] == "worker-1"


def test_excluded_companies_policy_blocks_reserving_ready_job_retaining_history(tmp_path):
    """2. excluded_companies policy blocks reserving an explicitly ready matching-company job.

    Job record and intake history are retained; another company is allowed.
    """
    s = Service.create(tmp_path / "jobs.db", instance_id="test-instance")
    s.identity(
        identity_id="candidate",
        person_key="person",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "fixture"}, "resume_ref": "asset:fixture-v1"},
    )

    # Intake jobs for an excluded company and an allowed company
    job_excluded = s.intake(
        url="https://careers.example.test/jobs/excluded-1",
        company="BlockedCorp",
        source_id="src-ex-1",
        title="Software Engineer",
    )
    job_allowed = s.intake(
        url="https://careers.example.test/jobs/allowed-1",
        company="AllowedCorp",
        source_id="src-al-1",
        title="Software Engineer",
    )

    # Both explicitly marked ready
    s.eligibility(job_excluded["id"], "ready", reason="operator approval")
    s.eligibility(job_allowed["id"], "ready", reason="operator approval")

    # Configure excluded_companies
    cur = s.settings_view()
    s.configure({"excluded_companies": ["BlockedCorp"]}, expected_version=cur["version"])

    # Reserving the explicitly ready matching-company job must be blocked
    with pytest.raises(ProtocolError):
        s.request_run(
            request_id="req-blocked",
            job_ids=[job_excluded["id"]],
            identity_id="candidate",
            browser_profile="fixture-browser",
        )

    # Job record and history are retained intact
    retained = s.job(job_excluded["id"])
    assert retained["id"] == job_excluded["id"]
    assert retained["company"] == "BlockedCorp"
    assert retained["eligibility"] == "ready"
    sources = s.sources(job_excluded["id"])
    assert len(sources) >= 1
    assert sources[0]["source_id"] == "src-ex-1"

    # Another company is allowed to be reserved
    r_allowed = s.request_run(
        request_id="req-allowed",
        job_ids=[job_allowed["id"]],
        identity_id="candidate",
        browser_profile="fixture-browser",
    )
    assert r_allowed["id"] is not None
    assert r_allowed["state"] == "awaiting_worker"


def test_second_service_created_before_configure_sees_updated_settings_on_new_run(tmp_path):
    """3. Second Service object created before configure sees updated values on a new run.

    Uses single effective source of truth, avoiding stale-cache snapshot.
    """
    s1 = Service.create(tmp_path / "jobs.db", instance_id="test-instance")
    s1.identity(
        identity_id="candidate",
        person_key="person",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "fixture"}, "resume_ref": "asset:fixture-v1"},
    )
    job = s1.intake(url="https://careers.example.test/jobs/1", source_id="1")
    s1.eligibility(job["id"], "ready", reason="operator approval")

    # Second service instance created BEFORE configure
    s2 = Service(s1.db_path, instance_id=s1.instance_id)

    # Update settings via s1
    cur = s1.settings_view()
    s1.configure(
        {"worker": "hermes", "no_progress_seconds": 90, "autofill": "native"},
        expected_version=cur["version"],
    )

    # s2 requests a new run
    r = s2.request_run(
        request_id="req-new-run",
        job_ids=[job["id"]],
        identity_id="candidate",
        browser_profile="fixture-browser",
    )

    # s2 must not write stale settings cached during s2.__init__
    run_settings = json.loads(r["settings_json"])
    assert run_settings["worker"] == "hermes"
    assert run_settings["no_progress_seconds"] == 90
    assert run_settings["autofill"] == "native"


def test_lease_seconds_update_does_not_alter_active_attempt_lease_duration_on_heartbeat(tmp_path):
    """4. Updating lease_seconds after claim does not alter active attempt's frozen lease duration on heartbeat.

    Uses frozen now and inspects lease expiry before and after.
    """
    s = Service.create(tmp_path / "jobs.db", instance_id="test-instance")
    s.identity(
        identity_id="candidate",
        person_key="person",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "fixture"}, "resume_ref": "asset:fixture-v1"},
    )
    job = s.intake(url="https://careers.example.test/jobs/1", source_id="1")
    s.eligibility(job["id"], "ready", reason="operator approval")

    r = s.request_run(
        request_id="req-1",
        job_ids=[job["id"]],
        identity_id="candidate",
        browser_profile="fixture-browser",
    )
    s.accept_run(
        r["id"],
        worker_id="worker-1",
        session_id="session-1",
        capabilities={
            "protocol": 1,
            "skill_version": "test-skill",
            "browser_profile": r["browser_profile"],
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )

    # Freeze now
    frozen_now = "2026-09-07T12:00:00+00:00"
    s.now = lambda: frozen_now

    # Claim attempt under current settings (default lease_seconds = 60)
    a = s.claim(r["id"], worker_id="worker-1")
    assert a is not None

    with s.tx() as db:
        lease_before = dict(
            db.execute("SELECT * FROM browser_leases WHERE profile=?", (r["browser_profile"],)).fetchone()
        )
    expiry_before = lease_before["expires_at"]
    duration_before = (
        datetime.fromisoformat(expiry_before) - datetime.fromisoformat(frozen_now)
    ).total_seconds()
    assert duration_before == 60

    # Operator updates lease_seconds to 180
    cur = s.settings_view()
    s.configure({"lease_seconds": 180}, expected_version=cur["version"])

    # Worker heartbeats on the active attempt
    s.heartbeat(a["id"], worker_id="worker-1", fence=a["fence"])

    with s.tx() as db:
        lease_after = dict(
            db.execute("SELECT * FROM browser_leases WHERE profile=?", (r["browser_profile"],)).fetchone()
        )
    expiry_after = lease_after["expires_at"]
    duration_after = (
        datetime.fromisoformat(expiry_after) - datetime.fromisoformat(frozen_now)
    ).total_seconds()

    # Active attempt's lease duration must remain frozen at 60s, not expanded to 180s
    assert duration_after == duration_before
    assert expiry_after == expiry_before
