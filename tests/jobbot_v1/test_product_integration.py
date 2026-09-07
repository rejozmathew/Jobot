"""Product integration contract tests for JobBot bounded integration bundle.

Contracts covered:
1. Factual legacy profile import, secret/policy rejection, skipped field names display.
2. Candidate email change generating distinct identity and preserving prior attempt snapshots & profile hash.
3. Local resume raw binary upload (/v1/upload_asset), SHA-256 calculation, storage under managed-assets,
   candidate default resume visibility, and honest required asset blocker.
4. browser_mode setting (default headed), headless rejection against headed request, fixture/unknown acceptance.
5. browser_observe operation permitted during active writer state and pending pause/stop; ordinary writer blocked;
   quiescence detection enabling ack_control.
6. Target and portal/company linkage persistence into attempt, views, and attempt report.
"""
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest
from fastapi.testclient import TestClient

from job_applier.cdp_client import CDPBrowser, inspect_browser_mode
from job_applier.hermes_plugin import PluginController
from job_applier.managed import Service, ProtocolError
from job_applier.managed_api import create_app
from job_applier.managed_client import Client
from job_applier.managed_settings import SettingsServices
from job_applier.managed_shared import sanitize_legacy_profile

OPERATOR_TOKEN = "synthetic-operator-token-jobbot-v1-32chars"
WORKER_TOKEN = "synthetic-worker-token-jobbot-v1-32chars"
WORKER_ID = "worker-prod-1"
BASE_URL = "http://127.0.0.1:8769"


def make_service_with_attempt(tmp_path, url="https://careers.example.test/jobs/0", company="Acme Corp"):
    s = Service.create(tmp_path / "jobs.db", instance_id="test-prod-instance")
    s.identity(
        identity_id="cand-alice",
        person_key="person-alice",
        email="alice@example.test",
        profile={"facts": {"full_name": "Alice Candidate", "work_authorization": "US Citizen"}},
    )
    job = s.intake(url=url, source_id="job-0", company=company)
    s.eligibility(job["id"], "ready", reason="operator approved")
    r = s.request_run(
        request_id="req-prod-1",
        job_ids=[job["id"]],
        identity_id="cand-alice",
        browser_profile="fixture-browser",
    )
    s.accept_run(
        r["id"],
        worker_id=WORKER_ID,
        session_id="session-prod-1",
        capabilities={
            "protocol": 1,
            "skill_version": "test-skill",
            "browser_profile": "fixture-browser",
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )
    attempt = s.claim(r["id"], worker_id=WORKER_ID)
    return s, job, r, attempt


# ---------------------------------------------------------------------------
# 1. Factual Legacy Profile Import & Secret/Policy Rejection & Skipped Fields
# ---------------------------------------------------------------------------

def test_legacy_profile_import_whitelists_factual_and_rejects_secrets():
    legacy_payload = {
        "identity": {
            "full_name": "Jane Doe",
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@example.test",
            "phone": "555-0199",
            "location": "San Francisco, CA",
            "linkedin": "https://linkedin.com/in/janedoe",
            "github": "https://github.com/janedoe",
        },
        "summary": "Experienced software engineer.",
        "skills": ["Python", "FastAPI", "SQLite"],
        "work_authorization": "US Citizen",
        "work_preferences": {"remote": True},
        "experience": [{"company": "Tech Corp", "role": "Senior Dev", "duration": "3 years"}],
        "education": [{"institution": "State University", "degree": "B.S. CS"}],
        "links": {"portfolio": "https://janedoe.dev"},
        # Sensitive / prohibited fields that MUST be rejected
        "accounts": {"greenhouse": {"username": "jane", "password": "supersecretpassword"}},
        "login": {"email": "jane@example.test", "password": "plaintext_password"},
        "automation_preferences": {"auto_submit": True, "bypass_review": True},
        "application_answer_policy": {"salary_negotiable": True},
        "cover_letter": "Dear Hiring Manager, hire me please.",
        "resume": {"text": "Raw OCR text of resume with private details", "path": "/secret/path.pdf"},
    }

    sanitized, skipped = sanitize_legacy_profile(legacy_payload)

    # Assert factual fields are preserved
    assert sanitized["identity"]["email"] == "jane.doe@example.test"
    assert sanitized["identity"]["full_name"] == "Jane Doe"
    assert sanitized["identity"]["phone"] == "555-0199"
    assert sanitized["identity"]["location"] == "San Francisco, CA"
    assert sanitized["skills"] == ["Python", "FastAPI", "SQLite"]
    assert sanitized["work_authorization"] == "US Citizen"
    assert sanitized["summary"] == "Experienced software engineer."
    assert len(sanitized["experience"]) == 1
    assert len(sanitized["education"]) == 1
    assert sanitized["links"]["portfolio"] == "https://janedoe.dev"

    # Assert sensitive sections are absent
    assert "accounts" not in sanitized
    assert "login" not in sanitized
    assert "automation_preferences" not in sanitized
    assert "application_answer_policy" not in sanitized
    assert "cover_letter" not in sanitized
    assert "password" not in str(sanitized).lower()
    assert "supersecretpassword" not in str(sanitized)
    assert "raw ocr text" not in str(sanitized).lower()

    # Assert skipped field names are reported cleanly without values
    assert "accounts" in skipped
    assert "login" in skipped
    assert "automation_preferences" in skipped
    assert "application_answer_policy" in skipped
    assert "cover_letter" in skipped
    assert "resume.text" in skipped or "resume" in skipped
    for field in skipped:
        assert isinstance(field, str)
        # Ensure values were not appended to field names
        assert "supersecretpassword" not in field
        assert "plaintext_password" not in field


def test_service_import_profile_persists_factual_and_returns_skipped_fields(tmp_path):
    s = Service.create(tmp_path / "jobs.db", instance_id="test-import")
    s.identity(
        identity_id="cand-import-1",
        person_key="person-1",
        email="initial@example.test",
        profile={"facts": {"work_authorization": "fixture"}},
    )

    import_data = {
        "identity": {
            "full_name": "Alex Tester",
            "email": "initial@example.test",
            "phone": "123-456-7890",
        },
        "skills": ["Go", "Distributed Systems"],
        "work_authorization": "Permanent Resident",
        "accounts": {"portal": {"secret": "dont_save_me"}},
        "login": {"pwd": "secret_pwd"},
    }

    result = s.import_profile(import_data, identity_id="cand-import-1")
    assert result["identity_id"] == "cand-import-1"
    assert "accounts" in result["skipped"]
    assert "login" in result["skipped"]

    cand = s.candidate("cand-import-1")
    assert cand["email"] == "initial@example.test"
    assert cand["profile"]["identity"]["full_name"] == "Alex Tester"
    assert cand["profile"]["skills"] == ["Go", "Distributed Systems"]
    assert cand["profile"]["work_authorization"] == "Permanent Resident"
    assert "accounts" not in cand["profile"]
    assert "secret" not in json.dumps(cand["profile"])


# ---------------------------------------------------------------------------
# 2. Email Change Generates Distinct Identity & Protects Snapshots
# ---------------------------------------------------------------------------

def test_candidate_email_change_creates_distinct_identity_and_preserves_attempt_snapshots(tmp_path):
    s, job, r, attempt = make_service_with_attempt(tmp_path)

    # Initial attempt has Alice's snapshot and profile_hash
    initial_context = s.application_context(attempt["id"])
    alice_profile_hash = initial_context["profile_hash"]
    assert alice_profile_hash is not None
    assert initial_context["attempt"]["identity_id"] == "cand-alice"

    # Operator imports or updates profile with a DIFFERENT email targeting cand-alice
    new_email_data = {
        "identity": {
            "full_name": "Bob Different",
            "email": "bob.different@example.test",
        },
        "skills": ["JavaScript", "Rust"],
    }
    result = s.import_profile(new_email_data, identity_id="cand-alice")

    # Distinct identity must be generated, NOT relabeling cand-alice
    new_id = result["identity_id"]
    assert new_id != "cand-alice"
    assert result["email"] == "bob.different@example.test"

    # Alice's identity remains completely intact
    alice_cand = s.candidate("cand-alice")
    assert alice_cand["email"] == "alice@example.test"
    assert alice_cand["profile"]["facts"]["full_name"] == "Alice Candidate"

    # Bob's identity exists independently
    bob_cand = s.candidate(new_id)
    assert bob_cand["email"] == "bob.different@example.test"
    assert bob_cand["profile"]["identity"]["full_name"] == "Bob Different"

    # Prior attempt snapshot and context remain 100% immutable
    preserved_context = s.application_context(attempt["id"])
    assert preserved_context["profile_hash"] == alice_profile_hash
    assert preserved_context["attempt"]["identity_id"] == "cand-alice"

    preserved_report = s.attempt_report(attempt["id"])
    assert preserved_report["attempt"]["profile_hash"] == alice_profile_hash
    assert preserved_report["attempt"]["identity_id"] == "cand-alice"


# ---------------------------------------------------------------------------
# 3. Resume Usability: Raw Upload, Hash, Managed Assets Storage & Asset Blocker
# ---------------------------------------------------------------------------

def test_resume_raw_upload_security_storage_and_required_asset_blocker(tmp_path):
    s, job, r, attempt = make_service_with_attempt(tmp_path)
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID})
    client = TestClient(app, base_url=BASE_URL)

    pdf_bytes = b"%PDF-1.4 synthetic binary resume content for testing sha256"
    expected_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    # 1. Unauthenticated or worker token upload rejected
    unauth_resp = client.post(
        "/v1/upload_asset",
        headers={"X-JobBot-Instance": s.instance_id},
        params={"identity_id": "cand-alice", "kind": "resume", "version": "v1", "filename": "resume.pdf"},
        content=pdf_bytes,
    )
    assert unauth_resp.status_code == 401

    worker_resp = client.post(
        "/v1/upload_asset",
        headers={"X-JobBot-Instance": s.instance_id, "Authorization": f"Bearer {WORKER_TOKEN}"},
        params={"identity_id": "cand-alice", "kind": "resume", "version": "v1", "filename": "resume.pdf"},
        content=pdf_bytes,
    )
    assert worker_resp.status_code == 403

    # 2. Path traversal attack rejected
    traversal_resp = client.post(
        "/v1/upload_asset",
        headers={"X-JobBot-Instance": s.instance_id, "Authorization": f"Bearer {OPERATOR_TOKEN}"},
        params={"identity_id": "cand-alice", "kind": "resume", "version": "v1", "filename": "../../evil.pdf"},
        content=pdf_bytes,
    )
    assert traversal_resp.status_code == 400

    # 3. Valid operator upload
    upload_resp = client.post(
        "/v1/upload_asset",
        headers={"X-JobBot-Instance": s.instance_id, "Authorization": f"Bearer {OPERATOR_TOKEN}"},
        params={"identity_id": "cand-alice", "kind": "resume", "version": "v1", "filename": "Alice_Resume.pdf"},
        content=pdf_bytes,
    )
    assert upload_resp.status_code == 200
    asset_data = upload_resp.json()
    assert asset_data["sha256"] == expected_sha256
    assert asset_data["kind"] == "resume"
    assert asset_data["version"] == "v1"

    # Verify file is stored under managed-assets in DB parent directory
    from urllib.parse import urlsplit
    from urllib.request import url2pathname
    storage_path = Path(url2pathname(urlsplit(asset_data["storage_ref"]).path))
    assert storage_path.exists()
    assert storage_path.read_bytes() == pdf_bytes
    assert "managed-assets" in str(storage_path)

    # 4. Default resume visibility in candidate & documents status
    s.identity(
        identity_id="cand-alice",
        person_key="person-alice",
        email="alice@example.test",
        profile={"facts": {"full_name": "Alice Candidate"}, "resume_ref": asset_data["id"]},
    )
    cand_row = s.candidate("cand-alice")
    assert cand_row["default_resume"] is not None
    assert cand_row["default_resume"]["id"] == asset_data["id"]
    assert cand_row["default_resume"]["sha256"] == expected_sha256

    # 5. Required document blocker: unselected resume blocks job readiness
    job_with_req = s.intake(
        url="https://careers.example.test/jobs/req-doc",
        source_id="s-req-1",
        required_documents=["resume"],
    )
    doc_status = s.documents_status(job_with_req["id"], identity_id="cand-alice")
    assert doc_status["ready"] is False
    assert "resume" in doc_status["missing"]
    assert doc_status["default_resume"]["id"] == asset_data["id"]

    # Once selected, document status becomes ready
    s.select_asset(asset_id=asset_data["id"], job_id=job_with_req["id"])
    doc_status_selected = s.documents_status(job_with_req["id"], identity_id="cand-alice")
    assert doc_status_selected["ready"] is True
    assert "resume" not in doc_status_selected["missing"]


# ---------------------------------------------------------------------------
# 4. browser_mode Setting & Headless Rejection Against Headed Request
# ---------------------------------------------------------------------------

def test_browser_mode_setting_and_connect_rejection(tmp_path):
    s = Service.create(tmp_path / "jobs.db", instance_id="test-browser-mode")

    # Default is headed
    values = s.settings_view()["values"]
    assert values["browser_mode"] == "headed"

    # Configure to headless succeeds
    v = s.settings_view()["version"]
    res = s.configure({"browser_mode": "headless"}, expected_version=v)
    assert res["values"]["browser_mode"] == "headless"

    # Configure with invalid choice raises ProtocolError
    v2 = s.settings_view()["version"]
    with pytest.raises(ProtocolError) as exc_info:
        s.configure({"browser_mode": "invisible"}, expected_version=v2)
    assert exc_info.value.code == "unsupported_browser_mode"

    # Reasoning matches checks: rejects headless worker capability against headed run settings
    run_headed = {"settings_json": json.dumps({"browser_mode": "headed"})}
    run_headless = {"settings_json": json.dumps({"browser_mode": "headless"})}

    # Headed run rejects headless worker
    with pytest.raises(ProtocolError) as r_exc:
        SettingsServices._reasoning_matches(run_headed, {"browser_mode": "headless"})
    assert r_exc.value.code == "browser_mode_mismatch"

    # Headed run accepts headed worker or unstated/fixture capability
    SettingsServices._reasoning_matches(run_headed, {"browser_mode": "headed"})
    SettingsServices._reasoning_matches(run_headed, {})

    # Headless run accepts headless or headed worker
    SettingsServices._reasoning_matches(run_headless, {"browser_mode": "headless"})
    SettingsServices._reasoning_matches(run_headless, {"browser_mode": "headed"})

    # inspect_browser_mode with HeadlessChrome vs standard Chrome
    with patch("urllib.request.urlopen") as mock_url:
        # 1. Headless Chrome detected
        mock_resp_headless = MagicMock()
        mock_resp_headless.read.return_value = json.dumps({"Browser": "HeadlessChrome/124.0.0"}).encode("utf-8")
        mock_resp_headless.__enter__.return_value = mock_resp_headless
        mock_url.return_value = mock_resp_headless

        assert inspect_browser_mode("http://127.0.0.1:9222") == "headless"

        # Connecting with expected_mode='headed' to headless browser raises ProtocolError/ValueError
        import asyncio
        with pytest.raises((ProtocolError, ValueError)) as p_exc:
            asyncio.run(CDPBrowser.connect("http://127.0.0.1:9222", expected_mode="headed"))
        assert "browser_mode_mismatch" in str(p_exc.value) or "headless browser cannot satisfy headed request" in str(p_exc.value)

        # 2. Standard UA alone cannot prove that a window is headed.
        mock_resp_headed = MagicMock()
        mock_resp_headed.read.return_value = json.dumps({"Browser": "Chrome/124.0.0"}).encode("utf-8")
        mock_resp_headed.__enter__.return_value = mock_resp_headed
        mock_url.return_value = mock_resp_headed

        assert inspect_browser_mode("http://127.0.0.1:9222") == "unknown"

        # 3. Connection failure or fixture endpoint preserved as unknown without failing
        mock_url.side_effect = urllib.error.URLError("Connection refused")
        assert inspect_browser_mode("http://127.0.0.1:9222") == "unknown"


# ---------------------------------------------------------------------------
# 5. Constrained browser_observe Operation, Active Writer & Pause/Stop Quiescence
# ---------------------------------------------------------------------------

def test_browser_observe_during_active_writer_and_pending_pause(tmp_path, monkeypatch):
    from test_product_observation import browser_probe
    s, job, r, attempt = make_service_with_attempt(tmp_path)

    # Bind loopback target
    s.bind_target(
        attempt["id"],
        worker_id=WORKER_ID,
        fence=1,
        target_id="target-tab-1",
        url="https://careers.example.test/jobs/0",
    )

    # Start an ordinary mutating browser action
    s.action_start(
        attempt["id"],
        worker_id=WORKER_ID,
        fence=1,
        action_id="act-write-1",
        tool_name="fill_form",
        writes_browser=True,
    )

    # Operator requests pause
    s.control(r["id"], command="pause")
    run_rec = s.view(run_id=r["id"])["current_run"]
    assert run_rec["control"] == "pause_requested"

    # An ordinary browser mutation tool MUST be blocked during pause_requested
    with pytest.raises(ProtocolError) as block_exc:
        s.action_start(
            attempt["id"],
            worker_id=WORKER_ID,
            fence=1,
            action_id="act-write-2",
            tool_name="click_submit",
            writes_browser=True,
        )
    assert block_exc.value.code == "pause_requested"

    # Constrained browser_observe is permitted during pause_requested even while writer is active
    browser_probe(monkeypatch, job['url'], 'active')
    obs_active = s.browser_observe(
        attempt["id"],
        worker_id=WORKER_ID,
        fence=1,
        target_id="target-tab-1",

    )
    assert obs_active["operation"] == "browser_observe"
    # Since act-write-1 is still active, quiescent MUST be False
    assert obs_active["quiescent"] is False

    # If worker attempts ack_control with quiescent=True while active, ack_control rejects
    with pytest.raises(ProtocolError):
        s.ack_control(attempt["id"], worker_id=WORKER_ID, fence=1, quiescent=True)

    # Conclude active writing action cleanly
    s.action_end(
        attempt["id"],
        worker_id=WORKER_ID,
        fence=1,
        action_id="act-write-1",
        status="success",
    )

    # Now browser_observe observes quiescence
    browser_probe(monkeypatch, job['url'], 'ready')
    obs_quiescent = s.browser_observe(
        attempt["id"],
        worker_id=WORKER_ID,
        fence=1,
        target_id="target-tab-1",

    )
    assert obs_quiescent["quiescent"] is True

    # Ack control now succeeds safely with quiescence established
    ack_res = s.ack_control(attempt["id"], worker_id=WORKER_ID, fence=1, quiescent=True)
    assert ack_res["control"] == "paused"


def test_hermes_plugin_handles_browser_observe_operation():
    from job_applier.hermes_plugin import OPERATIONS, SCHEMA
    assert "browser_observe" in OPERATIONS
    assert "browser_observe" in SCHEMA["parameters"]["properties"]["operation"]["enum"]


# ---------------------------------------------------------------------------
# 6. Target and Portal/Company Linkage Persistence in Views and Reports
# ---------------------------------------------------------------------------

def test_persist_observed_ats_and_company_linkage_in_views_and_reports(tmp_path, monkeypatch):
    from test_product_observation import browser_probe
    s, job, r, attempt = make_service_with_attempt(
        tmp_path,
        url="https://jobs.lever.co/initech/12345",
        company="Initech Corporation",
    )

    # Initial view before target binding: attempt in DB has platform 'unknown'
    with s.tx() as db:
        att_row = db.execute("SELECT platform FROM application_attempts WHERE id=?", (attempt["id"],)).fetchone()
        assert att_row["platform"] == "unknown"

    # Bind target to Lever URL
    s.bind_target(
        attempt["id"],
        worker_id=WORKER_ID,
        fence=1,
        target_id="tgt-lever-1",
        url="https://jobs.lever.co/initech/12345/apply",
    )

    # Verify application_context exposes company, platform, and profile_hash
    with s.tx() as db:
        att_row = db.execute("SELECT platform FROM application_attempts WHERE id=?", (attempt["id"],)).fetchone()
        assert att_row["platform"] == "lever"

    ctx = s.application_context(attempt["id"])
    assert ctx["attempt"]["company"] == "Initech Corporation"
    assert ctx["platform"] == "lever"
    assert ctx["profile_hash"] is not None

    # Actual bound-page observation retains verified portal/company linkage.
    browser_probe(monkeypatch, 'https://jobs.lever.co/initech/12345/apply')
    s.browser_observe(
        attempt["id"],
        worker_id=WORKER_ID,
        fence=1,
        target_id="tgt-lever-1",

    )

    # Check attempt_report has updated platform, company, and profile_hash
    report = s.attempt_report(attempt["id"])
    assert report["attempt"]["company"] == "Initech Corporation"
    assert report["attempt"]["platform"] == "lever"
    assert report["attempt"]["profile_hash"] == ctx["profile_hash"]

    # Operator view also reflects the detected platform
    view_after = s.view(run_id=r["id"])
    att_view_after = view_after["current_run"]["attempts"][0]
    assert att_view_after["platform"] == "lever"
    assert att_view_after["company"] == "Initech Corporation"
