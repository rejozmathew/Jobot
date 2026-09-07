"""Timing reports test suite for JobBot managed attempts.

Tests the primary implementation of attempt_report(attempt_id) and /v1/attempt_report:
1. Exact spans from event observed_at and duration_seconds, unioned wall time vs category totals.
2. Phase events creating ordered wall-time slices while retaining waits.
3. Missing durations / no events producing uncertainty, issue derivation & redaction, and late metadata isolation.
4. Worker-owned /v1/attempt_report HTTP endpoint preserving worker identity checks.
"""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure tests/jobbot_v1 directory is on sys.path for test_ownership imports
sys.path.insert(0, str(Path(__file__).parent))
from test_ownership import ready, accept
from job_applier.managed_api import create_app


def test_attempt_report_reproduces_exact_spans_unioned_wall_time_and_category_totals(tmp_path):
    s, r, ids = ready(tmp_path, count=1, settings={'lease_seconds': 300})
    s.now = lambda: "2026-09-06T12:00:00+00:00"
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    # Model finished at 12:00:40 with duration 30s -> span [12:00:10, 12:00:40]
    s.now = lambda: "2026-09-06T12:00:40+00:00"
    s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='ev-model-1',
        event_type='model_finished',
        observed_at='2026-09-06T12:00:40+00:00',
        duration_seconds=30.0,
        payload={'model': 'fixture-model', 'status': 'success'},
    )

    # Tool finished at 12:00:50 with duration 20s -> span [12:00:30, 12:00:50]
    # Overlaps model span during [12:00:30, 12:00:40] (10s overlap)
    s.now = lambda: "2026-09-06T12:00:50+00:00"
    s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='ev-tool-1',
        event_type='tool_finished',
        observed_at='2026-09-06T12:00:50+00:00',
        duration_seconds=20.0,
        payload={'tool_name': 'form_input', 'status': 'success'},
    )

    # Finish attempt at 12:01:40 (100 total wall seconds)
    s.now = lambda: "2026-09-06T12:01:40+00:00"
    s.finish(a['id'], worker_id='worker', fence=a['fence'], outcome='ready_for_review', evidence='fixture done', quiescent=True)

    report = s.attempt_report(a['id'])

    assert isinstance(report, dict)
    assert set(report.keys()) >= {'attempt', 'timeline', 'phases', 'timing', 'issues'}

    timing = report['timing']
    assert timing['wall_seconds'] == 100.0
    # Overlapping spans [10..40] and [30..50] union to [10..50] = 40s
    assert timing['observed_union_seconds'] == 40.0
    # Unattributed wall time = 100.0 - 40.0 = 60.0
    assert timing['unattributed_seconds'] == 60.0
    # Category totals clearly separate and may overlap
    assert timing['category_seconds']['model'] == 30.0
    assert timing['category_seconds']['tool'] == 20.0
    assert bool(timing['uncertainty']) is False
    assert len(report['timeline']) >= 2


def test_attempt_report_phase_events_create_ordered_wall_time_slices(tmp_path):
    s, r, ids = ready(tmp_path, count=1, settings={'lease_seconds': 300})
    s.now = lambda: "2026-09-06T12:00:00+00:00"
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    s.now = lambda: "2026-09-06T12:00:20+00:00"
    s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='p-nav',
        event_type='phase_changed',
        observed_at='2026-09-06T12:00:20+00:00',
        payload={'phase': 'navigation'},
    )

    s.now = lambda: "2026-09-06T12:01:00+00:00"
    s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='p-fill',
        event_type='phase_changed',
        observed_at='2026-09-06T12:01:00+00:00',
        payload={'phase': 'form_filling'},
    )

    s.now = lambda: "2026-09-06T12:01:30+00:00"
    s.event(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        event_id='p-rev',
        event_type='phase_changed',
        observed_at='2026-09-06T12:01:30+00:00',
        payload={'phase': 'review'},
    )

    s.now = lambda: "2026-09-06T12:01:40+00:00"
    s.finish(a['id'], worker_id='worker', fence=a['fence'], outcome='ready_for_review', evidence='fixture done', quiescent=True)

    report = s.attempt_report(a['id'])
    phases = report['phases']
    assert isinstance(phases, list)
    assert len(phases) >= 3

    phase_names = [p.get('phase') for p in phases if isinstance(p, dict)]
    assert 'navigation' in phase_names
    assert 'form_filling' in phase_names
    assert 'review' in phase_names

    for p in phases:
        assert 'phase' in p
        assert ('duration_seconds' in p or ('started_at' in p and 'ended_at' in p))


def test_attempt_report_missing_durations_uncertainty_issues_and_late_metadata_isolation(tmp_path):
    s, r, ids = ready(tmp_path, count=2, settings={'lease_seconds': 300})
    s.now = lambda: "2026-09-06T12:00:00+00:00"
    accept(s, r)
    a1 = s.claim(r['id'], worker_id='worker')

    # Missing duration & failed event
    s.now = lambda: "2026-09-06T12:00:15+00:00"
    s.event(
        a1['id'],
        worker_id='worker',
        fence=a1['fence'],
        event_id='ev-fail-1',
        event_type='tool_finished',
        observed_at='2026-09-06T12:00:15+00:00',
        duration_seconds=None,
        payload={'tool_name': 'click', 'status': 'failed', 'error_type': 'selector_not_found'},
    )

    s.now = lambda: "2026-09-06T12:00:30+00:00"
    s.finish(a1['id'], worker_id='worker', fence=a1['fence'], outcome='failed', evidence='fixture failed', quiescent=True)

    s.now = lambda: "2026-09-06T12:00:40+00:00"
    a2 = s.claim(r['id'], worker_id='worker')

    # Late event with original attempt fence stays on attempt 1, never attempt 2
    s.now = lambda: "2026-09-06T12:00:50+00:00"
    s.event(
        a1['id'],
        worker_id='worker',
        fence=a1['fence'],
        event_id='late-ev-1',
        event_type='tool_finished',
        observed_at='2026-09-06T12:00:50+00:00',
        duration_seconds=2.0,
        payload={'tool_name': 'cleanup', 'status': 'aborted', 'reason_code': 'worker_timeout'},
    )

    rep1 = s.attempt_report(a1['id'])
    assert bool(rep1['timing']['uncertainty']) is True
    # Missing durations yield unknown/unattributed, not fabricated zero-duration operations
    assert any(ev.get('duration_seconds') is None or ev.get('uncertain', False) for ev in rep1['timeline'])

    # Issues derive bounded structured failed/aborted event metadata without raw secrets or profile_json
    assert len(rep1['issues']) >= 1
    issue_statuses = {iss.get('status') for iss in rep1['issues']}
    assert ('failed' in issue_statuses or 'aborted' in issue_statuses)
    assert 'profile_json' not in rep1['attempt']

    # Late metadata stays on original attempt
    rep1_ids = {e.get('id') or e.get('event_id') for e in rep1['timeline']}
    assert 'late-ev-1' in rep1_ids

    rep2 = s.attempt_report(a2['id'])
    rep2_ids = {e.get('id') or e.get('event_id') for e in rep2['timeline']}
    assert 'late-ev-1' not in rep2_ids


def test_v1_attempt_report_endpoint_worker_owned_and_identity_checks(tmp_path):
    s, r, ids = ready(tmp_path, count=1, settings={'lease_seconds': 300})
    accept(s, r, worker='worker-1')
    a = s.claim(r['id'], worker_id='worker-1')

    op_tok = "synthetic-operator-token-long-1234"
    w1_tok = "synthetic-worker1-token-long-1234"
    w2_tok = "synthetic-worker2-token-long-1234"
    app = create_app(s, operator_token=op_tok, worker_tokens={w1_tok: 'worker-1', w2_tok: 'worker-2'})
    client = TestClient(app, base_url="http://127.0.0.1:8769")

    # 1. Unauthenticated -> 401
    res = client.post("/v1/attempt_report", json={"attempt_id": a['id']}, headers={"X-JobBot-Instance": s.instance_id})
    assert res.status_code == 401

    # 2. Worker 1 (owner) calls /v1/attempt_report -> 200 with structured report
    headers_w1 = {"Authorization": f"Bearer {w1_tok}", "X-JobBot-Instance": s.instance_id}
    res = client.post("/v1/attempt_report", json={"attempt_id": a['id'], "worker_id": "worker-1"}, headers=headers_w1)
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) >= {'attempt', 'timeline', 'phases', 'timing', 'issues'}

    # 3. Worker 2 calls /v1/attempt_report for Worker 1's attempt -> 403 attempt_forbidden
    headers_w2 = {"Authorization": f"Bearer {w2_tok}", "X-JobBot-Instance": s.instance_id}
    res = client.post("/v1/attempt_report", json={"attempt_id": a['id'], "worker_id": "worker-2"}, headers=headers_w2)
    assert res.status_code == 403
    assert res.json().get('error') in ('attempt_forbidden', 'role_forbidden')

    # 4. Worker 1 passes mismatched worker_id -> 403 worker_identity_mismatch
    res = client.post("/v1/attempt_report", json={"attempt_id": a['id'], "worker_id": "worker-2"}, headers=headers_w1)
    assert res.status_code == 403
    assert res.json().get('error') == 'worker_identity_mismatch'
