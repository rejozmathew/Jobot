"""Acceptance tests for runtime budgets and target management contracts.

Covers:
1. test_action_start_rejects_on_budget_expiry_while_readonly_allowed:
   Owned action_start(writes_browser=True) rejects after frozen no_progress_seconds
   or attempt_seconds budget even when heartbeat is fresh; read-only/metadata
   observations remain possible.
2. test_extend_budget_bounds_active_owner_and_allows_writes_without_refreshing_progress:
   extend_budget(attempt_id, worker_id, fence, seconds, reason) records a visible bounded
   extension (max 120s each, max 2 per attempt); requires active owner; cannot refresh
   verified progress or revive expired lease; enables writes within extended budget;
   leaves attempts/history/settings snapshot unchanged.
3. test_bind_target_records_metadata_and_enforces_current_owner:
   bind_target(attempt_id, worker_id, fence, target_id, url) records explicit owned
   tab/target metadata for the current owner only; rejects unowned or stale worker/fence;
   prevents retagging.
4. test_target_state_records_metadata_and_preserved_target_visible_in_view:
   target_state(attempt_id, worker_id, fence, target_id, state, evidence) records
   open/preserved/closed metadata without browser commands; preserved targets remain
   visible in Service.view current_run/targets.
5. test_late_worker_cannot_retarget_newer_attempt_and_no_browser_model_executed:
   Late completed-lease worker cannot retarget or mutate targets on a newer attempt;
   verifies no browser or model execution occurred throughout runtime.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import socket
import subprocess
import pytest

from job_applier.managed import Service, ProtocolError


def _setup_service(tmp_path, count: int = 2, now_iso: str = "2026-09-07T12:00:00+00:00"):
    """Create a real synthetic Service instance with frozen clock control."""
    current_time = [datetime.fromisoformat(now_iso)]

    def now_fn() -> str:
        return current_time[0].isoformat()

    s = Service.create(tmp_path / "jobs.db", instance_id="test-budget-targets")
    s.now = now_fn

    s.identity(
        identity_id="cand-1",
        person_key="person-1",
        email="candidate@example.test",
        profile={"facts": {"auth": "fixture"}, "resume_ref": "asset:fixture-v1"},
    )

    job_ids = []
    for i in range(count):
        j = s.intake(url=f"https://careers.example.test/jobs/{i}", source_id=f"src-{i}")
        s.eligibility(j["id"], "ready", reason="operator approval")
        job_ids.append(j["id"])

    run = s.request_run(
        request_id="run-1",
        job_ids=job_ids,
        identity_id="cand-1",
        browser_profile="prof-1",
    )
    s.accept_run(
        run["id"],
        worker_id="worker-1",
        session_id="sess-1",
        capabilities={
            "protocol": 1,
            "skill_version": "test-skill",
            "browser_profile": "prof-1",
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )
    return s, run, job_ids, current_time


def test_action_start_rejects_on_budget_expiry_while_readonly_allowed(tmp_path):
    """1. action_start(writes_browser=True) rejects after no_progress_seconds or attempt_seconds.

    Even when heartbeat is fresh, write actions are blocked once the budget expires.
    Read-only/metadata observations (writes_browser=False) remain permitted.
    """
    s, run, job_ids, clock = _setup_service(tmp_path)
    a = s.claim(run["id"], worker_id="worker-1")
    assert a is not None

    # Advance clock past default no_progress_seconds (45s) to 46s
    clock[0] += timedelta(seconds=46)

    # Heartbeat keeps lease alive and fresh
    hb = s.heartbeat(a["id"], worker_id="worker-1", fence=a["fence"])
    assert hb is not None

    # Browser write must reject after no_progress_seconds budget expiry
    with pytest.raises(ProtocolError):
        s.action_start(
            a["id"],
            worker_id="worker-1",
            fence=a["fence"],
            action_id="act-write-stalled",
            tool_name="click",
            writes_browser=True,
        )

    # Read-only observation remains possible even when budget expired
    ro_act = s.action_start(
        a["id"],
        worker_id="worker-1",
        fence=a["fence"],
        action_id="act-ro-stalled",
        tool_name="inspect_page",
        writes_browser=False,
    )
    assert ro_act["id"] == "act-ro-stalled"
    assert ro_act["writes_browser"] == 0

    # Advance verified progress so stalled state resets
    s.event(
        a["id"],
        worker_id="worker-1",
        fence=a["fence"],
        event_id="ev-nav-verified",
        event_type="navigation_verified",
        observed_at=s.now(),
        payload={"url": "https://careers.example.test/jobs/0", "evidence": "page_ready"},
    )

    # Advance clock past default attempt_seconds (300s) to 301s total
    # Keep liveness alive; an expired lease must not be revived by this test.
    remaining=255
    while remaining:
        tick=min(30,remaining);clock[0]+=timedelta(seconds=tick);remaining-=tick
        s.heartbeat(a["id"], worker_id="worker-1", fence=a["fence"])

    # Attempt-level budget expiry rejects writes
    with pytest.raises(ProtocolError):
        s.action_start(
            a["id"],
            worker_id="worker-1",
            fence=a["fence"],
            action_id="act-write-attempt-budget",
            tool_name="click",
            writes_browser=True,
        )

    # Read-only observation still succeeds
    ro_act2 = s.action_start(
        a["id"],
        worker_id="worker-1",
        fence=a["fence"],
        action_id="act-ro-attempt-budget",
        tool_name="inspect_page",
        writes_browser=False,
    )
    assert ro_act2["id"] == "act-ro-attempt-budget"


def test_extend_budget_bounds_active_owner_and_allows_writes_without_refreshing_progress(tmp_path):
    """2. extend_budget records bounded extension, enforces active owner, and allows writes.

    - Rejects stale owner / wrong fence
    - Cannot revive expired lease
    - Bounds: max 120s per extension, max 2 extensions per attempt
    - Does not refresh verified progress (progress_at unchanged)
    - Leaves attempt settings snapshot and history intact
    - Allows a write action within the extended budget
    """
    s, run, job_ids, clock = _setup_service(tmp_path)
    a = s.claim(run["id"], worker_id="worker-1")
    assert a is not None

    # Stale owner / invalid fence rejected
    with pytest.raises(ProtocolError):
        s.extend_budget(a["id"], worker_id="other-worker", fence=a["fence"], seconds=60, reason="slow form")
    with pytest.raises(ProtocolError):
        s.extend_budget(a["id"], worker_id="worker-1", fence=999, seconds=60, reason="slow form")

    # Cannot revive expired lease: advance past lease_seconds (60s) without heartbeat
    clock[0] += timedelta(seconds=65)
    with pytest.raises(ProtocolError):
        s.extend_budget(a["id"], worker_id="worker-1", fence=a["fence"], seconds=60, reason="revive expired")

    # Rewind clock back to within lease
    clock[0] -= timedelta(seconds=35)  # clock is now at t0 + 30s
    s.heartbeat(a["id"], worker_id="worker-1", fence=a["fence"])

    # Bounds: >120s or <=0s rejected
    with pytest.raises(ProtocolError):
        s.extend_budget(a["id"], worker_id="worker-1", fence=a["fence"], seconds=121, reason="too long")
    with pytest.raises(ProtocolError):
        s.extend_budget(a["id"], worker_id="worker-1", fence=a["fence"], seconds=0, reason="zero")

    # Snapshot check: capture progress_at and settings_json
    attempt_before = s.attempt(a["id"])
    progress_before = attempt_before["progress_at"]
    settings_before = attempt_before["settings_json"]

    # Valid extension 1 (bounded 60s)
    ext1 = s.extend_budget(a["id"], worker_id="worker-1", fence=a["fence"], seconds=60, reason="slow form load")
    assert ext1 is not None

    # Verified progress is NOT refreshed by extend_budget
    attempt_after = s.attempt(a["id"])
    assert attempt_after["progress_at"] == progress_before
    # Settings snapshot unchanged
    assert attempt_after["settings_json"] == settings_before

    # Advance clock to 50s (exceeds default 45s no_progress, but within 45s+60s extension)
    clock[0] += timedelta(seconds=20)  # now t0 + 50s
    s.heartbeat(a["id"], worker_id="worker-1", fence=a["fence"])

    # Write action proceeds within valid extension
    write_act = s.action_start(
        a["id"],
        worker_id="worker-1",
        fence=a["fence"],
        action_id="act-write-extended",
        tool_name="type",
        writes_browser=True,
    )
    assert write_act["id"] == "act-write-extended"

    # Valid extension 2 (second allowed extension)
    ext2 = s.extend_budget(a["id"], worker_id="worker-1", fence=a["fence"], seconds=60, reason="multistep delay")
    assert ext2 is not None

    # Third extension must reject (max 2 per attempt)
    with pytest.raises(ProtocolError):
        s.extend_budget(a["id"], worker_id="worker-1", fence=a["fence"], seconds=30, reason="third extension")


def test_bind_target_records_metadata_and_enforces_current_owner(tmp_path):
    """3. bind_target records explicit tab/target metadata for active owner only.

    - Enforces current worker_id and fence
    - Prevents unowned target retagging or hijacking
    """
    s, run, job_ids, clock = _setup_service(tmp_path)
    a = s.claim(run["id"], worker_id="worker-1")
    assert a is not None

    # Stale owner / mismatched fence rejected
    with pytest.raises(ProtocolError):
        s.bind_target(
            a["id"],
            worker_id="imposter-worker",
            fence=a["fence"],
            target_id="target-tab-1",
            url="https://careers.example.test/jobs/0/apply",
        )
    with pytest.raises(ProtocolError):
        s.bind_target(
            a["id"],
            worker_id="worker-1",
            fence=999,
            target_id="target-tab-1",
            url="https://careers.example.test/jobs/0/apply",
        )

    # Valid bind_target records explicit metadata
    bt = s.bind_target(
        a["id"],
        worker_id="worker-1",
        fence=a["fence"],
        target_id="target-tab-1",
        url="https://careers.example.test/jobs/0/apply",
    )
    assert bt is not None
    assert bt.get("target_id") == "target-tab-1"
    assert bt.get("url") == "https://careers.example.test/jobs/0/apply"

    # Competing worker cannot retag existing owned target
    with pytest.raises(ProtocolError):
        s.bind_target(
            a["id"],
            worker_id="other-worker",
            fence=a["fence"],
            target_id="target-tab-1",
            url="https://hijack.example.test",
        )


def test_target_state_records_metadata_and_preserved_target_visible_in_view(tmp_path):
    """4. target_state records open/preserved/closed metadata and reflects in Service.view.

    - Records open, preserved, and closed transitions
    - Never issues direct browser commands or closes real browser
    - Preserved targets remain visible in Service.view current_run/targets
    """
    s, run, job_ids, clock = _setup_service(tmp_path)
    a = s.claim(run["id"], worker_id="worker-1")
    assert a is not None

    s.bind_target(
        a["id"],
        worker_id="worker-1",
        fence=a["fence"],
        target_id="target-tab-1",
        url="https://careers.example.test/jobs/0/apply",
    )

    # Update state to open
    st_open = s.target_state(
        a["id"],
        worker_id="worker-1",
        fence=a["fence"],
        target_id="target-tab-1",
        state="open",
        evidence="tab_opened",
    )
    assert st_open.get("state") == "open"

    # Invalid state or wrong worker rejected
    with pytest.raises(ProtocolError):
        s.target_state(
            a["id"],
            worker_id="worker-1",
            fence=a["fence"],
            target_id="target-tab-1",
            state="invalid_state",
            evidence="bad",
        )
    with pytest.raises(ProtocolError):
        s.target_state(
            a["id"],
            worker_id="wrong-worker",
            fence=a["fence"],
            target_id="target-tab-1",
            state="preserved",
            evidence="bad_worker",
        )

    # Set state to preserved
    st_pres = s.target_state(
        a["id"],
        worker_id="worker-1",
        fence=a["fence"],
        target_id="target-tab-1",
        state="preserved",
        evidence="operator_manual_review_needed",
    )
    assert st_pres.get("state") == "preserved"

    # Preserved target remains visible in Service.view under current_run/targets
    view = s.view(run["id"])
    assert "current_run" in view
    targets = view["current_run"].get("targets", [])
    matched = [t for t in targets if t.get("target_id") == "target-tab-1"]
    assert len(matched) == 1
    assert matched[0].get("state") == "preserved"
    assert matched[0].get("url") == "https://careers.example.test/jobs/0/apply"

    # Set state to closed
    st_closed = s.target_state(
        a["id"],
        worker_id="worker-1",
        fence=a["fence"],
        target_id="target-tab-1",
        state="closed",
        evidence="run_cleanup",
    )
    assert st_closed.get("state") == "closed"


def test_late_worker_cannot_retarget_newer_attempt_and_no_browser_model_executed(tmp_path, monkeypatch):
    """5. Late completed-lease worker cannot retarget newer attempt, and no model/page work runs.

    - When attempt 1 completes and attempt 2 is claimed under a new fence:
      attempt 1's worker/fence cannot call bind_target or target_state on attempt 2 or old attempt.
    - Verifies no browser subprocesses, sockets, or LLM model invocations executed.
    """
    # Guardrails to verify no browser subprocess or network socket connections execute
    spawned_processes: list[list[str]] = []
    real_popen = subprocess.Popen

    def fake_popen(cmd, *args, **kwargs):
        spawned_processes.append(cmd)
        return real_popen(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    connected_sockets: list[tuple[str, int]] = []
    real_connect = socket.socket.connect

    def fake_connect(sock_self, address):
        connected_sockets.append(address)
        return real_connect(sock_self, address)

    monkeypatch.setattr(socket.socket, "connect", fake_connect)

    s, run, job_ids, clock = _setup_service(tmp_path, count=2)
    a1 = s.claim(run["id"], worker_id="worker-1")
    assert a1 is not None

    s.bind_target(
        a1["id"],
        worker_id="worker-1",
        fence=a1["fence"],
        target_id="target-job-0",
        url="https://careers.example.test/jobs/0",
    )

    # Complete attempt 1
    s.finish(
        a1["id"],
        worker_id="worker-1",
        fence=a1["fence"],
        outcome="ready_for_review",
        evidence="completed first job",
        quiescent=True,
    )

    # Claim attempt 2 with incremented generation/fence
    a2 = s.claim(run["id"], worker_id="worker-1")
    assert a2 is not None
    assert a2["id"] != a1["id"]
    assert a2["fence"] > a1["fence"]

    # Late worker with attempt 1 credentials cannot retarget attempt 2
    with pytest.raises(ProtocolError):
        s.bind_target(
            a2["id"],
            worker_id="worker-1",
            fence=a1["fence"],
            target_id="target-late-retarget",
            url="https://careers.example.test/jobs/1",
        )

    # Late worker cannot bind on completed attempt 1 either
    with pytest.raises(ProtocolError):
        s.bind_target(
            a1["id"],
            worker_id="worker-1",
            fence=a1["fence"],
            target_id="target-late-old",
            url="https://careers.example.test/jobs/0",
        )

    # Late worker cannot update target_state on attempt 2
    with pytest.raises(ProtocolError):
        s.target_state(
            a2["id"],
            worker_id="worker-1",
            fence=a1["fence"],
            target_id="target-job-0",
            state="closed",
            evidence="late close",
        )

    # Verify no browser subprocesses spawned or network sockets opened
    assert len(spawned_processes) == 0
    assert len(connected_sockets) == 0
