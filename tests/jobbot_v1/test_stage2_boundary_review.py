"""Targeted regressions for Stage 2 boundary review findings (R1, R6, R7).

Review findings covered:
- S2-R1 (R1): Unknown/unreadable initial panel must never return writer idle / native_takeover_authorized,
  regardless of whether controls are missing, disabled, or enabled. Unknown is not quiescence.
  Missing/unsupported before any invocation may still allow explicitly safe fallback per contract.
- S2-R6 (R6): Field fingerprint must observe actual value and selected-option changes on the page.
  Executes actual simplify_observe.js via Node vm + tiny synthetic DOM without new deps, preserving
  window state across calls. Asserts valid nonempty text change changes fingerprint, selected-option
  change changes fingerprint, no-change does not, and raw sentinels are never returned.
- S2-R7 (R7): Continue on unchanged still-complete panel must wait for actual page transition.
  Same-page fingerprint/value/validation change must NOT report verified navigation or release writer.
  Delayed new URL/page_ref or explicit page_marker/page_signature change may complete;
  timeout leaves unknown and no second click.

Rules:
- TEST-ONLY: No production edits, no commits, no real browser, no network, no models.
- Uses actual simplify_boundary.py and simplify_observe.js.
- Tests represent regression contracts against unpatched code (expected RED on review findings).
"""

import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import pytest

from job_applier.simplify_boundary import SimplifyBoundary

OBSERVE_JS_PATH = Path(__file__).parents[2] / "job_applier" / "browser_helpers" / "simplify_observe.js"


# ===========================================================================
# Test Utilities and Fixtures
# ===========================================================================


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


class DOMSeamPort:
    """Port simulating the browser page evaluate interface for SimplifyBoundary."""

    def __init__(self, initial_obs=None, url="https://careers.example.test/apply"):
        self.url = url
        self.observation = initial_obs or {}
        self.clicks = []
        self.observe_calls = []

    async def evaluate(self, script: str, arg=None):
        if "jobbot:simplify:click" in script:
            self.clicks.append(arg)
            return {"status": "clicked", "clicked": True}
        if "jobbot:simplify:observe" in script:
            self.observe_calls.append(arg)
            obs = dict(self.observation)
            obs.setdefault("url", self.url)
            return obs
        raise ValueError(f"Unrecognized script in port: {script[:60]}")


class SequentialObservationPort:
    """Port returning a deterministic sequence of observations across successive observe calls."""

    def __init__(self, sequence, url="https://careers.example.test/apply"):
        self.url = url
        self.sequence = list(sequence)
        self.clicks = []
        self.observe_calls = []
        self._index = 0

    async def evaluate(self, script: str, arg=None):
        if "jobbot:simplify:click" in script:
            self.clicks.append(arg)
            return {"status": "clicked", "clicked": True}
        if "jobbot:simplify:observe" in script:
            self.observe_calls.append(arg)
            if self._index < len(self.sequence):
                obs = dict(self.sequence[self._index])
                self._index += 1
            else:
                obs = dict(self.sequence[-1])
            obs.setdefault("url", self.url)
            return obs
        raise ValueError(f"Unrecognized script in port: {script[:60]}")


# ===========================================================================
# R1: Unknown initial panel must never return writer idle / native_takeover
# ===========================================================================


@pytest.mark.parametrize("operation", ["autofill", "continue"])
@pytest.mark.parametrize(
    "control_state,control_payload",
    [
        ("missing", {"ref": None, "enabled": False}),
        ("disabled", {"ref": "btn-disabled-1", "enabled": False}),
        ("enabled", {"ref": "btn-enabled-1", "enabled": True}),
    ],
    ids=["ctrl_missing", "ctrl_disabled", "ctrl_enabled"],
)
def test_r1_unknown_initial_panel_never_authorizes_native_takeover(operation, control_state, control_payload):
    """R1: Unknown/unreadable initial panel must never return writer idle or native_takeover_authorized=True.

    Regardless of whether controls are missing, disabled, or enabled:
    Unknown is not quiescence; absence of a usable control does not mean extension writes stopped.
    """
    initial_obs = {
        "url": "https://careers.example.test/apply",
        "status": "unknown",
        "panel": True,
        "page_signature": "sig_unknown_page",
        "fingerprint": "fp_unknown_page",
        "controls": {
            operation: control_payload,
            ("continue" if operation == "autofill" else "autofill"): {"ref": None, "enabled": False},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(initial_obs=initial_obs)
    time_sim = FakeClockSleeper()
    boundary = SimplifyBoundary(port, budget_seconds=45, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    result = asyncio.run(boundary.perform(operation))

    assert result["writer_state"] == "unknown", (
        f"R1: For status='unknown', writer_state must be 'unknown', but got '{result['writer_state']}' "
        f"(operation={operation}, control_state={control_state})"
    )
    assert result.get("native_takeover_authorized") is False, (
        f"R1: For status='unknown', native_takeover_authorized must be False, but got "
        f"'{result.get('native_takeover_authorized')}' (operation={operation}, control_state={control_state})"
    )


@pytest.mark.parametrize("status", ["missing", "unsupported"])
@pytest.mark.parametrize("operation", ["autofill", "continue"])
def test_r1_missing_and_unsupported_permit_idle_fallback(status, operation):
    """R1 contrast: Missing or unsupported before invocation may allow safe idle fallback per contract."""
    obs = {
        "url": "https://careers.example.test/apply",
        "status": status,
        "panel": status != "missing",
        "page_signature": f"sig_{status}",
        "fingerprint": f"fp_{status}",
        "controls": {
            "autofill": {"ref": None, "enabled": False},
            "continue": {"ref": None, "enabled": False},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(initial_obs=obs)
    time_sim = FakeClockSleeper()
    boundary = SimplifyBoundary(port, budget_seconds=45, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    result = asyncio.run(boundary.perform(operation))
    assert result["writer_state"] == "idle", (
        f"Known {status} before invocation is permitted to fall back with writer_state='idle'"
    )
    assert result.get("native_takeover_authorized") is True


# ===========================================================================
# R7: Continue with unchanged still-complete panel must wait for page transition
# ===========================================================================


def test_r7_continue_unchanged_still_complete_waits_for_actual_page_transition():
    """R7: Continue on unchanged still-complete panel must wait for actual page transition.

    Must not immediately return idle on poll 1 with 'no_observable_progress' when the panel
    is still complete; it must poll until the actual page transition (e.g. step 2) completes.
    """
    seq = [
        # Call 0: Initial observation before click
        {
            "url": "https://careers.example.test/apply/step1",
            "page_signature": "sig_step1",
            "fingerprint": "fp_step1",
            "status": "complete",
            "controls": {
                "autofill": {"ref": None, "enabled": False},
                "continue": {"ref": "btn-step1-cont", "enabled": True},
            },
        },
        # Call 1: Poll 1 after click - still complete, unchanged page
        {
            "url": "https://careers.example.test/apply/step1",
            "page_signature": "sig_step1",
            "fingerprint": "fp_step1",
            "status": "complete",
            "controls": {
                "autofill": {"ref": None, "enabled": False},
                "continue": {"ref": "btn-step1-cont", "enabled": True},
            },
        },
        # Call 2: Poll 2 after click - still complete, unchanged page
        {
            "url": "https://careers.example.test/apply/step1",
            "page_signature": "sig_step1",
            "fingerprint": "fp_step1",
            "status": "complete",
            "controls": {
                "autofill": {"ref": None, "enabled": False},
                "continue": {"ref": "btn-step1-cont", "enabled": True},
            },
        },
        # Call 3: Delayed page transition arrives! New URL, signature, and ready status
        {
            "url": "https://careers.example.test/apply/step2",
            "page_signature": "sig_step2",
            "fingerprint": "fp_step2",
            "status": "ready",
            "controls": {
                "autofill": {"ref": "btn-step2-auto", "enabled": True},
                "continue": {"ref": None, "enabled": False},
            },
        },
    ]
    port = SequentialObservationPort(seq)
    time_sim = FakeClockSleeper()
    boundary = SimplifyBoundary(port, budget_seconds=10, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    result = asyncio.run(boundary.perform("continue"))

    assert len(port.clicks) == 1
    assert port.clicks[0]["ref"] == "btn-step1-cont"

    # Must have waited through unchanged polls and captured the genuine page transition
    assert result["status"] == "ready", (
        f"R7: Expected boundary to wait for page transition to 'ready', but got '{result['status']}'"
    )
    assert result["observation"].get("page_signature") == "sig_step2", (
        f"R7: Expected page transition to sig_step2, but remained on: {result['observation'].get('page_signature')}"
    )
    assert result["observation"].get("url") == "https://careers.example.test/apply/step2"
    assert result["changed"] is True
    assert result["writer_state"] == "idle"
    assert len(port.observe_calls) >= 4, (
        f"R7: Expected at least 4 observe calls waiting for transition, got {len(port.observe_calls)}"
    )


def test_r7_continue_same_page_fingerprint_change_must_not_report_verified_navigation():
    """R7: Same-page fingerprint/value/validation change must NOT report verified navigation or release writer.

    When page_signature / URL is unchanged, an in-page validation error or residual field change
    must not emit page_changed_rediscover_controls or release writer as verified navigation.
    """
    seq = [
        # Call 0: Initial observation before click
        {
            "url": "https://careers.example.test/apply/step1",
            "page_signature": "sig_step1",
            "fingerprint": "fp_step1_valid",
            "status": "complete",
            "controls": {
                "autofill": {"ref": None, "enabled": False},
                "continue": {"ref": "btn-step1-cont", "enabled": True},
            },
        },
        # Call 1: Same page (identical URL and page_signature), but validation error changed fingerprint
        {
            "url": "https://careers.example.test/apply/step1",
            "page_signature": "sig_step1",
            "fingerprint": "fp_step1_validation_error",
            "status": "needs_review",
            "controls": {
                "autofill": {"ref": None, "enabled": False},
                "continue": {"ref": "btn-step1-cont", "enabled": False},
            },
        },
    ]
    port = SequentialObservationPort(seq)
    time_sim = FakeClockSleeper()
    boundary = SimplifyBoundary(port, budget_seconds=5, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    result = asyncio.run(boundary.perform("continue"))

    # A same-page validation/fingerprint delta must NOT report verified navigation or release writer as idle
    assert result.get("reason") != "page_changed_rediscover_controls", (
        "R7: Same-page fingerprint change must not report 'page_changed_rediscover_controls'"
    )
    assert not (result["writer_state"] == "idle" and result.get("reason") == "observed_change"), (
        "R7: Same-page fingerprint change must not report observed_change with idle writer"
    )
    assert result["writer_state"] != "idle", (
        f"R7: Same-page fingerprint/validation change must not release writer as idle; got {result['writer_state']}"
    )


def test_r7_continue_unchanged_still_complete_timeout_leaves_unknown_and_no_second_click():
    """R7: Continue with panel permanently unchanged still-complete times out to unknown without a second click.

    Timeout must leave writer_state='unknown', native_takeover_authorized=False, and exactly 1 click.
    """
    unchanged_complete = {
        "url": "https://careers.example.test/apply/step1",
        "page_signature": "sig_step1",
        "fingerprint": "fp_step1",
        "status": "complete",
        "controls": {
            "autofill": {"ref": None, "enabled": False},
            "continue": {"ref": "btn-step1-cont", "enabled": True},
        },
    }
    # Provide a steady stream of the same unchanged observation
    seq = [unchanged_complete] * 30
    port = SequentialObservationPort(seq)
    time_sim = FakeClockSleeper()
    boundary = SimplifyBoundary(port, budget_seconds=2.0, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    result = asyncio.run(boundary.perform("continue"))

    assert len(port.clicks) == 1, (
        f"R7: Exactly 1 click on continue must occur during wait/timeout, got {len(port.clicks)}"
    )
    assert result["writer_state"] == "unknown", (
        f"R7: Timeout waiting for page transition must yield writer_state='unknown', got '{result['writer_state']}'"
    )
    assert result.get("native_takeover_authorized") is not True, (
        "R7: Timeout waiting for page transition must not authorize native takeover"
    )


# ===========================================================================
# R6: Node vm synthetic DOM execution of actual simplify_observe.js
# ===========================================================================

SENTINEL_TEXT_VAL_ALPHA = "SYNTHETIC_SENTINEL_ALPHA_JOHN_DOE"
SENTINEL_TEXT_VAL_BETA = "SYNTHETIC_SENTINEL_BETA_JANE_ROE"
SENTINEL_OPT_VAL_A = "SYNTHETIC_SENTINEL_OPT_CITIZEN"
SENTINEL_OPT_VAL_B = "SYNTHETIC_SENTINEL_OPT_VISA_SPONSOR"


@pytest.fixture(scope="module")
def node_observations():
    """Execute actual simplify_observe.js using Node vm + tiny synthetic DOM across 4 states."""
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node genuinely unavailable on system PATH")

    assert OBSERVE_JS_PATH.is_file(), f"Missing simplify_observe.js at {OBSERVE_JS_PATH}"

    runner_script = f"""
const fs = require('fs');
const vm = require('vm');

const jsCode = fs.readFileSync({json.dumps(str(OBSERVE_JS_PATH))}, 'utf8');

class FakeElement {{
  constructor(opts) {{
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
    this.attributes = opts.attributes || {{}};
    if (opts.name) this.attributes['name'] = opts.name;
    this.width = opts.width !== undefined ? opts.width : 100;
    this.height = opts.height !== undefined ? opts.height : 24;
    this.validity = {{ valid: !this.invalid }};
  }}
  getAttribute(attr) {{
    if (attr === 'aria-invalid') return this.invalid ? 'true' : 'false';
    return this.attributes[attr] !== undefined ? String(this.attributes[attr]) : null;
  }}
  setAttribute(attr, val) {{ this.attributes[attr] = String(val); }}
  getBoundingClientRect() {{ return {{ width: this.width, height: this.height }}; }}
}}

const inputEl = new FakeElement({{
  tagName: 'INPUT',
  type: 'text',
  name: 'applicant_full_name',
  value: {json.dumps(SENTINEL_TEXT_VAL_ALPHA)},
  required: true
}});

const selectEl = new FakeElement({{
  tagName: 'SELECT',
  name: 'work_authorization',
  value: {json.dumps(SENTINEL_OPT_VAL_A)},
  required: true
}});

const domElements = [inputEl, selectEl];

const context = {{
  console,
  crypto: globalThis.crypto,
  TextEncoder,
  Uint8Array,
  JSON,
  Map,
  location: {{
    origin: 'https://careers.example.test',
    pathname: '/apply',
    href: 'https://careers.example.test/apply'
  }},
  document: {{
    querySelector: (sel) => null,
    querySelectorAll: (sel) => {{
      if (sel === 'input,select,textarea') return domElements;
      if (sel === 'h1,h2,h3') return [];
      return [];
    }},
    body: {{ textContent: '' }}
  }},
  getComputedStyle: () => ({{ visibility: 'visible' }})
}};
context.window = context;

vm.createContext(context);

(async () => {{
  // Call 1: initial valid nonempty values
  const obs1 = await vm.runInContext(jsCode, context);

  // Call 2: change text input to different valid nonempty text
  // A controlled framework may replace the node while keeping logical identity.
  domElements[0] = new FakeElement({{tagName:'INPUT',type:'text',name:'applicant_full_name',value:{json.dumps(SENTINEL_TEXT_VAL_BETA)},required:true}});
  const obs2 = await vm.runInContext(jsCode, context);

  // Call 3: no change (same state as call 2)
  const obs3 = await vm.runInContext(jsCode, context);

  // Call 4: change selected option
  selectEl.value = {json.dumps(SENTINEL_OPT_VAL_B)};
  const obs4 = await vm.runInContext(jsCode, context);

  process.stdout.write(JSON.stringify({{ obs1, obs2, obs3, obs4 }}));
}})();
"""
    proc = subprocess.run([node_bin, "-e", runner_script], capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def test_r6_window_state_preserved_across_evaluations(node_observations):
    """R6 invariant: Window state (page_ref) must be preserved across repeated observe calls on same page."""
    obs1 = node_observations["obs1"]
    obs2 = node_observations["obs2"]
    obs3 = node_observations["obs3"]
    obs4 = node_observations["obs4"]

    assert obs1["page_ref"] is not None
    assert obs1["page_ref"] == obs2["page_ref"] == obs3["page_ref"] == obs4["page_ref"], (
        f"Window scope id must be preserved across evaluations on same page: {obs1['page_ref']}"
    )


def test_r6_text_value_change_must_change_fingerprint(node_observations):
    """R6 regression: Same valid nonempty text -> different valid nonempty text must change fingerprint.

    Changing input value from SENTINEL_TEXT_VAL_ALPHA to SENTINEL_TEXT_VAL_BETA must alter the form fingerprint.
    """
    obs1 = node_observations["obs1"]
    obs2 = node_observations["obs2"]

    assert obs1["fingerprint"] != obs2["fingerprint"], (
        f"R6: Changing text input from valid nonempty '{SENTINEL_TEXT_VAL_ALPHA}' to "
        f"'{SENTINEL_TEXT_VAL_BETA}' must change fingerprint, but got identical fingerprint: {obs1['fingerprint']}"
    )


def test_r6_no_change_preserves_fingerprint(node_observations):
    """R6 contract: Unchanged DOM state must preserve identical fingerprint."""
    obs2 = node_observations["obs2"]
    obs3 = node_observations["obs3"]

    assert obs2["fingerprint"] == obs3["fingerprint"], (
        f"R6: Unchanged DOM must preserve identical fingerprint: {obs2['fingerprint']} vs {obs3['fingerprint']}"
    )


def test_r6_selected_option_change_must_change_fingerprint(node_observations):
    """R6 regression: Changing selected option must change fingerprint.

    Changing select value from SENTINEL_OPT_VAL_A to SENTINEL_OPT_VAL_B must alter the form fingerprint.
    """
    obs3 = node_observations["obs3"]
    obs4 = node_observations["obs4"]

    assert obs3["fingerprint"] != obs4["fingerprint"], (
        f"R6: Changing select option from '{SENTINEL_OPT_VAL_A}' to '{SENTINEL_OPT_VAL_B}' "
        f"must change fingerprint, but got identical fingerprint: {obs3['fingerprint']}"
    )


def test_r6_raw_sentinel_values_never_returned(node_observations):
    """R6 privacy contract: Raw sentinel values must never be returned in any observation structure."""
    sentinels = [
        SENTINEL_TEXT_VAL_ALPHA,
        SENTINEL_TEXT_VAL_BETA,
        SENTINEL_OPT_VAL_A,
        SENTINEL_OPT_VAL_B,
    ]
    for key in ("obs1", "obs2", "obs3", "obs4"):
        obs_json = json.dumps(node_observations[key])
        for sentinel in sentinels:
            assert sentinel not in obs_json, (
                f"R6 privacy leak: raw sentinel '{sentinel}' leaked in observation '{key}': {obs_json}"
            )
