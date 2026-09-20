"""Thin, resumable iCIMS supervisor over existing owned form services. No model."""
import asyncio
import json
import time
from contextlib import asynccontextmanager

from .application_answers import approved_answer, answer_action, saved_answer
from .browser_controls import observe, observe_writers, repair_fields, required_questions, click_control, simplify_document, upload_file
from .browser_frames import FrameUnavailable
from .form_audit import audit, recovery
from .managed_questions import question_key
from .managed_shared import ProtocolError, uid
from .simplify_boundary import SimplifyBoundary


class IcimsRunner:
    def __init__(self,page,call,package,ownership,config,target_id,*,account_lock=None):
        self.page,self.call,self.package,self.owner,self.config,self.target=page,call,package,ownership,config,target_id
        self.page.application_package=package;self.account_lock=account_lock
        self.profile=package['attempt'].get('profile_json') or {};self.settings=package['attempt'].get('settings_json') or {}
        if isinstance(self.profile,str):self.profile=json.loads(self.profile)
        if isinstance(self.settings,str):self.settings=json.loads(self.settings)
        self.started=time.monotonic();self.deadline=None;self.last={};self.audit={};self.questions=[];self.failures=[]
        self.actions={'autofill':0,'credentials':0,'repair_fields':0,'stage_advance':0,'audits':0}
        self.trace=[];self.documents=None;self.aid=None

    def owned(self,op,**params):return self.call(op,**self.owner,**params)

    async def control(self):
        pulse=self.owned('heartbeat')
        if pulse.get('control','running')!='running':raise ProtocolError(pulse['control'])
        if self.deadline is not None and time.monotonic()>=self.deadline:raise TimeoutError('call_slice_complete')

    async def checkpoint(self):
        await self.control()
        writers=await observe_writers(self.page,self.package)
        documents=[d.get('document_id') for d in writers.get('writer_documents',[])] or [writers.get('writer_document_id')]
        if self.documents is not None and documents!=self.documents:raise FrameUnavailable('application_document_changed')
        if writers.get('status')=='active' or writers.get('writer_pending'):
            raise FrameUnavailable('writer_settlement_required')
        if writers.get('status')=='unknown' and writers.get('writer_participant') and not writers.get('settled_evidence'):
            raise FrameUnavailable('writer_settlement_required')

    async def read(self):
        await self.control()
        self.last=await observe(self.page,self.package)
        await self.control()
        self.audit=audit(self.last);self.actions['audits']+=1
        self.trace.append('audit:'+self.audit['stage']['name'])
        return self.audit

    async def gate(self):
        await self.control()
        gate=await asyncio.to_thread(self.owned,'browser_observe',target_id=self.target,cdp_url=self.config['cdp_url'])
        await self.control()
        if gate.get('identity',{}).get('status') not in (None,'same_job'):raise FrameUnavailable('owned_route_requires_inspection')
        writers=gate.get('observation',{})
        self.documents=[d.get('document_id') for d in writers.get('writer_documents',[])] or [writers.get('writer_document_id')]
        self.audit['writer']={'ui_status':gate.get('status'),'state':gate.get('writer_state'),
                              'native_takeover_authorized':bool(gate.get('native_takeover_authorized',gate.get('quiescent')))}
        return self.audit['writer']['native_takeover_authorized']

    @asynccontextmanager
    async def batch(self,name):
        if not await self.gate():raise FrameUnavailable('writer_settlement_required')
        self.aid=uid();start=time.monotonic();success=False
        self.owned('action_start',action_id=self.aid,tool_name='icims_fast.'+name)
        try:
            await self.checkpoint();yield;success=True
        finally:
            self.owned('action_end',action_id=self.aid,status='success' if success else 'failed',duration_seconds=time.monotonic()-start)
            self.aid=None

    def result(self,status,reason,**extra):
        return dict(handler='icims_fast',status=status,reason=reason,stage=self.audit.get('stage'),audit=self.audit,
            actions=self.actions,questions=self.questions,control_failures=self.failures,trace=self.trace,
            elapsed_seconds=round(time.monotonic()-self.started,3),
            next_operation=recovery(self.last) if reason=='writer_settlement_required' else
                {'operation':'icims_advance','parameters':{'seconds':60}},
            instruction='Continue this same owned application. Resolve the supplied grouped questions/control evidence and resume; helper slices and unsupported layouts are handoffs, not application outcomes.',**extra)

    async def credentials(self,task):
        params=task.get('next_operation',{}).get('parameters',{})
        if task['kind']!='employer_credentials' or not params:return False
        from .managed_credentials import fill_page_credentials,credential_progress
        if self.account_lock:self.account_lock()
        async with self.batch('credentials'):
            credential_progress(self.call,self.owner,params)
            result=await fill_page_credentials(self.config,self.package,self.page,params)
            await self.control()
            credential_progress(self.call,self.owner,params,result=result,action_id=self.aid)
            self.actions['credentials']+=1;self.trace.append('private_credentials')
        if not result.get('values_committed'):
            self.failures.append({'kind':'credentials','reason':result.get('error','credential_commit_unconfirmed')});return False
        return True

    async def repair(self,plans):
        from .application_answers import apply_policy, save_answer_history
        work=self.audit['required_missing']+self.audit['invalid_blockers'];actions=[];questions=[];seen=set();approved={};changed=False
        async with self.batch('repair'):
            # Reuse policy only for actual residuals. Optional blanks remain untouched.
            refs={f['ref'] for f in work}
            policy=await apply_policy(self.page,self.package,dict(self.last,inventory=[f for f in self.last.get('inventory',[]) if f.get('ref') in refs]),checkpoint=self.checkpoint,deadline=self.deadline)
            self.actions['repair_fields']+=len(policy['fields'])
            self.failures.extend(f for f in policy['fields'] if not f.get('committed'))
            if policy['changed']:
                changed=True;await self.read();work=self.audit['required_missing']+self.audit['invalid_blockers']
            for field in work:
                if field.get('type')=='file':
                    from .managed_documents import local_asset_path
                    resume=next((a for a in self.package.get('documents',{}).get('assets',[]) if a.get('kind')=='resume'),None)
                    if not resume or not any(w in field.get('label','').lower() for w in ('resume','cv')):
                        self.failures.append({'ref':field['ref'],'reason':'selected_resume_widget_requires_inspection'});continue
                    if field.get('attachment')=='rejected':
                        from .browser_controls import FORM
                        from .browser_frames import resolve_control,FramePage
                        document,_=await resolve_control(self.page,{'ref':field['ref']})
                        widget=await document.evaluate_function(FORM,{'method':'resume_widget'})
                        wrap=document.wrap if isinstance(document,FramePage) else lambda ref:ref
                        if widget.get('reason') or not widget.get('required_error'):
                            self.failures.append({'ref':field['ref'],'reason':'resume_widget_requires_inspection'});continue
                        if widget.get('remove_ref'):
                            await self.checkpoint()
                            removed=await click_control(self.page,{'ref':wrap(widget['remove_ref'])})
                            if not removed.get('clicked'):
                                self.failures.append({'ref':field['ref'],'reason':'resume_remove_unconfirmed'});continue
                            widget=await document.evaluate_function(FORM,{'method':'resume_widget'})
                        if not widget.get('input_ref'):
                            self.failures.append({'ref':field['ref'],'reason':'resume_upload_control_unresolved'});continue
                        field=dict(field,ref=wrap(widget['input_ref']))
                    await self.checkpoint()
                    self.owned('report_upload',asset_id=resume['id'],status='upload_attempted',evidence='Selected approved resume through its observed Resume/CV widget')
                    await upload_file(self.page,{'ref':field['ref']},local_asset_path(resume))
                    self.actions['repair_fields']+=1;changed=True;continue
                found=await required_questions(self.page,[field['ref']],include_answered=True,include_optional=True,checkpoint=self.checkpoint)
                self.failures.extend(found['skipped'])
                for item in found['questions']:
                    data=item['data'];key=question_key(data)
                    if key in seen:continue
                    seen.add(key)
                    q=dict(data,ref=item['ref'],question_key=key)
                    q['options']=[dict(o,**({'ref':item['option_refs'][(o['value'],o['label'])]} if (o['value'],o['label']) in item['option_refs'] else {})) for o in data['options']]
                    plan=next((p for p in plans if p.get('ref')==q['ref'] and p.get('question_key')==key),None)
                    answer=plan['answer'] if plan else saved_answer(q,self.package)
                    if answer is None:answer=approved_answer(q['question'],self.profile)
                    if answer is None and self.audit['stage']['name']=='email_entry' and field.get('type')=='email':answer=self.profile.get('identity',{}).get('email')
                    if answer is None:questions.append(q);continue
                    action=answer_action(q,answer)
                    if action is None:self.failures.append({'ref':q['ref'],'reason':'approved_answer_option_unmatched'})
                    else:
                        actions.append(action)
                        approved[action['ref']]={'field':q['field'],'question':q['question'],'question_key':key,
                            'answer':str(answer),'answer_value':answer,'verified':True,
                            'answer_basis':plan['basis'] if plan else 'approved_profile_or_exact_saved_answer'}
            if actions:
                result=await repair_fields(self.page,actions,checkpoint=self.checkpoint)
                await self.control()
                self.actions['repair_fields']+=len(result['fields']);self.trace.append('grouped_repair')
                self.failures.extend(f for f in result['fields'] if not f.get('committed'))
                if result.get('remaining'):self.failures.append({'reason':result.get('reason','repair_incomplete')})
                save_answer_history(self.config,self.package,self.owner['attempt_id'],[approved[f['ref']] for f in result['fields'] if f.get('committed')],
                    page=self.audit['stage']['name'],source='icims_fast',basis='approved_profile_or_exact_saved_answer')
        self.questions=questions
        return bool(actions) or changed

    async def run(self,seconds=60,answers=None):
        self.deadline=time.monotonic()+seconds;plans=answers or []
        if not isinstance(plans,list) or any(not isinstance(p,dict) or not p.get('ref') or not p.get('question_key') or not p.get('basis') or 'answer' not in p for p in plans):
            raise ValueError('approved_grouped_answer_plan_required')
        prior=None
        try:
            while True:
                await self.read();stage=self.audit['stage']['name']
                # A prior unchanged decision returns evidence, never an application finish.
                signature=(self.last.get('structure'),stage,[(f.get('ref'),f.get('present'),f.get('checked'),f.get('validation')) for f in self.last.get('inventory',[])])
                if prior==signature:return self.result('inspection_required','unchanged_after_action')
                prior=signature
                if self.last.get('status')=='active' or self.last.get('writer_pending'):
                    # Wait across all accepted documents; never dispatch Autofill
                    # in one document while a different document owns the writer.
                    writers=self.last
                    while writers.get('status')=='active':
                        await asyncio.sleep(.15);await self.control()
                        writers=await observe_writers(self.page,self.package)
                    if writers.get('writer_pending'):return self.result('continue','writer_settlement_required')
                    prior=None;continue
                if not await self.gate():return self.result('inspection_required','writer_settlement_required')
                native=self.last.get('native',{})
                # Posting and email entry precede bulk application filling.
                if stage not in ('email_entry','sign_in','create_account') and not native.get('apply') and self.last.get('status')=='ready' and not self.last.get('settled_evidence') and self.last.get('controls',{}).get('autofill',{}).get('enabled'):
                    async with self.batch('autofill'):
                        document,_,_=await simplify_document(self.page,operation='autofill')
                        settled=await SimplifyBoundary(document,budget_seconds=max(.05,min(45,self.deadline-time.monotonic())),checkpoint=self.control).perform('autofill')
                        self.actions['autofill']+=int(settled.get('execution')=='clicked');self.trace.append('simplify_settlement')
                    if not settled.get('native_takeover_authorized'):return self.result('continue','writer_settlement_required')
                    continue
                self.trace.append('simplify_settled')
                verification=self.last.get('verification',{}).get('groups',[])
                if any(g.get('complete') is False for g in verification):
                    return self.result('verification_required','use_existing_credentials_mail_flow',verification={'groups':verification})
                if self.audit['credential_tasks']:
                    for task in self.audit['credential_tasks']:
                        if not await self.credentials(task):return self.result('authentication_required','private_credential_handoff')
                    continue
                if self.audit['required_missing'] or self.audit['invalid_blockers']:
                    changed=await self.repair(plans)
                    if self.failures:return self.result('inspection_required','control_recovery')
                    if self.questions:return self.result('questions_required','unresolved_required_questions')
                    if changed:continue
                if self.audit['unknown_controls'] or self.audit['coverage']['unresolved_documents']:
                    return self.result('inspection_required','unresolved_control_coverage')
                if any(not e.get('associated') and e.get('state')!='prior_cycle' for e in self.audit.get('validation_summary',[])):
                    return self.result('inspection_required','unassociated_validation')
                control=native.get('apply') or native.get('continue')
                if control and control.get('enabled'):
                    async with self.batch('advance'):
                        result=await click_control(self.page,{'ref':control['ref']})
                        await self.control()
                        self.actions['stage_advance']+=int(result.get('clicked'));self.trace.append('stage_advance:'+stage)
                    if not result.get('clicked'):return self.result('inspection_required',result.get('reason','advance_unconfirmed'))
                    await asyncio.sleep(.15);await self.control();continue
                control=native.get('submit',{})
                if control.get('enabled') or stage=='confirmation':
                    if self.settings.get('submission_mode')!='submit':return self.result('ready_for_review','configured_review_mode')
                    from .submission import submit
                    async def activate():
                        await self.checkpoint()
                        return await click_control(self.page,{'ref':control['ref']})
                    self.trace.append('shared_submission')
                    result=await submit(self.page,self.call,self.package,self.owner,self.config,self.target,activate,
                        application_control={'ref':control['ref']} if control.get('ref') else None,confirmation_only=stage=='confirmation',
                        seconds=max(.1,min(15,self.deadline-time.monotonic())))
                    return dict(self.result(result.get('status','inspection_required'),result.get('reason','submission_service_result')),**result)
                return self.result('inspection_required','current_stage_control_unresolved')
        except TimeoutError:return self.result('continue','call_slice_complete')
        except (FrameUnavailable,ProtocolError) as exc:
            return self.result('stopped' if str(exc) in ('stop_requested','pause_requested') else 'inspection_required',str(exc))


def advance(config,client,ownership,params):
    from .cdp_client import CDPBrowser
    if set(params)-{'target_id','seconds','answers'} or not params.get('target_id'):raise ProtocolError('invalid_icims_parameters')
    seconds=params.get('seconds',60)
    if type(seconds) not in (int,float) or not 0<seconds<=120:raise ValueError('bounded_seconds_required')
    package=client.call('application_context',attempt_id=ownership['attempt_id'],worker_id=ownership['worker_id'])
    async def execute():
        browser=await CDPBrowser.connect(config['cdp_url'],target_id=params['target_id'],expected_mode=config.get('browser_mode','headed'))
        try:
            service=getattr(client,'service',None);authority=getattr(service,'session_authority',None)
            account_lock=(lambda **kw:service.coordinate_account(authority[0],**kw)) if authority else None
            return await IcimsRunner(await browser.get_current_page(),client.call,package,ownership,config,params['target_id'],account_lock=account_lock).run(seconds,params.get('answers'))
        finally:await browser.close()
    return asyncio.run(execute())
