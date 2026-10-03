"""Credential gate failures retain their cause and leave owned recovery available."""
import pytest

from job_applier.managed import ProtocolError, Service
from job_applier.workspace_host import WorkspaceHost
from test_local_sessions import connect, reserve, setup


def host_fixture(tmp_path):
    service, asset, jobs, workspaces, config = setup(tmp_path)
    session = connect(service, reserve(service, asset, jobs))
    host = object.__new__(WorkspaceHost)
    host.service, host.config = service, config
    host.workspace, host.workspace_id = workspaces[0], session['workspace_id']
    host.host_id = 'host-' + session['workspace_id']
    return host, service, session


@pytest.mark.parametrize('mode', ['employer', 'verification'])
@pytest.mark.parametrize('identity,quiescent,code', [
    ('different_job', True, 'target_job_mismatch'),
    ('identity_unresolved', True, 'job_identity_unresolved'),
    ('same_job', False, 'simplify_input_or_settlement_required'),
    (None, False, 'simplify_input_or_settlement_required'),
])
def test_denied_credentials_report_actual_cause_and_allow_same_session_recovery(
        tmp_path, monkeypatch, mode, identity, quiescent, code):
    host, service, session = host_fixture(tmp_path)
    gate = {'identity': {'status': identity}, 'quiescent': quiescent,
            'native_takeover_authorized': False, 'private_probe': 'SYNTHETIC-PRIVATE-VALUE'}
    monkeypatch.setattr(Service, 'browser_observe', lambda *a, **kw: gate)
    calls = []
    def credentials(config, package, parameters):
        calls.append(parameters)
        return {'values_committed': True}
    monkeypatch.setattr('job_applier.managed_credentials.handle_credentials', credentials)
    request = {'instance_id': service.instance_id, 'session_id': session['id'],
               'driver_id': session['driver_id'], 'operation': 'credentials',
               'parameters': {'mode': mode}}
    before = service.session(session['id'])
    with pytest.raises(ProtocolError) as caught:
        host.dispatch(request)
    assert caught.value.code == code
    assert not calls
    current = service.session(session['id'])
    assert current['state'] == 'connected' and current['ended_at'] is None
    assert current['metadata_json'] == before['metadata_json']
    assert not service.attempt(session['attempt_id'])['completed_at']
    event = service.session_status(session['id'])['activity']['payload']
    assert event['error_type'] == code
    assert 'SYNTHETIC-PRIVATE-VALUE' not in str(event) + str(caught.value)
    if identity in ('different_job', 'identity_unresolved'):
        assert 'Simplify' not in event['evidence']
        assert 'screenshot' in event['evidence']
    with service.tx() as db:
        assert not db.execute('SELECT 1 FROM managed_actions WHERE attempt_id=?',
                              (session['attempt_id'],)).fetchone()
    # A later observed correction uses this same session, attempt and deadline.
    gate.update(identity={'status': 'same_job'}, quiescent=True, native_takeover_authorized=True)
    assert host.dispatch(request)['values_committed']
    assert len(calls) == 1 and calls[0]['target_id'] == session['target_id']
    assert service.session(session['id'])['metadata_json'] == before['metadata_json']


def test_legacy_quiescent_gate_still_authorizes_credentials(tmp_path, monkeypatch):
    host, service, session = host_fixture(tmp_path)
    monkeypatch.setattr(Service, 'browser_observe', lambda *a, **kw: {'quiescent': True})
    monkeypatch.setattr('job_applier.managed_credentials.handle_credentials',
                        lambda *a, **kw: {'values_committed': True})
    assert host.dispatch({'instance_id': service.instance_id, 'session_id': session['id'],
                          'driver_id': session['driver_id'], 'operation': 'credentials'})['values_committed']


@pytest.mark.parametrize('mode', ['employer', 'verification'])
def test_credentials_use_context_promoted_by_the_authorized_observation(tmp_path, monkeypatch, mode):
    host, service, session = host_fixture(tmp_path)
    before = service.application_context(session['attempt_id'])
    original = before['job']['url']
    current = original.rsplit('/job/', 1)[0] + '/screening'
    attempt = service.attempt(session['attempt_id'])
    owner = {k: attempt[k] for k in ('worker_id', 'fence')}
    owner['attempt_id'] = attempt['id']
    service.record_account_event(**owner, namespace=before['namespace'], state='confirmed',
        credential_ref='credential:profile/accounts/default', request_id='fixture-account',
        evidence='Synthetic retained employer account')

    def observe(observing_service, *args, **kwargs):
        observing_service.handoff_target(**owner, current_target_id=session['target_id'],
            new_target_id=session['target_id'], url=current, source_url=original,
            evidence='Synthetic observed same-document continuation')
        return {'identity': {'status': 'same_job'}, 'native_takeover_authorized': True}
    monkeypatch.setattr(Service, 'browser_observe', observe)
    context_calls = []
    original_context = Service.application_context
    def context(instance, *args, **kwargs):
        context_calls.append(args)
        return original_context(instance, *args, **kwargs)
    monkeypatch.setattr(Service, 'application_context', context)
    packages = []
    def credentials(config, package, parameters):
        packages.append(package)
        assert package['job']['url'] == current
        assert package['namespace'] == before['namespace']
        assert package['account']['credential_ref'] == 'credential:profile/accounts/default'
        return {'values_committed': True}
    monkeypatch.setattr('job_applier.managed_credentials.handle_credentials', credentials)
    assert host.dispatch({'instance_id': service.instance_id, 'session_id': session['id'],
        'driver_id': session['driver_id'], 'operation': 'credentials',
        'parameters': {'mode': mode}})['values_committed']
    assert len(packages) == 1
    assert len(context_calls) == 1  # Move the lookup; do not add normal-path work.
    assert service.job(session['job_id'])['url'] == original
    assert not service.attempt(attempt['id'])['completed_at']
