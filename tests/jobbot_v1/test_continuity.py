"""Acceptance tests for managed run continuity, checkpoints, and multi-session resumption.

Continuity contract:
- Uses ready, accept from test_ownership.
- s.checkpoint(run_id, worker_id='worker', session_id='session-1', checkpoint_id='cp1',
               data={'summary':'fixture residuals complete','next_job_id':ids[1]})
  returns immutable saved row; repeated same id/data returns same result;
  conflict raises ProtocolError; secrets/raw reasoning rejected.
- Checkpoint allowed active but must not finish attempt or change progress by itself.
- s.resume_run(run_id, worker_id='worker', session_id='session-2', capabilities=<same fixture caps>)
  must refuse while an active/unreconciled browser lease exists.
- After finish prior attempt quiescent ready_for_review, may resume at next pending job;
  preserves fixed membership, old attempt.session_id, saved checkpoint in returned run checkpoint_json,
  new attempt.session_id=='session-2'.
- DB reopen Service(s.db_path) retains continuity.
- No mandatory new session per job: same original tests must still pass.
"""
import json
import pytest

from job_applier.managed import Service, ProtocolError
from tests.jobbot_v1.test_ownership import ready, accept

FIXTURE_CAPABILITIES = {
    "protocol": 1,
    "skill_version": "test-skill",
    "browser_profile": "fixture-browser",
    "provider": "fixture",
    "model": "fixture",
    "telemetry": True,
}


def test_checkpoint_returns_immutable_saved_row_and_is_idempotent(tmp_path):
    """s.checkpoint returns immutable saved row; repeated same id/data same result.

    Checkpoint allowed active but must not finish attempt or change progress by itself.
    """
    s, r, ids = ready(tmp_path)
    accept(s, r)
    a = s.claim(r["id"], worker_id="worker")
    initial_progress = a["progress_at"]

    cp_data = {"summary": "fixture residuals complete", "next_job_id": ids[1]}
    saved_row = s.checkpoint(
        r["id"],
        worker_id="worker",
        session_id="session-1",
        checkpoint_id="cp1",
        data=cp_data,
    )
    assert saved_row is not None
    assert saved_row.get("checkpoint_id") == "cp1" or "cp1" in str(saved_row)

    # Repeated with exact same id and data returns identical result
    repeated_row = s.checkpoint(
        r["id"],
        worker_id="worker",
        session_id="session-1",
        checkpoint_id="cp1",
        data=cp_data,
    )
    assert repeated_row == saved_row

    # Active attempt must not be finished and progress must remain unchanged by checkpoint itself
    attempt_state = s.attempt(a["id"])
    assert attempt_state["completed_at"] is None
    assert attempt_state["outcome"] is None
    assert attempt_state["progress_at"] == initial_progress


def test_checkpoint_conflict_raises_protocol_error(tmp_path):
    """Repeated checkpoint with same id but different data raises ProtocolError."""
    s, r, ids = ready(tmp_path)
    accept(s, r)
    s.claim(r["id"], worker_id="worker")

    cp_data = {"summary": "fixture residuals complete", "next_job_id": ids[1]}
    s.checkpoint(
        r["id"],
        worker_id="worker",
        session_id="session-1",
        checkpoint_id="cp1",
        data=cp_data,
    )

    conflicting_data = {"summary": "conflicting summary", "next_job_id": ids[1]}
    with pytest.raises(ProtocolError):
        s.checkpoint(
            r["id"],
            worker_id="worker",
            session_id="session-1",
            checkpoint_id="cp1",
            data=conflicting_data,
        )


def test_checkpoint_rejects_secrets_and_raw_reasoning(tmp_path):
    """Secrets or raw reasoning in checkpoint data must be rejected with ProtocolError."""
    s, r, ids = ready(tmp_path)
    accept(s, r)
    s.claim(r["id"], worker_id="worker")

    # Rejection of explicit credential keys
    with pytest.raises(ProtocolError):
        s.checkpoint(
            r["id"],
            worker_id="worker",
            session_id="session-1",
            checkpoint_id="cp_secret_key",
            data={"password": "raw_secret_value_123"},
        )

    # Rejection of secret patterns in string values
    with pytest.raises(ProtocolError):
        s.checkpoint(
            r["id"],
            worker_id="worker",
            session_id="session-1",
            checkpoint_id="cp_bearer",
            data={"summary": "Bearer secret_api_token_value_abc"},
        )

    # Rejection of raw reasoning keys
    with pytest.raises(ProtocolError):
        s.checkpoint(
            r["id"],
            worker_id="worker",
            session_id="session-1",
            checkpoint_id="cp_raw_reasoning",
            data={"raw_reasoning": "internal chain of thought reasoning trace"},
        )

    with pytest.raises(ProtocolError):
        s.checkpoint(
            r["id"],
            worker_id="worker",
            session_id="session-1",
            checkpoint_id="cp_rawreasoning",
            data={"rawreasoning": "another reasoning dump"},
        )


def test_resume_run_refuses_while_active_lease_exists(tmp_path):
    """s.resume_run must refuse while an active/unreconciled browser lease exists."""
    s, r, ids = ready(tmp_path)
    accept(s, r)
    a = s.claim(r["id"], worker_id="worker")
    assert a is not None

    # While attempt `a` holds active browser lease, resume_run must be refused
    with pytest.raises(ProtocolError):
        s.resume_run(
            r["id"],
            worker_id="worker",
            session_id="session-2",
            capabilities=FIXTURE_CAPABILITIES,
        )


def test_resume_run_after_quiescent_finish_resumes_next_job(tmp_path):
    """After finish prior attempt quiescent ready_for_review, may resume at next pending job;

    preserves fixed membership, old attempt.session_id, saved checkpoint in returned run checkpoint_json,
    new attempt.session_id=='session-2'.
    """
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)
    a = s.claim(r["id"], worker_id="worker")
    assert a["job_id"] == ids[0]
    assert a["session_id"] == "session-1"

    # Save checkpoint before finishing attempt
    cp_data = {"summary": "fixture residuals complete", "next_job_id": ids[1]}
    s.checkpoint(
        r["id"],
        worker_id="worker",
        session_id="session-1",
        checkpoint_id="cp1",
        data=cp_data,
    )

    # Finish prior attempt quiescent ready_for_review
    s.finish(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        outcome="ready_for_review",
        evidence="fixture review",
        quiescent=True,
    )

    # Resume run with new session-2
    resumed = s.resume_run(
        r["id"],
        worker_id="worker",
        session_id="session-2",
        capabilities=FIXTURE_CAPABILITIES,
    )

    # Verify saved checkpoint preserved in returned run checkpoint_json
    cp_json_val = resumed.get("checkpoint_json", "{}")
    cp_dict = json.loads(cp_json_val) if isinstance(cp_json_val, str) else cp_json_val
    assert "cp1" in str(cp_dict) or "fixture residuals complete" in str(cp_dict)

    # Claim next pending job under new session
    b = s.claim(r["id"], worker_id="worker")
    assert b["job_id"] == ids[1]
    assert b["session_id"] == "session-2"

    # Old attempt session_id remains preserved as session-1
    old_attempt = s.attempt(a["id"])
    assert old_attempt["session_id"] == "session-1"


def test_db_reopen_retains_continuity(tmp_path):
    """DB reopen Service(s.db_path) retains continuity across process or service reloads."""
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)
    a = s.claim(r["id"], worker_id="worker")

    cp_data = {"summary": "fixture residuals complete", "next_job_id": ids[1]}
    s.checkpoint(
        r["id"],
        worker_id="worker",
        session_id="session-1",
        checkpoint_id="cp1",
        data=cp_data,
    )
    s.finish(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        outcome="ready_for_review",
        evidence="fixture review",
        quiescent=True,
    )

    # Reopen DB with fresh Service instance
    s_reloaded = Service(s.db_path)
    resumed = s_reloaded.resume_run(
        r["id"],
        worker_id="worker",
        session_id="session-2",
        capabilities=FIXTURE_CAPABILITIES,
    )

    cp_val = resumed.get("checkpoint_json", "{}")
    cp_dict = json.loads(cp_val) if isinstance(cp_val, str) else cp_val
    assert "cp1" in str(cp_dict) or "fixture residuals complete" in str(cp_dict)

    b = s_reloaded.claim(r["id"], worker_id="worker")
    assert b["job_id"] == ids[1]
    assert b["session_id"] == "session-2"

    # Reopen once more to verify complete history survives reload
    s_final = Service(s.db_path)
    assert s_final.attempt(a["id"])["session_id"] == "session-1"
    assert s_final.attempt(b["id"])["session_id"] == "session-2"


def test_no_mandatory_new_session_per_job_continuity(tmp_path):
    """No mandatory new session per job: same original tests must still pass.

    Continuous execution within session-1 across multiple jobs remains valid.
    """
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)
    a = s.claim(r["id"], worker_id="worker")
    assert a["job_id"] == ids[0]
    assert a["session_id"] == "session-1"

    s.finish(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        outcome="ready_for_review",
        evidence="fixture review",
        quiescent=True,
    )

    b = s.claim(r["id"], worker_id="worker")
    assert b["job_id"] == ids[1]
    assert b["session_id"] == "session-1"
