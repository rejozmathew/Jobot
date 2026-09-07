"""Stage 3 Review Closeout Regression Tests.

Covers findings S3-R1 through S3-R5 from artifacts/jobbot-v1-private/review-stage3/verdict.json:
- R1: Completed attempt cannot overwrite newer account state/reference. Stale novel request refused,
      registry unchanged; exact replay accepted.
- R2: bind_target must reject different identity-bearing query on same path (rx_job=A/B);
      aliases must preserve tenant path, cannot bind other tenant or arbitrary host path;
      same job binding works.
- R3: One job-bound namespace resolver preserving verified job.namespace, tenant path evidence,
      or exact verified host alias. Tenant-a operations succeed, tenant-b refused; unverified
      metadata alone not trusted.
- R4: Native PluginController milestone-to-hook path with field_context milestone, action_start
      context capture, action_end measured tool duration, field_seconds budget enforcement
      across tool names, distinct context isolation, and no raw arguments or field values persisted.
- R5: Unfinished attempt with partial successful tool span and expired browser lease reports
      uncertain timing and null completed_at on reopened Service; unfinished action also reports
      timing uncertainty.
"""

from datetime import datetime, timedelta
import json
from pathlib import Path
import uuid
import httpx
import pytest
from fastapi.testclient import TestClient

from job_applier.hermes_adapter import HermesAdapter
import job_applier.hermes_plugin as hp
from job_applier.hermes_plugin import PluginController
from job_applier.managed import ProtocolError, Service
from job_applier.managed_api import create_app
from job_applier.managed_client import Client

try:
    from test_ownership import accept, ready
except ImportError:
    from tests.jobbot_v1.test_ownership import accept, ready


OPERATOR_TOKEN = "synthetic-operator-token-jobbot-v1-32chars"
WORKER_TOKEN = "synthetic-worker-token-jobbot-v1-32chars"
WORKER_ID = "worker-stage3-review"
BASE_URL = "http://127.0.0.1:8769"


def worker_capabilities(browser_profile: str = "fixture-browser") -> dict:
    return {
        "protocol": 1,
        "skill_version": "test-skill",
        "browser_profile": browser_profile,
        "provider": "fixture-provider",
        "model": "fixture-model",
        "telemetry": True,
    }


class SwitchableTransport(httpx.BaseTransport):
    """In-process transport forwarding httpx requests to FastAPI TestClient."""

    def __init__(self, test_client: TestClient):
        self._test_client = test_client

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        result = self._test_client.request(
            request.method,
            request.url.path,
            headers=dict(request.headers),
            content=request.content,
        )
        return httpx.Response(
            result.status_code,
            headers=result.headers,
            content=result.content,
        )


def make_controller_env(tmp_path, monkeypatch, *, settings=None):
    s, r, ids = ready(tmp_path, count=2, settings=settings)
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID})
    test_client = TestClient(app, base_url=BASE_URL)
    transport = SwitchableTransport(test_client)

    real_client_cls = hp.Client
    monkeypatch.setattr(
        hp,
        "Client",
        lambda base_url, instance_id, token: real_client_cls(base_url, instance_id, token, transport=transport),
    )
    monkeypatch.setenv("JOBBOT_WORKER_TOKEN", WORKER_TOKEN)

    spool = tmp_path / f"spool_{uuid.uuid4().hex[:8]}"
    spool.mkdir(parents=True, exist_ok=True)
    cfg_file = tmp_path / f"config_{uuid.uuid4().hex[:8]}.json"
    cfg = {
        "base_url": BASE_URL,
        "instance_id": s.instance_id,
        "worker_id": WORKER_ID,
        "browser_profile": "fixture-browser",
        "skill_version": "test-skill",
        "provider": "fixture-provider",
        "model": "fixture-model",
        "worker_token_env": "JOBBOT_WORKER_TOKEN",
        "spool_dir": str(spool),
    }
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")
    return s, r, ids, PluginController(str(cfg_file)), transport


# ===========================================================================
# R1: Completed attempt cannot overwrite newer account state/reference
# ===========================================================================

def test_r1_completed_attempt_cannot_overwrite_newer_account_state_and_replay_accepted(tmp_path):
    """R1: Completed W1 attempt cannot overwrite newer W2 account state.

    Only live fenced attempt may apply NEW registry updates; exact replay of
    completed request returns cached result; late novel observation is refused.
    """
    s, r1, ids = ready(tmp_path, count=2)
    accept(s, r1, worker="worker-1")
    a1 = s.claim(r1["id"], worker_id="worker-1")

    # W1 records initial account state on attempt 1
    w1_initial = s.record_account_event(
        attempt_id=a1["id"],
        worker_id="worker-1",
        fence=a1["fence"],
        namespace="careers.example.test",
        state="created_unverified",
        credential_ref="credential:w1-cred-old",
        request_id="req-w1-initial",
        evidence="w1 initial account creation",
    )
    assert w1_initial["state"] == "created_unverified"

    # W1 completes attempt 1
    s.finish(
        a1["id"],
        worker_id="worker-1",
        fence=a1["fence"],
        outcome="ready_for_review",
        evidence="w1 completed submission",
        quiescent=True,
    )

    # W2 claims subsequent run for same candidate identity and records newer verified state
    r2 = s.request_run(
        request_id="request-w2",
        job_ids=[ids[1]],
        identity_id="candidate",
        browser_profile="fixture-browser-w2",
    )
    s.accept_run(
        r2["id"],
        worker_id="worker-2",
        session_id="session-w2",
        capabilities=worker_capabilities("fixture-browser-w2"),
    )
    a2 = s.claim(r2["id"], worker_id="worker-2")

    s.record_account_event(
        attempt_id=a2["id"],
        worker_id="worker-2",
        fence=a2["fence"],
        namespace="careers.example.test",
        state="verified",
        credential_ref="credential:w2-cred-new",
        request_id="req-w2-update",
        evidence="w2 verified credentials",
    )

    with s.tx() as db:
        acc = s._account_for_namespace(db, "careers.example.test", "candidate")
        assert acc["status"] == "verified"
        assert acc["credential_ref"] == "credential:w2-cred-new"

    # Late novel observation from completed W1 attempt MUST be refused
    with pytest.raises(ProtocolError):
        s.record_account_event(
            attempt_id=a1["id"],
            worker_id="worker-1",
            fence=a1["fence"],
            namespace="careers.example.test",
            state="created_unverified",
            credential_ref="credential:w1-cred-stale",
            request_id="req-w1-stale-novel",
            evidence="stale late observation from w1",
        )

    # Current registry entry remains untouched
    with s.tx() as db:
        acc_after = s._account_for_namespace(db, "careers.example.test", "candidate")
        assert acc_after["status"] == "verified"
        assert acc_after["credential_ref"] == "credential:w2-cred-new"

    # Exact replay of completed request must return cached result
    replay = s.record_account_event(
        attempt_id=a1["id"],
        worker_id="worker-1",
        fence=a1["fence"],
        namespace="careers.example.test",
        state="created_unverified",
        credential_ref="credential:w1-cred-old",
        request_id="req-w1-initial",
        evidence="w1 initial account creation",
    )
    assert replay["id"] == w1_initial["id"]

    # Registry remains verified after replay
    with s.tx() as db:
        acc_final = s._account_for_namespace(db, "careers.example.test", "candidate")
        assert acc_final["status"] == "verified"
        assert acc_final["credential_ref"] == "credential:w2-cred-new"


# ===========================================================================
# R2: Target binding validation on queries and aliases
# ===========================================================================

def test_r2_bind_target_rejects_different_identity_bearing_query_on_same_path(tmp_path):
    """R2: bind_target must reject different identity-bearing query on same path (rx_job=A/B)."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-r2")
    s.identity(identity_id="cand-1", person_key="person-1", email="cand@example.test", profile={"facts": {}})
    job_a = s.intake(url="https://portal.example.test/apply?rx_job=JOB_A", source_id="src-a")
    s.eligibility(job_a["id"], "ready", reason="approved")
    run = s.request_run(request_id="r1", job_ids=[job_a["id"]], identity_id="cand-1", browser_profile="prof-1")
    s.accept_run(
        run["id"],
        worker_id="worker-1",
        session_id="sess-1",
        capabilities=worker_capabilities("prof-1"),
    )
    a = s.claim(run["id"], worker_id="worker-1")

    # Same job binding works
    valid_bind = s.bind_target(
        a["id"],
        worker_id="worker-1",
        fence=a["fence"],
        target_id="target-1",
        url="https://portal.example.test/apply?rx_job=JOB_A",
    )
    assert valid_bind["target_id"] == "target-1"

    # Different identity-bearing query (rx_job=JOB_B) on same path MUST be rejected
    with pytest.raises(ProtocolError):
        s.bind_target(
            a["id"],
            worker_id="worker-1",
            fence=a["fence"],
            target_id="target-2",
            url="https://portal.example.test/apply?rx_job=JOB_B",
        )


def test_r2_bind_target_alias_must_preserve_tenant_path_and_reject_other_tenant_or_arbitrary_path(tmp_path):
    """R2: Redirect aliases must preserve tenant path, cannot bind other tenant or arbitrary host path."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-r2-alias")
    s.identity(identity_id="cand-1", person_key="person-1", email="cand@example.test", profile={"facts": {}})
    s.namespace_alias(
        alias="redirector.example.test",
        canonical="ats.example.test/tenant-a",
        verification_evidence="verified redirect evidence",
    )
    job = s.intake(url="https://redirector.example.test/jobs/123", source_id="src-123")
    s.eligibility(job["id"], "ready", reason="approved")
    run = s.request_run(request_id="r1", job_ids=[job["id"]], identity_id="cand-1", browser_profile="prof-1")
    s.accept_run(
        run["id"],
        worker_id="worker-1",
        session_id="sess-1",
        capabilities=worker_capabilities("prof-1"),
    )
    a = s.claim(run["id"], worker_id="worker-1")

    # Target binding for tenant-b or arbitrary path on ats.example.test MUST be rejected
    with pytest.raises(ProtocolError):
        s.bind_target(
            a["id"],
            worker_id="worker-1",
            fence=a["fence"],
            target_id="target-other-tenant",
            url="https://ats.example.test/tenant-b/jobs/999",
        )

    with pytest.raises(ProtocolError):
        s.bind_target(
            a["id"],
            worker_id="worker-1",
            fence=a["fence"],
            target_id="target-arbitrary",
            url="https://ats.example.test/arbitrary/path",
        )


# ===========================================================================
# R3: Job-bound namespace resolver and tenant verification
# ===========================================================================

def test_r3_job_bound_namespace_preserves_tenant_and_authorizes_tenant_a_rejects_tenant_b(tmp_path):
    """R3: Verified job.namespace preserves tenant scope for context, account events, and mail requests."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-r3")
    s.identity(identity_id="cand-1", person_key="person-1", email="cand@example.test", profile={"facts": {}})

    # Inspected intake signature: namespace, requisition_id, identity_evidence
    job = s.intake(
        url="https://ats.example.test/tenant-a/jobs/42",
        source_id="src-42",
        namespace="ats.example.test/tenant-a",
        requisition_id="42",
        identity_evidence="verified ATS job record",

    )
    assert job["namespace"] == "ats.example.test/tenant-a"

    s.eligibility(job["id"], "ready", reason="approved")
    run = s.request_run(request_id="r1", job_ids=[job["id"]], identity_id="cand-1", browser_profile="prof-1")
    s.accept_run(
        run["id"],
        worker_id="worker-1",
        session_id="sess-1",
        capabilities=worker_capabilities("prof-1"),
    )
    a = s.claim(run["id"], worker_id="worker-1")

    # 1. Application context must resolve and preserve verified tenant namespace
    ctx = s.application_context(a["id"], worker_id="worker-1")
    assert ctx["namespace"] == "ats.example.test/tenant-a"

    # 2. Account event for tenant-a must succeed
    acct = s.record_account_event(
        attempt_id=a["id"],
        worker_id="worker-1",
        fence=a["fence"],
        namespace="ats.example.test/tenant-a",
        state="created_unverified",
        credential_ref="credential:tenant-a-user",
        request_id="req-acct-tenant-a",
        evidence="created account on tenant-a portal",
    )
    assert acct["namespace"] == "ats.example.test/tenant-a"

    # 3. Mail request for tenant-a must succeed
    mail = s.request_mail_for_attempt(
        attempt_id=a["id"],
        worker_id="worker-1",
        fence=a["fence"],
        namespace="ats.example.test/tenant-a",
        purpose="email_verification",
        requested_at=s.now(),
        expected_sender="noreply@tenant-a.example.test",
    )
    assert mail["namespace"] == "ats.example.test/tenant-a"

    # 4. Account event and mail request for tenant-b MUST be refused
    with pytest.raises(ProtocolError):
        s.record_account_event(
            attempt_id=a["id"],
            worker_id="worker-1",
            fence=a["fence"],
            namespace="ats.example.test/tenant-b",
            state="created_unverified",
            credential_ref="credential:tenant-b-user",
            request_id="req-acct-tenant-b",
            evidence="created account on tenant-b",
        )

    with pytest.raises(ProtocolError):
        s.request_mail_for_attempt(
            attempt_id=a["id"],
            worker_id="worker-1",
            fence=a["fence"],
            namespace="ats.example.test/tenant-b",
            purpose="email_verification",
            requested_at=s.now(),
            expected_sender="noreply@tenant-b.example.test",
        )


def test_r3_unverified_metadata_alone_is_not_trusted_for_tenant_namespace(tmp_path):
    """R3: Unverified metadata alone without verified job namespace is not trusted."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-r3-unverified")
    s.identity(identity_id="cand-1", person_key="person-1", email="cand@example.test", profile={"facts": {}})

    # Unverified metadata alone
    job = s.intake(
        url="https://ats.example.test/tenant-a/jobs/99",
        source_id="src-99",
        account_namespace="ats.example.test/tenant-a",
    )
    s.eligibility(job["id"], "ready", reason="approved")
    run = s.request_run(request_id="r1", job_ids=[job["id"]], identity_id="cand-1", browser_profile="prof-1")
    s.accept_run(
        run["id"],
        worker_id="worker-1",
        session_id="sess-1",
        capabilities=worker_capabilities("prof-1"),
    )
    a = s.claim(run["id"], worker_id="worker-1")

    # Unverified metadata must not yield verified namespace in context
    ctx = s.application_context(a["id"], worker_id="worker-1")
    assert ctx["namespace"] is None

    # Account write for unverified namespace must be refused
    with pytest.raises(ProtocolError):
        s.record_account_event(
            attempt_id=a["id"],
            worker_id="worker-1",
            fence=a["fence"],
            namespace="ats.example.test/tenant-a",
            state="created_unverified",
            credential_ref="credential:unverified-user",
            request_id="req-acct-unverified",
            evidence="unverified claim",
        )


# ===========================================================================
# R4: Native PluginController field_context milestone and budget enforcement
# ===========================================================================

def test_r4_field_context_milestone_and_budget_enforcement(tmp_path, monkeypatch):
    """R4: field_context semantic milestone, action context capture, and budget enforcement across tools."""
    s, r, ids, ctrl, transport = make_controller_env(
        tmp_path,
        monkeypatch,
        settings={"field_seconds": 5, "attempt_seconds": 300, "no_progress_seconds": 300},
    )
    sid = "session-field-context"
    try:
        ctrl.route(
            "post_api_request",
            session_id=sid,
            provider="fixture-provider",
            model="fixture-model",
            response_model="fixture-model",
        )
        ctrl.handle({"operation": "accept", "parameters": {"run_id": r["id"]}}, session_id=sid)
        claim_res = json.loads(ctrl.handle({"operation": "next"}, session_id=sid))
        attempt_id = claim_res["id"]

        # 1. Emit field_context semantic milestone with page/field/category/evidence
        milestone_res = json.loads(ctrl.handle(
            {
                "operation": "milestone",
                "parameters": {
                    "event_type": "field_context",
                    "observed_at": s.now(),
                    "payload": {
                        "page": "app_page_1",
                        "field": "phone",
                        "category": "repair",
                        "evidence": "phone validation error displayed",
                    },
                },
            },
            session_id=sid,
        ))
        assert milestone_res.get("status") != "error", f"field_context milestone rejected: {milestone_res}"

        # 2. Action start captures current field_context; action_end records failure with measured duration
        pre1 = ctrl.route(
            "pre_tool_call",
            tool_name="click",
            args={"selector": "#phone-input", "raw_secret": "SENSITIVE_ARG_REDACT"},
            session_id=sid,
            tool_call_id="call-click-1",
        )
        assert pre1 is None

        ctrl.route(
            "post_tool_call",
            tool_name="click",
            args={"selector": "#phone-input", "raw_secret": "SENSITIVE_ARG_REDACT"},
            result={"error": "element intercepted"},
            session_id=sid,
            tool_call_id="call-click-1",
            duration_ms=6000,
            status="failed",
        )

        # 3. Next browser writer for SAME semantic context (regardless of tool name) MUST exceed budget
        block_res = ctrl.route(
            "pre_tool_call",
            tool_name="type_text",
            args={"selector": "#phone-input", "value": "5551234"},
            session_id=sid,
            tool_call_id="call-type-2",
        )
        assert block_res is not None
        assert block_res.get("action") == "block"
        assert "semantic_field_budget_exceeded" in block_res.get("message", "")

        # 4. Different field context does not charge the wrong field
        ctrl.handle(
            {
                "operation": "milestone",
                "parameters": {
                    "event_type": "field_context",
                    "observed_at": s.now(),
                    "payload": {
                        "page": "app_page_1",
                        "field": "email",
                        "category": "input",
                        "evidence": "filling email field",
                    },
                },
            },
            session_id=sid,
        )
        diff_field_res = ctrl.route(
            "pre_tool_call",
            tool_name="type_text",
            args={"selector": "#email-input", "value": "cand@test.com"},
            session_id=sid,
            tool_call_id="call-type-3",
        )
        assert diff_field_res is None

        # 5. No raw arguments or field values persisted
        with s.tx() as db:
            for table in ("managed_events", "managed_actions"):
                for row in db.execute(f"SELECT * FROM {table} WHERE attempt_id=?", (attempt_id,)).fetchall():
                    row_text = json.dumps(dict(row))
                    assert "SENSITIVE_ARG_REDACT" not in row_text
                    assert "5551234" not in row_text
    finally:
        ctrl.close()


# ===========================================================================
# R5: Timing uncertainty on crashed attempts and unfinished actions
# ===========================================================================

def test_r5_unfinished_attempt_with_expired_lease_reports_uncertainty_and_null_completed_at(tmp_path):
    """R5: Expired browser lease on unfinished attempt reports uncertain timing and null completed_at."""
    current_time = [datetime.fromisoformat("2026-09-07T12:00:00+00:00")]

    def now_fn():
        return current_time[0].isoformat()

    s = Service.create(tmp_path / "jobs.db", instance_id="test-r5", settings={"lease_seconds": 60})
    s.now = now_fn
    s.identity(identity_id="cand-1", person_key="person-1", email="cand@example.test", profile={"facts": {}})
    job = s.intake(url="https://careers.example.test/jobs/r5", source_id="src-r5")
    s.eligibility(job["id"], "ready", reason="approved")
    run = s.request_run(request_id="r1", job_ids=[job["id"]], identity_id="cand-1", browser_profile="prof-1")
    s.accept_run(
        run["id"],
        worker_id="worker-1",
        session_id="sess-1",
        capabilities=worker_capabilities("prof-1"),
    )
    a = s.claim(run["id"], worker_id="worker-1")

    # Record partial successful tool span
    s.action_start(a["id"], worker_id="worker-1", fence=a["fence"], action_id="act-span-1", tool_name="click", writes_browser=True)
    current_time[0] += timedelta(seconds=5)
    s.action_end(a["id"], worker_id="worker-1", fence=a["fence"], action_id="act-span-1", status="success", duration_seconds=5.0)

    # Worker crashes/stops without terminal outcome event; advance clock past lease expiry (60s)
    current_time[0] += timedelta(seconds=120)

    # Reopen Service
    s2 = Service(s.db_path, now_fn=now_fn)

    # attempt_report timing.uncertainty must be true; completed_at must stay null
    rep = s2.attempt_report(a["id"])
    assert rep["attempt"]["completed_at"] is None
    assert rep["timing"]["uncertainty"] is True

    # Operator view uncertain_duration must be true
    view = s2.view(run["id"])
    curr = view["current_run"]
    assert curr is not None
    assert curr["focused_context"]["uncertain_duration"] is True
    assert curr["attempts"][0]["uncertain_duration"] is True


def test_r5_unfinished_action_reports_timing_uncertainty(tmp_path):
    """R5: Unfinished action in managed_actions causes timing uncertainty in report and view."""
    current_time = [datetime.fromisoformat("2026-09-07T12:00:00+00:00")]

    def now_fn():
        return current_time[0].isoformat()

    s = Service.create(tmp_path / "jobs.db", instance_id="test-r5-action", settings={"lease_seconds": 300})
    s.now = now_fn
    s.identity(identity_id="cand-1", person_key="person-1", email="cand@example.test", profile={"facts": {}})
    job = s.intake(url="https://careers.example.test/jobs/r5-act", source_id="src-r5-act")
    s.eligibility(job["id"], "ready", reason="approved")
    run = s.request_run(request_id="r1", job_ids=[job["id"]], identity_id="cand-1", browser_profile="prof-1")
    s.accept_run(
        run["id"],
        worker_id="worker-1",
        session_id="sess-1",
        capabilities=worker_capabilities("prof-1"),
    )
    a = s.claim(run["id"], worker_id="worker-1")

    # Start action without ending it
    s.action_start(a["id"], worker_id="worker-1", fence=a["fence"], action_id="act-hanging", tool_name="type_text", writes_browser=True)

    rep = s.attempt_report(a["id"])
    assert rep["timing"]["uncertainty"] is True

    view = s.view(run["id"])
    assert view["current_run"]["focused_context"]["uncertain_duration"] is True
