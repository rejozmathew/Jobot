"""Synthetic Workday account lifecycle; no live employer or private credentials."""
import asyncio
import json

import pytest


def credential_fixture(tmp_path, reference=None):
    path=tmp_path/'private.json'
    path.write_text(json.dumps({'accounts':{'default':{'email':'person@example.test','password':'synthetic-default'},
        'site':{'email':'person@example.test','password':'synthetic-site'}}}))
    cfg={'credential_profile_path':str(path),'credential_account_keys':{'credential:site':'site'}}
    package={'attempt':{'profile_json':{'identity':{'email':'person@example.test'}}},
        'account':{'credential_ref':reference},'job':{'url':'https://fixture.wd1.myworkdayjobs.com/Jobs/job/City/Role_R1'}}
    return cfg,package


def test_saved_portal_reference_selects_its_credential(tmp_path):
    from job_applier.managed_credentials import resolve_employer_credential
    cfg,package=credential_fixture(tmp_path,'credential:site')
    assert resolve_employer_credential(cfg,package)['password']=='synthetic-site'
    package['account']['credential_ref']='vault:unconfigured'
    with pytest.raises(ValueError,match='saved_credential_reference_unavailable'):
        resolve_employer_credential(cfg,package)


def test_new_portal_uses_retained_default_and_checks_identity(tmp_path):
    from job_applier.managed_credentials import resolve_employer_credential
    cfg,package=credential_fixture(tmp_path)
    value=resolve_employer_credential(cfg,package)
    assert value['credential_ref']=='credential:profile/accounts/default'
    package['attempt']['profile_json']['identity']['email']='another@example.test'
    with pytest.raises(ValueError,match='candidate_credential_identity_mismatch'):
        resolve_employer_credential(cfg,package)


def test_workday_auth_observes_consent_without_selecting_marketing():
    from test_workday_dom import observe
    html='''<form><h2>Create Account</h2><input id="email" type="email">
    <input id="pw" type="password"><input id="confirm" type="password">
    <label><input type="checkbox" required>I agree to the Privacy Policy</label>
    <label><input type="checkbox">Send me job alerts</label>
    <button>Create Account</button><a>Sign In</a></form>'''
    result=observe(html)
    assert result['auth_ui']['mode']=='create_account'
    assert result['native']['auth_consent']['enabled']
    assert result['native']['auth_switch_sign_in']['enabled']
    assert result['native']['auth_submit']['enabled']
    assert 'person@example.test' not in json.dumps(result)


class AuthHarness:
    def __init__(self, tmp_path, action='unknown'):
        from job_applier.workday_fast import FastRunner
        self.cfg,self.package=credential_fixture(tmp_path)
        self.package['namespace']='fixture.wd1.myworkdayjobs.com'
        self.package['attempt'].update(identity_id='person',settings_json={})
        self.package['account'].update(action=action,namespace=self.package['namespace'])
        self.calls=[];self.clicks=[];self.now=0
        self.runner=FastRunner(None,self.call,self.package,{'attempt_id':1,'worker_id':'w','fence':1},
            self.cfg,'fixture',clock=lambda:self.now,account_lock=lambda **kw:self.calls.append(('lock',kw)))
        self.runner.click=self.click
        self.observation=self.auth('create_account')
        self.runner.observe=self.observe

    def auth(self,mode,consent=False,**extra):
        return {'url':self.package['job']['url']+'/apply','step':'unknown','status':'login_required','auth':True,
            'auth_refs':{'email_ref':'#email','password_ref':'#pw','confirmation_ref':'#confirm' if mode=='create_account' else None},
            'auth_ui':dict(mode=mode,**extra),'native':{'auth_submit':{'enabled':True,'ref':'auth_submit'},
                'auth_switch_sign_in':{'enabled':True,'ref':'auth_switch_sign_in'},
                'auth_switch_create_account':{'enabled':True,'ref':'auth_switch_create_account'},
                **({'auth_consent':{'enabled':True,'ref':'auth_consent'}} if consent else {})}}

    def call(self,op,**kw):
        self.calls.append((op,kw))
        if op=='heartbeat':return {'control':'running'}
        if op=='browser_observe':return {'quiescent':True}
        if op=='application_context':return self.package
        if op=='record_account_event':
            self.package['account'].update(action={'confirmed':'sign_in','creation_pending':'reconcile','created_unverified':'verify'}[kw['state']],credential_ref=kw['credential_ref'])
        return {}

    async def click(self,action,observed):self.clicks.append(action);return True
    async def observe(self):return self.observation


def test_unrecognized_page_hands_off_to_visual_recovery_without_repeated_actions(tmp_path):
    h=AuthHarness(tmp_path);h.observation=h.auth('unknown')
    async def sleep(seconds):h.now+=seconds
    h.runner.sleep=sleep
    result=asyncio.run(h.runner.run(seconds=5))
    again=asyncio.run(h.runner.run(seconds=5))
    assert result['status']==again['status']=='authentication_required'
    assert result['recovery']['kind']=='unsupported_or_changed_auth_ui'
    assert result['recovery']['next_operation']=={'operation':'browser','parameters':{'method':'screenshot'}}
    assert not h.clicks
    errors=[kw for op,kw in h.calls if op=='event' and kw['event_type']=='recovery']
    assert len(errors)==1 and errors[0]['payload']['error_type']=='workday_auth_controls_unrecognized'


def test_private_screenshot_restores_mask_after_capture_error(tmp_path):
    from job_applier.managed_credentials import capture_private_screenshot,MASK_CREDENTIALS,UNMASK_CREDENTIALS
    calls=[]
    class Page:
        async def evaluate(self,script):calls.append(script)
        async def screenshot(self,path):raise OSError('Synthetic capture failure')
    with pytest.raises(OSError,match='Synthetic capture failure'):
        asyncio.run(capture_private_screenshot(Page(),tmp_path/'shot.png'))
    assert calls==[MASK_CREDENTIALS,UNMASK_CREDENTIALS]


def test_new_account_records_pending_before_click_then_confirms_sign_in(tmp_path,monkeypatch):
    from job_applier import workday_auth
    h=AuthHarness(tmp_path)
    async def fill(*a):return {'values_committed':True,'credential_ref':'credential:profile/accounts/default'}
    monkeypatch.setattr(workday_auth,'fill_page_credentials',fill)
    h.observation=h.auth('create_account',consent=True)
    assert asyncio.run(workday_auth.advance_auth(h.runner,h.observation))['status']=='progress'
    assert h.clicks==['native_auth_consent']
    h.observation=h.auth('create_account')
    assert asyncio.run(workday_auth.advance_auth(h.runner,h.observation))['status']=='progress'
    assert h.clicks[-1]=='native_auth_submit'
    assert any(op=='record_account_event' and kw['state']=='creation_pending' for op,kw in h.calls)
    h.observation=h.auth('sign_in')
    assert asyncio.run(workday_auth.advance_auth(h.runner,h.observation))['status']=='progress'
    assert h.clicks.count('native_auth_submit')==2
    observed={'auth':False,'step':'my_information'}
    asyncio.run(workday_auth.confirm_authenticated(h.runner,observed))
    assert h.package['account']['action']=='sign_in'
    assert h.calls[-1]==('lock',{'release':True})


@pytest.mark.parametrize('action',['sign_in','reconcile','verify'])
def test_existing_or_uncertain_account_switches_to_sign_in_without_creation(tmp_path,action):
    from job_applier.workday_auth import advance_auth
    h=AuthHarness(tmp_path,action)
    result=asyncio.run(advance_auth(h.runner,h.observation))
    assert result['status']=='progress'
    assert h.clicks==['native_auth_switch_sign_in']
    assert not any(op=='record_account_event' for op,_ in h.calls)


def test_stalled_creation_is_not_replayed_across_helper_calls(tmp_path,monkeypatch):
    from job_applier import workday_auth
    h=AuthHarness(tmp_path)
    async def fill(*a):return {'values_committed':True,'credential_ref':'credential:profile/accounts/default'}
    monkeypatch.setattr(workday_auth,'fill_page_credentials',fill)
    asyncio.run(workday_auth.advance_auth(h.runner,h.observation))
    h.now=10
    result=asyncio.run(workday_auth.advance_auth(h.runner,h.observation))
    assert h.clicks==['native_auth_submit']
    assert result['status']=='authentication_required'
    assert result['reason']=='workday_create_account_unconfirmed'


def test_disabled_sign_in_button_is_checked_again_after_private_fill(tmp_path,monkeypatch):
    from job_applier import workday_auth
    h=AuthHarness(tmp_path,'sign_in');h.observation=h.auth('sign_in')
    h.observation['native']['auth_submit']['enabled']=False
    async def fill(*a):
        h.observation=h.auth('sign_in')
        return {'values_committed':True,'credential_ref':'credential:profile/accounts/default'}
    monkeypatch.setattr(workday_auth,'fill_page_credentials',fill)
    result=asyncio.run(workday_auth.advance_auth(h.runner,h.observation))
    assert result['status']=='progress' and h.clicks==['native_auth_submit']


def test_employer_creation_confirmation_is_saved_before_mail_handoff(tmp_path):
    from job_applier.workday_auth import advance_auth
    h=AuthHarness(tmp_path)
    h.runner.state['authentication']={'submitted':'create_account','credential_ref':'credential:profile/accounts/default'}
    h.observation=h.auth('unknown',account_created=True,challenge=True)
    result=asyncio.run(advance_auth(h.runner,h.observation))
    assert result['reason']=='workday_verification_required'
    assert any(op=='record_account_event' and kw['state']=='created_unverified' for op,kw in h.calls)
    assert h.clicks==[]


@pytest.mark.parametrize('extra,reason',[({'challenge':True},'workday_verification_required'),
    ({'credential_rejected':True},'workday_credentials_rejected'),
    ({'unknown_required_consent':True},'workday_consent_needs_inspection')])
def test_auth_exceptions_return_to_executor_without_blind_clicks(tmp_path,extra,reason):
    from job_applier.workday_auth import advance_auth
    h=AuthHarness(tmp_path);h.observation=h.auth('sign_in',**extra)
    result=asyncio.run(advance_auth(h.runner,h.observation))
    assert result['reason']==reason and h.clicks==[]
