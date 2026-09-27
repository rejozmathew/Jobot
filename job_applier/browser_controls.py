"""Shared form operations on the existing owned target; no ATS execution engine."""
import asyncio
import json
from pathlib import Path

ROOT=Path(__file__).parent/'browser_helpers'
FORM=(ROOT/'form_controls.js').read_text(encoding='utf-8')
POINTER=(ROOT/'workday_click.js').read_text(encoding='utf-8')


def next_operation(platform, observed=None, *, identity=None, quiescent=None, settings=None):
    """Actionable guidance from actual readiness; all actions retain their own guards."""
    observed=observed or {};status=observed.get('status')
    if identity and identity.get('status')!='same_job':
        return {'operation':'browser','parameters':{'method':'snapshot'},
                'instruction':'Inspect the owned page controls and identity evidence. Recover the observed application route before retrying a form action; this helper result does not end the application.'}
    if quiescent is False:
        if status=='unknown':
            from .form_audit import recovery
            return recovery(observed)
        return {'operation':'browser_observe','parameters':{},
                'instruction':'Observe active work or use the enabled Stop/Cancel; do not write concurrently.'}
    from .simplify_boundary import initial_autofill
    if isinstance(settings,str):settings=json.loads(settings)
    first=initial_autofill(observed) if (settings or {}).get('autofill')!='native' else None
    if first:
        return {'operation':'browser','parameters':{'method':'simplify','action':'autofill',**({'ref':first['ref']} if first.get('ref') else {})},
                'instruction':'Run Simplify Autofill on this form step, wait for settlement, then use the portal helper for residual work. Inspect and recover individual controls if the helper hands back.'}
    if platform=='icims':
        return {'operation':'icims_advance','parameters':{'seconds':60},
                'instruction':('Continue iCIMS using the selected native strategy; audit and repair observed fields. A helper handoff is resumable.' if (settings or {}).get('autofill')=='native' else
                    'Continue iCIMS: open the application or authenticate as needed, run initial Simplify Autofill, then audit and repair residual fields. A helper handoff is resumable.')}
    if platform=='workday':
        return {'operation':'fast_forward','parameters':{'seconds':60},
                'instruction':'Continue the owned Workday application with its routine runner.'}
    if platform=='greenhouse' or observed.get('greenhouse'):
        return {'operation':'greenhouse_advance','parameters':{'seconds':60},
                'instruction':'Batch the owned Greenhouse form with Simplify and approved residual answers; return one grouped answer plan for unresolved questions and resume this operation.'}
    if status=='unknown':
        from .form_audit import recovery
        return recovery(observed)
    if status=='active':
        return {'operation':'browser_observe','parameters':{},
                'instruction':'Observe the current writer until it settles. Inspect an unusable page with the shared recovery controls.'}
    if platform=='linkedin':
        route=observed.get('linkedin',{})
        if route.get('kind')=='easy_apply':
            return {'operation':'linkedin_easy_apply','parameters':{'seconds':60},
                    'instruction':'Batch the confirmed Easy Apply form in this owned session; resolve returned questions and resume.'}
        control=route.get('apply') or {}
        if route.get('kind')=='external' and control.get('enabled'):
            return {'operation':'browser','parameters':{'method':'click','ref':control['ref']},
                    'instruction':'Follow the observed external Apply through the existing correlated employer target handoff and ATS handler.'}
        return {'operation':'browser','parameters':{'method':'snapshot'},
                'instruction':'Inspect the assigned LinkedIn job. A missing employer URL does not establish Easy Apply. Follow login or current application evidence.'}
    for action in ('continue',):
        if observed.get('controls',{}).get(action,{}).get('enabled'):
            return {'operation':'browser','parameters':{'method':'simplify','action':action},
                    'instruction':('Start enabled Autofill now; inspect remaining questions after filling settles.' if action=='autofill' else
                                   'Use enabled Continue and inspect the next application step.')}
    if status in ('complete','needs_review','unsupported'):
        return {'operation':'browser','parameters':{'method':'snapshot'},
                'instruction':'Read audit: handle required_missing, invalid_blockers and credential_tasks, ignore optional_ignored and stale Simplify review items, then use the enabled native next action. Preserve existing answers.'}
    return {'operation':'browser_observe','parameters':{},
            'instruction':'Read the owned page and Simplify controls, then follow the returned next operation.'}


async def observe(page, package):
    from .managed_context import platform_for_url
    if platform_for_url(await page.evaluate('location.href'))=='workday':
        from .workday_fast import observe_page
        return await observe_page(page,package)
    from .simplify_boundary import OBSERVE
    if platform_for_url(package['job']['url'])=='linkedin' and platform_for_url(await page.evaluate('location.href'))=='linkedin':
        from .linkedin_easy_apply import observe_page
        native=await observe_page(page,package)
        return dict(await page.evaluate(OBSERVE),**native)
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
            writer['audit_document_id']=child.get('document_id','document')
            for field in child['inventory']:
                field['ref']=frame.wrap(field['ref']);field['document']=frame.wrap('document');field['document_id']=frame.wrap(field.get('document_id','document'))
                native['inventory'].append(field)
            for kind,control in child['native'].items():
                native['native'][kind]=({'enabled':False,'ref':None} if kind in native['native'] else
                    dict(control,ref=frame.wrap(control.get('ref'))))
            native['blocking_errors'].extend(child['blocking_errors'])
            for key in ('coverage_diagnostics','validation_summary'):native.setdefault(key,[]).extend(child.get(key,[]))
            if child.get('stage',{}).get('name') not in (None,'unknown'):native['stage']=child['stage']
            native['auth']=native.get('auth') or child.get('auth')
            if not native.get('job_metadata') and child.get('job_metadata'):native['job_metadata']=child['job_metadata']
            for group in child.get('verification',{}).get('groups',[]):
                native.setdefault('verification',{}).setdefault('groups',[]).append(dict(group,
                    refs=[frame.wrap(ref) for ref in group['refs']],
                    **({'resend_ref':frame.wrap(group['resend_ref'])} if group.get('resend_ref') else {})))
        native['application_frames']={'count':len(router.frames),'diagnostics':router.diagnostics}
        # The panel may live in the parent while the form advances inside an
        # accepted application iframe. Bind its receipt to those logical steps.
        hints=sorted([[w.get('writer_document_id'),w.get('autofill_page_key') or w.get('page_signature')]
                      for _,w in writers],key=lambda item:str(item[0]))
        await page.evaluate_function('(steps)=>{window.__jobbotApplicationSteps=steps}',hints)
        shared=await page.evaluate(OBSERVE)
        shared=_merge_writers(shared,writers,router.diagnostics)
    result=dict(shared,**native,simplify_inventory=simplify_inventory)
    return result


async def wait_for_page_recovery(page,package,*,seconds=12):
    """Return fresh application evidence after navigation, not DOM-ready alone."""
    deadline=asyncio.get_running_loop().time()+seconds;observed={};error_samples=0
    while asyncio.get_running_loop().time()<deadline:
        try:
            observed=await observe(page,package)
            error_samples=error_samples+1 if observed.get('refresh_error') else 0
            extension=any(c.get('enabled') for c in observed.get('controls',{}).values())
            native=observed.get('auth') or any(c.get('enabled') for c in observed.get('native',{}).values())
            if not error_samples and (extension or native):
                return {'status':'recovered','screen':inventory(observed,package),
                    'instruction':'The refreshed page has usable controls. Continue the application from this fresh screen. Do not reload or restart again for the old error.'}
            if error_samples>=2:
                return {'status':'error_present','screen':inventory(observed,package),
                    'instruction':'The current page still displays the refresh error. Choose further recovery using this new evidence.'}
        except Exception:
            pass  # Navigation can temporarily remove the execution context.
        await asyncio.sleep(.3)
    return {'status':'loading','screen':inventory(observed,package) if observed else None,
        'instruction':'The page is still initializing; the old error is not evidence of a new failure. Wait and inspect this same page. A missing panel immediately after reload does not justify another reload, restart or finish.'}


def _merge_writers(root, children, diagnostics):
    merged=dict(root)
    documents=[root]+[value for _,value in children]
    merged['autofill_candidates']=[]
    for frame,value in [(None,root)]+children:
        control=value.get('controls',{}).get('autofill',{})
        receipt=value.get('autofill_receipt') or {}
        if control.get('enabled') and control.get('ref'):
            merged['autofill_candidates'].append(dict(control,
                ref=frame.wrap(control['ref']) if frame else control['ref'],
                attempted=bool(value.get('autofill_attempted') or receipt.get('automatic_count',receipt.get('dispatch_count',0)) or receipt.get('repairs_started')),
                page_key=value.get('autofill_page_key'),document_id=value.get('writer_document_id')))
    settled=any(d.get('terminal_evidence') or d.get('settled_evidence') for d in documents)
    # Unrecognized decoration is not a participant. Pending writers remain relevant.
    relevant=[d for d in documents if not (settled and d.get('status')=='unknown' and
              d.get('writer_participant') is False and not d.get('writer_pending'))]
    relevant=relevant or documents
    priorities=('active','unknown','login_required','needs_review','ready','complete','unsupported','missing')
    merged['status']=next(status for status in priorities if any(d.get('status')==status for d in relevant))
    merged['panel']=any(d.get('panel') for d in documents)
    merged['writer_pending']=any(d.get('writer_pending') for d in documents)
    merged['writer_safe']=not merged['writer_pending'] and all(d.get('writer_safe') or d.get('settled_evidence') for d in relevant)
    merged['settled_evidence']=settled and not merged['writer_pending'] and not any(d.get('status')=='active' for d in documents)
    merged['writer_documents']=[{'document_id':d.get('writer_document_id'),
        'pending':bool(d.get('writer_pending')),'participant':bool(d.get('writer_participant')),
        'settled':bool(d.get('settled_evidence') or d.get('terminal_evidence'))} for d in documents]
    merged['activity']={key:any(d.get('activity',{}).get(key) for d in documents)
                        for key in ('busy_indicator','explicit_writer','waiting_for_input')}
    merged['source']='fixture' if any(d.get('source')=='fixture' for d in documents) else root.get('source','observed_dom')
    merged['application_frames']=[{'frame_id':frame.frame_id,'document':frame.nonce,
        **{k:value.get(k) for k in ('fingerprint','page_signature','page_ref','status','writer_document_id','writer_pending')}} for frame,value in children]
    merged['frame_diagnostics']=list(diagnostics)
    merged['review_items']=list(root.get('review_items',[]))+[
        {'label':item if isinstance(item,str) else item['label'],'document_id':frame.wrap(value.get('audit_document_id','document'))}
        for frame,value in children for item in value.get('review_items',[])]
    counts=[d.get('review_count') for d in documents if isinstance(d.get('review_count'),int)]
    if counts:merged['review_count']=sum(counts)
    return merged


async def observe_writers(page,package):
    """The quiescence gate accounts for every accepted application document."""
    from .simplify_boundary import SimplifyBoundary
    from .managed_context import platform_for_url
    from .cdp_client import CDPPage
    async def read(document):
        value=await SimplifyBoundary(document,budget_seconds=5).observe()
        if value.get('greenhouse'):
            scope={'attempt_id':package.get('attempt',{}).get('id'),'target_id':getattr(page,'target_id',None)}
            if scope['attempt_id'] is not None:
                value=await SimplifyBoundary(document,budget_seconds=5,scope=scope).observe()
            if value.get('autofill_receipt',{}).get('state') in ('dispatching','dispatched','active','uncertain'):
                value=dict(value,status='active',writer_safe=False)
        return value
    if platform_for_url(package['job']['url'])=='linkedin' and platform_for_url(await page.evaluate('location.href'))=='linkedin':
        from .linkedin_easy_apply import observe_page
        native=await observe_page(page,package)
        return dict(await read(page),**native)
    root=await read(page)
    if platform_for_url(package['job']['url'])=='workday' or not isinstance(page,CDPPage):return root
    from .browser_frames import router_for
    router=await router_for(page,package)
    router.frames.clear();router.diagnostics.clear()
    await router.discover()
    children=[]
    for frame in router.frames.values():children.append((frame,await read(frame)))
    return _merge_writers(root,children,router.diagnostics)


def remaining_submission_work(observed):
    """Describe visible unfinished work without inferring unknown field values."""
    from .form_audit import classify
    required=[dict(f) for f,state,mandatory,present,members in classify(observed)
              if mandatory and state in ('missing','credential','invalid')]
    groups=[g for g in observed.get('verification',{}).get('groups',[]) if g.get('complete') is False]
    return {'required_fields':required,'verification_groups':groups,'errors':observed.get('blocking_errors',[])}



def inventory(observed, package):
    from .workday_fast import screen_inventory
    result=screen_inventory(observed,package)
    result['next_operation']=next_operation(package.get('platform'),observed,settings=package.get('attempt',{}).get('settings_json'))
    if observed.get('verification',{}).get('groups'):result['verification']=observed['verification']
    settings=package.get('attempt',{}).get('settings_json') or {}
    if isinstance(settings,str):settings=json.loads(settings)
    strategy=('Use the selected native filling strategy and respect any active writer. ' if settings.get('autofill')=='native' else
        'Open the application and handle access/login if needed; on every accessible form step run available Simplify Autofill first and wait for settlement. ')
    result['instruction']=(strategy+'Use helpers for residual work, followed by field-by-field assessment and actual screenshot inspection/recovery. '
        'Use observed refs with browser select, check, fill, press or click. Values come from approved facts or explicit user choices. '
        'Use browser repair with fields:[{method:fill|select|check,ref,value}] to fix routine fields together and return verified results plus a fresh screen. '
        'Upload uses method:upload,ref,asset_id from selected_documents. Complete required questions using answer_context.standard_answers, answer_context.identity, approved profile facts and saved answers before requesting human input. '
        'A helper mismatch or failed selection is a recovery handoff, not an application outcome. Inspect actual options, refresh stale controls, '
        'if an expected control is missing, take and visually inspect an owned screenshot immediately, inspect embedded frames and scroll containers, then try another supported interaction. '
        'Before concluding that recovery is exhausted, inspect a fresh screenshot and attempt the remaining plausible actions. Keep the session open and continue after progress. '
        'Missing Simplify or an unusable page calls for browser_recovery: inspect loading, reload when appropriate, restart if needed and continue. '
        'Use browser submit for the final action; it captures confirmation before closing.')
    profile=package['attempt'].get('profile_json') or {}
    if isinstance(profile,str):profile=json.loads(profile)
    identity=profile.get('identity') or {}
    result['answer_context']['identity']={k:identity[k] for k in (
        'first_name','last_name','full_name','email','phone','location','linkedin','website') if k in identity}
    address=identity.get('address')
    if isinstance(address,dict):
        result['answer_context']['identity']['address']={k:address[k] for k in (
            'street','address_line1','address_line2','city','state','zip','postal_code','country') if k in address}
    report=result['audit']
    residuals={f['ref']:f for f in report['required_missing']+report['invalid_blockers'] if f['required']}
    result['remaining_required']=[dict(residuals[f['ref']],state='missing' if residuals[f['ref']]['presence']=='missing' else 'invalid')
        for f in observed.get('inventory',[]) if f.get('ref') in residuals]
    result['credential_tasks']=report['credential_tasks']
    result['supported_operations']={
        'repair':{'method':'repair','fields':[{'method':'fill|select|check','ref':'<observed ref>','value':'<approved value>'}]},
        'upload':{'method':'upload','ref':'<observed file ref>','asset_id':'<selected asset id>'},
        'snapshot':{'method':'snapshot'}}
    result['selected_documents']=[{k:asset.get(k) for k in ('id','kind','version')} for asset in package.get('documents',{}).get('assets',[])]
    result['answer_policy']=profile.get('application_answer_policy',{})
    if 'application_frames' in observed:result['application_frames']=observed['application_frames']
    return result


async def repair_fields(page, fields, *, checkpoint=None):
    """Group existing typed operations; preserve individual verification/failures."""
    if not isinstance(fields,list) or any(not isinstance(f,dict) or f.get('method') not in ('fill','select','check')
        or not isinstance(f.get('ref'),str) or not f['ref'] for f in fields):
        raise ValueError('repair_requires_observed_typed_fields')
    result={'fields':[],'remaining':[]}
    for index,field in enumerate(fields):
        try:
            if checkpoint:await checkpoint()
            applied=await form_action(page,field,**({'checkpoint':checkpoint} if checkpoint else {}))
        except (ValueError,TimeoutError) as exc:
            result.update(reason=str(exc),remaining=fields[index:])
            break
        result['fields'].append({'ref':field['ref'],'method':field['method'],**applied})
    return result


async def form_action(page, params, *, checkpoint=None, deadline=None):
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
    async def check():
        if deadline is not None and asyncio.get_running_loop().time()>=deadline:raise TimeoutError('call_slice_complete')
        if checkpoint:await checkpoint()
    async def pause(seconds):
        await asyncio.sleep(seconds)
        await check()
    async def command(operation, **values):
        await check()
        return await page.evaluate_function(FORM,dict(target,method=operation,**values))
    async def click(ref=None):
        await check()
        if not ref:
            refreshed=await command('inspect')
            if refreshed.get('reason'):return dict(refreshed,clicked=False)
        args={'ref':ref} if ref else dict(target)
        args['expected_url']=await page.evaluate('location.href')
        return await page.click_observed(POINTER,args)
    async def verify_selection(value=None,label=None):
        previous=None;stable=0;result={}
        # Rerendered controls are reacquired by their unique saved descriptor.
        # Two matching reads avoid treating a transient input update as a commit.
        for _ in range(30):
            result=await command('verify_select',value=value,label=label)
            signature=(result.get('value'),result.get('label'))
            stable=stable+1 if result.get('committed') and signature==previous else int(bool(result.get('committed')))
            if stable>=2:return dict(result,execution='executed')
            previous=signature
            await pause(.1)
        options=await command('select_options')
        return dict(result,committed=False,execution='executed',reason=result.get('reason') or 'selection_mismatch',
                    options=options.get('options',[]))
    if method=='press':
        focused=await command('focus')
        if not focused.get('committed'):return {'committed':False,'reason':'control_focus_unconfirmed'}
        await page.press_key(params['key'])
        if 'label' in params or 'value' in params:
            return dict(await verify_selection(params.get('value'),params.get('label',params.get('value'))),pressed=True)
        return {'pressed':True,'execution':'executed','answer_verified':False}
    if method=='fill':
        result=await command('fill',value=params.get('value'))
        await pause(.05)
        after=await command('inspect')
        result['committed']=bool(result.get('committed') and after.get('value')==params.get('value') and not after.get('validation',{}).get('rejected'))
        return result
    if method=='check':
        desired=params.get('value',True)
        result=await command('check',value=desired)
        if result.get('needs_click'):
            activated=await click()
            if not activated.get('clicked'):return activated
            await pause(.05)
            result=await command('check',value=desired)
        return result
    if method!='select':raise ValueError('unsupported_form_operation')
    supplied={k:params[k] for k in ('value','label') if k in params}
    if not supplied or any(not isinstance(v,str) and not (before.get('type')=='select-multiple' and
        isinstance(v,list) and all(isinstance(item,str) for item in v)) for v in supplied.values()):raise ValueError('exact_option_required')
    wanted=params.get('label',params.get('value'))
    if wanted in (before.get('value'),before.get('label')):
        return dict(await verify_selection(params.get('value',before.get('value')),params.get('label',before.get('label'))),unchanged=True)
    if before['tag']=='SELECT':
        result=await command('select_native',**supplied)
        if not result.get('committed'):return result
        return await verify_selection(result['value'],result['label'])
    # Workday, Greenhouse and custom ARIA comboboxes use the same association rules.
    if before.get('role')!='combobox' and before.get('haspopup') not in ('listbox','true','menu'):
        return {'committed':False,'reason':'select_control_unrecognized'}
    if before.get('expanded')!='true':
        activated=await click()
        if not activated.get('clicked'):return activated
    from .managed_context import platform_for_url
    greenhouse=platform_for_url(await page.evaluate('location.href'))=='greenhouse' or 'id' in before
    for attempt in range(20):
        options=await command('select_options')
        matches=[o for o in options.get('options',[]) if o['enabled'] and
                 (o['label']==wanted if 'label' in params else o['value']==wanted or o['label']==wanted)]
        if len(matches)>1:return {'committed':False,'reason':'ambiguous_option'}
        if len(matches)==1:
            result=await click(matches[0]['ref'])
            if not result.get('clicked'):
                if result.get('execution')=='possibly_executed':return result
                # Reacquire a detached option from the same widget's fresh menu.
                if result.get('reason') in ('control_unavailable','control_changed_before_press','stale_control','control_not_found'):
                    await pause(.1);continue
                return result
            # LinkedIn input typeaheads expose their final label as input.value.
            # The document receipt distinguishes this observed option click from
            # an uncommitted typed search, without changing other ATS read-back.
            if platform_for_url(await page.evaluate('location.href'))=='linkedin':
                await command('selection_dispatched',option_ref=matches[0]['ref'],label=matches[0]['label'])
            return await verify_selection(matches[0]['value'],matches[0]['label'])
        if attempt==0 and before['tag']=='INPUT':
            await command('search' if greenhouse else 'fill',value=wanted)
        if attempt==2 and greenhouse and before['tag']=='INPUT' and hasattr(page,'insert_text'):
            focused=await command('focus')
            if focused.get('committed'):
                await page.press_key('Control+A')
                await check()
                await page.insert_text(wanted)
        await pause(.1)
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


async def required_questions(page,refs,*,include_answered=False,include_optional=False,checkpoint=None):
    """Capture offered choices from actual controls; a failed control is not a missing fact."""
    from .browser_frames import resolve_control,FramePage
    from .managed_questions import question_data
    if not isinstance(refs,list) or not 1<=len(refs)<=50 or any(not isinstance(r,str) for r in refs):
        raise ValueError('observed_question_refs_required')
    result={'questions':[],'skipped':[]}
    for ref in dict.fromkeys(refs):
        if checkpoint:await checkpoint()
        document,target=await resolve_control(page,{'ref':ref})
        info=await document.evaluate_function(FORM,dict(target,method='inspect'))
        if info.get('reason'):
            result['skipped'].append({'ref':ref,'reason':info['reason']});continue
        question=await document.evaluate_function(FORM,dict(target,method='question'))
        if question.get('reason') or (not question.get('required') and not include_optional) or (question.get('answered') and not include_answered):
            result['skipped'].append({'ref':ref,'reason':question.get('reason') or ('already_answered' if question.get('answered') else 'optional_question')});continue
        if question['kind']=='select' and info['tag']!='SELECT':
            opened=info.get('expanded')!='true'
            if opened:
                await document.evaluate_function(FORM,dict(target,method='begin_menu_inspection'))
                clicked=await click_control(page,{'ref':ref})
                if not clicked.get('clicked'):
                    result['skipped'].append({'ref':ref,'reason':clicked.get('reason','control_unavailable')});continue
            try:
                options={}
                for _ in range(8):
                    options=await document.evaluate_function(FORM,dict(target,method='select_options'))
                    if options.get('options'):break
                    await asyncio.sleep(.1)
                    if checkpoint:await checkpoint()
                if not options.get('options'):
                    result['skipped'].append({'ref':ref,'reason':options.get('reason','observed_options_unavailable')});continue
                question['options']=[o for o in options['options'] if o['enabled']]
            finally:
                if opened:
                    # FramePage validates the original document; root refs belong
                    # to that document's scope and cannot bind after a reload.
                    await document.evaluate_function(FORM,dict(target,method='close_menu'))
        option_refs={(o['value'],o['label']):(document.wrap(o['ref']) if isinstance(document,FramePage) else o['ref'])
                     for o in question['options'] if o.get('ref')}
        data=question_data(**{k:question[k] for k in ('field','question','kind','context')},required=True,
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
        if operation and control['operation']!=operation:
            # Workday also labels the panel tab "Autofill". An explicit page-fill
            # request can recover to its unique observed "Autofill This Page"
            # button in this same document; other ATS/ref mappings stay strict.
            actual=observed.get('controls',{}).get('autofill',{})
            replacement=next((c for c in observed.get('inventory',[]) if c['ref']==actual.get('ref')),None)
            if observed.get('workday') and operation=='autofill' and actual.get('enabled') and replacement:
                control=dict(replacement,recovery='resolved_workday_page_autofill')
            else:raise FrameUnavailable('simplify_operation_mismatch')
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
