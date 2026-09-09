"""Small local workspace host. No model, network API, or expiring permission.

Owns the profile lock and a Windows Job Object. Requests use a local named pipe
and JSON bytes (never pickle); records and controls remain in the managed DB.
"""
import asyncio
from contextlib import closing
from datetime import datetime
import hashlib
import json
from multiprocessing.connection import Client as PipeClient, Listener
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import urllib.request

from .application_runtime import REPOSITORY, error_detail, handle, resolve_config
from .managed import Service
from .managed_client import LocalClient
from .managed_shared import ProtocolError, uid
from .workspace_process import FileLock, OwnedProcess, detached_launch, process_identity, process_matches


def workspace_record(service, workspace_id):
    with service.tx() as db:return dict(service._get(db,'browser_workspaces',workspace_id))


def lock_path(workspace):return Path(workspace['user_data_dir'])/'.jobbot-host.lock'


def pipe_address(config, workspace_id, host_id):
    key=hashlib.sha256(json.dumps([config['db_path'],workspace_id,host_id]).encode()).hexdigest()[:32]
    if os.name=='nt':return r'\\.\pipe\jobbot-'+key
    return str(Path(config['db_path']).parent/('host-'+key+'.sock'))


def ensure_host(config, workspace_id):
    service=Service(config['db_path'],instance_id=config['instance_id'])
    w=workspace_record(service,workspace_id);workspace=json.loads(w['config_json'])
    with FileLock(str(lock_path(workspace))+'.startup'):
        w=workspace_record(service,workspace_id)
        if w['state']=='offline' and w['host_identity_json'] and process_matches(json.loads(w['host_identity_json'])):
            deadline=time.monotonic()+8
            while process_matches(json.loads(w['host_identity_json'])) and time.monotonic()<deadline:time.sleep(.05)
            if process_matches(json.loads(w['host_identity_json'])):raise ProtocolError('workspace_host_stopping')
        if w['host_identity_json'] and process_matches(json.loads(w['host_identity_json'])):
            if not FileLock.is_locked(lock_path(workspace)):raise ProtocolError('host_lock_missing')
            return w
        # A released lock alone is not proof that an orphan browser is stopped.
        if w['browser_identity_json'] and process_matches(json.loads(w['browser_identity_json'])):
            raise ProtocolError('owned_browser_still_alive','Workspace remains isolated until the recorded child stops')
        if FileLock.is_locked(lock_path(workspace)):raise ProtocolError('workspace_owned_by_another_host')
        root=Path(config['spool_dir'])/'hosts';root.mkdir(parents=True,exist_ok=True)
        host_id=uid()
        interpreter=Path(sys.executable)
        if os.name=='nt' and interpreter.with_name('pythonw.exe').is_file():interpreter=interpreter.with_name('pythonw.exe')
        detached_launch([str(interpreter),'-m','job_applier.workspace_host','--config',config['config_path'],
                        '--workspace',workspace_id,'--host-id',host_id],cwd=REPOSITORY,
                        stdout_path=root/(workspace_id+'.out.log'),stderr_path=root/(workspace_id+'.err.log'))
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            w=workspace_record(service,workspace_id)
            if w['host_id']==host_id and w['host_identity_json'] and process_matches(json.loads(w['host_identity_json'])):
                return w
            time.sleep(.1)
        raise ProtocolError('host_start_unconfirmed','A launched host did not register in time; retain isolation and inspect '+str(root/(workspace_id+'.err.log')))


def call_host(config, session, operation, parameters, driver_id):
    service=Service(config['db_path'],instance_id=config['instance_id'])
    w=workspace_record(service,session['workspace_id'])
    if not w['host_identity_json'] or not process_matches(json.loads(w['host_identity_json'])):
        # Recovery stops/classifies the old owned session. It never blindly replays a command.
        ensure_host(config,session['workspace_id'])
        raise ProtocolError('session_recovering','Read status before retrying; the lost command was not replayed')
    address=pipe_address(config,session['workspace_id'],w['host_id'])
    message={'instance_id':config['instance_id'],'session_id':session['id'],'driver_id':driver_id,
             'operation':operation,'parameters':parameters}
    encoded=json.dumps(message).encode()
    if len(encoded)>65536:raise ProtocolError('payload_too_large')
    try:
        with PipeClient(address,family='AF_PIPE' if os.name=='nt' else 'AF_UNIX',authkey=None) as pipe:
            pipe.send_bytes(encoded)
            if not pipe.poll(150):raise ProtocolError('host_operation_timeout','Do not replay a browser write; inspect session status')
            result=json.loads(pipe.recv_bytes(4*1024*1024))
    except (OSError,EOFError) as exc:
        raise ProtocolError('host_connection_lost','Read session status; the command outcome is unknown') from exc
    if 'error' in result:raise ProtocolError(result['error']['code'],result['error']['detail'])
    return result['result']


def endpoint_info(endpoint):
    with urllib.request.urlopen(endpoint+'/json/version',timeout=2) as response:return json.load(response)


def profile_in_use(workspace):
    """Bounded OS process inventory; never operate on or terminate other browsers."""
    if os.name!='nt':raise ProtocolError('workspace_host_windows_only')
    executable=Path(workspace['browser_executable']).name.replace("'","''")
    command="Get-CimInstance Win32_Process -Filter \"Name = '"+executable+"'\" -ErrorAction Stop | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,timeout=10,
                          creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise ProtocolError('workspace_process_inventory_unavailable','Cannot verify that the configured user-data directory is unused')
    rows=json.loads(result.stdout or '[]');rows=rows if isinstance(rows,list) else [rows]
    wanted=str(Path(workspace['user_data_dir']).resolve()).casefold().replace('/','\\')
    import re
    for row in rows:
        cmd=row.get('CommandLine') or ''
        match=re.search(r'--user-data-dir(?:=|\s+)(?:"([^"]+)"|([^\s]+))',cmd,re.I)
        if match and str(Path(match[1] or match[2]).resolve()).casefold().replace('/','\\')==wanted:
            return row['ProcessId']
    return None


async def browser_command(endpoint, method, params=None):
    from .cdp_client import _WS, _CDPSession
    ws=await _WS.connect(endpoint_info(endpoint)['webSocketDebuggerUrl'])
    connection=_CDPSession(ws);await connection.start()
    try:return await connection.call(method,params,timeout=8)
    finally:await connection.close()


class WorkspaceHost:
    def __init__(self,config,workspace_id,host_id):
        self.config=config;self.workspace_id=workspace_id;self.host_id=host_id
        self.service=Service(config['db_path'],instance_id=config['instance_id'])
        self.workspace=json.loads(workspace_record(self.service,workspace_id)['config_json'])
        self.browser=None;self.busy=threading.Lock();self.exit=threading.Event()
        self.preparing=set();self.threads=[]
        self.retire=False;self.requests=0

    def active_session(self):
        with self.service.tx() as db:
            row=db.execute('SELECT * FROM application_sessions WHERE workspace_id=? AND ended_at IS NULL',(self.workspace_id,)).fetchone()
            return dict(row) if row else None

    def start_browser(self):
        w=self.workspace
        if self.browser and self.browser.alive():return
        if not Path(w['browser_executable']).is_file():raise ProtocolError('browser_executable_missing',w['browser_executable'])
        if not Path(w['user_data_dir']).is_dir():raise ProtocolError('workspace_profile_not_prepared',w['user_data_dir'])
        try:endpoint_info(w['cdp_url'])
        except (OSError,ValueError):pass
        else:raise ProtocolError('workspace_endpoint_already_in_use','A responding browser is not owned by this host')
        if profile_in_use(w):raise ProtocolError('workspace_profile_already_in_use','Never launch a second browser against a live user-data directory')
        args=[w['browser_executable'],'--user-data-dir='+w['user_data_dir'],
              '--remote-debugging-address=127.0.0.1','--remote-debugging-port='+str(urlsplit(w['cdp_url']).port),
              '--enable-automation','--no-first-run','--no-default-browser-check','about:blank']
        if w['mode']=='headless':args.insert(-1,'--headless=new')
        else:args.insert(-1,'--start-maximized')
        root=Path(self.config['spool_dir'])/'hosts'
        self.browser=OwnedProcess.launch(args,cwd=REPOSITORY,stdout_path=root/(w['id']+'.browser.out.log'),stderr_path=root/(w['id']+'.browser.err.log'))
        self.service.host_seen(w['id'],self.host_id,self.browser.identity)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if not self.browser.alive():raise ProtocolError('browser_exited_during_start','See workspace browser log')
            try:endpoint_info(w['cdp_url']);return
            except (OSError,ValueError):time.sleep(.2)
        raise ProtocolError('browser_endpoint_not_ready',w['cdp_url'])

    async def prepare_target(self, session):
        w=self.workspace;endpoint=w['cdp_url']
        observed=(await browser_command(endpoint,'Browser.getBrowserCommandLine'))['arguments']
        args={arg.split('=',1)[0]:arg.split('=',1)[1] if '=' in arg else True for arg in observed}
        if str(Path(str(args.get('--user-data-dir',''))).resolve()).casefold()!=str(Path(w['user_data_dir']).resolve()).casefold():
            raise ProtocolError('browser_profile_mismatch')
        mode='headless' if '--headless' in args else 'headed'
        if mode!=w['mode']:raise ProtocolError('browser_mode_mismatch')
        target=(await browser_command(endpoint,'Target.createTarget',{'url':'about:blank'}))['targetId']
        from .cdp_client import CDPBrowser
        from .managed_identity import is_same_application_scope,application_match
        browser=await CDPBrowser.connect(endpoint,target_id=target,expected_mode=mode)
        try:
            page=await browser.get_current_page();job=self.service.job(session['job_id'])
            window_state='headless'
            if mode=='headed':
                try:
                    window=await browser_command(endpoint,'Browser.getWindowForTarget',{'targetId':target})
                    await browser_command(endpoint,'Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':{'windowState':'maximized'}})
                    bounds=await browser_command(endpoint,'Browser.getWindowBounds',{'windowId':window['windowId']})
                    window_state=bounds['bounds'].get('windowState','unconfirmed')
                except Exception:window_state='maximize_requested'
            try:await page.goto(job['url'])
            except asyncio.TimeoutError:
                pass  # A delayed navigation response is resolved by owned reads.
            deadline=time.monotonic()+20
            observed_url=''
            recovery=None
            while time.monotonic()<deadline:
                observed_url=await page.evaluate('location.href')
                if is_same_application_scope(job['url'],observed_url) and await page.evaluate("document.readyState!=='loading'"):break
                await asyncio.sleep(.2)
            else:
                identity=application_match(job['url'],observed_url)
                recovery={'reason':'application_page_loading' if identity['status']=='same_job' else identity['status'],
                    'instruction':'The owned tab remains available. Inspect snapshot/screenshot, wait for loading, or navigate back to the assigned job.'}
            readiness={'profile_verified':True,'endpoint_verified':True,'target_operable':True,'browser_mode':mode,
                       'simplify':'unverified','observed_at':self.service.now(),'window_state':window_state,
                       'viewport':await page.evaluate('({width:innerWidth,height:innerHeight})')}
            if self.config.get('require_simplify',True):
                from .simplify_boundary import SimplifyBoundary
                boundary=SimplifyBoundary(page,budget_seconds=5)
                deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    try:obs=await boundary.observe()
                    except asyncio.TimeoutError:
                        await asyncio.sleep(.4);continue
                    if obs.get('panel') and obs.get('source')!='fixture':
                        readiness['simplify']='official_panel_observed';break
                    await asyncio.sleep(.4)
                else:
                    readiness['simplify']='not_observed'
                    recovery=recovery or {'reason':'simplify_setup_required',
                        'instruction':'Inspect the owned tab and recover the configured Simplify extension, then continue in this session.'}
            if recovery:readiness['recovery']=recovery
            return target,readiness
        finally:await browser.close()

    def prepare(self, session):
        try:
            with self.busy:
                self.start_browser()
                target,ready=asyncio.run(self.prepare_target(session))
                current=self.service.session(session['id'])
                with self.service.tx() as db:control=self.service._get(db,'runs',current['run_id'])['control']
                if control!='running':raise ProtocolError('startup_cancelled')
                self.service.session_connected(session['id'],self.host_id,target,ready)
        except Exception as exc:
            detail=error_detail(exc)
            self.stop_session(session,detail['code']+': '+detail['detail'])
        finally:self.preparing.discard(session['id'])

    def stop_session(self,session,reason,paused=False):
        # Closing the Job Object terminates all descendants, including Simplify.
        if self.browser:
            self.browser.stop()
            if process_matches(self.browser.identity):raise ProtocolError('owned_browser_stop_unconfirmed')
            self.browser=None
        self.service.session_stopped(session['id'],reason=reason,paused=paused,browser_stopped=True)
        self.service.host_seen(self.workspace_id,self.host_id,None)
        if not paused:self.retire=True

    def inspection_result(self,session_id,reason='confirmation_not_captured'):
        return {'status':'submission_unknown','reason':reason,'session_id':session_id,
                'next_step':'Inspect the owned screenshot/snapshot or reconcile confirmation. Do not submit again. The session remains open until completion, Stop, or the configured maximum runtime.'}

    def dispatch(self, request):
        try:
            result=self._dispatch(request)
            if isinstance(result,dict) and result.get('status')=='submission_unknown':
                result.update(self.inspection_result(request['session_id'],result.get('reason','confirmation_not_captured')))
            return result
        except Exception as exc:
            # Keep the real helper failure visible without ending the application.
            # Never attribute an invalid or foreign driver's request to this session.
            try:
                session=self.service.session(request['session_id'])
                if (request.get('instance_id')==self.config['instance_id'] and
                    session['workspace_id']==self.workspace_id and session['driver_id']==request.get('driver_id') and
                    session['attempt_id'] and not session['ended_at']):
                    a=self.service.attempt(session['attempt_id']);detail=error_detail(exc)
                    self.service.event(a['id'],worker_id=a['worker_id'],fence=a['fence'],event_id=uid(),
                        event_type='recovery',observed_at=self.service.now(),payload={
                            'phase':'helper_exception','activity':str(request.get('operation','Helper'))+' returned an error',
                            'error_type':detail['code'],'evidence':detail['detail'],'source':'Workspace host','status':'error',
                            'next_step':'Executor inspects the error and submission state before choosing a recovery'})
                    if a['submission_pending']:
                        result=self.inspection_result(session['id'],detail['code'])
                        result['diagnostic']=detail;return result
            except Exception:pass  # Retain the original exception if recording also fails.
            raise

    def _dispatch(self, request):
        if request.get('instance_id')!=self.config['instance_id']:raise ProtocolError('instance_mismatch')
        session=self.service.session(request['session_id'])
        if session['workspace_id']!=self.workspace_id:raise ProtocolError('workspace_mismatch')
        if session['driver_id']!=request.get('driver_id'):raise ProtocolError('driver_owned_elsewhere')
        if request.get('operation')=='shutdown':
            if self.active_session():raise ProtocolError('workspace_still_occupied')
            self.exit.set();return {'host_shutdown_requested':True}
        if session['state'] not in ('connected','waiting'):raise ProtocolError('local_session_not_connected')
        op=request['operation'];params=request.get('parameters') or {}
        if not isinstance(params,dict):raise ProtocolError('invalid_payload')
        service=Service(self.config['db_path'],instance_id=self.config['instance_id'])
        client=LocalClient(self.config,service=service,authority=(session['id'],session['driver_id'],self.host_id))
        attempt=service.attempt(session['attempt_id'])
        own={'attempt_id':attempt['id'],'worker_id':attempt['worker_id'],'fence':attempt['fence']}
        client.call('heartbeat',**own)
        if op=='finish' and attempt['submission_pending'] and params.get('outcome') not in ('applied','already_applied'):
            return self.inspection_result(session['id'])
        cfg=dict(self.config,cdp_url=self.workspace['cdp_url'],browser_profile=self.workspace_id,browser_mode=self.workspace['mode'])
        if op in ('context','report'):
            return client.call('application_context' if op=='context' else 'attempt_report',attempt_id=attempt['id'])
        if op=='fast_forward':
            from .workday_fast import advance
            return advance(cfg,client,own,dict(params,target_id=session['target_id']))
        if op=='account_lock':return service.coordinate_account(session['id'],release=params.get('release',False))
        if op in ('browser','credentials'):
            package=service.application_context(attempt['id'])
            if op=='credentials':
                service.coordinate_account(session['id'])
                from .managed_credentials import handle_credentials
                gate=client.call('browser_observe',**own,target_id=session['target_id'],cdp_url=cfg['cdp_url'])
                if not gate.get('native_takeover_authorized',gate.get('quiescent')):
                    raise ProtocolError('simplify_input_or_settlement_required')
                action=uid();started=time.monotonic();result={}
                client.call('action_start',**own,action_id=action,tool_name='credentials')
                try:result=handle_credentials(cfg,package,dict(params,target_id=session['target_id']));return result
                finally:client.call('action_end',**own,action_id=action,status='success' if result.get('values_committed') else 'failed',duration_seconds=time.monotonic()-started)
            from .application_runtime import browser_action
            return browser_action(cfg,client,own,package,session['target_id'],params)
        from .managed_api import WORKER
        prohibited={'accept_run','claim','resume_run','checkpoint','ack_run_control','ack_control','bind_target','extend_budget','next_request'}
        if op not in WORKER or op in prohibited:raise ProtocolError('unsupported_session_operation')
        if any(k in params for k in ('attempt_id','worker_id','fence','cdp_url','target_id')):raise ProtocolError('session_resolves_ownership')
        if op in ('browser_observe','target_state'):params=dict(params,target_id=session['target_id'])
        import inspect
        signature=inspect.signature(getattr(service,op)).parameters
        scoped={k:v for k,v in own.items() if k in signature}
        if 'identity_id' in signature:
            if 'identity_id' in params and params['identity_id']!=attempt['identity_id']:raise ProtocolError('context_forbidden')
            scoped['identity_id']=attempt['identity_id'];params.pop('identity_id',None)
        if 'job_id' in signature:
            if 'job_id' in params and params['job_id']!=attempt['job_id']:raise ProtocolError('context_forbidden')
            scoped['job_id']=attempt['job_id'];params.pop('job_id',None)
        result=client.call(op,**scoped,**params)
        if op=='finish':
            return {k:result.get(k) for k in ('id','job_id','outcome','evidence','completed_at','duration_seconds')}
        if op=='record_account_event' and params.get('state') in ('confirmed','verified','created_unverified'):
            service.coordinate_account(session['id'],release=True)
        return result

    def serve_requests(self,listener):
        while not self.exit.is_set():
            try:pipe=listener.accept()
            except (OSError,EOFError):return
            self.requests+=1
            try:
                if not pipe.poll(5):continue
                request=json.loads(pipe.recv_bytes(65536))
                # Readiness commits just before preparation releases this lock.
                # Allow its short tail to settle before rejecting the first call
                # from a newly connected/attached driver. Browser writes still serialize.
                if not self.busy.acquire(timeout=5):raise ProtocolError('session_operation_busy')
                try:result=self.dispatch(request)
                finally:self.busy.release()
                pipe.send_bytes(json.dumps({'result':result}).encode())
            except Exception as exc:
                try:pipe.send_bytes(json.dumps({'error':error_detail(exc)}).encode())
                except (OSError,EOFError):pass
            finally:
                pipe.close();self.requests-=1

    def run(self):
        with FileLock(lock_path(self.workspace)):
            old=workspace_record(self.service,self.workspace_id)
            if old['browser_identity_json'] and process_matches(json.loads(old['browser_identity_json'])):
                raise ProtocolError('orphan_browser_still_running')
            previous=self.active_session()
            self.service.host_registered(self.workspace_id,self.host_id,process_identity(os.getpid()))
            if previous and previous['state'] not in ('preparing','paused','capacity_wait'):
                self.service.session_stopped(previous['id'],reason='Previous host died; owned process identity is stopped. Lost command was not replayed.',browser_stopped=True)
            address=pipe_address(self.config,self.workspace_id,self.host_id)
            with Listener(address,family='AF_PIPE' if os.name=='nt' else 'AF_UNIX',authkey=None) as listener:
                server=threading.Thread(target=self.serve_requests,args=(listener,),daemon=True);server.start()
                last_seen=0
                idle_since=None
                try:
                    while not self.exit.wait(.25):
                        session=self.active_session()
                        if time.monotonic()-last_seen>5:
                            self.service.host_seen(self.workspace_id,self.host_id,self.browser.identity if self.browser else None);last_seen=time.monotonic()
                        if not session:
                            idle_since=idle_since or time.monotonic()
                            if self.retire and not self.requests and not self.busy.locked():
                                with FileLock(str(lock_path(self.workspace))+'.startup'):
                                    if not self.active_session():
                                        with self.service.tx() as db:
                                            db.execute("UPDATE browser_workspaces SET state='offline' WHERE id=? AND host_id=?",(self.workspace_id,self.host_id))
                                        break
                            if time.monotonic()-idle_since>60:break
                            continue
                        idle_since=None
                        with self.service.tx() as db:run=dict(self.service._get(db,'runs',session['run_id']))
                        maximum=self.config.get('maximum_runtime_seconds')
                        expired=maximum is not None and (datetime.fromisoformat(self.service.now())-datetime.fromisoformat(session['requested_at'])).total_seconds()>maximum
                        # Startup owns the child reference until it observes the pending
                        # control. Never acknowledge stop while a launch can still occur.
                        if session['id'] in self.preparing:continue
                        if session['state']=='finishing' or run['control'] in ('pause_requested','stop_requested') or expired:
                            self.stop_session(session,'Maximum runtime reached' if expired else session['reason'] or run['control'],
                                              paused=run['control']=='pause_requested' and not expired)
                        elif self.browser and not self.browser.alive() and session['state'] in ('connected','waiting'):
                            self.stop_session(session,'Owned browser exited; inspect exact submission state before retry')
                        elif session['state']=='preparing' and session['id'] not in self.preparing:
                            self.preparing.add(session['id'])
                            thread=threading.Thread(target=self.prepare,args=(session,),daemon=True);thread.start();self.threads.append(thread)
                finally:
                    self.exit.set()
                    if self.browser:self.browser.stop()
                    with self.service.tx() as db:
                        db.execute("UPDATE browser_workspaces SET state='offline',browser_identity_json=NULL,updated_at=? WHERE id=? AND host_id=?",(self.service.now(),self.workspace_id,self.host_id))


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True);parser.add_argument('--workspace',required=True);parser.add_argument('--host-id',required=True)
    args=parser.parse_args()
    try:WorkspaceHost(resolve_config(args.config),args.workspace,args.host_id).run()
    except Exception as exc:
        print(json.dumps(error_detail(exc)),flush=True);return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
