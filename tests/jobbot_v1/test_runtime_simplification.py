"""Synthetic counterexamples to the restrictions rejected by the runtime audit."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from job_applier import application_runtime as runtime
from job_applier.managed_identity import is_same_application_scope, same_job_url
from job_applier.managed_runtime import RuntimeServices


JOB = 'https://tenant.wd1.myworkdayjobs.com/Careers/job/City-State/Director_R100-1'


@pytest.mark.parametrize('url', [
    JOB.replace('City-State', 'City%2C-State') + '/apply/applyManually',
    JOB.replace('Director_', 'Director-of-AI_') + '/apply/newApplicationStep',
    JOB.replace('/job/City-State/', '/details/') + '?q=director',
])
def test_workday_identity_agrees_across_history_posting_and_application(url):
    assert is_same_application_scope(JOB, url)
    assert same_job_url(JOB, url)
    assert runtime.history_key(JOB) == runtime.history_key(url)


def test_workday_full_requisition_suffix_and_portal_are_not_discarded():
    for url in (JOB.replace('R100-1', 'R100-2'), JOB.replace('/Careers/', '/Other/'),
                JOB.replace('tenant.wd1', 'other.wd1')):
        assert not is_same_application_scope(JOB, url)
        assert not same_job_url(JOB, url)
        assert runtime.history_key(JOB) != runtime.history_key(url)
    with_suffix = JOB.replace('R100-1', 'R100_1')
    assert runtime.history_key(with_suffix) != runtime.history_key(with_suffix.replace('R100_', 'R200_'))


def test_bound_workday_login_does_not_need_a_repeated_job_in_its_url():
    login = 'https://tenant.wd1.myworkdayjobs.com/en-US/Careers/login'
    assert is_same_application_scope(JOB, login)
    assert not is_same_application_scope(JOB, login + '?redirect=' + JOB.replace('R100-1', 'R200-1'))


def test_owned_snapshot_and_return_navigation_survive_job_mismatch(monkeypatch, tmp_path):
    from job_applier.cdp_client import CDPBrowser
    foreign = JOB.replace('R100-1', 'R200-1')
    page = type('Page', (), {})()
    page.goto = AsyncMock()
    async def evaluate(script, *args, **kw):
        if script == 'location.href':return foreign
        if script == 'document.title':return 'Owned tab moved'
        if 'innerText' in script:return 'A different role'
        return {}
    page.evaluate = evaluate
    browser = type('Browser', (), {'get_current_page': AsyncMock(return_value=page), 'close': AsyncMock()})()
    monkeypatch.setattr(CDPBrowser, 'connect', AsyncMock(return_value=browser))
    calls = []
    class Client:
        def call(self, op, **kw):
            calls.append((op, kw))
            return {'quiescent': True, 'native_takeover_authorized': True}
    package = {'job': {'url': JOB}, 'attempt': {'profile_json': {}, 'settings_json': {}}}
    config = {'cdp_url': 'http://127.0.0.1:9222', 'spool_dir': str(tmp_path)}
    own = {'attempt_id': 1, 'worker_id': 'synthetic', 'fence': 1}
    result = runtime.browser_action(config, Client(), own, package, 'owned-tab', {'method': 'snapshot'})
    assert result['identity']['status'] == 'different_job' and result['recovery_only']
    runtime.browser_action(config, Client(), own, package, 'owned-tab', {'method': 'navigate', 'url': JOB})
    page.goto.assert_awaited_once_with(JOB)
    with pytest.raises(Exception, match='target_job_mismatch'):
        runtime.browser_action(config, Client(), own, package, 'owned-tab', {'method': 'fill', 'selector': '#field', 'value': 'wrong job'})


@pytest.mark.parametrize('duration', [None, 61])
def test_local_field_timing_is_telemetry_not_write_authority(duration, monkeypatch):
    from job_applier import managed_sessions
    monkeypatch.setattr(managed_sessions, 'local_session', lambda db, aid: {'id': 'owned-local'})
    class Rows(list):
        def fetchone(self):return self[0] if self else None
        def fetchall(self):return self
    context = {'page': 'questions', 'field': 'salary', 'category': 'required'}
    events = [dict(event_type='tool_finished', duration_seconds=duration, payload_json=json.dumps(context)),
              dict(event_type='field_context', duration_seconds=0, payload_json=json.dumps(context))]
    class DB:
        def execute(self, sql, args=()):return Rows([(0,)]) if 'budget_extensions' in sql else Rows(events)
    attempt = {'id': 1, 'settings_json': json.dumps({'field_seconds': 60, 'allowed_fallback': 'targeted'})}
    assert RuntimeServices()._strategy_check(DB(), attempt, 'browser.fill') == context
def test_mapped_recovery_allows_another_control_on_the_same_screen(tmp_path):
    import asyncio
    from test_workday_credentials import AuthHarness
    from job_applier.workday_auth import recover_screen
    from job_applier.workday_fast import screen_inventory
    h=AuthHarness(tmp_path)
    h.observation={'step':'unknown','page_signature':'chooser','auth':False,
        'inventory':[{'ref':'first','text':'Apply','enabled':True},{'ref':'second','text':'Apply Manually','enabled':True}]}
    key=screen_inventory(h.observation,h.package)['screen_key']
    for ref in ('first','second'):
        response=asyncio.run(recover_screen(h.runner,{'screen_key':key,'action':{'source':'native','ref':ref}}))
        assert response['status']=='progress', response
    assert len(h.clicks)==2


def test_auth_submit_label_and_prior_non_dispatch_do_not_block_mapped_recovery(tmp_path,monkeypatch):
    import asyncio
    from test_workday_credentials import AuthHarness
    from job_applier import workday_auth
    from job_applier.workday_fast import screen_inventory
    h=AuthHarness(tmp_path,'sign_in');h.observation=h.auth('sign_in')
    h.observation.update(page_signature='login',inventory=[{'ref':'login','text':'Submit','auth_form':True,'enabled':True}])
    h.runner.state['authentication']={'not_executed':{'sign_in':2}}
    async def fill(*args):return {'values_committed':True,'credential_ref':'credential:profile/accounts/default'}
    monkeypatch.setattr(workday_auth,'fill_page_credentials',fill)
    response=asyncio.run(workday_auth.recover_screen(h.runner,{
        'screen_key':screen_inventory(h.observation,h.package)['screen_key'],'account_mode':'sign_in',
        'credentials':h.observation['auth_refs'],'action':{'source':'native','ref':'login'}}))
    assert response['status']=='progress',response
    assert len(h.clicks)==1


def test_identity_check_distinguishes_applicant_from_reference_email():
    from test_workday_dom import observe
    html='<h2>My Information</h2><label>Email address<input type="email" name="email" value="person@example.test"></label><label>Reference email<input type="email" value="ref@example.test"></label>'
    assert not observe(html,expected_email='person@example.test')['identity_mismatch']
    assert observe(html.replace('person@example.test','wrong@example.test'),expected_email='person@example.test')['identity_mismatch']
    assert not observe('<label>Referrer email<input type="email" value="ref@example.test"></label>',expected_email='person@example.test')['identity_mismatch']
def test_unrelated_frame_diagnostic_does_not_block_readable_documents():
    from job_applier.browser_controls import _merge_writers
    root={'status':'ready','panel':True,'writer_safe':True,'activity':{}}
    observed=_merge_writers(root,[],[{'reason':'frame_not_available','frame_id':'unrelated'}])
    assert observed['status']=='ready' and observed['writer_safe']
    assert observed['frame_diagnostics']


@pytest.mark.parametrize('navigation_timeout',[False,True])
def test_slow_page_and_missing_extension_remain_available_for_recovery(tmp_path,monkeypatch,navigation_timeout):
    import asyncio
    from types import SimpleNamespace
    from job_applier import workspace_host
    from job_applier.cdp_client import CDPBrowser
    from job_applier.simplify_boundary import SimplifyBoundary
    job_url='https://tenant.wd1.myworkdayjobs.com/Jobs/job/City/Role_R1'
    workspace={'cdp_url':'http://127.0.0.1:12345','user_data_dir':str(tmp_path),'mode':'headless','id':'test'}
    async def command(endpoint,method,params=None):
        return {'arguments':['--user-data-dir='+str(tmp_path),'--headless=new']} if method=='Browser.getBrowserCommandLine' else {'targetId':'owned'}
    class Page:
        async def goto(self,url):
            if navigation_timeout:raise asyncio.TimeoutError('Synthetic delayed navigation response')
        async def evaluate(self,expression):
            if expression=='location.href':return job_url
            if 'readyState' in expression:return False
            return {'width':1000,'height':800}
    class Browser:
        async def get_current_page(self):return Page()
        async def close(self):pass
    async def connect(*args,**kwargs):return Browser()
    async def observe(self):return {'panel':False,'status':'missing'}
    ticks=iter(range(0,1000,10))
    monkeypatch.setattr(workspace_host,'time',SimpleNamespace(monotonic=lambda:next(ticks)))
    monkeypatch.setattr(workspace_host,'browser_command',command)
    monkeypatch.setattr(CDPBrowser,'connect',connect)
    monkeypatch.setattr(SimplifyBoundary,'observe',observe)
    h=workspace_host.WorkspaceHost.__new__(workspace_host.WorkspaceHost)
    h.workspace=workspace;h.config={'require_simplify':True}
    h.service=SimpleNamespace(job=lambda job_id:{'url':job_url},now=lambda:'2026-09-09T00:00:00+00:00')
    target,readiness=asyncio.run(h.prepare_target({'job_id':'job'}))
    assert target=='owned' and readiness['target_operable']
    assert readiness['recovery']['reason']=='application_page_loading'
    assert readiness['simplify']=='not_observed'


def test_confirmation_inspection_has_no_unrequested_close_timer():
    from job_applier.workspace_host import WorkspaceHost
    h=WorkspaceHost.__new__(WorkspaceHost);h.inspection_deadlines={};h.config={}
    result=h.inspection_result('session')
    assert result.get('inspection_seconds') is None
    assert not h.inspection_deadlines
def test_observed_extension_stop_recovers_unknown_writer_without_faking_idle():
    import asyncio
    from test_simplify_boundary import DOMSeamPort,FakeClockSleeper
    from job_applier.simplify_boundary import SimplifyBoundary
    clock=FakeClockSleeper()
    page=DOMSeamPort({'status':'unknown','panel':True,'controls':{'stop':{'ref':'stop','enabled':True}}})
    def click(args):
        assert args['operation']=='stop'
        page.observation={'status':'ready','panel':True,'fingerprint':'settled','controls':{}}
        return {'status':'clicked'}
    page._on_click=click
    boundary=SimplifyBoundary(page,budget_seconds=3,clock=clock.clock,sleeper=clock.sleep)
    result=asyncio.run(boundary.perform('stop'))
    assert result['writer_state']=='idle' and len(page.clicks)==1
    page.observation={'status':'active','panel':True,'controls':{}}
    result=asyncio.run(boundary.perform('stop'))
    assert result['writer_state']!='idle' and len(page.clicks)==1


def test_only_local_extension_stop_can_start_while_writer_unknown(tmp_path):
    import pytest
    from job_applier.managed import ProtocolError
    from test_local_sessions import setup,reserve,connect,own
    s,asset,jobs,*_=setup(tmp_path);session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    s.writer_state(**owner,state='unknown')
    with pytest.raises(ProtocolError,match='browser_writer_busy'):
        s.action_start(**owner,action_id='fill',tool_name='local_browser.fill')
    s.action_start(**owner,action_id='stop',tool_name='local_browser.simplify_stop')
    with pytest.raises(ProtocolError,match='browser_writer_busy'):
        s.action_start(**owner,action_id='stop-again',tool_name='local_browser.simplify_stop')
    assert s.attempt(owner['attempt_id'])['writer_state']=='unknown'


def test_proven_non_dispatch_allows_recovery_and_normal_stop(tmp_path):
    from test_local_sessions import setup,reserve,connect,own
    s,asset,jobs,*_=setup(tmp_path);session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    s.submission_intent(**owner,evidence='Synthetic final control',fixture=True)
    # Same timestamp and reverse-ordered ids exercise true insertion order.
    stamp=s.now()
    for event_id,status in [('z-intent','possibly_executed'),('a-result','not_executed')]:
        s.event(**owner,event_id=event_id,event_type='checkpoint',observed_at=stamp,
            payload={'operation':'submission_click','status':status})
    assert s.attempt(owner['attempt_id']).get('submission_pending') is False
    assert s.application_context(owner['attempt_id'])['attempt']['submission_pending'] is False
    finished=s.finish(**owner,outcome='blocked',evidence='Synthetic control cannot be activated',quiescent=True)
    assert finished['outcome']=='blocked'


def test_intent_without_dispatch_result_remains_uncertain(tmp_path):
    from test_local_sessions import setup,reserve,connect,own
    s,asset,jobs,*_=setup(tmp_path);session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    s.submission_intent(**owner,evidence='Synthetic final control',fixture=True)
    assert s.attempt(owner['attempt_id']).get('submission_pending') is True
def test_optional_answer_history_failure_does_not_replace_form_result(tmp_path):
    from job_applier.application_answers import save_answer_history
    spool=tmp_path/'spool';spool.write_text('Synthetic path collision')
    result=save_answer_history({'spool_dir':str(spool)}, {'job':{'url':'https://example.test/job/1'}},1,
        [{'field':'leadership','question':'Led a team?','answer':'Yes'}],page='questions',source='employer_form')
    assert result.get('answer_history_error')


def test_optional_progress_event_failure_does_not_abort_runner(tmp_path):
    from test_workday_credentials import AuthHarness
    h=AuthHarness(tmp_path)
    def fail(*args,**kwargs):raise OSError('Synthetic telemetry store unavailable')
    h.runner.call=fail
    h.runner.event('phase_changed',{'phase':'my_information'})
    assert h.runner.state.get('diagnostic_error')=='OSError'


def test_new_form_evidence_can_trigger_another_fill_after_earlier_retries():
    from job_applier.workday_fast import choose
    observed={'step':'my_information','status':'ready','fingerprint':'changed-required-fields',
        'controls':{'autofill':{'enabled':True}}}
    state={'fills':2,'fill_attempts':{'earlier-fields':2},'advance_failed':True}
    assert choose(observed,state) in ('retry','autofill')
@pytest.mark.parametrize('known_source',['saved_answer','configured_policy_control_failure'])
def test_known_answers_do_not_create_new_human_questions(tmp_path,monkeypatch,known_source):
    from unittest.mock import AsyncMock
    from test_answer_queue import QUESTION
    from job_applier import browser_controls
    from job_applier.application_runtime import browser_action
    from job_applier.cdp_client import CDPBrowser
    from job_applier.managed_questions import question_key
    url=QUESTION['context']['document'];applied=[]
    saved=dict(QUESTION,id='question',revision=1,state='answered',question_key=question_key(QUESTION),
        answer={'value':'yes','label':'Yes'})
    class Page:
        async def evaluate(self,expression):return url
    browser=type('Browser',(),{'get_current_page':AsyncMock(return_value=Page()),'close':AsyncMock()})()
    monkeypatch.setattr(CDPBrowser,'connect',AsyncMock(return_value=browser))
    monkeypatch.setattr(browser_controls,'observe',AsyncMock(return_value={'inventory':[]}))
    monkeypatch.setattr(browser_controls,'required_questions',AsyncMock(return_value={
        'questions':[{'ref':'leadership','data':QUESTION}],'skipped':[]}))
    if known_source=='configured_policy_control_failure':
        monkeypatch.setattr('job_applier.application_answers.apply_policy',AsyncMock(return_value={
            'changed':False,'fields':[{'ref':'leadership','field':QUESTION['question'],'committed':False,'reason':'control_obscured'}]}))
    async def fill(page,params):applied.append(params);return {'committed':True}
    monkeypatch.setattr(browser_controls,'form_action',fill)
    class Client:
        def call(self,op,**params):
            assert op!='request_question','A saved answer must not become a new human question'
            if op=='questions_for_attempt':return {'questions':[saved] if known_source=='saved_answer' else []}
            if op=='browser_observe':return {'quiescent':True,'native_takeover_authorized':True}
            return {}
    result=browser_action({'cdp_url':'http://127.0.0.1:1234','spool_dir':str(tmp_path)},Client(),
        {'attempt_id':1,'worker_id':'worker','fence':1}, {'job':{'url':url},'attempt':{'profile_json':{}}},
        'owned',{'method':'request_answers','refs':['leadership']})
    assert result['questions']==[]
    if known_source=='saved_answer':
        assert result['fields'][0]['committed']
        assert applied==[{'method':'select','ref':'leadership','value':'yes','label':'Yes'}]
    else:
        assert not applied
        assert result['skipped']==[{'ref':'leadership','reason':'configured_answer_control_unconfirmed'}]
def test_submit_non_dispatch_can_retry_but_uncertain_dispatch_cannot(tmp_path,monkeypatch):
    import asyncio
    from test_embedded_forms import SubmissionLedger
    from job_applier.submission import submit,SCRIPT
    from job_applier.managed_shared import submission_pending
    from job_applier import managed_credentials
    from unittest.mock import AsyncMock
    url='https://tenant.wd1.myworkdayjobs.com/Jobs/job/City/Role_R100_1'
    class Session:
        def subscribe(self,*args):return lambda:None
        async def call(self,*args,**kwargs):return {'identifier':'fixture'}
    class Page:
        _session=Session();confirmed=False
        async def evaluate(self,expression):return url
        async def evaluate_function(self,script,args):
            if script==SCRIPT and args.get('operation')=='read':
                return [{'source':'employer','text':'Application submitted','url':url}] if self.confirmed else []
            return {'baseline':[]}
    page=Page();ledger=SubmissionLedger();calls=[]
    monkeypatch.setattr(managed_credentials,'capture_private_screenshot',AsyncMock())
    package={'job':{'url':url},'attempt':{'profile_json':{}}}
    async def activate():
        calls.append('click')
        if len(calls)==1:return {'clicked':False,'execution':'not_executed','reason':'control_obscured'}
        page.confirmed=True;return {'clicked':True}
    async def check():
        first=await submit(page,ledger.call,package,{'attempt_id':1},{'spool_dir':str(tmp_path),'cdp_url':'fixture'},'owned',activate,seconds=1)
        assert first['execution']=='not_executed' and not submission_pending(ledger.attempt,ledger.events)
        second=await submit(page,ledger.call,package,{'attempt_id':1},{'spool_dir':str(tmp_path),'cdp_url':'fixture'},'owned',activate,seconds=1)
        assert second['status']=='applied' and len(calls)==2
        # A lost dispatch result has no not_executed event and stays read-only.
        uncertain=SubmissionLedger();uncertain.attempt['submit_intent_at']='fixture-lost-response';page.confirmed=False
        third=await submit(page,uncertain.call,package,{'attempt_id':1},{'spool_dir':str(tmp_path/'uncertain'),'cdp_url':'fixture'},'owned',activate,seconds=1)
        assert third['status']=='submission_unknown' and len(calls)==2
    asyncio.run(check())


def test_unrecognized_helper_screen_requests_inspection_without_claiming_blocker():
    import asyncio
    from test_workday_fast import Harness,snapshot
    observed=snapshot('missing');observed['controls']={}
    result=asyncio.run(Harness([observed]).runner().run(seconds=3))
    assert result['status']=='inspection_required' and result['reason']=='screen_controls_unrecognized'
def test_confirmation_observer_uses_complete_workday_requisition():
    import asyncio
    from job_applier.workday_fast import observe_page,WORKDAY_OBSERVE
    url='https://tenant.wd1.myworkdayjobs.com/Jobs/job/City/Role_R100_1'
    class Page:
        async def evaluate(self,script):return url if script=='location.href' else {}
        async def evaluate_function(self,script,args):
            assert script==WORKDAY_OBSERVE and args['requisition'].lower()=='r100_1'
            return {}
    asyncio.run(observe_page(Page(),{'job':{'url':url},'attempt':{'profile_json':{}}}))
def test_workday_intake_links_existing_alias_history_without_rewriting_rows(tmp_path):
    from job_applier.managed import Service
    from job_applier.managed_identity import job_key,linked_jobs
    s=Service.create(tmp_path/'history.db',instance_id='synthetic')
    first=s.intake(url='https://tenant.wd1.myworkdayjobs.com/Jobs/job/City/Role_R100')
    historical=dict(first,id='historical-duplicate',seq_id=first['seq_id']+1,
        url='https://tenant.wd1.myworkdayjobs.com/Jobs/job/OtherCity/Older-Title_R100',status='applied')
    historical['identity_key']=job_key(historical['url'])
    with s.tx() as db:
        db.execute('INSERT INTO jobs ('+','.join(historical)+') VALUES ('+','.join('?' for _ in historical)+')',tuple(historical.values()))
        db.execute('INSERT INTO job_identity_keys VALUES (?,?,?)',(historical['identity_key'],historical['id'],'synthetic historical row'))
    result=s.intake(url=first['url'])
    with s.tx() as db:assert set(linked_jobs(db,result['id']))=={first['id'],historical['id']}
    with s.tx() as db:
        assert dict(s._get(db,'jobs',first['id']))==first
        assert dict(s._get(db,'jobs',historical['id']))==historical


@pytest.mark.parametrize('site,title',[('IT','Role'),('Jobs','Role_R1_Experience')])
def test_workday_identity_does_not_confuse_site_or_title_with_requisition(site,title):
    original=f'https://tenant.wd1.myworkdayjobs.com/{site}/job/City/{title}_R100_1'
    changed=f'https://tenant.wd1.myworkdayjobs.com/en-US/{site}/job/OtherCity/New-Title_R100_1/application'
    assert is_same_application_scope(original,changed)
