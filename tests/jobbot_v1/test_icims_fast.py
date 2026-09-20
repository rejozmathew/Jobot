"""Native/portable dispatch through the actual host, service and synthetic browser."""
import asyncio
import json

import pytest

from test_form_audit import fixture_html,icims_browser


@pytest.mark.parametrize('submission_mode',['review','submit'])
def test_real_dispatch_password_profile_screening_and_final_service(tmp_path,monkeypatch,submission_mode,capsys):
    import test_embedded_forms as fixture
    from test_local_sessions import setup,connect
    from job_applier.workspace_host import WorkspaceHost
    from job_applier.hermes_plugin import PluginController,SCHEMA
    from job_applier import workspace_host,application_runtime
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page,package,_):
            service,asset,_,ws,cfg=setup(tmp_path/'ledger')
            ws[0].update(cdp_url=page.fixture_endpoint,mode='headless');service.configure_workspaces(ws)
            service.configure({'mode':'pilot' if submission_mode=='submit' else 'development','submission_mode':submission_mode,'browser_mode':'headless'},expected_version=service.settings_view()['version'])
            job=service.intake(url=package['job']['url']);service.eligibility(job['id'],'ready',reason='Synthetic')
            session=connect(service,service.reserve_session(request_id='icims-dispatch',job_id=job['id'],identity_id='candidate',driver_id='fixture',workspace_ids=['workspace-0'],concurrency_limit=1,resume_asset_id=asset['id']),page.target_id)
            credentials=tmp_path/'fake-credentials.json';credentials.write_text(json.dumps({'accounts':{'default':{'email':'candidate@example.test','password':'SYNTHETIC-secret-42!'}}}))
            cfg.update(cdp_url=page.fixture_endpoint,browser_mode='headless',spool_dir=str(tmp_path/'spool'),credential_profile_path=str(credentials))
            host=object.__new__(WorkspaceHost);host.config=cfg;host.service=service;host.workspace=ws[0];host.workspace_id='workspace-0';host.host_id='host-workspace-0'
            routes=[]
            def transport(config,current,operation,parameters,driver):
                routes.append(operation)
                return host._dispatch({'instance_id':config['instance_id'],'session_id':current['id'],
                    'driver_id':driver,'operation':operation,'parameters':parameters})
            monkeypatch.setattr(workspace_host,'call_host',transport)
            plugin=PluginController('synthetic');monkeypatch.setattr(plugin,'_config',lambda:cfg)
            plugin.local_sessions['fixture']=session['id']
            assert 'icims_advance' in SCHEMA['parameters']['properties']['operation']['enum']
            # Actual read-only public method, not a classifier-only test.
            compact=json.loads(await asyncio.to_thread(plugin.handle,{'operation':'browser','parameters':{'method':'audit'}},session_id='fixture'))
            assert compact['audit_version']==1 and compact['summary']['missing_credential_controls']==2,compact
            result=json.loads(await asyncio.to_thread(plugin.handle,{'operation':'icims_advance','parameters':{'seconds':30}},session_id='fixture'))
            assert result.get('status')=='questions_required',result
            assert len(result['questions'])==2
            assert result['actions']['credentials']==1 and result['actions']['autofill']==0
            assert result['actions']['repair_fields']==0 and result['actions']['stage_advance']==1
            assert not service.attempt(session['attempt_id'])['submit_intent_at']
            counters=await page.evaluate('fixture.counters')
            assert counters['profileSubmits']==1 and counters['autofillClicks']==0 and counters['finalSubmits']==0
            plans=[{'ref':q['ref'],'question_key':q['question_key'],'answer':'No','basis':'explicit_synthetic_answer'} for q in result['questions']]
            # CLI parser -> session_call -> host -> real runner, old-plugin fallback.
            monkeypatch.setattr(application_runtime,'resolve_config',lambda *a:cfg)
            code=await asyncio.to_thread(application_runtime.main,['call',session['id'],'icims_advance','--driver-id','fixture','--parameters',json.dumps({'seconds':30,'answers':plans})])
            output=json.loads(capsys.readouterr().out.strip().splitlines()[-1])
            assert code==0 and output['status']==('applied' if submission_mode=='submit' else 'ready_for_review'),output
            assert output['actions']['repair_fields']==2
            assert await page.evaluate('fixture.counters.finalSubmits')==(1 if submission_mode=='submit' else 0)
            assert 'SYNTHETIC-secret-42!' not in json.dumps([compact,result,output])
            assert routes==['browser','icims_advance','icims_advance']
            evidence={'mode':submission_mode,'routes':routes,'profile':result,'completion':output,'counters':await page.evaluate('fixture.counters')}
            folder=__import__('pathlib').Path('artifacts/jobbot-v1-private');folder.mkdir(parents=True,exist_ok=True)
            (folder/('icims-trace-'+submission_mode+'.json')).write_text(json.dumps(evidence,indent=2))
    asyncio.run(run())


def test_stop_during_private_fill_prevents_stage_click_and_reaudit(tmp_path,monkeypatch):
    import test_embedded_forms as fixture
    from job_applier.icims_fast import IcimsRunner
    from job_applier import managed_credentials
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page,package,_):
            state={'control':'running'};calls=[]
            def call(op,**params):
                calls.append(op)
                if op=='heartbeat':return state
                if op=='browser_observe':return {'native_takeover_authorized':True,'observation':{}}
                return {}
            async def fill(*args):state['control']='stop_requested';return {'values_committed':True}
            monkeypatch.setattr(managed_credentials,'fill_page_credentials',fill)
            runner=IcimsRunner(page,call,package,{'attempt_id':1,'worker_id':'test','fence':1},{'cdp_url':page.fixture_endpoint},page.target_id)
            # Test gate supplies the actual document identities but no production mutation.
            original_gate=runner.gate
            async def gate():
                result=await original_gate();runner.documents=None;return result
            runner.gate=gate
            result=await runner.run(10)
            assert result['reason']=='stop_requested' and result['actions']['audits']==1,result
            assert await page.evaluate('fixture.counters.profileSubmits')==0
            assert 'finish' not in calls
    asyncio.run(run())


def test_resume_repair_uses_selected_asset_and_not_cover_letter(tmp_path,monkeypatch):
    import hashlib
    import test_embedded_forms as fixture
    from job_applier.icims_fast import IcimsRunner
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page,package,_):
            await page.evaluate("""fixture.addVariant('upload-error');
              document.querySelector('#profile-form').insertAdjacentHTML('beforeend','<section><h3>Cover Letter</h3><input type=file id=cover></section>');
              document.querySelector('#resume').addEventListener('change',()=>document.querySelector('#server-error').remove());""")
            asset=tmp_path/'selected.pdf';asset.write_bytes(b'synthetic asset')
            package['documents']={'assets':[{'id':'selected','kind':'resume','storage_ref':asset.as_uri(),'sha256':hashlib.sha256(asset.read_bytes()).hexdigest()}]}
            calls=[]
            def call(op,**params):
                calls.append(op)
                if op=='heartbeat':return {'control':'running'}
                if op=='browser_observe':return {'native_takeover_authorized':True,'observation':{}}
                return {}
            runner=IcimsRunner(page,call,package,{'attempt_id':1,'worker_id':'test','fence':1},{'cdp_url':page.fixture_endpoint},page.target_id)
            original_gate=runner.gate
            async def gate():
                result=await original_gate();runner.documents=None;return result
            runner.gate=gate
            await runner.read();assert runner.audit['invalid_blockers'][0]['type']=='file'
            assert await runner.repair([])
            assert not runner.failures
            assert await page.evaluate("document.querySelector('#resume').files[0].name")=='selected.pdf'
            assert await page.evaluate("document.querySelector('#cover').files.length")==0
            await runner.read();assert not runner.audit['invalid_blockers']
            assert 'report_upload' in calls
    asyncio.run(run())


def test_expired_helper_slice_returns_continuation_without_finish(tmp_path,monkeypatch):
    import test_embedded_forms as fixture
    from job_applier.icims_fast import IcimsRunner
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page,package,_):
            calls=[]
            def call(op,**params):calls.append(op);return {'control':'running'}
            runner=IcimsRunner(page,call,package,{'attempt_id':1,'worker_id':'test','fence':1},{},page.target_id)
            result=await runner.run(.000001)
            assert result['status']=='continue' and result['reason']=='call_slice_complete'
            assert 'finish' not in calls
            assert await page.evaluate('fixture.counters.profileSubmits')==0
    asyncio.run(run())


def test_service_writer_gate_distinguishes_spa_and_destroyed_document(tmp_path,monkeypatch):
    import test_embedded_forms as fixture
    from test_local_sessions import setup,connect,own
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page,package,_):
            service,asset,_,ws,cfg=setup(tmp_path/'ledger')
            ws[0].update(cdp_url=page.fixture_endpoint,mode='headless');service.configure_workspaces(ws)
            service.configure({'browser_mode':'headless'},expected_version=service.settings_view()['version'])
            job=service.intake(url=package['job']['url']);service.eligibility(job['id'],'ready',reason='Synthetic')
            session=connect(service,service.reserve_session(request_id='writer-docs',job_id=job['id'],identity_id='candidate',driver_id='fixture',workspace_ids=['workspace-0'],concurrency_limit=1,resume_asset_id=asset['id']),page.target_id)
            owner=own(service,session)
            async def gate():return await asyncio.to_thread(service.browser_observe,**owner,target_id=page.target_id,cdp_url=page.fixture_endpoint)
            await page.evaluate("fixture.setSimplify('active')")
            assert not (await gate())['native_takeover_authorized']
            await page.evaluate('fixture.screening()')
            assert not (await gate())['native_takeover_authorized']
            await page.reload()
            await page.evaluate("document.querySelector('.simplify-jobs-shadow-root').remove()")
            result=await gate()
            assert result['native_takeover_authorized'],result
            with service.tx() as db:
                rows=[json.loads(r[0]) for r in db.execute("SELECT payload_json FROM managed_events WHERE attempt_id=?",(session['attempt_id'],))]
            assert any(r.get('prior_document_cancelled') is True for r in rows)
    asyncio.run(run())
