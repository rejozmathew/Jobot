"""Stage 2 Adapter and Plugin review regression tests.

Reproduces review findings from review-stage2/verdict.json:
- S2-R2: Bound managed pre_tool_call terminal background=true must explicitly block
         BEFORE spawning or creating an active writer; post_tool_call(blocked) must not
         poison subsequent foreground work. Unbound ordinary terminal behavior remains unaffected.
         Do not kill or launch real processes.
- S2-R3: While A owns a live attempt, Adapter.accept(B) must reject and preserve A local state;
         same-run idempotent accept must not drop A. finish(...quiescent=False) must preserve unsafe
         binding, so a subsequent ordinary tool cannot bypass control; normal quiescent finish then
         new run works.
- S2-R4: PluginController submission_intent passes explicit evidence and fixture flag through
         worker client on owned attempt; missing evidence refuses without recorded intent.
         Verifies actual Service.submission_intent signature.
- S2-R5: Recoverable outbox/heartbeat failure BEFORE action_start followed by native blocked post
         callback must not set permanent uncorrelated fault; after restoring transport, flush and
         a fresh foreground tool proceed with correct original attribution.
         Covers both flush-pending and heartbeat-only outage with real FastAPI TestClient and
         a faulting SwitchableTransport.
"""
import inspect
import json
from pathlib import Path
import sqlite3
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
    from test_ownership import ready
except ImportError:
    from tests.jobbot_v1.test_ownership import ready


OPERATOR_TOKEN = "synthetic-operator-token-jobbot-v1-32chars"
WORKER_TOKEN = "synthetic-worker-token-jobbot-v1-32chars"
WORKER_ID = "worker-stage2-review"
BASE_URL = "http://127.0.0.1:8769"


class SwitchableTransport(httpx.BaseTransport):
    """In-process transport forwarding httpx requests to FastAPI TestClient.

    Provides a failure switch to simulate delivery outages (httpx.ConnectError)
    without mocking the underlying Service.
    """

    def __init__(self, test_client: TestClient):
        self._test_client = test_client
        self.failing = False

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self.failing:
            raise httpx.ConnectError("Simulated transport delivery outage")
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


def make_test_env(tmp_path, count=2):
    s, r, ids = ready(tmp_path, count=count)
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID})
    test_client = TestClient(app, base_url=BASE_URL)
    transport = SwitchableTransport(test_client)
    worker_client = Client(
        base_url=BASE_URL,
        instance_id=s.instance_id,
        token=WORKER_TOKEN,
        transport=transport,
    )
    return s, r, ids, worker_client, transport


def make_controller_env(tmp_path, monkeypatch, *, provider="fixture-provider", model="fixture-model", count=2):
    s, r, ids = ready(tmp_path, count=count)
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
        "provider": provider,
        "model": model,
        "worker_token_env": "JOBBOT_WORKER_TOKEN",
        "spool_dir": str(spool),
    }
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")
    return s, r, ids, PluginController(str(cfg_file)), transport


# ===========================================================================
# S2-R2: Terminal background execution on bound managed attempt
# ===========================================================================
def test_r2_bound_terminal_background_blocks_before_writer_and_does_not_poison_foreground(tmp_path):
    """R2: Bound managed pre_tool_call terminal background=true must explicitly block

    BEFORE spawning or creating an active writer; post_tool_call(blocked) must not poison
    subsequent foreground work. Unbound ordinary terminal behavior remains unaffected.
    Do not kill or launch real processes.
    """
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-r2"
    spool_path = tmp_path / "outbox_r2.db"

    adapter = HermesAdapter(
        worker_client,
        worker_id=WORKER_ID,
        session_id=session_id,
        browser_profile="fixture-browser",
        skill_version="test-skill",
        provider="fixture",
        model="fixture",
        spool_path=spool_path,
    )

    # 1. Unbound ordinary terminal behavior remains unaffected
    unbound_bg = adapter.pre_tool_call(
        "terminal",
        args={"command": "echo unbound_bg", "background": True},
        session_id=session_id,
        tool_call_id="call-term-unbound-bg",
    )
    assert unbound_bg is None, f"Unbound terminal background must not be blocked: {unbound_bg}"

    unbound_fg = adapter.pre_tool_call(
        "terminal",
        args={"command": "echo unbound_fg", "background": False},
        session_id=session_id,
        tool_call_id="call-term-unbound-fg",
    )
    assert unbound_fg is None, f"Unbound terminal foreground must not be blocked: {unbound_fg}"

    # 2. Bind managed attempt
    adapter.accept(r["id"])
    attempt = adapter.claim()
    assert attempt is not None
    attempt_id = attempt["id"]

    # 3. Bound managed pre_tool_call terminal background=true must explicitly block
    #    BEFORE spawning or creating an active writer
    call_id_bg = "call-term-bg-bound"
    pre_res = adapter.pre_tool_call(
        "terminal",
        args={"command": "echo helper_bg", "background": True},
        session_id=session_id,
        tool_call_id=call_id_bg,
    )
    assert pre_res is not None, "Bound terminal background=True was not blocked"
    assert pre_res.get("action") == "block", f"Expected block directive, got: {pre_res}"

    # Verify no active writer or action spawned before authorization
    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row
        att = db.execute("SELECT * FROM application_attempts WHERE id=?", (attempt_id,)).fetchone()
        assert att["writer_state"] == "idle", f"Active writer created prematurely: writer_state={att['writer_state']}"
        active_actions = db.execute(
            "SELECT * FROM managed_actions WHERE attempt_id=? AND ended_at IS NULL", (attempt_id,)
        ).fetchall()
        assert len(active_actions) == 0, f"Managed actions created for blocked terminal: {active_actions}"
        events = db.execute("SELECT * FROM managed_events WHERE attempt_id=?", (attempt_id,)).fetchall()
        assert len(events) == 0, f"Events created before authorization: {events}"

    # 4. Native Hermes runner emits post_tool_call for the blocked tool; must not poison subsequent foreground work
    adapter.post_tool_call(
        "terminal",
        args={"command": "echo helper_bg", "background": True},
        result={"status": "blocked"},
        session_id=session_id,
        tool_call_id=call_id_bg,
        duration_ms=5,
        status="blocked",
    )

    with adapter._db() as db:
        fault = adapter._get(db, "fault")
        assert fault is None, f"Blocked post callback poisoned adapter fault: {fault}"

    # Subsequent foreground work proceeds normally
    call_id_fg = "call-foreground-after-blocked"
    fg_pre = adapter.pre_tool_call(
        "fixture_tool",
        args={"param": "safe_foreground"},
        session_id=session_id,
        tool_call_id=call_id_fg,
    )
    assert fg_pre is None, f"Foreground tool was poisoned by earlier blocked background terminal: {fg_pre}"

    adapter.post_tool_call(
        "fixture_tool",
        args={"param": "safe_foreground"},
        result={"status": "success"},
        session_id=session_id,
        tool_call_id=call_id_fg,
        duration_ms=100,
        status="success",
    )
    adapter.flush()

    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row
        evs = db.execute("SELECT * FROM managed_events WHERE attempt_id=?", (attempt_id,)).fetchall()
        assert len(evs) == 2  # blocked native callback plus successful foreground tool
        assert sum(json.loads(e['payload_json']).get('status')=='aborted' for e in evs)==1
        assert sum(json.loads(e['payload_json']).get('status')=='success' for e in evs)==1
        assert evs[0]["event_type"] == "tool_finished"


# ===========================================================================
# S2-R3: Accept while live attempt owned and finish quiescent guard
# ===========================================================================
def test_r3_accept_rejects_while_live_attempt_and_preserves_local_state(tmp_path):
    """R3 (part 1): While A owns a live attempt, Adapter.accept(B) must reject

    and preserve A local state; same-run idempotent accept must not drop A.
    """
    s, r_a, ids_a, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-r3-accept"
    spool_path = tmp_path / "outbox_r3_accept.db"

    # Create run B awaiting worker
    job_b = s.intake(url="https://careers.example.test/jobs/r3-b-1", source_id="r3-b-1")
    s.eligibility(job_b["id"], "ready", reason="approved")
    r_b = s.request_run(
        request_id="request-r3-b",
        job_ids=[job_b["id"]],
        identity_id="candidate",
        browser_profile="fixture-browser",
    )

    adapter = HermesAdapter(
        worker_client,
        worker_id=WORKER_ID,
        session_id=session_id,
        browser_profile="fixture-browser",
        skill_version="test-skill",
        provider="fixture",
        model="fixture",
        spool_path=spool_path,
    )

    # Run A accepted and claimed
    adapter.accept(r_a["id"])
    attempt_a = adapter.claim()
    assert attempt_a is not None
    attempt_a_id = attempt_a["id"]

    state_before = adapter._state()
    assert state_before.get("run_id") == r_a["id"]
    assert state_before.get("attempt") is not None
    assert state_before["attempt"]["attempt_id"] == attempt_a_id

    # Same-run idempotent accept must not drop A
    adapter.accept(r_a["id"])
    state_idempotent = adapter._state()
    assert state_idempotent.get("run_id") == r_a["id"]
    assert state_idempotent.get("attempt") is not None
    assert state_idempotent["attempt"]["attempt_id"] == attempt_a_id

    # While A owns a live attempt, Adapter.accept(B) must reject and preserve A local state
    with pytest.raises(ProtocolError):
        adapter.accept(r_b["id"])

    state_after = adapter._state()
    assert state_after.get("run_id") == r_a["id"], (
        f"Expected run_id to remain {r_a['id']}, got {state_after.get('run_id')}"
    )
    assert state_after.get("attempt") is not None, "Live attempt A was dropped by accept(B)"
    assert state_after["attempt"]["attempt_id"] == attempt_a_id


def test_r3_finish_non_quiescent_preserves_unsafe_binding_blocking_bypass(tmp_path, monkeypatch):
    """R3 (part 2): finish(...quiescent=False) must preserve unsafe binding, so a subsequent

    ordinary tool cannot bypass control; normal quiescent finish then new run works.
    """
    s, r, ids, ctrl, transport = make_controller_env(tmp_path, monkeypatch, count=2)
    sid = "session-r3-finish"
    try:
        ctrl.route(
            "post_api_request",
            session_id=sid,
            provider="fixture-provider",
            model="fixture-model",
            response_model="fixture-model",
        )
        ctrl.handle({"operation": "accept", "parameters": {"run_id": r["id"]}}, session_id=sid)
        j1 = json.loads(ctrl.handle({"operation": "next"}, session_id=sid))
        assert j1 is not None
        attempt_id = j1["id"]
        adapter = ctrl.adapters[sid]

        # finish(...quiescent=False)
        fin_res = json.loads(ctrl.handle(
            {
                "operation": "finish",
                "parameters": {
                    "outcome": "blocked",
                    "evidence": "fixture non-quiescent finish",
                    "quiescent": False,
                },
            },
            session_id=sid,
        ))
        assert fin_res.get("outcome") == "blocked"

        # Lease is quarantined, not released
        with s.tx() as db:
            lease = dict(db.execute("SELECT * FROM browser_leases WHERE profile=?", ("fixture-browser",)).fetchone())
            assert lease["state"] == "quarantined"

        # finish(...quiescent=False) must preserve unsafe binding
        state = adapter._state()
        assert state.get("attempt") is not None, "Unsafe binding was dropped by finish(quiescent=False)"

        # Subsequent ordinary tool cannot bypass control
        subsequent_pre = adapter.pre_tool_call(
            "fixture_tool",
            args={},
            session_id=sid,
            tool_call_id="call-after-nonquiescent",
        )
        assert subsequent_pre is not None and subsequent_pre.get("action") == "block", (
            f"Subsequent ordinary tool bypassed control after non-quiescent finish: {subsequent_pre}"
        )

        # Normal quiescent finish then new run works:
        # Reconcile quarantined attempt to release lease
        s.reconcile(
            attempt_id,

            outcome="blocked",
            evidence="quiescent operator reconcile",
            browser_quiescent=True,
        )
        with s.tx() as db:
            lease = dict(db.execute("SELECT * FROM browser_leases WHERE profile=?", ("fixture-browser",)).fetchone())
            assert lease["state"] == "released"

        # Clean quiescent finish on next job
        j2 = json.loads(ctrl.handle({"operation": "next"}, session_id=sid))
        assert j2 is not None
        fin2 = json.loads(ctrl.handle(
            {
                "operation": "finish",
                "parameters": {
                    "outcome": "ready_for_review",
                    "evidence": "quiescent finish",
                    "quiescent": True,
                },
            },
            session_id=sid,
        ))
        assert fin2.get("outcome") == "ready_for_review"

        # New run can now be accepted and claimed
        job_next = s.intake(url="https://careers.example.test/jobs/r3-next-run", source_id="r3-next-1")
        s.eligibility(job_next["id"], "ready", reason="approved")
        r_next = s.request_run(
            request_id="request-r3-next",
            job_ids=[job_next["id"]],
            identity_id="candidate",
            browser_profile="fixture-browser",
        )
        acc_next = json.loads(ctrl.handle({"operation": "accept", "parameters": {"run_id": r_next["id"]}}, session_id=sid))
        assert acc_next.get("id") == r_next["id"]
    finally:
        ctrl.close()


# ===========================================================================
# S2-R4: PluginController submission_intent signature and evidence
# ===========================================================================
def test_r4_plugin_controller_submission_intent_signature_and_evidence(tmp_path, monkeypatch):
    """R4: PluginController submission_intent passes explicit evidence and fixture flag

    through worker client on owned attempt; missing evidence refuses without recorded intent.
    Verifies actual Service.submission_intent signature:
        Service.submission_intent(attempt_id, *, worker_id, fence, evidence, fixture=False)
    """
    # 1. Verify actual Service method signature
    sig = inspect.signature(Service.submission_intent)
    params = list(sig.parameters.keys())
    assert "attempt_id" in params
    assert "worker_id" in params
    assert "fence" in params
    assert "evidence" in params
    assert "fixture" in params
    assert sig.parameters["evidence"].default is inspect.Parameter.empty, "evidence must be required keyword argument"

    s, r, ids, ctrl, transport = make_controller_env(tmp_path, monkeypatch, count=2)
    sid = "session-r4"
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
        assert claim_res is not None
        attempt_id = claim_res["id"]

        # 2. Missing evidence refuses without recorded intent
        res_missing_raw = ctrl.handle(
            {"operation": "submission_intent", "parameters": {"fixture": True}},
            session_id=sid,
        )
        res_missing = json.loads(res_missing_raw)
        assert res_missing.get("error") or res_missing.get("status") == "error", (
            f"Missing evidence must refuse, got: {res_missing}"
        )
        with s.tx() as db:
            row = db.execute("SELECT submit_intent_at FROM application_attempts WHERE id=?", (attempt_id,)).fetchone()
            assert row["submit_intent_at"] is None, "submit_intent_at recorded despite missing evidence"

        # 3. Explicit evidence and fixture flag passes through worker client on owned attempt
        evidence_text = "observed-form-submission-intent-hash-snapshot"
        res_valid_raw = ctrl.handle(
            {
                "operation": "submission_intent",
                "parameters": {
                    "evidence": evidence_text,
                    "fixture": True,
                },
            },
            session_id=sid,
        )
        res_valid = json.loads(res_valid_raw)
        assert "error" not in res_valid, f"submission_intent rejected valid evidence/fixture: {res_valid}"
        assert res_valid.get("submit_intent_at") is not None, f"submit_intent_at missing from response: {res_valid}"

        with s.tx() as db:
            row = db.execute("SELECT submit_intent_at FROM application_attempts WHERE id=?", (attempt_id,)).fetchone()
            assert row["submit_intent_at"] is not None, "submit_intent_at was not recorded in DB"
    finally:
        ctrl.close()


# ===========================================================================
# S2-R5: Recoverable outbox / heartbeat delivery outage before action_start
# ===========================================================================
def test_r5_outbox_flush_pending_outage_does_not_poison_session(tmp_path):
    """R5 (part 1): Recoverable outbox delivery failure BEFORE action_start followed

    by native blocked post callback must not set permanent uncorrelated fault;
    after restoring transport, flush and a fresh foreground tool proceed with correct
    original attribution.
    """
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-r5-flush"
    spool_path = tmp_path / "outbox_r5_flush.db"

    adapter = HermesAdapter(
        worker_client,
        worker_id=WORKER_ID,
        session_id=session_id,
        browser_profile="fixture-browser",
        skill_version="test-skill",
        provider="fixture",
        model="fixture",
        spool_path=spool_path,
    )
    adapter.accept(r["id"])
    attempt = adapter.claim()
    assert attempt is not None
    attempt_id = attempt["id"]

    # Execute prior tool call; simulate delivery outage during post_tool_call flush
    call_prior = "call-prior-tool"
    pre_prior = adapter.pre_tool_call("fixture_tool", args={}, session_id=session_id, tool_call_id=call_prior)
    assert pre_prior is None

    # Delivery outage begins
    transport.failing = True

    # Post tool call fails to drain outbox, leaving outbox row pending
    adapter.post_tool_call(
        "fixture_tool",
        args={},
        result={"status": "ok"},
        session_id=session_id,
        tool_call_id=call_prior,
        duration_ms=50,
        status="success",
    )
    with adapter._db() as db:
        pending_count = db.execute("SELECT count(*) FROM adapter_outbox").fetchone()[0]
        assert pending_count == 1, "Expected 1 pending outbox row"

    # Pre tool call for second tool is blocked because flush is pending BEFORE action_start
    call_blocked = "call-blocked-flush-pending"
    pre_blocked = adapter.pre_tool_call(
        "fixture_tool",
        args={},
        session_id=session_id,
        tool_call_id=call_blocked,
    )
    assert pre_blocked == {"action": "block", "message": "JobBot: telemetry_delivery_pending"}

    # Native Hermes invokes post_tool_call for the blocked tool
    adapter.post_tool_call(
        "fixture_tool",
        args={},
        result={"status": "blocked"},
        session_id=session_id,
        tool_call_id=call_blocked,
        duration_ms=5,
        status="blocked",
    )

    # Must NOT set permanent uncorrelated fault
    with adapter._db() as db:
        fault = adapter._get(db, "fault")
        assert fault is None, f"Permanent fault was set on recoverable flush outage: {fault}"

    # Restore transport
    transport.failing = False

    # Flush outbox
    remaining = adapter.flush()
    assert remaining == 0, f"Expected outbox to drain after transport restored, but {remaining} remain"

    # Fresh foreground tool proceeds with correct original attribution
    call_fresh = "call-fresh-after-flush-restored"
    pre_fresh = adapter.pre_tool_call(
        "fixture_tool",
        args={"action": "fresh"},
        session_id=session_id,
        tool_call_id=call_fresh,
    )
    assert pre_fresh is None, f"Fresh foreground tool was blocked: {pre_fresh}"

    adapter.post_tool_call(
        "fixture_tool",
        args={"action": "fresh"},
        result={"status": "ok"},
        session_id=session_id,
        tool_call_id=call_fresh,
        duration_ms=100,
        status="success",
    )
    adapter.flush()

    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row
        events = db.execute("SELECT * FROM managed_events WHERE attempt_id=? ORDER BY id", (attempt_id,)).fetchall()
        assert len(events) == 3  # two executed calls and the denied call
        assert sum(json.loads(e['payload_json']).get('status')=='success' for e in events)==2
        assert sum(json.loads(e['payload_json']).get('status')=='aborted' for e in events)==1
        successes=[e for e in events if json.loads(e['payload_json']).get('status')=='success']
        assert any(e['action_id'].startswith(call_prior) for e in successes)
        assert any(e['action_id'].startswith(call_fresh) for e in successes)


def test_r5_heartbeat_outage_does_not_poison_session(tmp_path):
    """R5 (part 2): Recoverable heartbeat failure BEFORE action_start followed

    by native blocked post callback must not set permanent uncorrelated fault;
    after restoring transport, flush and a fresh foreground tool proceed with correct
    original attribution.
    """
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-r5-hb"
    spool_path = tmp_path / "outbox_r5_hb.db"

    adapter = HermesAdapter(
        worker_client,
        worker_id=WORKER_ID,
        session_id=session_id,
        browser_profile="fixture-browser",
        skill_version="test-skill",
        provider="fixture",
        model="fixture",
        spool_path=spool_path,
    )
    adapter.accept(r["id"])
    attempt = adapter.claim()
    assert attempt is not None
    attempt_id = attempt["id"]

    # Verify outbox is empty
    with adapter._db() as db:
        assert db.execute("SELECT count(*) FROM adapter_outbox").fetchone()[0] == 0

    # Transport outage during heartbeat check BEFORE action_start
    transport.failing = True

    call_hb_blocked = "call-blocked-hb-outage"
    pre_hb = adapter.pre_tool_call(
        "fixture_tool",
        args={},
        session_id=session_id,
        tool_call_id=call_hb_blocked,
    )
    assert pre_hb is not None and pre_hb.get("action") == "block", f"Expected block directive, got: {pre_hb}"

    # Native Hermes invokes post_tool_call for the blocked tool
    adapter.post_tool_call(
        "fixture_tool",
        args={},
        result={"status": "blocked"},
        session_id=session_id,
        tool_call_id=call_hb_blocked,
        duration_ms=5,
        status="blocked",
    )

    # Must NOT set permanent uncorrelated fault
    with adapter._db() as db:
        fault = adapter._get(db, "fault")
        assert fault is None, f"Permanent fault was set on recoverable heartbeat outage: {fault}"

    # Restore transport
    transport.failing = False

    remaining = adapter.flush()
    assert remaining == 0

    # Fresh foreground tool proceeds with correct original attribution
    call_fresh_hb = "call-fresh-after-hb-restored"
    pre_fresh = adapter.pre_tool_call(
        "fixture_tool",
        args={"action": "fresh_hb"},
        session_id=session_id,
        tool_call_id=call_fresh_hb,
    )
    assert pre_fresh is None, f"Fresh foreground tool was blocked: {pre_fresh}"

    adapter.post_tool_call(
        "fixture_tool",
        args={"action": "fresh_hb"},
        result={"status": "ok"},
        session_id=session_id,
        tool_call_id=call_fresh_hb,
        duration_ms=100,
        status="success",
    )
    adapter.flush()

    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row
        events = db.execute("SELECT * FROM managed_events WHERE attempt_id=?", (attempt_id,)).fetchall()
        assert len(events) == 2  # executed call plus denied heartbeat-gated call
        assert sum(json.loads(e['payload_json']).get('status')=='success' for e in events)==1
        assert sum(json.loads(e['payload_json']).get('status')=='aborted' for e in events)==1
        assert any(e['action_id'].startswith(call_fresh_hb) and json.loads(e['payload_json']).get('status')=='success' for e in events)
