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
    return dict(shared,**native,simplify_inventory=shared.get('inventory',[]))


def inventory(observed, package):
    from .workday_fast import screen_inventory
    result=screen_inventory(observed,package)
    result['instruction']='Use observed refs with browser select, check, fill, press or click. Values come from approved profile facts. Use browser submit for the final action; it captures confirmation before closing.'
    profile=package['attempt'].get('profile_json') or {}
    if isinstance(profile,str):profile=json.loads(profile)
    result['answer_policy']=profile.get('application_answer_policy',{})
    return result


async def form_action(page, params):
    """Set a specific value, then verify it. A repeated check never toggles off."""
    method=params['method']
    target={k:params[k] for k in ('ref','selector') if params.get(k)}
    if not target:raise ValueError('observed_control_required')
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
