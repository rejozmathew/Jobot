"""Sequential queue dispatcher for the current local runtime, not the legacy worker.

Each explicit queue entry gets a fresh external CLI process and private brief.
The subprocess is replaceable; JobBot owns durable intake, outcomes and scheduling.
"""
import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .application_runtime import REPOSITORY, prepare_local, resolve_config
from .application_brief import application_brief
from .managed import Service
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
    with service.tx() as db:
        return [dict(row) for row in db.execute('''SELECT * FROM application_sessions
            WHERE job_id=? AND identity_id=? AND (request_id=? OR driver_id=?) ORDER BY rowid''',
            (item['job_id'], item['identity_id'], 'queue:'+item['id'], driver))]


def settle(service, item):
    """Observe durable evidence after process exit; never translate exit zero to applied."""
    sessions=find_sessions(service,item)
    active=[session for session in sessions if not session['ended_at']]
    if active:
        for session in active:
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
    if receipt_path and receipt_path.exists():
        timed_out=timed_out or json.loads(receipt_path.read_text()).get('stop_reason')=='application_time_limit'
    service.queue_complete(item['id'],outcome=(attempt or {}).get('outcome') or 'interrupted',
        detail=(attempt or {}).get('evidence') or (session or {}).get('reason') or
            ('application_time_limit: Application time limit reached' if timed_out else 'Executor exited without a recorded application outcome.'),
        session_id=session['id'] if session else None)
    return True


def recover_dispatch(service):
    with service.tx() as db:
        rows=[dict(r) for r in db.execute('''SELECT q.* FROM dispatch_queue q
            WHERE q.state='dispatched' OR (q.state='finished' AND EXISTS (
                SELECT 1 FROM application_sessions s WHERE s.job_id=q.job_id
                AND s.identity_id=q.identity_id AND s.ended_at IS NULL))''')]
    for item in rows:
        if item['state']=='dispatched':
            from .application_deadline import dispatch_expired
            dispatch_expired(service,item)
        active=any(not session['ended_at'] for session in find_sessions(service,item))
        if item['state']=='finished' and not active:continue
        if process_matches(json.loads(item['executor_identity_json'] or '{}')):return False
        # A desktop turn outlives its monitoring subprocess. Reconcile the native
        # owner before treating a monitor crash as an executor exit.
        from .hermes_desktop import orphan_is_active
        if orphan_is_active(service, item, check_finished=active):return False
        if not settle(service,item):return False
    return True


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


def dispatch_one(config, service, *, launcher=subprocess.Popen):
    service.desktop_dispatch_spool=config['spool_dir']
    if not recover_dispatch(service):return {'state':'waiting_for_executor_or_cleanup'}
    workspace_ids={w['id'] for w in config['workspaces']}
    with service.tx() as db:
        active=db.execute('SELECT workspace_id FROM application_sessions WHERE ended_at IS NULL AND workspace_id IS NOT NULL').fetchall()
    if any(r['workspace_id'] in workspace_ids for r in active):
        return {'state':'waiting_for_browser'}
    item=service.queue_take()
    if not item:return {'state':'empty'}
    root=Path(config['spool_dir'])/'dispatch'/item['id']
    from .model_settings import application_selection
    effective_settings=service.settings_view()['values']
    child_config=dict(application_selection(config,effective_settings),
                      identity_id=item['identity_id'],resume_asset_id=item['resume_asset_id'])
    from .application_deadline import freeze,Deadline,dispatch_expired
    child_config=freeze(child_config,effective_settings,service.now())
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
        with service.tx() as db:
            db.execute('UPDATE dispatch_queue SET executor_identity_json=? WHERE id=?',(dumps(identity or {}),item['id']))
        item=dict(item,executor_identity_json=dumps(identity or {}))
        while process.poll() is None:
            expired=dispatch_expired(service,item,clock=deadline)
            service.queue_heartbeat(process_identity(os.getpid()),current_item=item['id'],
                detail='Application time limit reached; stopping executor and cleaning up' if expired else 'In progress')
            time.sleep(2)
        finished=settle(service,item)
        return {'state':'finished' if finished else 'closing_browser','item_id':item['id'],'executor_exit_code':process.returncode}
    except (OSError,ValueError,ProtocolError) as exc:
        if process is not None:
            # Preserve an already-launched executor and its reservation; no replacement.
            raise
        code=getattr(exc,'code',type(exc).__name__)
        service.queue_complete(item['id'],outcome='failed',detail='Executor launch failed: '+code)
        return {'state':'launch_failed','item_id':item['id'],'error':code}


def watch(config, service, *, once=False):
    interval=float(config.get('queue_interval_seconds',10800))
    if interval<=0:raise ProtocolError('invalid_queue_interval')
    with FileLock(str(service.db_path)+'.dispatcher.lock'):
        service.desktop_dispatch_spool=config['spool_dir']
        service.dispatch_selection={key:config[key] for key in ('identity_id','resume_asset_id')}
        while True:
            service.queue_heartbeat(process_identity(os.getpid()))
            import_answer_retries(config,service)
            service.queue_reconcile(**service.dispatch_selection)
            status=service.queue_status()
            now=datetime.fromisoformat(service.now())
            due=not status['next_automatic_at'] or now>=datetime.fromisoformat(status['next_automatic_at'])
            # Cleanup is observed even with scheduling paused.
            recovered=recover_dispatch(service)
            if once or status['wake_requested'] or status['immediate_count'] or (status['enabled'] and due):
                result=dispatch_one(config,service) if recovered else {'state':'waiting_for_executor_or_cleanup'}
                if result['state'] not in ('waiting_for_browser','waiting_for_executor_or_cleanup'):
                    with service.tx() as db:
                        db.execute('UPDATE dispatch_control SET wake_requested=0,next_automatic_at=? WHERE id=1',
                                   ((datetime.fromisoformat(service.now())+timedelta(seconds=interval)).isoformat(),))
                service.queue_heartbeat(process_identity(os.getpid()),detail=result['state'])
                if once:return result
            time.sleep(2)


def serve(config, service):
    from urllib.parse import urlsplit
    import uvicorn
    from .managed_api import create_app
    from .managed_cli import credential
    from .managed_client import Client
    token=credential(config['operator_token_env'],config)
    service.executor_config=config
    service.dispatch_selection={key:config[key] for key in ('identity_id','resume_asset_id')}
    with Client(config['base_url'],config['instance_id'],token):pass
    workers=json.loads(credential(config['worker_tokens_env'],config)) if config.get('worker_tokens_env') else {
        credential(config['worker_token_env'],config):config['worker_id']}
    address=urlsplit(config['base_url'])
    uvicorn.run(create_app(service,operator_token=token,worker_tokens=workers),
                host=address.hostname,port=address.port or 60158,access_log=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config')
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('status','doctor','watch','once','serve','run-next','pause','resume'):sub.add_parser(command)
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
