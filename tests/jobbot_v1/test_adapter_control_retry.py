"""Regression tests for HermesAdapter control signals, missing duration telemetry,
and lost action_start acknowledgement recovery.

Verifies:
1. Blocked pre dispatch flushes aborted diagnostic without open managed action:
   Actual Hermes dispatch calls post_tool_call even when pre returns block.
   Accepted/claimed adapter, request pause before pre dummy fixture_tool.
   pre returns {action:block}. Invoke post for that SAME call id/status='blocked'/duration_ms=20.
   flush must reach 0, not queue an impossible action_end forever.
   Backend must preserve one aborted tool_finished diagnostic for that observed blocked invocation,
   without an executed/open managed action. Acknowledge pause, resume, next pre succeeds.
   Do not relax to dropping all blocked telemetry.
2. Missing duration_ms in post callback is NOT known zero:
   Pre valid call, then invoke post omitting duration_ms.
   No falsely precise 0-duration finish event; next pre must block for telemetry reconciliation.
   A legitimately supplied duration_ms=0 is allowed (separate control test).
3. Lost action_start HTTP acknowledgement AFTER real service accepts:
   Subclass forwarding transport to raise httpx.ConnectError once after routing /v1/action_start
   to TestClient. pre blocks due unknown acknowledgement; native post(status='blocked', duration_ms=20)
   plus recovery flush must close the known started action as aborted exactly once.
   No stale open action, no untracked execution. This existing-safe control must remain green when fixing case1.
"""
import json
import sqlite3
import httpx
import pytest
from fastapi.testclient import TestClient

from job_applier.managed_client import Client

try:
    from test_hermes_adapter import (
        BASE_URL,
        WORKER_ID,
        WORKER_TOKEN,
        SwitchableTransport,
        get_adapter_cls,
        make_test_env,
    )
except ImportError:
    from tests.jobbot_v1.test_hermes_adapter import (
        BASE_URL,
        WORKER_ID,
        WORKER_TOKEN,
        SwitchableTransport,
        get_adapter_cls,
        make_test_env,
    )


class LostAckActionStartTransport(SwitchableTransport):
    """Transport that commits action_start on the real Service, then raises ConnectError once."""

    def __init__(self, test_client: TestClient):
        super().__init__(test_client)
        self.drop_action_start_once = True
        self.dropped_action_start = False

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        # Route to real service first so action_start is committed in backend
        response = super().handle_request(request)
        if self.drop_action_start_once and request.url.path == "/v1/action_start":
            self.drop_action_start_once = False
            self.dropped_action_start = True
            raise httpx.ConnectError("Simulated lost action_start acknowledgement after service accepted")
        return response


def test_case_1_blocked_pre_dispatch_flushes_diagnostic_without_open_action(tmp_path):
    """Case 1: Blocked pre dispatch calls post; flush drains and preserves aborted diagnostic."""
    AdapterCls = get_adapter_cls()
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-control-1"
    spool_path = tmp_path / "outbox.db"

    adapter = AdapterCls(
        worker_client,
        worker_id=WORKER_ID,
        session_id=session_id,
        browser_profile="fixture-browser",
        skill_version="fixture-skill-v1",
        provider="fixture-provider",
        model="fixture-model",
        spool_path=spool_path,
    )
    assert adapter.capabilities["protocol"] == 1

    adapter.accept(r["id"])
    attempt = adapter.claim()
    assert attempt is not None
    attempt_id = attempt["id"]
    fence = attempt["fence"]

    # 1. Request pause before pre dummy fixture_tool
    ctrl = s.control(r["id"], command="pause")
    assert ctrl["control"] == "pause_requested"

    # 2. pre returns {action: block}
    call_id = "call-blocked-pause-1"
    hook_kwargs = {"api_request_id": "req-pause-1", "turn_id": "turn-1"}
    pre_res = adapter.pre_tool_call(
        "fixture_tool",
        args={"query": "test"},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id,
        **hook_kwargs,
    )
    assert isinstance(pre_res, dict)
    assert pre_res.get("action") == "block"

    # 3. Actual Hermes dispatch calls post_tool_call even when pre returns block
    adapter.post_tool_call(
        "fixture_tool",
        args={"query": "test"},
        result={"blocked": True},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id,
        duration_ms=20,
        status="blocked",
        **hook_kwargs,
    )

    # 4. flush must reach 0, not queue an impossible action_end forever
    pending = adapter.flush()
    assert pending == 0, f"flush() must reach 0, but {pending} pending items remained in outbox"

    # 5. Backend must preserve one aborted tool_finished diagnostic for that observed blocked invocation,
    #    without an executed/open managed action.
    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row
        open_actions = db.execute(
            "SELECT * FROM managed_actions WHERE attempt_id=? AND ended_at IS NULL",
            (attempt_id,),
        ).fetchall()
        assert len(open_actions) == 0, f"Expected no open managed actions, found: {open_actions}"

        events = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=? AND event_type='tool_finished'",
            (attempt_id,),
        ).fetchall()
        assert len(events) == 1, (
            f"Expected exactly one aborted tool_finished diagnostic, got {len(events)}"
        )
        ev = dict(events[0])
        assert ev["actor"] == "worker"
        payload = json.loads(ev["payload_json"])
        assert payload.get("status") == "aborted", f"Expected payload status 'aborted', got {payload}"
        assert ev["stale"] == 0

    # 6. Acknowledge pause, resume, next pre succeeds. Do not relax to dropping all blocked telemetry.
    ack = s.ack_control(attempt_id, worker_id=WORKER_ID, fence=fence, quiescent=True)
    assert ack["control"] == "paused"

    res = s.control(r["id"], command="resume")
    assert res["control"] == "running"

    call_id_2 = "call-after-resume-2"
    hook_kwargs_2 = {"api_request_id": "req-resume-2", "turn_id": "turn-2"}
    pre_2 = adapter.pre_tool_call(
        "fixture_tool",
        args={"query": "resumed"},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id_2,
        **hook_kwargs_2,
    )
    assert pre_2 is None, f"Expected next pre to succeed after resume, got: {pre_2}"


def test_case_2_missing_duration_ms_not_known_zero_blocks_reconciliation(tmp_path):
    """Case 2: Missing duration_ms in post is NOT known zero; next pre must block for reconciliation."""
    AdapterCls = get_adapter_cls()
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-control-2"
    spool_path = tmp_path / "outbox.db"

    adapter = AdapterCls(
        worker_client,
        worker_id=WORKER_ID,
        session_id=session_id,
        browser_profile="fixture-browser",
        skill_version="fixture-skill-v1",
        provider="fixture-provider",
        model="fixture-model",
        spool_path=spool_path,
    )
    adapter.accept(r["id"])
    attempt = adapter.claim()
    assert attempt is not None
    attempt_id = attempt["id"]

    # 1. Pre valid call
    call_id_1 = "call-missing-dur-1"
    hook_kwargs_1 = {"api_request_id": "req-dur-1", "turn_id": "turn-1"}
    pre_1 = adapter.pre_tool_call(
        "fixture_tool",
        args={"step": 1},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id_1,
        **hook_kwargs_1,
    )
    assert pre_1 is None

    # 2. Invoke post omitting duration_ms
    adapter.post_tool_call(
        "fixture_tool",
        args={"step": 1},
        result={"ok": True},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id_1,
        status="success",
        **hook_kwargs_1,
    )

    # 3. No falsely precise 0-duration finish event
    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row
        events = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=? AND event_type='tool_finished'",
            (attempt_id,),
        ).fetchall()
        zero_dur_events = [e for e in events if e["duration_seconds"] == 0.0]
        assert len(zero_dur_events) == 0, (
            f"Found falsely precise 0-duration finish event: {zero_dur_events}"
        )

    # 4. Next pre must block for telemetry reconciliation
    call_id_2 = "call-missing-dur-2"
    hook_kwargs_2 = {"api_request_id": "req-dur-2", "turn_id": "turn-2"}
    pre_2 = adapter.pre_tool_call(
        "fixture_tool",
        args={"step": 2},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id_2,
        **hook_kwargs_2,
    )
    assert isinstance(pre_2, dict), f"Expected next pre to block, got: {pre_2}"
    assert pre_2.get("action") == "block"
    assert "telemetry_reconciliation" in pre_2.get("message", "") or pre_2.get("message") == "JobBot: telemetry_reconciliation_required"


def test_case_2_control_explicit_zero_duration_allowed(tmp_path):
    """Case 2 Control: A legitimately supplied duration_ms=0 is allowed."""
    AdapterCls = get_adapter_cls()
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-control-2b"
    spool_path = tmp_path / "outbox.db"

    adapter = AdapterCls(
        worker_client,
        worker_id=WORKER_ID,
        session_id=session_id,
        browser_profile="fixture-browser",
        skill_version="fixture-skill-v1",
        provider="fixture-provider",
        model="fixture-model",
        spool_path=spool_path,
    )
    adapter.accept(r["id"])
    attempt = adapter.claim()
    assert attempt is not None
    attempt_id = attempt["id"]

    call_id = "call-explicit-zero-1"
    hook_kwargs = {"api_request_id": "req-zero-1", "turn_id": "turn-1"}
    pre_res = adapter.pre_tool_call(
        "fixture_tool",
        args={"step": 1},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id,
        **hook_kwargs,
    )
    assert pre_res is None

    # Explicitly supply duration_ms=0
    adapter.post_tool_call(
        "fixture_tool",
        args={"step": 1},
        result={"ok": True},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id,
        duration_ms=0,
        status="success",
        **hook_kwargs,
    )

    pending = adapter.flush()
    assert pending == 0

    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row
        events = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=? AND event_type='tool_finished'",
            (attempt_id,),
        ).fetchall()
        assert len(events) == 1
        ev = dict(events[0])
        assert ev["duration_seconds"] == pytest.approx(0.0)
        assert ev["actor"] == "worker"
        payload = json.loads(ev["payload_json"])
        assert payload.get("status") == "success"

    # Next pre succeeds (no reconciliation block)
    call_id_2 = "call-explicit-zero-2"
    hook_kwargs_2 = {"api_request_id": "req-zero-2", "turn_id": "turn-2"}
    pre_2 = adapter.pre_tool_call(
        "fixture_tool",
        args={"step": 2},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id_2,
        **hook_kwargs_2,
    )
    assert pre_2 is None


def test_case_3_lost_action_start_ack_aborts_action_once(tmp_path):
    """Case 3: Lost action_start HTTP ack after real service accepts: closes started action as aborted exactly once."""
    AdapterCls = get_adapter_cls()
    s, r, ids, base_client, base_transport = make_test_env(tmp_path, count=2)
    session_id = "session-control-3"
    spool_path = tmp_path / "outbox.db"

    # Subclass forwarding transport to drop action_start acknowledgement after service accepts
    lost_transport = LostAckActionStartTransport(base_transport._test_client)
    worker_client = Client(
        base_url=BASE_URL,
        instance_id=s.instance_id,
        token=WORKER_TOKEN,
        transport=lost_transport,
    )

    adapter = AdapterCls(
        worker_client,
        worker_id=WORKER_ID,
        session_id=session_id,
        browser_profile="fixture-browser",
        skill_version="fixture-skill-v1",
        provider="fixture-provider",
        model="fixture-model",
        spool_path=spool_path,
    )
    adapter.accept(r["id"])
    attempt = adapter.claim()
    assert attempt is not None
    attempt_id = attempt["id"]

    call_id = "call-lost-ack-1"
    hook_kwargs = {"api_request_id": "req-lost-1", "turn_id": "turn-1"}

    # 1. pre blocks due to unknown acknowledgement
    pre_res = adapter.pre_tool_call(
        "fixture_tool",
        args={"step": "lost_ack"},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id,
        **hook_kwargs,
    )
    assert lost_transport.dropped_action_start is True
    assert isinstance(pre_res, dict)
    assert pre_res.get("action") == "block"

    # 2. Native post(status='blocked', duration_ms=20) plus recovery flush
    adapter.post_tool_call(
        "fixture_tool",
        args={"step": "lost_ack"},
        result={"blocked": True},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id,
        duration_ms=20,
        status="blocked",
        **hook_kwargs,
    )

    pending = adapter.flush()
    assert pending == 0

    # 3. Must close the known started action as aborted exactly once.
    #    No stale open action, no untracked execution.
    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row

        actions = db.execute(
            "SELECT * FROM managed_actions WHERE attempt_id=?",
            (attempt_id,),
        ).fetchall()
        assert len(actions) == 1, f"Expected exactly 1 managed action, got {len(actions)}"
        action = dict(actions[0])
        assert action["status"] == "aborted"
        assert action["ended_at"] is not None

        open_actions = db.execute(
            "SELECT * FROM managed_actions WHERE attempt_id=? AND ended_at IS NULL",
            (attempt_id,),
        ).fetchall()
        assert len(open_actions) == 0, f"Found stale open action: {open_actions}"

        events = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=? AND event_type='tool_finished'",
            (attempt_id,),
        ).fetchall()
        assert len(events) == 1, f"Expected exactly 1 finish event, got {len(events)}"
        ev = dict(events[0])
        assert ev["actor"] == "worker"
        payload = json.loads(ev["payload_json"])
        assert payload.get("status") == "aborted"
        assert ev["stale"] == 0
