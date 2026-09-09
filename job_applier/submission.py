"""One submit and bounded evidence capture shared by local ATS execution paths."""
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import uuid
from urllib.parse import urlsplit,urlunsplit

from .managed_identity import is_post_submit_scope,is_same_application_scope,job_requisition
from .managed_redaction import safe_text

SCRIPT=(Path(__file__).parent/'browser_helpers/submission_observe.js').read_text(encoding='utf-8')


def _stamp():return datetime.now(timezone.utc).isoformat()


def _issued(call,ownership):
    from .managed_shared import submission_pending
    rows=call('events',attempt_id=ownership['attempt_id'])
    return submission_pending({'submit_intent_at':True},rows)


async def submit(page,call,package,ownership,config,target_id,activate,*,seconds=15,confirmation_only=False,application_control=None):
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
            'baseline':previous.get('baseline',[]),'observations':previous.get('observations',[]),
            'frames':previous.get('frames',[]),'diagnostics':[]}
    def persist():
        temporary=record_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record,indent=2),encoding='utf-8');temporary.replace(record_path)
    binding='__jobbotSubmit'+uuid.uuid4().hex;name=binding+'State'
    allowed=profile_policy(package).get('submission_evidence_sources',['employer'])
    def remember(item):
        item['text']=safe_text(item.get('text',''),700)
        if not any(r['source']==item['source'] and r['text']==item['text'] for r in record['observations']):
            record['observations'].append(item);persist()
    issued=already_issued
    def receive(params):
        if not issued or params.get('name')!=binding:return
        item=json.loads(params.get('payload','{}'))
        if item.get('source') not in ('employer','simplify') or not is_post_submit_scope(package['job']['url'],item.get('url','')):return
        remember(item)
    remove=page._session.subscribe('Runtime.bindingCalled',receive)
    embedded=_EmbeddedEvidence(page,package,record,remember,already_issued)
    script_id=None;aid=None;clicked=False;click_error=None
    try:
        await embedded.arm(application_control)
        await page._session.call('Runtime.addBinding',{'name':binding})
        args={'name':name,'binding':binding,'baseline':record['baseline'],'active':already_issued,
              'requisition':job_requisition(package['job'])}
        before=await page.evaluate_function(SCRIPT,args)
        if not already_issued:
            record['baseline']=before['baseline'];args['baseline']=before['baseline']
        # The new document hook retains capture across a normal submit redirect.
        future=dict(args,active=True)
        installed=await page._session.call('Page.addScriptToEvaluateOnNewDocument',{'source':'if(window===window.top){('+SCRIPT+')('+json.dumps(future)+')} '})
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
            issued=True
            await page.evaluate_function(SCRIPT,{'name':name,'operation':'start'})
            await embedded.start()
            try:
                result=await activate()
                clicked=bool(result.get('clicked') or result.get('status')=='clicked')
                if not clicked:
                    if result.get('execution')=='not_executed' or result.get('status') in ('stale','disabled'):
                        event('submission_click','not_executed',result.get('reason','control_not_activated'))
                        issued=False;embedded.started=False
                        record['dispatch']='not_executed';persist()
                        return {'status':'inspection_required','attempt_id':ownership['attempt_id'],
                            'execution':'not_executed','submission_pending':False,
                            'reason':result.get('reason','control_not_activated'),'evidence_path':str(record_path),
                            'next_step':'Refresh the observed final control and recover in this session. No submission was dispatched.'}
                    click_error=result.get('reason','click_unconfirmed')
            except Exception as exc:click_error=safe_text(str(exc),700)
            finally:
                owned('action_end',action_id=aid,status='success' if clicked else 'failed')
                aid=None
        deadline=time.monotonic()+min(max(seconds,1),30)
        while time.monotonic()<deadline:
            await embedded.poll()
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
        event('submission_observation','pending','Confirmation not captured; preserve the owned page for inspection')
        return {'status':'submission_unknown','attempt_id':ownership['attempt_id'],'reason':click_error or 'confirmation_not_captured',
                'evidence_path':str(record_path),'image_path':record.get('image_path'),'diagnostics':record['diagnostics'],
                'next_step':'Read the owned screenshot or snapshot, or reconcile direct user confirmation. Do not submit again.'}
    finally:
        if aid:owned('action_end',action_id=aid,status='failed')
        remove()
        await embedded.close()
        try:
            if script_id:await page._session.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':script_id},timeout=3)
            await page.evaluate_function('(name)=>{window[name]?.observerStop?.();delete window[name];}',name)
            await page._session.call('Runtime.removeBinding',{'name':binding},timeout=3)
        except Exception:pass


class _EmbeddedEvidence:
    """Companion collector scoped to the DOM-owned application frame ids.

    The ordinary submit collector still covers the employer parent and Simplify.
    Child bindings are filtered by execution context/frame id, including after a
    document navigation; replacing an iframe cannot manufacture confirmation.
    """
    def __init__(self, page, package, record, remember, already_issued):
        self.page,self.package,self.record,self.remember=page,package,record,remember
        self.already_issued=already_issued
        self.started=already_issued
        self.collectors=[]

    async def arm(self, control):
        from .cdp_client import CDPPage
        from .managed_context import platform_for_url
        if not isinstance(self.page,CDPPage) or platform_for_url(self.package['job']['url'])=='workday':return
        from .browser_frames import router_for,resolve_control,WORLD
        router=await router_for(self.page,self.package)
        if self.already_issued:
            router.frames.clear();router.diagnostics.clear()
        if not router.frames:await router.discover()
        if not self.already_issued and control and str(control.get('ref','')).startswith('frame:'):
            selected,_=await resolve_control(self.page,control)
            frames=[selected]
        else:frames=list(router.frames.values())
        previous={item['frame_id']:item for item in self.record['frames']}
        for frame in frames:
            if self.already_issued and frame.frame_id not in previous:continue
            await frame.validate()
            saved=previous.get(frame.frame_id,{})
            item={'frame_id':frame.frame_id,'url':saved.get('url',frame.url),
                  'baseline':saved.get('baseline',[])}
            if not saved:self.record['frames'].append(item)
            name='__jobbotFrameSubmit'+uuid.uuid4().hex
            collector={'frame':frame,'binding':name,'name':name+'State','saved':item,
                       'contexts':{frame.context_id},'removers':[],'script_id':None}
            self.collectors.append(collector)
            def created(params,c=collector):
                context=params.get('context',{})
                if context.get('auxData',{}).get('frameId')==c['frame'].frame_id and context.get('name')==WORLD:
                    c['contexts'].add(context['id']);c['frame'].context_id=context['id']
            def received(params,c=collector):
                if not self.started or params.get('name')!=c['binding'] or params.get('executionContextId') not in c['contexts']:return
                try:proof=json.loads(params.get('payload','{}'))
                except (TypeError,ValueError):return
                if proof.get('source') not in ('employer','simplify') or not is_post_submit_scope(c['saved']['url'],proof.get('url','')):return
                self.remember(dict(proof,frame_id=c['frame'].frame_id))
            collector['receive']=received
            collector['removers'].append(frame._session.subscribe('Runtime.executionContextCreated',created))
            collector['removers'].append(frame._session.subscribe('Runtime.bindingCalled',received))
            await frame._session.call('Runtime.addBinding',{'name':name,'executionContextName':WORLD})
            args={'name':collector['name'],'binding':name,'baseline':item['baseline'],'active':self.already_issued}
            before=await frame.evaluate_function(SCRIPT,args)
            if not self.already_issued:item['baseline']=before['baseline']
            future=dict(args,baseline=item['baseline'],active=True)
            installed=await frame._session.call('Page.addScriptToEvaluateOnNewDocument',
                {'source':'('+SCRIPT+')('+json.dumps(future)+')','worldName':WORLD})
            collector['script_id']=installed['identifier']

    async def start(self):
        self.started=True
        for c in self.collectors:
            await c['frame'].evaluate_function(SCRIPT,{'name':c['name'],'operation':'start'})

    async def poll(self):
        from .cdp_client import CDPPage
        for c in self.collectors:
            try:
                frame=c['frame']
                current=await CDPPage.evaluate(frame,'location.href')
                if not is_post_submit_scope(c['saved']['url'],current):continue
                proofs=await CDPPage.evaluate_function(frame,SCRIPT,{'name':c['name'],'operation':'read'})
                for proof in proofs:
                    c['receive']({'name':c['binding'],'executionContextId':frame.context_id,'payload':json.dumps(proof)})
            except Exception:
                pass  # A transient binding can still arrive across navigation.

    async def close(self):
        from .cdp_client import CDPPage
        for c in self.collectors:
            for remove in c['removers']:remove()
            try:
                frame=c['frame']
                if c['script_id']:await frame._session.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':c['script_id']},timeout=3)
                await CDPPage.evaluate_function(frame,'(name)=>{window[name]?.observerStop?.();delete window[name];}',c['name'])
                await frame._session.call('Runtime.removeBinding',{'name':c['binding']},timeout=3)
            except Exception:pass
