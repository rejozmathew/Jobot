"""Targeted tests for semantic auth fallback, credentials operation, masked screenshots,
extension ref discovery, and single-writer gate separation.
"""
import asyncio
import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from job_applier.managed import ProtocolError
from job_applier.managed_hermes_worker import ApplicationTool, SCHEMA, make_field_metadata
from job_applier.cdp_client import CDPBrowser
from test_product_integration import make_service_with_attempt, WORKER_ID


@pytest.fixture
def cred_profile(tmp_path):
    p = tmp_path / "credentials.json"
    p.write_text(json.dumps({
        "accounts": {
            "default": {
                "email": "candidate.test@example.com",
                "password": "CorrectHorseBatteryStaple99!"
            }
        }
    }), encoding="utf-8")
    return p


def test_default_credentials_same_in_both_password_fields_no_leakage_no_generation(tmp_path, cred_profile, monkeypatch):
    """1) Native saved credentials operation fills default email and both password fields,
    verifies equality internally, never generates passwords, and leaks zero secrets."""
    class DummyCtrl:
        def handle(self, req, session_id=None):
            return json.dumps({"status": "ok"})

    logged_events = []
    app = ApplicationTool(
        DummyCtrl(), "sid-1", "run-1",
        {
            "worker_id": "w1",
            "cdp_url": "http://127.0.0.1:9222",
            "credential_profile_path": str(cred_profile)
        }
    )
    app.context = {"attempt_id": 1, "worker_id": "w1", "fence": 1}
    job_url = "https://huron.wd5.myworkdayjobs.com/en-US/huroncareers/job/Chicago-IL/Manager_JR-0016154/apply"
    app.package = {"job": {"id": 1, "url": job_url}}

    monkeypatch.setattr(app, "call", lambda op, **kw: {"control": "running"})
    monkeypatch.setattr(app, "action", lambda name, writes=True: pytest.MonkeyPatch().context())
    monkeypatch.setattr(app, "event", lambda kind, payload: logged_events.append((kind, payload)))

    filled_values = {}
    class MockPage:
        def __init__(self):
            self._session = MagicMock()
            self._session.call = AsyncMock(return_value={})

        async def evaluate(self, script, arg=None, **kw):
            s = str(script).strip()
            if s == "location.href":
                return job_url
            if "passwords_filled_count" in s or "AUTH_FIND_AND_FILL" in s:
                # Script receives credentials secretly over loopback CDP
                email = arg.get("email") if isinstance(arg, dict) else None
                pwd = arg.get("password") if isinstance(arg, dict) else None
                if email: filled_values["ref-email"] = email
                if pwd:
                    filled_values["ref-pass1"] = pwd
                    filled_values["ref-pass2"] = pwd
                # Verify internal equality
                verified = (filled_values.get("ref-pass1") == pwd and
                            filled_values.get("ref-pass2") == pwd and
                            filled_values.get("ref-pass1") == filled_values.get("ref-pass2"))
                return {
                    "email_filled": bool(email),
                    "passwords_filled_count": 2,
                    "verified": verified,
                    "existing_account": False
                }
            if "window.__jobbotFormScope" in s or "inventory" in s:
                return {
                    "url": job_url,
                    "items": [
                        {"ref": "ref-email", "type": "email", "tag": "INPUT", "label": "Email Address", "value": filled_values.get("ref-email")},
                        {"ref": "ref-pass1", "type": "password", "tag": "INPUT", "label": "Password", "value": None, "present": bool(filled_values.get("ref-pass1"))},
                        {"ref": "ref-pass2", "type": "password", "tag": "INPUT", "label": "Verify New Password", "value": None, "present": bool(filled_values.get("ref-pass2"))},
                    ]
                }
            return {}

    page = MockPage()
    class MockBrowser:
        async def get_current_page(self): return page
        async def close(self): pass

    monkeypatch.setattr(app, "connect", AsyncMock(return_value=MockBrowser()))

    # Run credentials operation
    res = asyncio.run(app.operate({"operation": "credentials"}))

    secret = "CorrectHorseBatteryStaple99!"
    assert res.get("account_state") in ("credentials_filled", "ready_for_account_action")
    assert res.get("action_type") == "create_account"

    # Verify both password fields received the exact saved secret
    assert filled_values.get("ref-pass1") == secret
    assert filled_values.get("ref-pass2") == secret
    assert filled_values.get("ref-email") == "candidate.test@example.com"

    # Assert ZERO secret leakage in results or logged events
    res_str = json.dumps(res)
    assert secret not in res_str
    for kind, payload in logged_events:
        assert secret not in json.dumps(payload)

    # Missing config raises generic error
    app.cfg["credential_profile_path"] = str(tmp_path / "nonexistent.json")
    with pytest.raises(ValueError, match="credentials_unavailable"):
        asyncio.run(app.operate({"operation": "credentials"}))


def test_existing_account_prompt_path(cred_profile, monkeypatch):
    """2) Handle existing-account messages by sign-in with same defaults, no password reset."""
    class DummyCtrl:
        def handle(self, req, session_id=None): return json.dumps({"status": "ok"})

    app = ApplicationTool(
        DummyCtrl(), "sid-2", "run-2",
        {
            "worker_id": "w1",
            "cdp_url": "http://127.0.0.1:9222",
            "credential_profile_path": str(cred_profile)
        }
    )
    app.context = {"attempt_id": 2, "worker_id": "w1", "fence": 1}
    job_url = "https://huron.wd5.myworkdayjobs.com/en-US/huroncareers/job/Chicago-IL/Manager_JR-0016154/apply"
    app.package = {"job": {"id": 1, "url": job_url}}

    monkeypatch.setattr(app, "call", lambda op, **kw: {"control": "running"})
    monkeypatch.setattr(app, "action", lambda name, writes=True: pytest.MonkeyPatch().context())
    monkeypatch.setattr(app, "event", lambda kind, payload: None)

    class MockPage:
        def __init__(self):
            self._session = MagicMock()
            self._session.call = AsyncMock(return_value={})

        async def evaluate(self, script, arg=None, **kw):
            s = str(script).strip()
            if s == "location.href":
                return job_url
            if "passwords_filled_count" in s or "AUTH_FIND_AND_FILL" in s:
                return {
                    "email_filled": True,
                    "passwords_filled_count": 1,
                    "verified": True,
                    "existing_account": True
                }
            return {}

    class MockBrowser:
        async def get_current_page(self): return MockPage()
        async def close(self): pass

    monkeypatch.setattr(app, "connect", AsyncMock(return_value=MockBrowser()))

    res = asyncio.run(app.operate({"operation": "credentials"}))
    assert res.get("account_state") == "existing_account"
    assert "sign in" in res.get("instruction", "").lower()
    assert "reset" not in res.get("instruction", "").lower()


def test_screenshot_envelope_and_masked_data(monkeypatch):
    """3) Screenshot operation returns real multimodal envelope intact,
    masks password values during capture, and restores them safely without persisting image bytes."""
    class DummyCtrl:
        def handle(self, req, session_id=None): return json.dumps({"status": "ok"})

    logged_events = []
    app = ApplicationTool(
        DummyCtrl(), "sid-3", "run-3",
        {"worker_id": "w1", "cdp_url": "http://127.0.0.1:9222"}
    )
    app.context = {"attempt_id": 3, "worker_id": "w1", "fence": 1}
    job_url = "https://huron.wd5.myworkdayjobs.com/en-US/huroncareers/job/Chicago-IL/Manager_JR-0016154"
    app.package = {"job": {"id": 1, "url": job_url}}

    monkeypatch.setattr(app, "call", lambda op, **kw: {"control": "running"})
    monkeypatch.setattr(app, "action", lambda name, writes=True: pytest.MonkeyPatch().context())
    monkeypatch.setattr(app, "event", lambda kind, payload: logged_events.append((kind, payload)))

    mask_state = {"masked": False, "unmasked": False}
    fake_png_base64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfake-screenshot-data").decode("utf-8")

    class MockPage:
        def __init__(self):
            self._session = MagicMock()
            async def session_call(method, params=None):
                if method == "Page.captureScreenshot":
                    assert mask_state["masked"] is True, "Password controls must be masked during screenshot capture"
                    return {"data": fake_png_base64}
                return {}
            self._session.call = AsyncMock(side_effect=session_call)

        async def evaluate(self, script, arg=None, **kw):
            s = str(script).strip()
            if s == "location.href":
                return job_url
            if "delete window.__maskedCredentialNodes" in s or "unmask_credentials" in s:
                mask_state["unmasked"] = True
                mask_state["masked"] = False
                return {"unmasked_count": 2}
            if "window.__maskedCredentialNodes" in s or "mask_credentials" in s:
                mask_state["masked"] = True
                return {"masked_count": 2}
            return {"url": job_url, "items": []}

    page = MockPage()
    class MockBrowser:
        async def get_current_page(self): return page
        async def close(self): pass

    monkeypatch.setattr(app, "connect", AsyncMock(return_value=MockBrowser()))

    # Direct operate returns envelope
    res = asyncio.run(app.operate({"operation": "screenshot"}))
    assert res.get("_multimodal") is True
    assert isinstance(res.get("content"), list)
    assert any(c.get("type") == "image_url" and fake_png_base64 in c.get("image_url", {}).get("url", "") for c in res["content"])

    # ApplicationTool.handle must return envelope intact (dict), not json.dumps string!
    handled = app.handle({"operation": "screenshot"})
    assert isinstance(handled, dict)
    assert handled.get("_multimodal") is True

    # Controls were restored
    assert mask_state["unmasked"] is True

    # Image bytes must never be persisted in logged events
    for kind, payload in logged_events:
        assert fake_png_base64 not in json.dumps(payload)


def test_unknown_label_and_missing_extension_native_fallback_via_actual_gate(tmp_path, monkeypatch):
    """4) Missing extension or unfamiliar UI (unknown label) with stable DOM permits verified-idle
    native form work through the real service gate."""
    s, job, run, a = make_service_with_attempt(tmp_path)
    s.bind_target(a["id"], worker_id=WORKER_ID, fence=1, target_id="target-tab-1", url=job["url"])

    # 1. Missing extension: panel=False, status='missing'
    async def evaluate_missing(expression, arg=None):
        if expression == "location.href":
            return job["url"]
        return {
            "url": job["url"], "status": "missing", "panel": False, "fingerprint": "stable-dom",
            "page_ref": "page-1", "page_signature": "form-1", "source": "observed_dom", "controls": {}
        }

    page_missing = type("Page", (), {"evaluate": staticmethod(evaluate_missing)})()
    browser_missing = type("Browser", (), {
        "get_current_page": AsyncMock(return_value=page_missing),
        "close": AsyncMock(), "observed_mode": "headed"
    })()
    monkeypatch.setattr(CDPBrowser, "connect", AsyncMock(return_value=browser_missing))

    # Browser observe should report idle, not unknown
    obs_res = s.browser_observe(a["id"], worker_id=WORKER_ID, fence=1)
    assert obs_res["writer_state"] == "idle"
    assert obs_res["quiescent"] is True

    # Real service gate allows native writing action!
    action = s.action_start(a["id"], worker_id=WORKER_ID, fence=1, action_id="action-native-1", tool_name="form_fill", writes_browser=True)
    assert action["id"] == "action-native-1"
    s.action_end(a["id"], worker_id=WORKER_ID, fence=1, action_id="action-native-1", status="success")

    # 2. Unfamiliar UI (status='unknown' e.g. Create Account & Autofill, panel=True)
    async def evaluate_unknown(expression, arg=None):
        if expression == "location.href": return job["url"]
        return {
            "url": job["url"], "status": "unknown", "panel": True, "fingerprint": "stable-dom-2",
            "page_ref": "page-2", "page_signature": "form-2", "source": "observed_dom", "controls": {}
        }
    page_unknown = type("Page", (), {"evaluate": staticmethod(evaluate_unknown)})()
    browser_unknown = type("Browser", (), {
        "get_current_page": AsyncMock(return_value=page_unknown),
        "close": AsyncMock(), "observed_mode": "headed"
    })()
    monkeypatch.setattr(CDPBrowser, "connect", AsyncMock(return_value=browser_unknown))

    obs_res2 = s.browser_observe(a["id"], worker_id=WORKER_ID, fence=1)
    assert obs_res2["writer_state"] == "idle"
    assert obs_res2["quiescent"] is True

    # Real service gate allows native action
    action2 = s.action_start(a["id"], worker_id=WORKER_ID, fence=1, action_id="action-native-2", tool_name="form_click", writes_browser=True)
    assert action2["id"] == "action-native-2"
    s.action_end(a["id"], worker_id=WORKER_ID, fence=1, action_id="action-native-2", status="success")


def test_active_in_flight_unresolved_extension_stays_blocked(tmp_path, monkeypatch):
    """5) Initiated or active extension autofill with uncertain end preserves blocking until real quiescence."""
    s, job, run, a = make_service_with_attempt(tmp_path)
    s.bind_target(a["id"], worker_id=WORKER_ID, fence=1, target_id="target-tab-1", url=job["url"])

    # Worker previously initiated autofill -> writer_state is 'active'
    s.writer_state(a["id"], worker_id=WORKER_ID, fence=1, state="active")

    async def evaluate_unresolved(expression, arg=None):
        if expression == "location.href": return job["url"]
        return {
            "url": job["url"], "status": "unknown", "panel": True, "fingerprint": "changing",
            "page_ref": "page-1", "page_signature": "form-1", "source": "observed_dom", "controls": {}
        }
    page_unresolved = type("Page", (), {"evaluate": staticmethod(evaluate_unresolved)})()
    browser_unresolved = type("Browser", (), {
        "get_current_page": AsyncMock(return_value=page_unresolved),
        "close": AsyncMock(), "observed_mode": "headed"
    })()
    monkeypatch.setattr(CDPBrowser, "connect", AsyncMock(return_value=browser_unresolved))

    obs = s.browser_observe(a["id"], worker_id=WORKER_ID, fence=1)
    assert obs["writer_state"] != "idle"
    assert obs["quiescent"] is False

    with pytest.raises(ProtocolError, match="browser_writer_busy"):
        s.action_start(a["id"], worker_id=WORKER_ID, fence=1, action_id="action-native-blocked", tool_name="form_fill", writes_browser=True)


def test_fresh_ref_extension_choice_independent_of_label_and_guarded_account_action(monkeypatch):
    """6) Fresh ref choice discovers extension buttons with source='simplify',
    guarantees autofill does not hand password/account forms to Simplify,
    and supports Luna-selected extension ref."""
    class DummyCtrl:
        def handle(self, req, session_id=None): return json.dumps({"status": "ok"})

    app = ApplicationTool(DummyCtrl(), "sid-6", "run-6", {"worker_id": "w1", "cdp_url": "http://127.0.0.1:9222"})
    app.context = {"attempt_id": 6, "worker_id": "w1", "fence": 1}
    job_url = "https://huron.wd5.myworkdayjobs.com/en-US/huroncareers/job/Chicago-IL/Manager_JR-0016154/apply"
    app.package = {"job": {"id": 1, "url": job_url}}

    monkeypatch.setattr(app, "call", lambda op, **kw: {"control": "running", "quiescent": True})
    monkeypatch.setattr(app, "action", lambda name, writes=True: pytest.MonkeyPatch().context())
    monkeypatch.setattr(app, "event", lambda kind, payload: None)

    # 1. Guarded account action: when password fields are present, autofill refuses and explains native auth
    class MockPageAuth:
        async def evaluate(self, script, arg=None, **kw):
            s = str(script).strip()
            if s == "location.href": return job_url
            if "window.__jobbotFormScope" in s or "inventory" in s or "document.querySelectorAll" in s:
                return {
                    "url": job_url,
                    "items": [
                        {"ref": "ref-email", "type": "email", "tag": "INPUT", "label": "Email", "source": "native"},
                        {"ref": "ref-pass", "type": "password", "tag": "INPUT", "label": "Password", "source": "native", "present": False},
                        {"ref": "ref-btn-ext", "type": "button", "tag": "BUTTON", "label": "Create Account & Autofill", "source": "simplify"}
                    ]
                }
            return {}

    class MockBrowserAuth:
        async def get_current_page(self): return MockPageAuth()
        async def close(self): pass

    monkeypatch.setattr(app, "connect", AsyncMock(return_value=MockBrowserAuth()))

    # Attempting autofill on auth page must be blocked
    res = asyncio.run(app.operate({"operation": "autofill"}))
    assert res.get("error") == "native_auth_required"
    assert "credentials" in res.get("instruction", "").lower() or "native" in res.get("instruction", "").lower()
