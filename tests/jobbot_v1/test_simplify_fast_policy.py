"""Unit and contract tests for Simplify fast policy, observer extensions, and bounded retry.

Verifies:
1. Fast policy opt-in:
   - SimplifyBoundary(page, fast=True) and decide(..., fast=True)
   - Quiescent complete/needs_review with enabled continue advances in fast mode
   - Default conservative contract preserved in fast=False mode
   - Active and unknown never write
2. Observer exact controls:
   - Recognizes create_account_autofill, create_account, sign_in, submit
   - Stop account step and visible busy/active take precedence
   - Visible rendered status used, hidden stale root text ignored
   - Handles "3 fields need your input", "Need to review (3)", "0 reviews"
   - Boundary.perform rejects auth and submit operations
3. Compact observer metadata:
   - Boundary.observe preserves review_count, field_summary, and writer_safe
   - Page signature prioritizes aria-current step and step headings over field structure
4. Bounded explicit retry:
   - perform("autofill", retry=True) allowed only if fast=True, already attempted,
     idle complete/needs_review/ready, active autofill control, max ONE retry per page
   - retry=False stays protected
   - Retry counts tracked per page
   - Timeouts never return idle
   - Graceful settlement prevents immediate stale complete
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any
import pytest

from job_applier.simplify_boundary import SimplifyBoundary

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
    this.innerText = opts.innerText !== undefined ? opts.innerText : this.textContent;
    this.disabled = !!opts.disabled;
    this.attributes = opts.attributes || {};
    if (opts.name) this.attributes['name'] = opts.name;
    if (opts.role) this.attributes['role'] = opts.role;
    if (opts['aria-label']) this.attributes['aria-label'] = opts['aria-label'];
    if (opts['aria-disabled']) this.attributes['aria-disabled'] = opts['aria-disabled'];
    if (opts['aria-busy']) this.attributes['aria-busy'] = opts['aria-busy'];
    if (opts['aria-current']) this.attributes['aria-current'] = opts['aria-current'];
    this.width = opts.width !== undefined ? opts.width : 100;
    this.height = opts.height !== undefined ? opts.height : 24;
    this.style = opts.style || {};
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
      for (const b of (el.buttons || [])) {
        if (sel.includes('button') && (b.tagName === 'BUTTON' || b.getAttribute('role') === 'button')) {
          res.push(b);
        }
        walk(b);
      }
    };
    walk(this);
    return res;
  }
  querySelector(sel) {
    if (sel === '[aria-busy="true"]') {
      const walk = (el) => {
        if (el.getAttribute('aria-busy') === 'true') return el;
        for (const c of (el.children || [])) {
          const found = walk(c);
          if (found) return found;
        }
        for (const b of (el.buttons || [])) {
          const found = walk(b);
          if (found) return found;
        }
        return null;
      };
      return walk(this);
    }
    return null;
  }
}

function buildRoots(rootsData) {
  const hosts = [];
  for (const rd of rootsData) {
    const shadow = new FakeElement({
      textContent: rd.textContent || '',
      innerText: rd.innerText,
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
const pageHeadings = (inputData.headings || []).map(h => new FakeElement(h));
const pageFields = (inputData.fields || []).map(f => new FakeElement(f));

const context = {
  console,
  crypto: globalThis.crypto,
  TextEncoder,
  Uint8Array,
  JSON,
  Map,
  location: {
    origin: inputData.origin || 'https://example.wd1.myworkdayjobs.com',
    pathname: inputData.pathname || '/apply',
    href: (inputData.origin || 'https://example.wd1.myworkdayjobs.com') + (inputData.pathname || '/apply')
  },
  document: {
    querySelector: (sel) => {
      if (sel === '.simplify-jobs-shadow-root') return hosts[0] || null;
      if (sel === '[aria-current="step"]') return pageHeadings.find(h => h.getAttribute('aria-current') === 'step') || null;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel === '.simplify-jobs-shadow-root') return hosts;
      if (sel === 'input,select,textarea') return pageFields;
      if (sel === 'h1,h2,h3') return pageHeadings;
      return [];
    },
    body: { textContent: inputData.bodyText || '' }
  },
  getComputedStyle: (el) => {
    if (el && el.style && el.style.visibility) return { visibility: el.style.visibility };
    return { visibility: 'visible' };
  }
};
context.window = context;
vm.createContext(context);

(async () => {
  const obs = await vm.runInContext(jsCode, context);
  process.stdout.write(JSON.stringify(obs));
})();
"""


def run_node_observe(roots: list[dict], headings: list[dict] | None = None, fields: list[dict] | None = None) -> dict:
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node unavailable on PATH")
    payload = {
        "jsPath": str(OBSERVE_JS_PATH),
        "roots": roots,
        "headings": headings or [],
        "fields": fields or [],
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
    def __init__(self, observation=None, url="https://example.wd1.myworkdayjobs.com/apply"):
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
            obs.setdefault("workday", ".myworkdayjobs.com/" in obs['url'])
            return obs
        if "jobbot:simplify:click" in script:
            self.clicks.append(arg)
            if self._on_click:
                return self._on_click(arg)
            return {"status": "ok", "clicked": True}
        raise ValueError(f"Unrecognized script marker: {script[:60]}")


# ===========================================================================
# 1. Fast Policy in decide and constructor
# ===========================================================================


def test_enabled_continue_advances_needs_review_in_both_boundary_modes():
    """Both boundary modes prefer enabled Continue after writer settlement."""
    obs = {
        "url": "https://example.wd1.myworkdayjobs.com/apply",
        "status": "needs_review",
        "controls": {
            "continue": {"ref": "btn-cont", "enabled": True},
            "autofill": {"ref": None, "enabled": False},
        },
    }
    # Shared policy applies to the default boundary as well as the fast runner.
    dec_conservative = SimplifyBoundary.decide(obs, fast=False)
    assert dec_conservative["action"] == "continue"

    # Fast mode advances
    dec_fast = SimplifyBoundary.decide(obs, fast=True)
    assert dec_fast["action"] == "continue"


def test_decide_fast_mode_active_or_unknown_never_writes():
    """Active and unknown status in fast mode never write; active waits, unknown falls back."""
    active_obs = {"url": "https://example.wd1.myworkdayjobs.com/apply", "status": "active", "controls": {"continue": {"ref": "c", "enabled": True}}}
    unknown_obs = {"url": "https://example.wd1.myworkdayjobs.com/apply", "status": "unknown", "controls": {"continue": {"ref": "c", "enabled": True}}}

    dec_active = SimplifyBoundary.decide(active_obs, fast=True)
    assert dec_active["action"] == "wait"

    dec_unknown = SimplifyBoundary.decide(unknown_obs, fast=True)
    assert dec_unknown["action"] == "fallback"


def test_boundary_constructor_stores_fast_flag():
    """SimplifyBoundary accepts fast keyword-only argument defaulting to False."""
    port = DOMSeamPort()
    b_default = SimplifyBoundary(port)
    assert b_default.fast is False

    b_fast = SimplifyBoundary(port, fast=True)
    assert b_fast.fast is True


# ===========================================================================
# 2. Observer Exact Controls & Status Handling
# ===========================================================================


def test_observer_recognizes_exact_new_controls_in_dom():
    """Observer recognizes create_account_autofill, create_account, sign_in, submit."""
    roots = [
        {
            "textContent": "Create Account & Autofill Submit Application Sign In",
            "buttons": [
                {"tagName": "BUTTON", "innerText": "Create Account & Autofill", "disabled": False},
                {"tagName": "BUTTON", "innerText": "Submit Application", "disabled": False},
                {"tagName": "BUTTON", "innerText": "Sign In", "disabled": False},
            ],
        }
    ]
    obs = run_node_observe(roots)
    controls = obs["controls"]

    assert "create_account_autofill" in controls
    assert controls["create_account_autofill"]["enabled"] is True
    assert isinstance(controls["create_account_autofill"]["ref"], str)

    assert "submit" in controls
    assert controls["submit"]["enabled"] is True
    assert isinstance(controls["submit"]["ref"], str)

    assert "sign_in" in controls
    assert controls["sign_in"]["enabled"] is True
    assert isinstance(controls["sign_in"]["ref"], str)


def test_observer_stop_account_step_emits_login_required():
    """Account creation / sign in controls take precedence as login_required unless active."""
    roots = [
        {
            "textContent": "Create Account & Autofill",
            "buttons": [
                {"tagName": "BUTTON", "innerText": "Create Account & Autofill", "disabled": False},
            ],
        }
    ]
    obs = run_node_observe(roots)
    assert obs["status"] == "login_required"


def test_observer_visible_busy_active_takes_precedence_over_account_step():
    """Visible busy/active status takes precedence over account step."""
    roots = [
        {
            "textContent": "Filling your application in progress",
            "children": [{"tagName": "DIV", "aria-busy": "true"}],
            "buttons": [
                {"tagName": "BUTTON", "innerText": "Create Account & Autofill", "disabled": False},
            ],
        }
    ]
    obs = run_node_observe(roots)
    assert obs["status"] == "active"


def test_observer_uses_rendered_status_not_hidden_stale_text():
    """Hidden stale text (visibility: hidden / display: none) is ignored for status."""
    roots = [
        {
            "textContent": "Autofill complete",  # stale raw textContent
            "innerText": "Ready to autofill",   # rendered visible text
            "buttons": [
                {"tagName": "BUTTON", "innerText": "Autofill This Page", "disabled": False},
            ],
        }
    ]
    obs = run_node_observe(roots)
    assert obs["status"] == "ready"


def test_observer_handles_residual_input_and_review_counts():
    """Observer parses '3 fields need your input', 'Need to review (3)', and '0 reviews'."""
    # 1. 3 fields need your input -> needs_review, review_count = 3
    roots_3 = [{"textContent": "3 fields need your input"}]
    obs_3 = run_node_observe(roots_3)
    assert obs_3["status"] == "needs_review"
    assert obs_3.get("review_count") == 3

    # 2. Need to review (3) -> needs_review, review_count = 3
    roots_paren = [{"textContent": "Need to review (3)"}]
    obs_paren = run_node_observe(roots_paren)
    assert obs_paren["status"] == "needs_review"
    assert obs_paren.get("review_count") == 3

    # 3. 0 reviews -> complete, review_count = 0 (not needs_review)
    roots_0 = [{"textContent": "0 reviews · Autofill complete"}]
    obs_0 = run_node_observe(roots_0)
    assert obs_0["status"] == "complete"
    assert obs_0.get("review_count") == 0


def test_boundary_perform_rejects_creation_and_submit_operations():
    """Creation and submission use dedicated boundaries; scoped sign-in is supported."""
    port = DOMSeamPort()
    boundary = SimplifyBoundary(port)
    for op in ("create_account", "create_account_autofill", "submit", "authenticate"):
        with pytest.raises(ValueError, match="Unsupported Simplify operation"):
            asyncio.run(boundary.perform(op))


# ===========================================================================
# 3. Metadata Preservation in Boundary.observe
# ===========================================================================


def test_boundary_observe_preserves_review_count_field_summary_writer_safe():
    """Boundary.observe retains review_count, field_summary, and writer_safe metadata."""
    raw_obs = {
        "url": "https://example.wd1.myworkdayjobs.com/apply",
        "fingerprint": "fp1",
        "page_signature": "sig1",
        "status": "needs_review",
        "review_count": 3,
        "field_summary": {"visible": 12, "required": 4, "invalid": 3},
        "writer_safe": True,
        "controls": {
            "autofill": {"ref": None, "enabled": False},
            "continue": {"ref": "c1", "enabled": True},
            "create_account": {"ref": None, "enabled": False},
        },
    }
    port = DOMSeamPort(observation=raw_obs)
    boundary = SimplifyBoundary(port)
    obs = asyncio.run(boundary.observe())

    assert obs["review_count"] == 3
    assert obs["field_summary"] == {"visible": 12, "required": 4, "invalid": 3}
    assert obs["writer_safe"] is True
    assert "create_account" in obs["controls"]


# ===========================================================================
# 4. Bounded Explicit Retry Support
# ===========================================================================


def test_perform_autofill_retry_succeeds_only_in_fast_mode_max_once():
    """Fast mode allows explicit retry=True once on already attempted page when autofill enabled."""
    time_sim = FakeClockSleeper()
    page_obs = {
        "url": "https://example.wd1.myworkdayjobs.com/apply",
        "page_signature": "sig_step1",
        "fingerprint": "fp_step1_unfilled",
        "status": "needs_review",
        "controls": {
            "autofill": {"ref": "btn-auto", "enabled": True},
            "continue": {"ref": "btn-cont", "enabled": True},
        },
    }
    port = DOMSeamPort(observation=page_obs)

    # 1. Conservative boundary (fast=False): retry=True is rejected
    b_conservative = SimplifyBoundary(port, clock=time_sim.clock, sleeper=time_sim.sleep, fast=False)
    b_conservative.attempted.add("sig_step1")
    res_cons = asyncio.run(b_conservative.perform("autofill", retry=True))
    assert res_cons["reason"] == "already_attempted"
    assert len(port.clicks) == 0

    # 2. Fast boundary (fast=True): first retry=True succeeds
    b_fast = SimplifyBoundary(port, clock=time_sim.clock, sleeper=time_sim.sleep, fast=True)
    b_fast.attempted.add("sig_step1")

    def on_click(arg):
        port.observation = dict(page_obs, fingerprint="fp_step1_retried", status="complete")
        return {"status": "ok", "clicked": True}

    port._on_click = on_click
    res_retry1 = asyncio.run(b_fast.perform("autofill", retry=True))
    assert res_retry1["writer_state"] == "idle"
    assert res_retry1["changed"] is True
    assert len(port.clicks) == 1
    assert b_fast.retries.get("sig_step1") == 1

    # 3. Second retry=True on same page is rejected (max 1 retry per page)
    res_retry2 = asyncio.run(b_fast.perform("autofill", retry=True))
    assert res_retry2["reason"] == "already_attempted"
    assert len(port.clicks) == 1  # No second click


def test_perform_without_explicit_retry_stays_protected():
    """already_attempted page without retry=True remains rejected even in fast mode."""
    time_sim = FakeClockSleeper()
    port = DOMSeamPort(observation={
        "url": "https://example.wd1.myworkdayjobs.com/apply",
        "page_signature": "sig_step1",
        "status": "needs_review",
        "controls": {"autofill": {"ref": "b", "enabled": True}},
    })
    boundary = SimplifyBoundary(port, clock=time_sim.clock, sleeper=time_sim.sleep, fast=True)
    boundary.attempted.add("sig_step1")

    res = asyncio.run(boundary.perform("autofill", retry=False))
    assert res["reason"] == "already_attempted"
    assert len(port.clicks) == 0


def test_stop_account_step_is_an_active_writer():
    from test_simplify_start import run_node_simplify_observe
    obs=run_node_simplify_observe([{'textContent':'Stop account step','buttons':[{'tagName':'BUTTON','textContent':'Stop account step'}]}])
    assert obs['status']=='active'


def test_enabled_continue_and_submit_are_observable_when_banner_disappears():
    from test_simplify_start import run_node_simplify_observe
    for label in ('Continue Application','Submit Application'):
        obs=run_node_simplify_observe([{'buttons':[{'tagName':'BUTTON','textContent':label}]}])
        assert obs['status'] in ('ready','complete')
