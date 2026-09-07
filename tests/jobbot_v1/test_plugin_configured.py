"""Configured plugin controller and thin-client import regression tests."""
import json
from pathlib import Path
import subprocess
import sys
from fastapi.testclient import TestClient
import httpx
import pytest

from job_applier.managed_api import create_app
import job_applier.hermes_plugin as hp
from job_applier.hermes_plugin import PluginController
from tests.jobbot_v1.test_ownership import ready

OPERATOR_TOKEN = "synthetic-operator-token-jobbot-v1-32chars"
WORKER_TOKEN = "synthetic-worker-token-jobbot-v1-32chars"
WORKER_ID = "worker-1"
BASE_URL = "http://127.0.0.1:8769"


def _make_controller_env(tmp_path, monkeypatch, *, provider="fixture-provider", model="fixture-model"):
    s, r, ids = ready(tmp_path, count=2)
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID})
    tc = TestClient(app, base_url=BASE_URL)
    transport = httpx.MockTransport(lambda req: tc.request(req.method, req.url.path, headers=dict(req.headers), content=req.content))

    real_client_cls = hp.Client
    monkeypatch.setattr(hp, "Client", lambda base_url, instance_id, token: real_client_cls(base_url, instance_id, token, transport=transport))
    monkeypatch.setenv("JOBBOT_WORKER_TOKEN", WORKER_TOKEN)

    spool = tmp_path / "spool"
    spool.mkdir(parents=True, exist_ok=True)
    cfg_file = tmp_path / f"config_{provider}_{model}.json"
    cfg = {
        "base_url": BASE_URL,
        "instance_id": s.instance_id,
        "worker_id": WORKER_ID,
        "browser_profile": "fixture-browser",
        "skill_version": "test-skill",
        "provider": provider,
        "model": model,
        "worker_token_env": "JOBBOT_WORKER_TOKEN",
        "spool_dir": str(spool),
    }
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")
    return s, r, ids, PluginController(str(cfg_file))


def test_thin_client_import_blocked_modules_subprocess():
    """1. Thin-client import in subprocess with heavy modules blocked (expected RED)."""
    script = (
        "import sys\n"
        "for m in ('sqlalchemy', 'pydantic', 'fastapi', 'browser_use'):\n"
        "    sys.modules[m] = None\n"
        "import job_applier.hermes_plugin\n"
        "from job_applier import managed_client\n"
    )
    res = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert res.returncode == 0, f"Thin-client import failed with blocked ORM:\n{res.stderr}"


def test_original_exported_names_preserved():
    """Preserve original exported names in ordinary regression coverage."""
    import job_applier
    expected = (
        "JobApplyAgent", "JobQueue", "JobQueueDB", "QueuedJob", "AddJobRequest",
        "JobStatus", "JobRunner", "get_db_manager", "get_session",
        "migrate_from_json", "check_migration_status", "ApplicationTracker",
    )
    for name in expected:
        assert name in job_applier.__all__, f"job_applier.__all__ missing exported API '{name}'"
    for name in (
        "JobQueue", "JobQueueDB", "QueuedJob", "AddJobRequest",
        "JobStatus", "get_db_manager", "get_session",
        "migrate_from_json", "check_migration_status", "ApplicationTracker",
    ):
        assert hasattr(job_applier, name), f"job_applier missing exported attribute '{name}'"


def test_real_configured_controller_lifecycle_drives_db(tmp_path, monkeypatch):
    """2. Real configured PluginController drives Service/create_app through full DB lifecycle."""
    s, r, ids, ctrl = _make_controller_env(tmp_path, monkeypatch)
    sid = "session-1"
    try:
        ctrl.route("post_api_request", session_id=sid, model="fixture-model", provider="fixture-provider", response_model="fixture-model")

        acc = json.loads(ctrl.handle({"operation": "accept", "parameters": {"run_id": r["id"]}}, session_id=sid))
        assert acc.get("id") == r["id"]
        with s.tx() as db:
            run_row = dict(db.execute("SELECT * FROM runs WHERE id=?", (r["id"],)).fetchone())
            assert run_row["state"] == "accepted"
            assert run_row["worker_id"] == WORKER_ID

        j1 = json.loads(ctrl.handle({"operation": "next"}, session_id=sid))
        assert j1["job_id"] == ids[0]
        assert j1["identity_id"] == "candidate"
        att1 = s.attempt(j1["id"])
        assert att1["job_id"] == ids[0]
        assert att1["identity_id"] == "candidate"
        with s.tx() as db:
            lease = dict(db.execute("SELECT * FROM browser_leases WHERE profile=?", ("fixture-browser",)).fetchone())
            assert lease["state"] == "active"
            assert lease["attempt_id"] == j1["id"]

        st = json.loads(ctrl.handle({"operation": "status"}, session_id=sid))
        assert st.get("available") is True
        assert st.get("bound") is True

        strat_raw = json.loads(ctrl.handle(
            {"operation": "account_strategy", "parameters": {"namespace": "example.test/candidate"}},
            session_id=sid,
        ))
        assert 'error' not in strat_raw, strat_raw
        assert strat_raw.get('identity_id') == 'candidate'

        fin1 = json.loads(ctrl.handle(
            {"operation": "finish", "parameters": {"outcome": "ready_for_review", "evidence": "fixture-1", "quiescent": True}},
            session_id=sid,
        ))
        assert fin1.get("outcome") == "ready_for_review"
        assert s.attempt(j1["id"])["outcome"] == "ready_for_review"
        assert s.job(ids[0])["status"] == "ready_for_review"
        with s.tx() as db:
            lease = dict(db.execute("SELECT * FROM browser_leases WHERE profile=?", ("fixture-browser",)).fetchone())
            assert lease["state"] == "released"

        j2 = json.loads(ctrl.handle({"operation": "next"}, session_id=sid))
        assert j2["job_id"] == ids[1]
        assert j2["identity_id"] == "candidate"
        with s.tx() as db:
            lease = dict(db.execute("SELECT * FROM browser_leases WHERE profile=?", ("fixture-browser",)).fetchone())
            assert lease["state"] == "active"
            assert lease["attempt_id"] == j2["id"]

        ctrl.handle(
            {"operation": "finish", "parameters": {"outcome": "ready_for_review", "evidence": "fixture-2", "quiescent": True}},
            session_id=sid,
        )
        j3 = json.loads(ctrl.handle({"operation": "next"}, session_id=sid))
        assert j3 is None
        with s.tx() as db:
            run_row = dict(db.execute("SELECT * FROM runs WHERE id=?", (r["id"],)).fetchone())
            assert run_row["state"] == "completed"
            lease = dict(db.execute("SELECT * FROM browser_leases WHERE profile=?", ("fixture-browser",)).fetchone())
            assert lease["state"] == "released"
    finally:
        ctrl.close()


def test_observed_runtime_verification_and_paid_api_route_refused(tmp_path, monkeypatch):
    """3. Missing/mismatched observed runtime stays awaiting_worker; paid OpenAI API host refused."""
    s, r, ids, ctrl = _make_controller_env(tmp_path, monkeypatch, provider="openai-codex", model="gpt-6-astra")
    try:
        res_missing = json.loads(ctrl.handle({"operation": "accept", "parameters": {"run_id": r["id"]}}, session_id="session-missing"))
        assert res_missing.get("error") == "requested_runtime_not_verified"
        with s.tx() as db:
            assert db.execute("SELECT state FROM runs WHERE id=?", (r["id"],)).fetchone()[0] == "awaiting_worker"

        ctrl.route("post_api_request", session_id="session-mismatch", provider="openai-codex", model="mismatched-model", response_model="mismatched-model")
        res_mismatch = json.loads(ctrl.handle({"operation": "accept", "parameters": {"run_id": r["id"]}}, session_id="session-mismatch"))
        assert res_mismatch.get("error") == "requested_runtime_not_verified"
        with s.tx() as db:
            assert db.execute("SELECT state FROM runs WHERE id=?", (r["id"],)).fetchone()[0] == "awaiting_worker"

        ctrl.route(
            "post_api_request",
            session_id="session-astra-paid",
            provider="openai-codex",
            model="gpt-6-astra",
            response_model="gpt-6-astra",
            base_url="https://api.openai.com/v1",
        )
        res_paid = json.loads(ctrl.handle({"operation": "accept", "parameters": {"run_id": r["id"]}}, session_id="session-astra-paid"))
        assert res_paid.get("error") == "subscription_route_not_verified"
        with s.tx() as db:
            assert db.execute("SELECT state FROM runs WHERE id=?", (r["id"],)).fetchone()[0] == "awaiting_worker"

        ctrl.route(
            "post_api_request",
            session_id="session-astra-sub",
            provider="openai-codex",
            model="gpt-6-astra",
            response_model="gpt-6-astra",
            base_url="https://chatgpt.com/backend-api/codex",
        )
        res_sub = json.loads(ctrl.handle({"operation": "accept", "parameters": {"run_id": r["id"]}}, session_id="session-astra-sub"))
        assert res_sub.get("id") == r["id"]
        with s.tx() as db:
            assert db.execute("SELECT state FROM runs WHERE id=?", (r["id"],)).fetchone()[0] == "accepted"
    finally:
        ctrl.close()
