"""Tests for owned CDP target selection in CDPBrowser.connect.

Verifies:
- Keyword-only `target_id=None` parameter in CDPBrowser.connect.
- Exact page target matching (never fallback to first or blank tab).
- Missing, closed, or non-page target ID raises before _WS.connect.
- Conflicting combinations (target_id + create_new/page_url_substring) rejected.
- Empty or invalid target_id rejected.
- Non-loopback CDP URLs rejected when explicit target_id is supplied.
- Unsafe, remote, port-mismatched, or credentialed webSocketDebuggerUrls rejected.
- Legacy backward compatibility preserved for calls without target_id.
"""

from __future__ import annotations

import asyncio
import inspect
import io
import json
import urllib.request
from typing import Any

import pytest

from job_applier.cdp_client import CDPBrowser, CDPPage, _CDPSession, _WS


class ContextBytesIO(io.BytesIO):
    """Context-managed BytesIO simulating an HTTPResponse stream from urllib.request.urlopen."""

    def __enter__(self) -> "ContextBytesIO":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class DummyWS:
    """Minimal WebSocket transport seam stub."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def cdp_transport(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Transport seam monkeypatching urllib.request.urlopen, _WS.connect, and _CDPSession lifecycle.

    Constructs real CDPBrowser, CDPPage, and _CDPSession instances without opening network sockets.
    """
    connected_ws_urls: list[str] = []
    session_calls: list[str] = []

    # Multi-target fixture: first tab, blank tab, owned target, and a non-page service worker
    targets_data: list[dict[str, Any]] = [
        {
            "id": "target-unrelated-first",
            "type": "page",
            "url": "http://127.0.0.1:8080/jobs/listing/1",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/target-unrelated-first",
        },
        {
            "id": "target-blank",
            "type": "page",
            "url": "about:blank",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/target-blank",
        },
        {
            "id": "target-owned-42",
            "type": "page",
            "url": "http://127.0.0.1:8080/apply/target-owned-42",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/target-owned-42",
        },
        {
            "id": "worker-target",
            "type": "service_worker",
            "url": "http://127.0.0.1:8080/sw.js",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/worker-target",
        },
    ]

    new_target_data: dict[str, Any] = {
        "id": "target-newly-created",
        "type": "page",
        "url": "about:blank",
        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/target-newly-created",
    }

    state: dict[str, Any] = {
        "targets": targets_data,
        "new_target": new_target_data,
        "ws_urls": connected_ws_urls,
        "session_calls": session_calls,
    }

    def fake_urlopen(url_or_req: Any, *args: Any, **kwargs: Any) -> ContextBytesIO:
        req_url = url_or_req.full_url if hasattr(url_or_req, "full_url") else str(url_or_req)
        if "/json/new" in req_url:
            return ContextBytesIO(json.dumps(state["new_target"]).encode("utf-8"))
        return ContextBytesIO(json.dumps(state["targets"]).encode("utf-8"))

    @classmethod
    async def fake_ws_connect(cls: Any, ws_url: str) -> DummyWS:
        connected_ws_urls.append(ws_url)
        return DummyWS()

    async def fake_session_start(self: Any) -> None:
        session_calls.append("start")

    async def fake_session_call(self: Any, method: str, params: Any = None, timeout: float = 30.0) -> dict[str, Any]:
        session_calls.append(method)
        return {}

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(_WS, "connect", fake_ws_connect)
    monkeypatch.setattr(_CDPSession, "start", fake_session_start)
    monkeypatch.setattr(_CDPSession, "call", fake_session_call)

    return state


def test_connect_target_id_keyword_only_signature() -> None:
    """target_id must be a keyword-only parameter defaulting to None in CDPBrowser.connect."""
    sig = inspect.signature(CDPBrowser.connect)
    assert "target_id" in sig.parameters, "CDPBrowser.connect signature must accept 'target_id'"
    param = sig.parameters["target_id"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, "target_id must be keyword-only"
    assert param.default is None, "target_id default must be None"


def test_connect_exact_target_id_selected(cdp_transport: dict[str, Any]) -> None:
    """Explicit target_id selects exact matching page target and never falls back to first/blank tab."""
    browser = asyncio.run(CDPBrowser.connect("http://127.0.0.1:9222", target_id="target-owned-42"))
    assert isinstance(browser, CDPBrowser)
    assert browser.target_id == "target-owned-42"
    assert isinstance(browser._page, CDPPage)
    assert browser._page.target_id == "target-owned-42"
    assert browser._page.url == "http://127.0.0.1:8080/apply/target-owned-42"
    assert cdp_transport["ws_urls"] == ["ws://127.0.0.1:9222/devtools/page/target-owned-42"]
    assert "start" in cdp_transport["session_calls"]
    assert all(m in cdp_transport["session_calls"] for m in ["Page.enable", "DOM.enable", "Runtime.enable"])


@pytest.mark.parametrize(
    "missing_target_id",
    [
        "target-missing-123",
        "target-closed-tab",
        "worker-target",  # Present in target list, but type is service_worker, not page
    ],
)
def test_connect_missing_or_closed_target_id_raises_before_ws(
    cdp_transport: dict[str, Any], missing_target_id: str
) -> None:
    """Missing or closed target_id must raise before _WS.connect without falling back."""
    with pytest.raises((ValueError, RuntimeError)) as excinfo:
        asyncio.run(CDPBrowser.connect("http://127.0.0.1:9222", target_id=missing_target_id))
    assert "unexpected keyword argument" not in str(excinfo.value)
    assert cdp_transport["ws_urls"] == [], "Must not attempt _WS.connect on missing or closed target_id"


@pytest.mark.parametrize(
    "conflict_kwargs",
    [
        {"create_new": True},
        {"page_url_substring": "apply"},
        {"create_new": True, "page_url_substring": "apply"},
    ],
)
def test_connect_rejects_conflicting_options_with_target_id(
    cdp_transport: dict[str, Any], conflict_kwargs: dict[str, Any]
) -> None:
    """Combining target_id with create_new or page_url_substring must be rejected before _WS.connect."""
    with pytest.raises((ValueError, RuntimeError)) as excinfo:
        asyncio.run(CDPBrowser.connect("http://127.0.0.1:9222", target_id="target-owned-42", **conflict_kwargs))
    assert "unexpected keyword argument" not in str(excinfo.value)
    assert cdp_transport["ws_urls"] == [], "Must not attempt _WS.connect when conflicting options are passed"


@pytest.mark.parametrize(
    "invalid_id",
    [
        "",
        "   ",
        "\t\n",
        123,
        True,
        ["target-owned-42"],
    ],
)
def test_connect_rejects_empty_or_invalid_target_id(
    cdp_transport: dict[str, Any], invalid_id: Any
) -> None:
    """Empty, whitespace, or non-string target_id must be rejected before _WS.connect."""
    with pytest.raises((ValueError, RuntimeError, TypeError)) as excinfo:
        asyncio.run(CDPBrowser.connect("http://127.0.0.1:9222", target_id=invalid_id))
    assert "unexpected keyword argument" not in str(excinfo.value)
    assert cdp_transport["ws_urls"] == [], "Must not attempt _WS.connect when target_id is invalid or empty"


@pytest.mark.parametrize(
    "non_loopback_url",
    [
        "http://remote.example.com:9222",
        "http://192.168.1.100:9222",
        "http://10.0.0.5:9222",
        "https://127.0.0.1:9222",  # Must be http, not https
        "https://localhost:9222",
        "ftp://127.0.0.1:9222",
    ],
)
def test_connect_managed_target_requires_loopback_http_cdp_url(
    cdp_transport: dict[str, Any], non_loopback_url: str
) -> None:
    """Explicit target_id requests must use a loopback http CDP URL."""
    with pytest.raises((ValueError, RuntimeError)) as excinfo:
        asyncio.run(CDPBrowser.connect(non_loopback_url, target_id="target-owned-42"))
    assert "unexpected keyword argument" not in str(excinfo.value)
    assert cdp_transport["ws_urls"] == [], "Must not attempt _WS.connect with non-loopback or non-http CDP URL"


@pytest.mark.parametrize(
    "unsafe_ws_url",
    [
        "ws://evil.com:9222/devtools/page/target-owned-42",  # Remote host redirect
        "ws://127.0.0.1:9999/devtools/page/target-owned-42",  # Port mismatch
        "ws://127.0.0.1:9222/devtools/page/other-target",  # Target mismatch in path
        "ws://127.0.0.1:9222/devtools/browser",  # Non-page/browser target path
        "ws://127.0.0.1:9222/devtools/page/",  # Missing target in path
        "ws://user:pass@127.0.0.1:9222/devtools/page/target-owned-42",  # Credentials
        "ws://127.0.0.1:9222/devtools/page/target-owned-42?redirect=evil.com",  # Query string
        "ws://127.0.0.1:9222/devtools/page/target-owned-42#remote",  # Fragment
    ],
)
def test_connect_rejects_unsafe_websocket_debugger_urls(
    cdp_transport: dict[str, Any], unsafe_ws_url: str
) -> None:
    """webSocketDebuggerUrl must stay on loopback port, match exact target in path, and have no creds/query/frag."""
    cdp_transport["targets"] = [
        {
            "id": "target-owned-42",
            "type": "page",
            "url": "http://127.0.0.1:8080/apply/target-owned-42",
            "webSocketDebuggerUrl": unsafe_ws_url,
        }
    ]
    with pytest.raises((ValueError, RuntimeError)) as excinfo:
        asyncio.run(CDPBrowser.connect("http://127.0.0.1:9222", target_id="target-owned-42"))
    assert "unexpected keyword argument" not in str(excinfo.value)
    assert cdp_transport["ws_urls"] == [], "Must not connect to unsafe or mismatched webSocketDebuggerUrl"


@pytest.mark.parametrize(
    ("call_kwargs", "expected_id", "expected_ws"),
    [
        ({}, "target-blank", "ws://127.0.0.1:9222/devtools/page/target-blank"),
        (
            {"page_url_substring": "jobs/listing/1"},
            "target-unrelated-first",
            "ws://127.0.0.1:9222/devtools/page/target-unrelated-first",
        ),
        (
            {"create_new": True},
            "target-newly-created",
            "ws://127.0.0.1:9222/devtools/page/target-newly-created",
        ),
    ],
)
def test_connect_legacy_selection_semantics_backward_compatible(
    cdp_transport: dict[str, Any],
    call_kwargs: dict[str, Any],
    expected_id: str,
    expected_ws: str,
) -> None:
    """Legacy calls without target_id maintain existing selection semantics."""
    browser = asyncio.run(CDPBrowser.connect("http://127.0.0.1:9222", **call_kwargs))
    assert isinstance(browser, CDPBrowser)
    assert browser.target_id == expected_id
    assert browser._page.target_id == expected_id
    assert cdp_transport["ws_urls"] == [expected_ws]


def test_connect_legacy_fallback_when_no_blank_tab(cdp_transport: dict[str, Any]) -> None:
    """Legacy calls fall back to first page target when no about:blank target exists."""
    cdp_transport["targets"] = [
        {
            "id": "target-first",
            "type": "page",
            "url": "http://127.0.0.1:8080/page1",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/target-first",
        },
        {
            "id": "target-second",
            "type": "page",
            "url": "http://127.0.0.1:8080/page2",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/target-second",
        },
    ]
    browser = asyncio.run(CDPBrowser.connect("http://127.0.0.1:9222"))
    assert browser.target_id == "target-first"
    assert cdp_transport["ws_urls"] == ["ws://127.0.0.1:9222/devtools/page/target-first"]


def test_connect_explicit_target_id_none_is_backward_compatible(cdp_transport: dict[str, Any]) -> None:
    """Passing target_id=None explicitly behaves identically to legacy calls."""
    browser = asyncio.run(CDPBrowser.connect("http://127.0.0.1:9222", target_id=None))
    assert isinstance(browser, CDPBrowser)
    assert browser.target_id == "target-blank"
    assert cdp_transport["ws_urls"] == ["ws://127.0.0.1:9222/devtools/page/target-blank"]
