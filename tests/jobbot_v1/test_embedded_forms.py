"""Real isolated browser regressions; no live ATS, profile or application data."""
import asyncio
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
from urllib.parse import parse_qs, urlsplit

import pytest

from job_applier.browser_controls import observe, form_action
from job_applier.cdp_client import CDPBrowser
from job_applier.workspace_process import OwnedProcess


FORM_HTML = """<!doctype html><html><body style="margin:20px">
<label for="privacy">I acknowledge the Candidate Privacy Statement</label>
<select id="privacy" name="privacy" required>
 <option value="">Select...</option><option value="ack">I acknowledge</option>
</select>
<label id="team-label">Do you have experience leading technology teams?</label>
<button id="team" role="combobox" aria-labelledby="team-label" aria-controls="options"
 aria-expanded="false" aria-required="true" type="button">Select...</button>
<div id="options" role="listbox" hidden>
 <div role="option" data-value="yes" tabindex="0">Yes</div>
 <div role="option" data-value="no" tabindex="0">No</div>
</div>
<label for="optional">Optional pronouns</label><input id="optional" name="pronouns">
<label for="resume">Resume</label><input id="resume" name="resume" type="file">
<label for="existing">How did you hear about us?</label>
<select id="existing"><option selected>LinkedIn</option><option>Other</option></select>
<label for="hidden-secret">Password</label><input id="hidden-secret" type="password" value="synthetic-only">
<label for="login-email">Account email</label><input id="login-email" type="email">
<div style="height:800px"></div>
<button id="submit" type="button">Submit application</button>
<script>
window.counts={opened:0,chosen:0,submitted:0};
team.onclick=e=>{if(!e.isTrusted)return;counts.opened++;options.hidden=false;team.setAttribute('aria-expanded','true')};
options.onclick=e=>{if(!e.isTrusted||e.target.getAttribute('role')!=='option')return;
 counts.chosen++;team.textContent=e.target.textContent;team.setAttribute('aria-expanded','false');options.hidden=true};
submit.onclick=async e=>{if(!e.isTrusted)return;counts.submitted++;
 await fetch('/fake-submit',{method:'POST'});document.body.innerHTML='<p>Thank you for applying</p>'};
</script></body></html>"""


@asynccontextmanager
async def fixture_browser(tmp_path, mode='cross', *, entry_url=None, submit_outcome=None):
    executable = os.environ.get('JOBBOT_BROWSER_TEST_EXE')
    if not executable:
        pytest.skip('Explicit isolated browser executable required')
    submissions = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = urlsplit(self.path)
            if route.path.endswith('/confirmation'):
                body='<p>Thank you for applying</p>'
            elif route.path in ('/form', '/top'):
                body = FORM_HTML
                if submit_outcome:
                    action={'redirect':"location.href='/form/confirmation?gh_jid=12345'",
                        'wrong_job':"location.href='/form/confirmation?gh_jid=67890'",
                        'transient':"document.body.innerHTML='<p>Thank you for applying</p>';setTimeout(()=>document.body.innerHTML='<p>Done</p>',20)"}.get(submit_outcome,'')
                    body=body.replace("document.body.innerHTML='<p>Thank you for applying</p>'",action)
            else:
                host = 'localhost' if mode == 'same' else '127.0.0.1'
                src = f'http://{host}:{self.server.server_port}/form?gh_jid=12345'
                body = ('<!doctype html><html><body style="margin:0">'
                        '<h1>Example Careers</h1><div style="height:550px"></div>'
                        f'<iframe title="Job application" id="application" src="{src}" '
                        'style="width:650px;height:1200px;margin-left:40px;border:4px solid black"></iframe>'
                        '</body></html>')
            encoded = body.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self):
            submissions.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    route = 'top' if mode == 'top' else 'jobs'
    url = entry_url or f'http://localhost:{server.server_port}/{route}?gh_jid=12345'
    profile = tmp_path / ('browser-' + mode)
    profile.mkdir()
    process = OwnedProcess.launch([
        executable, '--headless=new', '--disable-gpu', '--no-first-run', '--no-proxy-server',
        '--site-per-process', '--remote-debugging-port=0', '--user-data-dir=' + str(profile), url,
    ], stdout_path=tmp_path / ('browser-' + mode + '.out'), stderr_path=tmp_path / ('browser-' + mode + '.err'))
    browser = None
    try:
        portfile = profile / 'DevToolsActivePort'
        deadline = time.monotonic() + 15
        while True:
            try:
                port = int(portfile.read_text().splitlines()[0])
                if not 0 < port < 65536:
                    raise ValueError('Invalid browser port')
                break
            except (FileNotFoundError, PermissionError, IndexError, ValueError):
                # Windows can expose the file before Chrome releases its write
                # handle or finishes writing it. Wait for readable readiness.
                if time.monotonic() >= deadline:
                    raise TimeoutError('Synthetic browser did not publish a readable debugging port') from None
                await asyncio.sleep(.05)
        endpoint = f'http://127.0.0.1:{port}'
        with urllib.request.urlopen(endpoint + '/json/list') as response:
            tabs = json.load(response)
        target = next(t['id'] for t in tabs if t['type'] == 'page')
        browser = await CDPBrowser.connect(endpoint, target_id=target, expected_mode='headless')
        page = await browser.get_current_page()
        page.fixture_endpoint = endpoint
        deadline = time.monotonic() + 8
        while not await page.evaluate("location.href==="+json.dumps(url)+"&&document.readyState==='complete'"):
            assert time.monotonic() < deadline, 'Synthetic fixture did not settle'
            await asyncio.sleep(.05)
        package = {'job': {'id': 'fixture-job', 'url': url, 'company': 'Example'},
                   'attempt': {'profile_json': {}, 'settings_json': {}}, 'platform': 'unknown'}
        yield page, package, submissions
    finally:
        if browser:
            await browser.close()
        process.stop()
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize('mode', ['top', 'same', 'cross'])
def test_one_select_operation_works_in_each_document(tmp_path, mode):
    async def check():
        async with fixture_browser(tmp_path, mode) as (page, package, _):
            screen = await observe(page, package)
            fields = {c['label']: c for c in screen['inventory']}
            privacy = fields.get('I acknowledge the Candidate Privacy Statement')
            assert privacy, 'The application field must be observed, including inside a frame'
            assert privacy['required']
            assert not fields['Optional pronouns']['required']
            result = await form_action(page, {'method': 'select', 'ref': privacy['ref'], 'label': 'I acknowledge'})
            assert result.get('committed'), result
            selected = await form_action(page, {'method': 'select', 'ref': privacy['ref'], 'label': 'I acknowledge'})
            assert selected['committed'] and selected.get('unchanged'), selected
            team = fields['Do you have experience leading technology teams?']
            result = await form_action(page, {'method': 'select', 'ref': team['ref'], 'label': 'Yes'})
            assert result.get('committed'), result
            result = await form_action(page, {'method': 'select', 'ref': fields['How did you hear about us?']['ref'], 'label': 'LinkedIn'})
            assert result['committed'] and result.get('unchanged'), result
    asyncio.run(check())


def test_frame_reference_is_rejected_after_iframe_replacement(tmp_path):
    async def check():
        async with fixture_browser(tmp_path) as (page, package, _):
            screen = await observe(page, package)
            privacy = next((c for c in screen['inventory'] if c['name'] == 'privacy'), None)
            assert privacy, 'Embedded control must be available before replacement'
            await page.evaluate("document.getElementById('application').outerHTML='<iframe title=Advertisement src=about:blank></iframe>'")
            result = await form_action(page, {'method': 'select', 'ref': privacy['ref'], 'label': 'I acknowledge'})
            assert not result.get('committed')
            assert result['execution'] == 'not_executed'
    asyncio.run(check())


def test_parent_overlay_blocks_frame_pointer_activation(tmp_path):
    async def check():
        async with fixture_browser(tmp_path) as (page, package, _):
            screen = await observe(page, package)
            team = next((c for c in screen['inventory'] if c['role'] == 'combobox'), None)
            assert team, 'Embedded combobox must be observed'
            await page.evaluate("const cover=document.createElement('div');cover.id='cover';cover.style='position:fixed;inset:0;z-index:999;background:white';document.body.append(cover)")
            result = await form_action(page, {'method': 'select', 'ref': team['ref'], 'label': 'Yes'})
            assert not result.get('committed')
            assert result['execution'] == 'not_executed'
            assert 'obscur' in result.get('reason', '')
    asyncio.run(check())


def test_frame_ref_survives_reconnect_but_not_document_navigation(tmp_path):
    async def check():
        async with fixture_browser(tmp_path) as (page, package, _):
            screen = await observe(page, package)
            field = next(c for c in screen['inventory'] if c['name'] == 'privacy')
            # A fresh connection has no Python-side frame/ref inventory, just
            # as on the next session-scoped CLI call.
            browser = await CDPBrowser.connect(page.fixture_endpoint, target_id=page.target_id, expected_mode='headless')
            try:
                reconnected = await browser.get_current_page()
                reconnected.application_package = package
                result = await form_action(reconnected, {'method': 'select', 'ref': field['ref'], 'label': 'I acknowledge'})
                assert result.get('committed'), result
                await page.evaluate("document.getElementById('application').src += '&changed=1'")
                result = await form_action(reconnected, {'method': 'select', 'ref': field['ref'], 'label': 'I acknowledge'})
                assert not result.get('committed') and result['execution'] == 'not_executed'
            finally:
                await browser.close()
    asyncio.run(check())


def test_upload_answer_capture_and_credential_mask_in_frame(tmp_path):
    async def check():
        from job_applier.application_answers import capture_answers
        from job_applier.browser_controls import upload_file
        from job_applier.browser_frames import resolve_control
        from job_applier.managed_credentials import capture_private_screenshot
        async with fixture_browser(tmp_path) as (page, package, _):
            screen = await observe(page, package)
            fields = {c['name'] or c['role']: c for c in screen['inventory']}
            asset = tmp_path / 'approved-fixture.txt';asset.write_text('synthetic approved upload')
            await upload_file(page, {'ref': fields['resume']['ref']}, asset)
            child, _ = await resolve_control(page, {'ref': fields['resume']['ref']})
            assert await child.evaluate("document.getElementById('resume').files[0].name") == asset.name
            result = await form_action(page, {'method': 'select', 'ref': fields['combobox']['ref'], 'label': 'Yes'})
            assert result.get('committed'), result
            history = await capture_answers(page, {'spool_dir':str(tmp_path)}, package, {'attempt_id':1})
            saved = json.loads(Path(history['answer_history_path']).read_text())
            assert any(a['question'].startswith('Do you have experience') and a['answer'] == 'Yes' for a in saved['answers'])
            original = page.screenshot
            async def screenshot(path):
                assert await child.evaluate("getComputedStyle(document.getElementById('hidden-secret')).visibility") == 'hidden'
                return await original(path)
            page.screenshot = screenshot
            await capture_private_screenshot(page, tmp_path / 'masked.png')
            assert await child.evaluate("getComputedStyle(document.getElementById('hidden-secret')).visibility") == 'visible'
    asyncio.run(check())


def test_embedded_writer_activity_and_value_changes_reach_shared_gate(tmp_path):
    async def check():
        from job_applier.browser_controls import observe_writers
        from job_applier.browser_frames import resolve_control
        async with fixture_browser(tmp_path) as (page, package, _):
            screen = await observe(page, package)
            field = next(c for c in screen['inventory'] if c['name'] == 'privacy')
            child, _ = await resolve_control(page, {'ref':field['ref']})
            before = await observe_writers(page, package)
            await form_action(page, {'method':'select','ref':field['ref'],'label':'I acknowledge'})
            after = await observe_writers(page, package)
            assert before['application_frames'] != after['application_frames'], 'Child value changes must prevent a stable writer snapshot'
            await child.evaluate("const host=document.createElement('div');host.className='simplify-jobs-shadow-root';host.attachShadow({mode:'open'}).innerHTML='<p>Filling your application</p>';document.body.append(host)")
            busy = await observe_writers(page, package)
            assert busy['status'] == 'active' and not busy['writer_safe']
    asyncio.run(check())


def test_embedded_simplify_controls_route_to_their_observed_document(tmp_path):
    async def check():
        from job_applier.browser_controls import simplify_document
        from job_applier.browser_frames import resolve_control
        from job_applier.simplify_boundary import SimplifyBoundary,CLICK
        async with fixture_browser(tmp_path) as (page,package,_):
            screen=await observe(page,package)
            child,_=await resolve_control(page,{'ref':screen['inventory'][0]['ref']})
            await child.evaluate("const host=document.createElement('div');host.className='simplify-jobs-shadow-root';host.attachShadow({mode:'open'}).innerHTML='<button>Autofill this page</button>';host.shadowRoot.querySelector('button').onclick=()=>host.shadowRoot.innerHTML='<p>Autofill complete</p>';document.body.append(host)")
            screen=await observe(page,package)
            control=next(c for c in screen['simplify_inventory'] if c['operation']=='autofill')
            document,observed,local=await simplify_document(page,ref=control['ref'])
            assert document is child or document.frame_id==child.frame_id
            result=await document.evaluate_function(CLICK,{'ref':local['ref'],'operation':'autofill','url':observed['url'],'page_ref':observed['page_ref']})
            assert result['clicked'],result
            await child.evaluate("document.querySelector('.simplify-jobs-shadow-root').shadowRoot.innerHTML='<button>Autofill this page</button>';document.querySelector('.simplify-jobs-shadow-root').shadowRoot.querySelector('button').onclick=()=>document.querySelector('.simplify-jobs-shadow-root').shadowRoot.innerHTML='<p>Autofill complete</p>'")
            document,_,_=await simplify_document(page,operation='autofill')
            result=await SimplifyBoundary(document,budget_seconds=1).perform('autofill')
            assert result['execution']=='clicked',result
    asyncio.run(check())


def test_duplicate_native_option_values_select_the_exact_label(tmp_path):
    async def check():
        from job_applier.browser_frames import resolve_control
        async with fixture_browser(tmp_path) as (page,package,_):
            screen=await observe(page,package)
            target=next(c for c in screen['inventory'] if c['name']=='privacy')
            child,_=await resolve_control(page,{'ref':target['ref']})
            await child.evaluate("document.getElementById('privacy').innerHTML='<option value=on>Yes</option><option value=on>No</option>'")
            result=await form_action(page,{'method':'select','ref':target['ref'],'value':'on','label':'No'})
            assert result['committed'] and result['label']=='No',result
            assert await child.evaluate("document.getElementById('privacy').selectedIndex")==1
    asyncio.run(check())


@pytest.mark.parametrize('kind',['native','aria'])
def test_radio_questions_keep_distinct_option_refs_and_verify_the_chosen_answer(tmp_path,kind):
    async def check():
        from job_applier.browser_controls import required_questions
        from job_applier.browser_frames import resolve_control
        async with fixture_browser(tmp_path) as (page,package,_):
            screen=await observe(page,package)
            child,_=await resolve_control(page,{'ref':screen['inventory'][0]['ref']})
            html='<fieldset><legend>Have you managed a budget?</legend>'
            if kind=='native':html+='<label><input type=radio name=budget required>Yes</label><label><input type=radio name=budget required>No</label>'
            else:html+='<div role=radio tabindex=0 aria-required=true aria-checked=false aria-label=Yes>Yes</div><div role=radio tabindex=0 aria-required=true aria-checked=false aria-label=No>No</div>'
            await child.evaluate_function('''html=>{const section=document.createElement('section');section.innerHTML=html+'</fieldset>';
                document.body.prepend(section);for(const item of section.querySelectorAll('[role=radio]'))item.onclick=e=>{
                    if(!e.isTrusted)return;for(const option of section.querySelectorAll('[role=radio]'))option.setAttribute('aria-checked',String(option===item));};}''',html)
            screen=await observe(page,package)
            field=next(c for c in screen['inventory'] if c['type']=='radio' or c['role']=='radio')
            question=(await required_questions(page,[field['ref']]))['questions'][0]
            option=next(o for o in question['data']['options'] if o['label']=='Yes')
            refs=question['option_refs']
            assert len(refs)==2
            result=await form_action(page,{'method':'check','ref':refs[(option['value'],option['label'])],'value':True})
            assert result['committed'],result
    asyncio.run(check())


def test_embedded_credentials_use_private_helper_and_one_document(tmp_path):
    async def check():
        from job_applier.managed_credentials import fill_page_credentials
        async with fixture_browser(tmp_path) as (page, package, _):
            screen=await observe(page,package)
            email=next(c for c in screen['inventory'] if c['type']=='email')
            password=next(c for c in screen['inventory'] if c['type']=='password')
            profile=tmp_path/'synthetic-credentials.json'
            profile.write_text(json.dumps({'accounts':{'default':{'email':'fixture@example.test','password':'fixture-password-only'}}}))
            package['attempt']['profile_json']={'identity':{'email':'fixture@example.test'}}
            result=await fill_page_credentials({'credential_profile_path':str(profile)},package,page,
                {'email_ref':email['ref'],'password_ref':password['ref']})
            assert result['values_committed'],result
            assert 'fixture-password-only' not in json.dumps(result)
            ordinary=await form_action(page,{'method':'fill','ref':password['ref'],'value':'not-allowed'})
            assert ordinary['reason']=='use_private_credentials_helper'
            mixed=await fill_page_credentials({'credential_profile_path':str(profile)},package,page,
                {'email_ref':'#parent-email','password_ref':password['ref']})
            assert not mixed['values_committed']
    asyncio.run(check())


def test_runtime_captures_missing_question_then_applies_exact_human_answer(tmp_path):
    async def check():
        from job_applier.application_runtime import browser_action
        from job_applier.managed_client import LocalClient
        from test_local_sessions import setup,connect,own
        async with fixture_browser(tmp_path) as (page, fixture_package, submissions):
            service,asset,_,workspaces,cfg=setup(tmp_path/'ledger')
            workspaces[0].update(cdp_url=page.fixture_endpoint,mode='headless')
            service.configure_workspaces(workspaces)
            service.identity(identity_id='candidate',person_key='same-person',email='candidate@example.test',
                profile={'identity':{'email':'candidate@example.test'},'application_answer_policy':{'routine_privacy_consent':True}})
            job=service.intake(url=fixture_package['job']['url'])
            service.eligibility(job['id'],'ready',reason='Synthetic job')
            session=service.reserve_session(request_id='embedded-human-answer',job_id=job['id'],identity_id='candidate',
                driver_id='fixture-driver',workspace_ids=['workspace-0'],concurrency_limit=1,resume_asset_id=asset['id'])
            session=connect(service,session,page.target_id);owner=own(service,session)
            package=service.application_context(owner['attempt_id'])
            cfg.update(cdp_url=page.fixture_endpoint,browser_mode='headless',spool_dir=str(tmp_path/'spool'))
            client=LocalClient(cfg,service=service)
            screen=await observe(page,package)
            refs=[c['ref'] for c in screen['inventory'] if c['name'] in ('privacy','pronouns') or c['role']=='combobox']
            result=await asyncio.to_thread(browser_action,cfg,client,owner,package,page.target_id,
                {'method':'request_answers','refs':refs})
            assert len(result['questions'])==1,result
            question=result['questions'][0]
            assert question['options']==[{'value':'yes','label':'Yes'},{'value':'no','label':'No'}]
            assert question['question']=='Do you have experience leading technology teams?'
            assert any(item['reason']=='optional_question' for item in result['skipped'])
            assert result['human_input']['messaging']['available'] is False
            service.answer_questions(answers=[{'question_id':question['id'],'answer':'no','expected_revision':0}])
            applied=await asyncio.to_thread(browser_action,cfg,client,owner,package,page.target_id,
                {'method':'apply_answers','refs':refs})
            assert len(applied['fields'])==1 and applied['fields'][0]['committed'],applied
            assert submissions==[]
            history=json.loads((tmp_path/'spool/answers'/f"attempt-{owner['attempt_id']}.json").read_text())
            assert any(a['answer']=='No' and a['source']=='human_answer_queue' for a in history['answers'])
    asyncio.run(check())


class SubmissionLedger:
    """In-memory service boundary for the real browser confirmation integration."""
    def __init__(self):
        self.attempt = {'id': 1, 'submit_intent_at': None}
        self.events = []

    def call(self, operation, **params):
        if operation == 'attempt_status':return dict(self.attempt)
        if operation == 'events':return list(self.events)
        if operation == 'browser_observe':return {'quiescent': True}
        if operation == 'heartbeat':return {'control':'running'}
        if operation == 'event':self.events.append({'payload_json':json.dumps(params['payload'])})
        elif operation == 'submission_intent':self.attempt['submit_intent_at'] = 'fixture-intent'
        elif operation == 'finish':self.attempt.update(completed_at='fixture-finished',outcome=params['outcome'],evidence=params['evidence'])
        return {}


@pytest.mark.parametrize('mode', ['same', 'cross'])
def test_embedded_submission_is_captured_once_before_page_closes(tmp_path, mode):
    async def check():
        from job_applier.browser_controls import click_control
        from job_applier.submission import submit
        async with fixture_browser(tmp_path, mode) as (page, package, submissions):
            screen = await complete_submission_fixture(page, package)
            target = {'ref': screen['native']['submit']['ref']}
            ledger = SubmissionLedger()
            async def activate():return await click_control(page, target)
            result = await submit(page, ledger.call, package, {'attempt_id':1},
                {'spool_dir':str(tmp_path),'cdp_url':'fixture'}, page.target_id, activate,
                seconds=1, application_control=target)
            assert result['status'] == 'applied', result
            assert result['source'] == 'employer'
            assert submissions == ['/fake-submit']
            again = await submit(page, ledger.call, package, {'attempt_id':1},
                {'spool_dir':str(tmp_path),'cdp_url':'fixture'}, page.target_id, activate,
                seconds=1, application_control=target)
            assert again['status'] == 'applied' and submissions == ['/fake-submit']
    asyncio.run(check())


async def complete_submission_fixture(page, package):
    """Confirmation tests start with the fixture's required answers committed."""
    screen = await observe(page, package)
    fields = {c['label']: c for c in screen['inventory']}
    for question, answer in [('I acknowledge the Candidate Privacy Statement', 'I acknowledge'),
                             ('Do you have experience leading technology teams?', 'Yes')]:
        result = await form_action(page, {'method': 'select', 'ref': fields[question]['ref'], 'label': answer})
        assert result.get('committed'), result
    return await observe(page, package)


@pytest.mark.parametrize('outcome',['redirect','transient','unknown','wrong_job','replaced'])
def test_embedded_confirmation_scope_and_uncertain_dispatch(tmp_path,outcome):
    async def check():
        from job_applier.browser_controls import click_control
        from job_applier.browser_frames import resolve_control
        from job_applier.submission import submit
        async with fixture_browser(tmp_path,'same' if outcome=='replaced' else 'cross',submit_outcome=outcome) as (page,package,submissions):
            screen=await complete_submission_fixture(page,package);target={'ref':screen['native']['submit']['ref']}
            ledger=SubmissionLedger()
            async def activate():
                result=await click_control(page,target)
                if outcome=='replaced':
                    deadline=time.monotonic()+2
                    while not submissions:
                        assert time.monotonic()<deadline,'Synthetic submit did not dispatch'
                        await asyncio.sleep(.02)
                    await page.evaluate("document.getElementById('application').outerHTML='<iframe title=Advertisement src=\"/form/confirmation?gh_jid=12345\"></iframe>'")
                return result
            result=await submit(page,ledger.call,package,{'attempt_id':1},{'spool_dir':str(tmp_path),'cdp_url':'fixture'},
                page.target_id,activate,seconds=1,application_control=target)
            expected='applied' if outcome in ('redirect','transient') else 'submission_unknown'
            assert result['status']==expected,result
            assert submissions==['/fake-submit']
            again=await submit(page,ledger.call,package,{'attempt_id':1},{'spool_dir':str(tmp_path),'cdp_url':'fixture'},
                page.target_id,activate,seconds=1,confirmation_only=True,application_control=target)
            assert again['status']==expected and submissions==['/fake-submit'],again
    asyncio.run(check())
def test_observed_simplify_stop_settles_in_its_real_document(tmp_path):
    async def check():
        from job_applier.simplify_boundary import SimplifyBoundary
        async with fixture_browser(tmp_path) as (page,package,_):
            await page.evaluate("const host=document.createElement('div');host.className='simplify-jobs-shadow-root';host.attachShadow({mode:'open'}).innerHTML='<p>Filling your application</p><button>Stop autofill</button>';host.shadowRoot.querySelector('button').onclick=()=>host.shadowRoot.innerHTML='<button>Autofill this page</button>';document.body.append(host)")
            boundary=SimplifyBoundary(page,budget_seconds=3)
            before=await boundary.observe()
            assert before['status']=='active' and before['controls']['stop']['enabled']
            result=await boundary.perform('stop')
            assert result['execution']=='clicked' and result['writer_state']=='idle'
            assert (await boundary.observe())['status']=='ready'
    asyncio.run(check())
