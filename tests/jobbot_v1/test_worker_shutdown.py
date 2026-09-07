"""Owned-tab shutdown retains verified outcomes and never fabricates quiescence."""
import asyncio
from types import SimpleNamespace
import pytest
from job_applier.managed_hermes_worker import ApplicationTool


@pytest.mark.parametrize('closed,confirmed,expected', [
    (True, True, 'applied'), (True, False, 'submission_unknown'),
    (False, True, None), (False, False, None),
])
def test_shutdown_preserves_confirmation_and_requires_verified_cleanup(closed, confirmed, expected):
    app = ApplicationTool(SimpleNamespace(), 'session', 'run', {'worker_id': 'worker'})
    app.context = {'attempt_id': 'attempt', 'worker_id': 'worker', 'fence': 1}
    app.target = 'owned-target'
    app.submit_clicked = True
    app.confirmation_receipt = {'outcome': 'applied', 'evidence': 'Verified employer receipt'} if confirmed else None
    calls = []

    async def close_target(reason):
        app.target_closed = closed
        return closed

    app.close_target = close_target
    app.call = lambda op, **params: calls.append((op, params)) or {}
    app.protocol = lambda op, **params: calls.append((op, params)) or {}
    try:
        status = asyncio.run(app.finalize())
        assert status == ('closed' if closed else 'cleanup_pending')
        finishes = [p for op, p in calls if op == 'finish']
        assert [p['outcome'] for p in finishes] == ([expected] if expected else [])
        assert all(p['quiescent'] is True for p in finishes)
        if expected == 'applied':
            assert finishes[0]['evidence'] == 'Verified employer receipt'
        if not closed:
            assert not any(op in ('writer_state', 'next') for op, _ in calls)
    finally:
        app.loop.close()
