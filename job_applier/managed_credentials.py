"""Fill private credentials into controls selected from Hermes's current page."""
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path

from .cdp_client import CDPBrowser
from .managed_identity import is_same_application_scope


def credential_progress(call,ownership,params,*,result=None,action_id=None):
    """Attach private work to the existing timeline using labels and booleans only."""
    from .managed_shared import uid
    verification=params.get('mode')=='verification'
    action=params.get('action','fill')
    activity=({'inspect':'Inspect email verification','resend':'Request a fresh verification email',
        'fill':'Retrieve verification email and enter its code'}.get(action,'Verify email') if verification else 'Enter employer sign-in details')
    completed=result is not None and (result.get('values_committed') or result.get('resend_requested') or action=='inspect' and result.get('groups'))
    payload={'stage_id':'email_verification' if verification else 'authentication',
        'task_id':'email-code' if verification else 'sign-in-details','activity':activity,
        'task_state':'in_progress' if result is None else 'completed' if completed else 'recovering',
        'source':'private_credentials','handler':'private_credentials'}
    if completed:payload['evidence']='Observed resend control activated' if result.get('resend_requested') else 'Private fields verified' if result.get('values_committed') else 'Observed current verification group'
    if result is not None:payload['verification_result']='committed' if result.get('values_committed') else 'not_verified'
    try:call('event',**ownership,event_id=uid(),action_id=action_id,event_type='checkpoint',
             observed_at=datetime.now(timezone.utc).isoformat(),payload=payload)
    except Exception as exc:
        if result is not None:result['progress_error']=type(exc).__name__


MASK_CREDENTIALS = r"""(() => {
 window.__maskedCredentialNodes = [];
 const els = Array.from(document.querySelectorAll('input,textarea,[data-credential]')).filter(el=>
   el.type==='password'||el.hasAttribute('data-credential')||el.maxLength===1||
   /password|one.?time|otp|(?:security|verification|authentication)[\s_-]*code/i.test(
    [el.name,el.id,el.autocomplete,el.getAttribute('aria-label'),...[...(el.labels||[])].map(e=>e.textContent)].join(' '))||
   window.__jobbotFormScope?.privateControl?.(el));
 for (const el of els) {
  window.__maskedCredentialNodes.push({el, visibility: el.style.visibility});
  el.style.visibility = 'hidden';
 }
 return {masked_count: window.__maskedCredentialNodes.length};
})()"""

UNMASK_CREDENTIALS = r"""(() => {
 const list = window.__maskedCredentialNodes || [];
 for (const item of list) {
  if (item.el) item.el.style.visibility = item.visibility;
 }
 delete window.__maskedCredentialNodes;
 return {unmasked_count: list.length};
})()"""


async def capture_private_screenshot(page,path):
    """Existing credential mask, shared by local and legacy browser paths."""
    documents=[page]
    if getattr(page,'application_package',None):
        from .browser_frames import router_for
        router=await router_for(page)
        if not router.frames:await router.discover()
        documents.extend(router.frames.values())
    masked=[]
    try:
        for document in documents:
            if hasattr(document,'validate'):await document.validate()
            await document.evaluate(MASK_CREDENTIALS);masked.append(document)
        await page.screenshot(str(path))
    finally:
        for document in reversed(masked):
            try:await document.evaluate(UNMASK_CREDENTIALS)
            except Exception:pass  # A replaced document has no retained mask.


FILL_SELECTED = r"""async (args) => {
 delete window.__jobbotCredentialReceipt;
 const result={email_filled:false,passwords_filled_count:0,
   confirmation_present:!!args.confirmation_ref,values_committed:false,
   account_mode:args.confirmation_ref?'create-account':'sign-in',error:null};
 const selected=[];
 for(const [role,ref] of [['email',args.email_ref],['password',args.password_ref],
                         ['confirmation',args.confirmation_ref]]) {
   if(role==='confirmation'&&!ref)continue;
   if(!ref)return {...result,error:'missing_'+role+'_ref'};
   let matches;
   try {
    const inventoryRef=ref.startsWith('wd:')||ref.startsWith('form:');
    const mapped=ref.startsWith('wd:')?window.__jobbotWorkdayScope?.inventory?.get(ref):window.__jobbotFormScope?.inventory?.get(ref);
    matches=inventoryRef?(mapped?[mapped]:[]):document.querySelectorAll(ref);
   }catch{return {...result,error:'invalid_'+role+'_ref'};}
   if(matches.length!==1)return {...result,error:'ambiguous_or_stale_'+role+'_ref',match_count:matches.length};
   const e=matches[0],r=e.getBoundingClientRect();
   if(e.tagName!=='INPUT'||!e.isConnected||!r.width||!r.height||getComputedStyle(e).visibility==='hidden'||e.disabled||e.readOnly)
     return {...result,error:'unavailable_'+role+'_control'};
   if((role!=='email'&&e.type!=='password')||(role==='email'&&!['email','text'].includes(e.type)))
     return {...result,error:'incorrect_'+role+'_control_type'};
   if(selected.some(x=>x.e===e))return {...result,error:'duplicate_control_ref'};
   selected.push({role,e,value:role==='email'?args.email:args.password});
 }
 const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
 for(const {e,value} of selected){
   e.focus();setter.call(e,value);
   e.dispatchEvent(new Event('input',{bubbles:true}));
   e.dispatchEvent(new Event('change',{bubbles:true}));e.blur();
 }
 // Background/occluded browser windows may suspend animation frames. Verify
 // the committed input values after a bounded settle, without waiting forever.
 await new Promise(resolve=>{
   const timer=setTimeout(resolve,150);
   requestAnimationFrame(()=>requestAnimationFrame(()=>{clearTimeout(timer);resolve();}));
 });
 for(const {role,e,value} of selected){
   const ok=e.isConnected&&(role==='email'?e.value.toLowerCase()===value.toLowerCase():e.value===value);
   if(role==='email')result.email_filled=ok;
   else if(ok)result.passwords_filled_count++;
 }
  result.values_committed=selected.every(({role,e,value})=>e.isConnected&&(role==='email'?e.value.toLowerCase()===value.toLowerCase():e.value===value));
 if(!result.values_committed)result.error='values_not_committed';
 if(result.values_committed){
   // A private, document-local receipt lets native activation recheck the same
   // approved values after observation, ledger writes and pointer hover. Values
   // remain in this closure; only an opaque token and booleans leave the page.
   const token=crypto.randomUUID(),url=location.href;
   const password=selected.find(x=>x.role==='password').e;
   const root=password.closest('[role="dialog"]')||password.closest('form')||document;
   const matches=({role,e,value})=>e.isConnected&&(role==='email'?e.value.toLowerCase()===value.toLowerCase():e.value===value);
   let refilled=false;
   window.__jobbotCredentialReceipt={token,verify(control){
     const safe=location.href===url&&root.contains(control)&&selected.every(({e})=>
       e.isConnected&&root.contains(e)&&!e.disabled&&!e.readOnly&&e.getBoundingClientRect().width&&
       e.getBoundingClientRect().height&&getComputedStyle(e).visibility!=='hidden');
     if(!safe)return {credentials_verified_before_click:false,reason:'credential_controls_changed_before_click'};
     for(const item of selected){
       if(matches(item))continue;
       const {e,value}=item;
       refilled=true;e.focus();setter.call(e,value);
       e.dispatchEvent(new Event('input',{bubbles:true}));
       e.dispatchEvent(new Event('change',{bubbles:true}));e.blur();
     }
     const matched=selected.every(matches);
     return {credentials_verified_before_click:matched,credentials_refilled_before_click:refilled,
       ...(matched?{}:{reason:'credential_values_changed_before_click'})};
   }};
   result.credential_token=token;
 }
 return result;
}"""


DEFAULT_CREDENTIAL_REF='credential:profile/accounts/default'


FILL_VERIFICATION = r"""async args => {
 const scope=window.__jobbotFormScope,group=scope?.verificationRecords?.get(args.challenge_ref);
 const fail=error=>({values_committed:false,error});
 if(!group||!Array.isArray(args.refs)||args.refs.length!==group.refs.length||new Set(args.refs).size!==args.refs.length)
   return fail('verification_group_changed');
 if(typeof args.value!=='string'||args.value.length!==group.length||!/^\w+$/.test(args.value))
   return fail('verification_length_mismatch');
 const elements=[];
 for(let i=0;i<args.refs.length;i++){
  const el=scope.inventory.get(args.refs[i]);
  if(args.refs[i]!==group.refs[i]||el!==group.elements[i])return fail('verification_refs_changed');
  const box=el.getBoundingClientRect();
  if(!el.isConnected||el.tagName!=='INPUT'||el.disabled||el.readOnly||!box.width||!box.height||getComputedStyle(el).visibility==='hidden')
   return fail('verification_control_unavailable');
  if(elements.includes(el))return fail('duplicate_verification_control');
  elements.push(el);
 }
 const values=elements.length===1?[args.value]:[...args.value];
 const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
 // All references and the full group are checked before any input changes.
 elements.forEach((el,i)=>setter.call(el,values[i]));
 elements.forEach(el=>{el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));});
 await new Promise(resolve=>setTimeout(resolve,150));
 const committed=elements.map((el,i)=>el.isConnected&&el.value===values[i]);
 return {values_committed:committed.every(Boolean),segments_committed:committed.filter(Boolean).length,
   ...(committed.every(Boolean)?{}:{error:'verification_values_not_committed'})};
}"""


async def fill_page_verification(config,package,page,params):
    """Enter the executor-selected code; mailbox interpretation belongs to the LLM."""
    from .browser_controls import FORM,click_control
    from .browser_frames import resolve_control,FramePage
    from .hermes_gmail import mailbox_handoff
    allowed={'target_id','mode','action','refs','challenge_ref','requested_at','resend_ref','message_id','received_at','value'}
    if set(params)-allowed:return {'values_committed':False,'error':'invalid_verification_parameters'}
    if not is_same_application_scope(package['job']['url'],await page.evaluate('location.href')):
        return {'values_committed':False,'error':'verification_target_scope_mismatch'}
    page.application_package=package
    refs=params.get('refs',[])
    if not isinstance(refs,list) or len(refs)>12 or any(not isinstance(ref,str) for ref in refs):
        return {'values_committed':False,'error':'observed_verification_refs_required'}
    document=None;local_refs=[]
    for ref in refs:
        current,local=await resolve_control(page,{'ref':ref})
        if document is not None and document is not current:
            return {'values_committed':False,'error':'verification_controls_must_share_document'}
        document=current;local_refs.append(local['ref'])
    document=document or page
    observed=await document.evaluate_function(FORM,{'method':'verification'})
    public_groups=[dict(g,refs=[document.wrap(ref) for ref in g['refs']],
        **({'resend_ref':document.wrap(g['resend_ref'])} if g.get('resend_ref') else {})) if isinstance(document,FramePage) else g
        for g in observed['groups']]
    handoff={'groups':public_groups,'mailbox':mailbox_handoff(config),
             'instruction':'Read the email with the existing Hermes Gmail skill. Choose the relevant code closest to the request timestamp and pass it as value with these refs, or fill the observed code fields with browser fill. Recheck delayed mail in this same application. This helper only enters the selected code; it does not verify email eligibility. Do not finalize blocked or ask for manual entry merely because a helper did not recognize the message.'}
    action=params.get('action','fill')
    if action=='inspect':return dict(handoff,values_committed=False)
    group=next((g for g in observed['groups'] if g['challenge_ref']==params.get('challenge_ref')),None)
    if not group or group['refs']!=local_refs:return dict(handoff,values_committed=False,error='verification_group_changed')
    if action=='resend':
        current,local=await resolve_control(page,{'ref':params.get('resend_ref','')})
        if current is not document or not group.get('resend_ref') or local['ref']!=group['resend_ref']:
            return dict(handoff,values_committed=False,error='observed_resend_control_required')
        requested=datetime.now(timezone.utc).isoformat()
        result=await click_control(page,{'ref':params['resend_ref']})
        if not result.get('clicked'):return dict(handoff,values_committed=False,error='verification_resend_unconfirmed')
        await asyncio.sleep(.2)
        fresh=await document.evaluate_function(FORM,{'method':'verification'})
        if len(fresh['groups'])!=1:return {'values_committed':False,'resend_requested':True,'requested_at':requested,'error':'verification_group_changed'}
        current_group=fresh['groups'][0]
        await document.evaluate_function('(a)=>{window.__jobbotFormScope.verificationRequests.set(a.ref,a.time);return true;}',
            {'ref':current_group['challenge_ref'],'time':requested})
        current_group=dict(current_group,requested_at=requested)
        if isinstance(document,FramePage):
            current_group['refs']=[document.wrap(ref) for ref in current_group['refs']]
            if current_group.get('resend_ref'):current_group['resend_ref']=document.wrap(current_group['resend_ref'])
        return {'values_committed':False,'resend_requested':True,'requested_at':requested,'group':current_group}
    if action!='fill':return {'values_committed':False,'error':'invalid_verification_action'}
    if 'value' not in params:return dict(handoff,values_committed=False)
    result=await document.evaluate_function(FILL_VERIFICATION,{
        'refs':local_refs,'challenge_ref':group['challenge_ref'],'value':params['value']})
    # `value` is intentionally never copied out of this private call.
    return dict(result,challenge_ref=group['challenge_ref'],message_id=params.get('message_id'),
                requested_at=group.get('requested_at') or params.get('requested_at'),received_at=params.get('received_at'),
                instruction='Submit promptly using the existing authorized submission boundary.' if result.get('values_committed') else
                'Reinspect the current verification group before recovery; no input value is returned.')


def resolve_employer_credential(config, package):
    """Resolve only a saved explicit reference or the configured retained default.

    Return values stay inside the private filler. The ledger stores the reference.
    Never replace an unavailable saved credential with a different password.
    """
    raw = json.loads(Path(config['credential_profile_path']).read_text(encoding='utf-8'))
    reference=(package.get('account') or {}).get('credential_ref') or DEFAULT_CREDENTIAL_REF
    key='default' if reference==DEFAULT_CREDENTIAL_REF else config.get('credential_account_keys',{}).get(reference)
    if not key:raise ValueError('saved_credential_reference_unavailable')
    account = raw.get('accounts', {}).get(key, {})
    if not account.get('email') or not account.get('password'):
        raise ValueError('configured_credentials_unavailable')
    profile = package['attempt']['profile_json']
    if isinstance(profile, str):
        profile = json.loads(profile)
    if profile.get('identity', {}).get('email', '').casefold() != account['email'].casefold():
        raise ValueError('candidate_credential_identity_mismatch')
    return dict(email=account['email'],password=account['password'],credential_ref=reference)


async def fill_page_credentials(config, package, page, params):
    """Fill the already-owned page; no new connection, credential output or logs."""
    if params.get('mode')=='verification':
        try:return await fill_page_verification(config,package,page,params)
        except Exception as exc:return {'error':'verification_transport_failed','error_type':type(exc).__name__,'values_committed':False}
    if set(params)-{'target_id','email_ref','password_ref','confirmation_ref'}:
        return {'error':'invalid_credential_parameters','values_committed':False}
    try:
        account=resolve_employer_credential(config,package)
        url=await page.evaluate('location.href')
        if not is_same_application_scope(package['job']['url'],url):
            return {'error':'credential_target_scope_mismatch','values_committed':False}
        page.application_package=package
        from .browser_frames import resolve_control
        target_page=None;local=dict(params)
        for key in ('email_ref','password_ref','confirmation_ref'):
            if not params.get(key):continue
            document,ref=await resolve_control(page,{'ref':params[key]})
            if target_page is not None and document is not target_page:
                return {'error':'credential_controls_must_share_document','values_committed':False}
            target_page=document;local[key]=ref['ref']
        result=await (target_page or page).evaluate_function(FILL_SELECTED,dict(local,email=account['email'],password=account['password']))
        return dict(result,credential_ref=account['credential_ref'])
    except ValueError as exc:
        known={'saved_credential_reference_unavailable','configured_credentials_unavailable','candidate_credential_identity_mismatch'}
        return {'error':str(exc) if str(exc) in known else 'credential_configuration_invalid','values_committed':False}
    except Exception as exc:
        return {'error':'credential_transport_failed','error_type':type(exc).__name__,'values_committed':False}


async def fill_credentials(config, package, params):
    """Selectors are observed control references, never inferred by this helper."""
    browser = await CDPBrowser.connect(config.get('cdp_url', 'http://127.0.0.1:9222'),
                                       target_id=params['target_id'], expected_mode=config.get('browser_mode','headed'))
    try:
        page = await browser.get_current_page()
        return await fill_page_credentials(config,package,page,params)
    finally:
        await browser.close()


def handle_credentials(config, package, params):
    try:
        return asyncio.run(fill_credentials(config, package, params))
    except Exception as exc:
        # Browser/transport exceptions can contain the evaluation arguments.
        return {'error': 'credential_transport_failed', 'error_type': type(exc).__name__,
                'values_committed': False}
