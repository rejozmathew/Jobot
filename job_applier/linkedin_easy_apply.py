"""Native owned-page Easy Apply, adapted from GodsScion's MIT implementation.

Copyright (c) 2024-2026 Sai Vignesh Golla. See third_party/godsscion-linkedin
for the pinned source, license and adaptation map. No donor runner is imported.
"""
import asyncio
import json
from pathlib import Path
import re

from .application_answers import label_has, match_answer_to_option, approved_answer, answer_action, saved_answer
import time

from .browser_controls import FORM, form_action, click_control, upload_file
from .managed_identity import linkedin_identity, application_match

SCRIPT=(Path(__file__).parent/'browser_helpers/linkedin_observe.js').read_text(encoding='utf-8')
OBSERVE='(args)=>('+SCRIPT+')(args,('+FORM+'))'


async def observe_page(page,package):
    identity=linkedin_identity(package['job']['url'])
    return await page.evaluate_function(OBSERVE,{'job_id':identity[-1] if identity else None})


class EasyApplyRunner:
    """Batch routine work using Jobbot's existing writer lock and submission service."""
    def __init__(self,page,call,package,ownership,config,target_id):
        self.page,self.call,self.package,self.owner,self.config,self.target=page,call,package,ownership,config,target_id
        self.page.application_package=package
        self.profile=package['attempt'].get('profile_json') or {}
        self.settings=package['attempt'].get('settings_json') or {}
        if isinstance(self.profile,str):self.profile=json.loads(self.profile)
        if isinstance(self.settings,str):self.settings=json.loads(self.settings)

    def owned(self,op,**params):return self.call(op,**self.owner,**params)

    async def observe(self):
        from .browser_controls import observe
        return await observe(self.page,self.package)

    def report(self,status,observed,reason,**extra):
        from .browser_controls import inventory
        instruction=('Already-applied employer evidence was recorded. Report that existing outcome.' if status=='already_applied' else
            'The current application is ready for the configured review. Report it using the existing review workflow.' if status=='ready_for_review' else
            'Continue this same owned application. Resolve returned questions from approved facts or exact saved answers; use scoped browser recovery, then resume linkedin_easy_apply. A helper handoff is not a terminal outcome.')
        return {'status':status,'reason':reason,'screen':inventory(observed,self.package),**extra,
                'instruction':instruction}

    async def write(self,operation,callback):
        from .managed_shared import uid
        # The authoritative gate checks ownership, current page and all writers.
        gate=await asyncio.to_thread(self.owned,'browser_observe',target_id=self.target,cdp_url=self.config['cdp_url'])
        if not gate.get('native_takeover_authorized',gate.get('quiescent')):
            return {'committed':False,'reason':'writer_settlement_required','execution':'not_executed'}
        if application_match(self.package['job']['url'],await self.page.evaluate('location.href'))['status']!='same_job':
            return {'committed':False,'reason':'job_identity_unresolved','execution':'not_executed'}
        aid=uid();self.owned('action_start',action_id=aid,tool_name='linkedin_easy_apply.'+operation)
        result={};started=time.monotonic()
        try:
            result=await callback()
            return result
        finally:
            self.owned('action_end',action_id=aid,status='success' if result.get('committed') or result.get('clicked') else 'failed',duration_seconds=time.monotonic()-started)

    async def fill(self,observed):
        from .application_answers import apply_policy,capture_answers
        unfilled={q['ref'] for q in observed['linkedin']['questions'] if not q['answered']}
        result=await apply_policy(self.page,self.package,dict(observed,inventory=[f for f in observed['inventory'] if f['ref'] in unfilled]))
        failures=[f for f in result['fields'] if not f.get('committed')]
        for question in observed['linkedin']['questions']:
            if question['answered'] or not question.get('enabled'):continue
            answer=saved_answer(question,self.package)
            if answer is None:answer=approved_answer(question['question'],self.profile)
            if answer is None:continue
            action=answer_action(question,answer)
            if action is None:
                failures.append({'ref':question['ref'],'reason':'approved_answer_option_unmatched'});continue
            fresh=await self.observe()
            current=next((q for q in fresh['linkedin']['questions'] if q['ref']==question['ref'] and q['question']==question['question']),None)
            if fresh['page_signature']!=observed['page_signature'] or not current:
                failures.append({'ref':question['ref'],'reason':'step_changed'});break
            if current['answered']:continue
            # Recheck extension state within the batch without treating our own
            # serialized native action as a competing writer.
            if fresh.get('status') in ('active','unknown'):
                failures.append({'ref':question['ref'],'reason':'writer_settlement_required'});break
            written=await form_action(self.page,action)
            if not written.get('committed'):failures.append({'ref':question['ref'],'reason':written.get('reason','value_unconfirmed')})
        await capture_answers(self.page,self.config,self.package,self.owner,page='easy_apply',source='linkedin_easy_apply',basis='approved_profile_or_saved_answer',call=self.call)
        return {'committed':not failures,'failures':failures}

    async def resume(self,observed):
        from .managed_documents import local_asset_path
        assets=[a for a in self.package['documents']['assets'] if a['kind']=='resume']
        if len(assets)!=1:return {'committed':False,'reason':'selected_resume_unavailable'}
        asset=assets[0];path=local_asset_path(asset);route=observed['linkedin']
        selected=[r for r in route['resumes'] if r['selected']]
        def matches(card):
            if not re.search(r'(?<![\w.-])'+re.escape(path.name)+r'(?![\w.-])',card['text']):return False
            size=re.search(r'\b(\d+(?:\.\d+)?)\s*(KB|MB|bytes)\b',card['text'],re.I)
            if not size:return True
            amount=float(size[1]);unit=size[2].casefold();actual=path.stat().st_size
            # Portals round displayed sizes and use either decimal or binary KB.
            factors={'bytes':(1,), 'kb':(1000,1024), 'mb':(1000000,1048576)}[unit]
            return any(abs(actual-amount*factor)<=factor for factor in factors)
        if len(selected)==1 and matches(selected[0]):return {'committed':True,'unchanged':True}
        matching=[r for r in route['resumes'] if matches(r) and r['control'].get('ref')]
        uploaded=False
        if len(matching)==1:
            result=await form_action(self.page,{'method':'check','ref':matching[0]['control']['ref'],'value':True})
            if not result.get('committed'):return result
        else:
            inputs=route['file_inputs']
            if len(inputs)!=1:return {'committed':False,'reason':'resume_upload_control_unresolved'}
            self.owned('report_upload',asset_id=asset['id'],status='upload_attempted',evidence='Upload selected resume through owned LinkedIn input')
            await upload_file(self.page,{'ref':inputs[0]['ref']},path)
            uploaded=True
        for _ in range(12):
            fresh=(await self.observe())['linkedin']
            selected=[r for r in fresh['resumes'] if r['selected']]
            files=[f for i in fresh['file_inputs'] for f in i['files']]
            confirmed=(len(selected)==1 and matches(selected[0])) or (not fresh['resumes'] and any(f['name']==path.name and f['size']==path.stat().st_size for f in files))
            if confirmed:
                if uploaded:
                    self.owned('report_upload',asset_id=asset['id'],status='upload_confirmed',evidence='Selected LinkedIn resume matches approved filename and upload/selection evidence')
                return {'committed':True}
            await asyncio.sleep(.2)
        return {'committed':False,'reason':'selected_resume_unconfirmed'}

    async def run(self,seconds=60):
        deadline=time.monotonic()+seconds;previous=None
        while time.monotonic()<deadline:
            observed=await self.observe();route=observed.get('linkedin',{})
            if observed.get('auth'):return self.report('authentication_required',observed,'linkedin_login_required')
            if application_match(self.package['job']['url'],await self.page.evaluate('location.href'))['status']!='same_job':
                return self.report('inspection_required',observed,'job_identity_unresolved')
            if route.get('already_applied'):
                self.owned('finish',outcome='already_applied',evidence='employer: '+route['already_applied'],quiescent=False)
                return self.report('already_applied',observed,'observed_linkedin_applied',evidence=route['already_applied'],source='employer')
            if route.get('kind')!='easy_apply':return self.report('inspection_required',observed,'external_apply' if route.get('kind')=='external' else 'easy_apply_unconfirmed')
            if observed.get('status') in ('active','unknown'):return self.report('inspection_required',observed,'writer_settlement_required')
            if not route.get('modal'):
                control=route.get('apply',{})
                if not control.get('enabled'):return self.report('inspection_required',observed,'easy_apply_control_unavailable')
                if previous==observed['page_signature']:return self.report('inspection_required',observed,'modal_not_opened')
                result=await self.write('open',lambda:click_control(self.page,{'ref':control['ref']}))
            else:
                from .simplify_boundary import SimplifyBoundary,initial_autofill
                first=initial_autofill(observed) if self.settings.get('autofill')!='native' else None
                if first:
                    async def autofill():
                        from .browser_controls import simplify_document
                        from .managed_shared import ProtocolError
                        async def checkpoint():
                            pulse=self.owned('heartbeat')
                            if pulse.get('control','running')!='running':raise ProtocolError(pulse['control'])
                        document,_,_=await simplify_document(self.page,ref=first.get('ref'),operation='autofill')
                        result=await SimplifyBoundary(document,budget_seconds=max(.05,min(45,deadline-time.monotonic())),checkpoint=checkpoint).perform('autofill',automatic=True)
                        return dict(result,clicked=result.get('execution')=='clicked')
                    settled=await self.write('autofill',autofill)
                    if not settled.get('native_takeover_authorized'):
                        return self.report('continue',await self.observe(),'writer_settlement_required')
                    continue
                filled=await self.write('fill',lambda:self.fill(observed))
                if not filled.get('committed'):return self.report('inspection_required',await self.observe(),filled.get('reason','field_recovery'),fields=filled.get('failures',[]))
                observed=await self.observe();route=observed['linkedin']
                if route['file_inputs'] or route['resumes']:
                    resume=await self.write('resume',lambda:self.resume(observed))
                    if not resume.get('committed'):return self.report('inspection_required',await self.observe(),resume.get('reason','resume_recovery'))
                observed=await self.observe();route=observed['linkedin']
                questions=[q for q in route['questions'] if q['required'] and not q['answered']]
                if questions:return self.report('questions_required',observed,'unresolved_required_questions',questions=questions)
                if observed['blocking_errors']:return self.report('inspection_required',observed,'inline_validation',errors=observed['blocking_errors'])
                controls=observed['native']
                if controls.get('submit',{}).get('enabled'):
                    if self.settings.get('submission_mode')!='submit':return self.report('ready_for_review',observed,'configured_review_mode')
                    from .submission import submit
                    target={'ref':controls['submit']['ref']}
                    async def activate():
                        fresh=await self.observe()
                        if fresh['page_signature']!=observed['page_signature'] or not fresh['native'].get('submit',{}).get('enabled'):
                            return {'clicked':False,'execution':'not_executed','reason':'submit_control_changed'}
                        return await click_control(self.page,{'ref':fresh['native']['submit']['ref']})
                    return await submit(self.page,self.call,self.package,self.owner,self.config,self.target,activate,application_control=target)
                control=next((controls[k] for k in ('review','continue') if controls.get(k,{}).get('enabled')),None)
                if not control:return self.report('inspection_required',observed,'progress_control_unavailable')
                if previous==observed['page_signature']:return self.report('inspection_required',observed,'step_unchanged')
                result=await self.write('advance',lambda:click_control(self.page,{'ref':control['ref']}))
            if not result.get('clicked'):return self.report('inspection_required',await self.observe(),result.get('reason','control_unconfirmed'))
            previous=observed['page_signature']
            for _ in range(15):
                await asyncio.sleep(.2)
                fresh=await self.observe()
                if fresh['page_signature']!=previous or fresh['blocking_errors']:break
        return self.report('continue',await self.observe(),'call_slice_complete')


def advance(config,client,ownership,params):
    """Registered native operation: attach to the session target, never launch a browser."""
    from .cdp_client import CDPBrowser
    from .managed_shared import ProtocolError
    if set(params)-{'target_id','seconds'} or not params.get('target_id'):raise ProtocolError('invalid_linkedin_parameters')
    seconds=params.get('seconds',60)
    if type(seconds) not in (int,float) or not 0<seconds<=120:raise ValueError('bounded_seconds_required')
    package=client.call('application_context',attempt_id=ownership['attempt_id'],worker_id=ownership['worker_id'])
    if not linkedin_identity(package['job']['url']):raise ProtocolError('linkedin_job_required')
    # This authoritative observation also verifies the current target before any
    # connection or write; no last-tab selection or separate ownership store.
    client.call('browser_observe',**ownership,target_id=params['target_id'],cdp_url=config['cdp_url'])
    async def execute():
        browser=await CDPBrowser.connect(config['cdp_url'],target_id=params['target_id'],expected_mode=config.get('browser_mode','headed'))
        try:return await EasyApplyRunner(await browser.get_current_page(),client.call,package,ownership,config,params['target_id']).run(seconds)
        finally:await browser.close()
    return asyncio.run(execute())
