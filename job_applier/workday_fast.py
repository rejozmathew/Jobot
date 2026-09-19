"""Workday fast-path policy. Supervises Simplify; never reconstructs candidate facts."""


def choose(observed, state):
    """Return one action from observed controls, never infer writer completion."""
    if state.get('submit_intent') or observed.get('confirmation_surface'):
        return 'confirm_only'
    if observed.get('status') == 'active':
        return 'wait'
    if observed.get('auth') or observed.get('native_authentication_required') or (
        state.get('authentication_pending') and observed.get('step','unknown')=='unknown'):
        return 'authentication_required'
    if observed.get('identity_mismatch'):
        return 'blocked'
    native = observed.get('native', {})
    if (observed.get('step')=='unknown' and native.get('apply',{}).get('enabled') and
        (observed.get('status')!='unknown' or observed.get('writer_safe'))):
        entry=native['apply'].get('label')
        return 'blocked' if entry in state.get('application_entries',[]) else 'native_apply'
    if observed.get('status') == 'unknown':
        return 'wait'
    controls = observed.get('controls', {})
    enabled = lambda key: controls.get(key, {}).get('enabled', False)
    # Values/fingerprints change while filling. The page checkpoint and shared
    # browser receipt remember the attempt across polls and executor tool calls.
    filled=bool(state.get('autofill_started') or state.get('fills') or observed.get('autofill_attempted'))
    if observed.get('status') not in ('ready', 'complete', 'needs_review'):
        return 'blocked'
    if (observed.get('step')=='unknown' and (state.get('account_action') in ('sign_in','verify') or state.get('account_state')=='creation_pending') and
        not state.get('account_entry_attempted') and native.get('sign_in',{}).get('enabled')):
        return 'native_sign_in'
    if observed.get('step') == 'review' and (enabled('submit') or native.get('submit', {}).get('enabled')):
        return 'blocked' if observed.get('blocking_errors') else 'submit'
    if enabled('continue') and not state.get('advance_failed'):
        return 'continue'
    if enabled('autofill_skills'):
        label=controls['autofill_skills'].get('label','autofill_skills')
        if label not in state.get('skills_actions',[]):return 'autofill_skills'
    if enabled('autofill') and not filled:
        return 'autofill'
    if state.get('advance_failed'):
        return 'blocked'
    if native.get('continue', {}).get('enabled'):
        return 'native_continue'
    if enabled('start'):
        return 'start'
    return 'blocked'


import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import unquote, urlsplit
import uuid

from .managed_identity import is_same_application_scope, is_workday_candidate_home, application_match, job_requisition
from .managed_shared import ProtocolError
from .simplify_boundary import OBSERVE, CLICK

HELPERS=Path(__file__).parent/'browser_helpers'
WORKDAY_OBSERVE=(HELPERS/'workday_observe.js').read_text(encoding='utf-8')
WORKDAY_CLICK=(HELPERS/'workday_click.js').read_text(encoding='utf-8')
WORKDAY_SOURCE=(HELPERS/'workday_source.js').read_text(encoding='utf-8')


def source_option(options):
    """Prefer familiar sources, then any offered source as the user authorized."""
    import re
    preferences=(r'\bother\b',r'\b(?:company|corporate|career|employer).*(?:site|page)\b',
                 r'\blinkedin\b',r'\bsearch engine\b',r'\bgoogle\b',r'\bbing\b',
                 r'\byahoo\b',r'\bjob (?:search|board|site|website)\b',r'\bindeed\b')
    for pattern in preferences:
        match=next((o for o in options if re.search(pattern,o['label'],re.I)),None)
        if match:return match
    return next((o for o in options if not o.get('child')),options[0] if options else None)


async def observe_page(page,package):
    """One native/extension inventory shared by snapshot and runner recovery."""
    url=await page.evaluate('location.href')
    if not (is_same_application_scope(package['job']['url'],url) or is_workday_candidate_home(package['job']['url'],url)):
        match=application_match(package['job']['url'],url)
        raise ProtocolError('target_job_mismatch' if match['status']=='different_job' else 'job_identity_unresolved',
            'The owned page needs job verification. Use browser snapshot/screenshot or navigate back to the assigned job.')
    profile=package['attempt'].get('profile_json') or {}
    if isinstance(profile,str):profile=json.loads(profile)
    asset=next((a for a in package.get('documents',{}).get('assets',[]) if a.get('kind')=='resume'),None)
    name=unquote(urlsplit(asset['storage_ref']).path).replace('\\','/').rsplit('/',1)[-1] if asset else ''
    shared=await page.evaluate(OBSERVE)
    wd=await page.evaluate_function(WORKDAY_OBSERVE,{
        'requisition':job_requisition(package['job']),
        'resume_name':name,'expected_email':profile.get('identity',{}).get('email'),
        'page_signature':shared.get('page_signature')})
    entry=wd.get('native',{}).get('apply',{})
    if entry.get('href') and not is_same_application_scope(package['job']['url'],entry['href']):
        entry['enabled']=False
    return dict(shared,**wd,simplify_inventory=shared.get('inventory',[]),
                confirmation_surface=is_workday_candidate_home(package['job']['url'],url))


def screen_inventory(observed,package):
    import hashlib
    # Values, spinners and ordinary rerenders are not new decisions. New questions,
    # native validation and auth transitions are useful evidence for another one.
    evidence=[observed.get('page_signature'),observed.get('step'),observed.get('auth_ui'),
              observed.get('blocking_errors'),[(c.get('label'),c.get('name')) for c in observed.get('inventory',[]) if c.get('required')],
              sorted({c.get('text') or c.get('label') or '' for c in observed.get('inventory',[]) if c.get('tag') in ('BUTTON','A') or c.get('role')=='button'})]
    key=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()
    account=package.get('account') or {}
    settings=package['attempt'].get('settings_json') or {}
    if isinstance(settings,str):settings=json.loads(settings)
    profile=package['attempt'].get('profile_json') or {}
    if isinstance(profile,str):profile=json.loads(profile)
    return {'screen_key':key,'page_signature':observed.get('page_signature'),'url':observed.get('url'),
        'step':observed.get('step'),'auth':observed.get('auth'),'auth_ui':observed.get('auth_ui'),
        'native':observed.get('inventory',[]),'errors':observed.get('blocking_errors',[]),'refresh_error':observed.get('refresh_error',False),
        'browser_recovery':{'available':True,
            'screenshot':{'operation':'browser','parameters':{'method':'screenshot'}},
            'visual_instruction':'If an expected control is missing, take this screenshot and inspect it with the harness image tool. Inspect embedded frames, overlays and scroll containers; continue from what is visible. Before giving up on any portal, inspect a fresh image and try the remaining plausible recovery. Capturing an image without reading it is not visual inspection.',
            'reload':{'operation':'browser','parameters':{'method':'reload'}},'restart':{'operation':'restart','parameters':{}},
            'instruction':'On any portal, inspect a broken page or missing Simplify panel and allow actual loading before recovery. After reload, use the fresh screen: once the page has usable controls or progresses, continue without another reload/restart for the old error. A new observed failure can support further recovery. Inspect submission evidence when relevant; a previous click does not disable recovery.'},
        'simplify':{'enabled':settings.get('autofill','simplify')=='simplify','status':observed.get('status'),'panel':observed.get('panel'),
                    'login_kind':observed.get('login_kind'),'controls':observed.get('simplify_inventory',[]),
                    'text':observed.get('panel_text',''),'credential_use':'unverified'},
        'account':{k:account.get(k) for k in ('action','namespace','credential_ref','state','created_at','last_attempt_id','last_action_at','creation_confirmed')},
        'answer_context':{'standard_answers':profile.get('standard_answers',{}),
            'work_authorization':profile.get('work_authorization',{}),
            'work_preferences':profile.get('work_preferences',{}),
            'instruction':'Use these approved facts/defaults and saved answers to complete the actual questions. Interpret the complete wording and offered choices. Attempt the answers and recover control failures before requesting human input. Other approved facts remain in the application context.'},
        'instruction':'Map the required fields and next action together. Call fast_forward with recovery:{screen_key, credentials:{email_ref,password_ref,confirmation_ref?}, fields:[{ref,value}], action:{source:native|simplify,ref}, account_mode:sign_in|create_account if submitting auth}. Workday authentication always uses native controls and the private retained credential filler; resume Simplify after the application form opens. Different observed controls can support further recovery on this screen. Omit unused fields. All refs come from this inventory. Never send secrets or use recovery for final Submit.'}


class FastRunner:
    """One bounded supervised loop over a fenced managed attempt, any harness.

    call is the authenticated JobBot protocol callable, not an LLM. State contains
    only action counters/booleans/step IDs; never candidate or credential values.
    """
    def __init__(self,page,call,package,ownership,config,target_id,*,state=None,
                 clock=time.monotonic,sleeper=asyncio.sleep,persist=None,account_lock=None):
        self.page=page; self.call=call; self.package=package; self.owner=ownership
        self.config=config; self.target=target_id; self.clock=clock; self.sleep=sleeper
        self.state=state if state is not None else {}; self._persist=persist or (lambda:None)
        self.state.setdefault('pages',{})
        self.state['submit_intent']=package['attempt'].get('submission_pending',bool(
            package['attempt'].get('submit_intent_at') or self.state.get('submit_intent')))
        self.settings=package['attempt'].get('settings_json') or {}
        if isinstance(self.settings,str): self.settings=json.loads(self.settings)
        profile=package['attempt'].get('profile_json') or {}
        if isinstance(profile,str): profile=json.loads(profile)
        self.email=profile.get('identity',{}).get('email')
        self.asset=next((a for a in package.get('documents',{}).get('assets',[]) if a.get('kind')=='resume'),None)
        self.resume_name=unquote(urlsplit(self.asset['storage_ref']).path).replace('\\','/').rsplit('/',1)[-1] if self.asset else ''
        self.last=None; self.stable=0
        self.pending=tuple(self.state['pending']) if self.state.get('pending') else None
        self.account_lock=account_lock
        self.last_action=self.clock()

    def persist(self):
        self.state['pending']=list(self.pending) if self.pending else None
        self._persist()

    def owned(self,operation,**params):
        return self.call(operation,**self.owner,**params)

    def event(self,kind,payload):
        try:
            payload=dict(payload)
            if kind=='phase_changed' and payload.get('phase'):
                from .managed_reports import STAGE_ALIASES,STAGE_TITLES
                phase=payload['phase'];stage=STAGE_ALIASES.get(phase,phase)
                if stage in STAGE_TITLES:
                    payload.update(stage_id=stage,parent_id=stage,task_id='workday:'+phase,task_state='in_progress')
                    if stage=='fill_application':payload['activity']='Fill '+phase.replace('_',' ')
                    elif stage=='remaining_questions':payload['activity']='Complete '+phase.replace('_',' ')
                    elif stage=='authentication':payload['activity']='Sign in to the employer'
                    elif stage=='submission':payload['activity']='Review and submit application'
            self.owned('event',event_id=str(uuid.uuid4()),event_type=kind,
                       observed_at=datetime.now(timezone.utc).isoformat(),payload=payload)
        except Exception as exc:
            self.state['diagnostic_error']=type(exc).__name__

    async def observe(self):
        observed=await observe_page(self.page,self.package)
        document=observed.get('document_id')
        if document is not None:
            if self.state.get('document_id') is not None and self.state['document_id']!=document:
                # A replaced document can have lost unsaved answers. Ordinary
                # rerenders do not change this marker or reauthorize Autofill.
                self.state['pages']={};self.pending=None;self.last=None;self.stable=0
            self.state['document_id']=document
        return observed

    async def recover_error_page(self,observed):
        recovery=self.state.setdefault('page_recovery',{})
        if not recovery.get('reload_attempted'):
            action=str(uuid.uuid4());started=self.clock()
            self.owned('action_start',action_id=action,tool_name='local_browser.reload',writes_browser=True)
            recovery['reload_attempted']=True;self.persist()
            result={}
            try:
                self.owned('writer_state',state='unknown')
                self.event('recovery',{'operation':'reload','evidence':'Workday displays Something went wrong and explicitly requests a page refresh'})
                result=await self.page.reload()
                if result.get('document_replaced'):
                    self.owned('writer_state',state='idle');recovery['awaiting_page']=True
            finally:
                self.owned('action_end',action_id=action,status='success' if result.get('document_replaced') else 'failed',duration_seconds=self.clock()-started)
            if result.get('document_replaced'):
                return await self.wait_after_reload()
        report=self.report('inspection_required',observed,'page_reload_needs_executor_recovery')
        report['recovery']={'operation':'restart','parameters':{},
            'instruction':'Inspect the refreshed page. If it is still broken, restart the owned browser in this same session, wait until connected and continue. Further observed recovery is an executor decision, not a helper retry limit or application outcome.'}
        return report

    async def wait_after_reload(self):
        from .browser_controls import wait_for_page_recovery
        recovery=await wait_for_page_recovery(self.page,self.package)
        self.state.setdefault('page_recovery',{})['awaiting_page']=recovery['status']=='loading'
        if recovery['status']=='recovered':return None
        report=self.report('waiting' if recovery['status']=='loading' else 'inspection_required',
            reason='post_reload_loading' if recovery['status']=='loading' else 'current_page_error')
        report['recovery']=recovery;report['instruction']=recovery['instruction'];return report

    async def fill_source(self, observed, page_state, deadline, *, choice=None):
        """One scoped prompt traversal after Simplify; no model turn per menu."""
        info=await self.page.evaluate_function(WORKDAY_SOURCE,{'method':'inspect'})
        if not info.get('found') or info.get('filled'):return None
        if deadline-self.clock()<3:return {'committed':False,'waiting':True,'reason':'bounded_call_elapsed'}
        from .managed_events import field_task_context
        task_context=field_task_context('How did you hear about us?',page=observed['step'],document=self.state.get('document_id',''))
        self.event('field_context',task_context)
        key=(observed.get('page_signature') or observed['step'])+':'+info['field_key']
        previous=page_state.setdefault('source_fallbacks',{}).get(key) or {}
        result={'committed':False,'path':[],'reason':'source_selection_unconfirmed','attempts':previous.get('attempts',0)+1}
        page_state['source_fallbacks'][key]=result;self.persist()
        end=min(deadline,self.clock()+30);method='begin';last_signature=None;scrolls=0
        last_click=0;click_retries={};reopens=0;empty_polls=0
        async def write(operation):
            aid=str(uuid.uuid4());outcome={}
            self.owned('action_start',action_id=aid,tool_name='workday_fast.source')
            try:
                outcome=await operation();return outcome
            finally:
                succeeded=outcome.get('clicked') or outcome.get('committed') or outcome.get('kind')=='scrolled'
                self.owned('action_end',action_id=aid,status='success' if succeeded else 'failed')
        try:
            while self.clock()<end:
                if self.owned('heartbeat').get('control')!='running':
                    result['reason']='control_requested';break
                gate=await asyncio.to_thread(self.owned,'browser_observe',target_id=self.target,cdp_url=self.config['cdp_url'])
                if not gate.get('native_takeover_authorized',gate.get('quiescent')):
                    result['reason']='writer_activity_unconfirmed';break
                fresh=await self.observe()
                if fresh.get('step')!=observed['step'] or fresh.get('auth') or fresh.get('identity_mismatch'):
                    result['reason']='source_page_changed';break
                command=lambda:self.page.evaluate_function(WORKDAY_SOURCE,{'method':method})
                info=await write(command) if method=='scroll' else await command()
                method='next'
                result['options']=[{k:o[k] for k in ('label','child') if k in o} for o in info.get('options',[])]
                if info.get('filled'):
                    result.update(committed=True,value=info.get('value'),reason=None);break
                kind=info.get('kind')
                if kind=='blocked' or not info.get('found'):
                    result['reason']=info.get('reason','source_control_unavailable');break
                if kind=='options' and info.get('signature')==last_signature and self.clock()-last_click>=1.5:
                    # Selecting a source is reversible. Retry a noncommitting
                    # row with fresh refs instead of treating one click as final.
                    last_signature=None
                if kind=='native' or kind=='options' and info.get('signature')!=last_signature:
                    empty_polls=0
                    option=(next((o for o in info.get('options',[]) if o['label']==choice),None)
                            if choice else source_option(info.get('options',[])))
                    if choice and not option:
                        result['reason']='source_choice_no_longer_visible';break
                    choice=None
                    if option and click_retries.get((info.get('signature'),option['label']),0)>=2:
                        option=source_option([o for o in info.get('options',[]) if click_retries.get((info.get('signature'),o['label']),0)<2])
                    if not option:
                        if kind=='native' or scrolls>=12:
                            result['reason']='source_option_not_found';break
                        scrolls+=1;method='scroll'
                    else:
                        if len(result['path'])>=12:
                            result['reason']='source_menu_depth_exceeded';break
                        if kind=='native':
                            from .browser_controls import form_action
                            selected=await write(lambda:form_action(self.page,{'method':'select','ref':info['ref'],'value':option['value']}))
                            result.update(selected);result['path'].append(option['label']);break
                        activated=await write(lambda:self.page.click_observed(WORKDAY_CLICK,{'ref':option['ref'],'step':fresh['step']}))
                        attempt_key=(info.get('signature'),option['label'])
                        click_retries[attempt_key]=click_retries.get(attempt_key,0)+1
                        if not activated.get('clicked'):
                            result['reason']=activated.get('reason','source_click_unconfirmed')
                        else:
                            result['path'].append(option['label']);last_signature=info.get('signature');last_click=self.clock()
                elif kind=='open':
                    activated=await write(lambda:self.page.click_observed(WORKDAY_CLICK,{'ref':info['ref'],'step':fresh['step']}))
                    if not activated.get('clicked'):
                        result['reason']=activated.get('reason','source_open_unconfirmed');method='reopen'
                elif kind=='waiting':
                    empty_polls+=1
                    if empty_polls>=5 and reopens<3:
                        reopens+=1;empty_polls=0;method='reopen';last_signature=None
                await self.sleep(.2)
            if not result.get('committed') and self.clock()>=end:
                result['waiting']=end==deadline
                result['reason']='bounded_call_elapsed' if result['waiting'] else 'source_selection_needs_inspection'
        finally:
            self.event('field_verified' if result.get('committed') else 'checkpoint',dict(task_context,
                task_state='completed' if result.get('committed') else 'recovering',handler='workday_source',
                verification_result='committed' if result.get('committed') else 'not_verified',
                evidence='Recruiting source selection verified in the current prompt' if result.get('committed') else None))
            self.persist()
        return result

    async def source_handoff(self, result):
        observed=await self.observe()
        if result.get('waiting'):return self.report('waiting',observed,'bounded_call_elapsed')
        current=await self.page.evaluate_function(WORKDAY_SOURCE,{'method':'next'})
        result['options']=[{k:o[k] for k in ('label','child') if k in o} for o in current.get('options',[])]
        result['options_state']=current.get('kind') or current.get('reason')
        report=self.report('inspection_required',observed,result.get('reason'))
        report['source_recovery']=dict(result,instruction=
            'Keep this application open and continue recovery. These are the actual available source options; child:true opens a submenu. '
            'Choose another offered label and call fast_forward with recovery:{screen_key:screen.screen_key,source_choice:"<exact label>"}. '
            'The handler resolves fresh controls, selects it and follows its children. If options are empty, inspect the source field screenshot '
            'and reopen its own menu using scoped browser controls, then call again. This is not a terminal application outcome or a question for the user.')
        return report

    async def click(self,action,observed):
        self.last_click_execution='not_executed'
        self.last_click_result={'clicked':False,'execution':'not_executed','reason':'control_unavailable'}
        operation='autofill' if action=='retry' else action
        native=operation.startswith('native_') or (operation=='submit' and not observed.get('controls',{}).get('submit',{}).get('enabled'))
        operation=operation.removeprefix('native_')
        control=observed['native' if native else 'controls'].get(operation,{})
        if not control.get('enabled') or not control.get('ref'):return False
        args={'ref':control['ref'],'step':observed['step']} if native else {
            'ref':control['ref'],'url':observed['url'],'page_ref':observed.get('page_ref'),
            'page_signature':observed.get('page_signature'),'operation':operation}
        if native and observed.get('credential_token'):args['credential_token']=observed['credential_token']
        result=await self.page.click_observed(WORKDAY_CLICK,args) if native else await self.page.evaluate_function(CLICK,args)
        self.last_click_execution=result.get('execution','possibly_executed') if isinstance(result,dict) else 'possibly_executed'
        if not native and isinstance(result,dict) and result.get('clicked') is False:
            self.last_click_execution='not_executed'
        self.last_click_result=result if isinstance(result,dict) else {'execution':'possibly_executed','reason':'click_result_unavailable'}
        return isinstance(result,dict) and (result.get('clicked') is True if native else result.get('status')=='clicked')

    def report(self,status,observed=None,reason=None):
        self.persist()
        observed=observed or {}
        return {'status':status,'reason':reason,'step':observed.get('step'),
                'review_count':observed.get('review_count'),
                'blocking_errors':observed.get('blocking_errors',[]),
                'auth_refs':observed.get('auth_refs',{}) if status=='authentication_required' else {},
                'metrics':self.state.get('metrics',{}),'target_id':self.target,
                'credential_check':{key:self.state.get('authentication',{}).get('last_dispatch',{}).get(key)
                    for key in ('credentials_verified_before_click','credentials_refilled_before_click')
                    if key in self.state.get('authentication',{}).get('last_dispatch',{})},
                'page_decisions':self.state.get('page_decisions',0),
                **({'diagnostic_error':self.state['diagnostic_error']} if self.state.get('diagnostic_error') else {}),
                **({'screen':screen_inventory(observed,self.package)} if observed and status in ('authentication_required','blocked','inspection_required') else {}),
                **({'helper_handoff':True,'instruction':
                    'This helper result is not an application outcome. Keep the owned session open, inspect the current controls/errors and '
                    'offered options, and choose another supported recovery using scoped browser tools or mapped fast_forward recovery. '
                    'Verify progress and continue. Do not finish because a matcher, click, retry limit or time slice failed. '
                    'Ask the user only for an actual missing required fact or unresolved verification; respect pause/stop and uncertain submission.'}
                   if status in ('authentication_required','blocked','inspection_required') else {}),
                'attempt_id':self.owner['attempt_id']}

    async def run(self,*,seconds=60,recovery=None):
        if type(seconds) not in (int,float) or not 0<seconds<=120:raise ValueError('bounded_seconds_required')
        start=self.clock(); deadline=start+seconds
        metrics=self.state.setdefault('metrics',{'polls':0,'clicks':0,'wait_seconds':0,'elapsed_seconds':0})
        try:
            if recovery is not None:
                if isinstance(recovery,dict) and 'source_choice' in recovery:
                    if set(recovery)!={'screen_key','source_choice'} or not isinstance(recovery['source_choice'],str) or not recovery['source_choice'].strip():
                        raise ValueError('source_choice_and_screen_key_required')
                    observed=await self.observe()
                    if screen_inventory(observed,self.package)['screen_key']!=recovery['screen_key']:
                        return await self.source_handoff({'committed':False,'reason':'source_screen_changed'})
                    recovered=await self.fill_source(observed,self.state['pages'].setdefault(observed['step'],{}),deadline,choice=recovery['source_choice'])
                    if recovered is not None and not recovered.get('committed'):
                        return await self.source_handoff(recovered)
                else:
                    from .workday_auth import recover_screen
                    recovered=await recover_screen(self,recovery)
                    if recovered['status']!='progress':
                        report=self.report('inspection_required',await self.observe(),recovered.get('reason'))
                        report['recovery_result']=recovered;return report
            while self.clock()<deadline:
                pulse=self.owned('heartbeat')
                observed=await self.observe(); metrics['polls']+=1
                if self.settings.get('autofill','simplify')!='simplify':observed['controls']={}
                if pulse.get('control')!='running':
                    gate=await asyncio.to_thread(self.owned,'browser_observe',target_id=self.target,cdp_url=self.config['cdp_url'])
                    if gate.get('quiescent') and pulse.get('control') in ('stop_requested','pause_requested'):
                        self.owned('ack_control',quiescent=True)
                    return self.report(pulse.get('control','control_unknown'),observed)
                if observed.get('refresh_error') and not observed.get('confirmation_surface'):
                    recovered=await self.recover_error_page(observed)
                    if recovered is not None:return recovered
                    continue
                if self.state.get('page_recovery',{}).get('awaiting_page'):
                    recovered=await self.wait_after_reload()
                    if recovered is not None:return recovered
                    observed=await self.observe()
                from .workday_auth import confirm_authenticated
                await confirm_authenticated(self,observed)
                if observed.get('submitted'):
                    if not self.state['submit_intent']:
                        return self.report('already_applied',observed,'employer_row_already_submitted')
                    gate=await asyncio.to_thread(self.owned,'browser_observe',target_id=self.target,cdp_url=self.config['cdp_url'])
                    if gate.get('quiescent'):
                        evidence='Employer My Applications row matches requisition and Application Submitted status'
                        self.owned('target_state',target_id=self.target,state='preserved',evidence='Completed target retained for benchmark inspection')
                        self.owned('finish',outcome='applied',evidence=evidence,quiescent=True)
                        recorded=self.call('attempt_status',attempt_id=self.owner['attempt_id'])
                        if recorded.get('outcome')!='applied' or not recorded.get('completed_at'):
                            return self.report('submission_unknown',observed,'outcome_readback_unconfirmed')
                        return self.report('applied',observed)
                if observed.get('identity_mismatch'):
                    return self.report('blocked',observed,'candidate_email_mismatch')
                if observed.get('resume_attached'):
                    if not self.state.get('resume_attached') and self.asset:
                        for status in ('upload_attempted','upload_confirmed'):
                            self.owned('report_upload',asset_id=self.asset['id'],status=status,evidence='Approved filename observed in employer attachment UI')
                    self.state['resume_attached']=True
                step=observed.get('step','unknown')
                page_state=self.state['pages'].setdefault(step,{})
                if page_state.get('advance_failed') and observed.get('fingerprint') and page_state.get('failure_fingerprint')!=observed['fingerprint']:
                    page_state['advance_failed']=False
                if self.state.get('step') and self.state['step']!=step:
                    from .managed_reports import STAGE_ALIASES
                    previous=self.state['step'];stage=STAGE_ALIASES.get(previous,previous)
                    self.event('checkpoint',{'stage_id':stage,'task_id':'workday:'+previous,'task_state':'completed',
                        'activity':'Complete '+previous.replace('_',' '),'evidence':'Employer advanced to the next application step'})
                    self.event('navigation_verified',{'page':step,'evidence':'Workday current step changed'})
                    self.pending=None
                self.state['step']=step
                key=(step,observed.get('fingerprint'),observed.get('status'))
                self.stable=self.stable+1 if key==self.last else 0
                if self.last and self.last[0]==step and self.last[1]!=key[1]:
                    self.event('field_verified',{'page':step,'evidence':'Observed form fingerprint changed'})
                self.last=key
                if self.pending and self.pending[0]==step:
                    # One advancement attempt then let actual navigation/validation settle.
                    if self.clock()-self.last_action<5 or observed.get('status')=='active':
                        await self.sleep(.5); metrics['wait_seconds']+=.5; continue
                    if self.pending[1] in ('continue','native_continue','start'):
                        page_state['advance_failed']=True
                        page_state['failure_fingerprint']=observed.get('fingerprint')
                    self.pending=None
                page_state['account_action']=(self.package.get('account') or {}).get('action')
                page_state['account_state']=(self.package.get('account') or {}).get('state')
                authentication=self.state.get('authentication',{})
                page_state['authentication_pending']=bool(authentication.get('submitted') and not authentication.get('complete'))
                action=choose(observed,dict(page_state,submit_intent=self.state['submit_intent']))
                if observed.get('status')=='unknown' and action not in ('authentication_required','native_apply'):
                    gate=await asyncio.to_thread(self.owned,'browser_observe',target_id=self.target,cdp_url=self.config['cdp_url'])
                    if gate.get('quiescent'):
                        return self.report('inspection_required',observed,'settled_screen_unrecognized')
                    return self.report('inspection_required',observed,'writer_activity_unconfirmed_observe_only')
                activity_key=[step,action]
                if self.state.get('reported_activity')!=activity_key:
                    labels={'wait':'Waiting for Simplify to settle','confirm_only':'Checking employer submission confirmation',
                            'authentication_required':'Checking the employer account and authentication form','blocked':'Inspecting required form blockers',
                            'native_sign_in':'Opening Sign In for the recorded portal account',
                            'native_apply':'Opening the direct application form',
                            'continue':'Continuing through Simplify','native_continue':'Continuing with the employer control',
                            'start':'Starting the Simplify application flow','autofill':'Starting Simplify autofill',
                            'autofill_skills':'Responding to the enabled Simplify skills prompt',
                            'retry':'Retrying Simplify after a failed advancement','submit':'Preparing the authorized submission'}
                    self.event('phase_changed',{'phase':step,'page':step,'activity':labels.get(action,action),
                        'source':'Workday helper','status':observed.get('status','unknown'),
                        'evidence':'Observed current Workday step and available controls'})
                    self.state['reported_activity']=activity_key
                if action in ('wait','confirm_only') or self.stable<1:
                    await self.sleep(.5); metrics['wait_seconds']+=.5; continue
                if action=='authentication_required':
                    from .workday_auth import advance_auth,recovery_handoff
                    auth=await advance_auth(self,observed)
                    if auth['status'] in ('progress','waiting'):
                        await self.sleep(.5);metrics['wait_seconds']+=.5;continue
                    reason=auth.get('reason');handoff=recovery_handoff(reason,observed)
                    if self.state.get('auth_recovery_reason')!=reason:
                        self.event('recovery',{'phase':'authentication','error_type':reason,
                            'activity':'Workday account routine needs executor inspection: '+handoff['kind'],
                            'next_step':'Inspect the owned screenshot and fresh controls; recover without repeating an uncertain action',
                            'source':'Workday helper'})
                        self.state['auth_recovery_reason']=reason
                    report=self.report('authentication_required',observed,reason)
                    if auth.get('click'):report['click']=auth['click'];report['execution']=auth.get('execution')
                    report['recovery']=handoff;return report
                if action=='blocked':
                    if observed.get('status') in ('complete','needs_review') or page_state.get('fills'):
                        source=await self.fill_source(observed,page_state,deadline)
                        if source is not None:
                            if source.get('waiting'):
                                return await self.source_handoff(source)
                            if source.get('committed'):
                                self.last=None;continue
                            return await self.source_handoff(source)
                    from .application_answers import apply_policy
                    completed=self.state.setdefault('answered_policy_fields',[])
                    planned=await apply_policy(self.page,self.package,observed,completed=completed,dry_run=True)
                    if planned['fields']:
                        gate=await asyncio.to_thread(self.owned,'browser_observe',target_id=self.target,cdp_url=self.config['cdp_url'])
                        if not gate.get('native_takeover_authorized',gate.get('quiescent')):
                            return self.report('inspection_required',observed,'writer_activity_unconfirmed')
                        aid=str(uuid.uuid4());self.owned('action_start',action_id=aid,tool_name='browser.apply_policy')
                        repaired={}
                        try:repaired=await apply_policy(self.page,self.package,await self.observe(),completed=completed)
                        finally:self.owned('action_end',action_id=aid,status='success' if repaired.get('changed') else 'failed')
                        if repaired.get('changed'):
                            self.event('field_verified',{'page':step,'evidence':'Applied and verified configured salary/privacy preferences','source':'Candidate profile'})
                            self.persist();self.last=None;continue
                        return self.report('inspection_required',observed,'configured_answer_control_unconfirmed')
                if action=='blocked':
                    if observed.get('identity_mismatch'):return self.report('inspection_required',observed,'candidate_email_mismatch')
                    if observed.get('blocking_errors'):
                        report=self.report('inspection_required',observed,'complete_required_answers')
                        report['answer_recovery']={
                            'fields':[field for field in observed.get('inventory',[]) if field.get('required') and field.get('enabled')],
                            'instruction':'Complete the Workday questions before considering a blocker. Read each full question and use screen.answer_context.standard_answers, approved profile facts and saved answers. '
                                'Decide the answers for the page together, then use browser select/check/fill or mapped recovery to enter them and verify commitment. '
                                'A Select One or needs_review label is unfinished work, not evidence of missing information. If a control fails, inspect its options and try another supported interaction. '
                                'Continue afterward. Only a required answer still unknown after this work belongs in request_answers; do not finalize blocked because this helper handed the questions to you.'}
                        return report
                    return self.report('inspection_required',observed,'screen_controls_unrecognized')
                if action=='submit':
                    if self.settings.get('submission_mode')!='submit':
                        return self.report('ready_for_review',observed,'submission_not_authorized')
                    from .submission import submit
                    async def activate():
                        fresh=await self.observe()
                        if choose(fresh,{})!='submit':return {'clicked':False,'execution':'not_executed','reason':'submit_control_changed'}
                        clicked=await self.click('submit',fresh)
                        return {'clicked':clicked,'execution':self.last_click_execution}
                    result=await submit(self.page,self.call,self.package,self.owner,self.config,self.target,activate,seconds=min(seconds,15))
                    attempt=self.call('attempt_status',attempt_id=self.owner['attempt_id'])
                    self.state['submit_intent']=attempt.get('submission_pending',bool(attempt.get('submit_intent_at')))
                    self.persist();return result
                gate=await asyncio.to_thread(self.owned,'browser_observe',target_id=self.target,cdp_url=self.config['cdp_url'])
                if not gate.get('quiescent'):
                    await self.sleep(.5); metrics['wait_seconds']+=.5; continue
                if action.startswith('native_') and not gate.get('native_takeover_authorized',True):
                    return self.report('inspection_required',observed,'simplify_input_required')
                # Server observation refreshes refs; rediscover immediately before click.
                fresh=await self.observe()
                if fresh.get('step')!=step or choose(fresh,dict(page_state,submit_intent=self.state['submit_intent']))!=action:
                    self.last=None; continue
                if action in ('continue','native_continue'):
                    from .application_answers import capture_answers
                    history=await capture_answers(self.page,self.config,self.package,self.owner,page=step,call=self.call)
                    if history.get('answers_added'):
                        self.event('checkpoint',{'operation':'answer_history','page':step,'source':'employer_form','evidence':history['answer_history_path']})
                    if history.get('answer_history_error'):
                        self.event('recovery',{'operation':'answer_history','error_type':history['answer_history_error'],'evidence':'Answer history capture failed; form action has not been replayed'})
                aid=str(uuid.uuid4()); t0=self.clock(); success=False
                self.owned('action_start',action_id=aid,tool_name='workday_fast.'+action)
                try:
                    if not action.startswith('native_'):self.owned('writer_state',state='active')
                    if action=='autofill':
                        page_state['autofill_started']=True;self.persist()
                    dispatched_at=datetime.now(timezone.utc).isoformat()
                    success=await self.click(action,fresh)
                    if success and action=='autofill':
                        self.owned('event',event_id=str(uuid.uuid4()),event_type='checkpoint',action_id=aid,observed_at=dispatched_at,
                            payload={'operation':'autofill_dispatch','status':'executed','source':'simplify',
                                'stage_id':'fill_application','task_id':'workday:'+step,'activity':'Fill '+step.replace('_',' '),
                                'evidence':'Observed Autofill control activated'})
                finally:
                    self.owned('action_end',action_id=aid,status='success' if success else 'failed',duration_seconds=self.clock()-t0,
                               observed_at=datetime.now(timezone.utc).isoformat())
                if not success:
                    if action=='autofill' and self.last_click_execution=='not_executed':
                        page_state['autofill_started']=False
                    report=self.report('submission_unknown' if self.state['submit_intent'] else 'inspection_required',fresh,'click_unconfirmed')
                    report['click']=self.last_click_result;report['execution']=self.last_click_execution
                    return report
                metrics['clicks']+=1
                if action=='native_sign_in':page_state['account_entry_attempted']=True
                if action=='native_apply':page_state.setdefault('application_entries',[]).append(fresh['native']['apply']['label'])
                if action in ('autofill','retry'):
                    page_state['fills']=page_state.get('fills',0)+1; page_state['advance_failed']=False
                    evidence=fresh.get('fingerprint') or fresh.get('page_signature') or step
                    attempts=page_state.setdefault('fill_attempts',{})
                    attempts[evidence]=attempts.get(evidence,0)+1
                if action=='autofill_skills':
                    page_state.setdefault('skills_actions',[]).append(fresh['controls']['autofill_skills'].get('label','autofill_skills'))
                    page_state['advance_failed']=False
                self.pending=(step,action); self.last_action=self.clock(); self.stable=0; self.persist()
                await self.sleep(.5); metrics['wait_seconds']+=.5
            return self.report('submission_unknown' if self.state['submit_intent'] else 'waiting',reason='bounded_call_elapsed')
        finally:
            metrics['elapsed_seconds']+=self.clock()-start
            self.persist()


def advance(config,client,ownership,params):
    """Harness-neutral entry point used by the CLI and Hermes plugin alike."""
    import hashlib
    import os
    from .application_runtime import history_matches
    from .cdp_client import CDPBrowser
    if set(params)-{'target_id','seconds','recovery'} or not isinstance(params.get('target_id'),str) or not params['target_id']:
        raise ValueError('invalid_fast_parameters')
    seconds=params.get('seconds',60)
    if type(seconds) not in (int,float) or not 0<seconds<=120:raise ValueError('bounded_seconds_required')
    if set(ownership)!={'attempt_id','worker_id','fence'}:raise ValueError('owned_attempt_required')
    health=client.call('health')
    if health.get('instance_id')!=config['instance_id'] or Path(health.get('db_path','')).resolve()!=Path(config['db_path']).resolve():
        raise ValueError('runtime_database_mismatch')
    package=client.call('application_context',attempt_id=ownership['attempt_id'],worker_id=ownership['worker_id'])
    if package['attempt']['worker_id']!=ownership['worker_id'] or package['attempt']['fence']!=ownership['fence']:
        raise ValueError('stale_owner')
    if history_matches(config.get('legacy_history_paths',[]),package['job']['url']):
        return {'status':'blocked','reason':'legacy_history_suppression'}
    from .managed_context import platform_for_url
    handed_off=False
    if platform_for_url(package['job']['url'])!='workday':
        gate=client.call('browser_observe',**ownership,target_id=params['target_id'],cdp_url=config.get('cdp_url'))
        if gate.get('platform')!='workday' or gate.get('identity',{}).get('status')!='same_job':raise ValueError('workday_only')
        route=gate.get('application_url') or gate.get('url')
        if platform_for_url(route)!='workday':route=gate['url']
        package=dict(package,job=dict(package['job'],url=route),platform='workday')
        handed_off=True
    endpoint=urlsplit(config.get('cdp_url',''))
    if endpoint.scheme!='http' or endpoint.hostname not in ('127.0.0.1','localhost','::1') or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path:
        raise ValueError('explicit_loopback_cdp_required')
    if not handed_off:client.call('bind_target',**ownership,target_id=params['target_id'],url=package['job']['url'])
    spool=Path(config['spool_dir'])
    if not spool.is_absolute():raise ValueError('absolute_spool_required')
    spool.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(json.dumps([config['instance_id'],ownership,params['target_id']],sort_keys=True).encode()).hexdigest()[:32]
    state_path=spool/('fast-'+key+'.json'); lock_path=spool/('fast-'+key+'.lock')
    from .workspace_process import FileLock
    from .managed_shared import ProtocolError
    try:lock=FileLock(lock_path).acquire()
    except ProtocolError:raise ValueError('fast_runner_already_owned_or_crash_lock')
    try:
        state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
        if not isinstance(state,dict):raise ValueError('invalid_fast_checkpoint')
        def persist():
            temporary=state_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(state,indent=2),encoding='utf-8')
            os.replace(temporary,state_path)
        async def execute():
            browser=await CDPBrowser.connect(config['cdp_url'],target_id=params['target_id'],expected_mode=config.get('browser_mode','headed'))
            try:
                service=getattr(client,'service',None)
                authority=getattr(service,'session_authority',None)
                account_lock=(lambda **kw:service.coordinate_account(authority[0],**kw)) if authority else None
                runner=FastRunner(await browser.get_current_page(),client.call,package,ownership,config,params['target_id'],state=state,persist=persist,account_lock=account_lock)
                return await runner.run(seconds=seconds,recovery=params.get('recovery'))
            finally:await browser.close()
        return asyncio.run(execute())
    finally:lock.release()


def main(argv=None):
    """A shell-only harness can call the exact same runtime; no model launch."""
    import argparse
    import os
    from .application_runtime import read_config,inspect_runtime
    from .managed_client import Client
    from .managed_shared import ProtocolError
    parser=argparse.ArgumentParser(description='Portable Workday Simplify supervisor. No default DB, no new agent.')
    subs=parser.add_subparsers(dest='operation',required=True)
    doctor=subs.add_parser('doctor',help='Read-only config/DB/legacy-history checks')
    doctor.add_argument('--config',required=True);doctor.add_argument('--url')
    run=subs.add_parser('advance',help='Advance an already claimed/fenced target for up to 120 seconds')
    run.add_argument('--config',required=True);run.add_argument('--attempt-id',type=int,required=True)
    run.add_argument('--fence',type=int,required=True);run.add_argument('--target-id',required=True)
    run.add_argument('--seconds',type=float,default=60)
    session=subs.add_parser('session',help='Advance a local session; endpoint/ownership resolved by its host')
    session.add_argument('session_id');session.add_argument('--config');session.add_argument('--driver-id')
    session.add_argument('--seconds',type=float,default=60)
    args=parser.parse_args(argv)
    try:
        if args.operation=='doctor':result=inspect_runtime(args.config,args.url)
        elif args.operation=='session':
            from .application_runtime import resolve_config,session_call
            result=session_call(resolve_config(args.config),args.session_id,'fast_forward',{'seconds':args.seconds},args.driver_id)
        else:
            inspect_runtime(args.config)
            cfg=read_config(args.config)
            from .managed_cli import credential
            token=credential(cfg['worker_token_env'],cfg)
            with Client(cfg['base_url'],cfg['instance_id'],token) as client:
                result=advance(cfg,client,{'attempt_id':args.attempt_id,'worker_id':cfg['worker_id'],'fence':args.fence},
                               {'target_id':args.target_id,'seconds':args.seconds})
        print(json.dumps(result,ensure_ascii=False));return 0
    except (ValueError,OSError,KeyError,ProtocolError) as exc:
        code=exc.code if isinstance(exc,ProtocolError) else str(exc) if isinstance(exc,ValueError) and str(exc).replace('_','').isalnum() else 'runtime_unavailable'
        print(json.dumps({'status':'error','error':code}));return 2


if __name__=='__main__':
    raise SystemExit(main())
