"""Private portal overrides, exercised only with synthetic accounts and secrets."""
import json
from unittest.mock import patch

from fastapi.testclient import TestClient
from test_operator_ui import make_test_environment, BASE_URL, WORKER_TOKEN
from job_applier.managed_credentials import resolve_employer_credential


def setup(tmp_path, reference='credential:profile/accounts/default'):
    service, _, app = make_test_environment(tmp_path)
    path = tmp_path / 'credentials.json'
    path.write_text(json.dumps({'unrelated': {'keep': True}, 'accounts': {
        'default': {'email': 'candidate@example.test', 'password': 'original-default'},
        'existing': {'email': 'candidate@example.test', 'password': 'original-existing'}}}))
    config = {'credential_profile_path': str(path),
              'credential_account_keys': {'credential:existing': 'existing'}}
    service.executor_config = config
    account = service.account_update(namespace='careers.example.test', identity_id='candidate',
        state='confirmed', credential_ref=reference, request_id='account-1', evidence='Synthetic sign-in')
    package = {'attempt': {'identity_id': 'candidate', 'profile_json': {
        'identity': {'email': 'candidate@example.test'}}},
        'account': service.account_strategy(namespace='careers.example.test', identity_id='candidate')}
    client = TestClient(app, base_url=BASE_URL)
    client.get('/')
    client.headers['X-JobBot-Instance'] = service.instance_id
    return service, config, package, path, client, account['id']


def test_override_save_resolve_update_remove_preserves_account_history(tmp_path):
    service, config, package, path, client, account_id = setup(tmp_path, 'credential:existing')
    before = service.account_strategy(namespace='careers.example.test', identity_id='candidate')
    password = ' Synthetic-override-12! '
    response = client.post('/v1/set_portal_password', json={'account_id': account_id, 'password': password})
    assert response.status_code == 200, response.text
    assert password not in response.text
    resolved = resolve_employer_credential(config, package)
    assert resolved['password'] == password
    package['account']['credential_ref'] = resolved['credential_ref']
    assert client.post('/v1/set_portal_password', json={'account_id': account_id, 'password': 'Updated-12!'}).status_code == 200
    assert resolve_employer_credential(config, package)['password'] == 'Updated-12!'
    view = client.post('/v1/view', json={}).json()
    assert view['accounts'][0]['password_source'] == 'override'
    assert password not in json.dumps(view) and 'Updated-12!' not in json.dumps(view)
    assert client.post('/v1/remove_portal_password', json={'account_id': account_id}).status_code == 200
    assert resolve_employer_credential(config, package)['password'] == 'original-existing'
    assert service.account_strategy(namespace='careers.example.test', identity_id='candidate') == before
    assert json.loads(path.read_text())['unrelated'] == {'keep': True}
    assert 'Updated-12!' not in path.read_text()
    with service.read() as db:
        assert password not in '\n'.join(db.iterdump())


def test_override_does_not_cross_candidate_or_portal_and_keeps_default(tmp_path):
    service, config, package, path, client, account_id = setup(tmp_path)
    assert client.post('/v1/set_portal_password', json={'account_id': account_id, 'password': 'Only-this-portal!'}).status_code == 200
    package['account']['namespace'] = 'another.example.test'
    assert resolve_employer_credential(config, package)['password'] == 'original-default'
    package['account']['namespace'] = 'careers.example.test'
    package['attempt']['identity_id'] = 'other-candidate'
    assert resolve_employer_credential(config, package)['password'] == 'original-default'
    assert json.loads(path.read_text())['accounts']['default']['password'] == 'original-default'


def test_password_mutations_require_operator_and_valid_account(tmp_path):
    service, config, package, path, client, account_id = setup(tmp_path)
    before = path.read_bytes()
    response = client.post('/v1/set_portal_password', json={'account_id': account_id, 'password': 'Nope!'},
        headers={'Authorization': 'Bearer ' + WORKER_TOKEN})
    assert response.status_code == 403
    for payload in ({'account_id': account_id, 'password': ''}, {'account_id': account_id, 'password': 42},
                    {'account_id': 999999, 'password': 'Nope!'}, {'account_id': True, 'password': 'Nope!'}):
        assert client.post('/v1/set_portal_password', json=payload).status_code == 422
    assert path.read_bytes() == before


def test_failed_atomic_write_keeps_original_file_and_removes_temp_secret(tmp_path):
    service, config, package, path, client, account_id = setup(tmp_path)
    before = path.read_bytes()
    with patch('job_applier.portal_credentials.os.replace', side_effect=PermissionError('private path')):
        response = client.post('/v1/set_portal_password', json={'account_id': account_id, 'password': 'Never-leak-this!'})
    assert response.status_code == 422
    assert response.json() == {'error': 'credential_profile_write_failed'}
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('.portal-password-*'))


def test_missing_or_malformed_private_store_does_not_break_dashboard(tmp_path):
    service, config, package, path, client, account_id = setup(tmp_path)
    for content in ('broken-json', '[]', '{"portal_password_overrides": []}'):
        path.write_text(content)
        response = client.post('/v1/set_portal_password', json={'account_id': account_id, 'password': 'Never-leak-this!'})
        assert response.status_code == 422
        assert path.read_text() == content
        response = client.post('/v1/view', json={})
        assert response.status_code == 200
        assert response.json()['accounts'][0]['password_editable'] is False
    path.unlink()
    assert client.post('/v1/view', json={}).status_code == 200


def test_verified_namespace_alias_and_retained_reference_use_same_override(tmp_path):
    service, config, package, path, client, account_id = setup(tmp_path)
    service.namespace_alias(alias='careers.example.test', canonical='canonical.example.test', verification_evidence='Synthetic shared account')
    assert client.post('/v1/set_portal_password', json={'account_id': account_id, 'password': 'Alias-only-12!'}).status_code == 200
    package['account'] = service.account_strategy(namespace='careers.example.test', identity_id='candidate')
    resolved = resolve_employer_credential(config, package)
    assert resolved['password'] == 'Alias-only-12!'
    # A successful executor observation may retain the override reference in the ledger.
    service.account_update(namespace='canonical.example.test', identity_id='candidate', state='confirmed',
        credential_ref=resolved['credential_ref'], request_id='confirmed-override', evidence='Synthetic sign-in')
    package['account'] = service.account_strategy(namespace='canonical.example.test', identity_id='candidate')
    assert client.post('/v1/remove_portal_password', json={'account_id': account_id}).status_code == 200
    assert resolve_employer_credential(config, package)['password'] == 'original-default'


def test_password_editor_masks_confirms_submits_and_clears_secret():
    from test_dispatch_queue_ui import dashboard_check
    dashboard_check(r'''
w.noRefresh();
const dialog=doc.getElementById('portal-password-dialog');
dialog.showModal=()=>{dialog.open=true;};
dialog.close=()=>{dialog.open=false;dialog.dispatchEvent(new w.Event('close'));};
const account={id:7,namespace:'careers.example.test',email:'candidate@example.test',identity_id:'candidate',password_source:'default',password_editable:true};
w.drawAccounts({accounts:[account],runs:[]});
doc.querySelector('#account-rows button').click();
assert(dialog.open,'Editor must open');
const password=doc.getElementById('portal-password'),confirm=doc.getElementById('portal-password-confirm');
assert(password.type==='password'&&confirm.type==='password','Password fields must be masked');
assert(password.value===''&&confirm.value==='','Never preload saved secrets');
let calls=[];w.fetch=async(path,options)=>{calls.push([path,JSON.parse(options.body)]);return {ok:true,status:200,json:async()=>({})};};
password.value=' Synthetic-12! ';confirm.value='different';
await doc.getElementById('portal-password-form').onsubmit({preventDefault(){}});
assert(calls.length===0&&doc.getElementById('portal-password-error').textContent.includes('match'),'Mismatched confirmation submitted');
confirm.value=password.value;
await doc.getElementById('portal-password-form').onsubmit({preventDefault(){}});
assert(calls[0][0]==='/v1/set_portal_password'&&calls[0][1].account_id===7,'Wrong endpoint or account');
assert(calls[0][1].password===' Synthetic-12! ','Password was trimmed');
assert(!dialog.open&&password.value===''&&confirm.value==='','Secret retained after save');
account.password_source='override';w.drawAccounts({accounts:[account],runs:[]});doc.querySelector('#account-rows button').click();
assert(!doc.getElementById('remove-portal-password').hidden,'Remove action missing');
await doc.getElementById('remove-portal-password').onclick();
assert(calls[1][0]==='/v1/remove_portal_password'&&!('password' in calls[1][1]),'Removal must not send a password');
doc.querySelector('#account-rows button').click();password.value='cancel-me';doc.getElementById('close-portal-password').click();
assert(password.value===''&&!dialog.open,'Cancel retained secret');
doc.querySelector('#account-rows button').click();password.value='disconnect-me';w.disconnect();
assert(password.value===''&&!dialog.open,'Disconnect retained secret');
''')
