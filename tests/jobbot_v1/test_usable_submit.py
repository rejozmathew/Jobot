import json
from pathlib import Path
import shutil
import subprocess
import pytest

OBSERVE_JS_PATH = Path(__file__).parents[2] / "job_applier" / "browser_helpers" / "simplify_observe.js"
CLICK_JS_PATH = Path(__file__).parents[2] / "job_applier" / "browser_helpers" / "simplify_click.js"


def test_node_simplify_multi_root_decoy_and_zero_size_host_regression():
    """Regression test: official Simplify has multiple shadow roots and zero-size hosts.

    Decoy first root must not mask live button in a later root with zero-size host.
    """
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node not available")

    runner_script = f"""
const fs = require('fs');
const vm = require('vm');

const observeCode = fs.readFileSync({json.dumps(str(OBSERVE_JS_PATH))}, 'utf8');
const clickCode = fs.readFileSync({json.dumps(str(CLICK_JS_PATH))}, 'utf8');

class FakeElement {{
  constructor(opts) {{
    this.tagName = (opts.tagName || 'DIV').toUpperCase();
    this.type = opts.type || 'text';
    this.name = opts.name || '';
    this.value = opts.value || '';
    this.textContent = opts.textContent || '';
    this.innerText = opts.innerText || this.textContent;
    this.disabled = !!opts.disabled;
    this.attributes = opts.attributes || {{}};
    this.width = opts.width !== undefined ? opts.width : 100;
    this.height = opts.height !== undefined ? opts.height : 24;
    this.children = opts.children || [];
    this.classList = {{
      classes: new Set(opts.classes || []),
      contains: (c) => this.classList.classes.has(c)
    }};
    this.isConnected = true;
    this.shadowRoot = opts.shadowRoot || null;
    this.rootNode = null;
  }}
  getAttribute(attr) {{
    if (attr === 'aria-disabled') return this.disabled ? 'true' : 'false';
    return this.attributes[attr] !== undefined ? String(this.attributes[attr]) : null;
  }}
  setAttribute(attr, val) {{ this.attributes[attr] = String(val); }}
  getBoundingClientRect() {{ return {{ width: this.width, height: this.height }}; }}
  getRootNode() {{ return this.rootNode || this; }}
  querySelectorAll(sel) {{
    const res = [];
    for (const c of this.children) {{
      if (sel.includes('button') && (c.tagName === 'BUTTON' || c.getAttribute('role') === 'button')) {{
        res.push(c);
      }}
    }}
    return res;
  }}
  querySelector(sel) {{
    const all = this.querySelectorAll(sel);
    return all.length ? all[0] : null;
  }}
  click() {{ this.clicked = true; }}
}}

// Host 1: decoy first root. Zero size, empty shadow root (no buttons)
const host1 = new FakeElement({{
  classes: ['simplify-jobs-shadow-root'],
  width: 0,
  height: 0
}});
const shadow1 = new FakeElement({{ children: [] }});
shadow1.host = host1;
host1.shadowRoot = shadow1;

// Host 2: zero-size host containing a visible live "Autofill This Page" button
const host2 = new FakeElement({{
  classes: ['simplify-jobs-shadow-root'],
  width: 0,
  height: 0
}});
const liveButton = new FakeElement({{
  tagName: 'BUTTON',
  textContent: 'Autofill This Page',
  width: 120,
  height: 36,
  disabled: false
}});
const shadow2 = new FakeElement({{ children: [liveButton] }});
shadow2.host = host2;
liveButton.rootNode = shadow2;
host2.shadowRoot = shadow2;

const allHosts = [host1, host2];

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
    querySelector: (sel) => {{
      if (sel === '.simplify-jobs-shadow-root') return allHosts[0];
      return null;
    }},
    querySelectorAll: (sel) => {{
      if (sel === '.simplify-jobs-shadow-root') return allHosts;
      if (sel === 'input,select,textarea') return [];
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
  // 1. Observe: must find live button in second root despite zero-size host
  const obs = await vm.runInContext(observeCode, context);

  // 2. Click: must validate root and click the control
  const clickFn = vm.runInContext(clickCode, context);
  let clickRes = null;
  if (obs.controls && obs.controls.autofill && obs.controls.autofill.ref) {{
    clickRes = clickFn({{
      ref: obs.controls.autofill.ref,
      operation: 'autofill',
      url: obs.url,
      page_ref: obs.page_ref
    }});
  }}

  process.stdout.write(JSON.stringify({{ obs, clickRes, liveButtonClicked: liveButton.clicked || false }}));
}})();
"""
    proc = subprocess.run([node_bin, "-e", runner_script], capture_output=True, text=True, check=True)
    res = json.loads(proc.stdout)
    obs = res["obs"]
    assert obs["panel"] is True
    assert obs["controls"]["autofill"]["enabled"] is True
    assert obs["controls"]["autofill"]["ref"] is not None
    assert obs["status"] == "ready"
    assert res["clickRes"] == {"status": "clicked", "clicked": True}
    assert res["liveButtonClicked"] is True


def test_node_simplify_active_writer_beats_ready():
    """Active writer in any relevant panel beats ready status."""
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node not available")

    runner_script = f"""
const fs = require('fs');
const vm = require('vm');

const observeCode = fs.readFileSync({json.dumps(str(OBSERVE_JS_PATH))}, 'utf8');

class FakeElement {{
  constructor(opts) {{
    this.tagName = (opts.tagName || 'DIV').toUpperCase();
    this.disabled = !!opts.disabled;
    this.textContent = opts.textContent || '';
    this.innerText = opts.innerText || this.textContent;
    this.width = opts.width !== undefined ? opts.width : 100;
    this.height = opts.height !== undefined ? opts.height : 24;
    this.children = opts.children || [];
    this.classList = {{ contains: () => true }};
    this.isConnected = true;
    this.attributes = opts.attributes || {{}};
  }}
  getAttribute(attr) {{ return this.attributes[attr] || null; }}
  getBoundingClientRect() {{ return {{ width: this.width, height: this.height }}; }}
  querySelectorAll(sel) {{
    const res = [];
    for (const c of this.children) {{
      if (sel.includes('button') && c.tagName === 'BUTTON') res.push(c);
    }}
    return res;
  }}
  querySelector(sel) {{
    if (sel.includes('aria-busy')) {{
      return this.children.find(c => c.getAttribute('aria-busy') === 'true') || null;
    }}
    return null;
  }}
}}

// Host 1 has ready button
const btn = new FakeElement({{ tagName: 'BUTTON', textContent: 'Autofill This Page', disabled: false }});
const shadow1 = new FakeElement({{ children: [btn] }});
const host1 = new FakeElement({{ children: [] }});
shadow1.host = host1;
host1.shadowRoot = shadow1;

// Host 2 has an explicit writer, not only a cosmetic spinner beside an input.
const busyEl = new FakeElement({{ tagName: 'DIV', attributes: {{ 'aria-busy': 'true' }} }});
const shadow2 = new FakeElement({{ children: [busyEl], textContent: 'Filling your application' }});
const host2 = new FakeElement({{ children: [] }});
shadow2.host = host2;
host2.shadowRoot = shadow2;

const context = {{
  console,
  crypto: globalThis.crypto,
  TextEncoder,
  Uint8Array,
  JSON,
  Map,
  location: {{ origin: 'https://careers.example.test', pathname: '/apply', href: 'https://careers.example.test/apply' }},
  document: {{
    querySelectorAll: (sel) => sel === '.simplify-jobs-shadow-root' ? [host1, host2] : [],
    querySelector: () => null,
    body: {{ textContent: '' }}
  }},
  getComputedStyle: () => ({{ visibility: 'visible' }})
}};
context.window = context;
vm.createContext(context);

(async () => {{
  const obs = await vm.runInContext(observeCode, context);
  process.stdout.write(JSON.stringify(obs));
}})();
"""
    proc = subprocess.run([node_bin, "-e", runner_script], capture_output=True, text=True, check=True)
    obs = json.loads(proc.stdout)
    assert obs["status"] == "active"


def test_node_simplify_ambiguous_multiple_actionable_controls():
    """Multiple actionable controls must not be guessed (fail closed)."""
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node not available")

    runner_script = f"""
const fs = require('fs');
const vm = require('vm');

const observeCode = fs.readFileSync({json.dumps(str(OBSERVE_JS_PATH))}, 'utf8');

class FakeElement {{
  constructor(opts) {{
    this.tagName = (opts.tagName || 'DIV').toUpperCase();
    this.disabled = !!opts.disabled;
    this.textContent = opts.textContent || '';
    this.innerText = opts.innerText || this.textContent;
    this.width = opts.width !== undefined ? opts.width : 100;
    this.height = opts.height !== undefined ? opts.height : 24;
    this.children = opts.children || [];
    this.classList = {{ contains: () => true }};
    this.isConnected = true;
    this.attributes = opts.attributes || {{}};
  }}
  getAttribute(attr) {{ return this.attributes[attr] || null; }}
  getBoundingClientRect() {{ return {{ width: this.width, height: this.height }}; }}
  querySelectorAll(sel) {{
    const res = [];
    for (const c of this.children) {{
      if (sel.includes('button') && c.tagName === 'BUTTON') res.push(c);
    }}
    return res;
  }}
  querySelector(sel) {{ return null; }}
}}

// Two different roots each with an enabled autofill button
const btn1 = new FakeElement({{ tagName: 'BUTTON', textContent: 'Autofill This Page', disabled: false }});
const shadow1 = new FakeElement({{ children: [btn1] }});
const host1 = new FakeElement({{ children: [] }});
shadow1.host = host1;
host1.shadowRoot = shadow1;

const btn2 = new FakeElement({{ tagName: 'BUTTON', textContent: 'Autofill This Page', disabled: false }});
const shadow2 = new FakeElement({{ children: [btn2] }});
const host2 = new FakeElement({{ children: [] }});
shadow2.host = host2;
host2.shadowRoot = shadow2;

const context = {{
  console,
  crypto: globalThis.crypto,
  TextEncoder,
  Uint8Array,
  JSON,
  Map,
  location: {{ origin: 'https://careers.example.test', pathname: '/apply', href: 'https://careers.example.test/apply' }},
  document: {{
    querySelectorAll: (sel) => sel === '.simplify-jobs-shadow-root' ? [host1, host2] : [],
    querySelector: () => null,
    body: {{ textContent: '' }}
  }},
  getComputedStyle: () => ({{ visibility: 'visible' }})
}};
context.window = context;
vm.createContext(context);

(async () => {{
  const obs = await vm.runInContext(observeCode, context);
  process.stdout.write(JSON.stringify(obs));
}})();
"""
    proc = subprocess.run([node_bin, "-e", runner_script], capture_output=True, text=True, check=True)
    obs = json.loads(proc.stdout)
    assert obs["controls"]["autofill"]["enabled"] is False
    assert obs["controls"]["autofill"]["ref"] is None
    assert obs["status"] != "ready"


def test_settings_reasoning_effort_defaults_and_choices(tmp_path):
    from job_applier.managed import Service
    from job_applier.managed_settings import DEFAULTS, CHOICES

    assert DEFAULTS["reasoning_effort"] == "low"
    assert "reasoning_effort" in CHOICES
    assert CHOICES["reasoning_effort"] == ("low", "medium", "high", "xhigh")

    s = Service.create(tmp_path / "jobs.db", instance_id="test-settings-effort")
    view = s.settings_view()
    assert view["values"]["reasoning_effort"] == "low"
    assert view["supported"]["reasoning_effort"] == ("low", "medium", "high", "xhigh")

    # Configure reasoning_effort
    updated = s.configure({"reasoning_effort": "high"}, expected_version=view["version"])
    assert updated["values"]["reasoning_effort"] == "high"


def test_reasoning_matches_and_backward_compatibility(tmp_path):
    from job_applier.managed import Service
    from job_applier.managed_shared import ProtocolError

    s = Service.create(tmp_path / "jobs.db", instance_id="test-effort-match")
    s.identity(
        identity_id="cand-1",
        person_key="pk-1",
        email="cand@example.test",
        profile={"facts": {}},
    )
    job = s.intake(url="https://careers.example.test/jobs/1", source_id="1")
    s.eligibility(job["id"], "ready", reason="operator approval")

    # 1. Run requested with default settings (low effort)
    r0 = s.request_run(
        request_id="req-0",
        job_ids=[job["id"]],
        identity_id="cand-1",
        browser_profile="profile-a",
    )
    # Matching worker capabilities without explicit effort (backward compatibility)
    acc0 = s.accept_run(
        r0["id"],
        worker_id="w-0",
        session_id="sess-0",
        capabilities={
            "protocol": 1,
            "skill_version": "v1",
            "browser_profile": "profile-a",
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )
    assert acc0["state"] == "accepted"

    # 2. Configure high effort and model
    cur = s.settings_view()
    s.configure(
        {
            "reasoning_provider": "openai-codex",
            "reasoning_model": "gpt-5.6-luna",
            "reasoning_effort": "high",
        },
        expected_version=cur["version"],
    )

    job2 = s.intake(url="https://careers.example.test/jobs/2", source_id="2")
    s.eligibility(job2["id"], "ready", reason="operator approval")
    r1 = s.request_run(
        request_id="req-1",
        job_ids=[job2["id"]],
        identity_id="cand-1",
        browser_profile="profile-a",
    )

    # Worker reporting mismatching effort 'low' must be rejected
    with pytest.raises(ProtocolError):
        s.accept_run(
            r1["id"],
            worker_id="w-1",
            session_id="sess-1",
            capabilities={
                "protocol": 1,
                "skill_version": "v1",
                "browser_profile": "profile-a",
                "provider": "openai-codex",
                "model": "gpt-5.6-luna",
                "reasoning_effort": "low",
                "telemetry": True,
            },
        )

    # Worker reporting matching effort 'high' is accepted
    acc1 = s.accept_run(
        r1["id"],
        worker_id="w-1",
        session_id="sess-1",
        capabilities={
            "protocol": 1,
            "skill_version": "v1",
            "browser_profile": "profile-a",
            "provider": "openai-codex",
            "model": "gpt-5.6-luna",
            "reasoning_effort": "high",
            "telemetry": True,
        },
    )
    assert acc1["state"] == "accepted"


def test_hermes_adapter_and_plugin_controller_effort(tmp_path):
    import os
    from job_applier.managed import Service
    from job_applier.hermes_adapter import HermesAdapter
    from job_applier.hermes_plugin import PluginController
    from job_applier.managed_client import Client

    s = Service.create(tmp_path / "jobs.db", instance_id="test-hermes-effort")
    spool = tmp_path / "spool.db"

    client = Client("http://127.0.0.1:8000", "test-hermes-effort", "dummy-token")
    adapter = HermesAdapter(
        client,
        worker_id="worker-h",
        session_id="sess-h",
        browser_profile="chrome",
        skill_version="v1",
        provider="openai-codex",
        model="gpt-5.6-luna",
        spool_path=spool,
        reasoning_effort="high",
    )
    assert adapter.capabilities.get("reasoning_effort") == "high"

    # Test PluginController _observe_runtime with reasoning_config
    cfg_path = tmp_path / "plugin_cfg.json"
    cfg_path.write_text(json.dumps({
        "base_url": "http://127.0.0.1:8000",
        "instance_id": "test-hermes-effort",
        "worker_id": "worker-h",
        "browser_profile": "chrome",
        "skill_version": "v1",
        "provider": "openai-codex",
        "model": "gpt-5.6-luna",
        "worker_token_env": "WORKER_TOKEN_ENV_TEST",
        "spool_dir": str(tmp_path),
        "reasoning_effort": "high",
    }), encoding="utf-8")
    os.environ["WORKER_TOKEN_ENV_TEST"] = "test-token"

    pc = PluginController(str(cfg_path))
    pc.route(
        "post_api_request",
        session_id="sess-h",
        model="gpt-5.6-luna",
        provider="openai-codex",
        response_model="gpt-5.6-luna",
        base_url="https://chatgpt.com/backend-api/codex",
        reasoning_config={"effort": "high"},
    )
    assert pc.runtime["sess-h"]["reasoning_effort"] == "high"


def test_next_request_protocol_and_worker_api(tmp_path):
    from fastapi.testclient import TestClient
    from job_applier.managed import Service
    from job_applier.managed_api import create_app

    operator_token = "synthetic-operator-token-jobbot-v1-32chars"
    worker_token = "synthetic-worker-token-jobbot-v1-32chars"
    worker_id = "worker-1"

    s = Service.create(tmp_path / "jobs.db", instance_id="test-next-request")
    s.identity(
        identity_id="candidate-1",
        person_key="pk",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "US Citizen", "location": "Austin TX"}},
    )
    cur = s.settings_view()
    s.configure(
        {
            "reasoning_provider": "openai-codex",
            "reasoning_model": "gpt-5.6-luna",
            "reasoning_effort": "medium",
        },
        expected_version=cur["version"],
    )

    job = s.intake(url="https://careers.example.test/jobs/0", source_id="0")
    s.eligibility(job["id"], "ready", reason="operator approval")

    # Before request_run: next_request returns None
    assert s.next_request("fixture-browser") is None

    # Request run
    r = s.request_run(
        request_id="req-next-1",
        job_ids=[job["id"]],
        identity_id="candidate-1",
        browser_profile="fixture-browser",
    )

    # 1. Protocol method next_request
    req_info = s.next_request("fixture-browser")
    assert req_info is not None
    assert req_info["run_id"] == r["id"]
    assert req_info["model"] == "gpt-5.6-luna"
    assert req_info["provider"] == "openai-codex"
    assert req_info["effort"] == "medium"
    assert req_info["reasoning_effort"] == "medium"
    # Verify no candidate profile/token/PII in req_info
    raw_str = json.dumps(req_info)
    assert "candidate@example.test" not in raw_str
    assert "US Citizen" not in raw_str
    assert "Austin TX" not in raw_str

    # 2. Worker HTTP API permission via /v1/next_request
    app = create_app(s, operator_token=operator_token, worker_tokens={worker_token: worker_id})
    client = TestClient(app, base_url="http://127.0.0.1:8769")

    # Worker can call next_request without worker_id in payload
    res = client.post(
        "/v1/next_request",
        headers={"Authorization": f"Bearer {worker_token}", "X-JobBot-Instance": s.instance_id},
        json={"browser_profile": "fixture-browser"},
    )
    assert res.status_code == 200
    worker_next = res.json()
    assert worker_next["run_id"] == r["id"]
    assert worker_next["model"] == "gpt-5.6-luna"
    assert worker_next["effort"] == "medium"

    # Mismatching browser profile returns None (JSON null)
    res_other = client.post(
        "/v1/next_request",
        headers={"Authorization": f"Bearer {worker_token}", "X-JobBot-Instance": s.instance_id},
        json={"browser_profile": "other-browser"},
    )
    assert res_other.status_code == 200
    assert res_other.json() is None

    # When control is stopped or paused, next_request returns None
    s.control(r["id"], command="stop")
    assert s.next_request("fixture-browser") is None


def test_view_exposes_effort_in_focused_context(tmp_path):
    from job_applier.managed import Service

    s = Service.create(tmp_path / "jobs.db", instance_id="test-view-effort")
    s.identity(identity_id="cand-v", person_key="pk", email="c@test.com", profile={"facts": {}})
    cur = s.settings_view()
    s.configure(
        {"reasoning_provider": "openai-codex", "reasoning_model": "gpt-5.6-luna", "reasoning_effort": "high"},
        expected_version=cur["version"],
    )
    job = s.intake(url="https://careers.example.test/jobs/view1", source_id="v1")
    s.eligibility(job["id"], "ready", reason="approval")
    r = s.request_run(request_id="req-v", job_ids=[job["id"]], identity_id="cand-v", browser_profile="chrome-v")
    s.accept_run(
        r["id"],
        worker_id="w-v",
        session_id="s-v",
        capabilities={
            "protocol": 1,
            "skill_version": "v1",
            "browser_profile": "chrome-v",
            "provider": "openai-codex",
            "model": "gpt-5.6-luna",
            "reasoning_effort": "high",
            "telemetry": True,
        },
    )
    v = s.view(run_id=r["id"])
    curr = v["current_run"]
    assert curr["requested_reasoning_effort"] == "high"
    assert curr["actual_reasoning_effort"] == "high"


def test_ui_redesign_contract():
    html_path = Path(__file__).parents[2] / "job_applier" / "static" / "jobbot.html"
    css_path = Path(__file__).parents[2] / "job_applier" / "static" / "jobbot.css"
    js_path = Path(__file__).parents[2] / "job_applier" / "static" / "jobbot.js"

    html = html_path.read_text(encoding="utf-8")
    css = css_path.read_text(encoding="utf-8")
    js = js_path.read_text(encoding="utf-8")

    # 1. New operator controls exist
    for el_id in (
        "start-application-btn",
        "main-model-picker",
        "main-effort-picker",
        "main-submission-mode",
        "main-resume-filename",
    ):
        assert f'id="{el_id}"' in html

    # 2. Key options exist
    assert "gpt-5.6-luna" in html
    assert "gpt-5.6-terra" in html
    assert "xhigh" in html

    # 3. Old IDs preserved
    for old_id in (
        "candidate",
        "browser-profile",
        "mark-ready",
        "request-run",
        "queue-rows",
        "queue-count",
        "selection",
        "run-picker",
        "run-state",
        "run-counts",
        "run-owner",
        "focused-context",
        "target-list",
        "extension-list",
        "attempts",
        "attempt-summary",
        "events",
        "profile-candidate",
        "profile-email",
        "profile-full-name",
        "profile-work-auth",
        "profile-resume",
        "profile-json",
        "settings-version",
        "settings-form",
        "setting-fields",
        "health",
    ):
        assert f'id="{old_id}"' in html

    # 4. CSS design contracts: neutral near-white canvas, dark ink, restrained teal, no gradient hero
    assert "--bg-canvas: #f8fafc;" in css
    assert "--text-main: #0f172a;" in css
    assert "--accent: #0d9488;" in css
    assert "linear-gradient" not in css
    assert "overflow-x: hidden" in css

    # 5. JS wires start-application-btn, auto-populates browser-profile, honest worker status
    assert "start-application-btn" in js
    assert "main-model-picker" in js
    assert "main-effort-picker" in js
    assert "Worker disconnected / not running" in js
    assert "Stop request pending" in js
    assert "verified-evidence" in js
