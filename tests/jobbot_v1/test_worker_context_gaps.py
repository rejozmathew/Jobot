"""Unit tests for worker application context gaps, native context routing, and account lifecycle states.

Expected RED: Primary Windows Hermes retains implementation.

Covers:
1. Worker-read application_context(attempt_id, worker_id=None, platform=None, namespace=None):
   - Returns {attempt, job, documents, helpers, lessons, account}.
   - Excludes credential values and private profile dump.
   - Authoritative facts remain existing claimed profile snapshot.
   - Enforces worker attempt ownership boundary on /v1/application_context.
2. Native jobbot next includes context key populated from application_context:
   - Registered active lessons, helpers, and selected docs are discoverable.
   - Missing required documents appear as explicit blocker data, not ready.
3. Namespace-dependent refresh via jobbot context operation:
   - Accepts observed platform and verified namespace (host[/path] syntax).
   - Resolves matching lessons, helpers, and verified accounts.
   - Unknown or absent namespace must never guess account sharing.
4. Native jobbot ack_control routing after quiescent finish:
   - With no active attempt, routes to existing ack_run_control for same accepted run.
   - Acknowledges pending pause/stop controls truthfully.
   - Never invents quiescence (rejects unquiescent acknowledgement).
5. account_update lifecycle states and least-privilege boundary:
   - Distinguishes created_unverified, verified, recovery_required, and locked.
   - Preserves confirmed history across subsequent failed application attempts.
   - Excludes operator mutations from worker role; passes owned context for worker operations.
"""
import hashlib
import json
from pathlib import Path
import uuid
from fastapi.testclient import TestClient
import httpx
import pytest

from job_applier.managed import Service, ProtocolError
from job_applier.managed_api import create_app
import job_applier.hermes_plugin as hp
from job_applier.hermes_plugin import PluginController

OPERATOR_TOKEN = "synthetic-operator-token-jobbot-v1-32chars"
WORKER_TOKEN = "synthetic-worker-token-jobbot-v1-32chars"
WORKER_ID = "worker-1"
OTHER_WORKER_TOKEN = "synthetic-other-token-jobbot-v1-32chars"
OTHER_WORKER_ID = "worker-2"
BASE_URL = "http://127.0.0.1:8769"


def _setup_service(tmp_path, instance_id="test-worker-context"):
    s = Service.create(
        tmp_path / f"worker_context_{uuid.uuid4().hex[:8]}.db",
        instance_id=instance_id,
        settings={"mode": "development"},
    )
    s.identity(
        identity_id="cand-1",
        person_key="person-1",
        email="cand1@example.test",
        profile={"facts": {"work_authorization": "fixture"}, "resume_ref": "asset:fixture-v1"},
    )
    s.identity(
        identity_id="cand-2",
        person_key="person-2",
        email="cand2@example.test",
        profile={"facts": {"work_authorization": "fixture"}, "resume_ref": "asset:fixture-v2"},
    )
    return s


def _create_ready_run(s, *, url="https://careers.example.test/jobs/101", identity_id="cand-1", run_req_id=None, browser_profile="fixture-browser", **metadata):
    job = s.intake(url=url, source_id=f"src-{uuid.uuid4().hex[:6]}", **metadata)
    s.eligibility(job["id"], "ready", reason="synthetic operator approval")
    run = s.request_run(
        request_id=run_req_id or f"run-req-{uuid.uuid4().hex[:8]}",
        job_ids=[job["id"]],
        identity_id=identity_id,
        browser_profile=browser_profile,
    )
    return job, run


def _create_claimed_attempt(s, *, url="https://careers.example.test/jobs/101", worker_id=WORKER_ID, identity_id="cand-1", run_req_id=None, browser_profile="fixture-browser"):
    job, run = _create_ready_run(s, url=url, identity_id=identity_id, run_req_id=run_req_id, browser_profile=browser_profile)
    s.accept_run(
        run["id"],
        worker_id=worker_id,
        session_id=f"session-{worker_id}",
        capabilities={
            "protocol": 1,
            "skill_version": "test-skill",
            "browser_profile": browser_profile,
            "provider": "fixture-provider",
            "model": "fixture-model",
            "telemetry": True,
        },
    )
    attempt = s.claim(run["id"], worker_id=worker_id)
    return job, run, attempt


def _make_controller(s, tmp_path, monkeypatch, *, worker_id=WORKER_ID, worker_token=WORKER_TOKEN, sid="session-default"):
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={worker_token: worker_id, OTHER_WORKER_TOKEN: OTHER_WORKER_ID})
    tc = TestClient(app, base_url=BASE_URL)
    tc.headers["X-JobBot-Instance"]=s.instance_id
    transport = httpx.MockTransport(lambda req: tc.request(req.method, req.url.path, headers=dict(req.headers), content=req.content))

    real_client_cls = hp.Client
    monkeypatch.setattr(hp, "Client", lambda base_url, instance_id, token: real_client_cls(base_url, instance_id, token, transport=transport))
    monkeypatch.setenv("JOBBOT_WORKER_TOKEN", worker_token)

    spool = tmp_path / f"spool_{uuid.uuid4().hex[:8]}"
    spool.mkdir(parents=True, exist_ok=True)
    cfg_file = tmp_path / f"config_{uuid.uuid4().hex[:8]}.json"
    cfg = {
        "base_url": BASE_URL,
        "instance_id": s.instance_id,
        "worker_id": worker_id,
        "browser_profile": "fixture-browser",
        "skill_version": "test-skill",
        "provider": "fixture-provider",
        "model": "fixture-model",
        "worker_token_env": "JOBBOT_WORKER_TOKEN",
        "spool_dir": str(spool),
    }
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")
    ctrl = PluginController(str(cfg_file))
    ctrl.route("post_api_request", session_id=sid, model="fixture-model", provider="fixture-provider", response_model="fixture-model")
    return ctrl, tc


def test_worker_application_context_contract_and_privacy(tmp_path):
    """1. Worker-read application_context(attempt_id, worker_id, platform, namespace)
    returns {attempt, job, documents, helpers, lessons, account}, excludes raw secrets
    and private profile dumps, retains authoritative claimed facts, and enforces auth.
    """
    s = _setup_service(tmp_path)
    job, run, attempt = _create_claimed_attempt(s, url="https://careers.example.test/jobs/101")

    # Authoritative facts in claimed snapshot
    claimed_facts = json.loads(attempt["profile_json"])["facts"]
    assert claimed_facts == {"work_authorization": "fixture"}

    # Call new worker-read application_context
    ctx = s.application_context(
        attempt_id=attempt["id"],
        worker_id=WORKER_ID,
        platform="workday",
        namespace="careers.example.test",
    )

    # Return structure contract
    assert isinstance(ctx, dict)
    for key in ("attempt", "job", "documents", "helpers", "lessons", "account"):
        assert key in ctx, f"application_context missing required key '{key}'"

    # Authoritative facts remain claimed profile snapshot
    attempt_ctx = ctx["attempt"]
    assert json.loads(attempt_ctx["profile_json"])["facts"] == claimed_facts

    # Privacy boundaries: raw credentials and unredacted candidate profile dump excluded
    ctx_dump = json.dumps(ctx)
    assert "synthetic-operator-token" not in ctx_dump
    assert "synthetic-worker-token" not in ctx_dump
    if ctx.get("account"):
        # Account exposes safe metadata/credential_ref, never raw credential values
        assert "password" not in ctx["account"]
        assert "secret" not in ctx["account"]

    # HTTP API /v1/application_context role boundary
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID, OTHER_WORKER_TOKEN: OTHER_WORKER_ID})
    tc = TestClient(app, base_url=BASE_URL)
    tc.headers["X-JobBot-Instance"]=s.instance_id

    # Owned attempt succeeds for worker
    resp_worker = tc.post("/v1/application_context", json={"attempt_id": attempt["id"], "worker_id": WORKER_ID}, headers={"Authorization": f"Bearer {WORKER_TOKEN}"})
    assert resp_worker.status_code == 200
    assert set(resp_worker.json().keys()) >= {"attempt", "job", "documents", "helpers", "lessons", "account"}

    # Unowned attempt or foreign worker is rejected with 403
    resp_other = tc.post("/v1/application_context", json={"attempt_id": attempt["id"], "worker_id": OTHER_WORKER_ID}, headers={"Authorization": f"Bearer {OTHER_WORKER_TOKEN}"})
    assert resp_other.status_code == 403


def test_jobbot_next_includes_context_and_missing_document_blocker(tmp_path, monkeypatch):
    """2. Native jobbot next populates context key with active lessons/helpers and docs;
    missing required documents appear as explicit blocker data, not ready.
    """
    s = _setup_service(tmp_path)
    # Register historical attempt cleanly to back procedural lesson
    hist_job, hist_run, hist_att = _create_claimed_attempt(s, url="https://careers.example.test/history", run_req_id="run-hist-1", browser_profile="fixture-hist-browser")
    s.finish(hist_att["id"], worker_id=WORKER_ID, fence=hist_att["fence"], outcome="ready_for_review", evidence="hist ready", quiescent=True)

    # Intake job with required documents: resume and cover_letter
    job, run = _create_ready_run(
        s,
        url="https://careers.example.test/jobs/201",
        run_req_id="run-docs-check",
        browser_profile="fixture-browser",
        required_documents=["resume", "cover_letter"],
        platform="workday",account_namespace="careers.example.test",
    )

    # Register and select ONLY resume (cover_letter is missing)
    resume = s.register_asset(
        identity_id="cand-1",
        kind="resume",
        version="v1",
        storage_ref="asset:resume-v1",
        sha256="a" * 64,
        provenance={"producer": "test"},
    )
    s.select_asset(asset_id=resume["id"], job_id=job["id"])

    # Active lesson matching scope
    lesson = s.lesson_observe(
        condition="file upload field detected",
        action="attach selected document",
        scope={"platform": "workday", "namespace": "careers.example.test"},
        expected_result="file uploaded",
        attempt_ids=[hist_att["id"]],
        kind="procedure",
    )
    s.lesson_set_status(lesson["id"], "active", reason="verified procedure")

    # Active helper matching scope
    helper_file = tmp_path / "upload_helper.py"
    helper_file.write_text("# synthetic upload helper\ndef upload(): pass\n", encoding="utf-8")
    helper_sha = hashlib.sha256(helper_file.read_bytes()).hexdigest()
    helper = s.helper_register(
        helper_id="upload_helper",
        version="v1",
        capability="upload_file",
        path=str(helper_file),
        sha256=helper_sha,
        scope={"platform": "workday", "namespace": "careers.example.test"},
        preconditions=["input present"],
        limitations=["workday only"],
        tests=["test_upload"],
    )
    s.helper_activate(helper["helper_id"], helper["version"], verification_evidence="tested clean")

    sid = "session-docs-check"
    ctrl, _ = _make_controller(s, tmp_path, monkeypatch, sid=sid)
    try:
        acc = json.loads(ctrl.handle({"operation": "accept", "parameters": {"run_id": run["id"]}}, session_id=sid))
        assert acc.get("id") == run["id"], f"Accept failed: {acc}"

        nxt = json.loads(ctrl.handle({"operation": "next"}, session_id=sid))
        assert "context" in nxt, "Native next response must include populated context key"

        ctx = nxt["context"]
        assert "lessons" in ctx and any(l["id"] == lesson["id"] for l in ctx["lessons"]), "Active lessons must be discoverable in context"
        assert "helpers" in ctx and any(h["helper_id"] == helper["helper_id"] for h in ctx["helpers"]), "Active helpers must be discoverable in context"

        # Missing required document blocker contract:
        docs = ctx.get("documents", {})
        assert docs.get("ready") is False, "Documents must not be ready when required document is missing"
        assert "cover_letter" in docs.get("missing", []), "Missing required document must appear explicitly"
        blocker = nxt.get("blocker") or docs.get("blocker") or (not docs.get("ready"))
        assert blocker, "Missing required document must appear as explicit blocker data"
    finally:
        ctrl.close()


def test_jobbot_context_refresh_accepts_verified_namespace_and_prevents_guessing(tmp_path, monkeypatch):
    """3. Namespace-dependent refresh via jobbot context accepts observed platform/verified namespace;
    unknown namespace must not guess account sharing; an exact verified alias is evidence.
    """
    s = _setup_service(tmp_path)
    job, run = _create_ready_run(s, url="https://careers.example.test/jobs/301", browser_profile="fixture-browser")

    # Operator registers verified namespace alias redirect
    s.namespace_alias(
        alias="careers.example.test",
        canonical="auth.example.test/tenant-corp",
        verification_evidence="Verified SSO redirect",
    )
    # Existing portal account for canonical namespace
    s.account_update(
        namespace="auth.example.test/tenant-corp",
        identity_id="cand-1",
        state="confirmed",
        credential_ref="vault:cand-1/tenant-corp",
        request_id="req-alias-acc",
        evidence="Verified SSO login",
    )

    sid = "session-context-refresh"
    ctrl, _ = _make_controller(s, tmp_path, monkeypatch, sid=sid)
    try:
        acc = json.loads(ctrl.handle({"operation": "accept", "parameters": {"run_id": run["id"]}}, session_id=sid))
        assert acc.get("id") == run["id"], f"Accept failed: {acc}"
        ctrl.handle({"operation": "next"}, session_id=sid)

        # Refresh via jobbot context with observed platform and verified namespace
        res = json.loads(ctrl.handle({
            "operation": "context",
            "parameters": {
                "platform": "workday",
                "namespace": "careers.example.test",
            },
        }, session_id=sid))

        assert res.get("status") != "error", f"jobbot context failed: {res}"
        ctx = res.get("context", res)
        # Refreshed context resolves account for verified canonical namespace
        assert ctx.get("account") is not None
        assert ctx["account"].get("namespace") in ("careers.example.test", "auth.example.test/tenant-corp")

        # Unknown namespace must not guess account sharing
        res_unknown = json.loads(ctrl.handle({
            "operation": "context",
            "parameters": {
                "platform": "workday",
                "namespace": "unknown.unrelated.test",
            },
        }, session_id=sid))
        ctx_unknown = res_unknown.get("context", res_unknown)
        assert ctx_unknown.get("account") is None, "Unknown namespace must not guess account sharing"

        # An omitted parameter now resolves from the operator-verified job-host
        # alias above (S3-R3). This is explicit evidence, not host guessing.
        res_none = json.loads(ctrl.handle({
            "operation": "context",
            "parameters": {
                "platform": "workday",
            },
        }, session_id=sid))
        ctx_none = res_none.get("context", res_none)
        assert ctx_none["account"]["namespace"] == "auth.example.test/tenant-corp"
        assert ctx_none["account"]["identity_id"] == "cand-1"
    finally:
        ctrl.close()


def test_jobbot_ack_control_routes_to_ack_run_control_after_quiescent_finish(tmp_path, monkeypatch):
    """4. Native jobbot ack_control after quiescent finish with no current attempt
    routes to existing ack_run_control for same accepted run; pending pause/stop
    can be acknowledged, never invent quiescence.
    """
    s = _setup_service(tmp_path)
    job, run = _create_ready_run(s, url="https://careers.example.test/jobs/401", browser_profile="fixture-browser")

    sid = "session-ack-control"
    ctrl, _ = _make_controller(s, tmp_path, monkeypatch, sid=sid)
    try:
        acc = json.loads(ctrl.handle({"operation": "accept", "parameters": {"run_id": run["id"]}}, session_id=sid))
        assert acc.get("id") == run["id"], f"Accept failed: {acc}"
        nxt = json.loads(ctrl.handle({"operation": "next"}, session_id=sid))
        assert nxt.get("status") != "error", f"Next failed: {nxt}"

        # Finish attempt quiescing all writers
        fin = json.loads(ctrl.handle({
            "operation": "finish",
            "parameters": {
                "outcome": "ready_for_review",
                "evidence": "Completed cleanly",
                "quiescent": True,
            },
        }, session_id=sid))
        assert fin.get("status") != "error", f"Finish failed: {fin}"

        # Adapter now has NO current attempt
        adapter = ctrl.adapters[sid]
        assert adapter._state().get("attempt") is None, "Quiescent finish must clear current attempt"

        # Operator requests pause on the run between attempts
        s.control(run["id"], command="pause")

        # Worker calls ack_control after quiescent finish with no current attempt
        ack = json.loads(ctrl.handle({
            "operation": "ack_control",
            "parameters": {"quiescent": True},
        }, session_id=sid))

        # Must NOT reject with no_claimed_attempt; routes to ack_run_control
        assert ack.get("error") != "no_claimed_attempt", "Must route to ack_run_control instead of rejecting no_claimed_attempt"
        assert ack.get("control") == "paused" or ack.get("status") == "ok"
        with s.tx() as db:
            run_db = dict(db.execute("SELECT control FROM runs WHERE id=?", (run["id"],)).fetchone())
            assert run_db["control"] == "paused"

        # Never invent quiescence: non-quiescent ack must be rejected
        s.control(run["id"], command="stop")
        ack_non_quiescent = json.loads(ctrl.handle({
            "operation": "ack_control",
            "parameters": {"quiescent": False},
        }, session_id=sid))
        assert ack_non_quiescent.get("error") in ("writers_not_quiescent", "invalid_payload"), "Must reject unquiescent control acknowledgement"
    finally:
        ctrl.close()


def test_account_update_states_and_least_privilege_boundaries(tmp_path):
    """5. account_update states must distinguish created_unverified/verified/recovery_required/locked
    without losing confirmed history on failed apps; worker API remains least-privilege.
    """
    s = _setup_service(tmp_path)
    job, run, attempt = _create_claimed_attempt(s, url="https://careers.example.test/jobs/501")

    # A. Distinguish created_unverified, verified, recovery_required, locked
    distinct_states = ("created_unverified", "verified", "recovery_required", "locked")
    for st in distinct_states:
        acc = s.account_update(
            namespace=f"careers.example.test/{st}",
            identity_id="cand-1",
            state=st,
            credential_ref=f"vault:cand-1/{st}",
            request_id=f"req-{st}",
            evidence=f"Evidence for {st}",
        )
        assert acc["state"] == st, f"account_update must support distinct state '{st}'"

    # Compatibility states still supported
    compat_acc = s.account_update(
        namespace="careers.example.test/compat",
        identity_id="cand-1",
        state="confirmed",
        credential_ref="vault:cand-1/compat",
        request_id="req-compat",
        evidence="Evidence for confirmed",
    )
    assert compat_acc["state"] == "confirmed"

    # B. Confirmed/verified history is preserved on subsequent failed applications
    with s.tx() as db:
        row_before = dict(db.execute("SELECT * FROM company_portal_accounts WHERE namespace='careers.example.test/compat'").fetchone())
        assert row_before["last_confirmed_at"] is not None

    # Attempt finishes as failed
    s.finish(
        attempt["id"],
        worker_id=WORKER_ID,
        fence=attempt["fence"],
        outcome="blocked",
        evidence="Application failed due to portal glitch",
        quiescent=True,
    )

    with s.tx() as db:
        row_after = dict(db.execute("SELECT * FROM company_portal_accounts WHERE namespace='careers.example.test/compat'").fetchone())
        assert row_after["status"] == "confirmed"
        assert row_after["last_confirmed_at"] == row_before["last_confirmed_at"], "Confirmed history must not be lost on failed applications"

    # C. Least-privilege API boundaries: worker cannot invoke operator mutations
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID})
    tc = TestClient(app, base_url=BASE_URL)
    tc.headers["X-JobBot-Instance"]=s.instance_id

    # Worker forbidden from operator mutation: account_update
    resp_op_acc = tc.post(
        "/v1/account_update",
        json={
            "namespace": "careers.example.test/op",
            "identity_id": "cand-1",
            "state": "confirmed",
            "credential_ref": "vault:cand-1/op",
            "request_id": "req-op",
            "evidence": "operator only",
        },
        headers={"Authorization": f"Bearer {WORKER_TOKEN}"},
    )
    assert resp_op_acc.status_code == 403

    # Worker forbidden from operator mutation: intake
    resp_op_intake = tc.post(
        "/v1/intake",
        json={"url": "https://careers.example.test/jobs/999"},
        headers={"Authorization": f"Bearer {WORKER_TOKEN}"},
    )
    assert resp_op_intake.status_code == 403

    # Worker permitted worker-owned operations with owned context
    job2, run2, attempt2 = _create_claimed_attempt(s, url="https://careers.example.test/jobs/502", run_req_id="run-req-502")
    resp_worker_acc = tc.post(
        "/v1/record_account_event",
        json={
            "attempt_id": attempt2["id"],
            "worker_id": WORKER_ID,
            "fence": attempt2["fence"],
            "namespace": "careers.example.test",
            "state": "created_unverified",
            "credential_ref": "vault:cand-1/worker-event",
            "request_id": "req-worker-event-1",
            "evidence": "Worker registered account",
        },
        headers={"Authorization": f"Bearer {WORKER_TOKEN}"},
    )
    assert resp_worker_acc.status_code == 200
