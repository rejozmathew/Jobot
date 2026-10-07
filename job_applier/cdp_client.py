"""Minimal raw CDP (Chrome DevTools Protocol) client for browser automation.

Why this exists:
  browser-use 0.11's ``Browser.start()`` spawns watchdogs that process every
  existing tab on connect — with a real user browser (Brave) holding dozens of
  tabs, ``start()`` hangs >15s per tab and never returns. This client speaks
  CDP directly over the WebSocket endpoint that any Chrome/Brave exposes with
  ``--remote-debugging-port``. No watchdogs, no framework, ~30 lines of
  protocol, works identically across machines and browsers.

API surface (matches what GreenhouseHandler expects via ``get_current_page``):
    session = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await session.get_current_page()
    value = await page.evaluate(js_expr, arg=None)
    await page.goto(url)
    els = await page.query_selector_all("input[type=file]")
    await els[0].set_input_files("/path/to/resume.pdf")
    await page.screenshot("/path/to/shot.png")
    await session.close()

Protocol notes:
  - Runtime.evaluate with ``returnByValue=True`` so we get JSON-serializable
    values (not remote object handles) back to Python.
  - Page.navigate for navigation; we poll Runtime.evaluate for a small delay
    rather than waiting on the full load event (Greenhouse is an SPA and we
    poll for state anyway).
  - File upload uses the two-step DOM protocol:
      DOM.getDocument -> DOM.querySelector -> DOM.setFileInputFiles
  - Every command is a CDP method call over the page's WS session.

Threading / lifecycle:
  - One WebSocket per session. Commands are serialized with an asyncio.Lock
    to avoid interleaved frames (CDP is request/response ordered per session).
  - ``close()`` cancels the WS cleanly; the underlying browser is NOT closed
    (we attached to an existing one) — only our session ends.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import threading
import base64
import json
import ipaddress
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Any, Optional


def _loopback_endpoint(cdp_url: str):
    endpoint=urlsplit(cdp_url.rstrip('/'))
    if (endpoint.scheme!='http' or endpoint.hostname not in ('127.0.0.1','localhost','::1')
            or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path):
        raise ValueError('owned_target_requires_loopback_cdp')
    return endpoint


def _public_destination(url: str) -> str:
    parsed=urlsplit(str(url or '').strip())
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        return ''
    host=parsed.hostname.rstrip('.').casefold()
    if host in ('localhost','localhost.localdomain') or host.endswith('.localhost'):
        return ''
    try:
        address=ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:return ''
    query=parse_qsl(parsed.query,keep_blank_values=True)
    if any(key.casefold() in ('access_token','refresh_token','otp','password','reset_token','authorization_code')
           for key,_ in query):return ''
    tracking={'utm_source','utm_medium','utm_campaign','utm_term','utm_content'}
    query=sorted((key,value) for key,value in query if key.casefold() not in tracking)
    return urlunsplit((parsed.scheme.lower(),parsed.netloc.lower(),parsed.path.rstrip('/'),urlencode(query),''))


def _target_rows(cdp_url: str) -> list[dict]:
    _loopback_endpoint(cdp_url)
    with urllib.request.urlopen(cdp_url.rstrip('/')+'/json/list',timeout=5) as response:
        rows=json.load(response)
    return [dict(row,targetId=row.get('targetId') or row.get('id')) for row in rows if row.get('type')=='page']


@dataclass(frozen=True)
class ApplyTargetObservation:
    cdp_url: str
    current_target_id: str
    expected_public_url: str
    baseline_target_ids: frozenset[str]
    browser_context_id: Optional[str]
    armed_at: float


class NavigationTrace:
    """Ephemeral evidence from one owned main frame, armed before an action."""
    def __init__(self, frame_id, source_url):
        self.frame_id=frame_id
        self.source_url=source_url
        self.chain=[source_url]
        self._remove=[]

    def _record(self,url):
        if _public_destination(url) and url!=self.chain[-1]:self.chain.append(url)

    def request(self,event):
        if event.get('type')=='Document' and event.get('frameId')==self.frame_id:
            self._record(event.get('request',{}).get('url'))

    def within_document(self,event):
        if event.get('frameId')==self.frame_id:self._record(event.get('url'))

    def accepts(self,url):
        from .managed_identity import explicit_job_conflict
        return bool(len(self.chain)>1 and _public_destination(url) and
                    _public_destination(self.chain[-1])==_public_destination(url) and
                    not explicit_job_conflict(self.source_url,url))

    @classmethod
    async def start(cls,page,source_url):
        session=getattr(page,'_session',None)
        if not session or not hasattr(session,'subscribe'):return None
        tree=await session.call('Page.getFrameTree')
        trace=cls(tree['frameTree']['frame']['id'],source_url)
        trace._remove=[session.subscribe('Network.requestWillBeSent',trace.request),
                       session.subscribe('Page.navigatedWithinDocument',trace.within_document)]
        await session.call('Network.enable')
        await session.call('Page.enable')
        return trace

    def close(self):
        for remove in self._remove:remove()
        self._remove=[]


def arm_target_observation(cdp_url: str, current_target_id: str, expected_url: Optional[str], *, targets=None):
    """Snapshot targets before an external Apply activation.

    An in-page/Easy Apply button has no public external destination and therefore
    does not create a popup requirement.
    """
    expected=_public_destination(expected_url)
    if not expected:return None
    _loopback_endpoint(cdp_url)
    rows=[dict(row,targetId=row.get('targetId') or row.get('id')) for row in (targets if targets is not None else _target_rows(cdp_url))]
    current=next((row for row in rows if row.get('targetId')==current_target_id and row.get('type')=='page'),None)
    if current is None:raise ValueError('owned_target_not_found')
    return ApplyTargetObservation(cdp_url.rstrip('/'),current_target_id,expected,
        frozenset(row.get('targetId') for row in rows if row.get('type')=='page' and row.get('targetId')),
        current.get('browserContextId'),time.monotonic())


async def wait_for_apply_target(observation, *, inventory=None, current_url=None, timeout=2.0, poll_interval=.05, navigation=None):
    """Resolve only one correlated same-tab or popup destination after Apply."""
    if observation is None:return None
    inventory=inventory or (lambda: asyncio.to_thread(_target_rows,observation.cdp_url))
    deadline=asyncio.get_running_loop().time()+max(0,timeout)
    while True:
        live_url=await current_url() if current_url else ''
        if (_public_destination(live_url)==observation.expected_public_url and
                (not navigation or live_url!=navigation.source_url)):
            return {'target_id':observation.current_target_id,'url':live_url,'kind':'same_tab'}
        if navigation and navigation.accepts(live_url):
            return {'target_id':observation.current_target_id,'url':live_url,'kind':'same_tab',
                    'navigation_chain':list(navigation.chain)}
        rows=await inventory()
        candidates=[]
        for raw in rows:
            row=dict(raw,targetId=raw.get('targetId') or raw.get('id'))
            target_id=row.get('targetId')
            if row.get('type')!='page' or not target_id or target_id in observation.baseline_target_ids:continue
            if observation.browser_context_id is not None and row.get('browserContextId')!=observation.browser_context_id:continue
            opener=row.get('openerId')
            if opener is not None and opener!=observation.current_target_id:continue
            exact=_public_destination(row.get('url'))==observation.expected_public_url
            if exact:candidates.append(row)
        if len(candidates)==1:
            row=candidates[0]
            result={'target_id':row['targetId'],'url':row['url'],'kind':'popup'}
            return result
        # Never choose among ambiguous matching tabs, even if one is newer.
        if len(candidates)>1:return None
        if asyncio.get_running_loop().time()>=deadline:return None
        await asyncio.sleep(poll_interval)


async def observe_popup_document(browser, observation, found, *, source_url, timeout=5.0):
    """Retain an already-correlated popup through its first document commit.

    TargetInfo can advertise the Apply URL while the new page is still blank or
    loading an HTTP redirect. That provisional URL is useful ownership evidence,
    but closing observation there loses the actual application document. Reuse
    the existing observation window; a slow page still retains its original
    handoff and ordinary executor recovery. No delay is added after readiness.
    """
    if found.get('kind') != 'popup':
        return found
    from .managed_identity import canonical_url, explicit_job_conflict
    child = None
    deadline = observation.armed_at + timeout
    if time.monotonic() >= deadline:
        return found
    try:
        # Helpers may own a page/CDP connection without borrowing its browser
        # wrapper. The armed observation already pins the validated loopback
        # endpoint and correlated child target; retain that same evidence.
        endpoint = browser.base_url if browser is not None else observation.cdp_url
        child = await CDPBrowser.connect(endpoint, target_id=found['target_id'],
                                         expected_mode=getattr(browser, 'observed_mode', None))
        page = await child.get_current_page()
        while True:
            try:
                state = await page.evaluate('({url:location.href,ready:document.readyState})',
                                            timeout=max(.1, min(1.0, deadline-time.monotonic())))
                url = state['url']
                if _public_destination(url) and state['ready'] in ('interactive', 'complete'):
                    if _public_destination(url) == _public_destination(found['url']):
                        return found
                    canonical_url(url)  # Private reset links do not become public posting identities.
                    # Both URLs were read from the same new, correlated target.
                    # Keep the original handoff if the transition introduces a
                    # conflicting job or cannot represent a public application.
                    if not any(explicit_job_conflict(base, url) for base in (source_url, found['url'])):
                        return dict(found, url=url,
                                    navigation_chain=[source_url, found['url'], url])
                    return found
            except (RuntimeError, asyncio.TimeoutError):
                pass  # Execution contexts disappear during document commit.
            if time.monotonic() >= deadline:
                return found
            await asyncio.sleep(.05)
    except (OSError, RuntimeError, ValueError, asyncio.TimeoutError):
        return found
    finally:
        if child:
            await child.close()


# ---------------------------------------------------------------------------
# Low-level WebSocket frame reader/writer (no external deps beyond stdlib).
# CDP frames are text (JSON) or binary. We implement a minimal RFC6455 client
# so we don't depend on the `websockets` package being present.
# ---------------------------------------------------------------------------
class _WS:
    """Tiny async WebSocket client (text + binary, client-side masking)."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.r = reader
        self.w = writer
        self._id = 0

    @classmethod
    async def connect(cls, ws_url: str) -> "_WS":
        import ssl
        from urllib.parse import urlparse
        u = urlparse(ws_url)
        host = u.hostname
        port = u.port or (443 if u.scheme == "wss" else 80)
        path = (u.path or "/") + (("?"+u.query) if u.query else "")
        is_tls = u.scheme == "wss"
        reader, writer = await asyncio.open_connection(host, port, ssl=ssl.create_default_context() if is_tls else None)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        writer.write(req.encode())
        await writer.drain()
        # Read headers
        status_line = await reader.readline()
        if b"101" not in status_line:
            raise RuntimeError(f"WebSocket handshake failed: {status_line!r}")
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
        return cls(reader, writer)

    async def send_text(self, text: str) -> None:
        data = text.encode("utf-8")
        self._frame(0x1, data)
        self.w.write(self._last_frame)
        await self.w.drain()

    def _frame(self, opcode: int, payload: bytes) -> None:
        b0 = 0x80 | opcode
        header = bytearray([b0])
        n = len(payload)
        mask = os.urandom(4)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += n.to_bytes(2, "big")
        else:
            header.append(0x80 | 127)
            header += n.to_bytes(8, "big")
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self._last_frame = bytes(header) + masked

    async def recv(self) -> tuple[int, bytes]:
        b1 = await self.r.readexactly(2)
        opcode = b1[0] & 0x0F
        masked = (b1[1] & 0x80) != 0
        ln = b1[1] & 0x7F
        if ln == 126:
            ln = int.from_bytes(await self.r.readexactly(2), "big")
        elif ln == 127:
            ln = int.from_bytes(await self.r.readexactly(8), "big")
        mask = await self.r.readexactly(4) if masked else b""
        payload = await self.r.readexactly(ln) if ln else b""
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload

    def close(self) -> None:
        try:
            self.w.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CDP command/response correlation
# ---------------------------------------------------------------------------
class _CDPSession:
    def __init__(self, ws: _WS):
        self.ws = ws
        self._lock = asyncio.Lock()
        self._pending: dict[int, asyncio.Future] = {}
        self._id = 0
        self._reader_task: Optional[asyncio.Task] = None
        self._listeners: dict[str, list] = {}

    def subscribe(self, method: str, callback, *, session_id=None):
        """Listen on this exact target connection; callbacks must not block."""
        key = (session_id, method)
        self._listeners.setdefault(key, []).append(callback)
        def remove():
            callbacks=self._listeners.get(key, [])
            if callback in callbacks:callbacks.remove(callback)
        return remove

    async def start(self) -> None:
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            while True:
                opcode, payload = await self.ws.recv()
                if opcode == 0x1:  # text
                    try:
                        msg = json.loads(payload.decode("utf-8"))
                    except Exception:
                        continue
                    mid = msg.get("id")
                    if mid is not None and mid in self._pending:
                        fut = self._pending.pop(mid)
                        if not fut.done():
                            if "error" in msg:
                                fut.set_exception(RuntimeError(msg["error"].get("message", "CDP error")))
                            else:
                                fut.set_result(msg.get("result", {}))
                    elif mid is None:
                        for callback in tuple(self._listeners.get((msg.get('sessionId'), msg.get('method')), [])):
                            try:callback(msg.get('params', {}))
                            except Exception:pass
                # opcode 0x2 = ping, 0x3 = close; ignore for our purposes
        except asyncio.IncompleteReadError:
            pass
        except Exception:
            pass

    async def call(self, method: str, params: Optional[dict] = None, timeout: float = 30.0, *, session_id=None) -> dict:
        self._id += 1
        mid = self._id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        async with self._lock:
            message = {"id": mid, "method": method, "params": params or {}}
            if session_id is not None:message['sessionId'] = session_id
            await self.ws.send_text(json.dumps(message))
        return await asyncio.wait_for(fut, timeout)

    def channel(self, session_id):
        return _CDPChannel(self, session_id)

    async def close(self) -> None:
        # IMPORTANT: we ATTACHED to an existing browser (the user's Brave).
        # We must NOT send "Browser.close" — that would kill the whole browser
        # and all the user's other tabs. Just tear down our CDP session.
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        self.ws.close()


# ---------------------------------------------------------------------------
# Page element handle (for query_selector_all / set_input_files)
# ---------------------------------------------------------------------------
class _CDPChannel:
    """Flattened child target, multiplexed on the already owned page connection."""
    def __init__(self, connection, session_id):
        self.connection, self.session_id = connection, session_id

    async def call(self, method, params=None, timeout=30.0):
        return await self.connection.call(method, params, timeout, session_id=self.session_id)

    def subscribe(self, method, callback):
        return self.connection.subscribe(method, callback, session_id=self.session_id)

    def channel(self, session_id):
        return self.connection.channel(session_id)


class CDPElement:
    def __init__(self, session: _CDPSession, object_id: str):
        self._session = session
        self.object_id = object_id

    async def set_input_files(self, *paths: str) -> None:
        await self._session.call("DOM.setFileInputFiles", {
            "files": [os.path.abspath(p) for p in paths],
            "objectId": self.object_id,
        })

    async def click(self) -> None:
        await self._session.call("DOM.resolveNode", {"objectId": self.object_id})
        # Dispatch a click via evaluate on the node (best-effort)
        await self._session.call("Runtime.callFunctionOn", {
            "objectId": self.object_id,
            "functionDeclaration": "function(){ this.click(); }",
        })


# ---------------------------------------------------------------------------
# Page (the thing handlers get from get_current_page)
# ---------------------------------------------------------------------------
async def _press_key(session, key: str, vk: int = 0) -> None:
    """Dispatch form keys on the attached target, including simple modifier chords."""
    if not isinstance(key,str) or not key:raise ValueError('key_required')
    parts=key.split('+'); modifiers=0
    for modifier in parts[:-1]:
        bit={'Alt':1,'Control':2,'Ctrl':2,'Meta':4,'Shift':8}.get(modifier)
        if bit is None:raise ValueError('unsupported_key_modifier')
        modifiers|=bit
    name={'Space':' ','Spacebar':' ','Esc':'Escape','Return':'Enter'}.get(parts[-1],parts[-1])
    codes={'Tab':9,'Enter':13,'Escape':27,' ':32,'ArrowLeft':37,'ArrowUp':38,
           'ArrowRight':39,'ArrowDown':40,'Home':36,'End':35,'PageUp':33,'PageDown':34,'Backspace':8,'Delete':46}
    code=vk or codes.get(name) or (ord(name.upper()) if len(name)==1 else 0)
    if not code:raise ValueError('unsupported_form_key')
    params={'key':name,'windowsVirtualKeyCode':code,'modifiers':modifiers}
    text='\r' if name=='Enter' else name if len(name)==1 and not modifiers&7 else ''
    await session.call('Input.dispatchKeyEvent',dict(params,type='keyDown',**({'text':text} if text else {})))
    await session.call('Input.dispatchKeyEvent',dict(params,type='keyUp'))


_BROWSER_INPUT_LOCKS = {}


class CDPPage:
    def __init__(self, session: _CDPSession, target_id: str, url: str):
        self._session = session
        self.target_id = target_id
        self.url = url

    @asynccontextmanager
    async def input_turn(self):
        """Briefly foreground the owned tab for trusted pointer/key input.

        Background Chromium tabs can acknowledge a mouse dispatch without running
        its activation (including window.open). The workspace host has one process
        per browser; its helper threads share this lock, not their entire call slice.
        """
        lock=getattr(self,'_input_lock',None)
        if lock is None:
            yield
            return
        while not lock.acquire(blocking=False):await asyncio.sleep(.02)
        try:
            await self._session.call('Page.bringToFront',{})
            # An occluded/remote desktop can keep even the selected tab hidden.
            # Scope Chromium's focus emulation to this input turn so real input
            # is delivered; do not change profile data or automation indicators.
            await self._session.call('Emulation.setFocusEmulationEnabled',{'enabled':True})
            yield
        finally:
            try:await self._session.call('Emulation.setFocusEmulationEnabled',{'enabled':False})
            except Exception:pass  # Navigation/closure may destroy this target.
            finally:lock.release()

    async def evaluate(self, expression: str, arg: Any = None, timeout: float = 30.0) -> Any:
        # A top-level function expression (e.g. `() => {...}` or `(args) => {...}`)
        # is NOT auto-invoked by Runtime.evaluate — returnByValue serializes the
        # function object (opaque → null). Detect and wrap so it's always called.
        # IIFEs like `(function(){...})()` do NOT match (they run as-is).
        is_callable = re.match(
            r"^\s*(?:async\s+)?(\(\s*[\w,\s]*\)\s*=>|function\b)", expression
        ) is not None
        if is_callable and arg is not None:
            expression = (
                f"((__p) => {{ const __f = {expression};"
                f" return (typeof __f === 'function') ? __f(__p) : __f; }})"
                f"({json.dumps(arg)})"
            )
        elif is_callable:
            expression = f"({expression})()"
        params: dict[str, Any] = {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        }
        if getattr(self, 'context_id', None) is not None:params['contextId'] = self.context_id
        res = await self._session.call("Runtime.evaluate", params, timeout=timeout)
        if "exceptionDetails" in res:
            det = res["exceptionDetails"]
            text = (det.get("exception") or {}).get("description") or det.get("text", "JS exception")
            raise RuntimeError(f"evaluate error: {text[:500]}")
        return res.get("result", {}).get("value")

    async def evaluate_function(self, function_declaration: str, arg: Any = None, timeout: float = 30.0) -> Any:
        # Bind to the current document's global object, not a guessed context ID.
        root_params = {"expression": "globalThis", "returnByValue": False}
        if getattr(self, 'context_id', None) is not None:root_params['contextId'] = self.context_id
        root = await self._session.call("Runtime.evaluate", root_params, timeout=timeout)
        object_id = root.get("result", {}).get("objectId")
        if not object_id:
            raise RuntimeError("evaluate error: execution_context_unavailable")
        params: dict[str, Any] = {
            "objectId": object_id,
            "functionDeclaration": function_declaration,
            "returnByValue": True,
            "awaitPromise": True,
        }
        if arg is not None:
            params["arguments"] = [{"value": arg}]
        try:
            res = await self._session.call("Runtime.callFunctionOn", params, timeout=timeout)
        finally:
            try:
                await self._session.call("Runtime.releaseObject", {"objectId": object_id}, timeout=timeout)
            except Exception:
                pass  # Navigation may already have destroyed this context.
        if "exceptionDetails" in res:
            det = res["exceptionDetails"]
            text = (det.get("exception") or {}).get("description") or det.get("text", "JS exception")
            raise RuntimeError(f"evaluate error: {text[:500]}")
        return res.get("result", {}).get("value")

    async def goto(self, url: str, timeout: float = 30.0) -> None:
        await self._session.call("Page.navigate", {"url": url}, timeout=timeout)
        self.url = url

    async def reload(self, timeout: float = 12.0) -> dict:
        """Cancel the old document and verify replacement before releasing its writer."""
        before=await self.evaluate('performance.timeOrigin')
        await self._session.call('Page.reload', {}, timeout=timeout)
        deadline=asyncio.get_running_loop().time()+timeout
        while asyncio.get_running_loop().time()<deadline:
            try:
                current=await self.evaluate('({origin:performance.timeOrigin,ready:document.readyState})')
                if current['origin']!=before and current['ready'] in ('interactive','complete'):
                    return {'reload_requested':True,'document_replaced':True}
            except Exception:
                pass  # Execution contexts disappear during document replacement.
            await asyncio.sleep(.2)
        return {'reload_requested':True,'document_replaced':False,
                'instruction':'Inspect the owned page; reload completion is unconfirmed. Use session restart if the page remains broken.'}

    async def press_key(self, key: str, vk: int = 0) -> None:
        async with self.input_turn():await _press_key(self._session,key,vk)

    async def insert_text(self, text: str) -> None:
        """Trusted text insertion into the explicitly focused current input."""
        if not isinstance(text, str):raise ValueError('text_required')
        async with self.input_turn():await self._session.call('Input.insertText', {'text': text})

    async def click_observed(self, validator: str, args: dict) -> dict:
        """Activate a validated owned-page control through browser input events."""
        async with self.input_turn():
            return await self._click_observed(validator,args)

    async def _click_observed(self, validator: str, args: dict) -> dict:
        prepared = dict(args, prepare_pointer=True)
        point = await self.evaluate_function(validator, prepared)
        if not isinstance(point, dict) or not point.get('pointer_ready'):
            return dict(point or {}, clicked=False, execution='not_executed')
        await self._session.call('Input.dispatchMouseEvent', dict(type='mouseMoved', x=point['x'], y=point['y']))
        fresh = await self.evaluate_function(validator, prepared)
        if not isinstance(fresh, dict) or not fresh.get('pointer_ready') or any(fresh[k]!=point[k] for k in ('x','y')):
            failed=fresh if isinstance(fresh,dict) else {}
            return dict(failed,clicked=False,execution='not_executed',
                reason=failed.get('reason','control_changed_before_press'))
        params = dict(x=point['x'], y=point['y'], button='left', clickCount=1)
        try:
            await self._session.call('Input.dispatchMouseEvent', dict(params, type='mousePressed', buttons=1))
            await self._session.call('Input.dispatchMouseEvent', dict(params, type='mouseReleased', buttons=0))
        except Exception:
            return {'clicked':False,'execution':'possibly_executed','reason':'pointer_dispatch_unconfirmed'}
        return {'clicked':True,'execution':'clicked','activation':'browser_pointer','outcome_verified':False,
            **{key:fresh[key] for key in ('credentials_verified_before_click','credentials_refilled_before_click') if key in fresh}}

    async def query_selector_all(self, selector: str) -> list[CDPElement]:
        res = await self._session.call("Runtime.evaluate", {
            "expression": f"document.querySelectorAll({json.dumps(selector)}).length",
            "returnByValue": True,
        })
        count = res.get("result", {}).get("value", 0) or 0
        els: list[CDPElement] = []
        doc = await self._session.call("DOM.getDocument", {"depth": 0})
        doc_id = doc.get("root", {}).get("nodeId")
        if doc_id is None:
            return els
        for _ in range(count):
            r = await self._session.call("DOM.querySelector", {
                "nodeId": doc_id,
                "selector": selector,
            })
            node_id = r.get("nodeId")
            if not node_id:
                break
            obj = await self._session.call("DOM.resolveNode", {"nodeId": node_id})
            object_id = obj.get("object", {}).get("objectId")
            if object_id:
                els.append(CDPElement(self._session, object_id))
            # querySelector returns the FIRST match; to get all we need to
            # use querySelectorAll. Fall back to that below.
            break
        # Simpler: use querySelectorAll to get all at once.
        els.clear()
        r2 = await self._session.call("DOM.querySelectorAll", {
            "nodeId": doc_id,
            "selector": selector,
        })
        for node_id in (r2.get("nodeIds") or [])[:100]:
            obj = await self._session.call("DOM.resolveNode", {"nodeId": node_id})
            object_id = obj.get("object", {}).get("objectId")
            if object_id:
                els.append(CDPElement(self._session, object_id))
        return els

    async def screenshot(self, path: str) -> str:
        res = await self._session.call("Page.captureScreenshot", {"format": "png"})
        data = base64.b64decode(res.get("data", ""))
        with open(path, "wb") as f:
            f.write(data)
        return path

    async def title(self) -> str:
        res = await self._session.call("Runtime.evaluate", {
            "expression": "document.title", "returnByValue": True,
        })
        return res.get("result", {}).get("value", "")

    @property
    def url_current(self) -> str:
        return self.url


# ---------------------------------------------------------------------------
def inspect_browser_mode(cdp_url: str) -> str:
    """Inspect CDP endpoint to check whether browser is headless or headed."""
    try:
        req = urllib.request.Request(cdp_url.rstrip("/") + "/json/version")
        with urllib.request.urlopen(req, timeout=3) as r:
            info = json.load(r)
        b_str = (info.get("Browser") or info.get("product") or "").lower()
        ua_str = (info.get("User-Agent") or "").lower()
        if "headless" in b_str or "headless" in ua_str:
            return "headless"
        if info.get("browser_mode") in ("headed", "headless"):
            return info["browser_mode"]
        if "headed" in b_str or "headful" in b_str or "headed" in ua_str:
            return "headed"
        # A normal/overridden UA is not proof of a visible window.
        return "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Session (what handlers receive as `browser_session`)
# ---------------------------------------------------------------------------
class CDPBrowser:
    """Attach to an existing browser via its CDP endpoint.

    Exposes ``get_current_page()`` so it is drop-in compatible with the
    handler contract (``browser_session.get_current_page()``).
    """

    def __init__(self, base_url: str, session: _CDPSession, page: CDPPage, target_id: str,
                 observed_mode: str = "unknown"):
        self.base_url = base_url.rstrip("/")
        self._session = session
        self._page = page
        page._input_lock = _BROWSER_INPUT_LOCKS.setdefault(self.base_url,threading.Lock())
        self.target_id = target_id
        self.observed_mode = observed_mode

    @classmethod
    async def connect(cls, cdp_url: str, page_url_substring: str = "",
                      create_new: bool = False, *, target_id: Optional[str] = None,
                      expected_mode: Optional[str] = None) -> "CDPBrowser":
        cdp_url = cdp_url.rstrip("/")
        observed_mode = inspect_browser_mode(cdp_url)
        if expected_mode == "headed" and observed_mode == "headless":
            raise ValueError("headless browser cannot satisfy headed request")
        if expected_mode == "headless" and observed_mode == "headed":
            raise ValueError("browser_mode_mismatch: headed browser cannot satisfy headless request")
        if target_id is not None:
            import re
            if not isinstance(target_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", target_id):
                raise ValueError("invalid_target_id")
            if create_new or page_url_substring:
                raise ValueError("conflicting_target_options")
            endpoint = urllib.parse.urlparse(cdp_url)
            if (endpoint.scheme != "http" or endpoint.hostname not in ("127.0.0.1", "localhost", "::1")
                    or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
                    or endpoint.path):
                raise ValueError("owned_target_requires_loopback_cdp")
        with urllib.request.urlopen(cdp_url + "/json/list", timeout=5) as r:
            targets = json.load(r)
        pages = [t for t in targets if t.get("type") == "page"]

        chosen = None
        if target_id is not None:
            chosen = next((t for t in pages if t.get("id") == target_id), None)
            if chosen is None:
                raise ValueError("owned_target_not_found")
        elif page_url_substring:
            for t in pages:
                if page_url_substring in (t.get("url") or ""):
                    chosen = t
                    break
        if chosen is None:
            if create_new:
                with urllib.request.urlopen(cdp_url + "/json/new?about:blank", timeout=5) as r:
                    chosen = json.load(r)
            elif pages:
                # Prefer an about:blank, else the first page.
                chosen = next((t for t in pages if "about:blank" in (t.get("url") or "")), pages[0])
            else:
                raise RuntimeError("No CDP page targets found.")
        ws_url = chosen.get("webSocketDebuggerUrl")
        if not ws_url:
            raise RuntimeError("CDP target has no webSocketDebuggerUrl")
        if target_id is not None:
            debugger = urllib.parse.urlparse(ws_url)
            if (debugger.scheme not in ("ws", "wss")
                    or debugger.hostname not in ("127.0.0.1", "localhost", "::1")
                    or debugger.port != (endpoint.port or 80)
                    or debugger.path != "/devtools/page/" + target_id
                    or debugger.username or debugger.password or debugger.query or debugger.fragment):
                raise ValueError("unsafe_owned_debugger_url")
        ws = await _WS.connect(ws_url)
        session = _CDPSession(ws)
        await session.start()
        await session.call("Page.enable")
        await session.call("DOM.enable")
        await session.call("Runtime.enable")
        page = CDPPage(session, chosen.get("id", ""), chosen.get("url", ""))
        return cls(cdp_url, session, page, chosen.get("id", ""), observed_mode=observed_mode)

    async def get_current_page(self) -> CDPPage:
        return self._page

    async def start(self) -> None:
        """No-op for compatibility (we already connected)."""
        return None

    # ---- CDP Input domain (real user-level input; React-safe) ----
    async def type_text(self, text: str) -> None:
        """Insert text at the focused element via CDP Input.insertText."""
        await self._page.insert_text(text)

    async def press_key(self, key: str, vk: int = 0) -> None:
        """Send a keydown+keyup via CDP Input.dispatchKeyEvent."""
        await self._page.press_key(key,vk)

    async def screenshot(self, path: str, full_page: bool = False) -> str:
        """Capture the current page to a PNG file via CDP Page.captureScreenshot."""
        res = await self._session.call("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": full_page,
        }, timeout=30)
        import base64
        data = base64.b64decode(res.get("data", ""))
        with open(path, "wb") as f:
            f.write(data)
        return path

    async def click_element(self, selector: str) -> bool:
        """Click the first element matching selector (JS click — fine for buttons)."""
        try:
            await self._session.call("Runtime.evaluate", {
                "expression": f"((s)=>{{const e=document.querySelector(s); if(!e) return false; e.scrollIntoView({{block:'center'}}); e.click(); return true;}})({json.dumps(selector)})",
                "returnByValue": True,
            })
            return True
        except Exception:
            return False

    async def fill_by_id(self, input_id: str, value: str, commit: str = "enter") -> bool:
        """Focus #input_id, type value via CDP, commit with Enter or Tab.
        Works on React-controlled text inputs AND comboboxes."""
        page = await self.get_current_page()
        await page.evaluate(f"document.getElementById({json.dumps(input_id)}).focus()")
        await asyncio.sleep(0.15)
        if value:
            await self.type_text(value)
            await asyncio.sleep(0.2)
        if commit == "enter":
            await self.press_key("Enter", 13)
        elif commit == "tab":
            await self.press_key("Tab", 9)
        await asyncio.sleep(0.3)
        # verify
        try:
            got = await page.evaluate(f"(document.getElementById({json.dumps(input_id)})||{{}}).value")
            return (got or "") == value
        except Exception:
            return True

    async def stop(self) -> None:
        await self._session.close()

    async def close(self) -> None:
        await self._session.close()
