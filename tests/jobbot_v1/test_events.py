import sqlite3
import pytest
from job_applier.managed import ProtocolError
from test_ownership import ready, accept


def test_event_recording_idempotence_and_conflict_rejection(tmp_path):
    s, r, ids = ready(tmp_path)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    ev = s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='e1',
        action_id='act-1',
        event_type='tool_finished',
        observed_at='2026-09-06T12:00:03+00:00',
        duration_seconds=3,
        payload={'tool': 'fixture_fill', 'status': 'success'},
    )
    assert isinstance(ev, dict)

    events = s.events(a['id'])
    assert isinstance(events, list)
    assert len(events) == 1
    assert 'payload_json' in events[0]
    assert 'stale' in events[0]
    assert not events[0]['stale']

    # Exact retry with same id and content is idempotent
    ev_retry = s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='e1',
        action_id='act-1',
        event_type='tool_finished',
        observed_at='2026-09-06T12:00:03+00:00',
        duration_seconds=3,
        payload={'tool': 'fixture_fill', 'status': 'success'},
    )
    assert ev_retry == ev
    assert len(s.events(a['id'])) == 1

    # Changed payload conflict rejected
    with pytest.raises(ProtocolError):
        s.event(
            a['id'],
            worker_id='worker',
            fence=a['fence'],
            event_id='e1',
            action_id='act-1',
            event_type='tool_finished',
            observed_at='2026-09-06T12:00:03+00:00',
            duration_seconds=3,
            payload={'tool': 'fixture_fill', 'status': 'conflict'},
        )


def test_tool_event_cannot_change_progress_at(tmp_path):
    s, r, ids = ready(tmp_path)
    s.now = lambda: '2026-09-06T12:00:00+00:00'
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')
    initial_progress = s.attempt_status(a['id'])['progress_at']

    s.now = lambda: '2026-09-06T12:00:05+00:00'
    s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='tool-1',
        action_id='act-tool',
        event_type='tool_finished',
        observed_at='2026-09-06T12:00:05+00:00',
        duration_seconds=3,
        payload={'tool_name': 'fixture_fill', 'status': 'success'},
    )
    status = s.attempt_status(a['id'])
    assert status['progress_at'] == initial_progress


def test_verified_navigation_sets_progress_and_late_event_stays_stale_on_job1(tmp_path):
    s, r, ids = ready(tmp_path, count=2)
    s.now = lambda: '2026-09-06T12:00:00+00:00'
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')
    initial_progress = s.attempt_status(a['id'])['progress_at']

    # Explicit semantic event_type='navigation_verified' sets verified progress while current owner
    s.now = lambda: '2026-09-06T12:00:10+00:00'
    s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='nav-1',
        action_id='act-nav',
        event_type='navigation_verified',
        observed_at='2026-09-06T12:00:10+00:00',
        duration_seconds=1,
        payload={'evidence': 'fixture page changed', 'page': 'questions'},
    )
    status_a = s.attempt_status(a['id'])
    assert status_a['progress_at'] == '2026-09-06T12:00:10+00:00'
    assert status_a['progress_at'] != initial_progress

    # Finish job 1 and claim job 2
    s.finish(a['id'], worker_id='worker', fence=a['fence'], outcome='ready_for_review', evidence='fixture done', quiescent=True)
    s.now = lambda: '2026-09-06T12:00:20+00:00'
    b = s.claim(r['id'], worker_id='worker')
    job2_initial_progress = s.attempt_status(b['id'])['progress_at']

    # Late event after finish + claim job2 stays job1/stale and cannot alter job2 progress
    s.now = lambda: '2026-09-06T12:00:30+00:00'
    s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='late-1',
        action_id='act-late',
        event_type='navigation_verified',
        observed_at='2026-09-06T12:00:30+00:00',
        duration_seconds=1,
        payload={'evidence': 'fixture page changed', 'page': 'questions'},
    )

    events_a = s.events(a['id'])
    late_events = [e for e in events_a if (e.get('id') == 'late-1' or e.get('event_id') == 'late-1')]
    assert len(late_events) == 1
    assert bool(late_events[0]['stale']) is True

    status_b = s.attempt_status(b['id'])
    assert status_b['progress_at'] == job2_initial_progress
    events_b = s.events(b['id'])
    assert not any((e.get('id') == 'late-1' or e.get('event_id') == 'late-1') for e in events_b)


def test_redaction_before_persistence(tmp_path):
    s, r, ids = ready(tmp_path)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    payload = {
        'category': 'auth_step',
        'error_type': 'authentication_failed',
        'password': 'SENTINEL_PASSWORD',
        'otp': '123456',
        'token': 'SENTINEL_TOKEN',
        'raw_reasoning': 'PRIVATE_REASONING',
        'error': 'password=SENTINEL_PASSWORD bearer SENTINEL_TOKEN',
    }
    s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='redact-e1',
        action_id='act-redact',
        event_type='tool_finished',
        observed_at='2026-09-06T12:00:05+00:00',
        duration_seconds=2,
        payload=payload,
    )

    events = s.events(a['id'])
    assert len(events) == 1
    persisted_payload_str = events[0]['payload_json']

    # None may appear in persisted JSON
    for sentinel in ('SENTINEL_PASSWORD', '123456', 'SENTINEL_TOKEN', 'PRIVATE_REASONING'):
        assert sentinel not in persisted_payload_str, f'{sentinel} found in persisted payload_json'

    # Keep ordinary safe semantic category/error_type available
    assert 'auth_step' in persisted_payload_str
    assert 'authentication_failed' in persisted_payload_str

    # Direct database check: none may appear in raw DB row
    with sqlite3.connect(s.db_path) as db:
        row = db.execute('SELECT payload_json FROM managed_events WHERE id=?', ('redact-e1',)).fetchone()
        assert row is not None
        db_payload = row[0]
        for sentinel in ('SENTINEL_PASSWORD', '123456', 'SENTINEL_TOKEN', 'PRIVATE_REASONING'):
            assert sentinel not in db_payload, f'{sentinel} found in raw DB payload'


def test_pause_control_pending_action_and_writer_state_ack(tmp_path):
    s, r, ids = ready(tmp_path)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    # action_start before pause creates pending action
    s.action_start(a['id'], worker_id='worker', fence=a['fence'], action_id='act-1', tool_name='fixture_fill')

    # s.control(r['id'], command='pause') returns control='pause_requested'
    ctrl = s.control(r['id'], command='pause')
    assert ctrl['control'] == 'pause_requested'

    # s.ack_control must reject while action remains
    with pytest.raises(ProtocolError):
        s.ack_control(a['id'], worker_id='worker', fence=a['fence'], quiescent=True)

    # s.action_end closes it
    s.action_end(a['id'], worker_id='worker', fence=a['fence'], action_id='act-1', status='success')

    # s.writer_state active means independent Simplify active: ack still rejected
    s.writer_state(a['id'], worker_id='worker', fence=a['fence'], state='active')
    with pytest.raises(ProtocolError):
        s.ack_control(a['id'], worker_id='worker', fence=a['fence'], quiescent=True)

    # writer_state idle: ack now -> control='paused'
    s.writer_state(a['id'], worker_id='worker', fence=a['fence'], state='idle')
    ack = s.ack_control(a['id'], worker_id='worker', fence=a['fence'], quiescent=True)
    assert ack['control'] == 'paused'

    # No new action_start while paused
    with pytest.raises(ProtocolError):
        s.action_start(a['id'], worker_id='worker', fence=a['fence'], action_id='act-2', tool_name='fixture_fill')

    # s.control(...command='resume') then allowed
    res = s.control(r['id'], command='resume')
    assert res['control'] in ('running', 'resumed', 'active')

    # New action_start allowed after resume
    s.action_start(a['id'], worker_id='worker', fence=a['fence'], action_id='act-2', tool_name='fixture_fill')
    s.action_end(a['id'], worker_id='worker', fence=a['fence'], action_id='act-2', status='success')


def test_stop_control_quiescence_ack_and_prevents_later_claims(tmp_path):
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    s.action_start(a['id'], worker_id='worker', fence=a['fence'], action_id='act-stop', tool_name='fixture_fill')
    stop_res = s.control(r['id'], command='stop')
    assert 'stop' in stop_res['control']

    # ack rejected while not quiescent
    with pytest.raises(ProtocolError):
        s.ack_control(a['id'], worker_id='worker', fence=a['fence'], quiescent=False)

    # ack rejected while pending action remains even if quiescent=True is passed
    with pytest.raises(ProtocolError):
        s.ack_control(a['id'], worker_id='worker', fence=a['fence'], quiescent=True)

    s.action_end(a['id'], worker_id='worker', fence=a['fence'], action_id='act-stop', status='aborted')
    ack = s.ack_control(a['id'], worker_id='worker', fence=a['fence'], quiescent=True)
    assert 'stop' in ack['control']

    s.finish(a['id'], worker_id='worker', fence=a['fence'], outcome='interrupted', evidence='stopped', quiescent=True)

    # stop request prevents later claims
    with pytest.raises(ProtocolError):
        s.claim(r['id'], worker_id='worker')


def test_attempt_status_elapsed_heartbeat_progress_and_stalled(tmp_path):
    # Budget is configured before the run snapshot, never mutated mid-attempt.
    s, r, ids = ready(tmp_path, settings={'no_progress_seconds': 5})
    s.now = lambda: '2026-09-06T12:00:00+00:00'
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    status0 = s.attempt_status(a['id'])
    assert status0['heartbeat_at'] == '2026-09-06T12:00:00+00:00'
    initial_progress = status0['progress_at']
    assert status0['elapsed_seconds'] == 0
    assert status0['stalled'] is False

    # Heartbeat at +10s must not change progress_at
    s.now = lambda: '2026-09-06T12:00:10+00:00'
    s.heartbeat(a['id'], worker_id='worker', fence=a['fence'])

    status1 = s.attempt_status(a['id'])
    assert status1['heartbeat_at'] == '2026-09-06T12:00:10+00:00'
    assert status1['progress_at'] == initial_progress
    assert status1['elapsed_seconds'] == 10
    assert status1['stalled'] is True

    # Record semantic verified progress event
    s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='nav-p1',
        action_id='act-p1',
        event_type='navigation_verified',
        observed_at='2026-09-06T12:00:10+00:00',
        duration_seconds=1,
        payload={'evidence': 'fixture page changed', 'page': 'questions'},
    )

    status2 = s.attempt_status(a['id'])
    assert status2['progress_at'] == '2026-09-06T12:00:10+00:00'
    assert status2['stalled'] is False


def test_total_elapsed_includes_waits_not_sum_of_tool_durations(tmp_path):
    s, r, ids = ready(tmp_path)
    s.now = lambda: '2026-09-06T12:00:00+00:00'
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    # Record a tool event with duration 3 seconds
    s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='tool-dur-1',
        action_id='act-dur',
        event_type='tool_finished',
        observed_at='2026-09-06T12:00:03+00:00',
        duration_seconds=3,
        payload={'tool_name': 'fixture_fill'},
    )

    # Advance clock by 45 seconds (wait / idle / deliberation time)
    s.now = lambda: '2026-09-06T12:00:45+00:00'
    status = s.attempt_status(a['id'])

    # Total elapsed includes waits, not sum of tool durations (which is 3)
    assert status['elapsed_seconds'] == 45
