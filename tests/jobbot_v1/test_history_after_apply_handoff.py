"""Synthetic continuity after a verified Apply handoff changes the current key."""
import asyncio
import json
import pytest
from job_applier.managed_identity import job_key
from test_local_sessions import setup, reserve, connect, own


@pytest.mark.parametrize('case',['valid','source_mismatch','stale_fence','stale_target_identity','stale_browser'])
def test_retained_history_source_survives_verified_target_key_change(tmp_path,case):
    s,asset,jobs,*_=setup(tmp_path)
    session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    source='https://employer0.example.test/posting?reference=synthetic';landing='https://employer0.example.test/application'
    s.handoff_target(**owner,current_target_id='new-target',new_target_id='new-target',
        url=source,expected_url=source,evidence='Synthetic observed posting redirect')
    anchor=dict(session_id=session['id'],attempt_id=owner['attempt_id'],fence=owner['fence'],
                target_id='new-target',browser_id=None,entry_id=7,source_url=source)
    with s.tx() as db:
        meta=json.loads(s.session(session['id'])['metadata_json']);meta['route_history_anchor']=anchor
        db.execute('UPDATE application_sessions SET metadata_json=? WHERE id=?',(json.dumps(meta),session['id']))
    s.handoff_target(**owner,current_target_id='new-target',new_target_id='new-target',
        url=landing,expected_url=landing,evidence='Synthetic observed Apply destination')
    replacement=dict(anchor,entry_id=9,source_url=landing+'/welcome')
    proof={'expected':dict(anchor),'replacement':replacement,'target_identity':job_key(landing),'identity_url':landing}
    if case=='source_mismatch':source='https://employer0.example.test/unobserved'
    if case=='stale_fence':proof['expected']['fence']=-1
    if case=='stale_target_identity':proof['target_identity']=job_key(source)
    if case=='stale_browser':proof['replacement']['browser_id']='different-browser'
    try:
        result=s.handoff_target(**owner,current_target_id='new-target',new_target_id='new-target',
            url=landing+'/welcome',source_url=source,_history_proof=proof,
            evidence='Synthetic internally observed same-origin browser history')
    except Exception as exc:
        from job_applier.managed_shared import ProtocolError
        assert case=='source_mismatch' and isinstance(exc,ProtocolError) and exc.code=='target_job_mismatch'
        result=None
    if case!='valid':
        assert not result
        assert s.application_context(owner['attempt_id'])['job']['url']==landing
        return
    assert result
    assert s.application_context(owner['attempt_id'])['job']['url']==landing+'/welcome'


@pytest.mark.parametrize('navigation',['document','pushState','replaceState'])
def test_delayed_page_after_apply_handoff_recovers_and_submits(tmp_path,navigation):
    from test_owned_route_history import owned_page,gate,SOURCE
    from job_applier.application_runtime import browser_action
    from job_applier.managed_client import LocalClient
    landing='https://applications.example.test/application'
    welcome='https://applications.example.test/welcome'
    async def run():
        from datetime import datetime, timezone
        from job_applier.application_deadline import freeze
        frozen=freeze({}, {'application_time_limit_minutes':60}, datetime.now(timezone.utc).isoformat())['application_deadline']
        async with owned_page(tmp_path,metadata={'application_deadline':frozen},
                              settings={'mode':'pilot','submission_mode':'submit'}) as (page,s,session,owner):
            source='https://applications.example.test/posting?reference=synthetic'
            s.handoff_target(**owner,current_target_id=page.target_id,new_target_id=page.target_id,
                url=source,expected_url=source,evidence='Synthetic observed posting redirect')
            await page.evaluate('history.replaceState({},"",'+json.dumps(source)+')')
            await gate(page,s,owner)  # Retain verified source history before Apply.
            s.handoff_target(**owner,current_target_id=page.target_id,new_target_id=page.target_id,
                url=landing,expected_url=landing,evidence='Synthetic observed Apply destination')
            await page.evaluate('history.pushState({},"",'+json.dumps(landing)+')')
            # No intermediate observation: the accepted Apply landing moves on.
            if navigation=='document':await page.goto(welcome)
            else:await page.evaluate('history.'+navigation+'({},"",'+json.dumps(welcome)+')')
            await page.evaluate('document.body.innerHTML='+json.dumps(
                '<label>Full name<input id="name" required></label><button onclick="if(!event.isTrusted)return;document.body.innerHTML=\'<h1>Thank you for applying</h1>\'">Submit application</button>'))
            before=s.attempt(owner['attempt_id']);deadline=json.loads(s.session(session['id'])['metadata_json']).get('application_deadline')
            result=await gate(page,s,owner)
            assert result['identity']['status']=='same_job',result
            client=LocalClient({'instance_id':s.instance_id},service=s);cfg={'cdp_url':page.fixture_endpoint,'browser_mode':'headless','spool_dir':str(tmp_path/'spool')}
            package=s.application_context(owner['attempt_id'])
            filled=await asyncio.to_thread(browser_action,cfg,client,owner,package,page.target_id,{'method':'fill','selector':'#name','value':'Synthetic Candidate'})
            assert filled['committed']
            submitted=await asyncio.to_thread(browser_action,cfg,client,owner,package,page.target_id,{'method':'submit','selector':'button'})
            assert submitted['status']=='applied',submitted
            assert s.attempt(owner['attempt_id'])['started_at']==before['started_at']
            assert json.loads(s.session(session['id'])['metadata_json']).get('application_deadline')==deadline
            assert deadline==frozen
            assert s.job(session['job_id'])['url']==SOURCE
    asyncio.run(run())
