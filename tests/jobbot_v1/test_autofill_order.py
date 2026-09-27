"""Autofill precedes residual helpers; entry/authentication and writer ownership remain intact."""
import asyncio

import pytest

from job_applier.browser_controls import next_operation, observe
from job_applier.simplify_boundary import SimplifyBoundary


def form(status='needs_review'):
    return {'status': status, 'stage': {'name': 'candidate_profile'}, 'native': {},
            'controls': {'autofill': {'ref': 'fill', 'enabled': True},
                         'continue': {'ref': 'next', 'enabled': True}},
            'inventory': [], 'writer_safe': True, 'settled_evidence': True}


@pytest.mark.parametrize('status', ['ready', 'complete', 'needs_review'])
@pytest.mark.parametrize('portal', ['unknown', 'icims', 'greenhouse', 'workday', 'linkedin'])
def test_accessible_form_recommends_autofill_before_portal_residuals(portal, status):
    observed = form(status)
    observed.update(step='my_information', linkedin={'kind': 'easy_apply', 'modal': True})
    if portal == 'workday': observed['workday'] = True
    if portal == 'greenhouse': observed.update(greenhouse=True, autofill_receipt={})
    result = next_operation(portal, observed, quiescent=True)
    assert result['operation'] == 'browser'
    assert result['parameters']['action'] == 'autofill'


@pytest.mark.parametrize('status', ['ready', 'complete', 'needs_review'])
def test_boundary_initial_autofill_precedes_continue_and_stale_review(status):
    observed = form(status)
    assert SimplifyBoundary.decide(observed)['action'] == 'autofill'
    observed['autofill_attempted'] = True
    assert SimplifyBoundary.decide(observed)['action'] == 'continue'


def test_workday_review_residuals_begin_with_available_autofill():
    from job_applier.workday_fast import choose
    observed = form()
    observed.update(workday=True, step='review', blocking_errors=['Required answer'])
    observed['native']['submit'] = {'enabled': True}
    assert choose(observed, {}) == 'autofill'
    observed['autofill_attempted'] = True
    assert choose(observed, {}) == 'blocked'


def test_icims_posting_opens_apply_before_repairing_footer_fields(monkeypatch):
    from job_applier.icims_fast import IcimsRunner
    from job_applier import icims_fast
    from job_applier.managed_shared import ProtocolError
    events=[]
    runner=IcimsRunner(type('Page', (), {})(), lambda *a, **k: {},
        {'attempt': {'profile_json': {}, 'settings_json': {}}}, {}, {}, 'fixture')
    async def read():
        runner.last={'status':'missing','native':{'apply':{'ref':'apply','enabled':True}},'inventory':[]}
        runner.audit={'stage':{'name':'email_entry'},'required_missing':[{'ref':'footer-email'}],
            'invalid_blockers':[],'credential_tasks':[],'unknown_controls':[], 'coverage':{'unresolved_documents':[]}}
    async def gate(): return True
    async def checkpoint(): pass
    async def repair(plans):
        events.append('repair');raise ProtocolError('stop_requested')
    async def click(*args):
        events.append('apply');raise ProtocolError('stop_requested')
    runner.read=read;runner.gate=gate;runner.checkpoint=checkpoint;runner.repair=repair
    monkeypatch.setattr(icims_fast,'click_control',click)
    asyncio.run(runner.run())
    assert events==['apply']


def test_generic_receipt_survives_reconnect_but_new_form_step_autofills(tmp_path, monkeypatch):
    from test_form_audit import fixture_html, icims_browser
    import test_embedded_forms as fixture
    monkeypatch.setattr(fixture, 'FORM_HTML', fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page, package, _):
            page.application_package=package
            # A stale completion label is not a record of filling this form.
            first=await observe(page, package)
            assert not first.get('autofill_attempted')
            await page.evaluate("document.querySelector('.simplify-jobs-shadow-root').shadowRoot.querySelector('button').addEventListener('click',()=>setTimeout(()=>fixture.setSimplify('needs_review'),250))")
            result=await SimplifyBoundary(page, budget_seconds=8).perform('autofill',automatic=True)
            assert result['execution']=='clicked',result
            second=await observe(page, package)
            assert second['autofill_attempted']
            repeat=await SimplifyBoundary(page,budget_seconds=2).perform('autofill',automatic=True)
            assert repeat['execution']=='not_executed'
            await page.evaluate("fixture.screening()")
            third=await observe(page,package)
            assert not third['autofill_attempted']
            assert third['autofill_page_key']!=second['autofill_page_key']
    asyncio.run(run())


def test_profile_with_email_is_not_misclassified_as_email_entry(tmp_path,monkeypatch):
    from test_form_audit import fixture_html,icims_browser
    import test_embedded_forms as fixture
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page,package,_):
            await page.evaluate("document.querySelectorAll('h1,h2,h3,[aria-current],input[type=password]').forEach(e=>e.remove())")
            observed=await observe(page,package)
            assert observed['stage']['name'] not in ('email_entry','sign_in','create_account')
    asyncio.run(run())


@pytest.mark.parametrize('label',['Email Address','Email *','Username'])
@pytest.mark.parametrize('password', [False, True])
def test_access_form_with_text_email_stays_authentication(label, password):
    from test_greenhouse_recovery import form_dom
    html=f'<label for="email">{label}</label><input id="email">'+ ('<input type="password">' if password else '') + '<button>Continue</button>'
    observed=form_dom(html,[{'method':'observe'}])['results'][0]
    assert observed['stage']['name']==('sign_in' if password else 'email_entry')
    from job_applier.simplify_boundary import initial_autofill
    assert initial_autofill(dict(form(), stage=observed['stage'])) is None


def test_apply_submit_button_is_not_posting_navigation():
    from test_greenhouse_recovery import form_dom
    html='<form><label>Name<input name="name" required></label><input type="email" required><button type="submit">Apply</button></form>'
    observed=form_dom(html,[{'method':'observe'},{'method':'inspect','selector':'button'}])
    assert observed['results'][0]['native']['submit']['enabled']
    assert not observed['results'][0]['native'].get('apply')
    assert observed['results'][1]['submission_control']


def test_workday_mapped_field_recovery_defers_to_initial_autofill(tmp_path,monkeypatch):
    from test_workday_credentials import AuthHarness
    from job_applier import workday_auth
    h=AuthHarness(tmp_path);h.cfg['cdp_url']='fixture'
    h.observation=dict(form(),workday=True,step='my_information',url=h.package['job']['url'])
    calls=[]
    async def recover(*args):
        calls.append('native');return {'status':'inspection_required'}
    async def perform(self,*args,**kwargs):
        calls.append('autofill');h.observation['autofill_attempted']=True
        return {'execution':'clicked','native_takeover_authorized':True}
    monkeypatch.setattr(workday_auth,'recover_screen',recover)
    monkeypatch.setattr(SimplifyBoundary,'perform',perform)
    result=asyncio.run(h.runner.run(seconds=10,recovery={'fields':[{'ref':'old','value':'approved'}]}))
    assert calls==['autofill']
    assert result['recovery_result']['execution']=='not_executed'
    assert result['reason']=='autofill_before_mapped_recovery'


def test_greenhouse_parent_autofill_precedes_iframe_residual_batch(tmp_path,monkeypatch):
    import test_embedded_forms as fixture
    from test_greenhouse_batch import batch_html,batch_profile
    from job_applier.greenhouse_fast import GreenhouseRunner
    monkeypatch.setattr(fixture,'FORM_HTML',batch_html())
    async def run():
        async with fixture.fixture_browser(tmp_path,mode='same') as (page,package,_):
            package['attempt'].update(profile_json=batch_profile(),settings_json={'submission_mode':'review'})
            await page.evaluate("""(()=>{window.order=[];const d=document.querySelector('iframe').contentDocument;
                d.addEventListener('input',()=>order.push('native'));
                const host=document.createElement('div');host.className='simplify-jobs-shadow-root';document.body.prepend(host);
                const root=host.attachShadow({mode:'open'});root.innerHTML='<p>Autofill complete</p><button>Autofill This Page</button>';
                root.querySelector('button').onclick=()=>{order.push('autofill');d.querySelector('#email').value='fixture@example.test';root.querySelector('p').textContent='Autofill complete';};
            })()""")
            ledger=fixture.SubmissionLedger()
            runner=GreenhouseRunner(page,ledger.call,package,{'attempt_id':1,'worker_id':'fixture','fence':1},
                {'spool_dir':str(tmp_path/'spool'),'cdp_url':page.fixture_endpoint},page.target_id)
            result=await runner.run(30)
            assert result['status']=='ready_for_review',result
            assert result['parent_autofill_dispatch_count']==1 and result['autofill_dispatch_count']==1
            events=await page.evaluate('window.order')
            assert events and events[0]=='autofill',events
    asyncio.run(run())


@pytest.mark.parametrize('portal',['unknown','workday','greenhouse','icims','linkedin'])
def test_native_only_recommendation_preserves_selected_strategy(portal):
    result=next_operation(portal,form(),settings={'autofill':'native'})
    assert result.get('parameters',{}).get('action')!='autofill'


@pytest.mark.parametrize('available',[False,True])
def test_linkedin_bulk_fill_precedes_residual_questions(monkeypatch,available):
    from job_applier.linkedin_easy_apply import EasyApplyRunner
    from job_applier import browser_controls
    events=[];attempted=False
    url='https://www.linkedin.com/jobs/view/123456'
    class Page:
        async def evaluate(self,*args):return url
    page=Page()
    runner=EasyApplyRunner(page,lambda *a,**kw:{'control':'running'},
        {'job':{'url':url},'attempt':{},'documents':{'assets':[]}}, {},{},'fixture')
    async def observe():
        return dict(form(),controls={'autofill':{'enabled':available,'ref':'bulk'}},autofill_attempted=attempted,
            page_signature='step',blocking_errors=[],linkedin={'kind':'easy_apply','modal':True,'file_inputs':[],'resumes':[],
            'questions':[{'required':True,'answered':False}]})
    async def write(op,fn):return await fn()
    async def fill(obs):events.append('native');return {'committed':True}
    async def document(*a,**kw):return page,{},None
    async def perform(*a,**kw):
        nonlocal attempted
        attempted=True;events.append('autofill');return {'execution':'clicked','native_takeover_authorized':True}
    runner.observe=observe;runner.write=write;runner.fill=fill
    runner.report=lambda status,*a,**kw:{'status':status}
    monkeypatch.setattr(browser_controls,'simplify_document',document)
    monkeypatch.setattr(SimplifyBoundary,'perform',perform)
    assert asyncio.run(runner.run(10))['status']=='questions_required'
    assert events==(['autofill','native'] if available else ['native'])


def test_conditional_field_expansion_does_not_repeat_generic_autofill(tmp_path,monkeypatch):
    from test_form_audit import fixture_html,icims_browser
    import test_embedded_forms as fixture
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page,package,_):
            await page.evaluate("document.querySelectorAll('h1,h2,h3,[aria-current]').forEach(e=>e.remove());fixture.setSimplify('active')")
            await observe(page,package)
            await page.evaluate("fixture.setSimplify('needs_review')")
            before=await observe(page,package)
            assert before['autofill_attempted']
            await page.evaluate("document.querySelector('form').insertAdjacentHTML('beforeend','<label>Follow up<input name=conditional></label>')")
            after=await observe(page,package)
            assert after['autofill_attempted']
            assert after['autofill_page_key']==before['autofill_page_key']
    asyncio.run(run())
