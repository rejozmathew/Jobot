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
        if workspace.get('connection_mode')!='existing' and w['browser_identity_json'] and process_matches(json.loads(w['browser_identity_json'])):
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
            if not pipe.poll(150):raise ProtocolError('host_operation_timeout','The response timed out; inspect current session and browser state before choosing the next operation')
            result=json.loads(pipe.recv_bytes(4*1024*1024))
    except (OSError,EOFError) as exc:
        raise ProtocolError('host_connection_lost','Read session status; the command outcome is unknown') from exc
    if 'error' in result:raise ProtocolError(result['error']['code'],result['error']['detail'])
    return result['result']


def endpoint_info(endpoint):
    with urllib.request.urlopen(endpoint+'/json/version',timeout=2) as response:return json.load(response)


def profile_in_use(workspace):
    """Bounded OS process inventory; never operate on or terminate other browsers."""
    if os.name != 'nt':
        from .workspace_linux import linux_profile_in_use
        return linux_profile_in_use(workspace)
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
        self.startup_timing={}
        self.attachment=None

    @property
    def existing_browser(self):
        return self.workspace.get('connection_mode')=='existing'

    def active_session(self):
        with self.service.tx() as db:
            row=db.execute('SELECT * FROM application_sessions WHERE workspace_id=? AND ended_at IS NULL',(self.workspace_id,)).fetchone()
            return dict(row) if row else None

    def session_deadline(self, session):
        from .application_deadline import Deadline
        budget=json.loads(session.get('metadata_json') or '{}').get('application_deadline')
        if not budget:return Deadline(None)  # Older sessions retain their original unlimited budget.
        if not hasattr(self,'deadline_clocks'):self.deadline_clocks={}
        if session['id'] not in self.deadline_clocks:
            self.deadline_clocks[session['id']]=Deadline(budget)
        return self.deadline_clocks[session['id']]

    def expire_session(self, session):
        """Cancellation/target closure cannot wait behind a blocked browser helper."""
        from .application_deadline import request_stop,REASON
        from .hermes_desktop import cancel_driver,native_driver_id
        request_stop(self.service,[session])
        try:
            native_id=native_driver_id(session)
            cancelled=cancel_driver(self.config,session['driver_id'],native_id)
            # Preparation observes stop and owns any as-yet-unrecorded launch.
            # Closing already recorded targets also wakes stuck navigation calls.
            if session['id'] in self.preparing:
                if self.existing_browser:asyncio.run(self.close_application_tabs(session))
                return
            if not cancelled:
                # Stop browser activity, but retain supervision until native
                # cancellation is confirmed. Do not report completed cleanup.
                if self.existing_browser:asyncio.run(self.close_application_tabs(session))
                elif self.browser:self.browser.stop()
                return
            self.stop_session(session,REASON)
            self.exit.set()  # Retire even if a cancelled helper has not unwound.
        except Exception as exc:
            with self.service.tx() as db:
                db.execute('UPDATE browser_workspaces SET reason=? WHERE id=?',
                    ('Application time limit reached; cleanup pending: '+error_detail(exc)['code'],self.workspace_id))
        finally:self.deadline_cleanup=False

    def remember_native_driver(self, session):
        from .hermes_desktop import remember_driver
        try:remember_driver(self.config,self.service,session)
        finally:self.native_binding=False

    def start_browser(self):
        w=self.workspace
        if self.existing_browser:
            from .workspace_attachment import verify_connection_process,existing_profile_process
            try:info=endpoint_info(w['cdp_url'])
            except (OSError,ValueError) as exc:
                raise ProtocolError('browser_endpoint_not_ready',
                    'Open Brave using the configured shared-browser launcher. A browser opened without its debugging connection needs a one-time close and reopen; Hermes will not close your personal browser.') from exc
            pid=existing_profile_process(w)
            if not pid:raise ProtocolError('browser_profile_mismatch')
            verify_connection_process(w,pid)
            self.attachment={'browser_id':info['webSocketDebuggerUrl'],'process_identity':process_identity(pid)}
            self.startup_timing['browser_endpoint_ready_at']=self.service.now()
            # This process belongs to the user. Never put it in OwnedProcess or
            # browser_identity_json, both of which mean process-lifetime ownership.
            return
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
        self.startup_timing['browser_launch_requested_at']=self.service.now()
        self.browser=OwnedProcess.launch(args,cwd=REPOSITORY,stdout_path=root/(w['id']+'.browser.out.log'),stderr_path=root/(w['id']+'.browser.err.log'))
        self.service.host_seen(w['id'],self.host_id,self.browser.identity)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if not self.browser.alive():raise ProtocolError('browser_exited_during_start','See workspace browser log')
            try:
                endpoint_info(w['cdp_url'])
                self.startup_timing['browser_endpoint_ready_at']=self.service.now();return
            except (OSError,ValueError):time.sleep(.2)
        raise ProtocolError('browser_endpoint_not_ready',w['cdp_url'])

    async def prepare_target(self, session):
        if self.session_deadline(session).expired():raise ProtocolError('application_time_limit')
        w=self.workspace;endpoint=w['cdp_url']
        if self.existing_browser:
            mode=w['mode']
            # Save the unique marker BEFORE creation: a host crash between CDP
            # creation and saving its id can still reclaim this exact blank tab.
            attachment={**self.attachment,'marker':'about:blank#jobbot-'+uid(),'target_ids':[]}
            self.service.session_browser_attachment(session['id'],self.host_id,attachment)
            target=(await browser_command(endpoint,'Target.createTarget',{'url':attachment['marker']}))['targetId']
            attachment['target_ids']=[target]
            self.service.session_browser_attachment(session['id'],self.host_id,attachment,target)
        else:
            observed=(await browser_command(endpoint,'Browser.getBrowserCommandLine'))['arguments']
            args={arg.split('=',1)[0]:arg.split('=',1)[1] if '=' in arg else True for arg in observed}
            if str(Path(str(args.get('--user-data-dir',''))).resolve()).casefold()!=str(Path(w['user_data_dir']).resolve()).casefold():
                raise ProtocolError('browser_profile_mismatch')
            mode='headless' if '--headless' in args else 'headed'
            if mode!=w['mode']:raise ProtocolError('browser_mode_mismatch')
            target=(await browser_command(endpoint,'Target.createTarget',{'url':'about:blank'}))['targetId']
        from .cdp_client import CDPBrowser,NavigationTrace
        from .managed_identity import is_same_application_scope,application_match,application_start_url
        browser=await CDPBrowser.connect(endpoint,target_id=target,expected_mode=mode)
        try:
            page=await browser.get_current_page();job=self.service.job(session['job_id'])
            employer_storage={'status':'retained'}
            if self.existing_browser:
                employer_storage['reason']='Shared browser retains cookies and other user tabs'
            if not self.existing_browser and not session.get('attempt_id') and json.loads(session.get('metadata_json') or '{}').get('fresh_employer_storage'):
                parsed=urlsplit(job['url']);origin=parsed.scheme+'://'+parsed.netloc
                try:
                    # This host owns the entire process. Close restored page tabs
                    # before clearing so an old application cannot repopulate data.
                    targets=(await browser_command(endpoint,'Target.getTargets'))['targetInfos']
                    for old in targets:
                        if old['type']=='page' and old['targetId']!=target:
                            closed=await browser_command(endpoint,'Target.closeTarget',{'targetId':old['targetId']})
                            if not closed.get('success'):raise ProtocolError('restored_page_close_unconfirmed')
                    await page._session.call('Storage.clearDataForOrigin',{'origin':origin,'storageTypes':'all'})
                except Exception as exc:
                    raise ProtocolError('employer_storage_cleanup_failed','Retry did not open the employer page; its prior browser data could not be cleared') from exc
                employer_storage={'status':'cleared','origin':origin}
            window_state='retained' if self.existing_browser and mode=='headed' else 'headless'
            if mode=='headed' and not self.existing_browser:
                try:
                    window=await browser_command(endpoint,'Browser.getWindowForTarget',{'targetId':target})
                    await browser_command(endpoint,'Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':{'windowState':'maximized'}})
                    bounds=await browser_command(endpoint,'Browser.getWindowBounds',{'windowId':window['windowId']})
                    window_state=bounds['bounds'].get('windowState','unconfirmed')
                except Exception:window_state='maximize_requested'
            self.startup_timing['employer_navigation_requested_at']=self.service.now()
            navigation=await NavigationTrace.start(page,job['url'])
            try:await page.goto(application_start_url(job['url']))
            except asyncio.TimeoutError:
                pass  # A delayed navigation response is resolved by owned reads.
            deadline=time.monotonic()+20
            observed_url=''
            recovery=None
            while time.monotonic()<deadline:
                observed_url=await page.evaluate('location.href')
                if (is_same_application_scope(job['url'],observed_url) or navigation and navigation.accepts(observed_url)) and await page.evaluate("document.readyState!=='loading'"):break
                await asyncio.sleep(.2)
            else:
                identity=application_match(job['url'],observed_url)
                recovery={'reason':'application_page_loading' if identity['status']=='same_job' else identity['status'],
                    'instruction':'The owned tab remains available. Inspect snapshot/screenshot, wait for loading, or navigate back to the assigned job.'}
            readiness={'profile_verified':True,'endpoint_verified':True,'target_operable':True,'browser_mode':mode,
                       'simplify':'unverified','observed_at':self.service.now(),'window_state':window_state,
                       'employer_storage':employer_storage,'startup_timing':dict(self.startup_timing),
                       'viewport':await page.evaluate('({width:innerWidth,height:innerHeight})')}
            if navigation and navigation.accepts(observed_url):
                readiness['application_navigation']={'url':observed_url,'chain':list(navigation.chain)}
            if navigation:navigation.close()
            readiness['connection_mode']='existing' if self.existing_browser else 'managed'
            readiness['navigator_webdriver']=await page.evaluate('navigator.webdriver')
            from .managed_context import platform_for_url
            linkedin=platform_for_url(job['url'])=='linkedin'
            if linkedin:
                from .browser_controls import observe
                readiness['observation']=await observe(page,{'job':job,'attempt':{}})
                readiness['simplify']='optional_native_helper'
            if self.config.get('require_simplify',True) and not linkedin:
                from .simplify_boundary import SimplifyBoundary
                boundary=SimplifyBoundary(page,budget_seconds=5)
                deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    try:obs=await boundary.observe()
                    except asyncio.TimeoutError:
                        await asyncio.sleep(.4);continue
                    if obs.get('panel') and obs.get('source')!='fixture':
                        readiness['simplify']='official_panel_observed'
                        readiness['observation']={k:obs.get(k) for k in ('status','controls','document_id','page_signature')}
                        break
                    await asyncio.sleep(.4)
                else:
                    readiness['simplify']='not_observed'
                    recovery=recovery or {'reason':'simplify_setup_required',
                        'instruction':'Inspect loading on the owned tab. If Simplify remains missing, use browser reload; if still unusable, use session restart and continue. This applies to every portal. Recover the configured extension or use approved native controls after fresh writer observation; do not finish merely because the panel is missing.'}
            if recovery:readiness['recovery']=recovery
            from .browser_controls import next_operation
            from .managed_context import platform_for_url
            readiness['next_operation']=next_operation(platform_for_url(job['url']),readiness.get('observation'),settings=self.service.settings_view()['values'])
            readiness['observed_at']=self.service.now()
            return target,readiness
        finally:await browser.close()

    def prepare(self, session):
        try:
            with self.busy:
                if self.session_deadline(session).expired():raise ProtocolError('application_time_limit')
                self.start_browser()
                target,ready=asyncio.run(self.prepare_target(session))
                current=self.service.session(session['id'])
                with self.service.tx() as db:control=self.service._get(db,'runs',current['run_id'])['control']
                if self.session_deadline(session).expired():raise ProtocolError('application_time_limit')
                if control!='running':raise ProtocolError('startup_cancelled')
                self.service.session_connected(session['id'],self.host_id,target,ready)
        except Exception as exc:
            detail=error_detail(exc)
            self.stop_session(session,detail['code']+': '+detail['detail'])
        finally:self.preparing.discard(session['id'])

    async def close_application_tabs(self,session):
        """Close only durable application-owned targets; never Browser.close.

        Re-checks and descendant ids are persisted before closure, so a host
        crash during cleanup cannot strand a known popup or touch personal tabs.
        """
        session=self.service.session(session['id'])
        attachment=json.loads(session['metadata_json']).get('browser_attachment') or {}
        if not attachment:return
        endpoint=self.workspace['cdp_url']
        try:current=endpoint_info(endpoint)['webSocketDebuggerUrl']
        except (OSError,ValueError):
            identity=attachment.get('process_identity')
            if identity and not process_matches(identity):return
            raise ProtocolError('application_tab_close_unconfirmed','Existing browser is temporarily unreachable; tab cleanup remains pending')
        if current!=attachment['browser_id']:
            # The old browser incarnation is gone; never close a tab in its replacement.
            return
        targets=(await browser_command(endpoint,'Target.getTargets'))['targetInfos']
        owned=set(attachment.get('target_ids',[]))
        if session.get('target_id'):owned.add(session['target_id'])
        owned.update(t['targetId'] for t in targets if attachment.get('marker') and t.get('url')==attachment['marker'])
        while True:
            descendants={t['targetId'] for t in targets if t.get('type')=='page' and t.get('openerId') in owned}
            if descendants<=owned:break
            owned.update(descendants)
        attachment['target_ids']=sorted(owned)
        self.service.session_browser_attachment(session['id'],self.host_id,attachment)
        present={t['targetId'] for t in targets if t.get('type')=='page'} & owned
        if present and not any(t.get('type')=='page' and t['targetId'] not in owned for t in targets):
            # Chromium exits when its last page closes. Leave a neutral tab if
            # the user has closed their dashboard/mail during the application.
            await browser_command(endpoint,'Target.createTarget',{'url':'about:blank'})
        # Close popups first, root last. A fresh inventory is the acknowledgement,
        # not the return value of closeTarget (the user may already have closed it).
        for target in sorted(present,key=lambda t:t==session.get('target_id')):
            try:await browser_command(endpoint,'Target.closeTarget',{'targetId':target})
            except RuntimeError:pass
        remaining=(await browser_command(endpoint,'Target.getTargets'))['targetInfos']
        if any(t['targetId'] in owned or t.get('openerId') in owned for t in remaining if t.get('type')=='page'):
            raise ProtocolError('application_tab_close_unconfirmed','Application tab closure is not yet confirmed')

    def stop_session(self,session,reason,paused=False):
        if self.existing_browser:
            asyncio.run(self.close_application_tabs(session))
            self.service.session_stopped(session['id'],reason=reason,paused=paused,tabs_closed=True)
            self.service.host_seen(self.workspace_id,self.host_id,None)
            if not paused:self.retire=True
            return
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
                'submission_confirmed':False,
                'next_step':'Inspect the current page. Complete visible required work, including email verification, in this session. A click is not success and does not lock editing. Finish on actual accepted confirmation; otherwise continue recovery and verification.'}

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
        if self.session_deadline(session).expired():
            from .application_deadline import request_stop
            request_stop(self.service,[session])
            raise ProtocolError('application_time_limit','The saved application deadline has expired; supervision is stopping this attempt.')
        op=request['operation'];params=request.get('parameters') or {}
        if not isinstance(params,dict):raise ProtocolError('invalid_payload')
        service=Service(self.config['db_path'],instance_id=self.config['instance_id'])
        client=LocalClient(self.config,service=service,authority=(session['id'],session['driver_id'],self.host_id))
        attempt=service.attempt(session['attempt_id'])
        own={'attempt_id':attempt['id'],'worker_id':attempt['worker_id'],'fence':attempt['fence']}
        client.call('heartbeat',**own)
        cfg=dict(self.config,cdp_url=self.workspace['cdp_url'],browser_profile=self.workspace_id,browser_mode=self.workspace['mode'])
        if op in ('context','report'):
            return client.call('application_context' if op=='context' else 'attempt_report',attempt_id=attempt['id'])
        if op=='restart':
            # Reuse pause/attach: termination proves cancellation, then the host
            # opens a new target with the same account/profile/session/attempt.
            # Mark preparing first so the monitor cannot mistake this for a crash.
            self.preparing.add(session['id'])
            try:
                client.call('event',**own,event_id=uid(),event_type='recovery',observed_at=service.now(),
                    payload={'operation':'restart','evidence':'Executor requested recovery of the owned browser',
                             'next_step':'Reopen the assigned job in the same attempt and continue'})
                self.stop_session(session,'Executor requested browser recovery',paused=True)
                resumed=self.service.attach_session(session['id'],session['driver_id'])
                thread=threading.Thread(target=self.prepare,args=(resumed,),daemon=True)
                thread.start();self.threads.append(thread)
            except Exception:
                self.preparing.discard(session['id']);raise
            return {**handle(service,session['id'],include_context=False),
                    'instruction':('The application tab is reopening; the shared browser and your other tabs stay open. '
                        if self.existing_browser else 'The owned browser is restarting. ')+
                        'This is the same attempt. Read status until connected, then inspect and continue; this is not an application outcome.'}
        if op in ('fast_forward','linkedin_easy_apply','greenhouse_advance','icims_advance'):
            if op=='icims_advance':from .icims_fast import advance
            elif op=='greenhouse_advance':from .greenhouse_fast import advance
            elif op=='linkedin_easy_apply':from .linkedin_easy_apply import advance
            else:from .workday_fast import advance
            return advance(cfg,client,own,dict(params,target_id=session['target_id']))
        if op=='account_lock':return service.coordinate_account(session['id'],release=params.get('release',False))
        if op in ('browser','credentials'):
            package=service.application_context(attempt['id'])
            if op=='credentials':
                if params.get('mode')!='verification':service.coordinate_account(session['id'])
                from .managed_credentials import handle_credentials,credential_progress
                gate=client.call('browser_observe',**own,target_id=session['target_id'],cdp_url=cfg['cdp_url'])
                if not gate.get('native_takeover_authorized',gate.get('quiescent')):
                    raise ProtocolError('simplify_input_or_settlement_required',
                        'Observe or cancel ongoing Simplify work. For a broken page or missing panel before submission, use browser reload or session restart, then inspect and continue.')
                action=uid();started=time.monotonic();result={}
                credential_progress(client.call,own,params)
                client.call('action_start',**own,action_id=action,tool_name='credentials')
                try:result=handle_credentials(cfg,package,dict(params,target_id=session['target_id']));return result
                finally:
                    client.call('action_end',**own,action_id=action,status='success' if result.get('values_committed') or result.get('resend_requested') or params.get('action')=='inspect' and 'groups' in result else 'failed',duration_seconds=time.monotonic()-started)
                    credential_progress(client.call,own,params,result=result,action_id=action)
            from .application_runtime import browser_action
            return browser_action(cfg,client,own,package,session['target_id'],params)
        from .managed_api import WORKER
        prohibited={'accept_run','claim','resume_run','checkpoint','ack_run_control','ack_control','bind_target','handoff_target','extend_budget','next_request'}
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
                # Queue operations on this physical browser instead of rejecting
                # the next call because preparation or another operation is busy.
                self.busy.acquire()
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
            if not self.existing_browser and old['browser_identity_json'] and process_matches(json.loads(old['browser_identity_json'])):
                raise ProtocolError('orphan_browser_still_running')
            previous=self.active_session()
            self.service.host_registered(self.workspace_id,self.host_id,process_identity(os.getpid()))
            if self.existing_browser and previous and json.loads(previous['metadata_json']).get('browser_attachment'):
                # Recover even a pre-readiness target from a lost host. For a
                # preparing session retain the request, then open a fresh tab.
                asyncio.run(self.close_application_tabs(previous))
                if previous['state'] not in ('preparing','paused','capacity_wait'):
                    self.stop_session(previous,'Previous host died; application tabs closed. Lost command was not replayed.')
            elif previous and previous['state'] not in ('preparing','paused','capacity_wait'):
                self.service.session_stopped(previous['id'],reason='Previous host died; owned process identity is stopped. Lost command was not replayed.',browser_stopped=True)
            address=pipe_address(self.config,self.workspace_id,self.host_id)
            if os.name == 'nt':
                listener_ctx = Listener(address, family='AF_PIPE', authkey=None)
            else:
                from .workspace_linux import create_linux_listener
                listener_ctx = create_linux_listener(address)
            with listener_ctx as listener:
                server=threading.Thread(target=self.serve_requests,args=(listener,),daemon=True);server.start()
                last_seen=0
                last_tab_check=0
                last_native_binding=0
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
                        # Read-only native identity capture runs beside browser work;
                        # an unavailable backend must not delay startup or helpers.
                        from .hermes_desktop import native_driver_id
                        if (isinstance(self.config.get('hermes_desktop'),dict) and
                            not native_driver_id(session) and
                            not getattr(self,'native_binding',False) and time.monotonic()-last_native_binding>10):
                            self.native_binding=True;last_native_binding=time.monotonic()
                            thread=threading.Thread(target=self.remember_native_driver,args=(session,),daemon=True)
                            thread.start();self.threads.append(thread)
                        with self.service.tx() as db:run=dict(self.service._get(db,'runs',session['run_id']))
                        expired=self.session_deadline(session).expired()
                        if expired:
                            if not getattr(self,'deadline_cleanup',False):
                                self.deadline_cleanup=True
                                thread=threading.Thread(target=self.expire_session,args=(session,),daemon=True)
                                thread.start();self.threads.append(thread)
                            continue
                        # Startup owns the child reference until it observes the pending
                        # control. Never acknowledge stop while a launch can still occur.
                        if session['id'] in self.preparing:continue
                        if session['state']=='finishing' or run['control'] in ('pause_requested','stop_requested'):
                            if self.busy.acquire(blocking=False):
                                try:
                                    self.stop_session(session,session['reason'] or run['control'],paused=run['control']=='pause_requested')
                                except Exception as exc:
                                    with self.service.tx() as db:
                                        db.execute('UPDATE browser_workspaces SET reason=? WHERE id=?',(error_detail(exc)['detail'],self.workspace_id))
                                finally:self.busy.release()
                        elif self.browser and not self.browser.alive() and session['state'] in ('connected','waiting'):
                            self.stop_session(session,'Owned browser exited; inspect exact submission state before retry')
                        elif session['state']=='preparing' and session['id'] not in self.preparing:
                            self.preparing.add(session['id'])
                            thread=threading.Thread(target=self.prepare,args=(session,),daemon=True);thread.start();self.threads.append(thread)
                        elif self.existing_browser and session['state'] in ('connected','waiting') and time.monotonic()-last_tab_check>2 and self.busy.acquire(blocking=False):
                            try:
                                last_tab_check=time.monotonic()
                                attachment=json.loads(session['metadata_json']).get('browser_attachment') or {}
                                try:
                                    info=endpoint_info(self.workspace['cdp_url'])
                                    targets=asyncio.run(browser_command(self.workspace['cdp_url'],'Target.getTargets'))['targetInfos']
                                    gone=info['webSocketDebuggerUrl']!=attachment.get('browser_id') or not any(t['targetId']==session['target_id'] for t in targets)
                                except (OSError,ValueError):
                                    gone=bool(attachment.get('process_identity') and not process_matches(attachment['process_identity']))
                                if gone:self.stop_session(session,'Application tab or shared browser was closed; retained submission evidence determines the outcome')
                            except Exception:pass  # Transient CDP loss does not establish closure.
                            finally:self.busy.release()
                finally:
                    self.exit.set()
                    if self.browser:self.browser.stop()
                    if self.existing_browser:
                        current=self.active_session()
                        if current and current['state']!='paused':
                            try:self.stop_session(current,'Host stopped; application tabs closed')
                            except Exception:pass  # Durable tab ownership remains for the next host.
                    with self.service.tx() as db:
                        db.execute("UPDATE browser_workspaces SET state='offline',browser_identity_json=NULL,updated_at=? WHERE id=? AND host_id=?",(self.service.now(),self.workspace_id,self.host_id))
                    if os.name != 'nt':
                        from .workspace_linux import cleanup_linux_socket
                        cleanup_linux_socket(address)


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
