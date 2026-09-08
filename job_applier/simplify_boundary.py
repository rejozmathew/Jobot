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
        for kind in ('autofill','continue','start','create_account_autofill','create_account','sign_in','submit'):
            item=(raw.get('controls') or {}).get(kind) or {}
            controls[kind]={'ref':item.get('ref') if isinstance(item.get('ref'),str) else None,'enabled':item.get('enabled') is True}
        result={key:raw[key] for key in ('url','fingerprint','page_ref','page_signature') if key in raw and isinstance(raw[key],str)}
        result.update(panel=raw.get('panel') is True,status=raw['status'],controls=controls,
            source='fixture' if raw.get('source')=='fixture' else 'observed_dom')
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
        if status=='active':return {'action':'wait','reason':'autofill_active'}
        if status in ('unsupported','missing','login_required'):return {'action':'fallback','reason':status}
        if status=='unknown':return {'action':'fallback','reason':'controls_unavailable'}
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

    @staticmethod
    def _result(observed,changed,writer,reason):
        return {'status':observed.get('status','unknown'),'changed':bool(changed),
            'writer_state':writer,'reason':reason,'native_takeover_authorized':writer=='idle',
            'observation':observed}

    async def perform(self,operation,*,retry=False):
        if operation not in ('autofill','continue','start'):raise ValueError('Unsupported Simplify operation')
        self.deadline=self.clock()+self.budget
        before=await self.observe();current=before
        page_key=before.get('page_signature') or before['url']
        already=page_key in self.attempted
        can_retry=(bool(retry) and self.fast and operation=='autofill' and already
            and before['status'] in ('ready','complete','needs_review')
            and bool(before.get('controls',{}).get('autofill',{}).get('enabled'))
            and self.retries.get(page_key,0)<1)
        decision=self.decide(before,already and not can_retry,fast=self.fast)
        active=before['status']=='active';clicked=False
        try:
            if before['status']=='unknown':
                return self._result(before,False,'unknown','quiescence_unverified')
            if operation in ('autofill','start') and already and not can_retry and before['status'] in ('ready','complete','needs_review'):
                return self._result(before,False,'idle','already_attempted')
            if not active:
                control=before['controls'][operation]
                if not control['ref'] or not control['enabled']:
                    return self._result(before,False,'idle','control_disabled_or_not available')
                if not can_retry and decision['action']!=operation:
                    return self._result(before,False,'unknown' if before['status']=='unknown' else 'idle',decision['reason'])
                args={'ref':control['ref'],'url':before['url'],'operation':operation}
                if before.get('page_ref'):args['page_ref']=before['page_ref']
                result=await asyncio.wait_for(self.page.evaluate(CLICK,args),timeout=max(0.05,self.deadline-self.clock()))
                if not isinstance(result,dict) or result.get('status') not in ('clicked','ok'):
                    return self._result(before,False,'unknown','stale_or_unconfirmed_control')
                clicked=True
                if can_retry:
                    self.retries[page_key]=self.retries.get(page_key,0)+1
                elif operation in ('autofill','start'):
                    self.attempted.add(page_key)
            stable_count=0;saw_active_or_change=False
            while self.clock()<self.deadline:
                current=await self.observe();changed=self._changed(before,current)
                if current['status']=='active' or changed:
                    saw_active_or_change=True
                if operation=='autofill' and current['status'] in ('complete','needs_review'):
                    if saw_active_or_change or stable_count>=1:
                        return self._result(current,changed,'idle','observed_change' if changed else 'no_observable_progress')
                    stable_count+=1
                if operation in ('continue','start') and self._page_changed(before,current) and current['status'] not in ('active','unknown'):
                    return self._result(current,True,'idle','page_changed_rediscover_controls')
                await self.sleep(self.poll)
            page_or_field_changed = self._page_changed(before,current) if operation in ('continue','start') else self._changed(before,current)
            return self._result(current,page_or_field_changed,'unknown','autofill_budget_timeout')
        except (asyncio.TimeoutError,ValueError,RuntimeError):
            page_or_field_changed = self._page_changed(before,current) if operation in ('continue','start') else self._changed(before,current)
            return self._result(current,page_or_field_changed,'unknown' if clicked or active else 'idle','observation_unavailable')
        finally:self.deadline=None
