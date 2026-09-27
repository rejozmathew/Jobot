"""Synthetic Easy Apply regressions; never open a live LinkedIn application."""
import asyncio
import importlib
import json
from pathlib import Path
import subprocess

import pytest

from job_applier.browser_controls import next_operation
from job_applier.managed_context import platform_for_url
from job_applier.managed_identity import same_job_url, application_match

URL = 'https://www.linkedin.com/jobs/view/123456'


def helper():
    return importlib.import_module('job_applier.linkedin_easy_apply')


def test_platform_and_confirmed_routing_are_separate():
    assert platform_for_url(URL) == 'linkedin'
    assert platform_for_url('https://notlinkedin.com/jobs/view/123456') == 'unknown'
    assert next_operation('linkedin', {'linkedin': {'kind': 'easy_apply'}})['operation'] == 'linkedin_easy_apply'
    assert next_operation('linkedin', {'linkedin': {'kind': 'unknown'}})['operation'] == 'browser'
    assert next_operation('linkedin', {'linkedin': {'kind': 'external', 'apply': {'ref': 'form:external', 'enabled': True}}})['parameters'] == {'method': 'click', 'ref': 'form:external'}
    assert next_operation('greenhouse', {'status': 'ready', 'controls': {'autofill': {'enabled': True}}})['parameters']['action'] == 'autofill'


def test_linkedin_job_identity_not_entire_hostname():
    assert same_job_url(URL, 'https://www.linkedin.com/jobs/search/?currentJobId=123456')
    assert not same_job_url(URL, 'https://www.linkedin.com/jobs/search/?currentJobId=654321')
    assert not same_job_url(URL, 'https://www.linkedin.com/jobs/search/')
    assert not same_job_url(URL, URL+'?currentJobId=654321')
    assert application_match(URL, 'https://www.linkedin.com/jobs/view/654321')['status'] == 'different_job'


def test_linkedin_intake_alias_preserves_job_key_history_and_success(tmp_path):
    from job_applier.managed import Service
    service=Service.create(tmp_path/'managed.db',instance_id='linkedin-fixture')
    original=service.intake(url=URL,source_type='jobnavigator_bridge',source_id='source:123456')
    with service.tx() as db:
        db.execute("UPDATE jobs SET status='applied' WHERE id=?",(original['id'],))
        before=[tuple(row) for row in db.execute('SELECT * FROM job_sources')]
    alias=service.intake(url='https://www.linkedin.com/jobs/search/?currentJobId=123456')
    assert alias['id']==original['id'] and alias['identity_key']==original['identity_key']
    assert alias['url']==URL and alias['status']=='applied'
    with service.tx() as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM job_sources WHERE source_id=?',('source:123456',))]==before
        assert db.execute('SELECT count(*) FROM jobs').fetchone()[0]==1
    other=service.intake(url='https://www.linkedin.com/jobs/search/?currentJobId=654321')
    assert other['id']!=original['id']


def test_donor_answer_regressions_use_only_approved_facts():
    m = helper()
    profile = {'standard_answers': {'requires_sponsorship': True, 'legally_authorized_to_work': True},
               'identity': {'state': 'Teststate'}, 'experience': {'years': 12}}
    assert not m.label_has('authorized to work in the United States', 'state')
    assert m.approved_answer('Are you legally authorized to work in the United States?', profile) is True
    assert m.approved_answer('Will you need sponsorship for work authorization?', profile) is True
    assert m.approved_answer('Are you a US citizen?', profile) is None
    assert m.approved_answer('How many years of Kubernetes experience?', profile) is None
    assert m.approved_answer('Active security clearance?', profile) is None
    assert m.approved_answer('Do you currently hold an H1B visa?', profile) is None
    assert m.approved_answer('Will you require sponsorship in the future?', profile) is None
    assert m.match_answer_to_option('Non-citizen allowed to work', ['Yes', 'No']) is None
    assert m.match_answer_to_option('Yes', ['I do not wish to answer', 'Yes']) == 1
    assert m.match_answer_to_option('Yes', ['Yes, citizen', 'Yes, permanent resident']) is None


def dom(html, after=''):
    m = helper()
    root = Path(__file__).resolve().parents[2]
    jsdom = root/'artifacts/jobbot-v1-private/dom-test/node_modules/jsdom'
    if not jsdom.exists():
        pytest.skip('optional jsdom fixture dependency not installed')
    script = r'''
const fs=require('fs'),{JSDOM}=require(process.argv[1]);
const d=JSON.parse(fs.readFileSync(0,'utf8'));
const w=new JSDOM(d.html,{url:d.url,runScripts:'outside-only'}).window;
w.HTMLElement.prototype.getClientRects=function(){return this.closest('[hidden]')?[]:[{width:100,height:20}]};
const observe=()=>w.eval(d.script)({job_id:'123456'});
const first=observe(); const extra=w.eval(d.after||'null');
console.log(JSON.stringify({first,extra,second:observe()}));w.close();
'''
    result = subprocess.run(['node', '-e', script, str(jsdom)], input=json.dumps({
        'html': html, 'script': m.OBSERVE, 'after': after, 'url': URL}),
        capture_output=True, text=True, check=True, timeout=15)
    return json.loads(result.stdout)


def modal(body):
    return '<div role="dialog" class="jobs-easy-apply-modal"><h2>Apply to Example</h2>'+body+'</div>'


def test_modal_controls_exclude_pagination_and_unconfirmed_apply():
    assert dom('<button id="jobs-apply-button-id">Apply</button>')['first']['linkedin']['kind'] == 'unknown'
    assert dom('<button id="jobs-apply-button-id" aria-label="Easy Apply to Example">Easy Apply</button>')['first']['linkedin']['kind'] == 'easy_apply'
    assert dom('<a class="jobs-apply-button" href="https://employer.example/jobs/1">Apply</a>')['first']['linkedin']['kind'] == 'external'
    observed = dom('<button>Next</button>'+modal('<button aria-label="Continue to next step">Next</button>'))['first']
    assert observed['native']['continue']['enabled']
    assert len(observed['inventory']) == 1
    assert dom('<button class="jobs-apply-button">Continue application</button>')['first']['linkedin']['kind'] == 'easy_apply'
    assert dom('<div data-job-id="999"><button class="jobs-apply-button">Easy Apply</button></div>')['first']['linkedin']['kind'] == 'unknown'


def test_form_groups_options_placeholders_and_prepopulation():
    output = dom(modal('''<div data-test-form-element><label for="years">Years using Python *</label><input id="years" type="number" required></div>
<div data-test-form-element><label for="bio">Why this role?</label><textarea id="bio">Already approved</textarea></div>
<div data-test-form-element><label for="status">Status *</label><select required id="status"><option>Select an option</option><option>Yes</option><option>No</option></select></div>
<div data-test-form-element><fieldset data-test-form-builder-radio-button-form-component="true"><span data-test-form-builder-radio-button-form-component__title>Require sponsorship? *</span><input type="radio" name="sponsor" id="yes" required><label for="yes">Yes</label><input type="radio" name="sponsor" id="no"><label for="no">No</label></fieldset></div>
<div data-test-form-element><input id="agree" type="checkbox" required><label for="agree">Specific consent *</label></div>'''))['first']
    questions = output['linkedin']['questions']
    assert len(questions) == 5
    assert questions[1]['answered']
    assert not questions[2]['answered']
    assert questions[3]['question'] == 'Require sponsorship? *'
    assert [x['label'] for x in questions[3]['options']] == ['Yes', 'No']
    assert questions[4]['kind'] == 'check'


def test_stale_step_cannot_reuse_previous_question_ref():
    output = dom(modal('<div data-test-form-element><label for="q">Years using Java</label><input id="q"></div>'),
                 "document.querySelector('label').textContent='Years using Python'; null")
    old = output['first']['linkedin']['questions'][0]
    new = output['second']['linkedin']['questions'][0]
    assert old['ref'] != new['ref']
    assert output['first']['page_signature'] != output['second']['page_signature']


def test_inline_validation_and_selected_resume_evidence():
    observed = dom(modal('''<input name="file" type="file" hidden>
<div class="jobs-document-upload-redesign-card__container"><input type="radio" checked><span>selected.pdf</span><span>12 KB</span></div>
<div role="alert">Please enter a valid answer</div><button>Review</button>'''))['first']
    assert observed['linkedin']['file_inputs']
    assert observed['linkedin']['resumes'][0]['selected']
    assert observed['blocking_errors']
    assert observed['native']['review']['enabled']
    assert not dom(modal('<div role="alert">Resume successfully uploaded</div><button>Next</button>'))['first']['blocking_errors']


def test_operation_is_registered():
    from job_applier.hermes_plugin import OPERATIONS
    assert 'linkedin_easy_apply' in OPERATIONS


def package(mode='review'):
    return {'job': {'url': URL}, 'platform': 'linkedin', 'documents': {'assets': []},
            'attempt': {'profile_json': {}, 'settings_json': {'submission_mode': mode}}, 'saved_questions': []}


def screen(signature='review', *, modal_open=True, questions=None, kind='easy_apply'):
    return {'page_signature': signature, 'step': 'form', 'status': 'missing', 'auth': False,
            'inventory': [], 'blocking_errors': [], 'native': {'submit': {'ref': 'form:submit', 'enabled': True}},
            'linkedin': {'kind': kind, 'modal': modal_open, 'questions': questions or [], 'resumes': [], 'file_inputs': [],
                         'apply': {'ref': 'form:open', 'enabled': True}}}


def runner(monkeypatch, observed, mode='review', gate=True):
    m=helper();calls=[]
    class Page:
        async def evaluate(self,script):return URL
    def call(op,**params):
        calls.append((op,params))
        if op=='browser_observe':return {'native_takeover_authorized':gate}
        return {}
    r=m.EasyApplyRunner(Page(),call,package(mode),{'attempt_id':1,'worker_id':'w','fence':1},{'cdp_url':'http://127.0.0.1:9222'},'owned-tab')
    async def observe():return observed
    async def filled(_):return {'committed':True}
    monkeypatch.setattr(r,'observe',observe);monkeypatch.setattr(r,'fill',filled)
    return r,calls


def test_review_mode_effective_without_tty_and_no_submit(monkeypatch):
    r,calls=runner(monkeypatch,screen())
    result=asyncio.run(r.run())
    assert result['status']=='ready_for_review'
    assert not any(op in ('submission_intent','finish') for op,_ in calls)


@pytest.mark.parametrize('outcome',['submission_unknown','applied','application_incomplete'])
def test_authorized_submit_uses_shared_guard_and_preserves_actual_result(monkeypatch,outcome):
    from job_applier import submission
    r,calls=runner(monkeypatch,screen(),mode='submit')
    invocations=[]
    async def submit(page,call,pkg,own,cfg,target,activate,**kwargs):
        invocations.append((target,kwargs));return {'status':outcome,'source':'employer' if outcome=='applied' else None}
    monkeypatch.setattr(submission,'submit',submit)
    assert asyncio.run(r.run())['status']==outcome
    assert invocations==[('owned-tab',{'application_control':{'ref':'form:submit'}})]
    assert not any(op=='finish' for op,_ in calls)


def test_unknown_questions_return_together_and_continue_after_answers(monkeypatch):
    questions=[{'ref':f'form:q{i}','question':f'Unfamiliar question {i}?','kind':'text','options':[],'required':True,'answered':False} for i in range(2)]
    r,calls=runner(monkeypatch,screen(questions=questions))
    result=asyncio.run(r.run())
    assert result['status']=='questions_required' and len(result['questions'])==2
    assert not any(op=='finish' for op,_ in calls)
    for q in questions:q['answered']=True
    assert asyncio.run(r.run())['status']=='ready_for_review'


def test_native_writer_gate_stays_authoritative_without_extension(monkeypatch):
    r,calls=runner(monkeypatch,screen(),gate=False)
    assert asyncio.run(r.run())['reason']=='writer_settlement_required'
    assert not any(op=='action_start' for op,_ in calls)


def test_modal_multistep_resume_application_and_review(monkeypatch):
    m=helper();current=screen('posting',modal_open=False);r,calls=runner(monkeypatch,current)
    clicks=[]
    async def click(page,target,**kwargs):
        clicks.append(target['ref'])
        if len(clicks)==1:
            current.update(screen('contact'));current['native']={'continue':{'ref':'form:next','enabled':True}}
        elif len(clicks)==2:
            current.update(screen('questions'));current['native']={'review':{'ref':'form:review','enabled':True}}
        else:current.update(screen('review'))
        return {'clicked':True}
    async def observe():return json.loads(json.dumps(current))
    monkeypatch.setattr(r,'observe',observe);monkeypatch.setattr(m,'click_control',click)
    assert asyncio.run(r.run())['status']=='ready_for_review'
    assert clicks==['form:open','form:next','form:review']


def test_existing_confirmation_is_recorded_without_new_click(monkeypatch):
    observed=screen();observed['linkedin']['already_applied']='Applied yesterday'
    r,calls=runner(monkeypatch,observed)
    assert asyncio.run(r.run())['status']=='already_applied'
    assert [(op,p['outcome']) for op,p in calls if op=='finish']==[('finish','already_applied')]
    assert not any(op=='action_start' for op,_ in calls)


def test_saved_answers_require_exact_question_context_and_choices():
    from job_applier.managed_questions import question_data,question_key
    m=helper();p=package()
    q={'field':'consent','question':'Specific consent?','kind':'check','options':[],
       'required':True,'context':{'page':'form','section':'','document':URL},'ref':'form:consent'}
    data=question_data(**{k:v for k,v in q.items() if k!='ref'})
    p['saved_questions']=[{'question_key':question_key(data),'answer':True,'state':'answered'}]
    assert m.saved_answer(q,p) is True
    assert m.saved_answer(dict(q,question='Another consent?'),p) is None
    assert m.answer_action(q,True)=={'method':'check','ref':'form:consent','value':True}


def test_selected_resume_upload_mismatch_and_recovery(monkeypatch,tmp_path):
    m=helper();path=tmp_path/'approved.pdf';path.write_bytes(b'synthetic fixture')
    import hashlib
    observed=screen();observed['linkedin']['file_inputs']=[{'ref':'form:file','files':[]}]
    observed['linkedin']['resumes']=[{'text':'wrong.pdf','selected':True,'control':{}}]
    r,calls=runner(monkeypatch,observed)
    r.package['documents']['assets']=[{'id':'resume-1','kind':'resume','storage_ref':path.as_uri(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]
    uploads=[]
    async def upload(page,target,selected):uploads.append((target,selected))
    monkeypatch.setattr(m,'upload_file',upload)
    async def no_wait(_):pass
    monkeypatch.setattr(m.asyncio,'sleep',no_wait)
    assert asyncio.run(r.resume(observed))['reason']=='selected_resume_unconfirmed'
    assert not any(op=='report_upload' and p['status']=='upload_confirmed' for op,p in calls)
    observed['linkedin']['resumes']=[{'text':'approved.pdf','selected':True,'control':{}}]
    assert asyncio.run(r.resume(observed))['committed']
    assert uploads[0][1]==path


def test_batch_fill_preserves_existing_and_uses_shared_verified_writes(monkeypatch):
    m=helper();from job_applier import application_answers
    questions=[{'field':'email','question':'Email','kind':'text','ref':'form:email','enabled':True,'required':True,'answered':False,'options':[],'context':{}},
               {'field':'name','question':'Full name','kind':'text','ref':'form:name','enabled':True,'required':True,'answered':True,'options':[],'context':{}}]
    observed=screen(questions=questions);r,_=runner(monkeypatch,observed)
    r.profile={'identity':{'email':'fixture@example.test','full_name':'Do not overwrite'}}
    writes=[]
    async def action(page,params):writes.append(params);return {'committed':True}
    async def policy(*args,**kwargs):return {'fields':[]}
    async def capture(*args,**kwargs):return {}
    monkeypatch.setattr(m,'form_action',action);monkeypatch.setattr(application_answers,'apply_policy',policy);monkeypatch.setattr(application_answers,'capture_answers',capture)
    assert asyncio.run(m.EasyApplyRunner.fill(r,observed))['committed']
    assert writes==[{'method':'fill','ref':'form:email','value':'fixture@example.test'}]


def test_dom_typeahead_filter_is_not_committed_but_explicit_selection_is():
    output=dom(modal('<div data-test-form-element><label for="city">City *</label><input id="city" role="combobox" aria-controls="cities" value="Chicago" required></div><ul id="cities" role="listbox"><li role="option">Chicago</li></ul>'),
               "document.querySelector('input').setAttribute('aria-valuetext','Chicago');null")
    assert not output['first']['linkedin']['questions'][0]['answered']
    assert output['second']['linkedin']['questions'][0]['answered']


def test_linkedin_input_typeahead_needs_dispatched_option_and_closed_menu():
    from job_applier.browser_controls import FORM
    body=modal('<div data-test-form-element><label for="city">City *</label><input id="city" role="combobox" aria-controls="cities" aria-expanded="true" value="Chicago" required></div><ul id="cities" role="listbox"><li role="option">Chicago</li></ul>')
    script='''const f=('''+FORM+'''); const options=f({method:'select_options',selector:'#city'});
f({method:'selection_dispatched',selector:'#city',option_ref:options.options[0].ref,label:'Chicago'});
const pending=f({method:'question',selector:'#city'});
document.querySelector('#cities').hidden=true;document.querySelector('#city').setAttribute('aria-expanded','false');
const committed=f({method:'verify_select',selector:'#city',label:'Chicago'});
document.querySelector('#city').value='Boston';
const changed=f({method:'question',selector:'#city'}); [pending,committed,changed]'''
    output=dom(body,script)
    assert not output['extra'][0]['answered']
    assert output['extra'][1]['committed']
    assert not output['extra'][2]['answered']


def test_dom_shared_fill_and_native_select_commit_values():
    from job_applier.browser_controls import FORM
    action='const f=('+FORM+'); [f({method:"fill",selector:"#text",value:"Approved"}),f({method:"select_native",selector:"#select",label:"No"})]'
    result=dom(modal('<div data-test-form-element><label for="text">Text *</label><textarea id="text" required></textarea></div><div data-test-form-element><label for="select">Choice *</label><select id="select" required><option>Select an option</option><option>Yes</option><option>No</option></select></div>'),action)
    assert all(item['committed'] for item in result['extra'])
    assert all(q['answered'] for q in result['second']['linkedin']['questions'])


def test_linkedin_confirmation_capture_requires_current_job_surface():
    from job_applier.submission import SCRIPT
    script='''const s=('''+SCRIPT+'''); s({name:'proof',active:true,requisition:'123456'}); JSON.stringify(window.proof.records)'''
    result=dom('<div data-job-id="999"><p>Your application was sent to WrongCo!</p></div><div role="dialog"><h2>Your application was sent to Example!</h2></div>',script)
    records=json.loads(result['extra'])
    assert len(records)==1 and records[0]['text']=='Your application was sent to Example!'
    empty=dom(modal('<button>Submit application</button>'),script)
    assert json.loads(empty['extra'])==[]


def test_native_dispatch_resolves_ownership_and_target(monkeypatch,tmp_path):
    from job_applier import workspace_host
    from test_local_sessions import setup,reserve,connect
    service,asset,jobs,workspaces,config=setup(tmp_path)
    session=connect(service,reserve(service,asset,jobs))
    host=object.__new__(workspace_host.WorkspaceHost)
    host.service=service;host.config=config;host.workspace_id=session['workspace_id']
    host.workspace=workspaces[0];host.host_id='host-'+session['workspace_id']
    called=[]
    def advance(cfg,client,own,params):called.append((cfg,own,params));return {'status':'fixture'}
    monkeypatch.setattr(helper(),'advance',advance)
    request={'instance_id':service.instance_id,'session_id':session['id'],'driver_id':session['driver_id'],
             'operation':'linkedin_easy_apply','parameters':{'seconds':60}}
    assert host._dispatch(request)=={'status':'fixture'}
    assert called[0][2]=={'seconds':60,'target_id':session['target_id']}
    assert called[0][1]['attempt_id']==session['attempt_id']
    assert called[0][0]['cdp_url']==workspaces[0]['cdp_url']
    request['driver_id']='another-driver'
    with pytest.raises(ValueError,match='driver_owned_elsewhere'):host._dispatch(request)


def test_advance_attaches_to_owned_page_and_only_closes_connection(monkeypatch):
    m=helper();from job_applier import cdp_client
    actions=[];page=object()
    class Browser:
        async def get_current_page(self):return page
        async def close(self):actions.append('close_connection')
    async def connect(url,**kwargs):
        actions.append(kwargs);return Browser()
    class Runner:
        def __init__(self,p,*args):assert p is page
        async def run(self,seconds):return {'status':'ready_for_review'}
    class Client:
        def call(self,op,**kwargs):
            actions.append(op)
            return package() if op=='application_context' else {}
    monkeypatch.setattr(cdp_client.CDPBrowser,'connect',connect);monkeypatch.setattr(m,'EasyApplyRunner',Runner)
    result=m.advance({'cdp_url':'http://127.0.0.1:9222'},Client(),{'attempt_id':1,'worker_id':'w','fence':1},{'target_id':'owned','seconds':10})
    assert result['status']=='ready_for_review'
    assert actions==['application_context','browser_observe',{'target_id':'owned','expected_mode':'headed'},'close_connection']
