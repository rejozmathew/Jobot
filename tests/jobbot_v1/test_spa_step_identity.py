"""Targeted regressions for S2-R8 SPA step identity and transition contracts.

Review finding covered:
- S2-R8: Revised page signature conflates distinct same-URL SPA steps.
  Under an unchanged h1 ("Application"), transitioning from an Experience h2/form
  to a Questions h2/form leaves url, page_ref, and page_signature identical when
  using only publicUrl and first h1. Consequently Continue times out waiting for
  navigation, and subsequent Autofill is suppressed by the shared attempted-page key.
  Preserves distinguishable step identity without treating field-value or validation
  changes alone as navigation.

Rules:
- TEST-ONLY: No production edits, no commits, no real browser, no network.
- Reuses actual-JS Node vm synthetic DOM seam pattern from test_stage2_boundary_review.py.
- Does not mock returned fingerprints or page signatures.
- <=3 compact tests.
- Keeps raw values out of observation assertions.
- Captures RED on unpatched implementation; Primary retains implementation.
"""

import asyncio
import json
from pathlib import Path
import shutil
import subprocess
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
    this.innerText = opts.innerText || this.textContent;
    this.disabled = !!opts.disabled;
    this.attributes = opts.attributes || {};
    if (opts.name) this.attributes['name'] = opts.name;
    if (opts.role) this.attributes['role'] = opts.role;
    if (opts['aria-label']) this.attributes['aria-label'] = opts['aria-label'];
    if (opts['aria-current']) this.attributes['aria-current'] = opts['aria-current'];
    this.width = opts.width !== undefined ? opts.width : 100;
    this.height = opts.height !== undefined ? opts.height : 24;
    this.validity = { valid: !this.invalid };
    this.buttons = (opts.buttons || []).map(b => new FakeElement(b));
  }
  getAttribute(attr) {
    if (attr === 'aria-invalid') return this.invalid ? 'true' : 'false';
    if (attr === 'aria-disabled') return this.disabled ? 'true' : 'false';
    return this.attributes[attr] !== undefined ? String(this.attributes[attr]) : null;
  }
  setAttribute(attr, val) { this.attributes[attr] = String(val); }
  getBoundingClientRect() { return { width: this.width, height: this.height }; }
  querySelectorAll(sel) {
    if (sel.includes('button')) return this.buttons || [];
    return [];
  }
  querySelector(sel) { return null; }
}

function buildDomState(state) {
  const headings = (state.headings || []).map(h => new FakeElement(h));
  const fields = (state.fields || []).map(f => new FakeElement(f));
  let host = null;
  if (state.panel) {
    const buttons = (state.panel.buttons || []).map(b => new FakeElement(b));
    const root = new FakeElement({ textContent: state.panel.text || '', buttons });
    host = new FakeElement({ tagName: 'DIV' });
    host.shadowRoot = root;
  }
  return { headings, fields, host, bodyText: state.bodyText || '' };
}

let activeDom = buildDomState(inputData.states ? inputData.states[0] : inputData.state);

const context = {
  console,
  crypto: globalThis.crypto,
  TextEncoder,
  Uint8Array,
  JSON,
  Map,
  location: {
    origin: inputData.origin || 'https://careers.example.test',
    pathname: inputData.pathname || '/apply',
    href: (inputData.origin || 'https://careers.example.test') + (inputData.pathname || '/apply')
  },
  document: {
    querySelector: (sel) => {
      if (sel === '.simplify-jobs-shadow-root') return activeDom.host;
      if (sel === 'h1') return activeDom.headings.find(h => h.tagName === 'H1') || null;
      if (sel === '[aria-current="step"]') return activeDom.headings.find(h => h.getAttribute('aria-current') === 'step') || null;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel === 'input,select,textarea') return activeDom.fields;
      if (sel === 'h1,h2,h3') return activeDom.headings;
      return [];
    },
    body: { get textContent() { return activeDom.bodyText; } }
  },
  getComputedStyle: () => ({ visibility: 'visible' })
};
context.window = context;

if (inputData.saved_scope) {
  context.window.__jobbotSimplifyScope = {
    url: context.location.href,
    id: inputData.saved_scope.id,
    controls: new Map(),
    fieldValues: new Map(inputData.saved_scope.fieldValues || []),
    valueEpoch: inputData.saved_scope.valueEpoch || 0
  };
}
vm.createContext(context);

(async () => {
  if (inputData.states) {
    const observations = [];
    for (const st of inputData.states) {
      activeDom = buildDomState(st);
      const obs = await vm.runInContext(jsCode, context);
      observations.push(obs);
    }
    const finalScope = context.window.__jobbotSimplifyScope;
    process.stdout.write(JSON.stringify({
      observations,
      scope: {
        id: finalScope.id,
        valueEpoch: finalScope.valueEpoch,
        fieldValues: Array.from(finalScope.fieldValues.entries())
      }
    }));
  } else {
    const obs = await vm.runInContext(jsCode, context);
    const finalScope = context.window.__jobbotSimplifyScope;
    process.stdout.write(JSON.stringify({
      obs,
      scope: {
        id: finalScope.id,
        valueEpoch: finalScope.valueEpoch,
        fieldValues: Array.from(finalScope.fieldValues.entries())
      }
    }));
  }
})();
"""


def run_node_sequence(states: list[dict], origin: str = "https://careers.example.test", pathname: str = "/apply") -> list[dict]:
    """Execute actual simplify_observe.js across a sequence of states in a shared window/context."""
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node genuinely unavailable on system PATH")
    assert OBSERVE_JS_PATH.is_file(), f"Missing simplify_observe.js at {OBSERVE_JS_PATH}"

    payload = {
        "jsPath": str(OBSERVE_JS_PATH),
        "states": states,
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
    result = json.loads(proc.stdout)
    return result["observations"]


def run_node_observe(state: dict, saved_scope: dict | None = None) -> tuple[dict, dict]:
    """Execute actual simplify_observe.js via Node vm + synthetic DOM seam without mocking."""
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node genuinely unavailable on system PATH")
    assert OBSERVE_JS_PATH.is_file(), f"Missing simplify_observe.js at {OBSERVE_JS_PATH}"

    payload = {
        "jsPath": str(OBSERVE_JS_PATH),
        "state": state,
        "saved_scope": saved_scope,
    }
    proc = subprocess.run(
        [node_bin, "-e", NODE_RUNNER_SCRIPT],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(proc.stdout)
    return result["obs"], result["scope"]


class FakeClockSleeper:
    """Deterministic virtual clock and sleeper avoiding real delays."""

    def __init__(self, start: float = 1000.0):
        self.now = start
        self.sleeps = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float):
        self.sleeps.append(seconds)
        self.now += seconds


class NodeVMBoundaryPort:
    """Evaluate port driving actual simplify_observe.js against dynamic synthetic DOM steps."""

    def __init__(self, url: str = "https://careers.example.test/apply"):
        self.url = url
        self.current_step = 1
        self.scope = None
        self.autofilled_steps = set()
        self.evaluations = []
        self.clicks = []

    def get_dom_state(self) -> dict:
        if self.current_step == 1:
            is_filled = 1 in self.autofilled_steps
            return {
                "origin": "https://careers.example.test",
                "pathname": "/apply",
                "headings": [
                    {"tagName": "H1", "textContent": "Application"},
                    {"tagName": "H2", "textContent": "Experience"},
                ],
                "fields": [
                    {
                        "name": "work_experience_company",
                        "type": "text",
                        "value": "Acme Corp" if is_filled else "",
                        "required": True,
                    },
                    {
                        "name": "work_experience_title",
                        "type": "text",
                        "value": "Software Engineer" if is_filled else "",
                        "required": True,
                    },
                ],
                "panel": {
                    "text": "Autofill complete" if is_filled else "Ready to autofill",
                    "buttons": [
                        {"textContent": "Autofill This Page", "disabled": is_filled},
                        {"textContent": "Continue Application", "disabled": not is_filled},
                    ],
                },
            }
        else:
            is_filled = 2 in self.autofilled_steps
            return {
                "origin": "https://careers.example.test",
                "pathname": "/apply",
                "headings": [
                    {"tagName": "H1", "textContent": "Application"},
                    {"tagName": "H2", "textContent": "Questions"},
                ],
                "fields": [
                    {
                        "name": "question_sponsorship",
                        "type": "text",
                        "value": "No" if is_filled else "",
                        "required": True,
                    },
                    {
                        "name": "question_notice_period",
                        "type": "text",
                        "value": "2 weeks" if is_filled else "",
                        "required": False,
                    },
                ],
                "panel": {
                    "text": "Autofill complete" if is_filled else "Ready to autofill",
                    "buttons": [
                        {"textContent": "Autofill This Page", "disabled": is_filled},
                        {"textContent": "Continue Application", "disabled": not is_filled},
                    ],
                },
            }

    async def evaluate(self, script: str, arg=None):
        self.evaluations.append((script, arg))
        if "jobbot:simplify:click" in script:
            self.clicks.append(arg)
            op = (arg or {}).get("operation")
            if op == "continue":
                self.current_step = 2
            elif op == "autofill":
                self.autofilled_steps.add(self.current_step)
            return {"status": "clicked", "clicked": True}
        if "jobbot:simplify:observe" in script:
            state = self.get_dom_state()
            obs, self.scope = run_node_observe(state, saved_scope=self.scope)
            return obs
        raise ValueError(f"Unrecognized script marker in port: {script[:60]}")


# ===========================================================================
# 1. SPA Step Transition Changes page_signature
# ===========================================================================


def test_spa_step_transition_changes_page_signature():
    """(1) same location/h1 Application, Experience h2+fields transitions to Questions h2+fields => page_signature changes.

    Under an unchanged top-level h1 'Application' and unchanged URL, transitioning from
    an Experience h2 and experience fields to Questions h2 and question fields must yield
    a different page_signature so that downstream boundary logic recognizes navigation.
    """
    raw_sentinels = ["Acme Sentinel Corp", "Senior Lead Engineer", "No Sponsorship Needed", "Two Weeks Notice"]

    step1_state = {
        "headings": [
            {"tagName": "H1", "textContent": "Application"},
            {"tagName": "H2", "textContent": "Experience"},
        ],
        "fields": [
            {"name": "work_experience_company", "type": "text", "value": raw_sentinels[0], "required": True},
            {"name": "work_experience_title", "type": "text", "value": raw_sentinels[1], "required": True},
        ],
    }
    step2_state = {
        "headings": [
            {"tagName": "H1", "textContent": "Application"},
            {"tagName": "H2", "textContent": "Questions"},
        ],
        "fields": [
            {"name": "question_sponsorship", "type": "text", "value": raw_sentinels[2], "required": True},
            {"name": "question_notice_period", "type": "text", "value": raw_sentinels[3], "required": False},
        ],
    }

    obs1, obs2 = run_node_sequence([step1_state, step2_state])

    # Window scope identity preserved across same-page SPA evaluation
    assert obs1["page_ref"] == obs2["page_ref"], (
        f"SPA window scope must be preserved across step transition on same document: {obs1['page_ref']}"
    )

    # Raw values must never leak into returned observation structures
    for sentinel in raw_sentinels:
        assert sentinel not in json.dumps(obs1), f"Raw sentinel '{sentinel}' leaked in obs1"
        assert sentinel not in json.dumps(obs2), f"Raw sentinel '{sentinel}' leaked in obs2"

    # Regression S2-R8: distinct SPA steps must produce distinct page_signature
    assert obs1["page_signature"] != obs2["page_signature"], (
        f"S2-R8: Page signature must change across distinct SPA steps (Experience -> Questions) "
        f"under unchanged h1, but got identical page_signature: '{obs1['page_signature']}'"
    )


# ===========================================================================
# 2. In-Page Validation and Value Changes Preserve page_signature
# ===========================================================================


def test_in_page_validation_and_value_changes_preserve_page_signature():
    """(2) same h1/h2/field identities with only values, invalidity/required flag, or role=alert heading change => fingerprint may change, page_signature must not.

    Preserves distinguishable step identity without conflating in-page mutation (user typing,
    validation errors, alert banners) with actual step navigation.
    """
    raw_sentinels = ["Acme Baseline Corp", "Beta Mutated Corp", "Software Engineer", "Staff Engineer"]

    base_state = {
        "headings": [
            {"tagName": "H1", "textContent": "Application"},
            {"tagName": "H2", "textContent": "Experience"},
        ],
        "fields": [
            {"name": "work_experience_company", "type": "text", "value": raw_sentinels[0], "required": False, "invalid": False},
            {"name": "work_experience_title", "type": "text", "value": raw_sentinels[2], "required": False, "invalid": False},
        ],
    }

    # Mutation A: Field values changed
    val_state = {
        "headings": [
            {"tagName": "H1", "textContent": "Application"},
            {"tagName": "H2", "textContent": "Experience"},
        ],
        "fields": [
            {"name": "work_experience_company", "type": "text", "value": raw_sentinels[1], "required": False, "invalid": False},
            {"name": "work_experience_title", "type": "text", "value": raw_sentinels[3], "required": False, "invalid": False},
        ],
    }

    # Mutation B: Invalidity and required flags changed
    inv_state = {
        "headings": [
            {"tagName": "H1", "textContent": "Application"},
            {"tagName": "H2", "textContent": "Experience"},
        ],
        "fields": [
            {"name": "work_experience_company", "type": "text", "value": raw_sentinels[1], "required": True, "invalid": True},
            {"name": "work_experience_title", "type": "text", "value": raw_sentinels[3], "required": True, "invalid": True},
        ],
    }

    # Mutation C: Clearly tagged role=alert validation heading added
    alert_state = {
        "headings": [
            {"tagName": "H1", "textContent": "Application"},
            {"tagName": "H2", "textContent": "Experience"},
            {"tagName": "H2", "textContent": "Please fix the 2 highlighted errors below", "role": "alert"},
        ],
        "fields": [
            {"name": "work_experience_company", "type": "text", "value": raw_sentinels[1], "required": True, "invalid": True},
            {"name": "work_experience_title", "type": "text", "value": raw_sentinels[3], "required": True, "invalid": True},
        ],
    }

    obs_base, obs_val, obs_inv, obs_alert = run_node_sequence([base_state, val_state, inv_state, alert_state])

    # Privacy invariant: raw field values never leak into observations
    for obs in (obs_base, obs_val, obs_inv, obs_alert):
        for sentinel in raw_sentinels:
            assert sentinel not in json.dumps(obs), f"Raw sentinel '{sentinel}' leaked in observation"

    # Invariant: page_signature must NOT change across in-page value/validation mutations
    assert obs_base["page_signature"] == obs_val["page_signature"], (
        f"Value change alone must not change page_signature: {obs_base['page_signature']} vs {obs_val['page_signature']}"
    )
    assert obs_base["page_signature"] == obs_inv["page_signature"], (
        f"Invalidity/required change alone must not change page_signature: {obs_base['page_signature']} vs {obs_inv['page_signature']}"
    )
    assert obs_base["page_signature"] == obs_alert["page_signature"], (
        f"role=alert validation heading change alone must not change page_signature: "
        f"{obs_base['page_signature']} vs {obs_alert['page_signature']}"
    )

    # Fingerprint may (and should) change to reflect in-page form and validation state mutations
    assert obs_base["fingerprint"] != obs_val["fingerprint"], (
        "Form fingerprint must observe value change"
    )
    assert obs_val["fingerprint"] != obs_inv["fingerprint"], (
        "Form fingerprint must observe required/invalidity flag change"
    )
    assert obs_inv["fingerprint"] != obs_alert["fingerprint"], (
        "Form fingerprint must observe alert heading change"
    )


# ===========================================================================
# 3. Boundary Same-URL New page_signature after Continue Allows Autofill Once
# ===========================================================================


def test_boundary_same_url_step_transition_allows_autofill_once():
    """(3) boundary same-URL new page signature after Continue returns recognized step and allows Autofill once on new step.

    Simulates the full boundary lifecycle on an SPA form:
    - Step 1 (Experience) is completed and Continue is executed.
    - Continue waits for and recognizes the new step via distinguishable page_signature.
    - On the new step (Questions), Autofill is permitted exactly once and not suppressed
      by the prior step's attempted-page key.
    - Subsequent Autofill attempt on the new step is correctly rejected as already_attempted.
    """
    port = NodeVMBoundaryPort()
    time_sim = FakeClockSleeper()
    boundary = SimplifyBoundary(port, budget_seconds=0.5, poll_seconds=0.05, clock=time_sim.clock, sleeper=time_sim.sleep)

    # Pre-condition: Step 1 (Experience) has been autofilled; page key is recorded in boundary.attempted
    obs_step1 = asyncio.run(boundary.observe())
    boundary.attempted.add(obs_step1.get("page_signature") or obs_step1["url"])
    port.autofilled_steps.add(1)

    # Perform Continue on Step 1 to transition to Step 2
    res_continue = asyncio.run(boundary.perform("continue"))

    # Must recognize navigation to the new step without timing out to 'unknown'
    assert res_continue["writer_state"] == "idle", (
        f"S2-R8: Continue on same-URL SPA transition must release writer as idle on recognized step, "
        f"but got writer_state='{res_continue['writer_state']}' (reason='{res_continue.get('reason')}')"
    )
    assert res_continue["status"] == "ready", (
        f"S2-R8: Continue must recognize new step as 'ready', but got '{res_continue['status']}'"
    )
    assert res_continue["reason"] == "page_changed_rediscover_controls", (
        f"S2-R8: Expected 'page_changed_rediscover_controls', got '{res_continue.get('reason')}'"
    )
    assert res_continue["changed"] is True

    # Step 2 page_signature must differ from Step 1
    obs_step2 = res_continue["observation"]
    assert obs_step2["page_signature"] != obs_step1["page_signature"], (
        f"S2-R8: Step 2 page_signature must differ from Step 1, but both got '{obs_step1['page_signature']}'"
    )

    # Autofill on the new step must be allowed (not suppressed by Step 1's attempted key)
    res_autofill_1 = asyncio.run(boundary.perform("autofill"))
    assert res_autofill_1["writer_state"] == "idle", (
        f"Autofill on new step must be permitted and release writer as idle, got '{res_autofill_1['writer_state']}'"
    )
    assert res_autofill_1["status"] in ("complete", "needs_review")
    assert res_autofill_1["reason"] in ("observed_change", "no_observable_progress")

    # A second Autofill on the same new step must now be rejected as already attempted
    res_autofill_2 = asyncio.run(boundary.perform("autofill"))
    assert res_autofill_2["reason"] == "already_attempted", (
        f"Second autofill on same step must be rejected as already_attempted, got '{res_autofill_2.get('reason')}'"
    )

    # Privacy invariant: raw field values never leak into observations
    for sentinel in ("Acme Corp", "Software Engineer", "No", "2 weeks"):
        for obs in (obs_step1, obs_step2, res_autofill_1["observation"]):
            assert sentinel not in json.dumps(obs), f"Raw sentinel '{sentinel}' leaked in observation"
