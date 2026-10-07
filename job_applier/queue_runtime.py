"""Concurrent queue dispatcher for the current local runtime, not the legacy worker.

Each explicit queue entry gets a fresh external CLI process and private brief.
The subprocess is replaceable; JobBot owns durable intake, outcomes and scheduling.
"""
import argparse
from datetime import datetime, timedelta
import json
import logging
import sqlite3
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .application_runtime import REPOSITORY, prepare_local, resolve_config
from .application_brief import application_brief
from .managed import Service
from .managed_migrations import database_busy
from .managed_shared import ProtocolError, dumps, uid
from .workspace_process import FileLock, process_identity, process_matches


def executor_command(config, prompt_file):
    if isinstance(config.get('hermes_desktop'),dict):
        return [sys.executable,'-m','job_applier.hermes_desktop',str(prompt_file)]
    command=config.get('hermes_command')
    if command is None:
        command=['hermes','chat','-q','Read the complete application task in {prompt_file} and execute only that task.']
    if not isinstance(command,list) or not command or not all(isinstance(x,str) and x for x in command):
        raise ProtocolError('invalid_hermes_command')
    if not any('{prompt_file}' in part for part in command):
        raise ProtocolError('hermes_command_requires_prompt_file')
    result=[part.replace('{prompt_file}',str(prompt_file)) for part in command]
    from .model_settings import executor_kind
    if executor_kind(config)=='hermes_cli' and config.get('application_model'):
        # Replace earlier explicit flags instead of relying on a CLI parser's
        # duplicate-option precedence. Preserve profile and unrelated arguments.
        filtered=[];skip=False
        for part in result:
            if skip:skip=False;continue
            if part in ('--provider','--model','-m','--reasoning'):skip=True;continue
            if part.startswith(('--provider=','--model=','--reasoning=')):continue
            filtered.append(part)
        result=filtered
        result.extend(['--provider',config['application_provider'],'--model',config['application_model']])
        if config.get('application_effort'):result.extend(['--reasoning',config['application_effort']])
    return result


def private_write(path, text):
    path.parent.mkdir(parents=True,exist_ok=True)
    if os.name!='nt':path.parent.chmod(0o700)
    with open(path,'w',encoding='utf-8') as stream:
        if os.name!='nt':os.fchmod(stream.fileno(),0o600)
        stream.write(text)


def find_sessions(service, item):
    """Follow this dispatch's native conversation through replacement requests."""
    driver = None
    root = getattr(service, 'desktop_dispatch_spool', None)
    if root:
        receipt = Path(root)/'dispatch'/item['id']/'desktop-session.json'
        if receipt.exists():
            driver = json.loads(receipt.read_text()).get('stored_session_id')
    with service.read() as db:
        return [dict(row) for row in db.execute('''SELECT * FROM application_sessions
            WHERE job_id=? AND identity_id=? AND (request_id=? OR driver_id=?) ORDER BY rowid''',
            (item['job_id'], item['identity_id'], 'queue:'+item['id'], driver))]


def settle(service, item):
    """Observe durable evidence after process exit; never translate exit zero to applied."""
    sessions=find_sessions(service,item)
    active=[session for session in sessions if not session['ended_at']]
    if active:
        root=getattr(service,'desktop_dispatch_spool',None)
        path=Path(root)/'dispatch'/item['id']/'desktop-session.json' if root else None
        receipt=json.loads(path.read_text()) if path and path.exists() else {}
        from .hermes_desktop import native_driver_id
        for session in active:
            if (receipt.get('stored_session_id') and session['driver_id']!=receipt['stored_session_id']
                    and native_driver_id(session)!=receipt.get('session_id')):continue
            if session['run_id']:service.control(session['run_id'],command='stop')
            else:service.session_stopped(session['id'],reason='Executor ended before browser allocation',browser_stopped=True)
        return False  # host acknowledges owned-browser stop before the next job
    session=sessions[-1] if sessions else None
    # A later unsuccessful replacement must not downgrade an earlier submission.
    for prior in sessions:
        if prior['attempt_id'] and service.attempt(prior['attempt_id'])['outcome'] in ('applied','already_applied'):
            session=prior
            break
    attempt=service.attempt(session['attempt_id']) if session and session['attempt_id'] else None
    root=getattr(service,'desktop_dispatch_spool',None)
    timed_out=bool(root and (Path(root)/'dispatch'/item['id']/'deadline.json').exists())
    receipt_path=Path(root)/'dispatch'/item['id']/'desktop-session.json' if root else None
    receipt={};failure=None
    if receipt_path and receipt_path.exists():
        receipt=json.loads(receipt_path.read_text())
        timed_out=timed_out or receipt.get('stop_reason')=='application_time_limit'
        terminal=receipt.get('last_terminal')
        if terminal and terminal.get('status')=='error' or 'last_terminal' not in receipt:
            failure=receipt.get('last_executor_failure')
        if receipt.get('stop_reason')=='application_stop_requested':failure=None
    launch_path=Path(root)/'dispatch'/item['id']/'desktop-error.json' if root else None
    if not failure and launch_path and launch_path.exists():
        launch=json.loads(launch_path.read_text());failure={'kind':'executor_launch_'+str(launch.get('error','unknown'))}
    detail=(attempt or {}).get('evidence') or (session or {}).get('reason')
    if (attempt or {}).get('outcome') not in ('applied','already_applied','blocked','ready_for_review'):
        if timed_out:detail='application_time_limit: Application time limit reached'
        elif failure:detail='Executor failure: '+str(failure.get('kind','executor_error'))+'; browser cleanup recorded separately.'
    service.queue_complete(item['id'],outcome=(attempt or {}).get('outcome') or 'interrupted',
        detail=detail or 'Executor exited without a recorded application outcome.',
        session_id=session['id'] if session else None)
    return True


def supervise_cached_dispatches(service):
    # Deadline cancellation cannot wait behind a pending identity write/heartbeat.
    from .application_deadline import dispatch_expired
    for item in list(getattr(service,'dispatch_items',{}).values()):
        dispatch_expired(service,item,clock=getattr(service,'dispatch_clocks',{}).get(item['id']))


def recover_dispatch(service):
    recovered=True
    supervise_cached_dispatches(service)
    processes=getattr(service,'dispatch_processes',{})
    for item_id,identity in list(getattr(service,'dispatch_identity_pending',{}).items()):
        with service.tx() as db:
            db.execute('UPDATE dispatch_queue SET executor_identity_json=? WHERE id=?',(dumps(identity),item_id))
        service.dispatch_identity_pending.pop(item_id,None)
    # Reap children even when the durable cleanup of their browser is pending.
    for item_id,process in list(processes.items()):
        if process.poll() is not None:processes.pop(item_id,None)
    with service.read() as db:
        rows=[dict(r) for r in db.execute('''SELECT q.* FROM dispatch_queue q
            WHERE q.state='dispatched' OR (q.state='finished' AND EXISTS (
                SELECT 1 FROM application_sessions s WHERE s.job_id=q.job_id
                AND s.identity_id=q.identity_id AND s.ended_at IS NULL))''')]
    for item in rows:
        if item['id']==getattr(service,'dispatch_preparation',{}).get('item',{}).get('id'):
            recovered=False;continue  # Resume this reserved launch after a busy read.
        if item['state']=='dispatched':
            from .application_deadline import dispatch_expired
            dispatch_expired(service,item,clock=getattr(service,'dispatch_clocks',{}).get(item['id']))
        active=any(not session['ended_at'] for session in find_sessions(service,item))
        if item['state']=='finished' and not active:continue
        if item['id'] in processes or process_matches(json.loads(item['executor_identity_json'] or '{}')):
            recovered=False;continue
        # A desktop turn outlives its monitoring subprocess. Reconcile the native
        # owner before treating a monitor crash as an executor exit.
        from .hermes_desktop import orphan_is_active
        if orphan_is_active(service, item, check_finished=active):
            recovered=False;continue
        if not settle(service,item):recovered=False
        else:
            getattr(service,'dispatch_clocks',{}).pop(item['id'],None)
            getattr(service,'dispatch_items',{}).pop(item['id'],None)
    return recovered


def import_answer_retries(config, service):
    """The existing Answers UI feeds the same dispatcher, for its configured identity."""
    for request in service.answer_retries(identity_id=config['identity_id'])['requests']:
        try:
            service.queue_enqueue(job_ids=[request['job_id']],identity_id=config['identity_id'],
                resume_asset_id=config['resume_asset_id'],request_id=request['request_id'],retry=True,
                enqueue_origin='answer_retry',producer='queue_worker')
        except ProtocolError as exc:
            # An excluded/applied posting is still subject to the existing policy.
            if exc.code not in ('already_applied','company_excluded','job_archived','not_ready','market_incompatible'):
                raise


def dispatch_capacity(config, service):
    """Count executor reservations and independent manual sessions exactly once."""
    limit=service.settings_view()['values']['application_concurrency']
    workspaces=config['workspaces']
    if not any(w.get('connection_mode')=='existing' for w in workspaces):
        limit=min(limit,len(workspaces))
    with service.read() as db:
        sessions=[dict(r) for r in db.execute('SELECT * FROM application_sessions WHERE ended_at IS NULL AND workspace_id IS NOT NULL')]
        items=[dict(r) for r in db.execute("SELECT * FROM dispatch_queue WHERE state='dispatched'")]
    associated={s['id'] for item in items for s in find_sessions(service,item)}
    manual=sum(s['id'] not in associated for s in sessions)
    occupied={s['workspace_id'] for s in sessions}
    browser_available=any(w.get('connection_mode')=='existing' or w['id'] not in occupied for w in workspaces)
    return limit,manual,items,browser_available


def dispatch_one(config, service, *, launcher=subprocess.Popen, wait=True):
    service.desktop_dispatch_spool=config['spool_dir']
    recover_dispatch(service)
    limit,manual,items,browser_available=dispatch_capacity(config,service)
    pending=getattr(service,'dispatch_preparation',None)
    if not pending:
        if len(items)>=limit:return {'state':'waiting_for_executor_or_cleanup'}
        if len(items)+manual>=limit or not browser_available:
            return {'state':'waiting_for_browser'}
        item=service.queue_take(concurrency_limit=limit-manual)
        if not item:return {'state':'paused' if service.queue_status()['automation_paused'] else 'empty'}
        pending=service.dispatch_preparation={'item':item,'limit':limit}
    item=pending['item']
    root=Path(config['spool_dir'])/'dispatch'/item['id']
    from .model_settings import application_selection
    from .application_deadline import freeze,Deadline,dispatch_expired
    if 'config' not in pending:
        effective_settings=service.settings_view()['values']
        child_config=dict(application_selection(config,effective_settings),
                          identity_id=item['identity_id'],resume_asset_id=item['resume_asset_id'],
                          concurrency_limit=pending['limit'])
        pending['config']=freeze(child_config,effective_settings,item.get('started_at') or service.now())
    child_config=dict(pending['config'])
    deadline=Deadline(child_config['application_deadline'])
    child_config['config_path']=str(root/'runtime.json')
    process=None
    try:
        private_write(root/'runtime.json',json.dumps(child_config,indent=2))
        private_write(root/'task.md',application_brief(child_config,service,item))
        command=executor_command(child_config,root/'task.md')
        environment=dict(os.environ,JOBBOT_CONFIG=child_config['config_path'])
        # Do not leak the dispatcher's calling conversation into a new Hermes session.
        environment.pop('HERMES_SESSION_ID',None)
        process=launcher(command,cwd=str(REPOSITORY),env=environment,stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,shell=False,
                         **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}))
        identity=process_identity(process.pid)
        # Retain ownership BEFORE any fallible persistence after launch. A busy
        # DB resumes this exact identity write; it never launches another child.
        if not hasattr(service,'dispatch_processes'):service.dispatch_processes={}
        if not hasattr(service,'dispatch_clocks'):service.dispatch_clocks={}
        if not hasattr(service,'dispatch_identity_pending'):service.dispatch_identity_pending={}
        if not hasattr(service,'dispatch_items'):service.dispatch_items={}
        service.dispatch_processes[item['id']]=process
        service.dispatch_clocks[item['id']]=deadline
        service.dispatch_identity_pending[item['id']]=identity or {}
        item=dict(item,executor_identity_json=dumps(identity or {}))
        service.dispatch_items[item['id']]=item
        service.dispatch_preparation={}
        try:
            with service.tx() as db:
                db.execute('UPDATE dispatch_queue SET executor_identity_json=? WHERE id=?',(dumps(identity or {}),item['id']))
            service.dispatch_identity_pending.pop(item['id'],None)
        except sqlite3.OperationalError as exc:
            if not database_busy(exc):raise
            logging.getLogger(__name__).warning('sqlite_contention operation=dispatch_identity; executor retained')
        if not wait:
            return {'state':'dispatched','item_id':item['id']}
        while process.poll() is None:
            try:
                recover_dispatch(service)
                expired=dispatch_expired(service,item,clock=deadline)
                service.queue_heartbeat(process_identity(os.getpid()),current_item=item['id'],
                    detail='Application time limit reached; stopping executor and cleaning up' if expired else 'In progress')
            except sqlite3.OperationalError as exc:
                if not database_busy(exc):raise
                logging.getLogger(__name__).warning('sqlite_contention operation=dispatch_wait; executor retained')
            time.sleep(2)
        finished=settle(service,item)
        return {'state':'finished' if finished else 'closing_browser','item_id':item['id'],'executor_exit_code':process.returncode}
    except (OSError,ValueError,ProtocolError) as exc:
        if process is not None:
            # Preserve an already-launched executor and its reservation; no replacement.
            raise
        code=getattr(exc,'code',type(exc).__name__)
        service.queue_complete(item['id'],outcome='failed',detail='Executor launch failed: '+code)
        service.dispatch_preparation={}
        return {'state':'launch_failed','item_id':item['id'],'error':code}


def watch(config, service, *, once=False):
    interval=float(config.get('queue_interval_seconds',10800))
    if interval<=0:raise ProtocolError('invalid_queue_interval')
    with FileLock(str(service.db_path)+'.dispatcher.lock'):
        service.desktop_dispatch_spool=config['spool_dir']
        service.dispatch_selection={key:config[key] for key in ('identity_id','resume_asset_id')}
        next_answer_review=0
        while True:
            try:
                supervise_cached_dispatches(service)
                service.queue_heartbeat(process_identity(os.getpid()))
                if time.monotonic()>=next_answer_review:
                    service.reconcile_answers(identity_id=config['identity_id'])
                    next_answer_review=time.monotonic()+60
                import_answer_retries(config,service)
                service.queue_reconcile(**service.dispatch_selection)
                status=service.queue_status()
                now=datetime.fromisoformat(service.now())
                due=not status['next_automatic_at'] or now>=datetime.fromisoformat(status['next_automatic_at'])
                # Cleanup is observed even with scheduling paused.
                recover_dispatch(service)
                if status['automation_paused']:
                    service.queue_heartbeat(process_identity(os.getpid()),detail='Paused; waiting for Resume JobBot')
                    if once:return {'state':'paused'}
                elif once or status['wake_requested'] or status['immediate_count'] or (status['enabled'] and due):
                    if once:result=dispatch_one(config,service)
                    else:
                        # Fill available slots without waiting for any executor. Every
                        # launch re-reads pause, capacity and the latest model settings.
                        while True:
                            result=dispatch_one(config,service,wait=False)
                            if result['state']!='dispatched':break
                            latest=service.queue_status()
                            # A manual Run next / Apply now is still its original
                            # request. Fill more slots only for due automatic work or
                            # remaining explicitly queued immediate requests.
                            if not ((latest['enabled'] and due) or latest['immediate_count']):break
                    if result['state'] not in ('paused','waiting_for_browser','waiting_for_executor_or_cleanup'):
                        with service.tx() as db:
                            db.execute('UPDATE dispatch_control SET wake_requested=0,next_automatic_at=? WHERE id=1 AND automation_paused=0',
                                       ((datetime.fromisoformat(service.now())+timedelta(seconds=interval)).isoformat(),))
                    service.queue_heartbeat(process_identity(os.getpid()),detail=result['state'])
                    if once:return result
            except sqlite3.OperationalError as exc:
                if not database_busy(exc):raise
                logging.getLogger(__name__).warning('sqlite_contention operation=queue_watch; retrying bookkeeping')
            time.sleep(2)


def serve(config, service):
    from urllib.parse import urlsplit
    import uvicorn
    from .managed_api import create_app
    from .managed_cli import credential
    from .managed_client import Client
    token=credential(config['operator_token_env'],config)
    service.executor_config=config
    from .answer_learning import AnswerLearner
    learner=AnswerLearner(service,config)
    learner.start()
    service.dispatch_selection={key:config[key] for key in ('identity_id','resume_asset_id')}
    with Client(config['base_url'],config['instance_id'],token):pass
    workers=json.loads(credential(config['worker_tokens_env'],config)) if config.get('worker_tokens_env') else {
        credential(config['worker_token_env'],config):config['worker_id']}
    address=urlsplit(config['base_url'])
    try:
        uvicorn.run(create_app(service,operator_token=token,worker_tokens=workers),
                    host=address.hostname,port=address.port or 60158,access_log=False)
    finally:learner.stop.set()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config')
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('status','doctor','watch','once','serve','run-next','pause','resume','pause-all','resume-all'):sub.add_parser(command)
    add=sub.add_parser('enqueue');add.add_argument('urls',nargs='*');add.add_argument('--job-id',action='append',default=[])
    add.add_argument('--retry',action='store_true');add.add_argument('--run-next',action='store_true')
    args=parser.parse_args(argv)
    try:
        config=resolve_config(args.config)
        if args.command=='doctor':
            from .hermes_gmail import mailbox_handoff
            command=executor_command(config,Path(config['spool_dir'])/'example-task.md')
            result={'executor_found':bool(shutil.which(command[0])),
                    'display_configured':os.name=='nt' or bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')),
                    'mailbox':mailbox_handoff(config),'deployment_verified':False,
                    'instruction':'Executable/config presence is not authenticated mailbox, Simplify, vision or employer acceptance verification.'}
        else:
            service=Service(config['db_path'],instance_id=config['instance_id']) if args.command=='status' else prepare_local(config)
            if args.command=='status':result=service.queue_status()
            elif args.command in ('watch','once'):result=watch(config,service,once=args.command=='once')
            elif args.command=='serve':serve(config,service);return 0
            elif args.command=='enqueue':
                job_ids=list(args.job_id)
                for url in args.urls:job_ids.append(service.intake(url=url,source_type='manual',producer='queue_cli')['id'])
                result=service.queue_enqueue(job_ids=job_ids,identity_id=config['identity_id'],
                    resume_asset_id=config['resume_asset_id'],request_id=uid(),retry=args.retry,
                    enqueue_origin='manual_retry' if args.retry else 'manual_enqueue',producer='queue_cli')
                if args.run_next:service.queue_control(command='run_next')
            else:
                service.dispatch_selection={key:config[key] for key in ('identity_id','resume_asset_id')}
                result=service.queue_control(command=args.command.replace('-','_'))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (ProtocolError,OSError,ValueError,KeyError) as exc:
        print(json.dumps({'error':getattr(exc,'code',type(exc).__name__)}));return 2


if __name__=='__main__':raise SystemExit(main())
