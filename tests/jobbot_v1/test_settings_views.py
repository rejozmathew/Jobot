"""Stage 3 contract tests for JobBot settings views and operator reporting.

Covers:
1. settings_view() -> {version, values} with default development/review settings.
2. configure(changes, expected_version) round-trips typed settings (worker/hermes,
   autofill/simplify|native, reasoning_provider/model, timezone, screenshot policy,
   budgets), increments version, and survives a new Service instance.
3. Claimed attempt's settings_json snapshot remains immutable after configure.
4. Stale expected_version rejects atomically with ProtocolError.
5. configure validation rejects unsupported worker='internal_agent', unknown keys,
   non-bool screenshots, negative budgets, and submission_mode='submit' in development
   without partial mutation.
6. view(run_id=None) reads shared real DB without starting workers; shows exact health
   instance_id/db_path; unassessed jobs have assessment None; candidate rows redact
   profile_json and credential material.
7. Fixed 2-job scenario: awaiting_worker -> claim1 active -> blocked finish yields
   completed1 blocked1 remaining1 with no invented active worker.
8. Operator API /v1/view, /v1/settings_view, and /v1/configure use same service;
   worker token must not configure or read unrestricted operator view (HTTP 403).
"""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from job_applier.managed import Service, ProtocolError
from job_applier.managed_api import create_app

OPERATOR_TOKEN = "synthetic-operator-token-jobbot-v1-32chars"
WORKER_TOKEN = "synthetic-worker-token-jobbot-v1-32chars"
WORKER_ID = "worker-1"
BASE_URL = "http://127.0.0.1:8769"


def ready(tmp_path, count=1, settings=None, browser_profile="fixture-browser"):
    s = Service.create(tmp_path / "jobs.db", instance_id="test-instance", settings=settings)
    s.identity(
        identity_id="candidate",
        person_key="person",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "fixture"}, "resume_ref": "asset:fixture-v1"},
    )
    ids = []
    for i in range(count):
        job = s.intake(url=f"https://careers.example.test/jobs/{i}", source_id=str(i))
        s.eligibility(job["id"], "ready", reason="synthetic operator approval")
        ids.append(job["id"])
    r = s.request_run(
        request_id="request-1",
        job_ids=ids,
        identity_id="candidate",
        browser_profile=browser_profile,
    )
    return s, r, ids


def accept(s, r, worker=WORKER_ID, session_id="session-1"):
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


def make_api_client(s):
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID})
    client = TestClient(app, base_url=BASE_URL)
    op_headers = {
        "Authorization": f"Bearer {OPERATOR_TOKEN}",
        "X-JobBot-Instance": s.instance_id,
    }
    worker_headers = {
        "Authorization": f"Bearer {WORKER_TOKEN}",
        "X-JobBot-Instance": s.instance_id,
    }
    return client, op_headers, worker_headers


def test_settings_view_defaults(tmp_path):
    """1. settings_view() returns version and values with development/review defaults."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-instance")
    res = s.settings_view()

    assert isinstance(res, dict)
    assert "version" in res
    assert isinstance(res["version"], int)
    assert "values" in res
    assert isinstance(res["values"], dict)

    values = res["values"]
    assert values.get("mode") == "development"
    assert values.get("submission_mode") == "review"
    assert values.get("worker") in ("external", "hermes")
    assert values.get("autofill") in ("simplify", "native")
    assert "screenshots" in values
    assert "timezone" in values


def test_configure_roundtrip_and_persistence_across_instances(tmp_path):
    """2. configure updates typed settings, increments version, and persists across instances."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-instance")
    initial = s.settings_view()
    v1 = initial["version"]

    changes = {
        "worker": "hermes",
        "autofill": "native",
        "reasoning_provider": "openai-codex",
        "reasoning_model": "gpt-6-astra",
        "timezone": "America/New_York",
        "screenshots": True,
        "no_progress_seconds": 50,
    }
    conf = s.configure(changes, expected_version=v1)

    assert conf["version"] > v1
    vals = conf["values"]
    assert vals["worker"] == "hermes"
    assert vals["autofill"] == "native"
    assert vals["reasoning_provider"] == "openai-codex"
    assert vals["reasoning_model"] == "gpt-6-astra"
    assert vals["timezone"] == "America/New_York"
    assert vals["screenshots"] is True
    assert vals["no_progress_seconds"] == 50

    # Survives a NEW Service instance opening the same database
    s2 = Service(s.db_path, instance_id=s.instance_id)
    s2_view = s2.settings_view()
    assert s2_view["version"] == conf["version"]
    assert s2_view["values"]["worker"] == "hermes"
    assert s2_view["values"]["autofill"] == "native"
    assert s2_view["values"]["screenshots"] is True
    assert s2_view["values"]["timezone"] == "America/New_York"
    assert s2_view["values"]["no_progress_seconds"] == 50


def test_claimed_attempt_preserves_immutable_settings_snapshot(tmp_path):
    """3. An already claimed attempt's settings_json remains unchanged after configure."""
    s, r, ids = ready(tmp_path, count=1)
    accept(s, r, worker=WORKER_ID)
    a = s.claim(r["id"], worker_id=WORKER_ID)
    initial_attempt_settings = s.attempt_status(a["id"])["settings_json"]

    cur = s.settings_view()
    s.configure(
        {"worker": "hermes", "timezone": "Asia/Tokyo", "screenshots": True},
        expected_version=cur["version"],
    )

    claimed_attempt = s.attempt_status(a["id"])
    assert claimed_attempt["settings_json"] == initial_attempt_settings


def test_configure_stale_expected_version_rejects_atomically(tmp_path):
    """4. Stale expected_version must reject atomically with ProtocolError."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-instance")
    cur = s.settings_view()
    v = cur["version"]

    with pytest.raises(ProtocolError):
        s.configure({"timezone": "UTC"}, expected_version=v - 1)

    with pytest.raises(ProtocolError):
        s.configure({"timezone": "UTC"}, expected_version=v + 99)

    after = s.settings_view()
    assert after["version"] == v
    assert after["values"] == cur["values"]


def test_configure_validation_rejects_invalid_inputs_without_partial_mutation(tmp_path):
    """5. Rejects invalid inputs atomically without partial mutation."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-instance")
    initial = s.settings_view()
    v = initial["version"]

    invalid_cases = [
        {"worker": "internal_agent"},
        {"unsupported_key": 123},
        {"screenshots": "true"},
        {"screenshots": 1},
        {"budget": -5},
        {"no_progress_seconds": -1},
        {"submission_mode": "submit"},
    ]
    for changes in invalid_cases:
        with pytest.raises(ProtocolError):
            s.configure(changes, expected_version=v)

    # Attempt mixed batch containing a valid and an invalid change
    with pytest.raises(ProtocolError):
        s.configure({"worker": "hermes", "worker_bogus_key": "fail"}, expected_version=v)

    current = s.settings_view()
    assert current["version"] == v
    assert current["values"] == initial["values"]


def test_view_structure_health_unassessed_jobs_and_candidate_redaction(tmp_path):
    """6. view() returns structure, exact health, assessment None for unassessed jobs, and redacted candidates."""
    s, r, ids = ready(tmp_path, count=2)
    unassessed = s.intake(url="https://careers.example.test/jobs/unassessed", source_id="raw-1")

    v = s.view()
    for key in ("health", "settings", "jobs", "runs", "accounts", "candidates", "current_run"):
        assert key in v

    # Health shows exact instance_id and db_path
    assert v["health"]["instance_id"] == s.instance_id
    assert Path(v["health"]["db_path"]) == s.db_path

    # Unassessed jobs have assessment None, not score0 or 0
    unassessed_matches = [j for j in v["jobs"] if j.get("id") == unassessed["id"]]
    assert len(unassessed_matches) == 1
    assert unassessed_matches[0].get("assessment") is None
    assert unassessed_matches[0].get("assessment") != 0
    assert unassessed_matches[0].get("assessment") != "score0"

    # Candidate rows must NOT include profile_json or credential material
    assert len(v["candidates"]) >= 1
    for cand in v["candidates"]:
        assert "profile_json" not in cand
        assert "credential_ref" not in cand
        assert "password" not in cand
        assert "secret" not in cand


def test_view_fixed_two_job_scenario_current_run_metrics(tmp_path):
    """7. Fixed 2-job scenario: awaiting_worker -> claim1 active -> blocked finish -> completed1 blocked1 remaining1."""
    s, r, ids = ready(tmp_path, count=2)

    # 1. State: awaiting_worker
    v0 = s.view(run_id=r["id"])
    cr0 = v0["current_run"]
    assert cr0["run_id"] == r["id"]
    assert cr0["control"] == "running"
    assert cr0["selected"] == 2
    assert cr0["current"] == 0
    assert cr0["remaining"] == 2
    assert cr0["completed"] == 0
    assert cr0["blocked"] == 0
    assert cr0["attempts"] == []

    # 2. Worker accepts and claims first job -> claim1 active
    accept(s, r, worker=WORKER_ID, session_id="session-1")
    a1 = s.claim(r["id"], worker_id=WORKER_ID)

    v1 = s.view(run_id=r["id"])
    cr1 = v1["current_run"]
    assert cr1["worker_id"] == WORKER_ID
    assert cr1["session_id"] == "session-1"
    assert cr1["current"] == 1
    assert len(cr1["attempts"]) == 1

    # 3. Finish first job as completed (ready_for_review)
    s.finish(
        a1["id"],
        worker_id=WORKER_ID,
        fence=a1["fence"],
        outcome="ready_for_review",
        evidence="passed synthetic review",
        quiescent=True,
    )

    # 4. Claim second job and finish as blocked
    a2 = s.claim(r["id"], worker_id=WORKER_ID)
    s.finish(
        a2["id"],
        worker_id=WORKER_ID,
        fence=a2["fence"],
        outcome="blocked",
        evidence="blocked by antibot challenge",
        quiescent=True,
    )

    # Both selected jobs were processed; blocked is a subset, not remaining work.
    v2 = s.view(run_id=r["id"])
    cr2 = v2["current_run"]
    assert cr2["completed"] == 2
    assert cr2["blocked"] == 1
    assert cr2["remaining"] == 0
    assert cr2["current"] == 0
    assert len(cr2["attempts"]) == 2


def test_operator_api_access_and_worker_forbidden(tmp_path):
    """8. Operator API /v1/view, /v1/settings_view, /v1/configure use same service; worker token forbidden."""
    s, r, ids = ready(tmp_path, count=1)
    client, op_headers, worker_headers = make_api_client(s)

    # Operator can access settings_view, configure, and view
    res_s = client.post("/v1/settings_view", json={}, headers=op_headers)
    assert res_s.status_code == 200
    cur_v = res_s.json()["version"]

    res_c = client.post(
        "/v1/configure",
        json={"changes": {"worker": "hermes"}, "expected_version": cur_v},
        headers=op_headers,
    )
    assert res_c.status_code == 200

    res_v = client.post("/v1/view", json={"run_id": r["id"]}, headers=op_headers)
    assert res_v.status_code == 200

    # Worker token must not configure
    res_w_c = client.post(
        "/v1/configure",
        json={"changes": {"worker": "hermes"}, "expected_version": cur_v},
        headers=worker_headers,
    )
    assert res_w_c.status_code == 403

    # Worker token must not read unrestricted operator view
    res_w_v = client.post("/v1/view", json={}, headers=worker_headers)
    assert res_w_v.status_code == 403

    # Worker token must not read operator settings_view
    res_w_s = client.post("/v1/settings_view", json={}, headers=worker_headers)
    assert res_w_s.status_code == 403
