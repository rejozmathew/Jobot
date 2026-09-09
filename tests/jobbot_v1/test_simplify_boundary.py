"""Unit and contract tests for SimplifyBoundary interface and Service single-writer enforcement.

Primary owns actual helper implementation and later real-browser integration.
These tests define the contract for:
1. SimplifyBoundary(page, *, budget_seconds=45, poll_seconds=0.1, clock=None, sleeper=None)
   - page evaluate port handling 'jobbot:simplify:observe' and 'jobbot:simplify:click'
   - decide(observation, already_attempted=False)
   - observe() -> sanitized observation
   - perform(operation) -> result {status, changed, writer_state, reason}
2. Service single-writer regression:
   - action_start gains writes_browser=True default
   - concurrent writing action rejected while writing action is open
   - read-only action (writes_browser=False) allowed concurrently
   - writing action rejected while writer_state is active or unknown
   - writing action allowed after confirmed idle and previous writer action ended
"""

import asyncio
import importlib.util
from pathlib import Path
import pytest

from job_applier.managed import Service, ProtocolError

try:
    from test_ownership import ready, accept
except ImportError:
    from tests.jobbot_v1.test_ownership import ready, accept

try:
    from job_applier.simplify_boundary import SimplifyBoundary
except ImportError:
    SimplifyBoundary = None


def get_boundary_cls():
    assert SimplifyBoundary is not None, (
        "job_applier.simplify_boundary module not found (expected RED in test-only stage; Primary owns actual helper)"
    )
    return SimplifyBoundary


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "simplify"


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
    """External DOM seam unit port implementing evaluate(script, arg=None)."""

    def __init__(self, observation=None, url="https://careers.example.test/jobs/1/apply"):
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
            return {"status": "ok", "clicked": arg}
        raise ValueError(f"Unrecognized script marker in port: {script[:60]}")


# ---------------------------------------------------------------------------
# HTML Fixture Contract Verifications
# ---------------------------------------------------------------------------


def test_fixtures_exist_and_meet_contract():
    """Fixtures must exist, declare synthetic notice, and contain no external scripts/PII."""
    expected_files = [
        "supported_standin.html",
        "disabled_standin.html",
        "missing_panel_form.html",
    ]
    for filename in expected_files:
        path = FIXTURES_DIR / filename
        assert path.is_file(), f"Missing fixture file: {path}"
        content = path.read_text(encoding="utf-8")
        assert "Synthetic fixture; not official Simplify support" in content
        assert "http://" not in content and "https://" not in content
        assert "<script src=" not in content.lower()

    supported = (FIXTURES_DIR / "supported_standin.html").read_text(encoding="utf-8")
    assert ".simplify-jobs-shadow-root" in supported
    assert "Autofill This Page" in supported
    assert "Continue Application" in supported


# ---------------------------------------------------------------------------
# SimplifyBoundary.decide Cases
# ---------------------------------------------------------------------------


def test_decide_ready_enabled_autofill_preferred():
    """Ready status with enabled autofill control prefers autofill."""
    cls = get_boundary_cls()
    obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "fp_step1_unfilled",
        "panel": True,
        "status": "ready",
        "controls": {
            "autofill": {"ref": "btn-auto-1", "enabled": True},
            "continue": {"ref": "btn-cont-1", "enabled": False},
        },
        "source": "observed_dom",
    }
    decision = cls.decide(obs, already_attempted=False)
    assert decision["action"] == "autofill"
    assert "autofill" in decision.get("reason", "").lower() or "ready" in decision.get("reason", "").lower()


def test_decide_complete_enabled_continue_chosen():
    """Complete status with enabled continue control chooses continue."""
    cls = get_boundary_cls()
    obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "fp_step1_filled",
        "panel": True,
        "status": "complete",
        "controls": {
            "autofill": {"ref": "btn-auto-1", "enabled": False},
            "continue": {"ref": "btn-cont-1", "enabled": True},
        },
        "source": "observed_dom",
    }
    decision = cls.decide(obs, already_attempted=False)
    assert decision["action"] == "continue"
    assert "continue" in decision.get("reason", "").lower() or "complete" in decision.get("reason", "").lower()


def test_decide_needs_review_reviews_residuals_not_skipping():
    """needs_review directs operator/worker to review residuals rather than skipping."""
    cls = get_boundary_cls()
    obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "fp_step1_partial",
        "panel": True,
        "status": "needs_review",
        "controls": {
            "autofill": {"ref": "btn-auto-1", "enabled": False},
            "continue": {"ref": "btn-cont-1", "enabled": False},
        },
        "source": "observed_dom",
    }
    decision = cls.decide(obs, already_attempted=False)
    assert decision["action"] in ("review", "needs_review")
    assert decision["action"] != "skip"
    assert any(k in decision.get("reason", "").lower() for k in ("review", "residual", "manual"))


@pytest.mark.parametrize("status", ["unsupported", "missing", "login_required"])
def test_decide_unsupported_missing_login_required_explicit_fallback(status):
    """Unsupported, missing panel, or login_required produces explicit fallback reason with no writer."""
    cls = get_boundary_cls()
    obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "fp_plain",
        "panel": status != "missing",
        "status": status,
        "controls": {
            "autofill": {"ref": None, "enabled": False},
            "continue": {"ref": None, "enabled": False},
        },
        "source": "observed_dom",
    }
    decision = cls.decide(obs, already_attempted=False)
    assert decision["action"] in ("fallback", "skip", "native")
    reason = decision.get("reason", "").lower()
    assert status in reason or status.replace("_", " ") in reason or "fallback" in reason


def test_decide_no_inference_that_all_controls_available_means_complete():
    """Availability of all controls must not cause automatic inference that application is complete."""
    cls = get_boundary_cls()
    obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "fp_step1_initial",
        "panel": True,
        "status": "ready",
        "controls": {
            "autofill": {"ref": "btn-auto-1", "enabled": True},
            "continue": {"ref": "btn-cont-1", "enabled": True},
        },
        "source": "observed_dom",
    }
    decision = cls.decide(obs, already_attempted=False)
    assert decision["action"] != "complete"
    assert decision["action"] == "continue"
    assert obs["status"] == "ready"


def test_decide_auth_and_final_submission_not_part_of_helper():
    """Helper must never decide to perform auth or final application submission."""
    cls = get_boundary_cls()
    for status in ("login_required", "complete", "ready"):
        obs = {
            "url": "https://careers.example.test/apply",
            "fingerprint": "fp_step1",
            "panel": True,
            "status": status,
            "controls": {
                "autofill": {"ref": "b1", "enabled": True},
                "continue": {"ref": "b2", "enabled": True},
            },
            "source": "observed_dom",
        }
        decision = cls.decide(obs, already_attempted=False)
        assert decision["action"] not in ("submit", "final_submit", "login", "authenticate")


def test_decide_already_attempted_prevents_autofill_loop():
    """When autofill has already been attempted on current page, decide prevents infinite autofill loop."""
    cls = get_boundary_cls()
    obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "fp_step1",
        "panel": True,
        "status": "ready",
        "controls": {
            "autofill": {"ref": "b1", "enabled": True},
            "continue": {"ref": "b2", "enabled": False},
        },
        "source": "observed_dom",
    }
    decision = cls.decide(obs, already_attempted=True)
    assert decision["action"] != "autofill"


# ---------------------------------------------------------------------------
# SimplifyBoundary.observe and perform Cases
# ---------------------------------------------------------------------------


def test_observe_returns_sanitized_shape_and_no_field_values_in_fingerprint():
    """observe calls evaluate marker 'jobbot:simplify:observe' and returns sanitized shape."""
    cls = get_boundary_cls()
    raw_obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "sha256_semantic_form_state_no_values",
        "panel": True,
        "status": "ready",
        "controls": {
            "autofill": {"ref": "btn-auto-1", "enabled": True},
            "continue": {"ref": "btn-cont-1", "enabled": False},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(observation=raw_obs)
    boundary = cls(port)
    obs = asyncio.run(boundary.observe())

    assert any("jobbot:simplify:observe" in s for s, _ in port.evaluations)
    assert obs["url"] == "https://careers.example.test/apply"
    assert obs["fingerprint"] == "sha256_semantic_form_state_no_values"
    assert obs["panel"] is True
    assert obs["status"] == "ready"
    assert "autofill" in obs["controls"]
    assert "continue" in obs["controls"]
    assert obs["source"] in ("fixture", "observed_dom")
    assert "candidate" not in obs["fingerprint"].lower()


def test_perform_autofill_success_releases_writer_idle():
    """Successful autofill triggers click script marker with ref/url, releases writer as idle with changed=True."""
    cls = get_boundary_cls()
    initial_obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "fp_empty",
        "panel": True,
        "status": "ready",
        "controls": {
            "autofill": {"ref": "btn-auto-1", "enabled": True},
            "continue": {"ref": "btn-cont-1", "enabled": False},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(observation=initial_obs, url="https://careers.example.test/apply")

    def on_click(arg):
        assert arg["ref"] == "btn-auto-1"
        assert arg["url"] == "https://careers.example.test/apply"
        port.observation = {
            "url": "https://careers.example.test/apply",
            "fingerprint": "fp_filled_fields",
            "panel": True,
            "status": "complete",
            "controls": {
                "autofill": {"ref": "btn-auto-1", "enabled": False},
                "continue": {"ref": "btn-cont-1", "enabled": True},
            },
            "source": "observed_dom",
        }
        return {"status": "ok"}

    port._on_click = on_click
    time_sim = FakeClockSleeper()
    boundary = cls(port, budget_seconds=45, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    result = asyncio.run(boundary.perform("autofill"))

    click_calls = [(s, a) for s, a in port.evaluations if "jobbot:simplify:click" in s]
    assert len(click_calls) == 1
    assert click_calls[0][1]["ref"] == "btn-auto-1"
    assert click_calls[0][1]["url"] == "https://careers.example.test/apply"

    assert result["changed"] is True
    assert result["writer_state"] == "idle"
    assert result["status"] in ("complete", "ready", "needs_review")
    assert "reason" in result


def test_perform_unchanged_fingerprint_yields_changed_false():
    """Autofill where form fingerprint does not change yields changed=False."""
    cls = get_boundary_cls()
    initial_obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "fp_same",
        "panel": True,
        "status": "ready",
        "controls": {
            "autofill": {"ref": "btn-auto-1", "enabled": True},
            "continue": {"ref": "btn-cont-1", "enabled": False},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(observation=initial_obs, url="https://careers.example.test/apply")

    def on_click(arg):
        port.observation = dict(initial_obs, status="complete")
        return {"status": "ok"}

    port._on_click = on_click
    time_sim = FakeClockSleeper()
    boundary = cls(port, budget_seconds=45, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    result = asyncio.run(boundary.perform("autofill"))
    assert result["changed"] is False
    assert result["writer_state"] == "idle"


def test_perform_disabled_control_not_clicked():
    """Disabled control is not clicked and does not invoke click script marker."""
    cls = get_boundary_cls()
    initial_obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "fp_disabled",
        "panel": True,
        "status": "unsupported",
        "controls": {
            "autofill": {"ref": "btn-auto-1", "enabled": False},
            "continue": {"ref": "btn-cont-1", "enabled": False},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(observation=initial_obs)
    time_sim = FakeClockSleeper()
    boundary = cls(port, budget_seconds=45, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    result = asyncio.run(boundary.perform("autofill"))
    assert len(port.clicks) == 0
    assert result["changed"] is False
    assert result["writer_state"] == "idle"
    assert "disabled" in result.get("reason", "").lower() or "not available" in result.get("reason", "").lower()


def test_perform_navigation_invalidates_prior_refs_requires_fresh_rediscovery():
    """Navigation invalidates prior refs; stale ref from prior page must not be clicked."""
    cls = get_boundary_cls()
    initial_obs = {
        "url": "https://careers.example.test/apply/page1",
        "fingerprint": "fp_page1",
        "panel": True,
        "status": "ready",
        "controls": {
            "autofill": {"ref": "btn-page1-auto", "enabled": True},
            "continue": {"ref": "btn-page1-cont", "enabled": False},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(observation=initial_obs, url="https://careers.example.test/apply/page1")
    time_sim = FakeClockSleeper()
    boundary = cls(port, budget_seconds=45, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    obs1 = asyncio.run(boundary.observe())
    assert obs1["controls"]["autofill"]["ref"] == "btn-page1-auto"

    port.url = "https://careers.example.test/apply/page2"
    port.observation = {
        "url": "https://careers.example.test/apply/page2",
        "fingerprint": "fp_page2",
        "panel": True,
        "status": "ready",
        "controls": {
            "autofill": {"ref": "btn-page2-auto", "enabled": True},
            "continue": {"ref": "btn-page2-cont", "enabled": False},
        },
        "source": "observed_dom",
    }

    def on_click(arg):
        if arg["ref"] == "btn-page1-auto" or arg["url"] != "https://careers.example.test/apply/page2":
            raise ValueError("Stale ref or wrong url clicked!")
        return {"status": "ok"}

    port._on_click = on_click
    asyncio.run(boundary.perform("autofill"))
    for click in port.clicks:
        assert click["ref"] != "btn-page1-auto"
        assert click["url"] == "https://careers.example.test/apply/page2"


def test_perform_timeout_returns_unknown_writer_and_no_native_takeover():
    """Active autofill timing out returns unknown writer and NO concurrent native takeover authorization."""
    cls = get_boundary_cls()
    active_obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "fp_stuck",
        "panel": True,
        "status": "active",
        "controls": {
            "autofill": {"ref": "btn-auto-1", "enabled": False},
            "continue": {"ref": "btn-cont-1", "enabled": False},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(observation=active_obs)
    time_sim = FakeClockSleeper()
    boundary = cls(port, budget_seconds=45, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    result = asyncio.run(boundary.perform("autofill"))
    assert result["writer_state"] == "unknown"
    assert result["changed"] is False
    assert result.get("native_takeover_authorized") is not True
    assert "timeout" in result.get("reason", "").lower() or "budget" in result.get("reason", "").lower()


def test_perform_continue_operation():
    """Continue operation clicks continue control and reports resulting state."""
    cls = get_boundary_cls()
    complete_obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "fp_step1_done",
        "panel": True,
        "status": "complete",
        "controls": {
            "autofill": {"ref": "btn-auto-1", "enabled": False},
            "continue": {"ref": "btn-cont-1", "enabled": True},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(observation=complete_obs)

    def on_click(arg):
        assert arg["ref"] == "btn-cont-1"
        port.observation = {
            "url": "https://careers.example.test/apply/step2",
            "fingerprint": "fp_step2_heading_changed",
            "panel": True,
            "status": "ready",
            "controls": {
                "autofill": {"ref": "btn-step2-auto", "enabled": True},
                "continue": {"ref": "btn-step2-cont", "enabled": False},
            },
            "source": "observed_dom",
        }
        return {"status": "ok"}

    port._on_click = on_click
    time_sim = FakeClockSleeper()
    boundary = cls(port, budget_seconds=45, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)

    result = asyncio.run(boundary.perform("continue"))
    assert result["changed"] is True
    assert result["writer_state"] == "idle"


def test_perform_invalid_operation_rejected():
    """Operations other than 'autofill' and 'continue' must be rejected."""
    cls = get_boundary_cls()
    port = DOMSeamPort()
    boundary = cls(port)
    with pytest.raises((ValueError, KeyError)):
        asyncio.run(boundary.perform("submit"))


def test_perform_result_exposes_required_shape_no_blanket_correctness_claim():
    """Result exposes status, changed bool, writer_state, reason, with no blanket correctness claims."""
    cls = get_boundary_cls()
    obs = {
        "url": "https://careers.example.test/apply",
        "fingerprint": "fp_init",
        "panel": True,
        "status": "ready",
        "controls": {
            "autofill": {"ref": "b1", "enabled": True},
            "continue": {"ref": "b2", "enabled": False},
        },
        "source": "observed_dom",
    }
    port = DOMSeamPort(observation=obs)
    time_sim = FakeClockSleeper()
    boundary = cls(port, budget_seconds=45, poll_seconds=0.1, clock=time_sim.clock, sleeper=time_sim.sleep)
    result = asyncio.run(boundary.perform("autofill"))

    assert "status" in result and isinstance(result["status"], str)
    assert "changed" in result and isinstance(result["changed"], bool)
    assert result["writer_state"] in ("idle", "active", "unknown")
    assert "reason" in result and isinstance(result["reason"], str)
    assert "all_fields_correct" not in result
    assert "fields_verified" not in result
    assert result.get("correct") is not True


# ---------------------------------------------------------------------------
# Service-Level Single-Writer Regression Cases (Expected RED)
# ---------------------------------------------------------------------------


def test_service_action_start_defaults_to_writes_browser_true(tmp_path):
    """Service action_start gains writes_browser=True default."""
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    act = s.action_start(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        action_id='act-w1',
        tool_name='click',
    )
    assert act.get('writes_browser') is True or act.get('writes_browser') == 1


def test_service_rejects_concurrent_browser_writing_actions(tmp_path):
    """While a browser-writing action is open, another writing action is rejected;

    read-only action with writes_browser=False is allowed.
    """
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    # Open first writing action (default writes_browser=True)
    s.action_start(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        action_id='act-w1',
        tool_name='fill',
        writes_browser=True,
    )

    # Second writing action while first writing action is open must be rejected
    with pytest.raises(ProtocolError):
        s.action_start(
            a['id'],
            worker_id='worker',
            fence=a['fence'],
            action_id='act-w2',
            tool_name='click',
            writes_browser=True,
        )

    # Read-only action with writes_browser=False is allowed concurrently
    ro = s.action_start(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        action_id='act-ro1',
        tool_name='observe_dom',
        writes_browser=False,
    )
    assert ro['id'] == 'act-ro1'
    assert ro.get('writes_browser') is False or ro.get('writes_browser') == 0


def test_service_rejects_writing_action_when_writer_state_active_or_unknown(tmp_path):
    """While writer_state active/unknown, writing action rejected but read-only observation allowed."""
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    # 1. When writer_state is active
    s.writer_state(a['id'], worker_id='worker', fence=a['fence'], state='active')

    with pytest.raises(ProtocolError):
        s.action_start(
            a['id'],
            worker_id='worker',
            fence=a['fence'],
            action_id='act-w-active',
            tool_name='fill',
            writes_browser=True,
        )

    ro1 = s.action_start(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        action_id='act-ro-active',
        tool_name='observe',
        writes_browser=False,
    )
    assert ro1['id'] == 'act-ro-active'
    s.action_end(a['id'], worker_id='worker', fence=a['fence'], action_id='act-ro-active', status='success')

    # 2. When writer_state is unknown
    s.writer_state(a['id'], worker_id='worker', fence=a['fence'], state='unknown')

    with pytest.raises(ProtocolError):
        s.action_start(
            a['id'],
            worker_id='worker',
            fence=a['fence'],
            action_id='act-w-unknown',
            tool_name='fill',
            writes_browser=True,
        )

    ro2 = s.action_start(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        action_id='act-ro-unknown',
        tool_name='observe',
        writes_browser=False,
    )
    assert ro2['id'] == 'act-ro-unknown'
    s.action_end(a['id'], worker_id='worker', fence=a['fence'], action_id='act-ro-unknown', status='success')


def test_service_allows_writing_after_idle_and_actions_ended(tmp_path):
    """After confirmed idle and previous writer action ended, writing allowed."""
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    s.action_start(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        action_id='act-prev',
        tool_name='fill',
        writes_browser=True,
    )
    s.action_end(a['id'], worker_id='worker', fence=a['fence'], action_id='act-prev', status='success')

    s.writer_state(a['id'], worker_id='worker', fence=a['fence'], state='idle')

    w = s.action_start(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        action_id='act-new-writer',
        tool_name='click',
        writes_browser=True,
    )
    assert w['id'] == 'act-new-writer'
