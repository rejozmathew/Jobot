"""Real shared reader on original, synthetic iCIMS-shaped DOM; no employer data."""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from job_applier import browser_controls

FIXTURES=Path(__file__).parent/'fixtures'/'icims'


@asynccontextmanager
async def icims_browser(tmp_path,mode='top'):
    import test_embedded_forms as fixture
    async with fixture.fixture_browser(tmp_path,mode) as (page,package,submissions):
        if mode=='top':
            # Own the exact plain route, without the shared server's GH query.
            await page.evaluate("history.replaceState(null,'',location.pathname)")
            package['job']['url']=await page.evaluate('location.href')
        yield page,package,submissions


def fixture_html():
    html=(FIXTURES/'icims-flow.html').read_text()
    html=html.replace('<script defer src="fixture.js"></script>','').replace(
        '<link rel="stylesheet" href="fixture.css">','<style>'+(FIXTURES/'fixture.css').read_text()+'</style>')
    script=(FIXTURES/'fixture.js').read_text()+";document.addEventListener('test-fixture-read',e=>{document.documentElement.dataset.fixtureResult=JSON.stringify(eval(e.detail))});"
    return html.replace('</body>','<script>'+script+'</script></body>')


async def fixture_read(document, expression):
    return await document.evaluate_function("(expression)=>{document.dispatchEvent(new CustomEvent('test-fixture-read',{detail:expression}));return JSON.parse(document.documentElement.dataset.fixtureResult)}",expression)



def test_contract_password_tasks_are_private_and_classification_is_shared():
    from job_applier.form_audit import audit
    fields=[{'ref':'pw','tag':'INPUT','type':'password','required':True,'private':True,'present':False,'enabled':True},
        {'ref':'optional','tag':'INPUT','type':'email','present':True,'enabled':True,'validation':{'rejected':True}},
        {'ref':'blank','tag':'INPUT','type':'text','present':False,'enabled':True}]
    result=audit({'inventory':fields})
    assert result['audit_version']==1 and not result['required_missing']
    assert result['credential_tasks'][0]['fields'][0]['ref']=='pw'
    assert result['invalid_blockers'][0]['ref']=='optional'
    assert result['optional_ignored']['count']==1
    work=browser_controls.remaining_submission_work({'inventory':fields})
    assert [f['ref'] for f in work['required_fields']]==['pw']


@pytest.mark.parametrize('mode',['top','same','cross'])
def test_cotiviti_profile_audit_and_readonly_privacy(tmp_path,monkeypatch,mode):
    import test_embedded_forms as fixture
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        async with icims_browser(tmp_path,mode) as (page,package,_):
            from job_applier.form_audit import audit
            from job_applier.browser_frames import router_for
            observed=await browser_controls.observe(page,package)
            document=page if mode=='top' else next(iter((await router_for(page,package)).frames.values()))
            before=await fixture_read(document,'JSON.stringify(fixture.counters)')
            result=audit(observed)
            assert not result['required_missing'],result
            assert result['summary']['missing_credential_controls']==2
            assert len(result['credential_tasks'])==1
            assert result['optional_ignored']['count']==13
            assert result['summary']['accepted_attachment_widgets']==1
            assert result['advancement']['kind']=='stage_advance'
            assert result['stage']['name']=='candidate_profile'
            assert result['simplify_review']['count']==15
            assert result['simplify_review']['matched_optional']>0
            assert result['simplify_review']['already_filled']>=1
            assert not result['invalid_blockers']
            assert await fixture_read(document,'JSON.stringify(fixture.counters)')==before
            assert 'candidate@example.invalid' not in json.dumps(result)
            assert 'synthetic_resume.pdf' not in json.dumps(result)
    asyncio.run(run())


@pytest.mark.parametrize('variant',['optional-invalid','checkboxes','two-forms','shadow','closed-shadow','hidden-required','upload-error'])
def test_semantic_variants(tmp_path,monkeypatch,variant):
    import test_embedded_forms as fixture
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page,package,_):
            from job_applier.form_audit import audit
            await page.evaluate_function('(name)=>fixture.addVariant(name)',variant)
            observed=await browser_controls.observe(page,package);result=audit(observed)
            if variant=='optional-invalid':assert result['invalid_blockers'][0]['type']=='email'
            elif variant=='checkboxes':assert len(result['required_missing'])==1
            elif variant=='two-forms':assert len(result['required_missing'])==1
            elif variant=='shadow':
                f=next(f for f in result['required_missing'] if 'shadow field' in f['label'])
                assert (await browser_controls.form_action(page,{'method':'fill','ref':f['ref'],'value':'approved'}))['committed']
                from job_applier.managed_credentials import MASK_CREDENTIALS,UNMASK_CREDENTIALS
                await page.evaluate(MASK_CREDENTIALS)
                assert await page.evaluate("document.querySelector('#employer-widget').shadowRoot.querySelector('[type=password]').style.visibility")=='hidden'
                await page.evaluate(UNMASK_CREDENTIALS)
            elif variant in ('closed-shadow','hidden-required'):assert result['unknown_controls'] or result['coverage']['unresolved_documents']
            elif variant=='upload-error':assert any(f['type']=='file' for f in result['invalid_blockers'])
    asyncio.run(run())


def test_unknown_fragment_does_not_override_terminal_but_actual_writer_does():
    from job_applier.browser_controls import _merge_writers
    class Frame:
        frame_id='child';nonce='doc'
        def wrap(self,ref):return 'frame:'+ref
    root={'status':'needs_review','panel':True,'writer_safe':True,'terminal_evidence':True}
    child={'status':'unknown','panel':True,'writer_safe':False,'writer_participant':False}
    assert _merge_writers(root,[(Frame(),child)],[])['status']=='needs_review'
    child.update(writer_participant=True,writer_pending=True)
    assert not _merge_writers(root,[(Frame(),child)],[])['writer_safe']


def test_writer_telemetry_only_retains_typed_document_identity_and_booleans():
    from job_applier.managed_redaction import safe_payload
    value=safe_payload({'operation':'writer_documents','writer_documents':[
        {'document_id':'12345678-1234-1234-1234-123456789abc','pending':True,'value':'PRIVATE-SENTINEL'},
        {'document_id':'PRIVATE-SENTINEL','pending':True}], 'prior_document_cancelled':True})
    assert value['writer_documents']==[{'document_id':'12345678-1234-1234-1234-123456789abc','pending':True,'participant':False,'settled':False}]
    assert value['prior_document_cancelled'] is True and 'PRIVATE-SENTINEL' not in json.dumps(value)


def test_actual_dispatch_contract_is_registered():
    from job_applier.hermes_plugin import OPERATIONS
    assert 'icims_advance' in OPERATIONS
    for status in ('ready','needs_review','unknown'):
        assert browser_controls.next_operation('icims',{'status':status})['operation']=='icims_advance'


def test_native_semantics_conditional_private_and_stale_refs(tmp_path,monkeypatch):
    import test_embedded_forms as fixture
    from job_applier.form_audit import audit
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page,package,_):
            await page.evaluate("""document.querySelector('#profile-form').insertAdjacentHTML('beforeend',`
              <label>Boolean required<input id="boolean-required" required="false"></label>
              <fieldset disabled><label>Inactive replica<input required></label></fieldset>
              <label>Valid zero<select required><option value="0" selected>Zero</option></select></label>
              <label>Uncommitted choice<input role="combobox" aria-required="true" value="Search only"></label>
              <div style="height:25px;overflow:auto"><div style="height:2000px"></div><label>Offscreen<input required></label></div>
              <label>Verification code<input autocomplete="one-time-code" value="PRIVATE-OTP-SENTINEL"></label>`);
              document.querySelector('#resume').required=true;
              document.querySelector('#password').value='PRIVATE-PASSWORD-SENTINEL';
              document.querySelector('#confirmation').value='PRIVATE-PASSWORD-SENTINEL';""")
            before=await fixture_read(page,'JSON.stringify(fixture.counters)')
            observed=await browser_controls.observe(page,package);result=audit(observed)
            labels=[f['label'] for f in result['required_missing']]
            assert any('Boolean required' in l for l in labels)
            assert any('Offscreen' in l for l in labels)
            assert any('Uncommitted' in l for l in labels)
            assert not any('Inactive' in l or 'Valid zero' in l or 'resume' in l for l in labels)
            assert 'PRIVATE-' not in json.dumps(result)
            assert await fixture_read(page,'JSON.stringify(fixture.counters)')==before
            ref=next(f['ref'] for f in observed['inventory'] if f.get('type')=='password')
            await page.evaluate('fixture.replacePassword()')
            stale=await page.evaluate_function(browser_controls.FORM,{'method':'inspect','ref':ref})
            assert stale.get('reason'),stale
            await page.evaluate('fixture.addRequired()')
            fresh=audit(await browser_controls.observe(page,package))
            assert any('Newly revealed' in f['label'] for f in fresh['required_missing'])
            await page.evaluate("document.querySelector('#server-error').textContent='The application is invalid: please contact support.'")
            summary=audit(await browser_controls.observe(page,package))['validation_summary']
            assert any(not e['associated'] and e['state']=='current' for e in summary)
            await page.evaluate("""document.querySelector('#application').insertAdjacentHTML('beforeend',
                '<form id=repeat><label for=again>Email again</label><input id=again type=email value=old@example.invalid></form><div id=repeat-error role=alert><a href=#again>Email again: invalid.</a></div>')""")
            await browser_controls.observe(page,package)
            await page.evaluate("document.querySelector('#again').value='new@example.invalid'")
            repaired=audit(await browser_controls.observe(page,package))
            assert not any(f['label']=='Email again' for f in repaired['invalid_blockers'])
            await page.evaluate("document.querySelector('#repeat-error').innerHTML='<a href=#again>Email again: invalid.</a>'")
            rejected=audit(await browser_controls.observe(page,package))
            assert any(f['label']=='Email again' for f in rejected['invalid_blockers'])
    asyncio.run(run())


def test_writer_receipts_survive_spa_but_not_document_replacement(tmp_path,monkeypatch):
    import test_embedded_forms as fixture
    from job_applier.simplify_boundary import OBSERVE, SimplifyBoundary
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page,package,_):
            initial=await browser_controls.observe_writers(page,package)
            assert initial['settled_evidence']
            await page.evaluate("fixture.setSimplify('active')")
            active=await browser_controls.observe_writers(page,package)
            assert active['writer_pending'] and not active['writer_safe']
            await page.evaluate("fixture.screening();history.replaceState(null,'',location.pathname+'?stage=screening')")
            unknown=await browser_controls.observe_writers(page,package)
            assert unknown['writer_pending'] and not unknown['writer_safe']
            assert unknown['writer_document_id']==active['writer_document_id']
            boundary=await SimplifyBoundary(page,budget_seconds=.2,poll_seconds=.02).perform('autofill')
            assert not boundary.get('native_takeover_authorized')
            assert boundary.get('audit') and boundary.get('next_operation')
            await page.evaluate("fixture.setSimplify('complete')")
            settled=await browser_controls.observe_writers(page,package)
            assert settled['writer_safe'] and settled['settled_evidence']
            assert await fixture_read(page,'fixture.counters.autofillClicks')==0
            await page.reload()
            replaced=await page.evaluate(OBSERVE)
            assert replaced['writer_document_id']!=active['writer_document_id']
    asyncio.run(run())


def test_large_form_reader_timings_and_single_collection(tmp_path,monkeypatch):
    """Measured evidence, not a machine-speed execution gate."""
    import os,statistics,subprocess,time
    import test_embedded_forms as fixture
    from job_applier.form_audit import audit
    baseline_path=os.environ.get('JOBBOT_AUDIT_BASELINE_PATH')
    baseline=Path(baseline_path).read_text(encoding='utf-8') if baseline_path else subprocess.check_output(
        ['git','show','8c56965673aafa7d7a139f8e6da6f4ca1ffba67e:job_applier/browser_helpers/form_controls.js'],text=True,encoding='utf-8')
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        measurements=[]
        async with icims_browser(tmp_path) as (page,package,_):
            for count in (100,500,1000):
                await page.evaluate_function("n=>{document.querySelector('#application').innerHTML='<form>'+Array.from({length:n},(_,i)=>'<label>Repeated field<input name=field'+i+' value=filled></label>').join('')+'</form>'}",count)
                entry={'fields':count,'runs':3}
                for name,source in [('before',baseline),('after',browser_controls.FORM)]:
                    times=[];queries=[];wire=[];projection=[]
                    wrapped="""args=>{let queries=0;const prototypes=[Document.prototype,Element.prototype,ShadowRoot.prototype];const originals=prototypes.map(p=>p.querySelectorAll);
                    prototypes.forEach((p,i)=>p.querySelectorAll=function(...a){queries++;return originals[i].apply(this,a)});
                    const start=performance.now();try {const result=("""+source+""")(args);return {result,dom_ms:performance.now()-start,queries};}
                    finally {prototypes.forEach((p,i)=>p.querySelectorAll=originals[i]);}}"""
                    for _ in range(3):
                        start=time.perf_counter();value=await page.evaluate_function(wrapped,{'method':'observe'});wire.append((time.perf_counter()-start)*1000)
                        times.append(value['dom_ms']);queries.append(value['queries'])
                        start=time.perf_counter();report=audit(value['result']);projection.append((time.perf_counter()-start)*1000)
                        assert report['summary']['observed_data_controls']==count
                        if name=='after':assert value['result']['audit_metrics']['root_queries']==1
                    entry[name]={'dom_ms_median':statistics.median(times),'roundtrip_ms_median':statistics.median(wire),'projection_ms_median':statistics.median(projection),'all_selector_queries':queries}
                assert max(entry['after']['all_selector_queries'])<min(entry['before']['all_selector_queries'])
                measurements.append(entry)
        folder=Path('artifacts/jobbot-v1-private');folder.mkdir(parents=True,exist_ok=True)
        (folder/'icims-audit-timings.json').write_text(json.dumps(measurements,indent=2))
    asyncio.run(run())
