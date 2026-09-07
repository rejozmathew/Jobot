"""Tests for verified namespace aliasing and worker owned account events (expected RED).

Primary Windows Hermes retains implementation.
Covers:
1. Operator namespace_alias(alias, canonical, verification_evidence):
   - Stores verified account-namespace redirect alias using host[/path] syntax.
   - Rejects company-name aliasing not matching valid_namespace host[/path] syntax.
   - Rejects cycles and conflicting reassignments.
   - account_strategy and account_update resolve aliases while retaining identity isolation.
2. Worker record_account_event(attempt_id, worker_id, fence, namespace, state, credential_ref, request_id, evidence):
   - Derives identity from owned attempt.
   - Validates fence and verified namespace belongs to job URL host (or verified alias of that host).
   - Uses existing account_update metadata lifecycle.
   - Created/confirmed account survives subsequent failed application finish.
3. Worker record_account_event safety rejections:
   - Wrong owner / worker_id mismatch.
   - Lease fence mismatch.
   - Namespace unrelated to job URL host / alias.
   - Missing evidence for confirmed account.
   - Unprotected credential_ref format.
4. HTTP API role boundary enforcement:
   - /v1/namespace_alias is operator only (worker rejected with 403 role_forbidden).
   - /v1/record_account_event is worker only (operator rejected with 403 role_forbidden).
   - Worker cannot invoke unrestricted /v1/account_update (403 role_forbidden).
   - Worker cannot record account events for unowned attempts (403 worker_identity_mismatch / attempt_forbidden).
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


def _setup_service(tmp_path, instance_id="test-owned-accounts"):
    s = Service.create(
        tmp_path / "owned_accounts.db",
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


def test_operator_namespace_alias_syntax_cycles_and_isolated_resolution(tmp_path):
    """1. Operator namespace_alias validates host[/path] syntax, rejects company names,
    cycles, conflicting reassignments, and resolves aliases while isolating identities.
    """
    s = _setup_service(tmp_path)

    # Valid registration of host[/path] alias redirect
    alias_row = s.namespace_alias(
        alias="careers.example.test",
        canonical="auth.example.test/tenant-corp",
        verification_evidence="Verified SSO redirect chain",
    )
    assert isinstance(alias_row, dict)
    assert alias_row["alias"] == "careers.example.test"
    assert alias_row["canonical"] == "auth.example.test/tenant-corp"

    # Reject company-name aliasing (does not match valid host[/path] syntax)
    with pytest.raises(ProtocolError):
        s.namespace_alias(
            alias="Acme Corporation",
            canonical="auth.example.test/tenant-corp",
            verification_evidence="Invalid company name alias",
        )

    # Reject cycle: canonical pointing back to alias or self
    with pytest.raises(ProtocolError):
        s.namespace_alias(
            alias="auth.example.test/tenant-corp",
            canonical="careers.example.test",
            verification_evidence="Cycle attempt",
        )
    with pytest.raises(ProtocolError):
        s.namespace_alias(
            alias="loop.example.test",
            canonical="loop.example.test",
            verification_evidence="Self loop attempt",
        )

    # Reject conflicting reassignment
    with pytest.raises(ProtocolError):
        s.namespace_alias(
            alias="careers.example.test",
            canonical="different.example.test",
            verification_evidence="Conflicting reassignment attempt",
        )

    # Update account under alias resolves to canonical target
    acc = s.account_update(
        namespace="careers.example.test",
        identity_id="cand-1",
        state="confirmed",
        credential_ref="vault:cand-1-oauth",
        request_id="acc-alias-1",
        evidence="Account verified via redirect",
    )
    assert acc["state"] == "confirmed"

    # account_strategy on canonical namespace resolves to the account
    strat_canonical = s.account_strategy(namespace="auth.example.test/tenant-corp", identity_id="cand-1")
    assert strat_canonical["action"] == "sign_in"

    # account_strategy on alias namespace also resolves to the account
    strat_alias = s.account_strategy(namespace="careers.example.test", identity_id="cand-1")
    assert strat_alias["action"] == "sign_in"

    # Retain selected identity isolation: cand-2 on alias namespace remains unknown
    strat_cand2 = s.account_strategy(namespace="careers.example.test", identity_id="cand-2")
    assert strat_cand2["action"] == "unknown"


def test_worker_record_account_event_lifecycle_and_survives_failed_application(tmp_path):
    """2. Worker record_account_event derives candidate identity from owned attempt,
    validates job URL host / alias, uses account_update lifecycle, and confirmed account
    survives failed application finish.
    """
    s = _setup_service(tmp_path)
    job, run, attempt = _create_claimed_attempt(s, url="https://careers.example.test/jobs/200", identity_id="cand-1")

    # Operator sets verified alias for the job URL host
    s.namespace_alias(
        alias="careers.example.test",
        canonical="login.example.test/idp",
        verification_evidence="Confirmed canonical login host for careers portal",
    )

    # Worker records confirmed account event using verified canonical namespace
    rec = s.record_account_event(
        attempt_id=attempt["id"],
        worker_id=WORKER_ID,
        fence=attempt["fence"],
        namespace="login.example.test/idp",
        state="confirmed",
        credential_ref="vault:cand-1-workday",
        request_id="worker-acc-evt-1",
        evidence="Worker completed signup and email confirmation",
    )
    assert isinstance(rec, dict)
    assert rec["state"] == "confirmed"
    assert rec["identity_id"] == "cand-1"
    assert rec["credential_ref"] == "vault:cand-1-workday"

    # Strategy for candidate is sign_in on both alias and canonical namespace
    assert s.account_strategy(namespace="careers.example.test", identity_id="cand-1")["action"] == "sign_in"
    assert s.account_strategy(namespace="login.example.test/idp", identity_id="cand-1")["action"] == "sign_in"

    # Application finishes with failed outcome
    s.finish(
        attempt["id"],
        worker_id=WORKER_ID,
        fence=attempt["fence"],
        outcome="failed",
        evidence="Application question unanswerable, run failed",
        quiescent=True,
    )

    # Confirmed account must survive subsequent failed application
    strat_after_fail = s.account_strategy(namespace="careers.example.test", identity_id="cand-1")
    assert strat_after_fail["action"] == "sign_in"
    assert strat_after_fail["credential_ref"] == "vault:cand-1-workday"


def test_worker_record_account_event_safety_guards_and_rejections(tmp_path):
    """3. Worker record_account_event rejects wrong owner, stale fence, namespace unrelated
    to job URL host/alias, missing evidence, or unprotected credential_ref.
    """
    s = _setup_service(tmp_path)
    job, run, attempt = _create_claimed_attempt(s, url="https://portal.example.test/jobs/300", identity_id="cand-1")

    # 1. Wrong owner / worker_id mismatch
    with pytest.raises(ProtocolError):
        s.record_account_event(
            attempt_id=attempt["id"],
            worker_id="unauthorized-worker",
            fence=attempt["fence"],
            namespace="portal.example.test",
            state="confirmed",
            credential_ref="vault:cand-1-pwd",
            request_id="err-req-1",
            evidence="Valid evidence",
        )

    # 2. Fence mismatch
    with pytest.raises(ProtocolError):
        s.record_account_event(
            attempt_id=attempt["id"],
            worker_id=WORKER_ID,
            fence=attempt["fence"] + 1,
            namespace="portal.example.test",
            state="confirmed",
            credential_ref="vault:cand-1-pwd",
            request_id="err-req-2",
            evidence="Valid evidence",
        )

    # 3. Namespace unrelated to job URL host (and not an authorized alias)
    with pytest.raises(ProtocolError):
        s.record_account_event(
            attempt_id=attempt["id"],
            worker_id=WORKER_ID,
            fence=attempt["fence"],
            namespace="unrelated-phishing.test",
            state="confirmed",
            credential_ref="vault:cand-1-pwd",
            request_id="err-req-3",
            evidence="Valid evidence",
        )

    # 4. Missing evidence for confirmed state
    with pytest.raises(ProtocolError):
        s.record_account_event(
            attempt_id=attempt["id"],
            worker_id=WORKER_ID,
            fence=attempt["fence"],
            namespace="portal.example.test",
            state="confirmed",
            credential_ref="vault:cand-1-pwd",
            request_id="err-req-4",
            evidence="",
        )

    # 5. Unprotected credential reference (e.g. raw password or missing prefix scheme)
    with pytest.raises(ProtocolError):
        s.record_account_event(
            attempt_id=attempt["id"],
            worker_id=WORKER_ID,
            fence=attempt["fence"],
            namespace="portal.example.test",
            state="confirmed",
            credential_ref="raw_plaintext_secret_123",
            request_id="err-req-5",
            evidence="Valid evidence",
        )


def test_account_events_api_role_boundaries_and_permissions(tmp_path):
    """4. HTTP API enforces role boundaries: /v1/namespace_alias is operator only;
    worker cannot call unrestricted account_update or namespace_alias;
    /v1/record_account_event is worker only and bound to owned attempt.
    """
    s = _setup_service(tmp_path)
    job, run, attempt = _create_claimed_attempt(s, url="https://careers.example.test/jobs/400", identity_id="cand-1")

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

    # 1. Operator can call /v1/namespace_alias
    op_res = client.post(
        "/v1/namespace_alias",
        headers=op_headers,
        json={
            "alias": "careers.example.test",
            "canonical": "auth.example.test",
            "verification_evidence": "Operator verified redirect",
        },
    )
    assert op_res.status_code == 200

    # 2. Worker cannot call /v1/namespace_alias (403 role_forbidden)
    w_alias_res = client.post(
        "/v1/namespace_alias",
        headers=worker_headers,
        json={
            "alias": "careers.example.test",
            "canonical": "auth.example.test",
            "verification_evidence": "Worker unauthorized alias",
        },
    )
    assert w_alias_res.status_code == 403
    assert w_alias_res.json()["error"] == "role_forbidden"

    # 3. Worker cannot call unrestricted /v1/account_update (403 role_forbidden)
    w_acc_res = client.post(
        "/v1/account_update",
        headers=worker_headers,
        json={
            "namespace": "careers.example.test",
            "identity_id": "cand-1",
            "state": "confirmed",
            "credential_ref": "vault:cand-1-pwd",
            "request_id": "w-unrestricted-1",
            "evidence": "Worker bypass attempt",
        },
    )
    assert w_acc_res.status_code == 403
    assert w_acc_res.json()["error"] == "role_forbidden"

    # 4. Operator cannot call /v1/record_account_event (403 role_forbidden)
    op_evt_res = client.post(
        "/v1/record_account_event",
        headers=op_headers,
        json={
            "attempt_id": attempt["id"],
            "worker_id": WORKER_ID,
            "fence": attempt["fence"],
            "namespace": "careers.example.test",
            "state": "confirmed",
            "credential_ref": "vault:cand-1-pwd",
            "request_id": "op-record-1",
            "evidence": "Operator cannot call worker record event",
        },
    )
    assert op_evt_res.status_code == 403
    assert op_evt_res.json()["error"] == "role_forbidden"

    # 5. Other worker cannot call /v1/record_account_event on unowned attempt (403 attempt_forbidden)
    other_evt_res = client.post(
        "/v1/record_account_event",
        headers=other_worker_headers,
        json={
            "attempt_id": attempt["id"],
            "worker_id": OTHER_WORKER_ID,
            "fence": attempt["fence"],
            "namespace": "careers.example.test",
            "state": "confirmed",
            "credential_ref": "vault:cand-1-pwd",
            "request_id": "other-worker-evt-1",
            "evidence": "Stolen attempt recording",
        },
    )
    assert other_evt_res.status_code == 403
    assert other_evt_res.json()["error"] in ("attempt_forbidden", "worker_identity_mismatch")

    # 6. Authorized worker successfully calls /v1/record_account_event on owned attempt
    valid_evt_res = client.post(
        "/v1/record_account_event",
        headers=worker_headers,
        json={
            "attempt_id": attempt["id"],
            "worker_id": WORKER_ID,
            "fence": attempt["fence"],
            "namespace": "careers.example.test",
            "state": "confirmed",
            "credential_ref": "vault:cand-1-pwd",
            "request_id": "worker-api-evt-1",
            "evidence": "Worker verified account creation on portal",
        },
    )
    assert valid_evt_res.status_code == 200
    assert valid_evt_res.json()["state"] == "confirmed"
    assert valid_evt_res.json()["identity_id"] == "cand-1"
