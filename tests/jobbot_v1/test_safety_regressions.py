"""Safety regression tests for jobbot_v1 contracts (expected RED).

Primary Windows Hermes retains all implementation/architecture/job logic/integration.
These tests define and assert contracts for:
1) Quiescent finish rejection while unfinished actions exist or writer_state is active/unknown.
2) Stale reconciliation cannot overwrite newer attempts on the same job.
3) Profile snapshots immutability and credential rejection in candidate profiles.
4) Run-level settings snapshot immutability (no_progress_seconds).
"""
import sqlite3
import pytest
from job_applier.managed import Service, ProtocolError
from test_ownership import ready, accept


def test_finish_quiescent_rejects_unfinished_action_and_active_or_unknown_writer(tmp_path):
    """Finish with quiescent=True must reject while action_start created an unfinished action

    or writer_state is active/unknown; heartbeat continues ownership, and no next claim
    until released.
    """
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    # 1. Unfinished action prevents quiescent finish even if quiescent=True
    s.action_start(a['id'], worker_id='worker', fence=a['fence'], action_id='act-1', tool_name='fixture_fill')
    with pytest.raises(ProtocolError):
        s.finish(a['id'], worker_id='worker', fence=a['fence'], outcome='ready_for_review', evidence='fixture done', quiescent=True)

    # Heartbeat continues ownership while finish is rejected
    hb = s.heartbeat(a['id'], worker_id='worker', fence=a['fence'])
    assert hb['control'] == 'running'
    assert s.attempt(a['id'])['completed_at'] is None

    # No next claim until released
    with pytest.raises(ProtocolError, match='owned_elsewhere'):
        s.claim(r['id'], worker_id='worker')

    # Close the action
    s.action_end(a['id'], worker_id='worker', fence=a['fence'], action_id='act-1', status='success')

    # 2. writer_state 'active' prevents quiescent finish
    s.writer_state(a['id'], worker_id='worker', fence=a['fence'], state='active')
    with pytest.raises(ProtocolError):
        s.finish(a['id'], worker_id='worker', fence=a['fence'], outcome='ready_for_review', evidence='fixture done', quiescent=True)

    # Heartbeat continues ownership and next claim blocked
    s.heartbeat(a['id'], worker_id='worker', fence=a['fence'])
    with pytest.raises(ProtocolError, match='owned_elsewhere'):
        s.claim(r['id'], worker_id='worker')

    # 3. writer_state 'unknown' prevents quiescent finish
    s.writer_state(a['id'], worker_id='worker', fence=a['fence'], state='unknown')
    with pytest.raises(ProtocolError):
        s.finish(a['id'], worker_id='worker', fence=a['fence'], outcome='ready_for_review', evidence='fixture done', quiescent=True)

    # Heartbeat continues ownership and next claim blocked
    s.heartbeat(a['id'], worker_id='worker', fence=a['fence'])
    with pytest.raises(ProtocolError, match='owned_elsewhere'):
        s.claim(r['id'], worker_id='worker')

    # 4. Once writer_state is 'idle' and no actions pending, finish succeeds and next claim succeeds
    s.writer_state(a['id'], worker_id='worker', fence=a['fence'], state='idle')
    fin = s.finish(a['id'], worker_id='worker', fence=a['fence'], outcome='ready_for_review', evidence='fixture done', quiescent=True)
    assert fin['outcome'] == 'ready_for_review'
    assert fin['completed_at'] is not None

    b = s.claim(r['id'], worker_id='worker')
    assert b['job_id'] == ids[1]


def test_stale_reconciliation_cannot_overwrite_newer_attempt_for_same_job(tmp_path):
    """Stale reconciliation must not overwrite a newer attempt for SAME job:

    ready count1, claim a; finish failed quiescent true; retry job;
    request new run with new request_id and same job identity/browser; accept same worker;
    claim b; reconcile a must raise ProtocolError and b/job running unaffected.
    """
    s, r, ids = ready(tmp_path, count=1)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    # Finish attempt a as failed, quiescent true
    s.finish(a['id'], worker_id='worker', fence=a['fence'], outcome='failed', evidence='fixture initial failure', quiescent=True)
    assert s.job(ids[0])['status'] == 'failed'

    # Retry job
    s.retry(ids[0])
    assert s.job(ids[0])['status'] == 'queued'

    # Request new run with new request_id and same job identity/browser
    r2 = s.request_run(
        request_id='request-retry-1',
        job_ids=[ids[0]],
        identity_id='candidate',
        browser_profile='fixture-browser',
    )
    accept(s, r2, worker='worker')
    b = s.claim(r2['id'], worker_id='worker')
    assert b['id'] != a['id']
    assert b['job_id'] == ids[0]
    assert s.job(ids[0])['status'] == 'running'

    # Reconciling old attempt a must raise ProtocolError
    with pytest.raises(ProtocolError):
        s.reconcile(a['id'], outcome='interrupted', evidence='fixture stale reconciliation', browser_quiescent=True)

    # b and job must remain running and unaffected
    assert s.job(ids[0])['status'] == 'running'
    b_status = s.attempt_status(b['id'])
    assert b_status['completed_at'] is None
    assert b_status['outcome'] is None
    assert s.attempt(b['id'])['completed_at'] is None

    # Heartbeat on b still works
    hb = s.heartbeat(b['id'], worker_id='worker', fence=b['fence'])
    assert hb['control'] == 'running'


def test_candidate_profile_snapshot_and_secret_rejection(tmp_path):
    """Settings/profile snapshots: edit candidate profile for later jobs; old attempt

    profile_json unchanged.
    s.identity(...profile={'facts':{'authorized':'fixture'},'password':'SENTINEL_PASSWORD'})
    must not persist credential values anywhere in candidates/attempt snapshots.
    API declared behavior is reject: expect ProtocolError on secret-bearing profile.
    No changes to authoritative real profile.
    """
    s, r, ids = ready(tmp_path, count=2)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    # Old attempt profile_json snapshot check
    attempt_a_before = s.attempt(a['id'])
    original_profile_json = attempt_a_before['profile_json']
    assert 'work_authorization' in original_profile_json

    # Edit candidate profile for later jobs
    s.identity(
        identity_id='candidate',
        person_key='person',
        email='candidate@example.test',
        profile={'facts': {'work_authorization': 'fixture-v2', 'location': 'Austin'}, 'resume_ref': 'asset:fixture-v2'},
    )

    # Old attempt profile_json must remain unchanged
    attempt_a_after = s.attempt(a['id'])
    assert attempt_a_after['profile_json'] == original_profile_json
    assert 'fixture-v2' not in attempt_a_after['profile_json']

    # Read candidate profile before secret rejection test
    with s.tx() as db:
        candidate_before = dict(db.execute('SELECT * FROM candidates WHERE id=?', ('candidate',)).fetchone())

    # Secret-bearing profile must be rejected with ProtocolError
    secret_profile = {
        'facts': {'authorized': 'fixture'},
        'password': 'SENTINEL_PASSWORD',
    }
    with pytest.raises(ProtocolError):
        s.identity(
            identity_id='candidate',
            person_key='person',
            email='candidate@example.test',
            profile=secret_profile,
        )

    # Check candidate profile values in DB: no changes to authoritative real profile
    with s.tx() as db:
        candidate_after = dict(db.execute('SELECT * FROM candidates WHERE id=?', ('candidate',)).fetchone())
        assert candidate_after['profile_json'] == candidate_before['profile_json']
        assert candidate_after['profile_hash'] == candidate_before['profile_hash']

        # Ensure sentinel password is not persisted anywhere in candidates or application_attempts
        cand_rows = db.execute('SELECT profile_json FROM candidates').fetchall()
        for row in cand_rows:
            assert 'SENTINEL_PASSWORD' not in row['profile_json']
        attempt_rows = db.execute('SELECT profile_json FROM application_attempts').fetchall()
        for row in attempt_rows:
            assert 'SENTINEL_PASSWORD' not in row['profile_json']


def test_run_snapshot_no_progress_seconds_immutable(tmp_path):
    """run snapshot no_progress_seconds=5 set BEFORE request_run (use Service.create settings=...).

    Later change s.settings to 999 after claim; attempt_status after 10s must remain
    stalled based on snapshot. Do not relax immutable snapshot policy to pass.
    """
    s = Service.create(
        tmp_path / 'snapshot.db',
        instance_id='snapshot-inst',
        settings={'no_progress_seconds': 5, 'mode': 'development'},
    )
    s.identity(
        identity_id='candidate',
        person_key='person',
        email='candidate@example.test',
        profile={'facts': {'work_authorization': 'fixture'}, 'resume_ref': 'asset:fixture-v1'},
    )
    job = s.intake(url='https://careers.example.test/jobs/snap1', source_id='snap1')
    s.eligibility(job['id'], 'ready', reason='approved')

    s.now = lambda: '2026-09-06T12:00:00+00:00'
    r = s.request_run(
        request_id='run-snap-1',
        job_ids=[job['id']],
        identity_id='candidate',
        browser_profile='fixture-browser',
    )
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    # Status initially: elapsed 0, not stalled
    status0 = s.attempt_status(a['id'])
    assert status0['stalled'] is False

    # Later change s.settings to 999 after claim
    s.settings['no_progress_seconds'] = 999

    # Advance clock by 10 seconds and heartbeat
    s.now = lambda: '2026-09-06T12:00:10+00:00'
    s.heartbeat(a['id'], worker_id='worker', fence=a['fence'])

    # attempt_status after 10s must remain stalled based on snapshot (5s), not live s.settings (999s)
    status1 = s.attempt_status(a['id'])
    assert status1['elapsed_seconds'] == 10
    assert status1['stalled'] is True, 'attempt_status must evaluate stalled using snapshotted settings, not mutated s.settings'
