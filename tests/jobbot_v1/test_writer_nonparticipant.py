"""Explicit browser receipts distinguish no writer from an unfinished writer."""
from unittest.mock import AsyncMock

import pytest

from job_applier.cdp_client import CDPBrowser
from job_applier.simplify_boundary import OBSERVE
from tests.jobbot_v1.test_product_observation import owned_service, WORKER_ID


def probe(monkeypatch, url, *, participant=False, pending=False, changed=False):
    reads = []
    async def evaluate(expression):
        if expression == 'location.href': return url
        assert expression == OBSERVE
        reads.append(True)
        return {'url': url, 'status': 'unknown', 'panel': True, 'fingerprint': str(len(reads)) if changed else 'fixed',
                'page_ref': 'page', 'page_signature': 'form', 'controls': {}, 'source': 'observed_dom',
                'writer_document_id': 'document', 'writer_participant': participant,
                'writer_pending': pending, 'writer_safe': False, 'activity': {}}
    page = type('Page', (), {'evaluate': staticmethod(evaluate)})()
    browser = type('Browser', (), {'get_current_page': AsyncMock(return_value=page),
                                   'close': AsyncMock(), 'observed_mode': 'headed'})()
    monkeypatch.setattr(CDPBrowser, 'connect', AsyncMock(return_value=browser))


def test_unknown_from_prior_observation_does_not_invent_autofill(tmp_path, monkeypatch):
    service, job, run, attempt = owned_service(tmp_path)
    owner = {'attempt_id': attempt['id'], 'worker_id': WORKER_ID, 'fence': 1}
    probe(monkeypatch, job['url'], changed=True)
    assert service.browser_observe(**owner)['writer_state'] == 'unknown'
    probe(monkeypatch, job['url'])
    result = service.browser_observe(**owner)
    assert result['native_takeover_authorized'] and result['writer_state'] == 'idle'
    # Native recovery can now begin and verify through the ordinary action ledger.
    service.action_start(**owner, action_id='next', tool_name='local_browser.click')
    service.action_end(**owner, action_id='next', status='success', duration_seconds=.1)
    assert service.attempt(attempt['id'])['completed_at'] is None


@pytest.mark.parametrize('participant,pending', [(True, False), (True, True), (None, False)])
def test_actual_or_unobserved_writer_still_needs_settlement(tmp_path, monkeypatch, participant, pending):
    service, job, _, attempt = owned_service(tmp_path)
    owner = {'attempt_id': attempt['id'], 'worker_id': WORKER_ID, 'fence': 1}
    service.writer_state(**owner, state='unknown')
    probe(monkeypatch, job['url'], participant=participant, pending=pending)
    assert not service.browser_observe(**owner)['native_takeover_authorized']


def test_nonparticipant_does_not_settle_an_unended_native_action(tmp_path, monkeypatch):
    service, job, _, attempt = owned_service(tmp_path)
    owner = {'attempt_id': attempt['id'], 'worker_id': WORKER_ID, 'fence': 1}
    service.action_start(**owner, action_id='running', tool_name='local_browser.fill')
    probe(monkeypatch, job['url'])
    assert not service.browser_observe(**owner)['native_takeover_authorized']
