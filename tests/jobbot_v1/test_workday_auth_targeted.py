"""Targeted tests for Workday auth bundle, URL scope, credential bridge, and browser mode."""
import json
import pytest
from unittest.mock import MagicMock, patch

from job_applier.cdp_client import CDPBrowser, inspect_browser_mode
from job_applier.managed_shared import ProtocolError


def test_inspect_browser_mode_detection():
    # Detects headless
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"Browser": "HeadlessChrome/124.0.0"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp
        assert inspect_browser_mode("http://127.0.0.1:9222") == "headless"

    # Detects headed when reported in version info
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"Browser": "Chrome/124.0.0 (headed)"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp
        assert inspect_browser_mode("http://127.0.0.1:9222") == "headed"


def test_cdp_browser_connect_browser_mode_mismatch():
    # 1. Headed expected, headless observed -> fails
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"Browser": "HeadlessChrome/124.0.0"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        import asyncio
        with pytest.raises(ValueError, match="headless browser cannot satisfy headed request"):
            asyncio.run(CDPBrowser.connect("http://127.0.0.1:9222", expected_mode="headed"))

    # 2. Headless expected, headed observed -> fails
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"Browser": "Chrome/124.0.0 (headed)"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        import asyncio
        with pytest.raises(ValueError, match="headed browser cannot satisfy headless request"):
            asyncio.run(CDPBrowser.connect("http://127.0.0.1:9222", expected_mode="headless"))
from job_applier.managed_identity import is_workday_application_scope, is_same_application_scope


def test_workday_application_scope_allowed_routes():
    base = "https://huron.wd5.myworkdayjobs.com/en-US/huroncareers/job/Chicago-IL/Manager_JR-0016154"

    # Same job, same locale
    assert is_workday_application_scope(base, base) is True

    # Same job, stripped locale
    no_locale = "https://huron.wd5.myworkdayjobs.com/huroncareers/job/Chicago-IL/Manager_JR-0016154"
    assert is_workday_application_scope(base, no_locale) is True

    # Same job, different locale
    other_locale = "https://huron.wd5.myworkdayjobs.com/fr-CA/huroncareers/job/Chicago-IL/Manager_JR-0016154"
    assert is_workday_application_scope(base, other_locale) is True

    # Allowed child routes
    for child in [
        "/apply",
        "/apply/applyManually",
        "/apply/autofillWithResume",
        "/apply/useMyLastApplication",
        "/apply/success",
        "/confirmation",
        "/apply/",
    ]:
        cand = f"https://huron.wd5.myworkdayjobs.com/en-US/huroncareers/job/Chicago-IL/Manager_JR-0016154{child}"
        assert is_workday_application_scope(base, cand) is True
        cand_no_loc = f"https://huron.wd5.myworkdayjobs.com/huroncareers/job/Chicago-IL/Manager_JR-0016154{child}"
        assert is_workday_application_scope(base, cand_no_loc) is True


def test_workday_application_scope_rejections():
    base = "https://huron.wd5.myworkdayjobs.com/en-US/huroncareers/job/Chicago-IL/Manager_JR-0016154"

    # Sibling job
    sibling = "https://huron.wd5.myworkdayjobs.com/en-US/huroncareers/job/Chicago-IL/Manager_JR-0016155"
    assert is_workday_application_scope(base, sibling) is False

    # Sibling tenant
    tenant = "https://huron.wd5.myworkdayjobs.com/en-US/othercareers/job/Chicago-IL/Manager_JR-0016154"
    assert is_workday_application_scope(base, tenant) is False

    # Sibling host
    host = "https://other.wd5.myworkdayjobs.com/en-US/huroncareers/job/Chicago-IL/Manager_JR-0016154"
    assert is_workday_application_scope(base, host) is False

    # Arbitrary subpath
    assert is_workday_application_scope(base, base + "/apply/unauthorized") is False
    assert is_workday_application_scope(base, base + "/edit") is False

    # User dashboard / login
    assert is_workday_application_scope(base, "https://huron.wd5.myworkdayjobs.com/en-US/huroncareers/userHome") is False
    assert is_workday_application_scope(base, "https://huron.wd5.myworkdayjobs.com/en-US/huroncareers/login") is False

    # Path tricks: dot and encoded slashes
    assert is_workday_application_scope(base, base + "/..") is False
    assert is_workday_application_scope(base, base + "/%2e%2e") is False
    assert is_workday_application_scope(base, base + "/apply%2fextra") is False
    assert is_workday_application_scope(base, base + "/apply%5cextra") is False

    # Sensitive query parameters
    assert is_workday_application_scope(base, base + "/apply?reset_token=secret") is False
    assert is_workday_application_scope(base, base + "/apply?otp=123456") is False
    assert is_workday_application_scope(base, base + "/apply?password=secret") is False

    # HTTP rejected
    http_cand = "http://huron.wd5.myworkdayjobs.com/en-US/huroncareers/job/Chicago-IL/Manager_JR-0016154/apply"
    assert is_workday_application_scope(base, http_cand) is False


def test_greenhouse_preservation():
    gh_base = "https://job-boards.greenhouse.io/acme/jobs/123456"
    assert is_same_application_scope(gh_base, gh_base) is True
    assert is_same_application_scope(gh_base, gh_base + "/apply") is True
    assert is_same_application_scope(gh_base, gh_base + "/confirmation") is True
    # Greenhouse rejects sibling job
    assert is_same_application_scope(gh_base, "https://job-boards.greenhouse.io/acme/jobs/123457") is False


def test_workday_details_to_canonical_job_keeps_exact_requisition_scope():
    base = "https://tenant.wd1.myworkdayjobs.com/en-US/Careers/details/Director_R12345-1?q=director"
    canonical = "https://tenant.wd1.myworkdayjobs.com/Careers/job/GBR---Oxford/Director_R12345-1"
    for child in ("", "/apply", "/apply/applyManually", "/apply/success"):
        assert is_same_application_scope(base, canonical + child)
    assert is_same_application_scope(canonical, base)
    for candidate in (
        canonical.replace("R12345-1", "R12346-1"),
        canonical.replace("R12345-1", "R12345-2"),
        canonical.replace("/Careers/", "/OtherCareers/"),
        canonical.replace("tenant.wd1", "other.wd1"),
        canonical + "/apply/unauthorized",
        canonical + "/apply?otp=123456",
    ):
        assert not is_same_application_scope(base, candidate)
import asyncio
from unittest.mock import AsyncMock

from job_applier.managed_hermes_worker import ApplicationTool


def test_anchor_click_valid_and_invalid(monkeypatch):
    class DummyCtrl:
        def handle(self, req, session_id=None):
            return json.dumps({"status": "ok"})

    app = ApplicationTool(DummyCtrl(), "sid-1", "run-1", {"worker_id": "w1", "cdp_url": "http://127.0.0.1:9222"})
    app.context = {"attempt_id": 1, "worker_id": "w1", "fence": 1}
    job_url = "https://huron.wd5.myworkdayjobs.com/en-US/huroncareers/job/Chicago-IL/Manager_JR-0016154"
    app.package = {"job": {"id": 1, "url": job_url}}
    monkeypatch.setattr(app, "call", lambda op, **kw: {"control": "running"})
    monkeypatch.setattr(app, "action", lambda name, writes=True: pytest.MonkeyPatch().context())
    monkeypatch.setattr(app, "event", lambda kind, payload: None)
    monkeypatch.setattr(app, "inventory", AsyncMock(return_value={"url": job_url, "items": []}))

    # 1. Hostile anchor (sibling job) -> rejected
    class MockPageInvalid:
        async def evaluate(self, script, *args):
            if str(script).strip() == "location.href":
                return job_url
            if "is_anchor" in str(script):
                return {"is_anchor": True, "href": "https://huron.wd5.myworkdayjobs.com/en-US/huroncareers/job/Chicago-IL/Manager_JR-0016155"}
            return {}

    class MockBrowserInvalid:
        async def get_current_page(self): return MockPageInvalid()
        async def close(self): pass

    monkeypatch.setattr(app, "connect", AsyncMock(return_value=MockBrowserInvalid()))
    with pytest.raises(ValueError, match="Anchor href not in same application scope"):
        asyncio.run(app.operate({"operation": "click", "ref": "anchor-ref-1"}))

    # 2. Valid anchor (allowed descendant /apply/applyManually) -> allowed
    clicked_args = []
    class MockPageValid:
        async def evaluate(self, script, arg=None, **kw):
            if str(script).strip() == "location.href":
                return job_url
            if "is_anchor" in str(script):
                return {"is_anchor": True, "href": job_url + "/apply/applyManually"}
            clicked_args.append(arg)
            return {"clicked": True, "label": "Apply Manually"}

    class MockBrowserValid:
        async def get_current_page(self): return MockPageValid()
        async def close(self): pass

    monkeypatch.setattr(app, "connect", AsyncMock(return_value=MockBrowserValid()))
    res = asyncio.run(app.operate({"operation": "click", "ref": "anchor-ref-2"}))
    assert res == {"url": job_url, "items": []}
    assert any(isinstance(a, dict) and a.get("allowed_href") == job_url + "/apply/applyManually" for a in clicked_args)
