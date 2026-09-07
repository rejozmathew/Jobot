"""Read-only status checks must not erase the action that actually failed."""
import asyncio
from unittest.mock import AsyncMock

from job_applier.managed_hermes_worker import ApplicationTool
from job_applier.managed_shared import ProtocolError
from job_applier.managed_views import resolve_failure_reason


def test_inventory_does_not_erase_failure_and_successful_retry_resolves_it():
    app = ApplicationTool(None, 'fixture-session', 'fixture-run', {})
    app.context = {'attempt_id': 1}
    events = []
    app.event = lambda kind, payload: events.append({'event_type': kind, 'payload': payload})
    app.operate = AsyncMock(side_effect=[
        ProtocolError('browser_writer_busy'), {'items': []},
        {'simplify': {'status': 'complete', 'writer_state': 'idle'}},
    ])
    try:
        app.handle({'operation': 'autofill'})
        cause = app._unresolved_cause
        assert 'browser_writer_busy' in cause
        app.handle({'operation': 'inventory'})
        assert app._unresolved_cause == cause
        app.handle({'operation': 'autofill'})
        assert app._unresolved_cause is None
        assert events[-1]['payload']['status'] == 'resolved'
        assert events[-1]['payload']['tool_name'] == 'autofill'
    finally:
        app.loop.close()


def test_resolved_operation_is_not_presented_as_current_failure():
    attempt = {'id': 1, 'outcome': 'failed', 'completed_at': '2026-01-01T00:01:00+00:00',
               'evidence': 'Worker exited before submission; owned target absence verified'}
    events = [
        {'id': 'failure', 'observed_at': '2026-01-01T00:00:10+00:00', 'event_type': 'outcome',
         'payload': {'status': 'failed', 'tool_name': 'autofill', 'reason_code': 'browser_writer_busy',
                     'evidence': 'JobBot blocked autofill (browser_writer_busy).'}},
        {'id': 'recovered', 'observed_at': '2026-01-01T00:00:20+00:00', 'event_type': 'recovery',
         'payload': {'status': 'resolved', 'tool_name': 'autofill', 'reason_code': 'browser_writer_busy',
                     'resolution': 'operation_succeeded_on_retry'}},
    ]
    assert resolve_failure_reason(None, attempt, events) == 'No specific failure reason was recorded.'
