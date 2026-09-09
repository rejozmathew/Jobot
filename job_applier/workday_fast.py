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
    if observed.get('status') == 'unknown':
        return 'wait'
    if observed.get('identity_mismatch'):
        return 'blocked'
    controls = observed.get('controls', {})
    native = observed.get('native', {})
    enabled = lambda key: controls.get(key, {}).get('enabled', False)
    evidence=observed.get('fingerprint') or observed.get('page_signature') or observed.get('step','unknown')
    fills=state.get('fill_attempts',{}).get(evidence,0) if 'fill_attempts' in state else state.get('fills',0)
    if observed.get('status') not in ('ready', 'complete', 'needs_review'):
        return 'blocked'
    if (observed.get('step')=='unknown' and (state.get('account_action') in ('sign_in','verify') or state.get('account_state')=='creation_pending') and
        not state.get('account_entry_attempted') and native.get('sign_in',{}).get('enabled')):
        return 'native_sign_in'
    if observed.get('step') == 'review' and (enabled('submit') or native.get('submit', {}).get('enabled')):
        return 'blocked' if observed.get('blocking_errors') else 'submit'
    if enabled('autofill_skills'):
        label=controls['autofill_skills'].get('label','autofill_skills')
        return 'blocked' if label in state.get('skills_actions',[]) else 'autofill_skills'
    if state.get('advance_failed'):
        if enabled('autofill') and fills < 2:
            return 'retry' if fills else 'autofill'
        return 'blocked'
    if observed.get('status')=='needs_review' and native.get('continue',{}).get('enabled'):
        return 'native_continue'
    if enabled('continue'):
        return 'continue'
    if native.get('continue', {}).get('enabled'):
        return 'native_continue'
    if enabled('start'):
        return 'start'
    if enabled('autofill') and not fills:
        return 'autofill'
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
    return {'screen_key':key,'page_signature':observed.get('page_signature'),'url':observed.get('url'),
        'step':observed.get('step'),'auth':observed.get('auth'),'auth_ui':observed.get('auth_ui'),
        'native':observed.get('inventory',[]),'errors':observed.get('blocking_errors',[]),
        'simplify':{'enabled':settings.get('autofill','simplify')=='simplify','status':observed.get('status'),'panel':observed.get('panel'),
                    'login_kind':observed.get('login_kind'),'controls':observed.get('simplify_inventory',[]),
                    'text':observed.get('panel_text',''),'credential_use':'unverified'},
        'account':{k:account.get(k) for k in ('action','namespace','credential_ref','state','created_at','last_attempt_id','last_action_at','creation_confirmed')},
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
            self.owned('event',event_id=str(uuid.uuid4()),event_type=kind,
                       observed_at=datetime.now(timezone.utc).isoformat(),payload=payload)
        except Exception as exc:
            self.state['diagnostic_error']=type(exc).__name__

    async def observe(self):
        return await observe_page(self.page,self.package)

    async def click(self,action,observed):
        self.last_click_execution='not_executed'
        self.last_click_result={'clicked':False,'execution':'not_executed','reason':'control_unavailable'}
        operation='autofill' if action=='retry' else action
        native=operation.startswith('native_') or (operation=='submit' and not observed.get('controls',{}).get('submit',{}).get('enabled'))
        operation=operation.removeprefix('native_')
        control=observed['native' if native else 'controls'].get(operation,{})
        if not control.get('enabled') or not control.get('ref'):return False
        args={'ref':control['ref'],'step':observed['step']} if native else {
            'ref':control['ref'],'url':observed['url'],'page_ref':observed.get('page_ref'),'operation':operation}
        if native and observed.get('credential_token'):args['credential_token']=observed['credential_token']
        result=await self.page.click_observed(WORKDAY_CLICK,args) if native else await self.page.evaluate_function(CLICK,args)
        self.last_click_execution=result.get('execution','possibly_executed') if isinstance(result,dict) else 'possibly_executed'
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
                'attempt_id':self.owner['attempt_id']}

    async def run(self,*,seconds=60,recovery=None):
        if type(seconds) not in (int,float) or not 0<seconds<=120:raise ValueError('bounded_seconds_required')
        start=self.clock(); deadline=start+seconds
        metrics=self.state.setdefault('metrics',{'polls':0,'clicks':0,'wait_seconds':0,'elapsed_seconds':0})
        try:
            if self.state['submit_intent']:
                from .submission import submit
                return await submit(self.page,self.call,self.package,self.owner,self.config,self.target,
                    lambda:None,seconds=min(seconds,15),confirmation_only=True)
            if recovery is not None:
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
                if observed.get('status')=='unknown' and action!='authentication_required':
                    gate=await asyncio.to_thread(self.owned,'browser_observe',target_id=self.target,cdp_url=self.config['cdp_url'])
                    if gate.get('quiescent'):
                        return self.report('inspection_required',observed,'settled_screen_unrecognized')
                    return self.report('inspection_required',observed,'writer_activity_unconfirmed_observe_only')
                activity_key=[step,action]
                if self.state.get('reported_activity')!=activity_key:
                    labels={'wait':'Waiting for Simplify to settle','confirm_only':'Checking employer submission confirmation',
                            'authentication_required':'Checking the employer account and authentication form','blocked':'Inspecting required form blockers',
                            'native_sign_in':'Opening Sign In for the recorded portal account',
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
                if action in ('blocked','continue','native_continue'):
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
                    if observed.get('blocking_errors'):return self.report('blocked',observed,'required_blocker_only')
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
                    history=await capture_answers(self.page,self.config,self.package,self.owner,page=step)
                    if history.get('answers_added'):
                        self.event('checkpoint',{'operation':'answer_history','page':step,'source':'employer_form','evidence':history['answer_history_path']})
                    if history.get('answer_history_error'):
                        self.event('recovery',{'operation':'answer_history','error_type':history['answer_history_error'],'evidence':'Answer history capture failed; form action has not been replayed'})
                aid=str(uuid.uuid4()); t0=self.clock(); success=False
                self.owned('action_start',action_id=aid,tool_name='workday_fast.'+action)
                try:
                    if not action.startswith('native_'):self.owned('writer_state',state='active')
                    success=await self.click(action,fresh)
                finally:
                    self.owned('action_end',action_id=aid,status='success' if success else 'failed',duration_seconds=self.clock()-t0,
                               observed_at=datetime.now(timezone.utc).isoformat())
                if not success:
                    report=self.report('submission_unknown' if self.state['submit_intent'] else 'inspection_required',fresh,'click_unconfirmed')
                    report['click']=self.last_click_result;report['execution']=self.last_click_execution
                    return report
                metrics['clicks']+=1
                if action=='native_sign_in':page_state['account_entry_attempted']=True
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
    if platform_for_url(package['job']['url'])!='workday':raise ValueError('workday_only')
    endpoint=urlsplit(config.get('cdp_url',''))
    if endpoint.scheme!='http' or endpoint.hostname not in ('127.0.0.1','localhost','::1') or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path:
        raise ValueError('explicit_loopback_cdp_required')
    client.call('bind_target',**ownership,target_id=params['target_id'],url=package['job']['url'])
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
