"""Tests for CDPPage.evaluate_function explicit Runtime.callFunctionOn path.

Verifies:
- CDPPage.evaluate_function(function_declaration, arg=None, timeout=30)
- Calls Runtime.callFunctionOn with functionDeclaration, returnByValue=True, awaitPromise=True
- Passes arg as JSON CallArgument [{"value": arg}] when arg is provided
- Omits arguments parameter when arg is None
- Returns JSON primitive values directly
- Surfaces JS exceptions from exceptionDetails as RuntimeError
- Does not alter evaluate API or behavior
"""

from __future__ import annotations

import asyncio
from typing import Any
import pytest

from job_applier.cdp_client import CDPPage


class FakeCDPSession:
    """Mock CDP session recording calls and returning configured responses."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any], float]] = []
        self.responses = responses or {}

    async def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
        params = params or {}
        self.calls.append((method, params, timeout))
        if method in self.responses:
            resp = self.responses[method]
            if isinstance(resp, Exception):
                raise resp
            if callable(resp):
                return resp(params)
            return resp
        if method == 'Runtime.evaluate':return {'result':{'objectId':'global-object'}}
        return {}


def test_evaluate_function_calls_runtime_call_function_on_with_arg() -> None:
    """evaluate_function invokes Runtime.callFunctionOn with JSON CallArgument and returnByValue."""
    session = FakeCDPSession({
        "Runtime.callFunctionOn": {
            "result": {"type": "object", "value": {"status": "ok", "count": 3}}
        }
    })
    page = CDPPage(session, "target-1", "https://example.test")

    fn = "(args) => ({ status: 'ok', count: args.x + 1 })"
    res = asyncio.run(page.evaluate_function(fn, arg={"x": 2}, timeout=15.0))

    assert res == {"status": "ok", "count": 3}
    assert len(session.calls) == 3
    method, params, timeout = session.calls[1]
    assert method == "Runtime.callFunctionOn"
    assert params["functionDeclaration"] == fn
    assert params["arguments"] == [{"value": {"x": 2}}]
    assert params["returnByValue"] is True
    assert params["awaitPromise"] is True
    assert timeout == 15.0


def test_evaluate_function_without_arg_omits_arguments() -> None:
    """evaluate_function without arg passes no arguments and returns primitive scalar."""
    session = FakeCDPSession({
        "Runtime.callFunctionOn": {
            "result": {"type": "number", "value": 42}
        }
    })
    page = CDPPage(session, "target-1", "https://example.test")

    fn = "function() { return 42; }"
    res = asyncio.run(page.evaluate_function(fn))

    assert res == 42
    assert len(session.calls) == 3
    method, params, _ = session.calls[1]
    assert method == "Runtime.callFunctionOn"
    assert params["functionDeclaration"] == fn
    assert "arguments" not in params
    assert params["returnByValue"] is True
    assert params["awaitPromise"] is True


def test_evaluate_function_surfaces_js_exception() -> None:
    """evaluate_function raises RuntimeError when exceptionDetails is returned."""
    session = FakeCDPSession({
        "Runtime.callFunctionOn": {
            "result": {"type": "undefined"},
            "exceptionDetails": {
                "text": "Uncaught TypeError: Cannot read properties of undefined",
                "exception": {
                    "type": "object",
                    "description": "TypeError: Cannot read properties of undefined (reading 'foo')",
                },
            },
        }
    })
    page = CDPPage(session, "target-1", "https://example.test")

    fn = "(args) => args.foo"
    with pytest.raises(RuntimeError, match="evaluate error.*TypeError"):
        asyncio.run(page.evaluate_function(fn, arg=None))


def test_evaluate_function_timeout_passed_to_session() -> None:
    """evaluate_function respects custom timeout parameter."""
    session = FakeCDPSession({
        "Runtime.callFunctionOn": {"result": {"type": "string", "value": "done"}}
    })
    page = CDPPage(session, "target-1", "https://example.test")

    asyncio.run(page.evaluate_function("() => 'done'", timeout=5.5))
    assert session.calls[0][2] == 5.5


def test_evaluate_backward_compatible_and_uses_runtime_evaluate() -> None:
    """Existing evaluate() method continues to use Runtime.evaluate without breaking."""
    session = FakeCDPSession({
        "Runtime.evaluate": {"result": {"type": "string", "value": "compat"}}
    })
    page = CDPPage(session, "target-1", "https://example.test")

    res = asyncio.run(page.evaluate("location.href"))
    assert res == "compat"
    assert session.calls[0][0] == "Runtime.evaluate"


def test_function_call_binds_execution_context_required_by_chrome():
    def validate(params):
        assert params.get('objectId') or params.get('executionContextId'), 'Chrome requires a context or remote object'
        return {'result':{'value':'verified'}}
    session=FakeCDPSession({'Runtime.evaluate':{'result':{'objectId':'global-object'}},'Runtime.callFunctionOn':validate})
    page=CDPPage(session,'target','https://example.test')
    assert asyncio.run(page.evaluate_function('() => "verified"'))=='verified'
