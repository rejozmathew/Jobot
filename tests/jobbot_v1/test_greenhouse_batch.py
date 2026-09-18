"""Managed Greenhouse contract; isolated synthetic documents only."""
import asyncio
import json
import time

import pytest

from job_applier import browser_controls
from job_applier.simplify_boundary import SimplifyBoundary
from test_greenhouse_recovery import form_dom, widget


def test_greenhouse_routes_to_batch_even_while_writer_active():
    for status in ('ready', 'active', 'unknown', 'needs_review', 'complete'):
        result = browser_controls.next_operation('greenhouse', {'status': status})
        assert result['operation'] == 'greenhouse_advance'


def test_invalid_selected_label_is_not_committed():
    html = widget(selection='IL').replace('id="veteran" role=', 'id="veteran" aria-invalid="true" role=')
    result = form_dom(html, [{'method': 'verify_select', 'selector': '#veteran', 'value': 'IL', 'label': 'IL'}])['results'][0]
    assert result['value_matches'] and not result['committed']
    assert result['validation']['rejected']


def test_unassociated_phone_menu_never_supplies_state_options():
    html = '''<label for="state">State *</label><div class="select__control">
<input id="state" role="combobox" aria-expanded="true"></div>
<ul id="iti-0__country-listbox" role="listbox"><li role="option">United States +1</li></ul>'''
    result = form_dom(html, [{'method': 'inspect', 'selector': '#state'},
        {'method': 'select_options', 'selector': '#state'}])['results'][-1]
    assert result['options'] == []


def test_search_is_distinct_from_committed_text_fill():
    html = widget(selection='')
    result = form_dom(html, [{'method': 'search', 'selector': '#veteran', 'value': 'Illinois'}])['results'][0]
    assert result['focused'] and not result['committed']


def test_enabled_greenhouse_needs_review_can_dispatch_first_and_second_pass():
    for count in (0, 1):
        observed = {'greenhouse': True, 'status': 'needs_review', 'writer_safe': True,
            'controls': {'autofill': {'enabled': True}},
            'autofill_receipt': {'dispatch_count': count, 'state': 'settled'}, 'required_residual_count': 3}
        assert SimplifyBoundary.decide(observed)['action'] == 'autofill'


def test_greenhouse_shared_answer_functions_remain_linkedin_compatible():
    from job_applier import application_answers, linkedin_easy_apply
    for name in ('label_has', 'match_answer_to_option', 'approved_answer', 'answer_action', 'saved_answer'):
        assert getattr(application_answers, name) is getattr(linkedin_easy_apply, name)


def test_greenhouse_state_alias_is_scoped_and_exact():
    from job_applier.greenhouse_fast import greenhouse_answer
    profile = {'identity': {'address': {'state': 'Illinois'}}}
    question = {'question': 'State', 'kind': 'select', 'options': [
        {'label': 'AK', 'value': 'AK'}, {'label': 'IL', 'value': 'IL'}]}
    assert greenhouse_answer(question, profile) == {'label': 'IL', 'value': 'IL'}
    assert greenhouse_answer(dict(question, question='Are you authorized to work in the United States?'), profile) is None


def batch_html(unknowns=0, simplify=''):
    fields='<label for="email">Email</label><input id="email" name="email" type="email" required>'
    fields+=''.join(f'<label for="f{i}">Approved fact {i}</label><input id="f{i}" name="f{i}" required>' for i in range(14))
    fields+=''.join(f'<label for="u{i}">Employer question {i}?</label><input id="u{i}" name="u{i}" required>' for i in range(unknowns))
    return '''<!doctype html><html><body><p>Synthetic fixture; not official Simplify support</p><form>'''+fields+'''
<button type="button" id="submit">Submit application</button></form>'''+simplify+'''
<script>submit.onclick=async e=>{if(!e.isTrusted)return;await fetch('/fake-submit',{method:'POST'});document.body.innerHTML='<p>Thank you for applying</p>'};</script></body></html>'''


def batch_profile():
    return {'identity':{'email':'fixture@example.test'},'standard_answers':{f'Approved fact {i}':f'approved-{i}' for i in range(14)}}


@pytest.mark.parametrize('mode',['top','same','cross'])
def test_fifteen_approved_fields_batch_and_shared_submission(tmp_path,monkeypatch,mode):
    import test_embedded_forms as fixture
    from job_applier.greenhouse_fast import GreenhouseRunner
    monkeypatch.setattr(fixture,'FORM_HTML',batch_html())
    async def run():
        async with fixture.fixture_browser(tmp_path,mode=mode) as (page,package,submissions):
            package['attempt'].update(profile_json=batch_profile(),settings_json={'submission_mode':'submit'})
            ledger=fixture.SubmissionLedger();calls=[]
            def call(op,**params):calls.append((op,params));return ledger.call(op,**params)
            runner=GreenhouseRunner(page,call,package,{'attempt_id':1,'worker_id':'fixture','fence':1},
                {'spool_dir':str(tmp_path/'spool'),'cdp_url':page.fixture_endpoint},page.target_id)
            result=await runner.run(30)
            assert result['status']=='applied',result
            assert result['completed_count']==15 and result['batch_count']==1,result
            assert result['field_action_count']==15 and result['autofill_dispatch_count']==0
            assert submissions==['/fake-submit']
            assert len([p for op,p in calls if op=='action_start' and p['tool_name']=='greenhouse_fast.batch'])==1
            operational=json.dumps([p for op,p in calls if op=='event'])
            assert 'approved-0' not in operational and 'fixture@example.test' not in operational
            print('GREENHOUSE_BATCH_METRICS',json.dumps({k:result[k] for k in ('elapsed_seconds','field_action_count','batch_count','completed_count','autofill_dispatch_count')}))
    asyncio.run(run())


def test_grouped_plan_reload_restores_only_verified_answers_with_fresh_refs(tmp_path,monkeypatch):
    import test_embedded_forms as fixture
    from job_applier.greenhouse_fast import GreenhouseRunner
    monkeypatch.setattr(fixture,'FORM_HTML',batch_html(2))
    async def run():
        async with fixture.fixture_browser(tmp_path,mode='top') as (page,package,submissions):
            package['attempt'].update(profile_json=batch_profile(),settings_json={'submission_mode':'review'})
            ledger=fixture.SubmissionLedger();cfg={'spool_dir':str(tmp_path/'spool'),'cdp_url':page.fixture_endpoint}
            def runner():return GreenhouseRunner(page,ledger.call,package,{'attempt_id':1,'worker_id':'fixture','fence':1},cfg,page.target_id)
            first=await runner().run(30)
            assert first['status']=='questions_required' and len(first['questions'])==2,first
            plan=[{'ref':q['ref'],'question_key':q['question_key'],'answer':'approved semantic '+str(i),'basis':'executor approved fact '+str(i)} for i,q in enumerate(first['questions'])]
            second=await runner().run(30,plan)
            assert second['status']=='ready_for_review' and second['field_action_count']==2,second
            assert (await page.reload())['document_replaced']
            stale=await runner().run(30,plan)
            assert any(f['reason']=='stale_answer_binding' for f in stale['control_failures']),stale
            restored=await runner().run(30)
            assert restored['status']=='ready_for_review' and not restored['questions'],restored
            assert await page.evaluate('u0.value')=='approved semantic 0'
            assert submissions==[]
    asyncio.run(run())


@pytest.mark.parametrize('mode',['top','cross'])
def test_blur_sensitive_search_trusted_fallback_and_validation_settlement(tmp_path,monkeypatch,mode):
    import test_embedded_forms as fixture
    html='''<label for="state">State</label><div class="select__control" id="widget">
<span class="select__single-value"></span><input id="state" role="combobox" aria-expanded="false" aria-controls="react-select-73-listbox"></div>
<ul id="react-select-73-listbox" role="listbox" hidden></ul><input id="ordinary">
<script>const menu=document.getElementById('react-select-73-listbox');
state.onclick=e=>{if(e.isTrusted){menu.hidden=false;state.setAttribute('aria-expanded','true')}};
state.onblur=()=>{menu.hidden=true};state.oninput=e=>{if(e.isTrusted&&state.value==='IL')menu.innerHTML='<li tabindex="0" role="option" data-value="IL">IL</li>'};
menu.onmousedown=e=>e.preventDefault();menu.onclick=e=>{if(!e.isTrusted)return;
widget.innerHTML='<span class="select__single-value">IL</span><input id="state" role="combobox" aria-invalid="true" aria-controls="react-select-73-listbox" aria-expanded="false">';
menu.hidden=true;setTimeout(()=>state.removeAttribute('aria-invalid'),250)};</script>'''
    monkeypatch.setattr(fixture,'FORM_HTML',html)
    async def run():
        async with fixture.fixture_browser(tmp_path,mode=mode) as (page,package,_):
            observed=await browser_controls.observe(page,package)
            field=next(f for f in observed['inventory'] if f['label']=='State')
            result=await browser_controls.form_action(page,{'method':'select','ref':field['ref'],'label':'IL'})
            assert result['committed'] and result['value_matches'],result
    asyncio.run(run())


def test_separate_runtime_calls_keep_simplify_receipts_and_reload_resets(tmp_path,monkeypatch):
    import test_embedded_forms as fixture
    from test_local_sessions import setup,connect,own
    from job_applier.managed_client import LocalClient
    from job_applier.application_runtime import browser_action
    panel='''<div class="simplify-jobs-shadow-root"><button type="button" id="fill">Autofill this page</button><p id="status">Need to review (15)</p></div>
<script>window.fills=0;fill.onclick=()=>{window.fills++;setTimeout(()=>{document.getElementById('status').textContent='Filling your application';
setTimeout(()=>{email.value='fixture@example.test';document.getElementById('status').textContent='Need to review (14)'},150)},300)};</script>'''
    monkeypatch.setattr(fixture,'FORM_HTML',batch_html(simplify=panel))
    async def run():
        async with fixture.fixture_browser(tmp_path,mode='top') as (page,fixture_package,_):
            service,asset,_,ws,cfg=setup(tmp_path/'ledger');ws[0].update(cdp_url=page.fixture_endpoint,mode='headless');service.configure_workspaces(ws)
            job=service.intake(url=fixture_package['job']['url']);service.eligibility(job['id'],'ready',reason='Synthetic')
            session=connect(service,service.reserve_session(request_id='gh-boundary',job_id=job['id'],identity_id='candidate',driver_id='fixture',workspace_ids=['workspace-0'],concurrency_limit=1,resume_asset_id=asset['id']),page.target_id)
            owner=own(service,session);package=service.application_context(owner['attempt_id'])
            cfg.update(cdp_url=page.fixture_endpoint,browser_mode='headless',spool_dir=str(tmp_path/'spool'))
            client=LocalClient(cfg,service=service)
            async def fill():return await asyncio.to_thread(browser_action,cfg,client,owner,package,page.target_id,{'method':'simplify','action':'autofill'})
            first=await fill();assert first['execution']=='clicked' and first['native_takeover_authorized'],first
            assert first['observation']['autofill_receipt']['dispatch_count']==1
            await page.evaluate("f0.outerHTML='<input id=f0 name=f0 required>';document.querySelector('.simplify-jobs-shadow-root p').textContent='Need to review (14)'")
            second=await fill();assert second['execution']=='clicked',second
            assert second['observation']['autofill_receipt']['dispatch_count']==2
            await asyncio.to_thread(browser_action,cfg,client,owner,package,page.target_id,{'method':'reload'})
            third=await fill();assert third['observation']['autofill_receipt']['dispatch_count']==1,third
    asyncio.run(run())


@pytest.mark.parametrize('fill_all',[True,False])
def test_automatic_second_pass_uses_native_residuals_then_never_clobbers_repairs(tmp_path,monkeypatch,fill_all):
    import test_embedded_forms as fixture
    from job_applier.greenhouse_fast import GreenhouseRunner
    panel='''<div class="simplify-jobs-shadow-root"><button type="button" id="fill">Autofill this page</button><p id="status">Need to review (15)</p></div>
<script>window.fills=0;fill.onclick=()=>{window.fills++;setTimeout(()=>{document.getElementById('status').textContent='Filling your application';
setTimeout(()=>{email.value='fixture@example.test';FILL_ALL;document.getElementById('status').textContent='Need to review (99)'},150)},300)};</script>'''
    panel=panel.replace('FILL_ALL',"for(let i=0;i<14;i++)document.getElementById('f'+i).value='approved-'+i" if fill_all else "f0.value='temporary wrong value'")
    monkeypatch.setattr(fixture,'FORM_HTML',batch_html(simplify=panel))
    async def run():
        async with fixture.fixture_browser(tmp_path,mode='top') as (page,package,_):
            package['attempt'].update(profile_json=batch_profile(),settings_json={'submission_mode':'review'})
            ledger=fixture.SubmissionLedger();cfg={'spool_dir':str(tmp_path/'spool'),'cdp_url':page.fixture_endpoint}
            def runner():return GreenhouseRunner(page,ledger.call,package,{'attempt_id':1,'worker_id':'fixture','fence':1},cfg,page.target_id)
            first=await runner().run(30)
            assert first['status']=='ready_for_review',first
            assert first['autofill_dispatch_count']==(1 if fill_all else 2),first
            assert await page.evaluate('f0.value')=='approved-0'
            second=await runner().run(15)
            assert second['field_action_count']==0 and second['autofill_dispatch_count']==first['autofill_dispatch_count'],second
    asyncio.run(run())


def test_plugin_session_host_dispatch_reaches_real_runner_without_self_writer_conflict(tmp_path,monkeypatch):
    import test_embedded_forms as fixture
    from test_local_sessions import setup,connect
    from job_applier.workspace_host import WorkspaceHost
    from job_applier.hermes_plugin import PluginController,SCHEMA
    from job_applier import workspace_host
    monkeypatch.setattr(fixture,'FORM_HTML',batch_html())
    async def run():
        async with fixture.fixture_browser(tmp_path,mode='top') as (page,fixture_package,_):
            service,asset,_,ws,cfg=setup(tmp_path/'ledger');ws[0].update(cdp_url=page.fixture_endpoint,mode='headless');service.configure_workspaces(ws)
            profile=batch_profile();profile['identity']['email']='candidate@example.test'
            service.identity(identity_id='candidate',person_key='same-person',email='candidate@example.test',profile=profile)
            job=service.intake(url=fixture_package['job']['url']);service.eligibility(job['id'],'ready',reason='Synthetic')
            session=connect(service,service.reserve_session(request_id='gh-dispatch',job_id=job['id'],identity_id='candidate',driver_id='fixture',workspace_ids=['workspace-0'],concurrency_limit=1,resume_asset_id=asset['id']),page.target_id)
            cfg.update(cdp_url=page.fixture_endpoint,browser_mode='headless',spool_dir=str(tmp_path/'spool'))
            host=object.__new__(WorkspaceHost);host.config=cfg;host.service=service;host.workspace=ws[0];host.workspace_id='workspace-0';host.host_id='host-workspace-0'
            def transport(config,session,operation,parameters,driver):
                return host._dispatch({'instance_id':config['instance_id'],'session_id':session['id'],
                    'driver_id':driver,'operation':operation,'parameters':parameters})
            monkeypatch.setattr(workspace_host,'call_host',transport)
            plugin=PluginController('synthetic');monkeypatch.setattr(plugin,'_config',lambda:cfg)
            plugin.local_sessions['fixture']=session['id']
            assert 'greenhouse_advance' in SCHEMA['parameters']['properties']['operation']['enum']
            result=json.loads(await asyncio.to_thread(plugin.handle,{'operation':'greenhouse_advance','parameters':{'seconds':30,'target_id':'arbitrary-tab'}},session_id='fixture'))
            assert result.get('handler')=='greenhouse_fast' and result.get('completed_count')==15,result
            assert result['document']['target_id']==page.target_id
            assert result['status']=='ready_for_review',result
            report=service.attempt_report(session['attempt_id'])
            assert not report['attempt']['completed_at']
    asyncio.run(run())


def test_phone_widget_owns_country_menu_and_react_ids_need_not_equal_business_id():
    html='''<div class="iti"><button id="phone" role="combobox" aria-controls="iti-0__country-listbox">Country</button>
<ul id="iti-0__country-listbox" role="listbox"><li role="option">United States +1</li></ul></div>
<div class="select__control"><input id="business-state" role="combobox" aria-activedescendant="react-select-91-option-0"></div>
<ul role="listbox" id="react-select-91-listbox"><li id="react-select-91-option-0" role="option">IL</li></ul>'''
    results=form_dom(html,[{'method':'select_options','selector':'#phone'}, {'method':'select_options','selector':'#business-state'}])['results']
    assert [o['label'] for o in results[0]['options']]==['United States +1']
    assert [o['label'] for o in results[1]['options']]==['IL']


def test_failed_option_inspection_closes_only_its_menu(tmp_path,monkeypatch):
    import test_embedded_forms as fixture
    html='''<label for="state">State</label><div class="select__control"><input id="state" role="combobox" required aria-controls="own" aria-expanded="false"></div>
<div id="own" role="listbox" hidden></div><div id="other" role="listbox">Unrelated menu</div>
<script>state.onclick=()=>{own.hidden=false;state.setAttribute('aria-expanded','true')};state.onblur=()=>{own.hidden=true;state.setAttribute('aria-expanded','false')};</script>'''
    monkeypatch.setattr(fixture,'FORM_HTML',html)
    async def run():
        async with fixture.fixture_browser(tmp_path,mode='top') as (page,package,_):
            field=(await browser_controls.observe(page,package))['inventory'][0]
            result=await browser_controls.required_questions(page,[field['ref']])
            assert result['skipped'] and not result['questions']
            assert await page.evaluate('own.hidden&&!other.hidden')
    asyncio.run(run())


def test_unapproved_journal_entries_are_not_restorable(tmp_path):
    from job_applier.greenhouse_fast import GreenhouseRunner
    folder=tmp_path/'answers';folder.mkdir()
    (folder/'attempt-1.json').write_text(json.dumps({'attempt_id':1,'job_url':'https://example.test',
        'answers':[{'question_key':'q','answer_value':'wrong','answer_basis':'captured','source':'executor_click','verified':False}]}))
    class Page:pass
    runner=GreenhouseRunner(Page(),lambda *a,**k:{},{'job':{'url':'https://example.test'},'attempt':{}},
        {'attempt_id':1},{'spool_dir':str(tmp_path)},'owned')
    assert runner.restored=={}


def test_native_multiselect_verifies_the_whole_exact_set():
    html='<label for="s">Regions</label><select multiple id="s"><option value="a" selected>A</option><option value="b" selected>B</option><option value="c">C</option></select>'
    good,bad,changed,verified=form_dom(html,[
        {'method':'verify_select','selector':'#s','value':['b','a'],'label':['B','A']},
        {'method':'verify_select','selector':'#s','value':['a'],'label':['A']},
        {'method':'select_native','selector':'#s','value':['b','c'],'label':['B','C']},
        {'method':'verify_select','selector':'#s','value':['b','c'],'label':['B','C']}])['results']
    assert good['committed'] and not bad['committed'] and changed['committed'] and verified['committed']


def test_resume_rejection_reuploads_only_scoped_selected_asset(tmp_path,monkeypatch):
    import hashlib
    import test_embedded_forms as fixture
    from job_applier.greenhouse_fast import GreenhouseRunner
    html=batch_html().replace('<button type="button" id="submit">','''<section><div id="resume-widget"><label for="resume-file">Resume/CV *</label>
<button type="button" id="remove" aria-label="Remove resume">X</button><span id="resume-error" role="alert">Resume/CV is required</span>
<input id="resume-file" type="file" hidden></div></section><label>Cover Letter</label><input id="cover" type="file">
<script>remove.onclick=e=>{if(e.isTrusted)document.getElementById('resume-file').hidden=false};document.getElementById('resume-file').onchange=()=>document.getElementById('resume-error').remove();</script>
<button type="button" id="submit">''')
    monkeypatch.setattr(fixture,'FORM_HTML',html)
    async def run():
        async with fixture.fixture_browser(tmp_path,mode='top') as (page,package,_):
            path=tmp_path/'selected.pdf';path.write_bytes(b'synthetic selected asset')
            package['documents']={'assets':[{'id':'selected','kind':'resume','storage_ref':path.as_uri(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]}
            package['attempt'].update(profile_json=batch_profile(),settings_json={'submission_mode':'review'})
            ledger=fixture.SubmissionLedger()
            runner=GreenhouseRunner(page,ledger.call,package,{'attempt_id':1,'worker_id':'fixture','fence':1},
                {'spool_dir':str(tmp_path/'spool'),'cdp_url':page.fixture_endpoint},page.target_id)
            result=await runner.run(30)
            assert result['status']=='ready_for_review',result
            assert await page.evaluate("document.getElementById('resume-file').files[0].name")=='selected.pdf'
            assert await page.evaluate('cover.files.length')==0
    asyncio.run(run())


def test_accepted_linkedin_intake_uses_current_greenhouse_document_and_submission(tmp_path,monkeypatch):
    import test_embedded_forms as fixture
    from job_applier.greenhouse_fast import advance
    from job_applier.managed_identity import public_url
    monkeypatch.setattr(fixture,'FORM_HTML',batch_html())
    async def run():
        async with fixture.fixture_browser(tmp_path,mode='top') as (page,package,submissions):
            current=package['job']['url'];package['job']=dict(package['job'],url='https://www.linkedin.com/jobs/view/424242')
            package['attempt'].update(profile_json=batch_profile(),settings_json={'submission_mode':'submit'})
            ledger=fixture.SubmissionLedger()
            class Client:
                def call(self,op,**params):
                    if op=='application_context':return package
                    if op=='browser_observe':return {'native_takeover_authorized':True,'identity':{'status':'same_job'},
                        'target_id':page.target_id,'observation':{'url':public_url(current)}}
                    return ledger.call(op,**params)
            result=await asyncio.to_thread(advance,{'cdp_url':page.fixture_endpoint,'browser_mode':'headless','spool_dir':str(tmp_path/'spool')},
                Client(),{'attempt_id':1,'worker_id':'fixture','fence':1},{'target_id':page.target_id,'seconds':30})
            assert result['status']=='applied' and result['document']['url']==current,result
            assert submissions==['/fake-submit']
    asyncio.run(run())


def test_nonlocal_plugin_dispatches_registered_greenhouse_operation(monkeypatch):
    from job_applier.hermes_plugin import PluginController
    from job_applier import greenhouse_fast
    class Adapter:
        client=object()
        def _state(self):return {'attempt':{'attempt_id':1,'worker_id':'w','fence':1}}
        def flush(self):return False
    plugin=PluginController('synthetic');monkeypatch.setattr(plugin,'_config',lambda:{'transport':'http'})
    monkeypatch.setattr(plugin,'_adapter',lambda *a:Adapter())
    calls=[]
    def advance(config,client,owner,params):calls.append((owner,params));return {'handler':'greenhouse_fast','status':'continue'}
    monkeypatch.setattr(greenhouse_fast,'advance',advance)
    result=json.loads(plugin.handle({'operation':'greenhouse_advance','parameters':{'target_id':'owned','seconds':60}},session_id='fixture'))
    assert result['handler']=='greenhouse_fast' and calls[0][1]['target_id']=='owned',result


@pytest.mark.parametrize('control',['pause_requested','stop_requested'])
def test_batch_honors_control_between_fields_without_finishing_attempt(tmp_path,monkeypatch,control):
    import test_embedded_forms as fixture
    from job_applier.greenhouse_fast import GreenhouseRunner
    monkeypatch.setattr(fixture,'FORM_HTML',batch_html())
    async def run():
        async with fixture.fixture_browser(tmp_path,mode='top') as (page,package,submissions):
            package['attempt'].update(profile_json=batch_profile(),settings_json={'submission_mode':'submit'})
            ledger=fixture.SubmissionLedger();state={'control':'running'}
            def call(op,**params):
                if op=='heartbeat':return dict(state)
                if op=='event' and params['event_type']=='field_verified':state['control']=control
                return ledger.call(op,**params)
            runner=GreenhouseRunner(page,call,package,{'attempt_id':1,'worker_id':'fixture','fence':1},
                {'spool_dir':str(tmp_path/'spool'),'cdp_url':page.fixture_endpoint},page.target_id)
            result=await runner.run(30)
            assert result['reason']==control and result['completed_count']==1,result
            assert await page.evaluate('f0.value')==''
            assert not ledger.attempt.get('completed_at') and not submissions
    asyncio.run(run())
