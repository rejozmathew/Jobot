"""Focused regression tests for failure reasons: persistence, views, reports, and UI.

Contracts covered:
1. ApplicationTool caught error before action_start persists safe event and finalize retains cause in cleanup.
2. Latest-attempt failure reason consistency across view jobs, run attempts, and attempt report.
3. Late outcome event surfaces specific explanation without overwriting original completion fields.
4. Blank-code or generic cleanup fallback explicitly says 'No specific failure reason was recorded.'
5. Successful/recovered attempts do not leak obsolete failure reason to job or active/successful attempt.
6. Genuine submission uncertainty (submission_unknown) stays explicit.
7. Node DOM regression proves visible literal text in queue, run, attempt detail, and populated Problems rows.
"""
import asyncio
from contextlib import nullcontext
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import pytest

from job_applier.managed import Service
from job_applier.managed_shared import ProtocolError
from job_applier.managed_hermes_worker import ApplicationTool

STATIC_JS_PATH = Path(__file__).parents[2] / "job_applier" / "static" / "jobbot.js"


def _make_env(tmp_path):
    s = Service.create(tmp_path / "jobs.db", instance_id="test-reasons")
    s.identity(
        identity_id="candidate-1",
        person_key="person-1",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "US Citizen"}},
    )
    job = s.intake(url="https://careers.example.test/jobs/1", source_id="job-1", company="Example Corp", title="Software Engineer")
    s.eligibility(job["id"], "ready", reason="Operator approval")
    run = s.request_run(
        request_id="req-1",
        job_ids=[job["id"]],
        identity_id="candidate-1",
        browser_profile="fixture-profile",
    )
    return s, job, run


def test_worker_caught_error_persists_event_and_finalize_retains_cause(tmp_path):
    """(1) Future ApplicationTool failures before action_start persist safe event; finalize retains cause."""
    s, job, run = _make_env(tmp_path)
    worker_id = "worker-1"
    s.accept_run(
        run["id"],
        worker_id=worker_id,
        session_id="session-1",
        capabilities={
            "protocol": 1,
            "skill_version": "1.0",
            "browser_profile": run["browser_profile"],
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )
    claimed = s.claim(run["id"], worker_id=worker_id)
    attempt_id = claimed["id"]

    events_recorded = []

    class DummyClient:
        def call(self, op, **kw):
            if op == "event":
                events_recorded.append(kw)
                return s.event(attempt_id, worker_id=worker_id, fence=claimed["fence"], **kw)
            elif op == "target_state":
                return {}
            elif op == "writer_state":
                return s.writer_state(attempt_id, worker_id=worker_id, fence=claimed["fence"], state=kw.get("state", "idle"))
            return {}

    class DummyAdapter:
        client = DummyClient()

    class DummyController:
        adapters = {"session-1": DummyAdapter()}
        def handle(self, req, session_id=None):
            op = req["operation"]
            p = req.get("parameters", {})
            if op == "finish":
                return json.dumps(s.finish(attempt_id, worker_id=worker_id, fence=claimed["fence"], **p))
            elif op == "next":
                return json.dumps({})
            return json.dumps({})

    ctrl = DummyController()
    cfg = {"worker_id": worker_id, "cdp_url": "http://127.0.0.1:9222"}
    app = ApplicationTool(ctrl, "session-1", run["id"], cfg)
    app.context = {"attempt_id": attempt_id, "worker_id": worker_id, "fence": claimed["fence"]}
    app.package = {"job": job, "attempt": claimed, "documents": {"ready": True}}
    app.target = "owned-tab"
    app.target_closed = True

    # Simulate an error raised before action_start (e.g. browser_writer_busy)
    async def fake_operate(args):
        raise ProtocolError("browser_writer_busy")

    app.operate = fake_operate

    res = json.loads(app.handle({"operation": "autofill"}))
    assert res.get("error") == "browser_writer_busy"

    # Verify event was persisted
    assert len(events_recorded) >= 1
    ev = events_recorded[-1]
    assert ev.get("event_type") == "outcome"
    payload = ev.get("payload", {})
    assert payload.get("status") == "failed"
    assert payload.get("reason_code") == "browser_writer_busy"
    assert "JobBot blocked" in payload.get("evidence", "")
    assert "browser_writer_busy" in payload.get("evidence", "")
    # Must NOT claim employer rejection
    assert "rejection" not in payload.get("evidence", "").lower()
    # Must NOT leak raw tracebacks or secret args
    assert "Traceback" not in str(payload)

    # Verify finalize preserves the unresolved cause in evidence
    finalize_status = asyncio.run(app.finalize())
    assert finalize_status == "closed"

    attempt_after = s.attempt(attempt_id)
    assert attempt_after["outcome"] == "failed"
    assert "browser_writer_busy" in attempt_after["evidence"]
    assert "owned target absence verified" in attempt_after["evidence"]


def test_latest_attempt_failure_reason_consistency_across_views_and_report(tmp_path):
    """(3) Expose one consistent failure_reason on failed attempts in view() and attempt_report()."""
    s, job, run = _make_env(tmp_path)
    worker_id = "worker-1"
    s.accept_run(
        run["id"],
        worker_id=worker_id,
        session_id="session-1",
        capabilities={
            "protocol": 1,
            "skill_version": "1.0",
            "browser_profile": run["browser_profile"],
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )
    claimed = s.claim(run["id"], worker_id=worker_id)
    attempt_id = claimed["id"]

    # Record specific outcome event
    expected_reason = "JobBot blocked the autofill action because its browser state was busy or unverified (browser_writer_busy). No submission was made."
    s.event(
        attempt_id,
        worker_id=worker_id,
        fence=claimed["fence"],
        event_id="outcome-event-1",
        event_type="outcome",
        observed_at=datetime.now(timezone.utc).isoformat(),
        payload={
            "status": "failed",
            "reason_code": "browser_writer_busy",
            "tool_name": "autofill",
            "source": "worker",
            "evidence": expected_reason,
        },
    )
    s.writer_state(attempt_id, worker_id=worker_id, fence=claimed["fence"], state="idle")
    s.finish(
        attempt_id,
        worker_id=worker_id,
        fence=claimed["fence"],
        outcome="failed",
        evidence=f"{expected_reason}; owned target absence verified",
        quiescent=True,
    )

    # Check view()
    v = s.view()
    job_in_view = next(j for j in v["jobs"] if j["id"] == job["id"])
    assert "failure_reason" in job_in_view
    assert job_in_view["failure_reason"] == expected_reason

    attempt_in_view = next(a for a in v["current_run"]["attempts"] if a["id"] == attempt_id)
    assert "failure_reason" in attempt_in_view
    assert attempt_in_view["failure_reason"] == expected_reason

    # Check attempt_report()
    rep = s.attempt_report(attempt_id)
    assert rep["attempt"].get("failure_reason") == expected_reason
    assert rep.get("failure_reason") == expected_reason


def test_late_outcome_event_surfaces_explanation_without_overwriting_original_fields(tmp_path):
    """(7) Late outcome event surfaces explanation without overwriting original completion evidence/time/outcome."""
    s, job, run = _make_env(tmp_path)
    worker_id = "worker-1"
    s.accept_run(
        run["id"],
        worker_id=worker_id,
        session_id="session-1",
        capabilities={
            "protocol": 1,
            "skill_version": "1.0",
            "browser_profile": run["browser_profile"],
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )
    claimed = s.claim(run["id"], worker_id=worker_id)
    attempt_id = claimed["id"]

    orig_evidence = "Worker exited before submission; owned target absence verified"
    s.writer_state(attempt_id, worker_id=worker_id, fence=claimed["fence"], state="idle")
    s.finish(
        attempt_id,
        worker_id=worker_id,
        fence=claimed["fence"],
        outcome="failed",
        evidence=orig_evidence,
        quiescent=True,
    )

    attempt_before = s.attempt(attempt_id)
    orig_completed_at = attempt_before["completed_at"]

    # Parent adds late outcome event through existing event API / DB
    late_explanation = "JobBot blocked the Simplify click because its browser state was busy or unverified (browser_writer_busy). No submission was made."
    with s.tx() as db:
        from job_applier.managed_shared import dumps
        db.execute(
            "INSERT INTO managed_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "late-event-huron-1",
                attempt_id,
                run["id"],
                None,
                worker_id,
                "outcome",
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
                None,
                0,
                dumps({
                    "status": "failed",
                    "reason_code": "browser_writer_busy",
                    "tool_name": "autofill",
                    "source": "saved_worker_log",
                    "evidence": late_explanation,
                }),
                "hash-late-1",
            ),
        )

    # Verify attempt in DB did not have its original completion fields modified
    attempt_after = s.attempt(attempt_id)
    assert attempt_after["evidence"] == orig_evidence
    assert attempt_after["completed_at"] == orig_completed_at
    assert attempt_after["outcome"] == "failed"

    # View and report surface the late explanation as failure_reason
    v = s.view()
    job_in_view = next(j for j in v["jobs"] if j["id"] == job["id"])
    assert job_in_view["failure_reason"] == late_explanation

    rep = s.attempt_report(attempt_id)
    assert rep["attempt"]["failure_reason"] == late_explanation


def test_blank_code_and_unrecorded_fallback(tmp_path):
    """(3) Existing records with generic cleanup and no precise reason say 'No specific failure reason was recorded.'"""
    s, job, run = _make_env(tmp_path)
    worker_id = "worker-1"
    s.accept_run(
        run["id"],
        worker_id=worker_id,
        session_id="session-1",
        capabilities={
            "protocol": 1,
            "skill_version": "1.0",
            "browser_profile": run["browser_profile"],
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )
    claimed = s.claim(run["id"], worker_id=worker_id)
    attempt_id = claimed["id"]

    s.writer_state(attempt_id, worker_id=worker_id, fence=claimed["fence"], state="idle")
    s.finish(
        attempt_id,
        worker_id=worker_id,
        fence=claimed["fence"],
        outcome="failed",
        evidence="Worker exited before submission; owned target absence verified",
        quiescent=True,
    )

    expected = "No specific failure reason was recorded."
    v = s.view()
    job_in_view = next(j for j in v["jobs"] if j["id"] == job["id"])
    assert job_in_view.get("failure_reason") == expected

    rep = s.attempt_report(attempt_id)
    assert rep["attempt"].get("failure_reason") == expected


def test_recovered_and_successful_attempts_do_not_leak_failure(tmp_path):
    """(2, 3) Successful retries/successful outcomes must not display obsolete failure as current."""
    s, job, run = _make_env(tmp_path)
    worker_id = "worker-1"
    s.accept_run(
        run["id"],
        worker_id=worker_id,
        session_id="session-1",
        capabilities={
            "protocol": 1,
            "skill_version": "1.0",
            "browser_profile": run["browser_profile"],
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )

    # Attempt 1 fails
    claimed1 = s.claim(run["id"], worker_id=worker_id)
    att1_id = claimed1["id"]
    s.writer_state(att1_id, worker_id=worker_id, fence=claimed1["fence"], state="idle")
    s.finish(
        att1_id,
        worker_id=worker_id,
        fence=claimed1["fence"],
        outcome="failed",
        evidence="Something failed; owned target absence verified",
        quiescent=True,
    )

    # Reset job to queued for retry in run
    with s.tx() as db:
        db.execute("UPDATE run_jobs SET state='pending' WHERE run_id=? AND job_id=?", (run["id"], job["id"]))
        db.execute("UPDATE jobs SET status='queued' WHERE id=?", (job["id"],))

    # Attempt 2 succeeds
    claimed2 = s.claim(run["id"], worker_id=worker_id)
    att2_id = claimed2["id"]
    s.submission_intent(att2_id, worker_id=worker_id, fence=claimed2["fence"], evidence="Intent verified", fixture=True)
    s.writer_state(att2_id, worker_id=worker_id, fence=claimed2["fence"], state="idle")
    s.finish(
        att2_id,
        worker_id=worker_id,
        fence=claimed2["fence"],
        outcome="applied",
        evidence="Employer confirmation verified",
        quiescent=True,
    )

    v = s.view()
    job_in_view = next(j for j in v["jobs"] if j["id"] == job["id"])
    assert job_in_view["status"] == "applied"
    assert job_in_view.get("failure_reason") is None, "Successful job must not retain obsolete failure reason"

    attempts = {a["id"]: a for a in v["current_run"]["attempts"]}
    assert attempts[att2_id].get("failure_reason") is None, "Applied attempt must not have failure reason"
    assert attempts[att1_id].get("failure_reason") is not None, "Old attempt preserves its own historical failure"


def test_submission_unknown_retains_explicit_uncertainty(tmp_path):
    """(5) Genuine submission uncertainty stays explicit and must not imply no submission."""
    s, job, run = _make_env(tmp_path)
    worker_id = "worker-1"
    s.accept_run(
        run["id"],
        worker_id=worker_id,
        session_id="session-1",
        capabilities={
            "protocol": 1,
            "skill_version": "1.0",
            "browser_profile": run["browser_profile"],
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )
    claimed = s.claim(run["id"], worker_id=worker_id)
    attempt_id = claimed["id"]

    s.submission_intent(attempt_id, worker_id=worker_id, fence=claimed["fence"], evidence="Intent verified", fixture=True)
    s.writer_state(attempt_id, worker_id=worker_id, fence=claimed["fence"], state="idle")
    s.finish(
        attempt_id,
        worker_id=worker_id,
        fence=claimed["fence"],
        outcome="submission_unknown",
        evidence="Submit clicked; employer confirmation not verified. Do not retry.",
        quiescent=True,
    )

    v = s.view()
    job_in_view = next(j for j in v["jobs"] if j["id"] == job["id"])
    assert "Submit clicked" in (job_in_view.get("failure_reason") or "")
    assert "not verified" in (job_in_view.get("failure_reason") or "")


def test_node_dom_behavior_render_queue_run_and_problems_table():
    """(4, 8) Node DOM behavior: renderQueue, renderRun, loadAttempt with literal text and populated Problems rows."""
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node not available")

    script = f"""
const fs = require('fs');
const vm = require('vm');

const jsCode = fs.readFileSync({json.dumps(str(STATIC_JS_PATH))}, 'utf8');

class FakeElement {{
  constructor(tag, text, cls) {{
    this.tagName = (tag || 'DIV').toUpperCase();
    this.textContent = text !== undefined ? String(text) : '';
    this.className = cls || '';
    this.children = [];
    this.attributes = {{}};
    this.dataset = {{}};
    this.hidden = false;
    const classes = new Set();
    this.classList = {{
      classes,
      toggle: (c, val) => {{ if (val) classes.add(c); else classes.delete(c); }},
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c)
    }};
  }}
  append(...nodes) {{
    for (const n of nodes) {{
      if (n === undefined || n === null) continue;
      if (typeof n === 'string') {{
        this.children.push(new FakeElement('SPAN', n));
        this.textContent += n;
      }} else {{
        this.children.push(n);
        this.textContent += n.textContent;
      }}
    }}
  }}
  replaceChildren(...nodes) {{
    this.children = [];
    this.textContent = '';
    this.append(...nodes);
  }}
  setAttribute(attr, val) {{ this.attributes[attr] = String(val); }}
  getAttribute(attr) {{ return this.attributes[attr] !== undefined ? this.attributes[attr] : null; }}
  querySelector(sel) {{ return this.querySelectorAll(sel)[0] || null; }}
  querySelectorAll(sel) {{
    const res = [];
    function scan(el) {{
      for (const c of el.children) {{
        if (c.tagName && (sel.startsWith('.') ? c.className.split(' ').includes(sel.slice(1)) :
          sel.startsWith('details[') ? c.tagName==='DETAILS' && 'progressKey' in c.dataset :
          sel.toUpperCase()===c.tagName)) res.push(c);
        scan(c);
      }}
    }}
    scan(this);
    return res;
  }}
}}

const elements = new Map();
function getEl(id) {{
  if (!elements.has(id)) elements.set(id, new FakeElement('DIV', '', id));
  return elements.get(id);
}}

const context = {{
  console,
  document: {{
    getElementById: (id) => getEl(id),
    createElement: (tag) => new FakeElement(tag),
    createTextNode: (text) => new FakeElement('SPAN', text),
    querySelectorAll: (sel) => []
  }},
  Intl: globalThis.Intl,
  Date: globalThis.Date,
  URL: globalThis.URL,
  JSON: globalThis.JSON,
  Set: globalThis.Set,
  Map: globalThis.Map,
  Number: globalThis.Number,
  String: globalThis.String,
  setInterval: () => {{}},
  clearInterval: () => {{}},
  location: {{ reload: () => {{}} }},
  fetch: async (path) => {{
    if (typeof path === 'string' && path.includes('attempt_report')) {{
      return {{ ok: true, status: 200, json: async () => testReport }};
    }}
    return {{ ok: true, status: 200, json: async () => ({{}}) }};
  }}
}};

vm.createContext(context);
vm.runInContext(jsCode, context);

// 1. Test renderQueue with failed job and failure_reason
const vQueue = {{
  jobs: [
    {{
      id: 'job-f1',
      title: 'Failed Job Title',
      company: 'Test Co',
      status: 'failed',
      failure_reason: 'JobBot blocked the Simplify click because state was busy (browser_writer_busy).'
    }}
  ]
}};
context.renderQueue(vQueue);
const queueRows = getEl('queue-rows');
const queueText = queueRows.textContent;
if (!queueText.includes('Reason: JobBot blocked the Simplify click')) {{
  throw new Error('renderQueue missing visible Reason text: ' + queueText);
}}

// 2. Test renderRun with attempt having failure_reason
const vRun = {{
  runs: [{{ id: 'run-1', requested_at: new Date().toISOString(), state: 'completed' }}],
  current_run: {{
    run_id: 'run-1',
    state: 'completed',
    attempts: [
      {{
        id: 101,
        outcome: 'failed',
        elapsed_seconds: 12.5,
        heartbeat_age_seconds: 5,
        progress_age_seconds: 5,
        writer_state: 'idle',
        failure_reason: 'JobBot blocked the Simplify click (browser_writer_busy).'
      }}
    ],
    selected: 1, completed: 1, applied: 0, blocked: 0, current: 0, remaining: 0
  }}
}};
context.renderRun(vRun);
const attemptsEl = getEl('attempts');
const runText = attemptsEl.textContent;
if (!runText.includes('Reason: JobBot blocked the Simplify click')) {{
  throw new Error('renderRun missing visible Reason text on attempt card: ' + runText);
}}

// 3. Test loadAttempt with failure_reason and populated Problems table rows
const testReport = {{
  attempt: {{
    id: 101,
    outcome: 'failed',
    company: 'Test Co',
    platform: 'greenhouse',
    started_at: new Date().toISOString(),
    completed_at: new Date().toISOString(),
    failure_reason: 'JobBot blocked the Simplify click (browser_writer_busy).'
  }},
  timing: {{ wall_seconds: 12.5, observed_union_seconds: 10.0, unattributed_seconds: 2.5, category_seconds: {{ tool: 5, model: 5 }}, uncertainty: false, overlap_note: '' }},
  phases: [],
  fields: {{}},
  simplify: {{ runs_count: 0, fallback_reasons: [] }},
  problems: [
    {{
      event_id: 'ev-prob-1',
      category: 'action_failed',
      field_key: 'first_name',
      fallback_reason: 'browser_writer_busy',
      source: 'native',
      status: 'unresolved',
      resolution: null
    }}
  ],
  timeline: []
}};

// Stub api to return testReport for attempt_report
context.api = async (op, params) => {{
  if (op === 'attempt_report') return testReport;
  return {{}};
}};

context.loadAttempt(101).then(() => {{
  const eventsEl = getEl('events');
  const eventsText = eventsEl.textContent;
  if (!eventsText.includes('Reason: JobBot blocked the Simplify click')) {{
    console.error('loadAttempt missing prominent Reason text:', eventsText);
    process.exit(1);
  }}

  // Check Problems table has populated row with fallback_reason and status
  const tables = eventsEl.querySelectorAll('table');
  let problemTableFound = false;
  for (const t of tables) {{
    const text = t.textContent;
    if (text.includes('action_failed') && text.includes('first_name') && text.includes('browser_writer_busy')) {{
      problemTableFound = true;
      break;
    }}
  }}
  if (!problemTableFound) {{
    console.error('Problems table was empty or missing expected row data');
    process.exit(2);
  }}

  console.log('SUCCESS: Node DOM behavior verified');
}}).catch(err => {{
  console.error(err);
  process.exit(3);
}});
"""

    res = subprocess.run([node_bin, "-e", script], capture_output=True, text=True, timeout=15)
    assert res.returncode == 0, f"Node DOM test failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
