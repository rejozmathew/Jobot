"""Generic registration routes and consistent recovery guidance."""
import pytest

from job_applier.managed_identity import application_match
from job_applier.browser_controls import next_operation


def test_requisition_is_preserved_from_posting_path_to_registration_query():
    posting='https://careers.example.com/Careers/JobDetail/12654'
    assert application_match(posting,'https://careers.example.com/Careers/Register?jobId=12654')['status']=='same_job'
    assert application_match(posting,'https://careers.example.com/Careers/Register?jobId=99999')['status']=='different_job'
    assert application_match(posting,'https://other.example.com/Careers/Register?jobId=12654')['status']=='different_job'
    assert application_match(posting,'https://careers.example.com/Careers/Register')['status']=='identity_unresolved'


@pytest.mark.parametrize('platform', ['unknown','workday','greenhouse','linkedin'])
def test_next_action_cannot_recommend_writes_when_identity_or_writer_disallows_them(platform):
    observed={'status':'ready','controls':{'autofill':{'enabled':True,'ref':'fill'}}}
    decision=next_operation(platform, observed, identity={'status':'identity_unresolved'}, quiescent=True)
    assert decision['operation']=='browser' and decision['parameters']['method']=='snapshot'
    decision=next_operation(platform, observed, identity={'status':'same_job'}, quiescent=False)
    assert decision['operation']=='browser_observe'
    decision=next_operation('unknown', observed, identity={'status':'same_job'}, quiescent=True)
    assert decision['parameters']=={'method':'simplify','action':'autofill','ref':'fill'}


def test_residual_inventory_exposes_missing_invalid_and_exact_actions():
    from job_applier.browser_controls import inventory
    fields=[{'ref':'address','tag':'INPUT','type':'text','label':'Address *','required':True,'present':False,'enabled':True},
            {'ref':'zip','tag':'INPUT','type':'text','label':'Postal Code *','required':True,'present':True,'enabled':True,'validation':{'rejected':True}},
            {'ref':'privacy','tag':'INPUT','type':'checkbox','label':'Privacy *','required':True,'present':True,'checked':False,'enabled':True},
            {'ref':'optional','tag':'INPUT','type':'text','label':'Home phone','present':False,'enabled':True}]
    result=inventory({'inventory':fields,'status':'complete'}, {'attempt':{'profile_json':{'identity':{
        'address':{'street':'123 Example St','zip':'60000'},'password':'never-project'}}}})
    assert [field['ref'] for field in result['remaining_required']]==['address','zip','privacy']
    assert result['remaining_required'][2]['action']['method']=='check'
    assert result['answer_context']['identity']['address']['zip']=='60000'
    assert 'never-project' not in str(result)
    assert result['supported_operations']['upload']=={'method':'upload','ref':'<observed file ref>','asset_id':'<selected asset id>'}


def test_shared_grouped_repairs_verify_values_and_stop_on_document_change(monkeypatch):
    import asyncio
    from job_applier import browser_controls as controls
    calls=[]
    async def action(page,params,**kwargs):
        calls.append(params['ref'])
        await kwargs['checkpoint']()
        return {'committed':params['ref']!='zip','reason':'rejected' if params['ref']=='zip' else None}
    monkeypatch.setattr(controls,'form_action',action)
    async def checkpoint():pass
    plans=[{'method':'fill','ref':'address','value':'123 Example St'},
           {'method':'fill','ref':'zip','value':'60000'},
           {'method':'check','ref':'privacy','value':True}]
    result=asyncio.run(controls.repair_fields(object(),plans,checkpoint=checkpoint))
    assert calls==['address','zip','privacy']
    assert [f['committed'] for f in result['fields']]==[True,False,True]
    calls.clear()
    async def changed():raise ValueError('application_document_changed')
    result=asyncio.run(controls.repair_fields(object(),plans,checkpoint=changed))
    assert not calls and result['reason']=='application_document_changed'
    assert len(result['remaining'])==3


def test_owned_transition_carries_no_id_intermediate_and_rejects_conflicting_job(tmp_path):
    from test_apply_target_handoff import connected,EXTERNAL
    from job_applier.managed_shared import ProtocolError
    s,session,owner,_=connected(tmp_path)
    s.handoff_target(**owner,current_target_id='linkedin',new_target_id='adp',url=EXTERNAL,expected_url=EXTERNAL,evidence='Observed Apply')
    intermediate='https://myjobs.adp.com/acme/cx/register'
    s.handoff_target(**owner,current_target_id='adp',new_target_id='adp',url=intermediate,source_url=EXTERNAL,evidence='Observed Continue')
    with pytest.raises(ProtocolError,match='target_job_mismatch'):
        s.handoff_target(**owner,current_target_id='adp',new_target_id='adp',url=EXTERNAL.replace('424242','999'),source_url=intermediate,evidence='Observed navigation')


def test_live_shared_form_batch_handles_asterisk_fields_and_continues(tmp_path):
    import asyncio
    from test_embedded_forms import fixture_browser
    from job_applier.browser_controls import FORM,inventory,repair_fields,click_control
    async def run():
        async with fixture_browser(tmp_path,'top') as (page,package,_):
            await page.evaluate('''document.body.innerHTML=`<form>
              <div><label>Address <span>*</span></label><input id="address"></div>
              <label for="postal">Postal Code *</label><input id="postal" required pattern="[0-9]{5}">
              <label><input id="privacy" type="checkbox" required>Privacy *</label>
              <label>Optional home phone<input id="optional"></label>
              <button type="button" id="next">Continue</button></form>`;
              document.querySelector('#next').onclick=()=>{if(document.querySelector('form').reportValidity())document.body.dataset.advanced='yes'};''')
            observed=await page.evaluate_function(FORM,{'method':'observe'})
            screen=inventory(observed,package)
            assert len(screen['remaining_required'])==3
            refs={field['label'].strip():field['ref'] for field in screen['remaining_required']}
            plans=[{'method':'fill','ref':refs['Address *'],'value':'123 Example St'},
                   {'method':'fill','ref':refs['Postal Code *'],'value':'60000'},
                   {'method':'check','ref':refs['Privacy *'],'value':True}]
            result=await repair_fields(page,plans)
            assert all(f['committed'] for f in result['fields'])
            after=await page.evaluate_function(FORM,{'method':'observe'})
            assert not inventory(after,package)['remaining_required']
            continued=await click_control(page,{'selector':'#next'})
            assert continued['clicked'] and await page.evaluate('document.body.dataset.advanced')=='yes'
    asyncio.run(run())


@pytest.mark.parametrize('recognized', [True,False])
def test_observation_and_execution_share_registration_identity_and_recovery_inventory(tmp_path,monkeypatch,recognized):
    from unittest.mock import AsyncMock
    from test_apply_target_handoff import connected
    from job_applier import browser_controls,application_answers,managed_credentials
    from job_applier.application_runtime import browser_action
    from job_applier.cdp_client import CDPBrowser
    from job_applier.simplify_boundary import SimplifyBoundary
    s,session,owner,workspace=connected(tmp_path)
    posting='https://careers.example.com/Careers/JobDetail/12654'
    s.handoff_target(**owner,current_target_id='linkedin',new_target_id='form',url=posting,expected_url=posting,evidence='Observed Apply')
    current='https://careers.example.com/Careers/Register'+('?jobId=12654' if recognized else '')
    class Page:
        async def evaluate(self,script):
            return current if script=='location.href' else 'Registration'
        async def evaluate_function(self,script,args):return {}
    page=Page()
    browser=type('Browser',(),{'get_current_page':AsyncMock(return_value=page),'close':AsyncMock(),'observed_mode':'headed'})()
    monkeypatch.setattr(CDPBrowser,'connect',AsyncMock(return_value=browser))
    observation={'status':'ready','url':current,'panel':True,'fingerprint':'stable','page_signature':'registration',
        'controls':{'autofill':{'enabled':True,'ref':'autofill'}},'activity':{},
        'inventory':[{'ref':'address','tag':'INPUT','type':'text','label':'Address *','required':True,'enabled':True,'present':False}],
        'native':{'continue':{'ref':'next','enabled':True}}}
    monkeypatch.setattr(browser_controls,'observe_writers',AsyncMock(return_value=observation))
    monkeypatch.setattr(browser_controls,'observe',AsyncMock(return_value=observation))
    monkeypatch.setattr(browser_controls,'simplify_document',AsyncMock(return_value=(page,observation,None)))
    monkeypatch.setattr(SimplifyBoundary,'perform',AsyncMock(return_value={'execution':'clicked','native_takeover_authorized':True}))
    monkeypatch.setattr(application_answers,'capture_answers',AsyncMock(return_value={}))
    monkeypatch.setattr(managed_credentials,'capture_private_screenshot',AsyncMock())
    class Client:
        def call(self,op,**params):return getattr(s,op)(**params)
    gate=s.browser_observe(**owner,target_id='form',cdp_url=workspace['cdp_url'])
    assert gate['url']==current.split('?')[0]
    assert gate['native_takeover_authorized'] is recognized
    package=s.application_context(owner['attempt_id'])
    cfg={'cdp_url':workspace['cdp_url'],'spool_dir':str(tmp_path)}
    result=browser_action(cfg,Client(),owner,package,'form',gate['next_operation']['parameters'])
    if recognized:assert result['execution']=='clicked'
    else:
        assert result['recovery_only'] and result['remaining_required'][0]['ref']=='address'
        assert result['native'][0]['ref']=='address'
