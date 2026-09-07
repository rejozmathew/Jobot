"""Reviewer regression tests for JobBot lifecycle and control contracts.

Regressions covered:
L1: Quarantined attempt on one browser profile must prevent reclaiming the selected job
    through another browser profile (request_run or claim must reject with ProtocolError;
    attempt count must not increase).
L4: Submit-enabled PILOT fixture acknowledges pause/stop; subsequent submission_intent
    must reject with ProtocolError and no change to submit_intent_at.
L5: Idle pause before first claim / between attempts must be recoverable via ack_run_control:
    quiescent=False must reject; active lease / active attempt must reject; idle pause
    returns paused/stopped, and control(resume) successfully recovers to running.
L6: Old progress event timestamp with timezone offset (e.g. +09:00), whose absolute instant
    is older than recorded progress, must not refresh progress_at (preventing lexicographical
    string comparisons from corrupting timestamps).
L7: Replay of same-result operator reconcile (failed, blocked, interrupted) with same evidence
    and quiescent=True after clock advance must return original result, timestamps, and
    duration without reset by transport retries.
"""
from datetime import datetime, timezone, timedelta
import pytest

from job_applier.managed import Service, ProtocolError


def ready(tmp_path, count=1, settings=None, browser_profile="fixture-browser"):
    s = Service.create(tmp_path / "jobs.db", instance_id="test", settings=settings)
    s.identity(
        identity_id="candidate",
        person_key="person",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "fixture"}, "resume_ref": "asset:fixture-v1"},
    )
    ids = []
    for i in range(count):
        job = s.intake(url=f"https://careers.example.test/jobs/{i}", source_id=str(i))
        s.eligibility(job["id"], "ready", reason="synthetic operator approval")
        ids.append(job["id"])
    r = s.request_run(
        request_id="request-1",
        job_ids=ids,
        identity_id="candidate",
        browser_profile=browser_profile,
    )
    return s, r, ids


def accept(s, r, worker="worker", session_id="session-1"):
    return s.accept_run(
        r["id"],
        worker_id=worker,
        session_id=session_id,
        capabilities={
            "protocol": 1,
            "skill_version": "test-skill",
            "browser_profile": r["browser_profile"],
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )


def test_L1_blocked_attempt_quarantine_prevents_reclaim_via_other_browser_profile(tmp_path):
    """L1: Blocked attempt finished quiescent=False creates quarantine;

    selected job must not be reclaimed through another browser_profile.
    request_run OR claim may reject ProtocolError; ensure attempt count does not increase.
    """
    s, r, ids = ready(tmp_path, count=1, browser_profile="profile-a")
    accept(s, r)
    a = s.claim(r["id"], worker_id="worker")
    job_id = ids[0]

    # Finish with outcome='blocked' and quiescent=False -> creates quarantine on profile-a lease
    fin = s.finish(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        outcome="blocked",
        evidence="blocked by anti-bot captcha",
        quiescent=False,
    )
    assert fin["outcome"] == "blocked"

    # Verify browser_leases shows quarantined state for profile-a
    with s.tx() as db:
        lease = db.execute("SELECT * FROM browser_leases WHERE profile=?", ("profile-a",)).fetchone()
        assert lease is not None
        assert lease["state"] == "quarantined"

    # Attempt to reclaim the same job via a different browser profile
    reclaimed = False
    try:
        r2 = s.request_run(
            request_id="request-reclaim-alternate",
            job_ids=[job_id],
            identity_id="candidate",
            browser_profile="profile-b",
        )
        accept(s, r2)
        s.claim(r2["id"], worker_id="worker")
        reclaimed = True
    except ProtocolError:
        reclaimed = False

    assert not reclaimed, "Quarantined job must not be reclaimed through another browser profile"

    # Ensure attempt count for this job did not increase
    with s.tx() as db:
        count = db.execute(
            "SELECT count(*) FROM application_attempts WHERE job_id=?",
            (job_id,),
        ).fetchone()[0]
    assert count == 1, f"Attempt count must remain 1, found {count}"


@pytest.mark.parametrize("command", ["pause", "stop"])
def test_L4_pilot_submission_intent_rejected_after_acknowledged_control(tmp_path, command):
    """L4: Submit-enabled PILOT fixture (settings={'mode':'pilot','submission_mode':'submit'})

    acknowledges pause/stop; subsequent submission_intent must reject with ProtocolError
    and no submitted_at / submit_intent_at change.
    """
    pilot_settings = {"mode": "pilot", "submission_mode": "submit"}
    s, r, ids = ready(tmp_path, count=1, settings=pilot_settings)
    accept(s, r)
    a = s.claim(r["id"], worker_id="worker")

    # Set writer state to idle so ack_control can succeed
    s.writer_state(a["id"], worker_id="worker", fence=a["fence"], state="idle")

    # Operator requests pause or stop
    s.control(r["id"], command=command)

    # Worker acknowledges the control
    ack = s.ack_control(a["id"], worker_id="worker", fence=a["fence"], quiescent=True)
    expected_control = "paused" if command == "pause" else "stopped"
    assert ack["control"] == expected_control

    # submission_intent must reject with ProtocolError
    with pytest.raises(ProtocolError):
        s.submission_intent(
            a["id"],
            worker_id="worker",
            fence=a["fence"],
            evidence="pilot submission verification intent",
        )

    # submit_intent_at must not be changed / remain None
    attempt = s.attempt(a["id"])
    assert attempt["submit_intent_at"] is None, "submit_intent_at must remain None after rejected submission_intent"


@pytest.mark.parametrize("timing", ["before_first_claim", "between_attempts"])
def test_L5_idle_run_control_recoverability(tmp_path, timing):
    """L5: Idle pause before first claim / between attempts must be recoverable:

    new service method ack_run_control(run_id, worker_id='worker', quiescent=True)
    returns paused/stopped only when no active/quarantined lease or active attempt;
    then control(resume) works if paused. quiescent=False must reject.
    """
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)

    if timing == "between_attempts":
        # Claim first attempt and finish cleanly to return to idle between attempts
        a = s.claim(r["id"], worker_id="worker")
        s.writer_state(a["id"], worker_id="worker", fence=a["fence"], state="idle")
        s.finish(
            a["id"],
            worker_id="worker",
            fence=a["fence"],
            outcome="ready_for_review",
            evidence="attempt 1 review",
            quiescent=True,
        )
        with s.tx() as db:
            lease = db.execute("SELECT * FROM browser_leases WHERE profile=?", (r["browser_profile"],)).fetchone()
            assert lease["state"] == "released"

    # Operator requests pause while run is idle
    s.control(r["id"], command="pause")

    # quiescent=False must reject
    with pytest.raises(ProtocolError):
        s.ack_run_control(r["id"], worker_id="worker", quiescent=False)

    # quiescent=True acknowledges idle run control
    ack_res = s.ack_run_control(r["id"], worker_id="worker", quiescent=True)
    assert ack_res["control"] == "paused"

    # Resuming from paused must work
    resumed = s.control(r["id"], command="resume")
    assert resumed["control"] == "running"

    # Worker can now claim the next attempt
    claimed = s.claim(r["id"], worker_id="worker")
    expected_job = ids[0] if timing == "before_first_claim" else ids[1]
    assert claimed["job_id"] == expected_job


def test_L5_ack_run_control_rejects_when_lease_active_or_quarantined(tmp_path):
    """L5 rejection: ack_run_control must reject when an active or quarantined lease

    or active attempt exists.
    """
    s, r, ids = ready(tmp_path, count=1)
    accept(s, r)
    a = s.claim(r["id"], worker_id="worker")

    # 1. Active attempt & lease: ack_run_control must reject
    s.control(r["id"], command="pause")
    with pytest.raises(ProtocolError):
        s.ack_run_control(r["id"], worker_id="worker", quiescent=True)

    # 2. Quarantined lease: finish quiescent=False then attempt ack_run_control -> must reject
    s.finish(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        outcome="blocked",
        evidence="blocked captcha",
        quiescent=False,
    )
    with pytest.raises(ProtocolError):
        s.ack_run_control(r["id"], worker_id="worker", quiescent=True)


def test_L6_old_progress_event_with_tz_offset_must_not_refresh_progress(tmp_path):
    """L6: Old progress event timestamp with +09:00 offset (absolute instant older than

    currently recorded progress) must not refresh progress. Use datetime arithmetic/fixed
    fake clock and assert parsed datetime not lexicographic.
    """
    t_claim = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    current_time = [t_claim]

    s, r, ids = ready(tmp_path, count=1, settings={"lease_seconds": 86400})
    s.now = lambda: current_time[0].isoformat()

    accept(s, r)
    a = s.claim(r["id"], worker_id="worker")

    initial_progress_raw = s.attempt(a["id"])["progress_at"]
    initial_progress_dt = datetime.fromisoformat(initial_progress_raw)
    assert initial_progress_dt == t_claim

    # Advance current time to 23:00 UTC (lease is still active because lease_seconds=86400)
    t_now = datetime(2026, 9, 6, 23, 0, 0, tzinfo=timezone.utc)
    current_time[0] = t_now

    # Construct an older event with +09:00 offset:
    # Instant in UTC: 11:30 UTC (strictly older than t_claim = 12:00 UTC)
    # Representation in +09:00: 2026-09-06T20:30:00+09:00
    tz_plus9 = timezone(timedelta(hours=9))
    t_event_utc = t_claim - timedelta(minutes=30)
    t_event = t_event_utc.astimezone(tz_plus9)

    # Precondition verifications:
    # 1. In absolute instant, event is strictly older than recorded progress
    assert t_event < initial_progress_dt
    # 2. In lexicographical string order, the +09:00 string is greater than initial '12:00:00+00:00'
    assert t_event.isoformat() > initial_progress_raw

    # Send progress event
    s.event(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        event_id="evt-progress-offset",
        event_type="navigation_verified",
        observed_at=t_event.isoformat(),
        payload={"evidence": "verified navigation via historical event"},
    )

    # Progress must NOT refresh to the older event
    updated_progress_raw = s.attempt(a["id"])["progress_at"]
    updated_progress_dt = datetime.fromisoformat(updated_progress_raw)

    assert updated_progress_dt == initial_progress_dt, (
        f"Progress timestamp was updated to older event: {updated_progress_raw} "
        f"(parsed {updated_progress_dt}) vs initial {initial_progress_raw} (parsed {initial_progress_dt})"
    )
    assert updated_progress_dt >= initial_progress_dt


@pytest.mark.parametrize("outcome", ["failed", "blocked", "interrupted"])
def test_L7_reconcile_replay_after_clock_advance_preserves_original_result_and_timestamps(tmp_path, outcome):
    """L7: Same-result operator reconcile failed/blocked/interrupted + same evidence +

    quiescent=True replay after fakeclock advance returns original result/timestamps/duration;
    no reset by transport retries.
    """
    t_start = datetime(2026, 9, 6, 10, 0, 0, tzinfo=timezone.utc)
    current_time = [t_start]

    s, r, ids = ready(tmp_path, count=1)
    s.now = lambda: current_time[0].isoformat()

    accept(s, r)
    a = s.claim(r["id"], worker_id="worker")

    # Advance clock by 60 seconds and perform initial reconcile
    current_time[0] = t_start + timedelta(seconds=60)
    evidence_text = f"operator confirmed {outcome} state"
    res1 = s.reconcile(
        a["id"],
        outcome=outcome,
        evidence=evidence_text,
        browser_quiescent=True,
    )
    orig_completed_at = res1["completed_at"]
    orig_duration = res1["duration_seconds"]
    assert orig_completed_at == (t_start + timedelta(seconds=60)).isoformat()
    assert orig_duration == 60.0
    assert res1["outcome"] == outcome

    # Advance clock by another 300 seconds to simulate a network transport retry
    current_time[0] = t_start + timedelta(seconds=360)
    res2 = s.reconcile(
        a["id"],
        outcome=outcome,
        evidence=evidence_text,
        browser_quiescent=True,
    )

    # Replay must return original result, completed_at, and duration_seconds
    assert res2["completed_at"] == orig_completed_at, (
        f"completed_at reset on retry: original {orig_completed_at}, got {res2['completed_at']}"
    )
    assert res2["duration_seconds"] == orig_duration, (
        f"duration_seconds reset on retry: original {orig_duration}, got {res2['duration_seconds']}"
    )
    assert res2["outcome"] == outcome

    # Ensure DB record is also preserved
    attempt = s.attempt(a["id"])
    assert attempt["completed_at"] == orig_completed_at
    assert attempt["duration_seconds"] == orig_duration

    job = s.job(ids[0])
    assert job["completed_at"] == orig_completed_at
