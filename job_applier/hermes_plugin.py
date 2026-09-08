"""Native plugin controller. Explicit worker config, observed runtime, no agent spawn."""
import hashlib
import json
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit
from .hermes_adapter import HermesAdapter, IDENTIFIER
from .managed_client import Client
from .managed_shared import ProtocolError, uid

HOOKS=('pre_tool_call','post_tool_call','pre_api_request','post_api_request','api_request_error')
OPERATIONS=('start','attach','pause','stop','retry','reconcile','browser','account_lock','status','accept','next','context','report','observe','mail_request','mail_match','record_account_event','report_upload','extend_budget','bind_target','target_state','finish','milestone','checkpoint','resume','heartbeat','ack_control','writer_state','submission_intent','account_strategy','browser_observe','credentials','fast_forward')
SCHEMA={'name':'jobbot','description':'Start one local application from a URL, use its owned browser and shared helpers, and record verified outcomes. No model is launched.',
    'parameters':{'type':'object','properties':{'operation':{'type':'string','enum':list(OPERATIONS)},'parameters':{'type':'object'}},'required':['operation'],'additionalProperties':False}}


class PluginController:
    def __init__(self, config_path):
        self.config_path=config_path
        self.adapters={}
        self.runtime={}
        self.local_sessions={}
        self._stop=threading.Event()
        self._thread=None
        self._lock=threading.RLock()

    def _config(self):
        if not self.config_path or not Path(self.config_path).is_absolute():raise ProtocolError('integration_not_configured')
        try:cfg=json.loads(Path(self.config_path).read_text(encoding='utf-8'))
        except (OSError,ValueError):raise ProtocolError('integration_not_configured')
        if not isinstance(cfg,dict):raise ProtocolError('integration_not_configured')
        if cfg.get('transport')=='local':
            from .application_runtime import resolve_config
            return resolve_config(self.config_path)
        required=('base_url','instance_id','worker_id','browser_profile','skill_version','provider','model','worker_token_env','spool_dir')
        if not isinstance(cfg,dict) or not all(isinstance(cfg.get(k),str) and cfg[k] for k in required):raise ProtocolError('integration_not_configured')
        if not Path(cfg['spool_dir']).is_absolute():raise ProtocolError('absolute_outbox_path_required')
        from .managed_cli import credential_available
        if not credential_available(cfg['worker_token_env'],cfg):raise ProtocolError('worker_credentials_unavailable')
        return cfg

    def available(self):
        try:self._config();return True
        except ProtocolError:return False

    def _observe_runtime(self, kwargs):
        sid=kwargs.get('session_id')
        if not isinstance(sid,str) or not sid:return
        result={}
        for key in ('model','provider','response_model'):
            value=kwargs.get(key)
            if isinstance(value,str) and IDENTIFIER.fullmatch(value):result[key]=value
        try:
            u=urlsplit(kwargs.get('base_url') or '')
            result['subscription_route']=(u.scheme=='https' and u.hostname=='chatgpt.com' and u.path.startswith('/backend-api/codex') and not u.query and not u.username and not u.password)
        except (ValueError,TypeError):result['subscription_route']=False
        rc=kwargs.get('reasoning_config')
        effort=None
        if isinstance(rc,dict):
            effort=rc.get('effort')
            result['reasoning_config']=rc
        elif hasattr(rc,'effort'):
            effort=getattr(rc,'effort')
            result['reasoning_config']={'effort':effort}
        elif isinstance(rc,str):
            effort=rc
            result['reasoning_config']={'effort':effort}
        if not effort and isinstance(kwargs.get('reasoning_effort'),str):
            effort=kwargs.get('reasoning_effort')
        if isinstance(effort,str):
            result['reasoning_effort']=effort.lower()
        with self._lock:self.runtime[sid]=result

    def route(self, name, **kwargs):
        if name=='post_api_request':self._observe_runtime(kwargs)
        if kwargs.get('session_id') in self.local_sessions:
            tool=kwargs.get('tool_name') or kwargs.get('name') or ''
            if name=='pre_tool_call' and tool.startswith('browser'):
                return {'action':'block','message':'This application has its own workspace. Use jobbot browser or fast_forward so actions stay scoped to its session.'}
            return None
        with self._lock:adapter=self.adapters.get(kwargs.get('session_id'))
        if adapter is None:return None
        try:return getattr(adapter,name)(**kwargs)
        except Exception:
            return {'action':'block','message':'JobBot: adapter_unavailable'} if name=='pre_tool_call' else None

    def _adapter(self, sid, cfg):
        if not isinstance(sid,str) or not IDENTIFIER.fullmatch(sid):raise ProtocolError('worker_session_required')
        observed=self.runtime.get(sid,{})
        if observed.get('provider')!=cfg['provider'] or observed.get('model')!=cfg['model'] or observed.get('response_model')!=cfg['model']:
            raise ProtocolError('requested_runtime_not_verified')
        if cfg['provider']=='openai-codex' and not observed.get('subscription_route'):
            raise ProtocolError('subscription_route_not_verified')
        if cfg.get('reasoning_effort') and observed.get('reasoning_effort') and observed['reasoning_effort']!=cfg['reasoning_effort']:
            raise ProtocolError('requested_runtime_not_verified')
        with self._lock:
            if sid not in self.adapters:
                from .managed_cli import credential
                client=Client(cfg['base_url'],cfg['instance_id'],credential(cfg['worker_token_env'],cfg))
                try:
                    health=client.call('health')
                    if health.get('instance_id')!=cfg['instance_id']:raise ProtocolError('instance_mismatch')
                    spool=Path(cfg['spool_dir'])/(hashlib.sha256(sid.encode()).hexdigest()+'.db')
                    self.adapters[sid]=HermesAdapter(client,worker_id=cfg['worker_id'],session_id=sid,
                        browser_profile=cfg['browser_profile'],skill_version=cfg['skill_version'],
                        provider=cfg['provider'],model=cfg['model'],spool_path=spool,
                        reasoning_effort=cfg.get('reasoning_effort'))
                except Exception:
                    client.close();raise
            return self.adapters[sid]

    def _start_pulse(self):
        if self._thread and self._thread.is_alive():return
        def pulse():
            while not self._stop.wait(10):
                with self._lock:adapters=list(self.adapters.values())
                for adapter in adapters:
                    if self._stop.is_set():break
                    try:
                        adapter.flush()
                        context=adapter._state().get('attempt')
                        if context:adapter.client.call('heartbeat',**context)
                    except Exception:
                        # Liveness failure never refreshes verified progress or revives ownership.
                        adapter.last_error='heartbeat_unavailable'
        self._thread=threading.Thread(target=pulse,name='jobbot-heartbeat',daemon=True)
        self._thread.start()

    def handle(self, args, **kwargs):
        try:
            cfg=self._config()
            op=args.get('operation')
            params=args.get('parameters') or {}
            if op not in OPERATIONS or not isinstance(params,dict):raise ProtocolError('invalid_operation')
            sid=kwargs.get('session_id')
            if cfg.get('transport')=='local':
                return json.dumps(self._handle_local(cfg,op,dict(params),sid),ensure_ascii=False)
            if op=='status':
                return json.dumps({'available':True,'runtime':self.runtime.get(sid),'bound':sid in self.adapters})
            adapter=self._adapter(sid,cfg)
            if op=='accept':
                result=adapter.accept(params['run_id']);self._start_pulse()
            elif op=='next':
                result=adapter.claim()
                if result:result=dict(result,context=adapter.client.call('application_context',attempt_id=result['id'],worker_id=adapter.worker_id))
            elif op=='report':
                aid=params.get('attempt_id') or (adapter._state().get('attempt') or {}).get('attempt_id')
                result=adapter.client.call('attempt_report',attempt_id=aid,worker_id=adapter.worker_id)
            elif op=='ack_control' and not adapter._state().get('attempt'):
                if set(params)!={'quiescent'}:raise ProtocolError('invalid_payload')
                result=adapter.client.call('ack_run_control',run_id=adapter._state()['run_id'],worker_id=adapter.worker_id,quiescent=params['quiescent'])
            elif op=='resume':
                result=adapter.client.call('resume_run',run_id=params['run_id'],worker_id=adapter.worker_id,
                    session_id=adapter.session_id,capabilities=adapter.capabilities)
                with adapter._db() as db:adapter._put(db,'state',{'run_id':params['run_id'],'attempt':None})
                self._start_pulse()
            elif op=='checkpoint':
                result=adapter.client.call('checkpoint',run_id=adapter._state()['run_id'],worker_id=adapter.worker_id,
                    session_id=adapter.session_id,checkpoint_id=params['checkpoint_id'],data=params['data'])
            else:
                context=adapter._state().get('attempt')
                if not context:raise ProtocolError('no_claimed_attempt')
                if adapter.flush():raise ProtocolError('telemetry_delivery_pending')
                if op=='fast_forward':
                    from .workday_fast import advance
                    result=advance(cfg,adapter.client,context,params)
                    if result.get('status')=='applied':
                        state=adapter._state();state['attempt']=None
                        with adapter._db() as db:adapter._put(db,'state',state)
                elif op=='credentials':
                    from .managed_credentials import handle_credentials
                    package=adapter.client.call('application_context',attempt_id=context['attempt_id'],worker_id=adapter.worker_id)
                    # Binding enforces attempt ownership before the private write.
                    adapter.client.call('bind_target',**context,target_id=params['target_id'],url=package['job']['url'])
                    action_id=uid()
                    adapter.client.call('action_start',**context,action_id=action_id,tool_name='credentials')
                    import time
                    from datetime import datetime,timezone
                    started=time.monotonic()
                    result={}
                    try:
                        result=handle_credentials(cfg,package,params)
                    finally:
                        adapter.client.call('action_end',**context,action_id=action_id,
                            status='success' if result.get('values_committed') else 'failed',
                            duration_seconds=time.monotonic()-started,observed_at=datetime.now(timezone.utc).isoformat())
                elif op=='context':
                    if set(params)-{'platform','namespace'}:raise ProtocolError('invalid_payload')
                    result=adapter.client.call('application_context',attempt_id=context['attempt_id'],worker_id=adapter.worker_id,**params)
                elif op=='observe':
                    if set(params)-{'condition','action','scope','expected_result'}:raise ProtocolError('invalid_payload')
                    result=adapter.client.call('observe_owned_lesson',**context,**params)
                elif op in ('mail_request','mail_match'):
                    allowed=('namespace','purpose','requested_at','expected_sender') if op=='mail_request' else ('request_id','messages')
                    if set(params)-set(allowed):raise ProtocolError('invalid_payload')
                    result=adapter.client.call('request_mail_for_attempt' if op=='mail_request' else 'match_mail_for_attempt',**context,**params)
                elif op=='milestone':
                    result=adapter.client.call('event',**context,event_id=params.get('event_id') or uid(),
                        event_type=params['event_type'],observed_at=params['observed_at'],
                        payload=params.get('payload',{}),duration_seconds=None,action_id=None)
                elif op=='account_strategy':
                    attempt=adapter.client.call('attempt_status',attempt_id=context['attempt_id'])
                    result=adapter.client.call('account_strategy',identity_id=attempt['identity_id'],namespace=params['namespace'])
                else:
                    permitted={'finish':('outcome','evidence','quiescent'), 'heartbeat':(),
                        'writer_state':('state',),'ack_control':('quiescent',), 'submission_intent':('fixture','evidence'),
                        'record_account_event':('namespace','state','credential_ref','request_id','evidence'),
                        'report_upload':('asset_id','status','evidence'),'extend_budget':('seconds','reason'),
                        'bind_target':('target_id','url'),'target_state':('target_id','state','evidence'),
                        'browser_observe':('target_id','cdp_url','expected_url')}[op]
                    if any(k not in permitted for k in params):raise ProtocolError('invalid_payload')
                    if op=='submission_intent' and not params.get('evidence'):raise ProtocolError('invalid_payload')
                    result=adapter.client.call(op,**context,**params)
                    if op=='finish' and params.get('quiescent') is True:
                        state=adapter._state();state['attempt']=None
                        with adapter._db() as db:adapter._put(db,'state',state)
            return json.dumps(result,ensure_ascii=False)
        except Exception as exc:
            code=exc.code if isinstance(exc,ProtocolError) else 'integration_error'
            from .managed_redaction import safe_text
            return json.dumps({'status':'unavailable' if code in ('integration_not_configured','worker_credentials_unavailable') else 'error','error':code,'detail':safe_text(str(exc))[:1000]})

    def _handle_local(self,cfg,op,params,sid):
        from .application_runtime import start,session_call,driver_identity
        from .managed import Service
        driver_identity(sid)
        if op=='start':
            observed=self.runtime.get(sid,{})
            result=start(cfg,driver_id=sid,metadata={k:observed.get(k) for k in ('model','provider','reasoning_effort','response_model')},**params)
            self.local_sessions[sid]=result['session_id'];return result
        session_id=params.pop('session_id',None) or self.local_sessions.get(sid)
        if not session_id:
            service=Service(cfg['db_path'],instance_id=cfg['instance_id'])
            with service.tx() as db:
                row=db.execute('SELECT id FROM application_sessions WHERE driver_id=? ORDER BY requested_at DESC LIMIT 1',(sid,)).fetchone()
            if row:session_id=row[0];self.local_sessions[sid]=session_id
        if op=='status' and not session_id:return {'available':True,'transport':'local','runtime':self.runtime.get(sid),'bound':False,'config_path':cfg['config_path']}
        if not session_id:raise ProtocolError('start_a_local_session_first')
        if op in ('accept','next','bind_target','checkpoint','ack_control','extend_budget'):raise ProtocolError('local_session_resolves_lifecycle')
        aliases={'resume':'attach','observe':'observe_owned_lesson','milestone':'event','mail_request':'request_mail_for_attempt','mail_match':'match_mail_for_attempt'}
        operation=aliases.get(op,op)
        if operation=='event':params.setdefault('event_id',uid())
        result=session_call(cfg,session_id,operation,params,sid)
        self.local_sessions[sid]=session_id
        return result

    def close(self):
        self._stop.set()
        if self._thread:self._thread.join(timeout=1)
        with self._lock:
            for adapter in self.adapters.values():adapter.client.close()
            self.adapters.clear()
