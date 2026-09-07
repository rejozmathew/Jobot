"""Stage 2 tests for HermesAdapter interface.

Verifies:
1. accept/claim same session, pre for safe dummy tool 'fixture_tool', post duration_ms=250.
   Actual backend managed_events contains one tool_finished for owned attempt with duration_seconds≈0.25.
   Synthetic password/OTP/mail/secret sentinels never appear in app DB or outbox DB text.
   'jobbot' RPC tool is exempt from recursive automatic spans.
2. Pause request after pre: another pre returns EXACT block directive format ({'action': 'block', 'message': ...}).
   Post completes old action during pause, quiescent control acknowledged. No second action starts before resume.
3. Freeze late callback attribution: pre job A; finish blocked/quiescent=False then reconcile blocked/browser_quiescent=True.
   Adapter claims B. Post A uses original call_id, creates stale tool_finished for A, never B, and does not alter B progress.
4. Delivery outage: forwarding transport switch raises httpx.ConnectError.
   Post queues bounded sanitized action_end envelope durably. New adapter same spool/session retains pending delivery.
   Transport restored, flush twice yields exactly one finish event. Future pre blocks while delivery unavailable.
5. Missing tool_call_id on bound active session blocks rather than silently dropping telemetry.
   Unbound unrelated session cannot acquire active attempt. Constructor/accept session binding is explicit.
"""
import importlib.util
from pathlib import Path
import sqlite3
import httpx
import pytest
from fastapi.testclient import TestClient

from job_applier.managed import ProtocolError
from job_applier.managed_api import create_app
from job_applier.managed_client import Client

try:
    from test_ownership import ready
except ImportError:
    from tests.jobbot_v1.test_ownership import ready


OPERATOR_TOKEN = "synthetic-operator-token-jobbot-v1-32chars"
WORKER_TOKEN = "synthetic-worker-token-jobbot-v1-32chars"
WORKER_ID = "worker"
BASE_URL = "http://127.0.0.1:8769"


def get_adapter_cls():
    assert importlib.util.find_spec("job_applier.hermes_adapter") is not None, (
        "job_applier.hermes_adapter module not found (expected RED in test-only stage)"
    )
    from job_applier.hermes_adapter import HermesAdapter
    return HermesAdapter


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


def assert_sentinels_absent_from_sqlite(db_path: Path, sentinels: list[str]) -> None:
    if not db_path.exists():
        return
    raw_data = db_path.read_bytes()
    for sentinel in sentinels:
        assert sentinel.encode() not in raw_data, (
            f"Sentinel '{sentinel}' leaked into raw storage of {db_path}"
        )
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for tbl in tables:
            rows = db.execute(f'SELECT * FROM "{tbl}"').fetchall()
            for row in rows:
                for col in row.keys():
                    val = row[col]
                    if isinstance(val, str):
                        for sentinel in sentinels:
                            assert sentinel not in val, (
                                f"Sentinel '{sentinel}' leaked into table '{tbl}', col '{col}': {val}"
                            )


def test_case_1_accept_claim_telemetry_sanitization_and_jobbot_exempt(tmp_path):
    AdapterCls = get_adapter_cls()
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-1"
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

    # 1. Accept and claim run
    adapter.accept(r["id"])
    attempt = adapter.claim()
    assert attempt is not None
    assert attempt["job_id"] == ids[0]
    owned_attempt_id = attempt["id"]

    # 2. Exemption: 'jobbot' RPC tool call does not produce recursive automatic spans
    pre_jobbot = adapter.pre_tool_call(
        "jobbot",
        args={"action": "query_state"},
        task_id="task-1",
        session_id=session_id,
        tool_call_id="call-jobbot-rpc",
    )
    assert pre_jobbot is None
    adapter.post_tool_call(
        "jobbot",
        args={"action": "query_state"},
        result={"status": "ok"},
        task_id="task-1",
        session_id=session_id,
        tool_call_id="call-jobbot-rpc",
        duration_ms=50,
        status="success",
    )

    with sqlite3.connect(s.db_path) as db:
        jobbot_ev = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=? AND payload_json LIKE '%jobbot%'",
            (owned_attempt_id,),
        ).fetchall()
        assert len(jobbot_ev) == 0, f"Exempt 'jobbot' RPC tool produced automatic events: {jobbot_ev}"

    # 3. Pre and post for safe dummy tool 'fixture_tool' with stable call_id
    call_id = "call-fixture-safe-1"
    sentinels = [
        "SYNTHETIC_PASSWORD_SENTINEL_8819",
        "SYNTHETIC_OTP_SENTINEL_654321",
        "SYNTHETIC_SECRET_SENTINEL_XYZZY",
        "SYNTHETIC_MAIL_SENTINEL_user@secret.test",
    ]

    pre_res = adapter.pre_tool_call(
        "fixture_tool",
        args={
            "field": "secret_field",
            "password": sentinels[0],
            "otp": sentinels[1],
        },
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id,
    )
    assert pre_res is None

    adapter.post_tool_call(
        "fixture_tool",
        args={
            "field": "secret_field",
            "password": sentinels[0],
            "otp": sentinels[1],
        },
        result={
            "status": "success",
            "secret_key": sentinels[2],
            "confirmation_email": sentinels[3],
        },
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id,
        duration_ms=250,
        status="success",
    )

    # 4. Backend verification
    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row
        events = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=? AND event_type='tool_finished'",
            (owned_attempt_id,),
        ).fetchall()
        assert len(events) == 1, f"Expected 1 tool_finished event, got {len(events)}"
        ev = dict(events[0])
        assert ev["duration_seconds"] == pytest.approx(0.25, abs=0.05)
        assert ev["stale"] == 0

    # 5. Security & Redaction verification: Sentinels never appear in app DB or outbox text
    assert_sentinels_absent_from_sqlite(s.db_path, sentinels)
    assert_sentinels_absent_from_sqlite(spool_path, sentinels)


def test_case_2_pause_request_exact_block_directive_and_quiescent_ack(tmp_path):
    AdapterCls = get_adapter_cls()
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-1"
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
    fence = attempt["fence"]

    call_1 = "call-pause-1"
    pre_1 = adapter.pre_tool_call(
        "fixture_tool",
        args={"q": 1},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_1,
    )
    assert pre_1 is None

    # Pause request after pre
    ctrl = s.control(r["id"], command="pause")
    assert ctrl["control"] == "pause_requested"

    # Another pre must return EXACT block directive format: {'action': 'block', 'message': ...}
    call_2 = "call-pause-2"
    pre_2 = adapter.pre_tool_call(
        "fixture_tool",
        args={"q": 2},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_2,
    )
    assert isinstance(pre_2, dict), f"Expected dict block directive, got {type(pre_2)}"
    assert pre_2.get("action") == "block", f"Expected action 'block', got {pre_2}"
    assert "message" in pre_2 and isinstance(pre_2["message"], str) and len(pre_2["message"]) > 0

    # Quiescence cannot be acknowledged while call_1 is pending
    with pytest.raises(ProtocolError):
        s.ack_control(attempt_id, worker_id=WORKER_ID, fence=fence, quiescent=True)

    # Post completes old action during pause
    adapter.post_tool_call(
        "fixture_tool",
        args={"q": 1},
        result={"ok": True},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_1,
        duration_ms=100,
        status="success",
    )

    # Now app can acknowledge control quiescent
    ack = s.ack_control(attempt_id, worker_id=WORKER_ID, fence=fence, quiescent=True)
    assert ack["control"] == "paused"

    # No second action starts before resume
    call_3 = "call-pause-3"
    pre_3 = adapter.pre_tool_call(
        "fixture_tool",
        args={"q": 3},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_3,
    )
    assert isinstance(pre_3, dict)
    assert pre_3.get("action") == "block"

    # Resume run allows new actions
    s.control(r["id"], command="resume")
    pre_after_resume = adapter.pre_tool_call(
        "fixture_tool",
        args={"q": 3},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_3,
    )
    assert pre_after_resume is None


def test_case_3_freeze_late_callback_attribution_and_stale_event(tmp_path):
    AdapterCls = get_adapter_cls()
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-1"
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

    # Pre job A
    attempt_a = adapter.claim()
    assert attempt_a is not None
    assert attempt_a["job_id"] == ids[0]
    att_a_id = attempt_a["id"]
    att_a_fence = attempt_a["fence"]

    call_id_a = "call-freeze-a"
    pre_a = adapter.pre_tool_call(
        "fixture_tool",
        args={"step": "a"},
        task_id="task-a",
        session_id=session_id,
        tool_call_id=call_id_a,
    )
    assert pre_a is None

    # Finish A blocked with quiescent=False
    s.finish(
        att_a_id,
        worker_id=WORKER_ID,
        fence=att_a_fence,
        outcome="blocked",
        evidence="operator intervention needed",
        quiescent=False,
    )

    # Operator reconciles blocked with browser_quiescent=True
    s.reconcile(
        att_a_id,
        outcome="blocked",
        evidence="fixture reconciled by operator",
        browser_quiescent=True,
    )

    # Adapter claims B
    attempt_b = adapter.claim()
    assert attempt_b is not None
    assert attempt_b["job_id"] == ids[1]
    att_b_id = attempt_b["id"]
    progress_b_before = s.attempt_status(att_b_id)["progress_at"]

    # Post A uses original call_id
    adapter.post_tool_call(
        "fixture_tool",
        args={"step": "a"},
        result={"status": "late_done"},
        task_id="task-a",
        session_id=session_id,
        tool_call_id=call_id_a,
        duration_ms=120,
        status="success",
    )

    # Stale tool_finished event created for A, never B
    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row
        ev_a = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=?",
            (att_a_id,),
        ).fetchall()
        matching_a = [e for e in ev_a if e["action_id"] == call_id_a or call_id_a in e["id"]]
        assert len(matching_a) == 1, f"Expected 1 event for call_id_a on attempt A, got {matching_a}"
        assert matching_a[0]["event_type"] == "tool_finished"
        assert matching_a[0]["stale"] == 1

        ev_b = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=?",
            (att_b_id,),
        ).fetchall()
        matching_b = [e for e in ev_b if e["action_id"] == call_id_a or call_id_a in e["id"]]
        assert len(matching_b) == 0, f"Attempt A callback leaked into Attempt B events: {matching_b}"

    # Must not change B progress
    progress_b_after = s.attempt_status(att_b_id)["progress_at"]
    assert progress_b_after == progress_b_before


def test_case_4_delivery_outage_spool_durability_and_flush_idempotence(tmp_path):
    AdapterCls = get_adapter_cls()
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-1"
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
    att_id = attempt["id"]

    call_id = "call-outage-durability-1"
    pre = adapter.pre_tool_call(
        "fixture_tool",
        args={"data": "test"},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id,
    )
    assert pre is None

    # Delivery outage via transport failure switch
    transport.failing = True

    # Post must queue bounded sanitized action_end envelope durably without crashing
    adapter.post_tool_call(
        "fixture_tool",
        args={"data": "test"},
        result={"status": "ok"},
        task_id="task-1",
        session_id=session_id,
        tool_call_id=call_id,
        duration_ms=150,
        status="success",
    )

    # Future pre blocks while delivery is unavailable (not fail-open)
    pre_blocked_1 = adapter.pre_tool_call(
        "fixture_tool",
        args={"data": "future"},
        task_id="task-1",
        session_id=session_id,
        tool_call_id="call-outage-future-1",
    )
    assert isinstance(pre_blocked_1, dict)
    assert pre_blocked_1.get("action") == "block"

    # Verify spool file exists on disk
    assert spool_path.exists(), "Spool outbox file was not created"

    # New adapter with same spool and session must retain pending delivery
    adapter_2 = AdapterCls(
        worker_client,
        worker_id=WORKER_ID,
        session_id=session_id,
        browser_profile="fixture-browser",
        skill_version="fixture-skill-v1",
        provider="fixture-provider",
        model="fixture-model",
        spool_path=spool_path,
    )

    pre_blocked_2 = adapter_2.pre_tool_call(
        "fixture_tool",
        args={"data": "future_2"},
        task_id="task-1",
        session_id=session_id,
        tool_call_id="call-outage-future-2",
    )
    assert isinstance(pre_blocked_2, dict)
    assert pre_blocked_2.get("action") == "block"

    # Flush while failing retains pending count
    pending = adapter_2.flush()
    assert pending > 0

    # Restore transport
    transport.failing = False

    # Flush twice
    count_1 = adapter_2.flush()
    assert count_1 == 0
    count_2 = adapter_2.flush()
    assert count_2 == 0

    # Exactly one finish event in backend managed_events
    with sqlite3.connect(s.db_path) as db:
        events = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=? AND (action_id=? OR id LIKE ?)",
            (att_id, call_id, f"%{call_id}%"),
        ).fetchall()
        assert len(events) == 1, f"Expected exactly 1 finish event, got {len(events)}"


def test_case_5_missing_tool_call_id_blocks_and_strict_session_ownership(tmp_path):
    AdapterCls = get_adapter_cls()
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-1"
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
    assert attempt["session_id"] == session_id

    # 1. Missing tool_call_id on bound active session must block rather than silently dropping telemetry
    empty_res = adapter.pre_tool_call(
        "fixture_tool",
        args={"k": "v"},
        task_id="task-1",
        session_id=session_id,
        tool_call_id="",
    )
    assert isinstance(empty_res, dict)
    assert empty_res.get("action") == "block"

    none_res = adapter.pre_tool_call(
        "fixture_tool",
        args={"k": "v"},
        task_id="task-1",
        session_id=session_id,
    )
    assert isinstance(none_res, dict)
    assert none_res.get("action") == "block"

    # 2. Unbound unrelated session must not acquire this session's attempt
    unrelated_res = adapter.pre_tool_call(
        "fixture_tool",
        args={"k": "v"},
        task_id="task-unrelated",
        session_id="unrelated-session-xyz",
        tool_call_id="call-unrelated-1",
    )
    assert isinstance(unrelated_res, dict)
    assert unrelated_res.get("action") == "block"

    with sqlite3.connect(s.db_path) as db:
        unrelated_ev = db.execute(
            "SELECT * FROM managed_events WHERE action_id='call-unrelated-1' OR id LIKE '%call-unrelated-1%'",
        ).fetchall()
        assert len(unrelated_ev) == 0

    # 3. Explicit session binding: an adapter with an arbitrary session cannot acquire session-1's attempt
    adapter_other = AdapterCls(
        worker_client,
        worker_id=WORKER_ID,
        session_id="arbitrary-session-other",
        browser_profile="fixture-browser",
        skill_version="fixture-skill-v1",
        provider="fixture-provider",
        model="fixture-model",
        spool_path=tmp_path / "outbox_other.db",
    )
    with pytest.raises(ProtocolError):
        adapter_other.accept(r["id"])

    try:
        other_attempt = adapter_other.claim()
        assert other_attempt is None or other_attempt.get("session_id") != session_id
    except ProtocolError:
        pass
