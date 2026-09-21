"""Workday account credentials stay with native auth, using synthetic pages only."""
import asyncio
import json
import subprocess

import pytest


@pytest.mark.parametrize('operation', ['sign_in', 'autofill', 'start', 'continue'])
def test_workday_auth_does_not_accept_a_credential_reference_as_extension_evidence(operation):
    from test_simplify_boundary import DOMSeamPort, FakeClockSleeper
    from job_applier.simplify_boundary import SimplifyBoundary
    page=DOMSeamPort({'panel':True,'status':'login_required' if operation=='sign_in' else 'ready',
        'login_kind':'employer','native_authentication_required':True,
        'controls':{operation:{'ref':'extension-action','enabled':True}}},
        url='https://fixture.wd1.myworkdayjobs.com/Jobs/login')
    clock=FakeClockSleeper()
    boundary=SimplifyBoundary(page,clock=clock.clock,sleeper=clock.sleep)
    response=asyncio.run(boundary.perform(operation,credential_evidence='credential:profile/accounts/default'))
    assert response['reason']=='workday_native_authentication_required'
    assert response['execution']=='not_executed' and not page.clicks
    assert 'fast_forward' in response['instruction']


def test_workday_login_transition_keeps_native_auth_until_the_form_opens(tmp_path,monkeypatch):
    from test_workday_credentials import AuthHarness
    from job_applier import workday_auth
    from job_applier.workday_fast import choose
    h=AuthHarness(tmp_path)
    h.cfg['cdp_url']='http://127.0.0.1:1234'
    fills=[]
    async def fill(config,package,page,refs):
        fills.append(dict(refs))
        return {'values_committed':True,'credential_ref':'credential:profile/accounts/default'}
    monkeypatch.setattr(workday_auth,'fill_page_credentials',fill)
    async def sleep(seconds):
        h.now+=seconds
        if h.runner.state.get('authentication',{}).get('submitted')=='create_account':
            h.observation=(dict(url=h.package['job']['url']+'/apply',step='unknown',status='missing',
                auth=False,auth_ui={'mode':'unknown'},native={},controls={}) if h.now<2 else h.auth('sign_in'))
    async def click(action,observed):
        h.clicks.append(action)
        if action=='native_auth_submit' and observed['auth_ui']['mode']=='sign_in':
            h.observation={'url':h.package['job']['url']+'/apply','step':'my_information',
                'status':'ready','auth':False,'native':{},'controls':{'autofill':{'enabled':True,'ref':'fill'}}}
        elif action=='autofill':h.observation['status']='active'
        return True
    h.runner.sleep=sleep;h.runner.click=click
    response=asyncio.run(h.runner.run(seconds=4))
    assert response['status']=='waiting'
    assert h.clicks==['native_auth_submit','native_auth_submit','autofill']
    assert len(fills)==2 and fills[0]['confirmation_ref'] and not fills[1]['confirmation_ref']
    assert h.package['account']['state']=='confirmed'
    assert choose({'step':'unknown','status':'ready','auth':False,'native_authentication_required':True,
        'controls':{'autofill':{'enabled':True}}},{})=='authentication_required'


def test_mapped_workday_sign_in_uses_native_credentials_even_with_extension_evidence(tmp_path):
    from test_workday_credentials import AuthHarness
    from job_applier.workday_auth import recover_screen
    from job_applier.workday_fast import screen_inventory
    h=AuthHarness(tmp_path,'sign_in');h.observation=h.auth('sign_in')
    h.observation.update(page_signature='sign-in',inventory=[],simplify_inventory=[
        {'ref':'extension-sign-in','operation':'sign_in','label':'Sign In & Autofill','enabled':True}])
    mapping={'screen_key':screen_inventory(h.observation,h.package)['screen_key'],'account_mode':'sign_in',
        'credentials':h.observation['auth_refs'],'credential_evidence':'credential:profile/accounts/default',
        'action':{'source':'simplify','ref':'extension-sign-in'}}
    response=asyncio.run(recover_screen(h.runner,mapping))
    assert response['reason']=='workday_native_authentication_required'
    assert response['execution']=='not_executed' and not h.clicks
    assert not any(op=='action_start' for op,_ in h.calls)


@pytest.mark.parametrize('surface', ['password_form', 'email_chooser', 'loading_login', 'late_password_form', 'application'])
def test_extension_click_uses_current_native_auth_state(surface):
    from test_workday_dom import JSDOM
    from job_applier.simplify_boundary import OBSERVE,CLICK
    if not JSDOM.exists():pytest.skip('optional jsdom fixture dependency not installed')
    script=r'''
const fs=require('fs'),{JSDOM}=require(process.argv[1]),d=JSON.parse(fs.readFileSync(0,'utf8'));
const url='https://fixture.wd1.myworkdayjobs.com/Jobs/'+(d.surface==='loading_login'?'login':'job/City/Role_R1/apply');
const dom=new JSDOM('<main></main><div class="simplify-jobs-shadow-root"><button>Autofill This Page</button><button>Stop Autofill</button></div>',{url,runScripts:'outside-only'});
const w=dom.window;Object.defineProperty(w.crypto,'subtle',{value:require('crypto').webcrypto.subtle});w.TextEncoder=TextEncoder;
w.HTMLElement.prototype.getBoundingClientRect=function(){return this.hidden?{width:0,height:0}:{width:100,height:30}};
const form='<form><input type="email"><input type="password"><button>Sign In</button></form>';
const main=w.document.querySelector('main');
main.innerHTML=d.surface==='password_form'?form:d.surface==='email_chooser'?'<button data-automation-id="SignInWithEmailButton">Sign in with email</button>':'';
let fills=0,stops=0;const buttons=w.document.querySelector('.simplify-jobs-shadow-root').querySelectorAll('button');
buttons[0].onclick=()=>fills++;buttons[1].onclick=()=>stops++;
(async()=>{
const observed=await w.eval(d.observe);
if(d.surface==='late_password_form')main.innerHTML=form;
const args=kind=>({operation:kind,ref:observed.controls[kind].ref,url:observed.url,page_ref:observed.page_ref});
const result=w.eval(d.click)(args('autofill')),stop=w.eval(d.click)(args('stop'));
console.log(JSON.stringify({auth:observed.native_authentication_required,result,stop,fills,stops}));w.close();
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script,str(JSDOM)],input=json.dumps({'observe':OBSERVE,'click':CLICK,'surface':surface}),
        text=True,capture_output=True,check=True)
    data=json.loads(result.stdout)
    assert data['auth']==(surface not in ('application','late_password_form'))
    assert data['fills']==(1 if surface=='application' else 0)
    if surface!='application':assert data['result']['reason']=='workday_native_authentication_required'
    assert data['stops']==1 and data['stop']['clicked']


@pytest.mark.parametrize('overwrite', ['after_fill', 'after_hover', 'normalized_email'])
def test_native_sign_in_refills_credentials_replaced_after_initial_verification(tmp_path,overwrite):
    from test_embedded_forms import fixture_browser
    from job_applier.managed_credentials import FILL_SELECTED
    from job_applier.workday_fast import FastRunner,WORKDAY_OBSERVE
    async def check():
        async with fixture_browser(tmp_path,mode='top') as (page,*_):
            await page.evaluate("""document.body.innerHTML='<header><button>Sign In</button></header><div role="dialog"><form><label>Email Address<input id="email" type="text"></label><label>Password<input id="password" type="password"></label><button id="sign-in" type="button">Sign In</button></form></div>';
                window.accepted=0;window.retainedAtClick=false;
                document.getElementById('sign-in').onclick=e=>{if(e.isTrusted){window.accepted++;window.retainedAtClick=document.getElementById('email').value==='approved@example.test'&&document.getElementById('password').value==='synthetic-approved';}}""")
            if overwrite=='normalized_email':
                await page.evaluate("document.getElementById('email').oninput=e=>e.target.value=e.target.value.toLowerCase()")
            observed=await page.evaluate_function(WORKDAY_OBSERVE,{})
            email='Approved@Example.Test' if overwrite=='normalized_email' else 'approved@example.test'
            filled=await page.evaluate_function(FILL_SELECTED,dict(observed['auth_refs'],email=email,password='synthetic-approved'))
            assert filled['values_committed']
            mutation="document.getElementById('password').value='synthetic-generated-longer-password'"
            if overwrite!='after_hover':await page.evaluate(mutation)
            else:
                original=page._session.call
                async def call(method,params=None,**kwargs):
                    response=await original(method,params,**kwargs)
                    if method=='Input.dispatchMouseEvent' and params.get('type')=='mouseMoved':
                        await page.evaluate(mutation)
                    return response
                page._session.call=call
            fresh=await page.evaluate_function(WORKDAY_OBSERVE,{})
            fresh['credential_token']=filled.get('credential_token')
            runner=FastRunner(page,lambda *a,**kw:None,{'attempt':{'profile_json':{},'settings_json':{}},'job':{}},{},{},'fixture')
            assert await runner.click('native_auth_submit',fresh)
            result=runner.last_click_result
            assert await page.evaluate('window.retainedAtClick'), 'A later autofill must not supply the password used by native Sign In'
            assert await page.evaluate('window.accepted')==1
            assert result['credentials_verified_before_click'] and result['credentials_refilled_before_click']
            assert 'synthetic-approved' not in json.dumps(result)
    asyncio.run(check())


@pytest.mark.parametrize('mapped',[False,True])
def test_auth_threads_private_receipt_to_activation_and_records_only_match_evidence(tmp_path,monkeypatch,mapped):
    from test_workday_credentials import AuthHarness
    from job_applier import workday_auth
    from job_applier.workday_fast import screen_inventory
    h=AuthHarness(tmp_path,'sign_in');h.observation=h.auth('sign_in')
    h.observation.update(page_signature='sign-in',inventory=[{'ref':'wd:sign-in','text':'Sign In','enabled':True,'auth_form':True}])
    async def fill(*args):
        return {'values_committed':True,'credential_ref':'credential:profile/accounts/default','credential_token':'opaque-page-receipt'}
    async def click(action,observed):
        assert observed.get('credential_token')=='opaque-page-receipt'
        h.runner.last_click_result={'execution':'clicked','credentials_verified_before_click':True,'credentials_refilled_before_click':True}
        return True
    monkeypatch.setattr(workday_auth,'fill_page_credentials',fill);h.runner.click=click
    if mapped:
        result=asyncio.run(workday_auth.recover_screen(h.runner,{
            'screen_key':screen_inventory(h.observation,h.package)['screen_key'],
            'account_mode':'sign_in','credentials':h.observation['auth_refs'],
            'action':{'source':'native','ref':'wd:sign-in'}}))
    else:result=asyncio.run(workday_auth.advance_auth(h.runner,h.observation))
    assert result['status']=='progress'
    assert h.runner.report('authentication_required')['credential_check']=={
        'credentials_verified_before_click':True,'credentials_refilled_before_click':True}
    assert 'opaque-page-receipt' not in json.dumps(h.runner.state)
    assert any(op=='event' and kw['event_type']=='field_verified' and kw['payload'].get('credentials_refilled_before_click') for op,kw in h.calls)
