"""Workday fast-path policy. Supervises Simplify; never reconstructs candidate facts."""


def choose(observed, state):
    """Return one action from observed controls, never infer writer completion."""
    if state.get('submit_intent') or observed.get('confirmation_surface'):
        return 'confirm_only'
    if observed.get('status') == 'active':
        return 'wait'
    if observed.get('auth'):
        return 'authentication_required'
    if observed.get('status') == 'unknown':
        return 'wait'
    if observed.get('identity_mismatch'):
        return 'blocked'
    controls = observed.get('controls', {})
    native = observed.get('native', {})
    enabled = lambda key: controls.get(key, {}).get('enabled', False)
    if observed.get('status') not in ('ready', 'complete', 'needs_review'):
        return 'blocked'
    if observed.get('step') == 'review' and (enabled('submit') or native.get('submit', {}).get('enabled')):
        return 'blocked' if observed.get('blocking_errors') else 'submit'
    if state.get('advance_failed'):
        if enabled('autofill') and state.get('fills', 0) < 2:
            return 'retry' if state.get('fills', 0) else 'autofill'
        return 'blocked'
    if enabled('continue'):
        return 'continue'
    if native.get('continue', {}).get('enabled'):
        return 'native_continue'
    if enabled('start'):
        return 'start'
    if enabled('autofill') and not state.get('fills'):
        return 'autofill'
    return 'blocked'


import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import unquote, urlsplit
import uuid

from .managed_identity import is_same_application_scope, is_workday_candidate_home
from .simplify_boundary import OBSERVE, CLICK

HELPERS=Path(__file__).parent/'browser_helpers'
WORKDAY_OBSERVE=(HELPERS/'workday_observe.js').read_text(encoding='utf-8')
WORKDAY_CLICK=(HELPERS/'workday_click.js').read_text(encoding='utf-8')


class FastRunner:
    """One bounded supervised loop over a fenced managed attempt, any harness.

    call is the authenticated JobBot protocol callable, not an LLM. State contains
    only action counters/booleans/step IDs; never candidate or credential values.
    """
    def __init__(self,page,call,package,ownership,config,target_id,*,state=None,
                 clock=time.monotonic,sleeper=asyncio.sleep,persist=None):
        self.page=page; self.call=call; self.package=package; self.owner=ownership
        self.config=config; self.target=target_id; self.clock=clock; self.sleep=sleeper
        self.state=state if state is not None else {}; self._persist=persist or (lambda:None)
        self.state.setdefault('pages',{})
        self.state['submit_intent']=bool(package['attempt'].get('submit_intent_at') or self.state.get('submit_intent'))
        self.settings=package['attempt'].get('settings_json') or {}
        if isinstance(self.settings,str): self.settings=json.loads(self.settings)
        profile=package['attempt'].get('profile_json') or {}
        if isinstance(profile,str): profile=json.loads(profile)
        self.email=profile.get('identity',{}).get('email')
        self.asset=next((a for a in package.get('documents',{}).get('assets',[]) if a.get('kind')=='resume'),None)
        self.resume_name=unquote(urlsplit(self.asset['storage_ref']).path).replace('\\','/').rsplit('/',1)[-1] if self.asset else ''
        self.last=None; self.stable=0
        self.pending=tuple(self.state['pending']) if self.state.get('pending') else None
        self.last_action=self.clock()

    def persist(self):
        self.state['pending']=list(self.pending) if self.pending else None
        self._persist()

    def owned(self,operation,**params):
        return self.call(operation,**self.owner,**params)

    def event(self,kind,payload):
        self.owned('event',event_id=str(uuid.uuid4()),event_type=kind,
                   observed_at=datetime.now(timezone.utc).isoformat(),payload=payload)

    async def observe(self):
        url=await self.page.evaluate('location.href')
        if not (is_same_application_scope(self.package['job']['url'],url) or is_workday_candidate_home(self.package['job']['url'],url)):
            raise ValueError('target_scope_changed')
        shared=await self.page.evaluate(OBSERVE)
        args={'requisition':self.package['job'].get('requisition_id') or self.package['job']['url'].rstrip('/').rsplit('_',1)[-1],
              'resume_name':self.resume_name,'expected_email':self.email}
        wd=await self.page.evaluate_function(WORKDAY_OBSERVE,args)
        return dict(shared,**wd,confirmation_surface=is_workday_candidate_home(self.package['job']['url'],url))

    async def click(self,action,observed):
        operation='autofill' if action=='retry' else action
        native=operation.startswith('native_') or (operation=='submit' and not observed.get('controls',{}).get('submit',{}).get('enabled'))
        operation=operation.removeprefix('native_')
        control=observed['native' if native else 'controls'].get(operation,{})
        if not control.get('enabled') or not control.get('ref'):return False
        args={'ref':control['ref'],'step':observed['step']} if native else {
            'ref':control['ref'],'url':observed['url'],'page_ref':observed.get('page_ref'),'operation':operation}
        result=await self.page.evaluate_function(WORKDAY_CLICK if native else CLICK,args)
        return isinstance(result,dict) and (result.get('clicked') is True if native else result.get('status')=='clicked')

    def report(self,status,observed=None,reason=None):
        self.persist()
        observed=observed or {}
        return {'status':status,'reason':reason,'step':observed.get('step'),
                'review_count':observed.get('review_count'),
                'blocking_errors':observed.get('blocking_errors',[]),
                'auth_refs':observed.get('auth_refs',{}) if status=='authentication_required' else {},
                'metrics':self.state.get('metrics',{}),'target_id':self.target,
                'attempt_id':self.owner['attempt_id']}

    async def run(self,*,seconds=60):
        if type(seconds) not in (int,float) or not 0<seconds<=120:raise ValueError('bounded_seconds_required')
        start=self.clock(); deadline=start+seconds
        metrics=self.state.setdefault('metrics',{'polls':0,'clicks':0,'wait_seconds':0,'elapsed_seconds':0})
        try:
            while self.clock()<deadline:
                pulse=self.owned('heartbeat')
                observed=await self.observe(); metrics['polls']+=1
                if pulse.get('control')!='running':
                    gate=self.owned('browser_observe',target_id=self.target,cdp_url=self.config['cdp_url'])
                    if gate.get('quiescent') and pulse.get('control') in ('stop_requested','pause_requested'):
                        self.owned('ack_control',quiescent=True)
                    return self.report(pulse.get('control','control_unknown'),observed)
                if observed.get('submitted'):
                    if not self.state['submit_intent']:
                        return self.report('already_applied',observed,'employer_row_already_submitted')
                    gate=self.owned('browser_observe',target_id=self.target,cdp_url=self.config['cdp_url'])
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
                action=choose(observed,dict(page_state,submit_intent=self.state['submit_intent']))
                if action in ('wait','confirm_only') or self.stable<1:
                    await self.sleep(.5); metrics['wait_seconds']+=.5; continue
                if action in ('blocked','authentication_required'):
                    return self.report(action,observed,'required_blocker_only' if action=='blocked' else 'use_configured_native_credentials')
                if action=='submit':
                    if self.settings.get('submission_mode')!='submit':
                        return self.report('ready_for_review',observed,'submission_not_authorized')
                    if not self.state.get('resume_attached'):
                        return self.report('blocked',observed,'approved_resume_not_observed')
                gate=self.owned('browser_observe',target_id=self.target,cdp_url=self.config['cdp_url'])
                if not gate.get('quiescent'):
                    await self.sleep(.5); metrics['wait_seconds']+=.5; continue
                # Server observation refreshes refs; rediscover immediately before click.
                fresh=await self.observe()
                if fresh.get('step')!=step or choose(fresh,dict(page_state,submit_intent=self.state['submit_intent']))!=action:
                    self.last=None; continue
                aid=str(uuid.uuid4()); t0=self.clock(); success=False
                self.owned('action_start',action_id=aid,tool_name='workday_fast.'+action)
                try:
                    if action=='submit':
                        self.owned('submission_intent',evidence='Workday Review step with enabled submit and approved attachment observed')
                        self.state['submit_intent']=True; self.persist()
                    self.owned('writer_state',state='active')
                    success=await self.click(action,fresh)
                finally:
                    self.owned('action_end',action_id=aid,status='success' if success else 'failed',duration_seconds=self.clock()-t0,
                               observed_at=datetime.now(timezone.utc).isoformat())
                if not success:return self.report('submission_unknown' if self.state['submit_intent'] else 'blocked',fresh,'click_unconfirmed')
                metrics['clicks']+=1
                if action in ('autofill','retry'):
                    page_state['fills']=page_state.get('fills',0)+1; page_state['advance_failed']=False
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
    if set(params)-{'target_id','seconds'} or not isinstance(params.get('target_id'),str) or not params['target_id']:
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
    try:lock=lock_path.open('x',encoding='utf-8')
    except FileExistsError:raise ValueError('fast_runner_already_owned_or_crash_lock')
    try:
        lock.close()
        state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
        if not isinstance(state,dict):raise ValueError('invalid_fast_checkpoint')
        def persist():
            temporary=state_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(state,indent=2),encoding='utf-8')
            os.replace(temporary,state_path)
        async def execute():
            browser=await CDPBrowser.connect(config['cdp_url'],target_id=params['target_id'],expected_mode='headed')
            try:
                runner=FastRunner(await browser.get_current_page(),client.call,package,ownership,config,params['target_id'],state=state,persist=persist)
                return await runner.run(seconds=seconds)
            finally:await browser.close()
        return asyncio.run(execute())
    finally:lock_path.unlink(missing_ok=True)


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
    args=parser.parse_args(argv)
    try:
        if args.operation=='doctor':result=inspect_runtime(args.config,args.url)
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
