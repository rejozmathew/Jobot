"""Tests for owned attempt mail protocol and API scoping (expected RED).

Covers:
1. Service-level owned mail lifecycle:
   - request_mail_for_attempt derives candidate identity from owned attempt
   - Permits only job host or verified namespace alias
   - Persists request-attempt binding and uses mail_request correlation contract
   - match_mail_for_attempt validates attempt ownership & binding
   - Returns only matching message_id (no body/code exposed)
   - Unmatched messages return None; multiple matching messages raise ambiguous_mail
2. Safety guards and rejections:
   - Rejects wrong worker_id or stale fence
   - Rejects unverified / unrelated namespaces not aliased to job host
   - Rejects invalid purpose or expected_sender format
   - Rejects cross-attempt request matching (request bound to attempt A cannot match in attempt B)
3. HTTP API role boundary enforcement & worker scoping:
   - /v1/mail_request and /v1/match_mail are operator-only (workers rejected with 403 role_forbidden)
   - /v1/request_mail_for_attempt and /v1/match_mail_for_attempt are worker-scoped (operator gets 403 role_forbidden)
   - Workers cannot invoke owned mail endpoints for unowned attempts (403 attempt_forbidden / worker_identity_mismatch)
   - Authorized worker can successfully execute owned mail protocol via /v1 endpoints
"""
import pytest
from fastapi.testclient import TestClient

from job_applier.managed import Service, ProtocolError
from job_applier.managed_api import create_app

OPERATOR_TOKEN = "synthetic-operator-token-min24chars"
WORKER_TOKEN = "synthetic-worker-token-min24chars"
WORKER_ID = "worker-1"
OTHER_WORKER_TOKEN = "synthetic-other-token-min24chars"
OTHER_WORKER_ID = "worker-2"
BASE_URL = "http://127.0.0.1:8769"


def _setup_service(tmp_path, instance_id="test-owned-mail"):
    s = Service.create(
        tmp_path / "owned_mail.db",
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


def _create_claimed_attempt(s, *, url="https://careers.example.test/jobs/101", worker_id=WORKER_ID, identity_id="cand-1", run_req_id="run-req-1"):
    job = s.intake(url=url, source_id="src-1")
    s.eligibility(job["id"], "ready", reason="synthetic operator approval")
    run = s.request_run(
        request_id=run_req_id,
        job_ids=[job["id"]],
        identity_id=identity_id,
        browser_profile=f"browser-{identity_id}",
    )
    s.accept_run(
        run["id"],
        worker_id=worker_id,
        session_id=f"session-{worker_id}",
        capabilities={
            "protocol": 1,
            "skill_version": "test-skill",
            "browser_profile": f"browser-{identity_id}",
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )
    attempt = s.claim(run["id"], worker_id=worker_id)
    return job, run, attempt


def test_owned_mail_request_and_match_lifecycle_with_alias_binding(tmp_path):
    """1. request_mail_for_attempt derives identity from attempt, validates verified alias,
    persists request-attempt binding, and match_mail_for_attempt correlates metadata only.
    """
    s = _setup_service(tmp_path)
    job, run, attempt = _create_claimed_attempt(
        s,
        url="https://careers.example.test/jobs/101",
        worker_id=WORKER_ID,
        identity_id="cand-1",
    )

    # Register verified namespace alias for the job host
    s.namespace_alias(
        alias="careers.example.test",
        canonical="auth.example.test/tenant",
        verification_evidence="Verified SSO redirect chain",
    )

    # Worker requests mail correlation for owned attempt using verified alias namespace
    req = s.request_mail_for_attempt(
        attempt_id=attempt["id"],
        worker_id=WORKER_ID,
        fence=attempt["fence"],
        namespace="auth.example.test/tenant",
        purpose="email_verification",
        requested_at="2026-09-07T12:00:00+00:00",
        expected_sender="auth@example.test",
    )
    assert isinstance(req, dict)
    req_id = req.get("id") or req.get("request_id")
    assert req_id
    # Candidate identity is derived from owned attempt
    assert req.get("identity_id") == "cand-1"
    assert req.get("purpose") == "email_verification"
    assert req.get("expected_sender") == "auth@example.test"

    # Match mail against supplied metadata: only message_id returned, bodies/codes omitted
    valid_message = {
        "id": "msg-101",
        "recipient": "cand1@example.test",
        "sender": "auth@example.test",
        "namespace": "auth.example.test/tenant",
        "purpose": "email_verification",
        "received_at": "2026-09-07T12:01:00+00:00",
        "code": "SYNTHETIC_CODE_MUST_NOT_LEAK",
        "body": "Your verification code is 123456",
    }
    match_result = s.match_mail_for_attempt(
        attempt_id=attempt["id"],
        worker_id=WORKER_ID,
        fence=attempt["fence"],
        request_id=req_id,
        messages=[valid_message],
    )
    assert match_result == {"message_id": "msg-101"}
    assert "code" not in match_result
    assert "body" not in match_result

    # Non-matching message (wrong recipient) returns None
    wrong_recipient = {**valid_message, "id": "msg-wrong-rcpt", "recipient": "other@example.test"}
    assert s.match_mail_for_attempt(
        attempt_id=attempt["id"],
        worker_id=WORKER_ID,
        fence=attempt["fence"],
        request_id=req_id,
        messages=[wrong_recipient],
    ) is None

    # Ambiguous match (multiple matching messages) raises explicit ProtocolError
    duplicate_match = {**valid_message, "id": "msg-102", "received_at": "2026-09-07T12:02:00+00:00"}
    with pytest.raises(ProtocolError, match="ambiguous_mail"):
        s.match_mail_for_attempt(
            attempt_id=attempt["id"],
            worker_id=WORKER_ID,
            fence=attempt["fence"],
            request_id=req_id,
            messages=[valid_message, duplicate_match],
        )


def test_owned_mail_guards_reject_wrong_owner_fence_binding_and_unverified_namespace(tmp_path):
    """2. Service rejects wrong worker owner, fence mismatch, unverified namespace,
    invalid purpose/sender, and cross-attempt request tampering.
    """
    s = _setup_service(tmp_path)
    job1, run1, attempt1 = _create_claimed_attempt(
        s,
        url="https://portal.example.test/jobs/201",
        worker_id=WORKER_ID,
        identity_id="cand-1",
        run_req_id="run-req-1",
    )
    job2, run2, attempt2 = _create_claimed_attempt(
        s,
        url="https://other.example.test/jobs/202",
        worker_id=OTHER_WORKER_ID,
        identity_id="cand-2",
        run_req_id="run-req-2",
    )

    # 1. Reject wrong owner / worker mismatch on request_mail_for_attempt
    with pytest.raises(ProtocolError):
        s.request_mail_for_attempt(
            attempt_id=attempt1["id"],
            worker_id=OTHER_WORKER_ID,
            fence=attempt1["fence"],
            namespace="portal.example.test",
            purpose="email_verification",
            requested_at="2026-09-07T12:00:00+00:00",
            expected_sender="auth@portal.example.test",
        )

    # 2. Reject stale / invalid fence
    with pytest.raises(ProtocolError):
        s.request_mail_for_attempt(
            attempt_id=attempt1["id"],
            worker_id=WORKER_ID,
            fence=attempt1["fence"] + 1,
            namespace="portal.example.test",
            purpose="email_verification",
            requested_at="2026-09-07T12:00:00+00:00",
            expected_sender="auth@portal.example.test",
        )

    # 3. Reject unverified / unrelated namespace (not matching job host or registered alias)
    with pytest.raises(ProtocolError):
        s.request_mail_for_attempt(
            attempt_id=attempt1["id"],
            worker_id=WORKER_ID,
            fence=attempt1["fence"],
            namespace="unrelated-phishing.test",
            purpose="email_verification",
            requested_at="2026-09-07T12:00:00+00:00",
            expected_sender="auth@portal.example.test",
        )

    # 4. Reject invalid purpose
    with pytest.raises(ProtocolError):
        s.request_mail_for_attempt(
            attempt_id=attempt1["id"],
            worker_id=WORKER_ID,
            fence=attempt1["fence"],
            namespace="portal.example.test",
            purpose="marketing_blast",
            requested_at="2026-09-07T12:00:00+00:00",
            expected_sender="auth@portal.example.test",
        )

    # Create a legitimate request bound to attempt 1
    req1 = s.request_mail_for_attempt(
        attempt_id=attempt1["id"],
        worker_id=WORKER_ID,
        fence=attempt1["fence"],
        namespace="portal.example.test",
        purpose="email_verification",
        requested_at="2026-09-07T12:00:00+00:00",
        expected_sender="auth@portal.example.test",
    )
    req1_id = req1.get("id") or req1.get("request_id")

    # 5. Reject cross-attempt matching: attempt2 worker cannot match a request bound to attempt1
    msg_for_cand1 = {
        "id": "msg-cross-1",
        "recipient": "cand1@example.test",
        "sender": "auth@portal.example.test",
        "namespace": "portal.example.test",
        "purpose": "email_verification",
        "received_at": "2026-09-07T12:01:00+00:00",
    }
    with pytest.raises(ProtocolError):
        s.match_mail_for_attempt(
            attempt_id=attempt2["id"],
            worker_id=OTHER_WORKER_ID,
            fence=attempt2["fence"],
            request_id=req1_id,
            messages=[msg_for_cand1],
        )

    # 6. Reject matching with mismatched fence on attempt 1
    with pytest.raises(ProtocolError):
        s.match_mail_for_attempt(
            attempt_id=attempt1["id"],
            worker_id=WORKER_ID,
            fence=attempt1["fence"] + 1,
            request_id=req1_id,
            messages=[msg_for_cand1],
        )


def test_owned_mail_api_role_boundaries_and_worker_scoping(tmp_path):
    """3. HTTP API enforces role boundaries:
    - Worker cannot call operator mail_request / match_mail (403 role_forbidden)
    - Operator cannot call worker request_mail_for_attempt / match_mail_for_attempt (403 role_forbidden)
    - Worker cannot call owned mail endpoints for unowned attempts (403 attempt_forbidden)
    - Authorized worker successfully requests and matches mail via worker-scoped endpoints
    """
    s = _setup_service(tmp_path)
    job, run, attempt = _create_claimed_attempt(
        s,
        url="https://careers.example.test/jobs/301",
        worker_id=WORKER_ID,
        identity_id="cand-1",
    )

    app = create_app(
        s,
        operator_token=OPERATOR_TOKEN,
        worker_tokens={WORKER_TOKEN: WORKER_ID, OTHER_WORKER_TOKEN: OTHER_WORKER_ID},
    )
    client = TestClient(app, base_url=BASE_URL)

    op_headers = {
        "Authorization": f"Bearer {OPERATOR_TOKEN}",
        "X-JobBot-Instance": s.instance_id,
    }
    worker_headers = {
        "Authorization": f"Bearer {WORKER_TOKEN}",
        "X-JobBot-Instance": s.instance_id,
    }
    other_worker_headers = {
        "Authorization": f"Bearer {OTHER_WORKER_TOKEN}",
        "X-JobBot-Instance": s.instance_id,
    }

    # 1. Worker cannot call unrestricted operator /v1/mail_request (403 role_forbidden)
    res = client.post(
        "/v1/mail_request",
        headers=worker_headers,
        json={
            "identity_id": "cand-1",
            "namespace": "careers.example.test",
            "purpose": "email_verification",
            "requested_at": "2026-09-07T12:00:00+00:00",
            "expected_sender": "auth@example.test",
        },
    )
    assert res.status_code == 403
    assert res.json()["error"] == "role_forbidden"

    # 2. Worker cannot call unrestricted operator /v1/match_mail (403 role_forbidden)
    res = client.post(
        "/v1/match_mail",
        headers=worker_headers,
        json={"request_id": "req-dummy", "messages": []},
    )
    assert res.status_code == 403
    assert res.json()["error"] == "role_forbidden"

    # 3. Operator cannot call worker-scoped /v1/request_mail_for_attempt (403 role_forbidden)
    res = client.post(
        "/v1/request_mail_for_attempt",
        headers=op_headers,
        json={
            "attempt_id": attempt["id"],
            "worker_id": WORKER_ID,
            "fence": attempt["fence"],
            "namespace": "careers.example.test",
            "purpose": "email_verification",
            "requested_at": "2026-09-07T12:00:00+00:00",
            "expected_sender": "auth@example.test",
        },
    )
    assert res.status_code == 403
    assert res.json()["error"] == "role_forbidden"

    # 4. Other worker cannot call /v1/request_mail_for_attempt on unowned attempt (403 attempt_forbidden)
    res = client.post(
        "/v1/request_mail_for_attempt",
        headers=other_worker_headers,
        json={
            "attempt_id": attempt["id"],
            "worker_id": OTHER_WORKER_ID,
            "fence": attempt["fence"],
            "namespace": "careers.example.test",
            "purpose": "email_verification",
            "requested_at": "2026-09-07T12:00:00+00:00",
            "expected_sender": "auth@example.test",
        },
    )
    assert res.status_code == 403
    assert res.json()["error"] in ("attempt_forbidden", "worker_identity_mismatch")

    # 5. Authorized worker successfully calls /v1/request_mail_for_attempt on owned attempt
    req_res = client.post(
        "/v1/request_mail_for_attempt",
        headers=worker_headers,
        json={
            "attempt_id": attempt["id"],
            "worker_id": WORKER_ID,
            "fence": attempt["fence"],
            "namespace": "careers.example.test",
            "purpose": "email_verification",
            "requested_at": "2026-09-07T12:00:00+00:00",
            "expected_sender": "auth@example.test",
        },
    )
    assert req_res.status_code == 200
    req_data = req_res.json()
    req_id = req_data.get("id") or req_data.get("request_id")
    assert req_id
    assert req_data.get("identity_id") == "cand-1"

    # 6. Authorized worker successfully calls /v1/match_mail_for_attempt on owned attempt
    match_res = client.post(
        "/v1/match_mail_for_attempt",
        headers=worker_headers,
        json={
            "attempt_id": attempt["id"],
            "worker_id": WORKER_ID,
            "fence": attempt["fence"],
            "request_id": req_id,
            "messages": [
                {
                    "id": "msg-api-301",
                    "recipient": "cand1@example.test",
                    "sender": "auth@example.test",
                    "namespace": "careers.example.test",
                    "purpose": "email_verification",
                    "received_at": "2026-09-07T12:01:00+00:00",
                    "code": "SECRET_OTP",
                }
            ],
        },
    )
    assert match_res.status_code == 200
    assert match_res.json() == {"message_id": "msg-api-301"}
