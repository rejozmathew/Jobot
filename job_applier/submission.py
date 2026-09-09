"""One submit and bounded evidence capture shared by local ATS execution paths."""
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import uuid
from urllib.parse import urlsplit,urlunsplit

from .managed_identity import is_post_submit_scope,is_same_application_scope
from .managed_redaction import safe_text

SCRIPT=(Path(__file__).parent/'browser_helpers/submission_observe.js').read_text(encoding='utf-8')


def _stamp():return datetime.now(timezone.utc).isoformat()


def _issued(call,ownership):
    rows=call('events',attempt_id=ownership['attempt_id'])
    for row in reversed(rows):
        p=json.loads(row['payload_json'])
        if p.get('operation')=='submission_click':return p.get('status')!='not_executed'
    return False


async def submit(page,call,package,ownership,config,target_id,activate,*,seconds=15,confirmation_only=False):
    """Capture before click, never repeat an uncertain click, and persist before finish."""
    from .application_answers import profile_policy
    from .managed_credentials import capture_private_screenshot
    def owned(operation,**params):return call(operation,**ownership,**params)
    def event(operation,status,evidence='',source='JobBot'):
        owned('event',event_id=str(uuid.uuid4()),event_type='checkpoint',observed_at=_stamp(),
              payload={'phase':'submission','operation':operation,'status':status,'evidence':evidence,'source':source})
    attempt=call('attempt_status',attempt_id=ownership['attempt_id'])
    if attempt.get('completed_at'):
        return dict({k:attempt.get(k) for k in ('id','outcome','evidence','completed_at')},
                    status=attempt.get('outcome'),attempt_id=ownership['attempt_id'])
    already_issued=bool(confirmation_only or (attempt.get('submit_intent_at') and _issued(call,ownership)))
    folder=Path(config['spool_dir'])/'submission';folder.mkdir(parents=True,exist_ok=True)
    record_path=folder/('attempt-'+str(ownership['attempt_id'])+'.json')
    previous=json.loads(record_path.read_text(encoding='utf-8')) if already_issued and record_path.is_file() else {}
    if previous and previous.get('target_id')!=target_id:raise ValueError('submission_target_mismatch')
    record={'attempt_id':ownership['attempt_id'],'target_id':target_id,'started_at':previous.get('started_at',_stamp()),
            'baseline':previous.get('baseline',[]),'observations':previous.get('observations',[]),'diagnostics':[]}
    def persist():
        temporary=record_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record,indent=2),encoding='utf-8');temporary.replace(record_path)
    binding='__jobbotSubmit'+uuid.uuid4().hex;name=binding+'State'
    allowed=profile_policy(package).get('submission_evidence_sources',['employer'])
    def receive(params):
        if params.get('name')!=binding:return
        item=json.loads(params.get('payload','{}'))
        if item.get('source') not in ('employer','simplify') or not is_post_submit_scope(package['job']['url'],item.get('url','')):return
        item['text']=safe_text(item.get('text',''),700)
        if not any(r['source']==item['source'] and r['text']==item['text'] for r in record['observations']):
            record['observations'].append(item);persist()
    remove=page._session.subscribe('Runtime.bindingCalled',receive)
    script_id=None;aid=None;clicked=False;click_error=None
    try:
        await page._session.call('Runtime.addBinding',{'name':binding})
        args={'name':name,'binding':binding,'baseline':record['baseline'],'active':already_issued,
              'requisition':package['job'].get('requisition_id') or package['job']['url'].rstrip('/').rsplit('_',1)[-1]}
        before=await page.evaluate_function(SCRIPT,args)
        if not already_issued:
            record['baseline']=before['baseline'];args['baseline']=before['baseline']
        # The new document hook retains capture across a normal submit redirect.
        future=dict(args,active=True)
        installed=await page._session.call('Page.addScriptToEvaluateOnNewDocument',{'source':'('+SCRIPT+')('+json.dumps(future)+')'})
        script_id=installed['identifier'];persist()
        if not already_issued:
            url=await page.evaluate('location.href')
            if not is_same_application_scope(package['job']['url'],url):raise ValueError('target_job_mismatch')
            gate=await asyncio.to_thread(owned,'browser_observe',target_id=target_id,cdp_url=config['cdp_url'])
            if not gate.get('native_takeover_authorized',gate.get('quiescent')):
                return {'status':'inspection_required','reason':'writer_activity_unconfirmed','attempt_id':ownership['attempt_id']}
            aid=str(uuid.uuid4());owned('action_start',action_id=aid,tool_name='browser.submit')
            if not attempt.get('submit_intent_at'):
                owned('submission_intent',evidence='Observed enabled final submit control for the owned application in authorized submit mode')
            event('submission_click','possibly_executed','Confirmation capture armed before the single submit')
            await page.evaluate_function(SCRIPT,{'name':name,'operation':'start'})
            try:
                result=await activate()
                clicked=bool(result.get('clicked') or result.get('status')=='clicked')
                if not clicked:
                    if result.get('execution')=='not_executed' or result.get('status') in ('stale','disabled'):
                        event('submission_click','not_executed',result.get('reason','control_not_activated'))
                    click_error=result.get('reason','click_unconfirmed')
            except Exception as exc:click_error=safe_text(str(exc),700)
            finally:
                owned('action_end',action_id=aid,status='success' if clicked else 'failed')
                aid=None
        deadline=time.monotonic()+min(max(seconds,1),30)
        while time.monotonic()<deadline:
            if any(r['source'] in allowed for r in record['observations']):break
            try:
                url=await page.evaluate('location.href')
                parts=urlsplit(url)
                record['last_url']=urlunsplit((parts.scheme,parts.netloc,parts.path,'',''))
                if is_post_submit_scope(package['job']['url'],url):
                    for item in await page.evaluate_function(SCRIPT,{'name':name,'operation':'read'}):
                        receive({'name':binding,'payload':json.dumps(item)})
                else:
                    detail='Post-submit URL is outside confirmation scope'
                    if detail not in record['diagnostics']:record['diagnostics'].append(detail)
            except Exception as exc:
                detail=safe_text(str(exc),700)
                if detail not in record['diagnostics']:record['diagnostics'].append(detail)
            pulse=owned('heartbeat')
            if pulse.get('control')!='running':break
            await asyncio.sleep(.2)
        if click_error:record['diagnostics'].append(click_error)
        try:
            if is_post_submit_scope(package['job']['url'],await page.evaluate('location.href')):
                screenshot=folder/('attempt-'+str(ownership['attempt_id'])+'-'+uuid.uuid4().hex[:8]+'.png')
                await capture_private_screenshot(page,screenshot);record['image_path']=str(screenshot)
        except Exception as exc:record['diagnostics'].append('Screenshot: '+safe_text(str(exc),700))
        record['observed_at']=_stamp();persist()
        proof=next((r for r in record['observations'] if r['source'] in allowed),None)
        if proof:
            evidence=proof['source']+': '+proof['text']
            event('submission_confirmed','applied',evidence,proof['source'])
            # The host stops the owned process tree before releasing the workspace.
            # Confirmation does not grant another form write or assume writer idle.
            owned('finish',outcome='applied',evidence=evidence,quiescent=False)
            return {'status':'applied','attempt_id':ownership['attempt_id'],'source':proof['source'],
                    'evidence':evidence,'evidence_path':str(record_path),'image_path':record.get('image_path')}
        event('submission_observation','pending','Confirmation not captured; preserve the owned page for bounded inspection')
        return {'status':'submission_unknown','attempt_id':ownership['attempt_id'],'reason':click_error or 'confirmation_not_captured',
                'evidence_path':str(record_path),'image_path':record.get('image_path'),'diagnostics':record['diagnostics'],
                'inspection_seconds':120,'next_step':'Read the owned screenshot or snapshot, or reconcile direct user confirmation. Do not submit again.'}
    finally:
        if aid:owned('action_end',action_id=aid,status='failed')
        remove()
        try:
            if script_id:await page._session.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':script_id},timeout=3)
            await page.evaluate_function('(name)=>{window[name]?.observerStop?.();delete window[name];}',name)
            await page._session.call('Runtime.removeBinding',{'name':binding},timeout=3)
        except Exception:pass
