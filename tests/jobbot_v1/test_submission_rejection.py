"""Retain truthful dispatch evidence and continue forms with validation feedback."""
import asyncio
from datetime import datetime,timezone,timedelta
import json

import pytest

from job_applier.managed import ProtocolError
from job_applier.managed_shared import submission_pending
from test_local_sessions import setup,reserve,connect,own


def event(operation,status,**kwargs):
    return {'payload_json':json.dumps({'operation':operation,'status':status,**kwargs}),
            'observed_at':'2026-09-09T12:00:02+00:00','stale':0}


def dispatch():
    return event('submission_click','possibly_executed',dispatch_id='dispatch-1',
                 document_id='document-1',frame_id='root',source='JobBot')


def rejected(**changes):
    payload={'dispatch_id':'dispatch-1','document_id':'document-1','frame_id':'root','source':'employer',
             'reason_code':'invalid_security_code','resolution':'fresh_employer_rejection'}
    payload.update(changes)
    return event('submission_resolution','rejected',**payload)


def test_fresh_rejection_resolves_only_the_corresponding_dispatch():
    attempt={'submit_intent_at':'2026-09-09T12:00:00+00:00'}
    assert not submission_pending(attempt,[dispatch(),rejected()])
    assert submission_pending(attempt,[dispatch(),rejected(),event('submission_click','possibly_executed',dispatch_id='dispatch-2')])


@pytest.mark.parametrize('changes',[{'dispatch_id':'other'},{'document_id':'other'},{'frame_id':'other'},
                                   {'source':'operator'},{'resolution':'failed'}])
def test_wrong_dispatch_document_frame_or_source_does_not_unlock_retry(changes):
    assert submission_pending({'submit_intent_at':'intent'},[dispatch(),rejected(**changes)])


def test_stale_rejection_and_absent_confirmation_remain_pending():
    stale=rejected();stale['stale']=1
    assert submission_pending({'submit_intent_at':'intent'},[dispatch(),stale])
    assert submission_pending({'submit_intent_at':'intent'},[dispatch(),event('reconciliation','failed')])
    assert submission_pending({'submit_intent_at':'intent'},[dispatch()])


def test_contradictory_success_evidence_prevents_rejection_retry():
    assert submission_pending({'submit_intent_at':'intent'},[
        dispatch(),event('submission_confirmed','applied',source='employer'),rejected()])


def service_dispatch(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path);session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    s.submission_intent(**owner,evidence='Synthetic final control',fixture=True)
    s.action_start(**owner,action_id='dispatch-1',tool_name='browser.submit')
    s.event(**owner,event_id='dispatch-event',action_id='dispatch-1',event_type='checkpoint',observed_at=s.now(),
        payload=json.loads(dispatch()['payload_json']))
    s.action_end(**owner,action_id='dispatch-1',status='success')
    return s,session,owner,jobs


def test_ledger_resolution_allows_one_fresh_intent_and_keeps_original_dispatch(tmp_path):
    s,session,owner,jobs=service_dispatch(tmp_path)
    proof={'dispatch_id':'dispatch-1','document_id':'document-1','frame_id':'root','source':'employer',
           'reason_code':'invalid_security_code','observed_at':s.now(),'fresh_after_dispatch':True}
    result=s.record_submission_rejection(**owner,proof=proof)
    assert result['submission_pending'] is False
    assert s.application_context(owner['attempt_id'])['attempt']['submission_pending'] is False
    s.action_start(**owner,action_id='correction',tool_name='local_browser.fill')
    s.action_end(**owner,action_id='correction',status='success')
    s.submission_intent(**owner,evidence='Corrected fresh challenge',fixture=True)
    assert s.attempt(owner['attempt_id'])['submission_pending'] is True
    original=next(json.loads(row['payload_json']) for row in s.events(owner['attempt_id']) if row['id']=='dispatch-event')
    assert original['status']=='possibly_executed'


def test_rejection_proof_requires_freshness_and_matching_action(tmp_path):
    s,session,owner,jobs=service_dispatch(tmp_path)
    with pytest.raises(ProtocolError,match='submission_rejection_unproven'):
        s.record_submission_rejection(**owner,proof={'dispatch_id':'dispatch-1','document_id':'document-1',
            'frame_id':'root','source':'employer','reason_code':'invalid_security_code',
            'observed_at':s.now(),'fresh_after_dispatch':False})
    assert s.attempt(owner['attempt_id'])['submission_pending']


@pytest.mark.parametrize('mode',['top','cross'])
def test_local_form_rejection_is_captured_and_correction_can_submit_once(tmp_path,monkeypatch,mode):
    import test_embedded_forms as fixture
    from job_applier.browser_controls import observe,click_control
    from job_applier.submission import submit
    html='''<form><label for="code">Security code</label><input id="code" maxlength="8" value="12345678">
<button id="submit" type="button">Submit application</button><div id="error" role="alert"></div></form>
<script>submit.onclick=async e=>{if(!e.isTrusted)return;await fetch('/fake-submit',{method:'POST'});
if(document.body.dataset.corrected==='true')document.body.innerHTML='<p>Thank you for applying</p>';
else document.getElementById('error').textContent='Invalid security code';};</script>'''
    monkeypatch.setattr(fixture,'FORM_HTML',html)
    class Ledger(fixture.SubmissionLedger):
        def call(self,operation,**params):
            if operation=='event':
                self.events.append({'payload_json':json.dumps(params['payload']),'observed_at':params['observed_at'],'stale':0})
                return {}
            if operation=='record_submission_rejection':
                proof=params['proof']
                row=event('submission_resolution','rejected',**{k:proof[k] for k in (
                    'dispatch_id','document_id','frame_id','source','reason_code')},resolution='fresh_employer_rejection')
                row['observed_at']=proof['observed_at'];self.events.append(row)
                return {'submission_pending':False}
            return super().call(operation,**params)
    async def check():
        async with fixture.fixture_browser(tmp_path,mode=mode) as (page,package,submissions):
            screen=await observe(page,package);target={'ref':screen['native']['submit']['ref']};ledger=Ledger()
            result=await submit(page,ledger.call,package,{'attempt_id':1},{'spool_dir':str(tmp_path),'cdp_url':'fixture'},
                page.target_id,lambda:click_control(page,target),seconds=1,application_control=target)
            assert result['status']=='application_incomplete' and result['submission_pending'] is False,result
            assert submissions==['/fake-submit']
            from job_applier.browser_frames import resolve_control
            document,_=await resolve_control(page,target)
            # A second fresh rejection must use the new dispatch, not the first
            # cycle's retained error with the same document and frame identity.
            await document.evaluate("document.getElementById('error').textContent=''")
            result=await submit(page,ledger.call,package,{'attempt_id':1},{'spool_dir':str(tmp_path),'cdp_url':'fixture'},
                page.target_id,lambda:click_control(page,target),seconds=1,application_control=target)
            assert result['status']=='application_incomplete' and len(submissions)==2,result
            await document.evaluate("document.body.dataset.corrected='true';document.getElementById('error').textContent=''")
            result=await submit(page,ledger.call,package,{'attempt_id':1},{'spool_dir':str(tmp_path),'cdp_url':'fixture'},
                page.target_id,lambda:click_control(page,target),seconds=1,application_control=target)
            assert result['status']=='applied' and submissions==['/fake-submit']*3,result
    asyncio.run(check())
