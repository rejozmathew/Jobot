"""Regressions for the demonstrated integration, not a new recovery matrix."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from job_applier.cdp_client import CDPBrowser
from job_applier.simplify_boundary import OBSERVE
from job_applier.managed import ProtocolError
from job_applier.managed_api import create_app
from test_product_integration import (make_service_with_attempt, WORKER_ID,
                                      OPERATOR_TOKEN, WORKER_TOKEN, BASE_URL)


def browser_probe(monkeypatch, url, status='ready', panel=True, display_url=None, after_url=None):
    calls = []
    async def evaluate(expression):
        calls.append(expression)
        if expression == 'location.href':
            return after_url if after_url and calls.count(expression)>1 else url
        assert expression == OBSERVE, 'Only the fixed Simplify observer may execute'
        return {'url': display_url or url, 'status': status, 'panel': panel, 'fingerprint': 'stable',
                'page_ref': 'page-1', 'page_signature': 'form-1',
                'source': 'observed_dom', 'controls': {}}
    page = type('Page', (), {'evaluate': staticmethod(evaluate)})()
    browser = type('Browser', (), {'get_current_page': AsyncMock(return_value=page),
                                   'close': AsyncMock(), 'observed_mode': 'unknown'})()
    connect = AsyncMock(return_value=browser)
    monkeypatch.setattr(CDPBrowser, 'connect', connect)
    return calls, connect


def owned_service(tmp_path):
    s, job, run, a = make_service_with_attempt(tmp_path)
    s.bind_target(a['id'], worker_id=WORKER_ID, fence=1, target_id='target-tab-1', url=job['url'])
    return s, job, run, a


@pytest.mark.parametrize('control', ['pause', 'stop'])
def test_fixed_observer_reads_cdp_during_pending_control(tmp_path, monkeypatch, control):
    s, job, run, a = owned_service(tmp_path)
    calls, connect = browser_probe(monkeypatch, job['url'])
    s.writer_state(a['id'], worker_id=WORKER_ID, fence=1, state='active')
    s.control(run['id'], command=control)
    result = s.browser_observe(a['id'], worker_id=WORKER_ID, fence=1)
    assert calls.count(OBSERVE) >= 2
    assert connect.call_args.kwargs['expected_mode'] == 'headed'
    assert connect.call_args.kwargs['target_id'] == 'target-tab-1'
    assert result['quiescent'] is True
    assert result['observed_browser_mode'] == 'unknown'
    with pytest.raises(ProtocolError):
        s.action_start(a['id'], worker_id=WORKER_ID, fence=1, action_id='shell-read',
                       tool_name='terminal', writes_browser=False)
    with pytest.raises(ProtocolError):
        s.action_start(a['id'], worker_id=WORKER_ID, fence=1, action_id='write',
                       tool_name='fill', writes_browser=True)
    s.ack_control(a['id'], worker_id=WORKER_ID, fence=1, quiescent=True)


@pytest.mark.parametrize('status', ['active', 'unknown', 'missing', 'login_required'])
def test_unobserved_writer_never_becomes_quiescent(tmp_path, monkeypatch, status):
    s, job, run, a = owned_service(tmp_path)
    calls, _ = browser_probe(monkeypatch, job['url'], status, panel=status not in ('missing', 'unknown'))
    s.writer_state(a['id'], worker_id=WORKER_ID, fence=1, state='active')
    result = s.browser_observe(a['id'], worker_id=WORKER_ID, fence=1)
    assert OBSERVE in calls
    assert result['quiescent'] is False
    assert result['writer_state'] != 'idle'


def test_unknown_writer_settles_when_extension_reports_unsupported(tmp_path,monkeypatch):
    s,job,run,a=owned_service(tmp_path)
    browser_probe(monkeypatch,job['url'],'unsupported')
    s.writer_state(a['id'],worker_id=WORKER_ID,fence=1,state='unknown')
    result=s.browser_observe(a['id'],worker_id=WORKER_ID,fence=1)
    assert result['quiescent'] and result['writer_state']=='idle'


def test_caller_cannot_supply_completion_and_worker_cannot_read_other_candidate(tmp_path):
    s, job, run, a = owned_service(tmp_path)
    s.identity(identity_id='other', person_key='other', email='other@example.test', profile={})
    s.writer_state(a['id'], worker_id=WORKER_ID, fence=1, state='unknown')
    headers = {'Authorization': 'Bearer '+WORKER_TOKEN, 'X-JobBot-Instance': s.instance_id}
    client = TestClient(create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID}), base_url=BASE_URL)
    forged = client.post('/v1/browser_observe', headers=headers, json={
        'attempt_id': a['id'], 'worker_id': WORKER_ID, 'fence': 1,
        'observation': {'status': 'complete', 'url': job['url']}})
    assert forged.status_code == 422
    assert s.attempt(a['id'])['writer_state'] == 'unknown'
    assert client.post('/v1/candidate', headers=headers, json={'identity_id': 'other'}).status_code == 403


def test_observer_exposes_owned_diagnostics_without_granting_foreign_job_writes(tmp_path, monkeypatch):
    s, job, run, a = owned_service(tmp_path)
    calls, _ = browser_probe(monkeypatch, 'https://careers.example.test/jobs/unowned')
    result=s.browser_observe(a['id'], worker_id=WORKER_ID, fence=1)
    assert result['identity']['status']=='identity_unresolved'
    assert not result['native_takeover_authorized']
    assert OBSERVE in calls


@pytest.mark.parametrize('redirect,changes_during_observation', [('R1',False),('R2',False),('R2',True)])
def test_workday_login_scope_uses_full_browser_url_not_redacted_display(tmp_path,monkeypatch,redirect,changes_during_observation):
    from urllib.parse import quote
    job_url='https://tenant.wd5.myworkdayjobs.com/Jobs/job/City/Role_R1'
    display='https://tenant.wd5.myworkdayjobs.com/en-US/Jobs/login'
    def login(req):return display+'?redirect='+quote('/en-US/Jobs/job/City/Role_'+req+'/apply/applyManually',safe='')
    s,job,run,a=make_service_with_attempt(tmp_path,url=job_url)
    s.bind_target(a['id'],worker_id=WORKER_ID,fence=1,target_id='target-tab-1',url=job_url)
    browser_probe(monkeypatch,login('R1') if changes_during_observation else login(redirect),
                  display_url=display,after_url=login(redirect) if changes_during_observation else None)
    if redirect=='R1':
        observed=s.browser_observe(a['id'],worker_id=WORKER_ID,fence=1)
        assert observed['quiescent'] and observed['observation']['url']==display
        assert '?redirect=' not in json.dumps(observed)
    else:
        observed=s.browser_observe(a['id'],worker_id=WORKER_ID,fence=1)
        assert not observed['native_takeover_authorized']
        assert observed['identity']['status']=='different_job'


def test_http_observer_can_execute_async_cdp(tmp_path, monkeypatch):
    s, job, run, a = owned_service(tmp_path)
    calls, _ = browser_probe(monkeypatch, job['url'])
    client = TestClient(create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID}), base_url=BASE_URL)
    response = client.post('/v1/browser_observe', headers={
        'Authorization': 'Bearer '+WORKER_TOKEN, 'X-JobBot-Instance': s.instance_id},
        json={'attempt_id': a['id'], 'worker_id': WORKER_ID, 'fence': 1})
    assert response.status_code == 200, response.json()
    assert calls.count(OBSERVE) >= 2
    assert response.json()['quiescent'] is True
