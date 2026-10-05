"""Completed-attempt evidence must not be replaced by a recoverable tool error."""
import pytest

from job_applier.managed_views import resolve_failure_reason


COMPLETED = '2026-10-05T10:10:00+00:00'


def event(kind='recovery', *, at='2026-10-05T10:05:00+00:00', **payload):
    return {'event_type': kind, 'observed_at': at, 'recorded_at': at,
            'id': at, 'payload': payload}


@pytest.mark.parametrize('evidence,code', [
    ('Employer posting is no longer available after reload and inspection.', 'target_job_mismatch'),
    ('Needs your answer: one required question saved in the answer queue.', 'SyntaxError'),
    ('Employer requires a password with at least 16 characters.', 'idempotency_conflict'),
    ('Verified account recovery link remains outside the owned route.', 'target_job_mismatch'),
])
def test_specific_completion_wins_over_earlier_helper_error(evidence, code):
    attempt = {'outcome': 'blocked', 'completed_at': COMPLETED, 'evidence': evidence}
    errors = [event(status='error', error_type=code, evidence=code)]
    assert resolve_failure_reason(None, attempt, errors) == evidence


def test_late_helper_error_does_not_replace_terminal_evidence():
    evidence = 'Employer posting is closed.'
    attempt = {'outcome': 'blocked', 'completed_at': COMPLETED, 'evidence': evidence}
    errors = [event(at='2026-10-05T10:11:00+00:00', status='error', error_type='target_job_mismatch')]
    assert resolve_failure_reason(None, attempt, errors) == evidence


def test_explicit_late_outcome_still_updates_projection_without_mutation():
    attempt = {'outcome': 'blocked', 'completed_at': COMPLETED, 'evidence': 'Initial terminal explanation.'}
    original = dict(attempt)
    events = [event('outcome', at='2026-10-05T10:11:00+00:00', status='blocked',
                    evidence='Later employer evidence identifies the unresolved account recovery.')]
    assert resolve_failure_reason(None, attempt, events) == events[0]['payload']['evidence']
    assert attempt == original


def test_generic_cleanup_preserves_latest_unresolved_error():
    attempt = {'outcome': 'failed', 'completed_at': COMPLETED,
               'evidence': 'Worker exited before submission; owned target absence verified'}
    events = [event(status='error', error_type='target_job_mismatch')]
    assert resolve_failure_reason(None, attempt, events) == 'target_job_mismatch'


@pytest.mark.parametrize('outcome', ['applied', 'already_applied', 'ready_for_review'])
def test_successful_controls_do_not_acquire_old_failure(outcome):
    attempt = {'outcome': outcome, 'completed_at': COMPLETED, 'evidence': 'Employer confirmation.'}
    assert resolve_failure_reason(None, attempt, [event(status='error', error_type='target_job_mismatch')]) is None
