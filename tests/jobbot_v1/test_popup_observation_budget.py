"""Popup observation reuses the action window and retains ordinary recovery."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from job_applier import cdp_client as cdp


@pytest.mark.parametrize('destination,accepted', [
    ('https://forms.example.test/candidate', True),
    ('https://jobs.example.test/jobs/999', False),
    ('https://forms.example.test/reset-password?reset_token=private', False),
])
@pytest.mark.parametrize('borrowed_browser', [True, False])
def test_ready_popup_has_no_sleep_and_preserves_identity_rules(monkeypatch, destination, accepted, borrowed_browser):
    found = {'kind': 'popup', 'target_id': 'child', 'url': 'https://jobs.example.test/apply/123'}
    page = SimpleNamespace(evaluate=AsyncMock(return_value={'url': destination, 'ready': 'complete'}))
    child = SimpleNamespace(get_current_page=AsyncMock(return_value=page), close=AsyncMock())
    connect = AsyncMock(return_value=child)
    monkeypatch.setattr(cdp.CDPBrowser, 'connect', connect)
    monkeypatch.setattr(cdp, 'time', SimpleNamespace(monotonic=lambda: 10))
    # A sensitive URL retains the original handoff at expiry.
    if 'reset_token' in destination:
        ticks = iter([10, 15])
        monkeypatch.setattr(cdp.time, 'monotonic', lambda: next(ticks, 15))
    sleep = AsyncMock()
    monkeypatch.setattr(cdp.asyncio, 'sleep', sleep)
    result = asyncio.run(cdp.observe_popup_document(
        SimpleNamespace(base_url='http://127.0.0.1:9222', observed_mode='headless') if borrowed_browser else None,
        SimpleNamespace(armed_at=10, cdp_url='http://127.0.0.1:9222'), found,
        source_url='https://jobs.example.test/jobs/123'))
    assert result['url'] == (destination if accepted else found['url'])
    sleep.assert_not_awaited()
    child.close.assert_awaited_once()
    connect.assert_awaited_once_with('http://127.0.0.1:9222', target_id='child', expected_mode='headless' if borrowed_browser else None)


@pytest.mark.parametrize('kind,armed_at', [('same_tab', 10), ('popup', 4)])
def test_other_navigation_or_expired_window_adds_no_connection(monkeypatch, kind, armed_at):
    monkeypatch.setattr(cdp, 'time', SimpleNamespace(monotonic=lambda: 10))
    connect = AsyncMock()
    monkeypatch.setattr(cdp.CDPBrowser, 'connect', connect)
    found = {'kind': kind, 'target_id': 'child', 'url': 'https://jobs.example.test/apply/123'}
    result = asyncio.run(cdp.observe_popup_document(None, SimpleNamespace(armed_at=armed_at),
        found, source_url='https://jobs.example.test/jobs/123'))
    assert result is found
    connect.assert_not_awaited()


def test_connection_failure_retains_original_handoff(monkeypatch):
    monkeypatch.setattr(cdp, 'time', SimpleNamespace(monotonic=lambda: 10))
    monkeypatch.setattr(cdp.CDPBrowser, 'connect', AsyncMock(side_effect=OSError('Disconnected')))
    found = {'kind': 'popup', 'target_id': 'child', 'url': 'https://jobs.example.test/apply/123'}
    assert asyncio.run(cdp.observe_popup_document(
        SimpleNamespace(base_url='http://127.0.0.1:9222', observed_mode='headless'),
        SimpleNamespace(armed_at=10), found, source_url='https://jobs.example.test/jobs/123')) is found
