"""Posting identifiers and credential namespaces stay separate; synthetic fixtures only."""
import asyncio
import json

import pytest

from job_applier.managed import ProtocolError
from test_local_sessions import setup, reserve, connect, own


def posting_fixture(tmp_path, namespace='SITE_TEST'):
    service, asset, jobs, workspaces, config = setup(tmp_path)
    job = service.intake(url=jobs[0]['url'], namespace=namespace, requisition_id='101',
                         identity_evidence='Synthetic verified posting identifier')
    session = connect(service, reserve(service, asset, jobs))
    return service, job, session, own(service, session), workspaces, config


@pytest.mark.parametrize('posting_namespace', ['SITE_TEST', 'board:fixture', 'site_test/tenant'])
def test_posting_identifier_does_not_break_owned_context(tmp_path, posting_namespace):
    service, job, session, owner, _, _ = posting_fixture(tmp_path, posting_namespace)
    service.account_update(namespace='employer0.example.test', identity_id='candidate', state='verified',
        credential_ref='credential:profile/accounts/default', request_id='saved-account',
        evidence='Synthetic verified account')
    before = service.job(job['id'])
    with service.tx() as db:
        keys_before = [tuple(r) for r in db.execute('SELECT * FROM job_identity_keys WHERE job_id=?', (job['id'],))]
    package = service.application_context(owner['attempt_id'], worker_id=owner['worker_id'])
    assert package['namespace'] == 'employer0.example.test'
    assert package['account']['action'] == 'sign_in'
    assert package['account']['credential_ref'] == 'credential:profile/accounts/default'
    assert package['job']['namespace'] == posting_namespace
    assert package['job']['requisition_id'] == '101'
    assert service.job(job['id']) == before
    with service.tx() as db:
        assert [tuple(r) for r in db.execute('SELECT * FROM job_identity_keys WHERE job_id=?', (job['id'],))] == keys_before
    assert not service.attempt(owner['attempt_id'])['completed_at']
    with pytest.raises(ProtocolError, match='attempt_forbidden'):
        service.application_context(owner['attempt_id'], worker_id='foreign-worker')


def test_posting_fallback_retains_alias_and_explicit_account_scope_checks(tmp_path):
    service, _, _, owner, _, _ = posting_fixture(tmp_path)
    service.namespace_alias(alias='employer0.example.test', canonical='auth.example.test/tenant',
                            verification_evidence='Synthetic verified account alias')
    service.record_account_event(**owner, namespace='employer0.example.test', state='confirmed',
        credential_ref='credential:profile/accounts/default', request_id='owned-account',
        evidence='Synthetic owned account confirmation')
    package = service.application_context(owner['attempt_id'])
    assert package['namespace'] == 'auth.example.test/tenant'
    assert package['account']['action'] == 'sign_in'
    with pytest.raises(ProtocolError, match='invalid_namespace'):
        service.application_context(owner['attempt_id'], namespace='invalid_account')
    assert service.application_context(owner['attempt_id'], namespace='unrelated.example.test')['account'] is None
    with pytest.raises(ProtocolError, match='account_namespace_not_verified_for_job'):
        service.record_account_event(**owner, namespace='unrelated.example.test', state='verified',
            credential_ref='credential:profile/accounts/default', request_id='wrong-account', evidence='Synthetic')
    with pytest.raises(ProtocolError, match='namespace_alias_cycle'):
        service.namespace_alias(alias='auth.example.test/tenant', canonical='employer0.example.test',
                                verification_evidence='Synthetic invalid cycle')


def test_verified_account_shaped_posting_namespace_keeps_tenant_account(tmp_path):
    service, _, _, owner, _, _ = posting_fixture(tmp_path, 'tenant.myworkdayjobs.com/External')
    service.account_update(namespace='tenant.myworkdayjobs.com/external', identity_id='candidate', state='created_unverified',
        credential_ref='credential:profile/accounts/default', request_id='tenant-account', evidence='Synthetic')
    package = service.application_context(owner['attempt_id'])
    assert package['namespace'] == 'tenant.myworkdayjobs.com/external'
    assert package['account']['action'] == 'verify'


def test_owned_host_continues_after_helper_miss_with_same_posting_and_deadline(tmp_path, monkeypatch):
    from job_applier.workspace_host import WorkspaceHost
    from job_applier.application_deadline import freeze
    service, _, session, owner, workspaces, config = posting_fixture(tmp_path)
    frozen = freeze({}, {'application_time_limit_minutes': 60}, service.now())['application_deadline']
    # Synthetic session metadata only: freeze an operator-selected clock before calls.
    metadata = json.loads(service.session(session['id'])['metadata_json'])
    metadata['application_deadline'] = frozen
    with service.tx() as db:
        db.execute('UPDATE application_sessions SET metadata_json=? WHERE id=?', (json.dumps(metadata), session['id']))
    host = object.__new__(WorkspaceHost)
    host.service = service; host.config = config; host.workspace_id = session['workspace_id']
    host.host_id = 'host-' + session['workspace_id']; host.workspace = workspaces[0]
    calls = []
    def synthetic_browser(cfg, client, current_owner, package, target_id, params):
        calls.append(params['method'])
        assert current_owner == owner and package['namespace'] == 'employer0.example.test'
        return {'method': params['method'], 'synthetic': True}
    monkeypatch.setattr('job_applier.application_runtime.browser_action', synthetic_browser)
    def helper_miss(*args, **kwargs):
        return {'status': 'inspection_required', 'reason': 'unsupported_control'}
    monkeypatch.setattr('job_applier.greenhouse_fast.advance', helper_miss)
    request = {'instance_id': service.instance_id, 'session_id': session['id'], 'driver_id': session['driver_id']}
    assert host.dispatch(dict(request, operation='greenhouse_advance'))['status'] == 'inspection_required'
    for method in ('snapshot', 'screenshot', 'repair'):
        assert host.dispatch(dict(request, operation='browser', parameters={'method': method}))['synthetic']
    assert calls == ['snapshot', 'screenshot', 'repair']
    assert service.session(session['id'])['state'] == 'connected'
    assert json.loads(service.session(session['id'])['metadata_json'])['application_deadline'] == frozen
    assert not service.attempt(owner['attempt_id'])['completed_at']
    with pytest.raises(ProtocolError, match='driver_owned_elsewhere'):
        host.dispatch(dict(request, driver_id='foreign', operation='browser', parameters={'method': 'snapshot'}))


@pytest.mark.parametrize('posting_namespace', ['SITE_TEST', 'applications.example.test'])
def test_posting_identifier_allows_real_browser_recovery_and_confirmed_submission(tmp_path, posting_namespace):
    from job_applier.application_runtime import browser_action
    from job_applier.managed_client import LocalClient
    from test_owned_route_history import SOURCE, owned_page
    class SyntheticClient(LocalClient):
        def call(self, operation, *args, **kwargs):
            if operation == 'submission_intent':
                kwargs['fixture'] = True  # Existing explicitly synthetic development permission.
            return super().call(operation, *args, **kwargs)
    def html_for(url):
        return '''<html><body><form><h1>Application</h1>
        <label>Full name<input id="name" name="name" required></label>
        <button id="submit" type="button" onclick="if(document.querySelector('form').reportValidity())document.body.innerHTML='<p>Thank you for applying</p>'">Submit application</button>
        </form></body></html>'''
    async def run():
        async with owned_page(tmp_path, html_for) as (page, service, session, owner):
            service.intake(url=SOURCE, namespace=posting_namespace, requisition_id='123', identity_evidence='Synthetic verified posting')
            client = SyntheticClient({'instance_id': service.instance_id}, service=service)
            config = {'cdp_url': page.fixture_endpoint, 'browser_mode': 'headless', 'spool_dir': str(tmp_path / 'private-spool')}
            async def action(params):
                package = service.application_context(owner['attempt_id'])
                return await asyncio.to_thread(browser_action, config, client, owner, package, page.target_id, params)
            assert (await action({'method': 'snapshot'}))
            incomplete = await action({'method': 'submit', 'selector': '#submit'})
            assert incomplete['status'] == 'application_incomplete'
            assert not service.attempt(owner['attempt_id'])['completed_at']
            await action({'method': 'fill', 'selector': '#name', 'value': 'Synthetic Candidate'})
            result = await action({'method': 'submit', 'selector': '#submit'})
            assert result['status'] == 'applied', result
            assert service.attempt(owner['attempt_id'])['outcome'] == 'applied'
            assert service.session(session['id'])['attempt_id'] == owner['attempt_id']
            assert service.job(session['job_id'])['namespace'] == posting_namespace
    asyncio.run(run())
