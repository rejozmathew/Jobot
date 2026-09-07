"""Contract tests for Service operator context, versions, and runtime history exposure.

Expected RED: Primary implements production features.

Contracts covered (<= 3 concise synthetic Service tests):
1. test_service_health_exposes_versions_and_safe_metadata:
   Service.health must expose code_version (actual Git revision when available,
   otherwise explicit unknown), canonical_skill_hash (actual staged skill SHA or
   unknown), schema_version, and instance/DB path; without leaking secrets.
2. test_service_view_current_run_focused_context_and_uncertainty:
   Service.view(run_id) current_run includes focused_context for active attempt or
   explicitly labeled last completed attempt: job company/title/url, current page/activity
   from latest structured phase/tool milestone, latest unresolved issue, worker
   skill/model/provider version metadata, and snapshot settings hash.
   Must not label last-completed as currently running. Run timestamps retained.
   Persisted uncertain_duration / backward wall-clock uncertainty must be visible.
3. test_service_view_exposes_targets_budget_extensions_and_lesson_history:
   Existing target/budget-extension records and lesson verification/failure history
   already exist and should be exposed, not hidden behind fake counts.
   Assert actual source-derived values/relations, not copied commit strings.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import subprocess
import pytest

from job_applier.managed import Service, ProtocolError

REPO_ROOT = Path(__file__).resolve().parents[2]


def _get_git_revision() -> str:
    """Retrieve actual Git revision HEAD if available, else 'unknown'."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        out = res.stdout.strip()
        return out if out else "unknown"
    except Exception:
        return "unknown"


def _get_canonical_skill_hash() -> str:
    """Compute actual SHA-256 of canonical staged skill file if present, else 'unknown'."""
    skill_file = REPO_ROOT / "skills" / "productivity" / "job-apply" / "SKILL.md"
    if skill_file.is_file():
        return hashlib.sha256(skill_file.read_bytes()).hexdigest()
    return "unknown"


def test_service_health_exposes_versions_and_safe_metadata(tmp_path):
    """1. Service.health must expose code_version, canonical_skill_hash, schema_version, and DB path without secrets."""
    db_path = tmp_path / "jobs_health.db"
    s = Service.create(db_path, instance_id="op-test-instance")

    expected_git_rev = _get_git_revision()
    expected_skill_sha = _get_canonical_skill_hash()

    with s.tx() as db:
        expected_schema_version = db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]

    health = s.health()
    assert isinstance(health, dict), "health() must return a dictionary"

    # Must expose instance_id and db_path
    assert health.get("instance_id") == "op-test-instance"
    assert health.get("db_path") == str(s.db_path)

    # Must expose schema_version derived from schema_migrations
    assert "schema_version" in health, "health must expose schema_version"
    assert health["schema_version"] == expected_schema_version

    # Must expose code_version (actual Git revision when available, otherwise explicit 'unknown')
    assert "code_version" in health, "health must expose code_version"
    assert health["code_version"] == expected_git_rev
    assert health["code_version"] != "copied_commit_string"

    # Must expose canonical_skill_hash (actual staged skill SHA or 'unknown')
    assert "canonical_skill_hash" in health, "health must expose canonical_skill_hash"
    assert health["canonical_skill_hash"] == expected_skill_sha
    assert health["canonical_skill_hash"] != "copied_skill_hash"

    # Safe: no secrets exposed in health payload or settings
    secret_terms = ("token", "secret", "password", "key_ref", "credential_ref", "bearer")
    for key in health:
        assert not any(sec in key.lower() for sec in secret_terms), f"Leaked secret key '{key}' in health"
    if "settings" in health and isinstance(health["settings"], dict):
        for key in health["settings"]:
            assert not any(sec in key.lower() for sec in secret_terms), f"Leaked secret key '{key}' in settings"


def test_service_view_current_run_focused_context_and_uncertainty(tmp_path):
    """2. Service.view(run_id) includes focused_context for active or completed attempts and retains timestamps/uncertainty."""
    clock = [datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)]
    s = Service.create(tmp_path / "jobs_view.db", instance_id="op-test-view")
    s.now = lambda: clock[0].isoformat()

    s.identity(
        identity_id="cand-1",
        person_key="person-1",
        email="candidate@example.test",
        profile={"facts": {"work_auth": "citizen"}, "resume_ref": "asset:fixture-v1"},
    )
    job = s.intake(
        url="https://careers.example.test/jobs/staff-eng-42",
        company="Acme Corp",
        title="Staff Software Engineer",
        source_id="job-42",
    )
    s.eligibility(job["id"], "ready", reason="operator approved")

    run = s.request_run(
        request_id="run-req-42",
        job_ids=[job["id"]],
        identity_id="cand-1",
        browser_profile="fixture-profile",
    )
    worker_caps = {
        "protocol": 1,
        "skill_version": "2.4.0",
        "provider": "deepmind-gemini",
        "model": "gemini-3.8-flash",
        "browser_profile": "fixture-profile",
        "telemetry": True,
    }
    s.accept_run(
        run["id"],
        worker_id="worker-1",
        session_id="sess-1",
        capabilities=worker_caps,
    )

    # Step A: Active attempt
    attempt = s.claim(run["id"], worker_id="worker-1")
    assert attempt is not None

    clock[0] += timedelta(seconds=10)
    # Record structured phase/milestone navigation event
    s.event(
        attempt_id=attempt["id"],
        worker_id="worker-1",
        fence=attempt["fence"],
        event_id="evt-phase-nav-1",
        event_type="navigation_verified",
        observed_at=clock[0].isoformat(),
        payload={
            "phase": "application_form",
            "activity": "contact_info",
            "url": "https://careers.example.test/jobs/staff-eng-42/apply",
            "evidence": "verified",
        },
    )

    view_active = s.view(run["id"])
    cr_active = view_active.get("current_run")
    assert cr_active is not None, "view must return current_run"
    assert "focused_context" in cr_active, "current_run must include focused_context for active attempt"

    fc_active = cr_active["focused_context"]
    # Must represent active attempt
    assert fc_active.get("is_active") is True or fc_active.get("state") == "active"

    # Job company, title, url exposed
    job_info = fc_active if "company" in fc_active else fc_active.get("job", {})
    assert job_info.get("company") == "Acme Corp"
    assert job_info.get("title") == "Staff Software Engineer"
    assert job_info.get("url") == "https://careers.example.test/jobs/staff-eng-42"

    # Current page / activity from latest milestone exposed
    assert any(
        "contact_info" in str(v) or "application_form" in str(v) or "staff-eng-42/apply" in str(v)
        for v in fc_active.values()
    ), "focused_context must reflect current page or activity from latest milestone"

    # Worker metadata exposed
    worker_meta = fc_active.get("worker_metadata", fc_active)
    assert worker_meta.get("skill_version") == "2.4.0"
    assert worker_meta.get("provider") == "deepmind-gemini"
    assert worker_meta.get("model") == "gemini-3.8-flash"

    # Snapshot settings hash exposed
    assert "settings_hash" in fc_active
    assert fc_active["settings_hash"] == attempt.get("settings_hash")

    # Timestamps retained
    assert cr_active.get("requested_at") is not None
    assert attempt.get("started_at") is not None

    # Step B: Completed attempt with unresolved issue and clock uncertainty
    clock[0] += timedelta(seconds=20)
    s.finish(
        attempt["id"],
        worker_id="worker-1",
        fence=attempt["fence"],
        outcome="failed",
        evidence="unresolved_rate_limit_lockout",
    )

    # Simulate persisted uncertain_duration / backward wall-clock uncertainty
    with s.tx() as db:
        db.execute("UPDATE application_attempts SET uncertain_duration=1 WHERE id=?", (attempt["id"],))

    view_done = s.view(run["id"])
    cr_done = view_done["current_run"]
    assert "focused_context" in cr_done, "current_run must include focused_context for last completed attempt"

    fc_done = cr_done["focused_context"]
    # Must NOT label last-completed as currently running
    assert fc_done.get("is_active") is False, "Last completed attempt must not be marked active"
    assert fc_done.get("state") not in ("active", "running")

    # Must expose latest unresolved issue
    unresolved = fc_done.get("latest_unresolved_issue") or fc_done.get("unresolved_issue")
    assert unresolved == "unresolved_rate_limit_lockout"

    # Persisted uncertain_duration / clock uncertainty must be visible in view
    att_row = next(a for a in cr_done["attempts"] if a["id"] == attempt["id"])
    assert att_row.get("uncertain_duration") in (True, 1)
    assert fc_done.get("uncertain_duration") in (True, 1)


def test_service_view_exposes_targets_budget_extensions_and_lesson_history(tmp_path):
    """3. Existing target/budget-extension records and lesson verification/failure history must be exposed, not hidden behind fake counts."""
    clock = [datetime(2026, 9, 7, 14, 0, 0, tzinfo=timezone.utc)]
    s = Service.create(tmp_path / "jobs_records.db", instance_id="op-test-records")
    s.now = lambda: clock[0].isoformat()

    s.identity(
        identity_id="cand-rec",
        person_key="person-rec",
        email="rec@example.test",
        profile={"facts": {"auth": "us"}, "resume_ref": "asset:rec-v1"},
    )
    job = s.intake(
        url="https://careers.example.test/jobs/infra-100",
        company="InfraCorp",
        title="Infrastructure Lead",
        source_id="job-infra-100",
    )
    s.eligibility(job["id"], "ready", reason="operator approval")

    run = s.request_run(
        request_id="run-rec-1",
        job_ids=[job["id"]],
        identity_id="cand-rec",
        browser_profile="prof-rec",
    )
    s.accept_run(
        run["id"],
        worker_id="worker-rec",
        session_id="sess-rec",
        capabilities={
            "protocol": 1,
            "skill_version": "1.0",
            "browser_profile": "prof-rec",
            "provider": "p",
            "model": "m",
            "telemetry": True,
        },
    )
    attempt = s.claim(run["id"], worker_id="worker-rec")
    assert attempt is not None

    # 1. Bind target and record state transition history
    s.bind_target(
        attempt_id=attempt["id"],
        worker_id="worker-rec",
        fence=attempt["fence"],
        target_id="target-tab-100",
        url="https://careers.example.test/jobs/infra-100/apply",
    )
    s.target_state(
        attempt_id=attempt["id"],
        worker_id="worker-rec",
        fence=attempt["fence"],
        target_id="target-tab-100",
        state="preserved",
        evidence="operator manual review hold",
    )

    # 2. Record budget extension
    s.extend_budget(
        attempt_id=attempt["id"],
        worker_id="worker-rec",
        fence=attempt["fence"],
        seconds=60.0,
        reason="document parsing delay",
    )

    # 3. Record lesson, status verification, and failure/success outcomes
    lesson = s.lesson_observe(
        condition="captcha_wall",
        action="request_operator_intervention",
        scope={"platform": "workday"},
        expected_result="captcha_solved",
        attempt_ids=[attempt["id"]],
    )
    s.lesson_set_status(lesson["id"], "active", reason="verified by operator audit")

    clock[0] += timedelta(seconds=1)
    s.lesson_record_outcome(
        lesson["id"],
        attempt_id=attempt["id"],
        success=False,
        reason="captcha solver timeout",
    )
    clock[0] += timedelta(seconds=1)
    s.lesson_record_outcome(
        lesson["id"],
        attempt_id=attempt["id"],
        success=True,
        reason="captcha solved successfully on retry",
    )

    # 4. View assertions
    view = s.view(run["id"])
    cr = view["current_run"]

    # Target records exposed with actual values and target_history
    targets = cr.get("targets")
    assert isinstance(targets, list) and len(targets) == 1, "targets must be exposed as record list"
    t0 = targets[0]
    assert t0["target_id"] == "target-tab-100"
    assert t0["url"] == "https://careers.example.test/jobs/infra-100/apply"
    assert t0["state"] == "preserved"
    assert t0["evidence"] == "operator manual review hold"
    assert "history" in t0, "Target record must expose its target_history entries"
    assert len(t0["history"]) >= 1
    assert t0["history"][0]["state"] == "preserved"
    assert t0["history"][0]["evidence"] == "operator manual review hold"

    # Budget extension records exposed with actual values
    extensions = cr.get("budget_extensions")
    assert isinstance(extensions, list) and len(extensions) == 1, "budget_extensions must be exposed as record list"
    e0 = extensions[0]
    assert e0["attempt_id"] == attempt["id"]
    assert e0["seconds"] == 60.0
    assert e0["reason"] == "document parsing delay"

    # Lesson verification and failure history exposed
    lessons = view.get("lessons")
    assert isinstance(lessons, list) and len(lessons) >= 1
    l0 = next((l for l in lessons if l["id"] == lesson["id"]), None)
    assert l0 is not None, "Created lesson must be in view['lessons']"

    history = l0.get("history")
    assert isinstance(history, list) and len(history) >= 3, "Lesson must expose full history records"

    # Status verification in history
    assert any(
        h.get("status") == "active" and h.get("reason") == "verified by operator audit"
        for h in history
    ), "Lesson verification history must be exposed"

    # Failure outcome in history
    fail_entry = next((h for h in history if h.get("success") is False), None)
    assert fail_entry is not None, "Lesson failure history must be exposed"
    assert fail_entry.get("attempt_id") == attempt["id"]
    assert fail_entry.get("reason") == "captcha solver timeout"

    # Success outcome in history
    succ_entry = next((h for h in history if h.get("success") is True), None)
    assert succ_entry is not None, "Lesson success history must be exposed"
    assert succ_entry.get("attempt_id") == attempt["id"]
    assert succ_entry.get("reason") == "captcha solved successfully on retry"
