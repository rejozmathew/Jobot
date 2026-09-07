"""Protocol type enforcement and requisition query token acceptance tests.

Primary owns production architecture and implementation.
Verifies protocol contracts:
1) JSON strings and numbers passed to boolean fields ('quiescent',
   'browser_quiescent', 'fixture') must return HTTP 422 invalid_payload
   and must not alter control, outcome, or submit_intent.
2) Real accepted+claimed fixture with pause requested: quiescent='false'
   must not acknowledge paused control.
3) Operator reconcile browser_quiescent='false' must reject without completed_at.
4) Worker submission_intent fixture='false' must reject without marker.
5) bool=True supplied as attempt_id or fence must be rejected HTTP 422
   (not interpreted as integer 1).
6) Genuine booleans and integers continue existing positive behavior.
7) Legacy JobQueue.add on managed instance: generic query token
   ('token=REQUISITION-ID') can identify a requisition, preserving exact
   URL identity and queue intake rather than rejecting as secret, while
   'access_token=' sensitive URLs remain rejected.
"""
import pytest
from job_applier.managed import ProtocolError
from job_applier.db_queue import JobQueue, AddJobRequest

try:
    from test_protocol import (
        make_test_service,
        make_clients,
        OPERATOR_TOKEN,
        WORKER_TOKEN,
        WORKER_ID,
    )
except ImportError:
    from tests.jobbot_v1.test_protocol import (
        make_test_service,
        make_clients,
        OPERATOR_TOKEN,
        WORKER_TOKEN,
        WORKER_ID,
    )


_counter = 0


def make_claimed_attempt(s, *, pause=False):
    """Real accepted+claimed fixture, optionally with pause requested."""
    global _counter
    _counter += 1
    idx = _counter
    job = s.intake(url=f"https://careers.example.test/jobs/type-test-{idx}", source_id=f"src-type-{idx}")
    s.eligibility(job["id"], "ready", reason="approved")
    s.identity(
        identity_id=f"cand-types-{idx}",
        person_key=f"p-types-{idx}",
        email=f"types-{idx}@example.test",
        profile={"facts": {"work_auth": "synthetic"}},
    )
    run = s.request_run(
        request_id=f"run-{idx}",
        job_ids=[job["id"]],
        identity_id=f"cand-types-{idx}",
        browser_profile="fixture-browser",
    )
    s.accept_run(
        run["id"],
        worker_id=WORKER_ID,
        session_id=f"sess-{idx}",
        capabilities={
            "protocol": 1,
            "skill_version": "v1.0-test",
            "browser_profile": "fixture-browser",
            "provider": "fixture",
            "model": "fixture-model",
            "telemetry": True,
        },
    )
    attempt = s.claim(run["id"], worker_id=WORKER_ID)
    if pause:
        s.control(run["id"], command="pause")
    return job, run, attempt



@pytest.mark.parametrize(
    "operation,field,bad_value,role",
    [
        ("ack_control", "quiescent", "false", "worker"),
        ("ack_control", "quiescent", 0, "worker"),
        ("reconcile", "browser_quiescent", "false", "operator"),
        ("submission_intent", "fixture", "false", "worker"),
        ("finish", "quiescent", "false", "worker"),
    ],
    ids=[
        "ack_control_quiescent_str_false",
        "ack_control_quiescent_int_0",
        "reconcile_browser_quiescent_str_false",
        "submission_intent_fixture_str_false",
        "finish_quiescent_str_false",
    ],
)
def test_json_strings_and_numbers_for_booleans_rejected_422(
    tmp_path, operation, field,bad_value, role
):
    """JSON strings/numbers passed to booleans must return 422 invalid_payload
    and must not alter control, outcome, or submit_intent.
    """
    s = make_test_service(tmp_path)
    client, op_headers, worker_headers = make_clients(s)
    headers = op_headers if role == "operator" else worker_headers

    pause = operation == "ack_control"
    job, run, attempt = make_claimed_attempt(s, pause=pause)

    if operation == "ack_control":
        payload = {
            "attempt_id": attempt["id"],
            "worker_id": WORKER_ID,
            "fence": attempt["fence"],
            "quiescent": bad_value,
        }
    elif operation == "reconcile":
        payload = {
            "attempt_id": attempt["id"],
            "outcome": "interrupted",
            "evidence": "proof of interruption",
            "browser_quiescent": bad_value,
        }
    elif operation == "submission_intent":
        payload = {
            "attempt_id": attempt["id"],
            "worker_id": WORKER_ID,
            "fence": attempt["fence"],
            "evidence": "fixture intent",
            "fixture": bad_value,
        }
    elif operation == "finish":
        payload = {
            "attempt_id": attempt["id"],
            "worker_id": WORKER_ID,
            "fence": attempt["fence"],
            "outcome": "ready_for_review",
            "evidence": "fixture review",
            "quiescent": bad_value,
        }
    else:
        raise ValueError(f"Unknown operation: {operation}")

    res = client.post(f"/v1/{operation}", json=payload, headers=headers)
    assert res.status_code == 422
    assert res.json().get("error") == "invalid_payload"

    # Verify no state alterations
    with s.tx() as db:
        run_row = dict(db.execute("SELECT * FROM runs WHERE id=?", (run["id"],)).fetchone())
        attempt_row = dict(
            db.execute("SELECT * FROM application_attempts WHERE id=?", (attempt["id"],)).fetchone()
        )

    if operation == "ack_control":
        # quiescent='false' must not incorrectly acknowledge paused
        assert run_row["control"] == "pause_requested"
    elif operation == "reconcile":
        # Operator reconcile browser_quiescent='false' must reject without completed_at
        assert attempt_row["completed_at"] is None
        assert attempt_row["outcome"] is None
    elif operation == "submission_intent":
        # Worker submission_intent fixture='false' must reject without marker
        assert attempt_row["submit_intent_at"] is None
    elif operation == "finish":
        assert attempt_row["completed_at"] is None
        assert attempt_row["outcome"] is None


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("attempt_id", True),
        ("fence", True),
    ],
    ids=["attempt_id_bool_true", "fence_bool_true"],
)
def test_bool_true_supplied_as_id_or_fence_rejected_422(tmp_path, field, bad_value):
    """bool=True supplied as attempt_id/fence must return 422 invalid_payload
    and must not be interpreted as integer 1.
    """
    s = make_test_service(tmp_path)
    client, _, worker_headers = make_clients(s)
    _, run, attempt = make_claimed_attempt(s, pause=True)

    payload = {
        "attempt_id": bad_value if field == "attempt_id" else attempt["id"],
        "worker_id": WORKER_ID,
        "fence": bad_value if field == "fence" else attempt["fence"],
        "quiescent": True,
    }

    res = client.post("/v1/ack_control", json=payload, headers=worker_headers)
    assert res.status_code == 422
    assert res.json().get("error") == "invalid_payload"

    with s.tx() as db:
        run_row = dict(db.execute("SELECT control FROM runs WHERE id=?", (run["id"],)).fetchone())
        assert run_row["control"] == "pause_requested"


def test_genuine_booleans_and_integers_continue_positive_behavior(tmp_path):
    """Genuine booleans and integers succeed and maintain positive behavior."""
    s = make_test_service(tmp_path)
    client, op_headers, worker_headers = make_clients(s)

    # 1. Genuine attempt_id and fence integers, quiescent=True on ack_control
    _, run, attempt = make_claimed_attempt(s, pause=True)
    res_ack = client.post(
        "/v1/ack_control",
        json={
            "attempt_id": attempt["id"],
            "worker_id": WORKER_ID,
            "fence": attempt["fence"],
            "quiescent": True,
        },
        headers=worker_headers,
    )
    assert res_ack.status_code == 200
    assert res_ack.json()["control"] == "paused"

    # 2. Genuine fixture=True on submission_intent
    # First resume run to running control
    s.control(run["id"], command="resume")
    res_intent = client.post(
        "/v1/submission_intent",
        json={
            "attempt_id": attempt["id"],
            "worker_id": WORKER_ID,
            "fence": attempt["fence"],
            "evidence": "valid fixture intent",
            "fixture": True,
        },
        headers=worker_headers,
    )
    assert res_intent.status_code == 200
    assert res_intent.json()["submit_intent_at"] is not None

    # 3. Genuine quiescent=True on finish
    res_finish = client.post(
        "/v1/finish",
        json={
            "attempt_id": attempt["id"],
            "worker_id": WORKER_ID,
            "fence": attempt["fence"],
            "outcome": "applied",
            "evidence": "proof of submission",
            "quiescent": True,
        },
        headers=worker_headers,
    )
    assert res_finish.status_code == 200
    assert res_finish.json()["outcome"] == "applied"

    # 4. Genuine browser_quiescent=True on reconcile for a fresh attempt
    _, _, attempt2 = make_claimed_attempt(s)
    res_recon = client.post(
        "/v1/reconcile",
        json={
            "attempt_id": attempt2["id"],
            "outcome": "interrupted",
            "evidence": "reconciliation proof",
            "browser_quiescent": True,
        },
        headers=op_headers,
    )
    assert res_recon.status_code == 200
    assert res_recon.json()["completed_at"] is not None


def test_legacy_job_queue_token_param_preserved_and_access_token_rejected(tmp_path):
    """JobQueue.add with generic token query parameter preserves exact URL
    and queues intake on managed instance, while access_token remains rejected.
    """
    s = make_test_service(tmp_path)
    queue = JobQueue(db_path=str(s.db_path))

    # Safe fixture job URL: generic query token can identify a requisition
    safe_url = "https://careers.example.test/jobs/form?token=REQUISITION-ID"
    job_record = queue.add(AddJobRequest(url=safe_url))

    assert job_record is not None
    assert job_record.url == safe_url

    # Check managed instance preserved exact URL-identity and queued intake
    job = s.job(job_record.id)
    assert job["status"] == "queued"
    assert job["url"] == safe_url

    # Sensitive access_token URL must still be rejected
    sensitive_url = "https://careers.example.test/jobs/form?access_token=SECRET-TOKEN"
    with pytest.raises(ProtocolError, match="sensitive_url"):
        queue.add(AddJobRequest(url=sensitive_url))
