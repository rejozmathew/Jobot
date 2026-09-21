"""Synthetic missing-mail recovery; no employer or mailbox interaction."""
import asyncio
import json

import pytest

from job_applier.greenhouse_fast import advance
from job_applier.managed_questions import question_data


def test_missing_email_recovery_does_not_reload_another_ats(monkeypatch):
    from job_applier import application_runtime
    monkeypatch.setattr(application_runtime,'browser_action',lambda *a,**k:pytest.fail('Other ATS was reloaded'))
    class Client:
        def call(self,op,**params):
            if op=='application_context':return {'job':{'url':'https://example.myworkdayjobs.com/job/1'},'attempt':{}}
            assert op=='browser_observe'
            return {'platform':'workday','next_operation':{'operation':'fast_forward','parameters':{'seconds':60}}}
    result=advance({'cdp_url':'unused'},Client(),{'attempt_id':1,'worker_id':'fixture'},
        {'target_id':'owned','recovery':'missing_verification_email'})
    assert result['next_operation']['operation']=='fast_forward'


def test_country_choice_list_is_not_rejected_at_200_options():
    options=[{'value':str(i),'label':'Country '+str(i)} for i in range(249)]
    question=question_data(field='country',question='Country',kind='select',options=options)
    assert question['options']==options


@pytest.mark.parametrize('renewed_verification',[False,True])
@pytest.mark.parametrize('initial_verification',[False,True])
def test_owned_missing_email_recovery_reloads_refills_and_follows_current_submit(tmp_path,monkeypatch,renewed_verification,initial_verification):
    import test_embedded_forms as fixture
    from test_greenhouse_batch import batch_html,batch_profile
    from test_local_sessions import setup,connect,own
    from job_applier.managed_client import LocalClient
    from job_applier import managed_context
    original_platform=managed_context.platform_for_url
    # The isolated fixture uses localhost, never an actual employer hostname.
    monkeypatch.setattr(managed_context,'platform_for_url',
        lambda url:'greenhouse' if str(url).startswith('http://localhost:') else original_platform(url))
    html=batch_html()
    if renewed_verification:
        html=html.replace("<p>Thank you for applying</p>",
            '<label for="verification">Security code</label><input id="verification" name="security_code" required autocomplete="one-time-code">')
    monkeypatch.setattr(fixture,'FORM_HTML',html)
    async def run():
        async with fixture.fixture_browser(tmp_path,mode='top') as (page,fixture_package,submissions):
            service,asset,_,ws,cfg=setup(tmp_path/'ledger')
            ws[0].update(cdp_url=page.fixture_endpoint,mode='headless');service.configure_workspaces(ws)
            profile=batch_profile();profile['identity']['email']='candidate@example.test'
            service.identity(identity_id='candidate',person_key='same-person',email='candidate@example.test',profile=profile)
            service.configure({'browser_mode':'headless'},expected_version=service.settings_view()['version'])
            job=service.intake(url=fixture_package['job']['url']);service.eligibility(job['id'],'ready',reason='Synthetic')
            session=connect(service,service.reserve_session(request_id='missing-mail',job_id=job['id'],identity_id='candidate',
                driver_id='fixture',workspace_ids=['workspace-0'],concurrency_limit=1,resume_asset_id=asset['id']),page.target_id)
            owner=own(service,session)
            cfg.update(cdp_url=page.fixture_endpoint,browser_mode='headless',spool_dir=str(tmp_path/'spool'))
            client=LocalClient(cfg,service=service)
            original_call=client.call
            def call(op,**params):
                if op=='application_context':
                    package=original_call(op,**params)
                    package['attempt']['settings_json']=dict(json.loads(package['attempt']['settings_json']),submission_mode='submit')
                    return package
                if op=='submission_intent':params['fixture']=True
                return original_call(op,**params)
            monkeypatch.setattr(client,'call',call)
            if initial_verification:
                await page.evaluate("document.body.innerHTML='<label>Email security code<input name=security_code required autocomplete=one-time-code></label>'")
            before=await page.evaluate('performance.timeOrigin')
            result=await asyncio.to_thread(advance,cfg,client,owner,
                {'target_id':page.target_id,'seconds':30,'recovery':'missing_verification_email'})
            assert result.get('email_recovery_result',{}).get('document_replaced',False) is initial_verification,result
            assert (await page.evaluate('performance.timeOrigin')!=before) is initial_verification
            assert submissions==['/fake-submit']
            if renewed_verification:
                assert result['status']=='application_incomplete',result
                assert result['email_recovery']['operation']=='greenhouse_advance'
                assert 'renewed verification' in result['instruction']
                assert not service.attempt_report(owner['attempt_id'])['attempt']['completed_at']
            else:
                assert result['status']=='applied',result
                assert result['completed_count']==15
            events=service.attempt_report(owner['attempt_id'])['timeline']
            assert any(e['event_type']=='recovery' and e['payload'].get('operation')=='reload' for e in events) is initial_verification
    asyncio.run(run())
