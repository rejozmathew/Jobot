"""Bounded regression tracer tests for Simplify Start Application root-cause fix.

Validates:
1. Node observer recognizes Start Application + Autofill tab as ready with controls.start enabled,
   and excludes standalone Autofill navigation tab from autofill action.
2. Active, disabled, and ambiguous guards fail closed.
3. SimplifyBoundary.decide selects 'start' when start is ready and autofill is absent.
4. SimplifyBoundary.perform('start') verifies page transition (URL/page_signature), not value-only changes.
5. SimplifyBoundary.perform('start') fails closed on disabled and stale controls.
6. Worker autofill operation chooses start when no autofill action but start ready,
   executes under scoped action/writer fencing, returns explicit simplify_start and instruction rediscover,
   and does NOT emit field_verified.
"""
import asyncio
from contextlib import nullcontext
import json
from pathlib import Path
import shutil
import subprocess
import pytest

from job_applier.simplify_boundary import SimplifyBoundary, OBSERVE, CLICK

OBSERVE_JS_PATH = Path(__file__).parents[2] / "job_applier" / "browser_helpers" / "simplify_observe.js"

NODE_RUNNER_SCRIPT = """
const fs = require('fs');
const vm = require('vm');

const inputData = JSON.parse(fs.readFileSync(0, 'utf8'));
const jsCode = fs.readFileSync(inputData.jsPath, 'utf8');

class FakeElement {
  constructor(opts) {
    this.tagName = (opts.tagName || 'DIV').toUpperCase();
    this.type = opts.type || 'text';
    this.name = opts.name || '';
    this.value = opts.value || '';
    this.checked = !!opts.checked;
    this.required = !!opts.required;
    this.invalid = !!opts.invalid;
    this.textContent = opts.textContent || '';
    this.innerText = opts.innerText || this.textContent;
    this.disabled = !!opts.disabled;
    this.attributes = opts.attributes || {};
    if (opts.name) this.attributes['name'] = opts.name;
    if (opts.role) this.attributes['role'] = opts.role;
    if (opts['aria-label']) this.attributes['aria-label'] = opts['aria-label'];
    if (opts['aria-disabled']) this.attributes['aria-disabled'] = opts['aria-disabled'];
    if (opts['aria-busy']) this.attributes['aria-busy'] = opts['aria-busy'];
    this.width = opts.width !== undefined ? opts.width : 100;
    this.height = opts.height !== undefined ? opts.height : 24;
    this.validity = { valid: !this.invalid };
    this.children = (opts.children || []).map(c => new FakeElement(c));
    this.buttons = (opts.buttons || []).map(b => new FakeElement(b));
    this.classList = {
      classes: new Set(opts.classes || []),
      contains: (c) => this.classList.classes.has(c)
    };
    this.isConnected = true;
    this.shadowRoot = opts.shadowRoot || null;
  }
  getAttribute(attr) {
    if (attr === 'aria-invalid') return this.invalid ? 'true' : 'false';
    if (attr === 'aria-disabled') return this.disabled ? 'true' : (this.attributes['aria-disabled'] || 'false');
    if (attr === 'aria-busy') return this.attributes['aria-busy'] || null;
    return this.attributes[attr] !== undefined ? String(this.attributes[attr]) : null;
  }
  setAttribute(attr, val) { this.attributes[attr] = String(val); }
  getBoundingClientRect() { return { width: this.width, height: this.height }; }
  querySelectorAll(sel) {
    const res = [];
    const walk = (el) => {
      for (const c of (el.children || [])) {
        if (sel.includes('button') && (c.tagName === 'BUTTON' || c.getAttribute('role') === 'button')) {
          res.push(c);
        }
        walk(c);
      }
    };
    for (const b of (this.buttons || [])) {
      if (sel.includes('button') && (b.tagName === 'BUTTON' || b.getAttribute('role') === 'button')) {
        res.push(b);
      }
      walk(b);
    }
    walk(this);
    return res;
  }
  querySelector(sel) {
    if (sel === '[aria-busy="true"]') {
      const all = [];
      const walk = (el) => {
        if (el.getAttribute('aria-busy') === 'true') all.push(el);
        for (const c of (el.children || [])) walk(c);
        for (const b of (el.buttons || [])) walk(b);
      };
      walk(this);
      return all.length ? all[0] : null;
    }
    return null;
  }
}

function buildRoots(rootsData) {
  const hosts = [];
  for (const rd of rootsData) {
    const shadow = new FakeElement({
      textContent: rd.textContent || '',
      buttons: rd.buttons || [],
      children: rd.children || []
    });
    const host = new FakeElement({
      tagName: 'DIV',
      classes: ['simplify-jobs-shadow-root'],
      width: 0,
      height: 0
    });
    host.shadowRoot = shadow;
    shadow.host = host;
    hosts.push(host);
  }
  return hosts;
}

const hosts = buildRoots(inputData.roots || []);

const context = {
  console,
  crypto: globalThis.crypto,
  TextEncoder,
  Uint8Array,
  JSON,
  Map,
  location: {
    origin: inputData.origin || 'https://huron.wd1.myworkdayjobs.com',
    pathname: inputData.pathname || '/huroncareers/job/Chicago/JR-0016154',
    href: (inputData.origin || 'https://huron.wd1.myworkdayjobs.com') + (inputData.pathname || '/huroncareers/job/Chicago/JR-0016154')
  },
  document: {
    querySelector: (sel) => {
      if (sel === '.simplify-jobs-shadow-root') return hosts[0] || null;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel === '.simplify-jobs-shadow-root') return hosts;
      if (sel === 'input,select,textarea') return [];
      if (sel === 'h1,h2,h3') return [];
      return [];
    },
    body: { textContent: inputData.bodyText || '' }
  },
  getComputedStyle: () => ({ visibility: 'visible' })
};
context.window = context;
vm.createContext(context);

(async () => {
  const obs = await vm.runInContext(jsCode, context);
  process.stdout.write(JSON.stringify(obs));
})();
"""


def run_node_simplify_observe(roots: list[dict], origin: str = "https://huron.wd1.myworkdayjobs.com", pathname: str = "/huroncareers/job/Chicago/JR-0016154") -> dict:
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node genuinely unavailable on system PATH")
    payload = {
        "jsPath": str(OBSERVE_JS_PATH),
        "roots": roots,
        "origin": origin,
        "pathname": pathname,
    }
    proc = subprocess.run(
        [node_bin, "-e", NODE_RUNNER_SCRIPT],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


class FakeClockSleeper:
    def __init__(self, start: float = 100.0):
        self.now = start
        self.sleeps = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float):
        self.sleeps.append(seconds)
        self.now += seconds


class DOMSeamPort:
    def __init__(self, observation=None, url="https://huron.wd1.myworkdayjobs.com/apply"):
        self.url = url
        self.observation = observation or {}
        self.clicks = []
        self.evaluations = []
        self._on_click = None

    async def evaluate(self, script: str, arg=None):
        self.evaluations.append((script, arg))
        if "jobbot:simplify:observe" in script:
            obs = dict(self.observation)
            obs.setdefault("url", self.url)
            return obs
        if "jobbot:simplify:click" in script:
            self.clicks.append(arg)
            if self._on_click:
                return self._on_click(arg)
            return {"status": "ok", "clicked": True}
        raise ValueError(f"Unrecognized script marker: {script[:60]}")


# ---------------------------------------------------------------------------
# Test 1: Node observer recognizes Start Application + Autofill tab as ready
# ---------------------------------------------------------------------------


def test_node_observe_huron_official_pattern_start_application():
    """Huron official pattern: standalone Autofill tab in header, Start Application in body.

    Must emit ready status with controls.start enabled with ref.
    Must NOT alias standalone Autofill tab to autofill action (controls.autofill ref=None, enabled=False).
    """
    roots = [
        # Root 0: decoy header items (Dismiss, etc.)
        {
            "textContent": "Improve My Match Dismiss",
            "buttons": [
                {"tagName": "BUTTON", "innerText": "Dismiss", "aria-label": "Dismiss", "disabled": False},
                {"tagName": "BUTTON", "innerText": "Improve My Match", "disabled": False},
            ],
        },
        # Root 1: Sticky header with tabs + body with Start Application
        {
            "textContent": "Autofill Resume Score Profile Start Application",
            "buttons": [
                # Navigation tabs:
                {"tagName": "BUTTON", "innerText": "Autofill", "disabled": False},
                {"tagName": "BUTTON", "innerText": "Resume Score", "disabled": False},
                {"tagName": "BUTTON", "innerText": "Profile", "disabled": False},
                # Action button:
                {"tagName": "BUTTON", "innerText": "Start Application", "aria-label": "Start application", "disabled": False},
            ],
        },
    ]
    obs = run_node_simplify_observe(roots)
    assert obs["status"] == "ready"
    assert "start" in obs["controls"]
    assert obs["controls"]["start"]["enabled"] is True
    assert isinstance(obs["controls"]["start"]["ref"], str) and len(obs["controls"]["start"]["ref"]) > 0

    # Standalone Autofill tab must NOT be aliased to autofill action
    assert obs["controls"]["autofill"]["enabled"] is False
    assert obs["controls"]["autofill"]["ref"] is None


# ---------------------------------------------------------------------------
# Test 2: Standalone Autofill tab only is not actionable
# ---------------------------------------------------------------------------


def test_node_observe_standalone_autofill_tab_only_is_not_actionable():
    """Only standalone Autofill tab present (no Start Application, no Autofill This Page).

    Must emit unknown status, controls.autofill disabled, controls.start disabled.
    """
    roots = [
        {
            "textContent": "Autofill Resume Score Profile",
            "buttons": [
                {"tagName": "BUTTON", "innerText": "Autofill", "disabled": False},
                {"tagName": "BUTTON", "innerText": "Resume Score", "disabled": False},
                {"tagName": "BUTTON", "innerText": "Profile", "disabled": False},
            ],
        },
    ]
    obs = run_node_simplify_observe(roots)
    assert obs["status"] == "unknown"
    assert obs["controls"].get("autofill", {}).get("enabled") is False
    assert obs["controls"].get("start", {}).get("enabled") is False


# ---------------------------------------------------------------------------
# Test 3: Guards fail closed: active, disabled, ambiguous
# ---------------------------------------------------------------------------


def test_node_observe_start_application_guards():
    """Start Application button subject to fail-closed guards."""
    # 3.1 Active guard: busy marker beats ready
    roots_active = [
        {
            "textContent": "Filling your application in progress",
            "children": [{"tagName": "DIV", "aria-busy": "true"}],
            "buttons": [
                {"tagName": "BUTTON", "innerText": "Start Application", "aria-label": "Start application", "disabled": False},
            ],
        }
    ]
    obs_active = run_node_simplify_observe(roots_active)
    assert obs_active["status"] == "active"

    # 3.2 Disabled guard: Start Application disabled -> unknown status
    roots_disabled = [
        {
            "textContent": "Start Application",
            "buttons": [
                {"tagName": "BUTTON", "innerText": "Start Application", "aria-label": "Start application", "disabled": True},
            ],
        }
    ]
    obs_disabled = run_node_simplify_observe(roots_disabled)
    assert obs_disabled["status"] == "unknown"
    assert obs_disabled["controls"].get("start", {}).get("enabled") is False

    # 3.3 Ambiguous guard: multiple enabled Start Application buttons -> fail closed
    roots_ambiguous = [
        {
            "textContent": "Start Application Start Application",
            "buttons": [
                {"tagName": "BUTTON", "innerText": "Start Application", "aria-label": "Start application", "disabled": False},
                {"tagName": "BUTTON", "innerText": "Start Application", "aria-label": "Start application", "disabled": False},
            ],
        }
    ]
    obs_ambiguous = run_node_simplify_observe(roots_ambiguous)
    assert obs_ambiguous["status"] == "unknown"
    assert obs_ambiguous["controls"].get("start", {}).get("enabled") is False


# ---------------------------------------------------------------------------
# Test 4: SimplifyBoundary.decide chooses start when ready and autofill absent
# ---------------------------------------------------------------------------


def test_simplify_boundary_decide_start():
    """decide prefers start when status is ready, start is enabled, and autofill is absent."""
    obs = {
        "url": "https://huron.wd1.myworkdayjobs.com/apply",
        "fingerprint": "fp1",
        "panel": True,
        "status": "ready",
        "controls": {
            "start": {"ref": "btn-start-1", "enabled": True},
            "autofill": {"ref": None, "enabled": False},
            "continue": {"ref": None, "enabled": False},
        },
        "source": "observed_dom",
    }
    decision = SimplifyBoundary.decide(obs, already_attempted=False)
    assert decision["action"] == "start"
    assert "start" in decision.get("reason", "").lower()

    # When already attempted on same page, fail closed / fallback to avoid loop
    decision_attempted = SimplifyBoundary.decide(obs, already_attempted=True)
    assert decision_attempted["action"] != "start"
    assert decision_attempted["action"] == "fallback"


# ---------------------------------------------------------------------------
# Test 5: SimplifyBoundary.perform('start') verifies page transition
# ---------------------------------------------------------------------------


def test_simplify_boundary_perform_start_verifies_page_transition():
    """perform('start') clicks start control and verifies page transition (URL/page_signature)."""
    initial_obs = {
        "url": "https://huron.wd1.myworkdayjobs.com/job/JR-0016154",
        "fingerprint": "fp_job_page",
        "page_ref": "ref_page_1",
        "page_signature": "sig_job_page",
        "panel": True,
        "status": "ready",
        "controls": {
            "start": {"ref": "btn-start-1", "enabled": True},
            "autofill": {"ref": None, "enabled": False},
            "continue": {"ref": None, "enabled": False},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(observation=initial_obs, url=initial_obs["url"])

    def on_click(arg):
        assert arg["ref"] == "btn-start-1"
        assert arg["operation"] == "start"
        # Navigation to step 1 form
        port.observation = {
            "url": "https://huron.wd1.myworkdayjobs.com/job/JR-0016154/apply/step1",
            "fingerprint": "fp_step1_empty",
            "page_ref": "ref_page_2",
            "page_signature": "sig_step1",
            "panel": True,
            "status": "ready",
            "controls": {
                "start": {"ref": None, "enabled": False},
                "autofill": {"ref": "btn-step1-auto", "enabled": True},
                "continue": {"ref": None, "enabled": False},
            },
            "source": "observed_dom",
        }
        return {"status": "ok", "clicked": True}

    port._on_click = on_click
    time_sim = FakeClockSleeper()
    boundary = SimplifyBoundary(port, budget_seconds=30, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    result = asyncio.run(boundary.perform("start"))
    assert result["changed"] is True
    assert result["writer_state"] == "idle"
    assert result["reason"] == "page_changed_rediscover_controls"
    assert len(port.clicks) == 1
    assert port.clicks[0]["operation"] == "start"


# ---------------------------------------------------------------------------
# Test 6: perform('start') rejects value-only changes without page transition
# ---------------------------------------------------------------------------


def test_boundary_perform_start_rejects_value_only_change():
    """perform('start') must NOT treat field-value changes alone as a successful start transition."""
    initial_obs = {
        "url": "https://huron.wd1.myworkdayjobs.com/job/JR-0016154",
        "fingerprint": "fp_val1",
        "page_ref": "ref_page_1",
        "page_signature": "sig_job_page",
        "panel": True,
        "status": "ready",
        "controls": {
            "start": {"ref": "btn-start-1", "enabled": True},
            "autofill": {"ref": None, "enabled": False},
            "continue": {"ref": None, "enabled": False},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(observation=initial_obs, url=initial_obs["url"])

    def on_click(arg):
        # Value changes, but URL, page_ref, and page_signature do NOT change
        port.observation = dict(initial_obs, fingerprint="fp_val2_modified")
        return {"status": "ok", "clicked": True}

    port._on_click = on_click
    time_sim = FakeClockSleeper()
    boundary = SimplifyBoundary(port, budget_seconds=10, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    result = asyncio.run(boundary.perform("start"))
    assert result["changed"] is False
    assert result["writer_state"] == "unknown"
    assert "timeout" in result.get("reason", "").lower() or "budget" in result.get("reason", "").lower()


# ---------------------------------------------------------------------------
# Test 7: perform('start') fails closed on disabled and stale controls
# ---------------------------------------------------------------------------


def test_boundary_perform_start_disabled_and_stale_guards():
    """Disabled control is not clicked; stale click response returns unknown writer."""
    # Disabled control:
    disabled_obs = {
        "url": "https://huron.wd1.myworkdayjobs.com/apply",
        "fingerprint": "fp1",
        "panel": True,
        "status": "ready",
        "controls": {
            "start": {"ref": "btn-disabled", "enabled": False},
            "autofill": {"ref": None, "enabled": False},
            "continue": {"ref": None, "enabled": False},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(observation=disabled_obs)
    boundary = SimplifyBoundary(port)
    res_disabled = asyncio.run(boundary.perform("start"))
    assert len(port.clicks) == 0
    assert res_disabled["changed"] is False
    assert res_disabled["writer_state"] == "idle"

    # Stale control:
    enabled_obs = {
        "url": "https://huron.wd1.myworkdayjobs.com/apply",
        "fingerprint": "fp1",
        "panel": True,
        "status": "ready",
        "controls": {
            "start": {"ref": "btn-stale", "enabled": True},
            "autofill": {"ref": None, "enabled": False},
            "continue": {"ref": None, "enabled": False},
        },
        "source": "observed_dom",
    }
    port_stale = DOMSeamPort(observation=enabled_obs)
    port_stale._on_click = lambda arg: {"status": "stale", "reason": "control_changed", "clicked": False}
    boundary_stale = SimplifyBoundary(port_stale)
    res_stale = asyncio.run(boundary_stale.perform("start"))
    assert res_stale["writer_state"] == "unknown"
    assert res_stale["reason"] == "stale_or_unconfirmed_control"


# ---------------------------------------------------------------------------
# Test 8: Worker autofill operation chooses start when no autofill but start ready
# ---------------------------------------------------------------------------


def test_worker_autofill_chooses_start_when_no_autofill_but_start_ready(monkeypatch):
    from job_applier import browser_controls
    from unittest.mock import AsyncMock
    monkeypatch.setattr(browser_controls, 'observe', AsyncMock(return_value={
        'status': 'missing', 'controls': {}, 'native_authentication_required': False}))
    """Worker operate({'operation': 'autofill'}) selects start when only start is ready.

    Performs under existing scoped action/writer fencing, returns explicit simplify_start
    and instruction rediscover, and does NOT emit field_verified.
    """
    from job_applier.managed_hermes_worker import ApplicationTool

    async def _run():
        events_emitted = []
        calls_made = []

        class DummyClient:
            def call(self, op, **kw):
                calls_made.append((op, kw))
                return {"control": "running", "quiescent": True}

        class DummyAdapter:
            def __init__(self, client):
                self.client = client

        class DummyController:
            def __init__(self, client):
                self.adapters = {"sid-1": DummyAdapter(client)}
            def handle(self, req, session_id=None):
                return json.dumps({})

        client = DummyClient()
        ctrl = DummyController(client)
        cfg = {"worker_id": "w1", "cdp_url": "http://127.0.0.1:9222"}
        app = ApplicationTool(ctrl, "sid-1", "run-1", cfg)
        app.context = {"attempt_id": 1, "worker_id": "w1", "fence": 1}
        app.package = {"job": {"url": "https://huron.wd1.myworkdayjobs.com/job/JR-0016154"}}

        class MockPage:
            def __init__(self):
                self.current_url = "https://huron.wd1.myworkdayjobs.com/job/JR-0016154"
                self.step = 0
            async def evaluate(self, script, args=None):
                if script == "location.href":
                    return self.current_url
                if "jobbot:simplify:observe" in script:
                    if self.step == 0:
                        return {
                            "url": "https://huron.wd1.myworkdayjobs.com/job/JR-0016154",
                            "fingerprint": "fp_job_step0",
                            "page_ref": "page_1",
                            "page_signature": "sig_job_landing",
                            "panel": True,
                            "status": "ready",
                            "controls": {
                                "start": {"ref": "start-ref-1", "enabled": True},
                                "autofill": {"ref": None, "enabled": False},
                                "continue": {"ref": None, "enabled": False},
                            },
                            "source": "observed_dom",
                        }
                    else:
                        return {
                            "url": "https://huron.wd1.myworkdayjobs.com/job/JR-0016154/apply/step1",
                            "fingerprint": "fp_job_step1",
                            "page_ref": "page_2",
                            "page_signature": "sig_step1_form",
                            "panel": True,
                            "status": "ready",
                            "controls": {
                                "start": {"ref": None, "enabled": False},
                                "autofill": {"ref": "auto-ref-2", "enabled": True},
                                "continue": {"ref": None, "enabled": False},
                            },
                            "source": "observed_dom",
                        }
                if "jobbot:simplify:click" in script:
                    assert args["operation"] == "start"
                    self.step = 1
                    self.current_url = "https://huron.wd1.myworkdayjobs.com/job/JR-0016154/apply/step1"
                    return {"status": "ok", "clicked": True}
                return {"url": self.current_url, "items": [], "errors": [], "text": ""}

        page = MockPage()
        class DummyBrowser:
            async def get_current_page(self): return page
            async def close(self): pass

        monkeypatch.setattr(app, "connect", lambda: asyncio.sleep(0, result=DummyBrowser()))
        monkeypatch.setattr(app, "event", lambda kind, payload: events_emitted.append((kind, payload)))

        result = await app.operate({"operation": "autofill"})

        # 1. Returns explicit simplify_start and instruction rediscover
        assert "simplify_start" in result
        assert result["simplify_start"]["changed"] is True
        assert result["simplify_start"]["writer_state"] == "idle"
        assert "rediscover" in result.get("instruction", "").lower()

        # 2. Does NOT emit field_verified for start application
        field_verified_events = [e for e in events_emitted if e[0] == "field_verified"]
        assert len(field_verified_events) == 0, f"Unexpected field_verified events: {field_verified_events}"

        # 3. Action fencing was applied
        action_starts = [c for c in calls_made if c[0] == "action_start"]
        action_ends = [c for c in calls_made if c[0] == "action_end"]
        assert len(action_starts) >= 1
        assert len(action_ends) >= 1
        writer_states = [c[1]["state"] for c in calls_made if c[0] == "writer_state"]
        assert "active" in writer_states
        assert "idle" in writer_states

    asyncio.run(_run())
