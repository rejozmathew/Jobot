"""Stage 3 operator UI and cookie-based authentication contract tests.

Contracts covered (<= 6 concise tests):
1. Unauthenticated GET / serves static login/bootstrap HTML without leaking DB path, candidate
   data, or tokens; GET /static/jobbot.js and /static/jobbot.css serve static assets without token leaks.
2. JSON POST /login with operator token returns instance_id and sets an opaque HttpOnly SameSite=Strict
   cookie (not the raw operator token).
3. Incorrect tokens and worker tokens cannot log in as operator; neither bodies nor error responses
   echo the supplied token.
4. Cookie session + X-JobBot-Instance permits /v1/view; POST /logout revokes the session.
5. Original bearer worker API (and operator bearer API) remains fully functional with existing protections.
6. Cross-origin login and control requests are rejected (403), wrong instance rejected (409), and tokens
   are rejected from query strings.
"""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from job_applier.managed import Service
from job_applier.managed_api import create_app

OPERATOR_TOKEN = "synthetic-operator-token-jobbot-v1-32chars"
WORKER_TOKEN = "synthetic-worker-token-jobbot-v1-32chars"
WORKER_ID = "worker-1"
BASE_URL = "http://127.0.0.1:8769"


def make_test_environment(tmp_path):
    s = Service.create(tmp_path / "jobs.db", instance_id="test-instance-ui")
    s.identity(
        identity_id="candidate",
        person_key="person",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "fixture-work-auth"}, "resume_ref": "asset:fixture-v1"},
    )
    job = s.intake(url="https://careers.example.test/jobs/0", source_id="0")
    s.eligibility(job["id"], "ready", reason="synthetic operator approval")
    r = s.request_run(
        request_id="request-1",
        job_ids=[job["id"]],
        identity_id="candidate",
        browser_profile="fixture-browser",
    )
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID})
    return s, r, app


def test_static_assets_and_unauthenticated_root_served_without_leaks(tmp_path):
    """1. GET / returns static login HTML without secrets; /static/jobbot.js and .css serve static assets."""
    s, _, app = make_test_environment(tmp_path)
    client = TestClient(app, base_url=BASE_URL)

    # 1. Unauthenticated root serves bootstrap/login HTML
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "text/html" in res_root.headers.get("content-type", "").lower()

    # Must NOT leak resolved DB path, candidate data, or raw tokens
    root_text = res_root.text
    assert str(s.db_path) not in root_text
    assert s.db_path.name not in root_text
    assert "candidate@example.test" not in root_text
    assert "fixture-work-auth" not in root_text
    assert OPERATOR_TOKEN not in root_text
    assert WORKER_TOKEN not in root_text
    assert "localstorage" not in root_text.lower()

    # 2. Fixed static assets are served
    res_js = client.get("/static/jobbot.js")
    assert res_js.status_code == 200
    assert any(ct in res_js.headers.get("content-type", "").lower() for ct in ("javascript", "text/plain"))
    assert OPERATOR_TOKEN not in res_js.text

    res_css = client.get("/static/jobbot.css")
    assert res_css.status_code == 200
    assert "css" in res_css.headers.get("content-type", "").lower()


def test_operator_login_sets_opaque_httponly_samesite_cookie(tmp_path):
    """2. POST /login with operator token returns instance_id and sets opaque HttpOnly SameSite=Strict cookie."""
    s, _, app = make_test_environment(tmp_path)
    client = TestClient(app, base_url=BASE_URL)

    res = client.post("/login", json={"token": OPERATOR_TOKEN})
    assert res.status_code == 200
    data = res.json()
    assert data.get("instance_id") == s.instance_id
    assert OPERATOR_TOKEN not in res.text

    # Cookie attributes: opaque, HttpOnly, SameSite=Strict
    set_cookie = res.headers.get("set-cookie", "")
    assert set_cookie != ""
    assert "httponly" in set_cookie.lower()
    assert "samesite=strict" in set_cookie.lower()
    assert OPERATOR_TOKEN not in set_cookie

    cookies = dict(client.cookies)
    assert len(cookies) > 0
    assert all(val != OPERATOR_TOKEN for val in cookies.values())


def test_login_rejects_worker_and_invalid_tokens_without_token_echo(tmp_path):
    """3. Worker or invalid token cannot log in as operator; error responses never echo the token."""
    s, _, app = make_test_environment(tmp_path)
    client = TestClient(app, base_url=BASE_URL)

    invalid_token = "invalid-operator-token-jobbot-v1-99chars"
    res_invalid = client.post("/login", json={"token": invalid_token})
    assert res_invalid.status_code in (401, 403)
    assert invalid_token not in res_invalid.text
    assert not client.cookies

    res_worker = client.post("/login", json={"token": WORKER_TOKEN})
    assert res_worker.status_code in (401, 403)
    assert WORKER_TOKEN not in res_worker.text
    assert not client.cookies


def test_cookie_session_with_instance_permits_view_and_logout_revokes_it(tmp_path):
    """4. Cookie session + X-JobBot-Instance permits /v1/view; POST /logout revokes the session."""
    s, _, app = make_test_environment(tmp_path)
    client = TestClient(app, base_url=BASE_URL)

    # Log in as operator to obtain cookie
    res_login = client.post("/login", json={"token": OPERATOR_TOKEN})
    assert res_login.status_code == 200
    captured_cookies = dict(client.cookies)

    # Valid session + instance header permits /v1/view
    res_view = client.post("/v1/view", json={}, headers={"X-JobBot-Instance": s.instance_id})
    assert res_view.status_code == 200
    assert "health" in res_view.json()

    # Logout revokes session
    res_logout = client.post("/logout", headers={"X-JobBot-Instance": s.instance_id})
    assert res_logout.status_code in (200, 204)

    # Subsequent /v1/view with current client is unauthorized
    res_after = client.post("/v1/view", json={}, headers={"X-JobBot-Instance": s.instance_id})
    assert res_after.status_code == 401

    # Fresh client attempting to replay the old cookie is also unauthorized
    replay_client = TestClient(app, base_url=BASE_URL, cookies=captured_cookies)
    res_replay = replay_client.post("/v1/view", json={}, headers={"X-JobBot-Instance": s.instance_id})
    assert res_replay.status_code == 401


def test_original_bearer_worker_and_operator_api_still_works(tmp_path):
    """5. Original bearer token authentication for worker and operator continues to function."""
    s, r, app = make_test_environment(tmp_path)
    client = TestClient(app, base_url=BASE_URL)

    op_headers = {
        "Authorization": f"Bearer {OPERATOR_TOKEN}",
        "X-JobBot-Instance": s.instance_id,
    }
    worker_headers = {
        "Authorization": f"Bearer {WORKER_TOKEN}",
        "X-JobBot-Instance": s.instance_id,
    }

    # Operator bearer can view and settings_view
    res_op = client.post("/v1/view", json={}, headers=op_headers)
    assert res_op.status_code == 200
    res_settings = client.post("/v1/settings_view", json={}, headers=op_headers)
    assert res_settings.status_code == 200

    # Worker bearer can perform worker operation (accept_run)
    res_worker = client.post(
        "/v1/accept_run",
        json={
            "run_id": r["id"],
            "worker_id": WORKER_ID,
            "session_id": "session-ui-1",
            "capabilities": {
                "protocol": 1,
                "skill_version": "test",
                "browser_profile": r["browser_profile"],
                "provider": "fixture",
                "model": "fixture",
                "telemetry": True,
            },
        },
        headers=worker_headers,
    )
    assert res_worker.status_code == 200

    # Worker bearer remains forbidden from operator-only endpoints
    res_forbidden = client.post("/v1/view", json={}, headers=worker_headers)
    assert res_forbidden.status_code == 403


def test_security_origin_instance_mismatch_and_no_token_in_url(tmp_path):
    """6. Untrusted origins, instance mismatches, and tokens in query strings are rejected."""
    s, _, app = make_test_environment(tmp_path)
    client = TestClient(app, base_url=BASE_URL)

    # Cross-origin login rejected
    res_cors_login = client.post(
        "/login",
        json={"token": OPERATOR_TOKEN},
        headers={"Origin": "http://untrusted-origin.example.test"},
    )
    assert res_cors_login.status_code == 403

    # Authenticate legitimately
    res_login = client.post("/login", json={"token": OPERATOR_TOKEN})
    assert res_login.status_code == 200

    # Cross-origin control request with session cookie rejected
    res_cors_view = client.post(
        "/v1/view",
        json={},
        headers={
            "Origin": "http://untrusted-origin.example.test",
            "X-JobBot-Instance": s.instance_id,
        },
    )
    assert res_cors_view.status_code == 403

    # Instance mismatch with session cookie rejected
    res_inst_mismatch = client.post(
        "/v1/view",
        json={},
        headers={"X-JobBot-Instance": "wrong-instance-identifier"},
    )
    assert res_inst_mismatch.status_code == 409

    # Tokens in query strings are rejected and never echoed
    res_query_login = client.post(f"/login?token={OPERATOR_TOKEN}")
    assert res_query_login.status_code in (401, 422)
    assert OPERATOR_TOKEN not in res_query_login.text
