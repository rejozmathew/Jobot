"""Shared form operations on the existing owned target; no ATS execution engine."""
import asyncio
import json
from pathlib import Path

ROOT=Path(__file__).parent/'browser_helpers'
FORM=(ROOT/'form_controls.js').read_text(encoding='utf-8')
POINTER=(ROOT/'workday_click.js').read_text(encoding='utf-8')


async def observe(page, package):
    from .managed_context import platform_for_url
    if platform_for_url(package['job']['url'])=='workday':
        from .workday_fast import observe_page
        return await observe_page(page,package)
    from .simplify_boundary import OBSERVE
    shared=await page.evaluate(OBSERVE)
    native=await page.evaluate_function(FORM,{'method':'observe','page_signature':shared.get('page_signature')})
    simplify_inventory=list(shared.get('inventory',[]))
    # Workday's observer above is intentionally unchanged. All other ATSs share
    # the same inventory whether controls live in this document or an embed.
    from .cdp_client import CDPPage
    if isinstance(page, CDPPage):
        from .browser_frames import router_for
        router=await router_for(page,package)
        router.frames.clear();router.diagnostics.clear()
        await router.discover()
        writers=[]
        for frame in router.frames.values():
            writer=await frame.evaluate(OBSERVE)
            writers.append((frame,writer))
            simplify_inventory.extend(dict(c,ref=frame.wrap(c['ref']),document='application_frame') for c in writer.get('inventory',[]))
            child=await frame.evaluate_function(FORM,{'method':'observe','page_signature':shared.get('page_signature')})
            for field in child['inventory']:
                field['ref']=frame.wrap(field['ref']);field['document']='application_frame'
                native['inventory'].append(field)
            for kind,control in child['native'].items():
                native['native'][kind]=({'enabled':False,'ref':None} if kind in native['native'] else
                    dict(control,ref=frame.wrap(control.get('ref'))))
            native['blocking_errors'].extend(child['blocking_errors'])
            native['auth']=native.get('auth') or child.get('auth')
        native['application_frames']={'count':len(router.frames),'diagnostics':router.diagnostics}
        shared=_merge_writers(shared,writers,router.diagnostics)
    return dict(shared,**native,simplify_inventory=simplify_inventory)


def _merge_writers(root, children, diagnostics):
    merged=dict(root)
    documents=[root]+[value for _,value in children]
    priorities=('active','unknown','login_required','needs_review','ready','complete','unsupported','missing')
    merged['status']=next(status for status in priorities if any(d.get('status')==status for d in documents))
    merged['panel']=any(d.get('panel') for d in documents)
    merged['writer_safe']=all(d.get('writer_safe') for d in documents)
    merged['activity']={key:any(d.get('activity',{}).get(key) for d in documents)
                        for key in ('busy_indicator','explicit_writer','waiting_for_input')}
    merged['source']='fixture' if any(d.get('source')=='fixture' for d in documents) else root.get('source','observed_dom')
    merged['application_frames']=[{'frame_id':frame.frame_id,'document':frame.nonce,
        **{k:value.get(k) for k in ('fingerprint','page_signature','page_ref','status')}} for frame,value in children]
    merged['frame_diagnostics']=list(diagnostics)
    return merged


async def observe_writers(page,package):
    """The quiescence gate accounts for every accepted application document."""
    from .simplify_boundary import SimplifyBoundary
    from .managed_context import platform_for_url
    from .cdp_client import CDPPage
    root=await SimplifyBoundary(page,budget_seconds=5).observe()
    if platform_for_url(package['job']['url'])=='workday' or not isinstance(page,CDPPage):return root
    from .browser_frames import router_for
    router=await router_for(page,package)
    router.frames.clear();router.diagnostics.clear()
    await router.discover()
    children=[]
    for frame in router.frames.values():children.append((frame,await SimplifyBoundary(frame,budget_seconds=5).observe()))
    return _merge_writers(root,children,router.diagnostics)


def inventory(observed, package):
    from .workday_fast import screen_inventory
    result=screen_inventory(observed,package)
    result['instruction']='Use observed refs with browser select, check, fill, press or click. Values come from approved profile facts. Use browser submit for the final action; it captures confirmation before closing.'
    profile=package['attempt'].get('profile_json') or {}
    if isinstance(profile,str):profile=json.loads(profile)
    result['answer_policy']=profile.get('application_answer_policy',{})
    if 'application_frames' in observed:result['application_frames']=observed['application_frames']
    return result


async def form_action(page, params):
    """Set a specific value, then verify it. A repeated check never toggles off."""
    method=params['method']
    target={k:params[k] for k in ('ref','selector') if params.get(k)}
    if not target:raise ValueError('observed_control_required')
    from .browser_frames import resolve_control,FrameUnavailable
    try:page,target=await resolve_control(page,target)
    except FrameUnavailable as exc:
        return {'committed':False,'execution':'not_executed','reason':str(exc)}
    before=await page.evaluate_function(FORM,dict(target,method='inspect'))
    if before.get('reason'):return before
    async def command(operation, **values):
        return await page.evaluate_function(FORM,dict(target,method=operation,**values))
    async def click(ref=None):
        args={'ref':ref} if ref else dict(target)
        args['expected_url']=await page.evaluate('location.href')
        return await page.click_observed(POINTER,args)
    if method=='press':
        focused=await command('focus')
        if not focused.get('committed'):return {'committed':False,'reason':'control_focus_unconfirmed'}
        await page.press_key(params['key']);return {'pressed':True}
    if method=='fill':
        result=await command('fill',value=params.get('value'))
        await asyncio.sleep(.15)
        after=await command('inspect')
        result['committed']=bool(result.get('committed') and after.get('value')==params.get('value'))
        return result
    if method=='check':
        desired=params.get('value',True)
        result=await command('check',value=desired)
        if result.get('needs_click'):
            activated=await click()
            if not activated.get('clicked'):return activated
            await asyncio.sleep(.15)
            result=await command('check',value=desired)
        return result
    if method!='select':raise ValueError('unsupported_form_operation')
    supplied={k:params[k] for k in ('value','label') if k in params}
    if not supplied or any(not isinstance(v,str) for v in supplied.values()):raise ValueError('exact_option_required')
    wanted=params.get('label',params.get('value'))
    if before.get('expanded')!='true' and wanted in (before.get('value'),before.get('label')):
        return {'committed':True,'unchanged':True,'value':before.get('value'),'label':before.get('label')}
    if before['tag']=='SELECT':
        result=await command('select_native',**supplied)
        if not result.get('committed'):return result
        await asyncio.sleep(.15)
        return await command('verify_select',value=result['value'],label=result['label'])
    # Workday, Greenhouse and custom ARIA comboboxes use the same association rules.
    if before.get('role')!='combobox' and before.get('haspopup') not in ('listbox','true','menu'):
        return {'committed':False,'reason':'select_control_unrecognized'}
    if before.get('expanded')!='true':
        activated=await click()
        if not activated.get('clicked'):return activated
    for attempt in range(8):
        options=await command('select_options')
        matches=[o for o in options.get('options',[]) if o['enabled'] and
                 (o['label']==wanted if 'label' in params else o['value']==wanted or o['label']==wanted)]
        if len(matches)>1:return {'committed':False,'reason':'ambiguous_option'}
        if len(matches)==1:
            result=await click(matches[0]['ref'])
            if not result.get('clicked'):return result
            await asyncio.sleep(.2)
            return await command('verify_select',value=matches[0]['value'],label=matches[0]['label'])
        if attempt==0 and before['tag']=='INPUT':
            await command('fill',value=wanted)
        await asyncio.sleep(.15)
    return {'committed':False,'reason':options.get('reason','option_not_found'),
            'options':options.get('options',[])}


async def inspect_control(page,target):
    from .browser_frames import resolve_control,FrameUnavailable
    try:
        document,local=await resolve_control(page,target)
        return await document.evaluate_function(FORM,dict(local,method='inspect'))
    except FrameUnavailable as exc:
        return {'committed':False,'execution':'not_executed','reason':str(exc)}


async def click_control(page,target,**checks):
    from .browser_frames import resolve_control,FrameUnavailable
    try:
        document,local=await resolve_control(page,target)
        return await document.click_observed(POINTER,dict(local,**checks,expected_url=await document.evaluate('location.href')))
    except FrameUnavailable as exc:
        return {'clicked':False,'execution':'not_executed','reason':str(exc)}


async def upload_file(page,target,path):
    """Route the already approved asset to one observed file input."""
    from .browser_frames import resolve_control,_remote,_owner_call,FrameUnavailable
    from .cdp_client import CDPElement
    document,local=await resolve_control(page,target)
    if local.get('selector'):
        selector=local['selector']
        if await document.evaluate_function('(s)=>document.querySelectorAll(s).length',selector)!=1:
            raise FrameUnavailable('ambiguous_or_stale_control')
        expression='document.querySelector('+json.dumps(selector)+')'
    else:
        expression='window.__jobbotFormScope?.inventory.get('+json.dumps(local['ref'])+')'
    owner=await _remote(document,expression)
    if not owner:raise FrameUnavailable('file_control_unavailable')
    valid=await _owner_call(document,owner,"function(){return this.isConnected&&this.type==='file'&&!this.disabled}")
    if not valid:raise FrameUnavailable('file_control_unavailable')
    await CDPElement(document._session,owner).set_input_files(str(path))


async def required_questions(page,refs,*,include_answered=False):
    """Capture offered choices from actual controls; a failed control is not a missing fact."""
    from .browser_frames import resolve_control,FramePage
    from .managed_questions import question_data
    if not isinstance(refs,list) or not 1<=len(refs)<=50 or any(not isinstance(r,str) for r in refs):
        raise ValueError('observed_question_refs_required')
    result={'questions':[],'skipped':[]}
    for ref in dict.fromkeys(refs):
        document,target=await resolve_control(page,{'ref':ref})
        info=await document.evaluate_function(FORM,dict(target,method='inspect'))
        if info.get('reason'):
            result['skipped'].append({'ref':ref,'reason':info['reason']});continue
        question=await document.evaluate_function(FORM,dict(target,method='question'))
        if question.get('reason') or not question.get('required') or (question.get('answered') and not include_answered):
            result['skipped'].append({'ref':ref,'reason':question.get('reason') or ('already_answered' if question.get('answered') else 'optional_question')});continue
        if question['kind']=='select' and info['tag']!='SELECT':
            opened=info.get('expanded')!='true'
            if opened:
                clicked=await click_control(page,{'ref':ref})
                if not clicked.get('clicked'):
                    result['skipped'].append({'ref':ref,'reason':clicked.get('reason','control_unavailable')});continue
            options={}
            for _ in range(8):
                options=await document.evaluate_function(FORM,dict(target,method='select_options'))
                if options.get('options'):break
                await asyncio.sleep(.1)
            if not options.get('options'):
                result['skipped'].append({'ref':ref,'reason':options.get('reason','observed_options_unavailable')});continue
            question['options']=[o for o in options['options'] if o['enabled']]
            if opened:await document.press_key('Escape')
        option_refs={(o['value'],o['label']):(document.wrap(o['ref']) if isinstance(document,FramePage) else o['ref'])
                     for o in question['options'] if o.get('ref')}
        data=question_data(**{k:question[k] for k in ('field','question','kind','required','context')},
                           options=[{k:o[k] for k in ('value','label')} for o in question['options']])
        result['questions'].append({'ref':ref,'data':data,'option_refs':option_refs})
    return result


async def simplify_document(page,*,ref=None,operation=None):
    """Resolve one extension control/document beneath the shared browser API."""
    from .browser_frames import resolve_control,router_for,FrameUnavailable
    from .cdp_client import CDPPage
    from .managed_context import platform_for_url
    from .simplify_boundary import OBSERVE
    if ref:
        document,local=await resolve_control(page,{'ref':ref})
        observed=await document.evaluate(OBSERVE)
        control=next((c for c in observed.get('inventory',[]) if c['ref']==local['ref']),None)
        if not control:raise FrameUnavailable('simplify_control_stale')
        if operation and control['operation']!=operation:raise FrameUnavailable('simplify_operation_mismatch')
        return document,observed,control
    documents=[page]
    package=getattr(page,'application_package',None)
    if isinstance(page,CDPPage) and package and platform_for_url(package['job']['url'])!='workday':
        router=await router_for(page)
        if not router.frames:await router.discover()
        documents+=list(router.frames.values())
    observed=[(document,await document.evaluate(OBSERVE)) for document in documents]
    choices=[(document,value) for document,value in observed
        if value.get('controls',{}).get(operation,{}).get('enabled') or value.get('status')=='active']
    if len(choices)>1:raise FrameUnavailable('ambiguous_simplify_document_use_observed_ref')
    document,value=choices[0] if choices else observed[0]
    return document,value,None
