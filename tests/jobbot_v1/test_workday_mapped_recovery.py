"""The demonstrated Wiley mapping/Simplify actuation gaps, using synthetic DOM."""
import asyncio
import json
import subprocess

from test_workday_dom import ROOT,JSDOM


def test_observed_mapping_survives_rerender_and_fills_privately():
    from job_applier.managed_credentials import FILL_SELECTED
    from job_applier.workday_fast import WORKDAY_OBSERVE,WORKDAY_CLICK
    script=r'''
const {JSDOM}=require(process.argv[1]),fs=require('fs'),d=JSON.parse(fs.readFileSync(0,'utf8'));
const dom=new JSDOM('<main></main>',{url:'https://tenant.wd1.myworkdayjobs.com/Jobs/job/City/Role_R1',runScripts:'outside-only'});
const w=dom.window;
w.HTMLElement.prototype.getBoundingClientRect=()=>({width:100,height:20});
w.HTMLElement.prototype.getClientRects=()=>[{width:100,height:20}];
w.requestAnimationFrame=f=>setTimeout(f,0);
function render(id){w.document.querySelector('main').innerHTML='<form><h2>Sign In</h2><label for="'+id+'">Email Address *</label><input id="'+id+'" type="text"><label for="pw">Password</label><input id="pw" type="password"><button type="button">Continue securely</button></form>';}
(async()=>{
render('input-14');const first=w.eval(d.observe)({page_signature:'same-screen'});
const email=first.inventory.find(c=>c.label==='Email Address *').ref;
const password=first.inventory.find(c=>c.type==='password').ref;
const button=first.inventory.find(c=>c.text==='Continue securely').ref;
if(first.auth_refs.email_ref!=='[id="input-14"]')throw Error('labelled text email was missed');
render('input-29');const fresh=w.eval(d.observe)({page_signature:'same-screen'});
if(fresh.inventory.find(c=>c.label==='Email Address *').ref!==email)throw Error('ordinary rerender lost mapping');
let clicks=0;w.document.querySelector('button').onclick=()=>clicks++;
const filled=await w.eval(d.fill)({email_ref:email,password_ref:password,email:'person@example.test',password:'synthetic-retained'});
if(!filled.values_committed)throw Error(JSON.stringify(filled));
const clicked=w.eval(d.click)({ref:button,step:'unknown',page_signature:'same-screen'});
if(!clicked.clicked||clicks!==1)throw Error('mapped button not clicked');
if(JSON.stringify(first).includes('synthetic-retained')||JSON.stringify(filled).includes('synthetic-retained'))throw Error('secret output');
console.log(JSON.stringify({mapped:true,clicked:true}));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script,str(JSDOM)],input=json.dumps({'observe':WORKDAY_OBSERVE,'click':WORKDAY_CLICK,'fill':FILL_SELECTED}),text=True,capture_output=True,check=True)
    assert json.loads(result.stdout)=={'mapped':True,'clicked':True}


def test_simplify_employer_sign_in_requires_credential_evidence_and_is_callable():
    from test_simplify_boundary import DOMSeamPort,FakeClockSleeper
    from job_applier.simplify_boundary import SimplifyBoundary
    initial={'status':'login_required','panel':True,'login_kind':'employer','page_signature':'auth',
             'controls':{'sign_in':{'ref':'extension-sign-in','enabled':True}}}
    page=DOMSeamPort(initial);clock=FakeClockSleeper()
    boundary=SimplifyBoundary(page,clock=clock.clock,sleeper=clock.sleep)
    denied=asyncio.run(boundary.perform('sign_in'))
    assert denied['reason']=='retained_credential_use_unverified' and not page.clicks
    page.observation=dict(initial,login_kind='simplify')
    assert asyncio.run(boundary.perform('sign_in',credential_evidence='Synthetic retained-input contract'))['reason']=='simplify_login_is_not_employer_sign_in'
    page.observation=initial
    def clicked(args):
        page.observation={'status':'complete','panel':True,'page_signature':'my-information','controls':{}}
        return {'status':'clicked'}
    page._on_click=clicked
    response=asyncio.run(boundary.perform('sign_in',credential_evidence='Synthetic retained-input contract'))
    assert response['execution']=='clicked' and response['native_takeover_authorized'] and len(page.clicks)==1


def test_mapped_auth_updates_runner_account_state_without_rematching(tmp_path,monkeypatch):
    from test_workday_credentials import AuthHarness
    from job_applier import workday_auth
    from job_applier.workday_fast import screen_inventory
    h=AuthHarness(tmp_path,'reconcile');h.observation=h.auth('sign_in')
    h.observation.update(page_signature='same-screen',inventory=[{'ref':'wd:chosen','text':'Continue securely','enabled':True}])
    h.observation['auth_refs']['email_ref']=None
    h.observation['native']={}
    seen=[]
    async def fill(cfg,package,page,refs):
        seen.append(refs);return {'values_committed':True,'credential_ref':'credential:profile/accounts/default'}
    monkeypatch.setattr(workday_auth,'fill_page_credentials',fill)
    mapping={'screen_key':screen_inventory(h.observation,h.package)['screen_key'],'account_mode':'sign_in',
             'credentials':{'email_ref':'wd:chosen-email','password_ref':'wd:chosen-password'},
             'action':{'source':'native','ref':'wd:chosen'}}
    response=asyncio.run(workday_auth.recover_screen(h.runner,mapping))
    assert response['status']=='progress' and seen==[mapping['credentials']]
    assert h.clicks==['native_mapped']
    assert not any(op=='writer_state' and kw.get('state')=='active' for op,kw in h.calls), 'A native click is not an outstanding Simplify writer'
    assert asyncio.run(workday_auth.recover_screen(h.runner,mapping))['reason']=='screen_action_already_attempted'
    asyncio.run(workday_auth.confirm_authenticated(h.runner,{'auth':False,'step':'my_information'}))
    assert h.package['account']['action']=='sign_in' and h.runner.state['authentication']['complete']


def test_new_native_application_chooser_is_new_screen_evidence(tmp_path):
    from test_workday_credentials import AuthHarness
    from job_applier.workday_fast import screen_inventory
    h=AuthHarness(tmp_path)
    before={'page_signature':'unchanged-role-heading','step':'unknown','auth_ui':{'mode':'unknown'},
            'inventory':[{'tag':'BUTTON','text':'Apply'}]}
    after=dict(before,inventory=before['inventory']+[{'tag':'BUTTON','text':'Apply Manually'}, {'tag':'BUTTON','text':'Autofill with Resume'}])
    assert screen_inventory(before,h.package)['screen_key']!=screen_inventory(after,h.package)['screen_key']


def test_workday_account_navigation_outside_form_is_not_submission(tmp_path,monkeypatch):
    from test_workday_dom import observe
    from test_workday_credentials import AuthHarness
    from job_applier import workday_auth
    from job_applier.workday_fast import screen_inventory
    html='<form><h2>Create Account</h2><input id="email" type="email"><input id="pw" type="password"><input id="confirm" type="password"><button>Create Account</button></form><button data-automation-id="signInLink">Sign In</button>'
    page=observe(html)
    assert page['native'].get('auth_switch_sign_in',{}).get('enabled'), 'Account view navigation can be outside its form'
    h=AuthHarness(tmp_path,'reconcile');h.observation=h.auth('create_account')
    h.observation.update(page_signature='create-view',inventory=[{'ref':'wd:switch','text':'Sign In','enabled':True}])
    async def fill(*args):return {'values_committed':True,'credential_ref':'credential:profile/accounts/default'}
    monkeypatch.setattr(workday_auth,'fill_page_credentials',fill)
    mapping={'screen_key':screen_inventory(h.observation,h.package)['screen_key'],'account_mode':'sign_in',
        'credentials':{'email_ref':'#email','password_ref':'#pw'},'action':{'source':'native','ref':'wd:switch'}}
    assert asyncio.run(workday_auth.recover_screen(h.runner,mapping))['status']=='progress'
    assert not h.runner.state.get('authentication',{}).get('submitted'), 'Opening Sign In must not start its submission timer'
