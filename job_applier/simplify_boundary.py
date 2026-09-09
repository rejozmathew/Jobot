"""Small observable Simplify boundary; no ATS filler, authentication or submission engine."""
import asyncio
from pathlib import Path
import time

ROOT=Path(__file__).parent/'browser_helpers'
OBSERVE=(ROOT/'simplify_observe.js').read_text(encoding='utf-8')
CLICK=(ROOT/'simplify_click.js').read_text(encoding='utf-8')
STATES={'ready','active','complete','needs_review','unsupported','login_required','missing','unknown'}


class SimplifyBoundary:
    def __init__(self,page,*,budget_seconds=45,poll_seconds=0.1,clock=None,sleeper=None,fast=False):
        if not 0<budget_seconds<=120 or not 0<poll_seconds<=5:raise ValueError('Invalid Simplify budget')
        self.page=page;self.budget=budget_seconds;self.poll=poll_seconds
        self.clock=clock or time.monotonic;self.sleep=sleeper or asyncio.sleep
        self.attempted=set();self.deadline=None;self.fast=bool(fast)
        self.retries={}

    async def observe(self):
        timeout=self.budget if self.deadline is None else max(0.05,min(self.budget,self.deadline-self.clock()))
        raw=await asyncio.wait_for(self.page.evaluate(OBSERVE),timeout=timeout)
        if not isinstance(raw,dict) or raw.get('status') not in STATES or not isinstance(raw.get('url'),str):
            raise ValueError('Unrecognized Simplify observation')
        controls={}
        for kind in ('autofill','autofill_skills','continue','start','create_account_autofill','create_account','sign_in','submit','stop'):
            item=(raw.get('controls') or {}).get(kind) or {}
            controls[kind]={'ref':item.get('ref') if isinstance(item.get('ref'),str) else None,'enabled':item.get('enabled') is True,
                            'label':item.get('label','')}
        result={key:raw[key] for key in ('url','fingerprint','page_ref','page_signature') if key in raw and isinstance(raw[key],str)}
        result.update(panel=raw.get('panel') is True,status=raw['status'],controls=controls,
            source='fixture' if raw.get('source')=='fixture' else 'observed_dom')
        result['login_kind']=raw.get('login_kind')
        result['native_authentication_required']=raw.get('native_authentication_required') is True
        if raw.get('workday') is True:
            result['workday']=True
            result['autofill_attempted']=raw.get('autofill_attempted') is True
            result['autofill_page_key']=raw.get('autofill_page_key')
        result['activity']=raw.get('activity') or {}
        if 'review_count' in raw and (raw['review_count'] is None or isinstance(raw['review_count'], int)):
            result['review_count']=raw['review_count']
        if 'field_summary' in raw and isinstance(raw['field_summary'], dict):
            result['field_summary']=raw['field_summary']
        if 'writer_safe' in raw:
            result['writer_safe']=bool(raw['writer_safe'])
        else:
            result['writer_safe']=raw['status'] not in ('active','unknown')
        return result

    @staticmethod
    def decide(observation,already_attempted=False,*,fast=False):
        status=observation.get('status','unknown');controls=observation.get('controls') or {}
        already_attempted=already_attempted or bool(observation.get('workday') and observation.get('autofill_attempted'))
        if status=='active':return {'action':'wait','reason':'autofill_active'}
        if observation.get('native_authentication_required'):
            return {'action':'fallback','reason':'workday_native_authentication_required'}
        if status in ('unsupported','missing','login_required'):return {'action':'fallback','reason':status}
        if status=='unknown':return {'action':'fallback','reason':'controls_unavailable'}
        if controls.get('continue',{}).get('enabled'):
            return {'action':'continue','reason':'prefer_extension_continue'}
        if controls.get('autofill_skills',{}).get('enabled'):
            return {'action':'autofill_skills','reason':'simplify_waiting_for_skills_input'}
        if observation.get('workday') and not already_attempted and not observation.get('autofill_attempted') and controls.get('autofill',{}).get('enabled'):
            return {'action':'autofill','reason':'autofill_once_before_continue'}
        if fast and status in ('complete','needs_review') and controls.get('continue',{}).get('enabled'):
            return {'action':'continue','reason':'prefer_extension_continue'}
        if status=='needs_review':return {'action':'review','reason':'review_residual_fields'}
        if status=='ready' and not already_attempted and controls.get('autofill',{}).get('enabled'):
            return {'action':'autofill','reason':'autofill_ready'}
        if status=='ready' and not already_attempted and controls.get('start',{}).get('enabled'):
            return {'action':'start','reason':'start_ready'}
        if status=='complete' and controls.get('continue',{}).get('enabled'):
            return {'action':'continue','reason':'prefer_extension_continue'}
        return {'action':'fallback','reason':'already_attempted' if already_attempted else 'controls_unavailable'}

    @staticmethod
    def _changed(before,after):
        return (before.get('url')!=after.get('url') or before.get('fingerprint')!=after.get('fingerprint') or
            (before.get('page_ref') is not None and before.get('page_ref')!=after.get('page_ref')))

    @staticmethod
    def _page_changed(before,after):
        return (before.get('url')!=after.get('url') or
            any(before.get(k) and after.get(k) and before[k]!=after[k] for k in ('page_ref','page_signature')))

    def _result(self,observed,changed,writer,reason):
        return {'status':observed.get('status','unknown'),'changed':bool(changed),
            'writer_state':writer,'reason':reason,'native_takeover_authorized':writer=='idle' and not (
                observed.get('activity',{}).get('busy_indicator') and observed.get('activity',{}).get('waiting_for_input')),
            'observation':observed,'execution':getattr(self,'execution','not_executed'),
            'instruction':('While a writer is active, observe it or use its enabled Stop/Cancel control and verify settlement. '
                'For a broken page or missing Simplify panel on any portal, inspect loading and use browser reload when appropriate; '
                'if that fails, use session restart and continue. These operations cancel old activity even when its settlement is unknown, before submission only. '
                'Once settled, a missing control, unsupported field or failed helper is a handoff to the executor. '
                'Inspect the actual screen/options, recover with scoped browser tools and resume filling or advancement. '
                'A helper limit is not a terminal application outcome; keep working on the open session.')}

    async def perform(self,operation,*,retry=False,credential_evidence=None):
        if operation not in ('autofill','autofill_skills','continue','start','sign_in','stop'):raise ValueError('Unsupported Simplify operation')
        self.execution='not_executed'
        self.deadline=self.clock()+self.budget
        before=await self.observe();current=before
        if operation!='stop' and before.get('native_authentication_required'):
            self.deadline=None
            return dict(self._result(before,False,'unknown' if before['status'] in ('active','unknown') else 'idle',
                'workday_native_authentication_required'),
                instruction='Use fast_forward for native Workday authentication with the retained credential. Resume Simplify after the application form opens.')
        page_key=before.get('autofill_page_key') or before.get('page_signature') or before['url']
        if operation=='autofill_skills':
            page_key=(page_key,operation,before['controls'][operation].get('label'))
        already=page_key in self.attempted or operation=='autofill' and before.get('workday') and before.get('autofill_attempted',False)
        can_retry=(bool(retry) and self.fast and operation=='autofill' and already
            and before['status'] in ('ready','complete','needs_review')
            and bool(before.get('controls',{}).get('autofill',{}).get('enabled'))
            and self.retries.get(page_key,0)<1)
        decision=self.decide(before,already and not can_retry,fast=self.fast)
        # An explicit first Autofill can repair failed advancement even when
        # Continue remains enabled. The default recommendation still advances.
        if (operation=='autofill' and before.get('workday') and not already and
            before['status'] in ('ready','complete','needs_review') and before['controls'].get('autofill',{}).get('enabled')):
            decision={'action':'autofill','reason':'first_page_autofill_before_manual_repair'}
        active=before['status']=='active';clicked=False
        try:
            if operation=='stop':
                control=before['controls']['stop']
                if not control['ref'] or not control['enabled']:
                    return self._result(before,False,'unknown','observed_stop_control_required')
                self.execution='possibly_executed'
                response=await self.page.evaluate(CLICK,{'ref':control['ref'],'url':before['url'],
                    'page_ref':before.get('page_ref'),'operation':'stop'})
                if response.get('status')!='clicked':
                    self.execution='not_executed' if response.get('clicked') is False else 'possibly_executed'
                    return self._result(before,False,'unknown','stop_unconfirmed')
                self.execution='clicked';previous=None
                while self.clock()<self.deadline:
                    current=await self.observe()
                    settled=current.get('panel') and current.get('writer_safe') and current['status'] in ('ready','complete','needs_review','unsupported','login_required')
                    if settled and previous==current:
                        return self._result(current,True,'idle','observed_stop_settled')
                    previous=current
                    await self.sleep(self.poll)
                return self._result(current,False,'unknown','stop_settlement_unconfirmed')
            if operation=='sign_in' and not active:
                if before.get('login_kind')!='employer':
                    return self._result(before,False,'idle','simplify_login_is_not_employer_sign_in')
                if not isinstance(credential_evidence,str) or not credential_evidence.strip():
                    return self._result(before,False,'idle','retained_credential_use_unverified')
                if ('sign_in',page_key) in self.attempted:
                    return self._result(before,False,'idle','sign_in_already_attempted')
                decision={'action':'sign_in','reason':'observed_employer_sign_in'}
            if before['status']=='unknown':
                return self._result(before,False,'unknown','quiescence_unverified')
            if operation in ('autofill','autofill_skills','start') and already and not can_retry and before['status'] in ('ready','complete','needs_review'):
                result=self._result(before,False,'idle','already_attempted')
                if operation=='autofill' and before.get('workday'):
                    result['instruction']='Autofill was already attempted on this Workday page. Continue after settlement; handle any actual remaining questions using approved answers. Do not click Autofill repeatedly.'
                return result
            if not active:
                control=before['controls'][operation]
                if not control['ref'] or not control['enabled']:
                    return self._result(before,False,'idle','control_disabled_or_not available')
                if not can_retry and decision['action']!=operation:
                    return self._result(before,False,'unknown' if before['status']=='unknown' else 'idle',decision['reason'])
                args={'ref':control['ref'],'url':before['url'],'operation':operation}
                if before.get('page_ref'):args['page_ref']=before['page_ref']
                if before.get('workday') and before.get('page_signature'):args['page_signature']=before['page_signature']
                if can_retry:args['retry']=True
                if operation=='sign_in':self.attempted.add(('sign_in',page_key))
                self.execution='possibly_executed'
                result=await asyncio.wait_for(self.page.evaluate(CLICK,args),timeout=max(0.05,self.deadline-self.clock()))
                if not isinstance(result,dict) or result.get('status') not in ('clicked','ok'):
                    if isinstance(result,dict) and result.get('clicked') is False:self.execution='not_executed'
                    if isinstance(result,dict) and result.get('reason')=='workday_native_authentication_required':
                        return dict(self._result(before,False,'idle',result['reason']),
                            instruction='The Workday authentication form appeared. Use fast_forward to sign in natively with the retained credential.')
                    return self._result(before,False,'unknown','stale_or_unconfirmed_control')
                clicked=True
                self.execution='clicked'
                if can_retry:
                    self.retries[page_key]=self.retries.get(page_key,0)+1
                elif operation in ('autofill','autofill_skills','start'):
                    self.attempted.add(page_key)
            stable_count=0;saw_active_or_change=False
            while self.clock()<self.deadline:
                current=await self.observe();changed=self._changed(before,current)
                if current['status']=='active' or changed:
                    saw_active_or_change=True
                if operation in ('autofill','autofill_skills','sign_in') and current['status'] in ('complete','needs_review'):
                    # Workday can leave the prior "complete" panel visible
                    # briefly after a click. Give its async fill time to start.
                    settled_without_change=stable_count>=1 and (not (before.get('workday') and operation=='autofill') or
                        self.clock()-(self.deadline-self.budget)>=5)
                    if saw_active_or_change or settled_without_change:
                        return self._result(current,changed,'idle','observed_change' if changed else 'no_observable_progress')
                    stable_count+=1
                if operation in ('continue','start','sign_in') and self._page_changed(before,current) and current['status'] not in ('active','unknown'):
                    return self._result(current,True,'idle','page_changed_rediscover_controls')
                if operation=='sign_in' and current['status']=='login_required' and self.clock()-(self.deadline-self.budget)>5:
                    return self._result(current,changed,'idle','sign_in_response_needs_inspection')
                await self.sleep(self.poll)
            page_or_field_changed = self._page_changed(before,current) if operation in ('continue','start') else self._changed(before,current)
            return self._result(current,page_or_field_changed,'unknown','autofill_budget_timeout')
        except (asyncio.TimeoutError,ValueError,RuntimeError):
            page_or_field_changed = self._page_changed(before,current) if operation in ('continue','start') else self._changed(before,current)
            return self._result(current,page_or_field_changed,'unknown' if self.execution!='not_executed' or active or before['status']=='unknown' else 'idle','observation_unavailable')
        finally:self.deadline=None
