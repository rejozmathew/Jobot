"""browser-use-compatible page/element shim over the fast raw-CDP client.

WorkdayHandler is written against browser-use's element API:
    page = await session.get_current_page()
    els  = await page.get_elements_by_css_selector(selector)
    await element.evaluate("(el) => {...}")      # fn called with the element as arg
    await element.get_attribute("value")
    await element.fill("text")
    await element.click()
    await element.check()

cdp_client.py deliberately avoids browser-use (its Browser.start() hangs on a
multi-tab real browser). This module adapts the fast CDP session to the same
surface so the deterministic Workday/Greenhouse handlers can run on it without
the watchdog path.

Usage:
    from job_applier.cdp_client import CDPBrowser
    from job_applier.bu_compat import make_bu_session
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    bu_session = make_bu_session(cdp)          # has get_current_page() / start()
    handler = WorkdayHandler(browser_session=bu_session, profile=..., job_url=...)
    outcome = await handler.run()
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from .cdp_client import CDPBrowser, CDPPage, CDPElement as _RawElement


class BUElement:
    """A DOM element speaking browser-use's element API, backed by a CDP objectId."""

    def __init__(self, cdp: CDPBrowser, object_id: str):
        self._cdp = cdp
        self._s = cdp._session  # _CDPSession
        self.object_id = object_id

    async def _call(self, function_declaration: str, args: Optional[list[dict]] = None,
                    return_by_value: bool = True, timeout: float = 30.0) -> Any:
        params: dict[str, Any] = {
            "objectId": self.object_id,
            "functionDeclaration": function_declaration,
            "returnByValue": return_by_value,
        }
        if args:
            params["arguments"] = args
            params["silent"] = False
        res = await self._s.call("Runtime.callFunctionOn", params, timeout=timeout)
        if "exceptionDetails" in res:
            det = res["exceptionDetails"]
            text = (det.get("exception") or {}).get("description") or det.get("text", "js error")
            raise RuntimeError(f"callFunctionOn: {text[:400]}")
        return res.get("result", {}).get("value")

    async def evaluate(self, expression: str) -> Any:
        """Run `expression` as a function with this element passed as the first arg.

        Accepts a function expression like `(el) => {...}` (browser-use convention)
        or a plain value expression (evaluated with `this` = element).
        """
        expr = (expression or "").strip()
        looks_like_fn = expr.startswith("(") and "=>" in expr or expr.startswith("function")
        if looks_like_fn:
            return await self._call(expr, args=[{"objectId": self.object_id}])
        # value expression: run with this = element
        return await self._call("function(){ return (" + expr + "); }")

    async def get_attribute(self, name: str) -> Any:
        return await self._call(
            "function(n){ try { return this.getAttribute(n); } catch(e){ return null; } }",
            args=[{"value": name}],
        )

    async def text_content(self) -> str:
        try:
            v = await self._call("function(){ return this.textContent || ''; }")
            return " ".join(str(v or "").split())
        except Exception:
            return ""

    async def _center(self) -> Optional[tuple[float, float]]:
        rect = await self._call(
            "function(){ try { this.scrollIntoView({block:'center'});}catch(e){} "
            "var r=this.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height};"
            "}"
        )
        if not rect or rect.get("w", 0) <= 0:
            # fall back to JS click
            return None
        cx = rect["x"] + rect["w"] / 2
        cy = rect["y"] + rect["h"] / 2
        return (cx, cy)

    async def click(self) -> None:
        try:
            center = await self._center()
        except Exception:
            center = None
        if center:
            x, y = center
            await self._s.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
            await self._s.call("Input.dispatchMouseEvent",
                               {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
            await self._s.call("Input.dispatchMouseEvent",
                               {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
            return
        # fallback: JS click
        try:
            await self._call("function(){ this.click(); }")
        except Exception:
            pass

    async def fill(self, value: str) -> None:
        """Clear (React-safe) then focus + insert text via CDP Input.

        Clearing first is essential: Workday/React controlled inputs keep their
        value across re-renders, so a bare type_text appends. The Workday state
        loop can re-enter the same field, and without clearing the value doubles
        (e.g. email 'a@b.coma@b.com'), silently failing submit validation.
        """
        value = str(value or "")
        try:
            await self._call(
                "function(){ try{this.scrollIntoView({block:'center'});}catch(e){} this.focus(); }"
            )
            await asyncio.sleep(0.1)
            # Clear any existing value using the native setter (React-safe).
            await self._call(
                "function(){ "
                "var proto = this.tagName==='TEXTAREA' ? window.HTMLTextAreaElement.prototype "
                ": (this.tagName==='SELECT' ? window.HTMLSelectElement.prototype "
                ": window.HTMLInputElement.prototype); "
                "var d = Object.getOwnPropertyDescriptor(proto,'value'); "
                "if (d && d.set) { d.set.call(this, ''); } else { this.value=''; } "
                "this.dispatchEvent(new Event('input',{bubbles:true})); "
                "}"
            )
            await asyncio.sleep(0.08)
            if value:
                await self._cdp.type_text(value)
                await asyncio.sleep(0.1)
            # ensure React controlled inputs see it
            await self._call(
                "function(){ this.dispatchEvent(new Event('input',{bubbles:true})); "
                "this.dispatchEvent(new Event('change',{bubbles:true})); }"
            )
        except Exception:
            # last resort: set .value directly (React-safe setter) + events
            await self._call(
                "function(v){ "
                "var proto = window.HTMLInputElement.prototype; "
                "var d = Object.getOwnPropertyDescriptor(proto,'value'); "
                "if (d && d.set) { d.set.call(this, v); } else { this.value = v; } "
                "this.focus(); "
                "this.dispatchEvent(new Event('input',{bubbles:true})); "
                "this.dispatchEvent(new Event('change',{bubbles:true})); }",
                args=[{"value": value}],
            )

    async def check(self) -> None:
        try:
            state = await self._call("function(){ return !!(this.checked); }")
            if not state:
                await self.click()
        except Exception:
            await self.click()

    # compatibility aliases some code paths use
    async def is_checked(self) -> bool:
        try:
            return bool(await self._call("function(){ return !!this.checked; }"))
        except Exception:
            return False


class BUPage:
    """Page speaking browser-use's page API, backed by the CDP session."""

    def __init__(self, cdp: CDPBrowser):
        self._cdp = cdp
        self._s = cdp._session

    async def get_current_page(self) -> "BUPage":
        return self

    async def wait_for_timeout(self, ms: int) -> None:
        await asyncio.sleep(max(0, int(ms)) / 1000.0)

    async def evaluate(self, expression: str, *args: Any) -> Any:
        # delegate to the proven CDPPage.evaluate (handles fn-expr + dict arg)
        arg = args[0] if len(args) == 1 else None
        return await (await self._cdp.get_current_page()).evaluate(expression, arg)

    async def get_elements_by_css_selector(self, selector: str) -> list[BUElement]:
        raw = await (await self._cdp.get_current_page()).query_selector_all(selector)
        return [BUElement(self._cdp, e.object_id) for e in raw]

    async def goto(self, url: str) -> None:
        await (await self._cdp.get_current_page()).goto(url)

    async def navigate_to(self, url: str, new_tab: bool = False) -> None:
        await (await self._cdp.get_current_page()).goto(url)

    async def screenshot(self, path: str) -> str:
        return await self._cdp.screenshot(path)


class BUSession:
    """Drop-in for browser_session: exposes get_current_page() / start()."""

    def __init__(self, cdp: CDPBrowser):
        self._cdp = cdp
        self._page = BUPage(cdp)

    async def get_current_page(self) -> BUPage:
        return self._page

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        await self._cdp.close()


def make_bu_session(cdp: CDPBrowser) -> BUSession:
    return BUSession(cdp)
