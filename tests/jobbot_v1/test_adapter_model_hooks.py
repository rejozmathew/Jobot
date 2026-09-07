"""Stage 2 tests for HermesAdapter model API hooks and outbox tamper resistance.

Verifies:
1. Capture model call at attempt A with fixture provider/model labels, exact duration 1.25,
   numeric usage {'input_tokens': 23, 'output_tokens': 7}, and redaction of synthetic sentinel
   secrets from app DB and outbox DB. Replay is idempotent.
2. Late model callback after operator-quiescent completion of attempt A and claim of attempt B
   stays attributed to attempt A and marked stale; produces no progress on attempt B.
3. Observed different model or provider faults and blocks subsequent pre_tool dispatches,
   storing factual failure metadata rather than raw model responses.
4. Missing API duration or usage never invents precise zero counters or timestamps.
5. Error callbacks record failures cleanly without leaking raw secret exceptions.
6. Tampered outbox row with operation='identity' remains blocked/invalid on flush;
   it is neither dropped nor executed.
"""
import json
from pathlib import Path
import sqlite3
import pytest

try:
    from test_hermes_adapter import (
        WORKER_ID,
        assert_sentinels_absent_from_sqlite,
        get_adapter_cls,
        make_test_env,
    )
except ImportError:
    from tests.jobbot_v1.test_hermes_adapter import (
        WORKER_ID,
        assert_sentinels_absent_from_sqlite,
        get_adapter_cls,
        make_test_env,
    )


SENTINELS = [
    "SYNTHETIC_API_KEY_SECRET_8821_XYZ",
    "SYNTHETIC_RAW_PROMPT_SENTINEL_USER_MSG",
    "SYNTHETIC_RAW_RESPONSE_SENTINEL_ASSISTANT_MSG",
    "SYNTHETIC_CONVERSATION_HISTORY_SENTINEL_OLD_MSG",
]


def create_adapter(tmp_path, worker_client, **overrides):
    AdapterCls = get_adapter_cls()
    defaults = {
        "worker_id": WORKER_ID,
        "session_id": "session-model-1",
        "browser_profile": "fixture-browser",
        "skill_version": "fixture-skill-v1",
        "provider": "fixture-provider",
        "model": "fixture-model",
        "spool_path": tmp_path / "outbox.db",
    }
    defaults.update(overrides)
    return AdapterCls(worker_client, **defaults)


def test_model_call_capture_duration_usage_and_redaction(tmp_path):
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-model-1"
    spool_path = tmp_path / "outbox.db"
    adapter = create_adapter(tmp_path, worker_client, session_id=session_id)

    adapter.accept(r["id"])
    attempt = adapter.claim()
    assert attempt is not None
    attempt_id = attempt["id"]
    api_request_id = "req-model-attempt-a"

    adapter.pre_api_request(
        session_id=session_id,
        api_request_id=api_request_id,
        model="fixture-model",
        provider="fixture-provider",
        raw_request={"messages": [{"role": "user", "content": SENTINELS[1]}], "api_key": SENTINELS[0]},
        history=[{"role": "system", "content": SENTINELS[3]}],
    )

    usage = {"input_tokens": 23, "output_tokens": 7}
    adapter.post_api_request(
        session_id=session_id,
        api_request_id=api_request_id,
        model="fixture-model",
        provider="fixture-provider",
        response_model="fixture-model",
        api_duration=1.25,
        usage=usage,
        raw_response={"content": SENTINELS[2]},
        assistant_message={"role": "assistant", "content": SENTINELS[2]},
        history=[SENTINELS[3]],
    )
    adapter.flush()

    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row
        events = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=? AND event_type='model_finished'",
            (attempt_id,),
        ).fetchall()
        assert len(events) == 1, f"Expected 1 model_finished event, got {len(events)}"
        ev = dict(events[0])
        assert ev["duration_seconds"] == pytest.approx(1.25, abs=0.001)
        assert ev["stale"] == 0
        payload = json.loads(ev["payload_json"])
        assert payload.get("provider") == "fixture-provider"
        assert payload.get("model") == "fixture-model"
        assert payload.get("response_model") == "fixture-model"
        assert payload.get("input_tokens") == usage["input_tokens"]
        assert payload.get("output_tokens") == usage["output_tokens"]

    assert_sentinels_absent_from_sqlite(s.db_path, SENTINELS)
    assert_sentinels_absent_from_sqlite(spool_path, SENTINELS)

    # Replay idempotent
    adapter.post_api_request(
        session_id=session_id,
        api_request_id=api_request_id,
        model="fixture-model",
        provider="fixture-provider",
        response_model="fixture-model",
        api_duration=1.25,
        usage=usage,
    )
    adapter.flush()
    with sqlite3.connect(s.db_path) as db:
        events = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=? AND event_type='model_finished'",
            (attempt_id,),
        ).fetchall()
        assert len(events) == 1, f"Replay was not idempotent, got {len(events)} events"


def test_late_model_callback_after_quiescent_completion_stays_stale(tmp_path):
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-model-late"
    spool_path = tmp_path / "outbox.db"
    adapter = create_adapter(tmp_path, worker_client, session_id=session_id)

    adapter.accept(r["id"])
    attempt_a = adapter.claim()
    assert attempt_a is not None
    att_a_id = attempt_a["id"]
    att_a_fence = attempt_a["fence"]

    api_request_id = "req-model-late-a"
    adapter.pre_api_request(
        session_id=session_id,
        api_request_id=api_request_id,
        model="fixture-model",
        provider="fixture-provider",
    )

    s.finish(
        att_a_id,
        worker_id=WORKER_ID,
        fence=att_a_fence,
        outcome="blocked",
        evidence="operator pause requested",
        quiescent=False,
    )
    s.reconcile(
        att_a_id,
        outcome="blocked",
        evidence="reconciled quiescent by operator",
        browser_quiescent=True,
    )

    attempt_b = adapter.claim()
    assert attempt_b is not None
    att_b_id = attempt_b["id"]
    progress_b_before = s.attempt_status(att_b_id)["progress_at"]

    adapter.post_api_request(
        session_id=session_id,
        api_request_id=api_request_id,
        model="fixture-model",
        provider="fixture-provider",
        response_model="fixture-model",
        api_duration=1.25,
        usage={"input_tokens": 23, "output_tokens": 7},
    )
    adapter.flush()

    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row
        ev_a = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=? AND event_type='model_finished'",
            (att_a_id,),
        ).fetchall()
        assert len(ev_a) == 1, f"Expected 1 model_finished on attempt A, got {len(ev_a)}"
        assert ev_a[0]["stale"] == 1

        ev_b = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=? AND event_type='model_finished'",
            (att_b_id,),
        ).fetchall()
        assert len(ev_b) == 0, f"Attempt A model event leaked to attempt B: {ev_b}"

    assert s.attempt_status(att_b_id)["progress_at"] == progress_b_before


def test_observed_different_model_or_provider_faults_and_blocks_pre_tool(tmp_path):
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-model-drift"
    spool_path = tmp_path / "outbox.db"
    adapter = create_adapter(
        tmp_path,
        worker_client,
        session_id=session_id,
        provider="fixture-provider",
        model="fixture-model",
    )

    adapter.accept(r["id"])
    attempt = adapter.claim()
    assert attempt is not None

    sentinel_drift = "SYNTHETIC_SECRET_DRIFT_RESPONSE_TEXT_9912"
    api_request_id = "req-drift-1"

    adapter.pre_api_request(
        session_id=session_id,
        api_request_id=api_request_id,
        model="fixture-model",
        provider="fixture-provider",
    )
    adapter.post_api_request(
        session_id=session_id,
        api_request_id=api_request_id,
        model="unauthorized-model",
        provider="unexpected-provider",
        response_model="unauthorized-model",
        api_duration=1.0,
        usage={"input_tokens": 10, "output_tokens": 5},
        raw_response={"text": sentinel_drift},
    )

    pre_tool_res = adapter.pre_tool_call(
        "fixture_tool",
        args={"step": 1},
        task_id="task-1",
        session_id=session_id,
        tool_call_id="call-after-drift-1",
    )
    assert isinstance(pre_tool_res, dict), f"Expected block directive, got: {pre_tool_res}"
    assert pre_tool_res.get("action") == "block"

    with sqlite3.connect(spool_path) as db:
        db.row_factory = sqlite3.Row
        fault = db.execute("SELECT value_json FROM adapter_meta WHERE key='fault'").fetchone()
        assert fault is not None, "Expected fault recorded in adapter_meta"
        fault_val = json.loads(fault["value_json"])
        assert any(term in str(fault_val).lower() for term in ("model", "provider", "mismatch", "telemetry"))

    assert_sentinels_absent_from_sqlite(spool_path, [sentinel_drift])
    assert_sentinels_absent_from_sqlite(s.db_path, [sentinel_drift])


def test_missing_api_duration_and_usage_never_invents_zero(tmp_path):
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-model-missing"
    spool_path = tmp_path / "outbox.db"
    adapter = create_adapter(tmp_path, worker_client, session_id=session_id)

    adapter.accept(r["id"])
    attempt = adapter.claim()
    assert attempt is not None
    attempt_id = attempt["id"]

    api_request_id = "req-missing-metrics-1"
    adapter.pre_api_request(
        session_id=session_id,
        api_request_id=api_request_id,
        model="fixture-model",
        provider="fixture-provider",
    )
    adapter.post_api_request(
        session_id=session_id,
        api_request_id=api_request_id,
        model="fixture-model",
        provider="fixture-provider",
        response_model="fixture-model",
        api_duration=None,
        usage=None,
    )
    adapter.flush()

    with sqlite3.connect(s.db_path) as db:
        db.row_factory = sqlite3.Row
        events = db.execute(
            "SELECT * FROM managed_events WHERE attempt_id=? AND event_type='model_finished'",
            (attempt_id,),
        ).fetchall()
        assert len(events) == 1
        ev = dict(events[0])
        assert ev["duration_seconds"] is None, f"Expected None duration, got {ev['duration_seconds']}"
        payload = json.loads(ev["payload_json"])
        assert 'input_tokens' not in payload
        assert 'output_tokens' not in payload


def test_api_request_error_records_event_without_leaking_secrets(tmp_path):
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-model-error"
    spool_path = tmp_path / "outbox.db"
    adapter = create_adapter(tmp_path, worker_client, session_id=session_id)

    adapter.accept(r["id"])
    attempt = adapter.claim()
    assert attempt is not None

    err_sentinel = "SYNTHETIC_API_ERROR_TOKEN_SECRET_987654"
    api_request_id = "req-model-err-1"
    adapter.pre_api_request(
        session_id=session_id,
        api_request_id=api_request_id,
        model="fixture-model",
        provider="fixture-provider",
    )
    adapter.api_request_error(
        session_id=session_id,
        api_request_id=api_request_id,
        api_duration=None,
        error_type="upstream_timeout",
        raw_error=err_sentinel,
    )
    adapter.flush()

    assert_sentinels_absent_from_sqlite(s.db_path, [err_sentinel])
    assert_sentinels_absent_from_sqlite(spool_path, [err_sentinel])


def test_tampered_outbox_identity_operation_blocked_not_executed_or_dropped(tmp_path):
    s, r, ids, worker_client, transport = make_test_env(tmp_path, count=2)
    session_id = "session-tampered"
    spool_path = tmp_path / "outbox.db"
    adapter = create_adapter(tmp_path, worker_client, session_id=session_id)

    tampered_id = "tampered-outbox-row-1"
    tampered_payload = json.dumps({"action": "unauthorized_business_operation", "target": "admin"})
    with adapter._db() as db:
        db.execute(
            "INSERT INTO adapter_outbox(id, operation, payload_json) VALUES (?, ?, ?)",
            (tampered_id, "identity", tampered_payload),
        )

    pending = adapter.flush()
    assert pending > 0, f"Expected pending > 0, got {pending}"
    assert adapter.last_error == "invalid_outbox_operation"

    with adapter._db() as db:
        row = db.execute("SELECT * FROM adapter_outbox WHERE id=?", (tampered_id,)).fetchone()
        assert row is not None, "Tampered row was unexpectedly dropped from outbox"
        assert row["operation"] == "identity"

    with sqlite3.connect(s.db_path) as db:
        events = db.execute(
            "SELECT * FROM managed_events WHERE payload_json LIKE '%unauthorized_business_operation%'"
        ).fetchall()
        assert len(events) == 0, "Tampered operation executed business action on service"
