"""Resource protocol acceptance tests for JobBot managed API.

Covers:
1. test_operator_resource_endpoints_succeed_and_reject_anonymous:
   Exposes operator resource methods via /v1/ (lesson_observe, lesson_set_status/set_status,
   lesson_record_outcome/record_outcome, helper_register, helper_activate/activate,
   register_asset, select_asset, register_assessment) on valid existing contracts;
   rejects unauthenticated state-changing access.
2. test_worker_cannot_promote_lessons_activate_helpers_register_assets_or_change_settings:
   Ensures workers are forbidden from operator mutations (promoting lessons, activating
   shared helpers, registering assets, or updating configuration).
3. test_observe_owned_lesson_requires_owner_fence_and_supporting_attempt:
   Worker-safe observe_owned_lesson(attempt_id, worker_id, fence, condition, action,
   scope, expected_result, kind='procedure') validates owner + fence, generates candidate
   with supporting attempt [id], and rejects policy/profile writes.
4. test_worker_read_context_and_membership_fenced_documents_status:
   Allows worker read access to lessons_for_context and helpers_for_context; enforces
   candidate+job membership in worker's accepted run for documents_status; preserves
   fenced worker validation on report_upload.
5. test_service_view_projection_includes_resources_and_redacts_secrets:
   Service.view operator projection includes lessons, helpers, assets, and assessments
   arrays while redacting candidate profile_json and account credentials.
"""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from job_applier.managed import Service, ProtocolError
from job_applier.managed_api import create_app

OPERATOR_TOKEN = "synthetic-operator-token-32chars"
WORKER_TOKEN = "synthetic-worker-token-32chars-1"
OTHER_WORKER_TOKEN = "synthetic-worker-token-32chars-2"
WORKER_ID = "worker-1"
OTHER_WORKER_ID = "worker-2"
BASE_URL = "http://127.0.0.1:8769"


def setup_resource_test_env(tmp_path):
    s = Service.create(tmp_path / "proto.db", instance_id="test-resource-instance")
    worker_tokens = {
        WORKER_TOKEN: WORKER_ID,
        OTHER_WORKER_TOKEN: OTHER_WORKER_ID,
    }
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens=worker_tokens)
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
    return s, client, op_headers, worker_headers, other_worker_headers


def create_test_attempt(s, client, op_headers, worker_headers, worker_id=WORKER_ID, job_url="https://jobs.example.test/role-1", cand_id="cand-1"):
    intake_res = client.post(
        "/v1/intake",
        json={"url": job_url, "source_id": f"src-{job_url[-6:]}"},
        headers=op_headers,
    )
    job_id = intake_res.json()["id"]
    client.post(
        "/v1/eligibility",
        json={"job_id": job_id, "decision": "ready", "reason": "test"},
        headers=op_headers,
    )
    client.post(
        "/v1/identity",
        json={
            "identity_id": cand_id,
            "person_key": f"person-{cand_id}",
            "email": f"{cand_id}@example.test",
            "profile": {"facts": {}},
        },
        headers=op_headers,
    )
    req_res = client.post(
        "/v1/request_run",
        json={
            "request_id": f"req-{job_id}",
            "job_ids": [job_id],
            "identity_id": cand_id,
            "browser_profile": "prof-1",
        },
        headers=op_headers,
    )
    run_id = req_res.json()["id"]
    client.post(
        "/v1/accept_run",
        json={
            "run_id": run_id,
            "worker_id": worker_id,
            "session_id": f"sess-{run_id}",
            "capabilities": {
                "protocol": 1,
                "skill_version": "v1.0",
                "browser_profile": "prof-1",
                "provider": "fixture",
                "model": "fixture-model",
                "telemetry": True,
            },
        },
        headers=worker_headers,
    )
    claim_res = client.post(
        "/v1/claim",
        json={"run_id": run_id, "worker_id": worker_id},
        headers=worker_headers,
    )
    attempt = claim_res.json()
    return job_id, cand_id, run_id, attempt["id"], attempt["fence"]


def test_operator_resource_endpoints_succeed_and_reject_anonymous(tmp_path):
    """1. Operator resource endpoints succeed on valid existing contracts; anonymous rejected 401."""
    s, client, op_headers, worker_headers, _ = setup_resource_test_env(tmp_path)
    # 2. Operator: helper_register and helper_activate succeed when quiescent
    helper_path = tmp_path / "test_helper.py"
    helper_path.write_text("# Synthetic helper\ndef apply_helper(): pass\n", encoding="utf-8")
    helper_sha = hashlib.sha256(helper_path.read_bytes()).hexdigest()
    reg_helper_res = client.post(
        "/v1/helper_register",
        json={
            "helper_id": "synthetic_helper",
            "version": "v1",
            "capability": "form_fill",
            "path": str(helper_path),
            "sha256": helper_sha,
            "scope": {"platform": "fixture"},
            "preconditions": ["ready"],
            "limitations": ["chrome_only"],
            "tests": ["test_fill"],
        },
        headers=op_headers,
    )
    assert reg_helper_res.status_code == 200

    act_helper_res = client.post(
        "/v1/helper_activate",
        json={
            "helper_id": "synthetic_helper",
            "version": "v1",
            "verification_evidence": "tested in fixture sandbox",
        },
        headers=op_headers,
    )
    assert act_helper_res.status_code == 200
    assert act_helper_res.json()["status"] == "active"

    # Create real attempt for lesson and document tests
    job_id, cand_id, run_id, attempt_id, fence = create_test_attempt(s, client, op_headers, worker_headers)

    # 3. Anonymous access to state-changing resource endpoints rejected with 401
    anon_headers = {"X-JobBot-Instance": s.instance_id}
    res = client.post(
        "/v1/lesson_observe",
        json={
            "condition": "c",
            "action": "a",
            "scope": {"platform": "fixture"},
            "expected_result": "e",
            "attempt_ids": [attempt_id],
        },
        headers=anon_headers,
    )
    assert res.status_code == 401

    res = client.post(
        "/v1/register_asset",
        json={
            "identity_id": cand_id,
            "kind": "resume",
            "version": "v1",
            "storage_ref": "storage://cand/res.pdf",
            "sha256": "a" * 64,
            "provenance": {"src": "fixture"},
        },
        headers=anon_headers,
    )
    assert res.status_code == 401

    # 4. Operator: lesson_observe succeeds
    obs_res = client.post(
        "/v1/lesson_observe",
        json={
            "condition": "login captcha appears",
            "action": "wait for operator checkpoint",
            "scope": {"platform": "fixture"},
            "expected_result": "captcha solved",
            "attempt_ids": [attempt_id],
            "kind": "procedure",
        },
        headers=op_headers,
    )
    assert obs_res.status_code == 200
    lesson = obs_res.json()
    lesson_id = lesson["id"]
    assert lesson["status"] == "candidate"
    assert lesson["attempt_ids"] == [attempt_id]

    # 5. Operator: lesson_set_status (or set_status) succeeds
    status_res = client.post(
        "/v1/lesson_set_status",
        json={
            "lesson_id": lesson_id,
            "status": "active",
            "reason": "verified in test run",
        },
        headers=op_headers,
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "active"

    # 6. Operator: lesson_record_outcome (or record_outcome) succeeds
    outcome_res = client.post(
        "/v1/lesson_record_outcome",
        json={
            "lesson_id": lesson_id,
            "attempt_id": attempt_id,
            "success": True,
            "reason": "step completed as expected",
        },
        headers=op_headers,
    )
    assert outcome_res.status_code == 200

    # 6. Operator: register_asset and select_asset succeed
    resume_sha = hashlib.sha256(b"synthetic_resume_bytes").hexdigest()
    reg_asset_res = client.post(
        "/v1/register_asset",
        json={
            "identity_id": cand_id,
            "kind": "resume",
            "version": "v1",
            "storage_ref": "storage://synthetic/cand-1/resume-v1.pdf",
            "sha256": resume_sha,
            "provenance": {"source": "candidate_upload"},
        },
        headers=op_headers,
    )
    assert reg_asset_res.status_code == 200
    asset_id = reg_asset_res.json()["id"]

    sel_asset_res = client.post(
        "/v1/select_asset",
        json={
            "asset_id": asset_id,
            "job_id": job_id,
            "attempt_id": attempt_id,
        },
        headers=op_headers,
    )
    assert sel_asset_res.status_code == 200

    # 7. Operator: register_assessment succeeds
    reg_assess_res = client.post(
        "/v1/register_assessment",
        json={
            "job_id": job_id,
            "jd_hash": hashlib.sha256(b"jd_desc").hexdigest(),
            "resume_hash": resume_sha,
            "profile_hash": hashlib.sha256(b"cand_profile").hexdigest(),
            "evaluator": "llm-evaluator",
            "model": "gemini-pro",
            "rubric": "rubric-v1",
            "score": 92.5,
            "scale_min": 0,
            "scale_max": 100,
            "recommendation": "Strong apply",
            "reasons": ["excellent qualifications", "matched experience"],
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        },
        headers=op_headers,
    )
    assert reg_assess_res.status_code == 200


def test_worker_cannot_promote_lessons_activate_helpers_register_assets_or_change_settings(tmp_path):
    """2. Worker cannot promote lessons, activate shared helpers, register foreign assets, or change settings."""
    s, client, op_headers, worker_headers, _ = setup_resource_test_env(tmp_path)
    job_id, cand_id, run_id, attempt_id, fence = create_test_attempt(s, client, op_headers, worker_headers)

    # Setup a candidate lesson and registered helper
    lesson = s.lesson_observe(
        condition="c",
        action="a",
        scope={"platform": "fixture"},
        expected_result="e",
        attempt_ids=[attempt_id],
        kind="procedure",
    )
    helper_path = tmp_path / "helper2.py"
    helper_path.write_text("# helper\n", encoding="utf-8")
    helper_sha = hashlib.sha256(helper_path.read_bytes()).hexdigest()
    s.helper_register(
        helper_id="h2",
        version="v1",
        capability="form_fill",
        path=str(helper_path),
        sha256=helper_sha,
        scope={"platform": "fixture"},
        preconditions=["ready"],
        limitations=["none"],
        tests=["t1"],
    )

    # 1. Worker cannot promote lessons -> 403
    res1 = client.post(
        "/v1/lesson_set_status",
        json={
            "lesson_id": lesson["id"],
            "status": "active",
            "reason": "worker promotion attempt",
        },
        headers=worker_headers,
    )
    res2 = client.post(
        "/v1/set_status",
        json={
            "lesson_id": lesson["id"],
            "status": "active",
            "reason": "worker promotion attempt",
        },
        headers=worker_headers,
    )
    assert res1.status_code == 403

    # 2. Worker cannot activate shared helpers -> 403
    res1 = client.post(
        "/v1/helper_activate",
        json={
            "helper_id": "h2",
            "version": "v1",
            "verification_evidence": "worker trying to activate",
        },
        headers=worker_headers,
    )
    res2 = client.post(
        "/v1/activate",
        json={
            "helper_id": "h2",
            "version": "v1",
            "verification_evidence": "worker trying to activate",
        },
        headers=worker_headers,
    )
    assert res1.status_code == 403

    # 3. Worker cannot register foreign/any document assets -> 403
    res = client.post(
        "/v1/register_asset",
        json={
            "identity_id": cand_id,
            "kind": "resume",
            "version": "v2",
            "storage_ref": "storage://foreign/resume.pdf",
            "sha256": "b" * 64,
            "provenance": {"source": "worker"},
        },
        headers=worker_headers,
    )
    assert res.status_code == 403

    # 4. Worker cannot change settings -> 403
    res = client.post(
        "/v1/configure",
        json={"settings": {"mode": "production"}},
        headers=worker_headers,
    )
    assert res.status_code == 403


def test_observe_owned_lesson_requires_owner_fence_and_supporting_attempt(tmp_path):
    """3. Worker-safe observe_owned_lesson requires owner validation and fence; cannot write profile/policy."""
    s, client, op_headers, worker_headers, other_worker_headers = setup_resource_test_env(tmp_path)
    job_id, cand_id, run_id, attempt_id, fence = create_test_attempt(
        s, client, op_headers, worker_headers, worker_id=WORKER_ID
    )

    payload = {
        "attempt_id": attempt_id,
        "worker_id": WORKER_ID,
        "fence": fence,
        "condition": "submit button is disabled until scroll",
        "action": "scroll terms to bottom before submit click",
        "scope": {"platform": "fixture"},
        "expected_result": "submit button enables",
        "kind": "procedure",
    }

    # Verify Service has observe_owned_lesson method
    assert hasattr(s, "observe_owned_lesson"), "Service must implement observe_owned_lesson"

    # 1. Valid owning worker with matching fence succeeds via endpoint and creates candidate
    res = client.post("/v1/observe_owned_lesson", json=payload, headers=worker_headers)
    assert res.status_code == 200
    lesson = res.json()
    assert lesson["status"] == "candidate"
    assert lesson["attempt_ids"] == [attempt_id]
    assert lesson["kind"] == "procedure"

    # Direct call on service behaves equivalently
    srv_lesson = s.observe_owned_lesson(
        attempt_id=attempt_id,
        worker_id=WORKER_ID,
        fence=fence,
        condition="input field requires blur event",
        action="dispatch blur event after typing",
        scope={"platform": "fixture"},
        expected_result="form validation passes",
        kind="procedure",
    )
    assert srv_lesson["status"] == "candidate"
    assert srv_lesson["attempt_ids"] == [attempt_id]

    # 2. Worker identity mismatch / other worker rejected
    mismatch_payload = dict(payload, worker_id=OTHER_WORKER_ID)
    res_mismatch = client.post("/v1/observe_owned_lesson", json=mismatch_payload, headers=other_worker_headers)
    assert res_mismatch.status_code in (403, 422)

    with pytest.raises(ProtocolError):
        s.observe_owned_lesson(
            attempt_id=attempt_id,
            worker_id=OTHER_WORKER_ID,
            fence=fence,
            condition="c",
            action="a",
            scope={"platform": "fixture"},
            expected_result="e",
        )

    # 3. Stale / invalid fence rejected
    stale_payload = dict(payload, fence=fence + 99)
    res_stale = client.post("/v1/observe_owned_lesson", json=stale_payload, headers=worker_headers)
    assert res_stale.status_code in (403, 409, 422)

    with pytest.raises(ProtocolError):
        s.observe_owned_lesson(
            attempt_id=attempt_id,
            worker_id=WORKER_ID,
            fence=fence + 99,
            condition="c",
            action="a",
            scope={"platform": "fixture"},
            expected_result="e",
        )

    # 4. Cannot write profile or policy (policy kinds rejected)
    policy_payload = dict(payload, kind="policy")
    res_policy = client.post("/v1/observe_owned_lesson", json=policy_payload, headers=worker_headers)
    assert res_policy.status_code in (400, 422)

    with pytest.raises(ProtocolError):
        s.observe_owned_lesson(
            attempt_id=attempt_id,
            worker_id=WORKER_ID,
            fence=fence,
            condition="c",
            action="a",
            scope={"platform": "fixture"},
            expected_result="e",
            kind="candidate_fact",
        )


def test_worker_read_context_and_membership_fenced_documents_status(tmp_path):
    """4. Worker read access to context lessons/helpers; documents_status requires membership; report_upload fenced."""
    s, client, op_headers, worker_headers, other_worker_headers = setup_resource_test_env(tmp_path)

    # Setup active helper before claiming attempts (quiescent lease state)
    helper_path = tmp_path / "helper_ctx.py"
    helper_path.write_text("# ctx\n", encoding="utf-8")
    helper_sha = hashlib.sha256(helper_path.read_bytes()).hexdigest()
    s.helper_register(
        helper_id="hctx",
        version="v1",
        capability="form_fill",
        path=str(helper_path),
        sha256=helper_sha,
        scope={"platform": "fixture"},
        preconditions=["ready"],
        limitations=["none"],
        tests=["t"],
    )
    s.helper_activate("hctx", "v1", verification_evidence="evidence")

    job_id, cand_id, run_id, attempt_id, fence = create_test_attempt(
        s, client, op_headers, worker_headers, worker_id=WORKER_ID
    )

    # Setup active lesson with the claimed attempt
    lesson = s.lesson_observe(
        condition="c",
        action="a",
        scope={"platform": "fixture"},
        expected_result="e",
        attempt_ids=[attempt_id],
    )
    s.lesson_set_status(lesson["id"], "active", reason="op verified")

    # 1. Existing read methods lessons_for_context / helpers_for_context allowed to worker
    res_lessons = client.post(
        "/v1/lessons_for_context",
        json={"platform": "fixture", "namespace": "synthetic", "limit": 3},
        headers=worker_headers,
    )
    assert res_lessons.status_code == 200
    assert isinstance(res_lessons.json(), list)

    res_helpers = client.post(
        "/v1/helpers_for_context",
        json={"platform": "fixture", "namespace": "synthetic"},
        headers=worker_headers,
    )
    assert res_helpers.status_code == 200
    assert isinstance(res_helpers.json(), list)

    # 2. documents_status requires candidate+job membership in worker's accepted run
    # For accepted run (cand_id + job_id) -> 200
    res_doc_ok = client.post(
        "/v1/documents_status",
        json={"job_id": job_id, "identity_id": cand_id},
        headers=worker_headers,
    )
    assert res_doc_ok.status_code == 200
    assert "ready" in res_doc_ok.json()

    # For foreign job (not in worker's accepted run) -> 403
    foreign_intake = client.post(
        "/v1/intake",
        json={"url": "https://jobs.example.test/foreign-job", "source_id": "foreign-1"},
        headers=op_headers,
    )
    foreign_job_id = foreign_intake.json()["id"]
    res_doc_foreign = client.post(
        "/v1/documents_status",
        json={"job_id": foreign_job_id, "identity_id": cand_id},
        headers=worker_headers,
    )
    assert res_doc_foreign.status_code == 403

    # Other worker (who did not accept this run) accessing documents_status -> 403
    res_doc_other = client.post(
        "/v1/documents_status",
        json={"job_id": job_id, "identity_id": cand_id},
        headers=other_worker_headers,
    )
    assert res_doc_other.status_code == 403

    # 3. report_upload keeps existing fenced worker validation
    asset_sha = hashlib.sha256(b"asset_doc_bytes").hexdigest()
    asset = s.register_asset(
        identity_id=cand_id,
        kind="resume",
        version="v1",
        storage_ref="storage://cand/res.pdf",
        sha256=asset_sha,
        provenance={"src": "upload"},
    )
    s.select_asset(asset_id=asset["id"], job_id=job_id, attempt_id=attempt_id)

    # Owning worker with valid fence succeeds -> 200
    res_upload_ok = client.post(
        "/v1/report_upload",
        json={
            "attempt_id": attempt_id,
            "worker_id": WORKER_ID,
            "fence": fence,
            "asset_id": asset["id"],
            "status": "upload_attempted",
            "evidence": "file selected in input element",
        },
        headers=worker_headers,
    )
    assert res_upload_ok.status_code == 200

    # Wrong worker_id or stale fence -> 403 or 409
    res_upload_stale = client.post(
        "/v1/report_upload",
        json={
            "attempt_id": attempt_id,
            "worker_id": WORKER_ID,
            "fence": fence + 10,
            "asset_id": asset["id"],
            "status": "upload_confirmed",
            "evidence": "stale fence attempt",
        },
        headers=worker_headers,
    )
    assert res_upload_stale.status_code in (403, 409, 422)


def test_service_view_projection_includes_resources_and_redacts_secrets(tmp_path):
    """5. Service.view operator projection includes lessons/helpers/assets/assessments and redacts secrets."""
    s, client, op_headers, worker_headers, _ = setup_resource_test_env(tmp_path)

    # Register helper before claiming attempts (quiescent lease state)
    helper_path = tmp_path / "view_helper.py"
    helper_path.write_text("# helper\n", encoding="utf-8")
    helper_sha = hashlib.sha256(helper_path.read_bytes()).hexdigest()
    s.helper_register(
        helper_id="vh",
        version="v1",
        capability="form_fill",
        path=str(helper_path),
        sha256=helper_sha,
        scope={"platform": "fixture"},
        preconditions=["ready"],
        limitations=["none"],
        tests=["t"],
    )

    job_id, cand_id, run_id, attempt_id, fence = create_test_attempt(s, client, op_headers, worker_headers)

    # Populate lesson, asset, assessment
    lesson = s.lesson_observe(
        condition="c",
        action="a",
        scope={"platform": "fixture"},
        expected_result="e",
        attempt_ids=[attempt_id],
    )
    asset_sha = hashlib.sha256(b"cand_resume").hexdigest()
    asset = s.register_asset(
        identity_id=cand_id,
        kind="resume",
        version="v1",
        storage_ref="storage://cand/resume.pdf",
        sha256=asset_sha,
        provenance={"src": "cand"},
    )
    s.register_assessment(
        job_id=job_id,
        jd_hash=hashlib.sha256(b"jd").hexdigest(),
        resume_hash=asset_sha,
        profile_hash=hashlib.sha256(b"profile").hexdigest(),
        evaluator="llm-judge",
        model="gemini",
        rubric="standard",
        score=90.0,
        scale_min=0,
        scale_max=100,
        recommendation="Apply",
        reasons=["good fit"],
        evaluated_at=datetime.now(timezone.utc).isoformat(),
    )

    # 1. Service.view() projection directly and via operator POST /v1/view
    view_data = s.view()
    op_view_res = client.post("/v1/view", json={}, headers=op_headers)
    assert op_view_res.status_code == 200
    op_view = op_view_res.json()

    # Projection must include lessons, helpers, assets, assessments arrays
    for data in (view_data, op_view):
        assert "lessons" in data, "Projection must include lessons array"
        assert "helpers" in data, "Projection must include helpers array"
        assert "assets" in data, "Projection must include assets array"
        assert "assessments" in data, "Projection must include assessments array"

        assert isinstance(data["lessons"], list)
        assert isinstance(data["helpers"], list)
        assert isinstance(data["assets"], list)
        assert isinstance(data["assessments"], list)

        assert any(l["id"] == lesson["id"] for l in data["lessons"])
        assert any(h["helper_id"] == "vh" for h in data["helpers"])
        assert any(a["id"] == asset["id"] for a in data["assets"])
        assert any(m["job_id"] == job_id for m in data["assessments"])

        # 2. Candidates array does not expose profile_json or raw credentials
        for candidate in data["candidates"]:
            assert "profile_json" not in candidate
            assert "password" not in str(candidate).lower()
            assert "secret" not in str(candidate).lower()

        # 3. Accounts array does not expose credential_ref or raw credentials
        for account in data["accounts"]:
            assert "credential_ref" not in account
            assert "password" not in str(account).lower()
            assert "token" not in str(account).lower()
