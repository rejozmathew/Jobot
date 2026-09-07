"""Protocol acceptance tests for JobBot managed API and client.

Verifies:
1) Authentication (Bearer tokens) and instance binding (X-JobBot-Instance).
2) Origin header / CSRF rejection.
3) Role-based access control and worker ID binding.
4) Response error safety (no raw payloads/secrets leaked).
5) End-to-end operator/worker HTTP lifecycle (intake -> eligibility -> identity -> request_run -> accept_run -> claim -> event -> finish -> claim None).
6) Capability failures visibly preserved in awaiting_worker state.
7) Managed Client abstraction.
8) Clean subprocess isolation: create_app imports without browser_use or Hermes.
"""
from pathlib import Path
import subprocess
import sys
import pytest
from fastapi.testclient import TestClient

from job_applier.managed import Service, ProtocolError
from job_applier.managed_api import create_app
from job_applier.managed_client import Client

OPERATOR_TOKEN = "synthetic-operator-test-token"
WORKER_TOKEN = "synthetic-worker-test-token"
WORKER_ID = "worker"
BASE_URL = "http://127.0.0.1:8769"


def make_test_service(tmp_path, instance_id="synthetic-proto-test"):
    return Service.create(
        tmp_path / "proto.db",
        instance_id=instance_id,
        settings={"mode": "development"},
    )


def make_clients(s, operator_token=OPERATOR_TOKEN, worker_tokens=None):
    if worker_tokens is None:
        worker_tokens = {WORKER_TOKEN: WORKER_ID}
    app = create_app(s, operator_token=operator_token, worker_tokens=worker_tokens)
    client = TestClient(app, base_url=BASE_URL)
    op_headers = {
        "Authorization": f"Bearer {operator_token}",
        "X-JobBot-Instance": s.instance_id,
    }
    worker_headers = {
        "Authorization": f"Bearer {WORKER_TOKEN}",
        "X-JobBot-Instance": s.instance_id,
    }
    return client, op_headers, worker_headers


def test_auth_missing_or_invalid_rejects_401(tmp_path):
    s = make_test_service(tmp_path)
    client, op_headers, _ = make_clients(s)

    # 1. Missing Authorization header -> 401
    res = client.get("/v1/health", headers={"X-JobBot-Instance": s.instance_id})
    assert res.status_code == 401

    # 2. Invalid Bearer token -> 401
    res = client.get(
        "/v1/health",
        headers={
            "Authorization": "Bearer invalid-token",
            "X-JobBot-Instance": s.instance_id,
        },
    )
    assert res.status_code == 401

    # 3. Unauthorized POST operation -> 401
    res = client.post(
        "/v1/intake",
        json={"url": "https://careers.example.test/jobs/1"},
        headers={"X-JobBot-Instance": s.instance_id},
    )
    assert res.status_code == 401


def test_instance_header_mismatch_rejects_409(tmp_path):
    s = make_test_service(tmp_path)
    client, _, _ = make_clients(s)

    # 1. Missing X-JobBot-Instance header -> 409
    res = client.get(
        "/v1/health",
        headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"},
    )
    assert res.status_code == 409

    # 2. Wrong X-JobBot-Instance header -> 409
    res = client.get(
        "/v1/health",
        headers={
            "Authorization": f"Bearer {OPERATOR_TOKEN}",
            "X-JobBot-Instance": "wrong-instance-id",
        },
    )
    assert res.status_code == 409

    # 3. Valid credentials and instance header -> 200
    res = client.get(
        "/v1/health",
        headers={
            "Authorization": f"Bearer {OPERATOR_TOKEN}",
            "X-JobBot-Instance": s.instance_id,
        },
    )
    assert res.status_code == 200
    assert res.json()["instance_id"] == s.instance_id


def test_origin_header_forbidden_even_if_authorized(tmp_path):
    s = make_test_service(tmp_path)
    client, op_headers, worker_headers = make_clients(s)

    # Operator request with untrusted origin -> 403
    headers = dict(op_headers)
    headers["Origin"] = "https://evil.example"
    res = client.get("/v1/health", headers=headers)
    assert res.status_code == 403

    # Worker request with untrusted origin -> 403
    w_headers = dict(worker_headers)
    w_headers["Origin"] = "https://evil.example"
    res = client.get("/v1/health", headers=w_headers)
    assert res.status_code == 403


def test_unknown_operation_and_bad_payload_handling(tmp_path):
    s = make_test_service(tmp_path)
    client, op_headers, _ = make_clients(s)

    # Unknown operation -> 404
    res = client.post(
        "/v1/non_existent_operation",
        json={"some": "payload"},
        headers=op_headers,
    )
    assert res.status_code == 404

    # Bad payload / schema error -> 422
    res = client.post(
        "/v1/intake",
        json={"bad_key": 123},
        headers=op_headers,
    )
    assert res.status_code == 422


def test_response_errors_do_not_echo_raw_secrets(tmp_path):
    s = make_test_service(tmp_path)
    client, op_headers, _ = make_clients(s)

    secret_sentinel = "SUPER_SECRET_TOKEN_XYZ123_DO_NOT_LEAK"
    secret_password = "MY_SECRET_PLAINTEXT_PASSWORD_456"

    # Send bad payload containing secrets to trigger an error
    res = client.post(
        "/v1/identity",
        json={
            "identity_id": "candidate-test",
            "person_key": "person-1",
            "email": "invalid-email-no-at",
            "profile": {
                "password": secret_password,
                "token": secret_sentinel,
            },
        },
        headers=op_headers,
    )
    assert res.status_code in (400, 422)
    assert secret_sentinel not in res.text
    assert secret_password not in res.text


def test_role_permissions_and_worker_id_binding(tmp_path):
    s = make_test_service(tmp_path)
    client, op_headers, worker_headers = make_clients(s)

    # 1. Operator MUST NOT masquerade as worker for claim -> 403
    res = client.post(
        "/v1/claim",
        json={"run_id": "any-run-id", "worker_id": "worker"},
        headers=op_headers,
    )
    assert res.status_code == 403

    # 2. Worker token bound to worker_id='worker': different worker_id must reject 403
    res = client.post(
        "/v1/claim",
        json={"run_id": "any-run-id", "worker_id": "different-worker-id"},
        headers=worker_headers,
    )
    assert res.status_code == 403

    # 3. Worker cannot perform operator-only operations:
    # Worker cannot request_run -> 403
    res = client.post(
        "/v1/request_run",
        json={
            "request_id": "req-1",
            "job_ids": ["job-1"],
            "identity_id": "cand-1",
            "browser_profile": "prof-1",
        },
        headers=worker_headers,
    )
    assert res.status_code == 403

    # Worker cannot identity edit -> 403
    res = client.post(
        "/v1/identity",
        json={
            "identity_id": "cand-1",
            "person_key": "p-1",
            "email": "c@example.test",
            "profile": {},
        },
        headers=worker_headers,
    )
    assert res.status_code == 403

    # Worker cannot reconcile -> 403
    res = client.post(
        "/v1/reconcile",
        json={
            "attempt_id": 1,
            "outcome": "interrupted",
            "evidence": "proof",
            "browser_quiescent": True,
        },
        headers=worker_headers,
    )
    assert res.status_code == 403


def test_end_to_end_http_application_flow(tmp_path):
    """C1: End-to-end HTTP workflow from intake through finish.

    Operator performs intake -> eligibility -> identity -> request_run.
    Worker performs accept_run -> claim -> event -> finish -> claim None.
    Final job status is ready_for_review.
    """
    s = make_test_service(tmp_path)
    client, op_headers, worker_headers = make_clients(s)

    # 1. Operator: intake
    intake_res = client.post(
        "/v1/intake",
        json={
            "url": "https://careers.example.test/jobs/e2e-role-1",
            "source_id": "e2e-src-1",
            "company": "E2E Corp",
            "title": "Protocol Engineer",
        },
        headers=op_headers,
    )
    assert intake_res.status_code == 200
    job_id = intake_res.json()["id"]

    # 2. Operator: eligibility
    elig_res = client.post(
        "/v1/eligibility",
        json={
            "job_id": job_id,
            "decision": "ready",
            "reason": "operator test approval",
        },
        headers=op_headers,
    )
    assert elig_res.status_code == 200
    assert elig_res.json()["eligibility"] == "ready"

    # 3. Operator: identity
    ident_res = client.post(
        "/v1/identity",
        json={
            "identity_id": "cand-e2e",
            "person_key": "person-e2e",
            "email": "cand@example.test",
            "profile": {"facts": {"work_auth": "synthetic"}},
        },
        headers=op_headers,
    )
    assert ident_res.status_code == 200

    # 4. Operator: request_run
    req_res = client.post(
        "/v1/request_run",
        json={
            "request_id": "run-req-e2e-1",
            "job_ids": [job_id],
            "identity_id": "cand-e2e",
            "browser_profile": "e2e-browser",
        },
        headers=op_headers,
    )
    assert req_res.status_code == 200
    run_data = req_res.json()
    run_id = run_data["id"]
    assert run_data["state"] == "awaiting_worker"

    # 5. Worker: accept_run
    capabilities = {
        "protocol": 1,
        "skill_version": "v1.0-test",
        "browser_profile": "e2e-browser",
        "provider": "fixture",
        "model": "fixture-model",
        "telemetry": True,
    }
    accept_res = client.post(
        "/v1/accept_run",
        json={
            "run_id": run_id,
            "worker_id": WORKER_ID,
            "session_id": "session-e2e-1",
            "capabilities": capabilities,
        },
        headers=worker_headers,
    )
    assert accept_res.status_code == 200
    assert accept_res.json()["state"] == "accepted"

    # 6. Worker: claim
    claim_res = client.post(
        "/v1/claim",
        json={"run_id": run_id, "worker_id": WORKER_ID},
        headers=worker_headers,
    )
    assert claim_res.status_code == 200
    attempt = claim_res.json()
    attempt_id = attempt["id"]
    fence = attempt["fence"]
    assert attempt["job_id"] == job_id

    # 7. Worker: event
    event_res = client.post(
        "/v1/event",
        json={
            "attempt_id": attempt_id,
            "worker_id": WORKER_ID,
            "fence": fence,
            "event_id": "ev-e2e-1",
            "event_type": "checkpoint",
            "observed_at": "2026-09-06T12:00:00+00:00",
            "payload": {"phase": "testing_fill"},
        },
        headers=worker_headers,
    )
    assert event_res.status_code == 200

    # 8. Worker: finish
    finish_res = client.post(
        "/v1/finish",
        json={
            "attempt_id": attempt_id,
            "worker_id": WORKER_ID,
            "fence": fence,
            "outcome": "ready_for_review",
            "evidence": "e2e review verification",
            "quiescent": True,
        },
        headers=worker_headers,
    )
    assert finish_res.status_code == 200
    assert finish_res.json()["outcome"] == "ready_for_review"

    # 9. Worker: claim None (all jobs in run processed)
    claim_next = client.post(
        "/v1/claim",
        json={"run_id": run_id, "worker_id": WORKER_ID},
        headers=worker_headers,
    )
    assert claim_next.status_code == 200
    assert claim_next.json() is None

    # 10. Check final job status
    job_res = client.post(
        "/v1/job",
        json={"job_id": job_id},
        headers=op_headers,
    )
    assert job_res.status_code == 200
    assert job_res.json()["status"] == "ready_for_review"
    assert s.job(job_id)["status"] == "ready_for_review"


def test_capability_failure_visibly_awaiting_worker(tmp_path):
    """C2: Capability mismatch preserves awaiting_worker state."""
    s = make_test_service(tmp_path)
    client, op_headers, worker_headers = make_clients(s)

    # Setup job and run via operator
    job = s.intake(url="https://careers.example.test/jobs/cap-fail", source_id="cap-1")
    s.eligibility(job["id"], "ready", reason="approved")
    s.identity(
        identity_id="cand-cap",
        person_key="p-cap",
        email="cap@example.test",
        profile={"facts": {"auth": "ok"}},
    )
    r = s.request_run(
        request_id="req-cap-1",
        job_ids=[job["id"]],
        identity_id="cand-cap",
        browser_profile="fixture-browser",
    )
    assert r["state"] == "awaiting_worker"

    # Worker attempts accept_run with unsupported capability (protocol 99 != 1)
    bad_caps = {
        "protocol": 99,
        "skill_version": "v1",
        "browser_profile": "fixture-browser",
        "provider": "fixture",
        "model": "fixture",
        "telemetry": True,
    }
    accept_res = client.post(
        "/v1/accept_run",
        json={
            "run_id": r["id"],
            "worker_id": WORKER_ID,
            "session_id": "sess-cap",
            "capabilities": bad_caps,
        },
        headers=worker_headers,
    )
    assert accept_res.status_code in (400, 422)

    # Verify run state remains visibly awaiting_worker in service
    with s.tx() as db:
        run_row = dict(db.execute("SELECT * FROM runs WHERE id=?", (r["id"],)).fetchone())
        assert run_row["state"] == "awaiting_worker"

    # Worker attempt to claim without successful accept must reject
    claim_res = client.post(
        "/v1/claim",
        json={"run_id": r["id"], "worker_id": WORKER_ID},
        headers=worker_headers,
    )
    assert claim_res.status_code in (400, 403, 409, 422)


def test_managed_client_call(tmp_path):
    s = make_test_service(tmp_path)
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID})
    test_client = TestClient(app, base_url=BASE_URL)
    # Explicit in-process transport: never fall through to a real localhost service.
    import httpx
    class InProcessTransport(httpx.BaseTransport):
        def handle_request(self, request):
            result = test_client.request(request.method, request.url.path, headers=dict(request.headers), content=request.content)
            return httpx.Response(result.status_code, headers=result.headers, content=result.content)
    transport = InProcessTransport()

    client = Client(
        base_url=BASE_URL,
        instance_id=s.instance_id,
        token=OPERATOR_TOKEN,
        transport=transport,
    )
    res = client.call("health")
    assert res["instance_id"] == s.instance_id


def test_clean_subprocess_import_isolation():
    """Crucial test: create_app does not import browser_use or Hermes in clean environment."""
    repo_root = str(Path(__file__).parents[2])
    script = (
        "import sys\n"
        "from job_applier.managed_api import create_app\n"
        "leaked = [m for m in sys.modules if 'browser_use' in m or ('hermes' in m.lower() and 'hermes' not in sys.prefix.lower())]\n"
        "if leaked:\n"
        "    print(f'Leaked modules: {leaked}', file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "sys.exit(0)\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert res.returncode == 0, f"Clean subprocess import failed or leaked modules:\n{res.stderr}"
