"""Run queued applications in the existing Hermes desktop backend.

This process is a monitor, not an application agent. Native desktop sessions
retain their usual prompt/steer/approval UI and single-writer ownership.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlsplit

import httpx
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from .application_runtime import REPOSITORY
from .workspace_process import process_identity, process_matches


def discover_backend(options, *, proc=Path('/proc')):
    """Find this profile's existing local `hermes serve`, including random ports."""
    if options.get('url'):
        url=options['url'].rstrip('/')
        address=urlsplit(url)
        if address.scheme!='http' or address.hostname not in ('127.0.0.1','localhost','::1'):
            raise ValueError('Hermes desktop URL must refer to its local HTTP backend')
        return url, None
    home=Path(options.get('profile_home') or Path.home()/'.hermes').resolve()
    candidates=[]
    for directory in proc.iterdir():
        if not directory.name.isdigit():continue
        try:
            if directory.stat().st_uid!=os.getuid():continue
            argv=(directory/'cmdline').read_bytes().decode().split('\0')
            if 'serve' not in argv or not any('hermes' in part for part in argv):continue
            # Initial /proc environ can predate Hermes's profile switch.
            if '--profile' in argv and argv[argv.index('--profile')+1]!=(options.get('profile') or 'default'):
                continue
            env=dict(part.split('=',1) for part in (directory/'environ').read_bytes().decode().split('\0') if '=' in part)
            actual=Path(env.get('HERMES_HOME') or Path(env.get('HOME',str(Path.home())))/'.hermes').resolve()
            if actual!=home:continue
            sockets={p.readlink().as_posix() for p in (directory/'fd').iterdir()}
            for line in (proc/'net'/'tcp').read_text().splitlines()[1:]:
                parts=line.split()
                if parts[3]!='0A' or 'socket:['+parts[9]+']' not in sockets:continue
                ip,port=parts[1].split(':')
                if ip=='0100007F':
                    candidates.append(('http://127.0.0.1:'+str(int(port,16)),
                        process_identity(int(directory.name)),_has_desktop_parent(directory,proc)))
        except (OSError,ValueError,UnicodeError):
            continue
    preferred=[candidate for candidate in candidates if candidate[2]] or candidates
    if len(preferred)==1:return preferred[0][:2]
    if preferred:raise OSError('Multiple Hermes backends found; select the desktop backend URL')
    raise OSError('The selected Hermes desktop backend is not running')


def _has_desktop_parent(directory, proc):
    try:
        parent=int((directory/'stat').read_text().rsplit(')',1)[1].split()[1])
        argv=(proc/str(parent)/'cmdline').read_bytes().decode().split('\0')
        return Path(argv[0]).name.lower() in ('hermes','hermes.exe')
    except (OSError,ValueError,IndexError,UnicodeError):
        return False


class RPCRejected(ValueError):
    """Explicit native rejection, distinct from a lost acknowledgement."""
    pass


class RPC:
    def __init__(self, socket, *, timeout=60):
        self.socket=socket
        self.timeout=timeout
        self.sequence=0
        self.terminal_events={}

    def call(self, method, params):
        self.sequence+=1
        rid=self.sequence
        self.socket.send(json.dumps({'jsonrpc':'2.0','id':rid,'method':method,'params':params}))
        deadline=time.monotonic()+self.timeout
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Hermes desktop RPC response timed out')
            frame=self.socket.recv(timeout=remaining)
            for line in frame.splitlines():
                message=json.loads(line)
                event=message.get('params',{}) if message.get('method')=='event' else {}
                if event.get('type')=='message.complete' and event.get('session_id'):
                    self.terminal_events[event['session_id']]=terminal_summary(event.get('payload',{}))
                if message.get('id')!=rid:continue
                if 'error' in message:
                    # Do not copy arbitrary server payloads (which can contain private prompts).
                    raise RPCRejected('Hermes desktop RPC failed: '+method+' ('+str(message['error'].get('code'))+')')
                return message['result']


def terminal_summary(payload):
    """Keep a cause signature, never a provider's raw prompt/error payload."""
    status=payload.get('status');error=str(payload.get('error') or '').casefold()
    if 'decod' in error and ('fail' in error or 'error' in error):kind='model_decode_error'
    elif 'timeout' in error or 'timed out' in error:kind='model_timeout'
    elif 'tool' in error and ('stream' in error or 'partial' in error):kind='tool_stream_incomplete'
    elif status=='error' or error:kind='executor_error'
    elif status=='interrupted':kind='executor_interrupted'
    else:kind='executor_turn_complete'
    result={'status':status,'kind':kind}
    surface=payload.get('error_surface')
    if isinstance(surface,dict):
        result['error_surface']={k:v for k,v in surface.items() if k in ('layer','code','retryable') and
            (type(v) is bool or isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',v))}
    return result


def continuation_context(config,receipt):
    """Durable application state decides whether an idle model still has work."""
    if not config.get('db_path') or not receipt.get('dispatch_id'):return None
    from .managed import Service
    from .queue_runtime import find_sessions
    service=Service(config['db_path'],instance_id=config.get('instance_id'))
    service.desktop_dispatch_spool=config['spool_dir']
    with service.tx() as db:
        row=db.execute('SELECT * FROM dispatch_queue WHERE id=?',(receipt['dispatch_id'],)).fetchone()
        if not row or row['state']!='dispatched':return None
        item=dict(row)
    sessions=find_sessions(service,item)
    if not sessions:return {'job_id':item['job_id'],'request_id':'queue:'+item['id'],'stage':'startup'}
    if any(s['attempt_id'] and service.attempt(s['attempt_id'])['outcome'] in ('applied','already_applied') for s in sessions):return None
    session=sessions[-1]
    if session['ended_at'] or session['state']=='finishing':return None
    if session['driver_id']!=receipt.get('stored_session_id') and native_driver_id(session)!=receipt.get('session_id'):return None
    attempt=service.attempt(session['attempt_id']) if session['attempt_id'] else None
    if attempt and attempt['completed_at']:return None
    with service.tx() as db:
        run=db.execute('SELECT control FROM runs WHERE id=?',(session['run_id'],)).fetchone() if session['run_id'] else None
        if run and run['control'] in ('stop_requested','stopped'):return {'terminal':'application_stop_requested'}
        waiting=bool(run and run['control'] in ('pause_requested','paused') or session['state']=='paused')
        if attempt:waiting=waiting or any(q['state']=='pending' for q in service._questions(db,item['job_id'],item['identity_id']))
    return {'session_id':session['id'],'attempt_id':session['attempt_id'],'request_id':session['request_id'],
        'stage':(attempt or {}).get('phase') or session['state'],'wait':waiting}


def idle_snapshot(rpc,receipt):
    state=rpc.call('session.activate',{'session_id':receipt['session_id'],'omit_messages':True})
    replay=rpc.call('session.events.since',{'session_id':receipt['session_id'],'last_seen':receipt.get('event_seq',0)})
    if receipt.get('event_epoch') and replay.get('epoch')!=receipt['event_epoch']:
        getattr(rpc,'terminal_events',{}).pop(receipt['session_id'],None)
        replay=rpc.call('session.events.since',{'session_id':receipt['session_id'],'last_seen':0})
    terminal=None
    for event in replay.get('events',[]):
        data=event.get('params',event)
        if data.get('type')=='message.complete':terminal=terminal_summary(data.get('payload',{}))
    if terminal is None:
        inflight=state.get('inflight') or {}
        if inflight.get('status') in ('error','complete','interrupted'):terminal=terminal_summary(inflight)
    if terminal is None:terminal=getattr(rpc,'terminal_events',{}).get(receipt['session_id'])
    receipt['event_seq']=replay.get('latest_seq',receipt.get('event_seq',0))
    receipt['event_epoch']=replay.get('epoch')
    if terminal:
        receipt['last_terminal']=terminal
        if terminal['status']=='error':receipt['last_executor_failure']=terminal
    return state,replay


def continuation_accepted(rpc,receipt,state):
    marker=receipt.get('continuation_marker')
    if not marker:return False
    if any(marker in str((state.get(k) or {}).get('user','')) for k in ('inflight','queued')):return True
    # The native API has no prompt idempotency key or filtered-history endpoint.
    # Inspect privately only after uncertain acknowledgement; never save messages.
    history=rpc.call('session.history',{'session_id':receipt['session_id']})
    return any(row.get('role')=='user' and marker in row.get('text','') for row in history.get('messages',[]))


@contextmanager
def connection(options, *, timeout=15, rpc_timeout=60):
    url,owner=discover_backend(options)
    with httpx.Client(trust_env=False,timeout=timeout) as client:
        response=client.get(url+'/')
        response.raise_for_status()
    # Same short-lived loopback bootstrap credential used by the installed desktop.
    match=re.search(r'window\.__HERMES_SESSION_TOKEN__\s*=\s*("[^"\n]+")',response.text)
    if not match:raise ValueError('Hermes desktop bootstrap credential is unavailable')
    token=json.loads(match.group(1))
    websocket_url='ws'+url[4:]+'/api/ws?'+urlencode({'token':token})
    with connect(websocket_url,proxy=None,max_size=None,open_timeout=timeout,close_timeout=min(timeout,10)) as socket:
        yield RPC(socket,timeout=rpc_timeout),owner


def backend_ready(options):
    """Observe startup readiness without creating a native application session."""
    try:
        with connection(options,timeout=2,rpc_timeout=2) as (rpc,_):
            result=rpc.call('session.active_list',{})
            return isinstance(result,dict) and isinstance(result.get('sessions'),list)
    except (OSError,ValueError,httpx.HTTPError,WebSocketException):
        return False


def write_receipt(path, receipt):
    from .queue_runtime import private_write
    temporary=path.with_suffix('.tmp')
    private_write(temporary,json.dumps(receipt,indent=2))
    temporary.replace(path)


def session_active(rpc, session_id, *, stored_session_id=None):
    rows=rpc.call('session.active_list',{})['sessions']
    return any(row['status']!='idle' for row in rows if row['id']==session_id or
               (stored_session_id and row.get('session_key')==stored_session_id))


def interrupt_owned(rpc, session_id=None, stored_session_id=None):
    """Interrupt matching live turns; acknowledgement is a fresh idle observation."""
    rows=rpc.call('session.active_list',{})['sessions']
    active=[row for row in rows if row['status']!='idle' and
            (row['id']==session_id or (stored_session_id and row.get('session_key')==stored_session_id))]
    for row in active:rpc.call('session.interrupt',{'session_id':row['id']})
    return not active or not session_active(rpc,session_id,stored_session_id=stored_session_id)


def cancel_dispatch(config, receipt_path):
    if not receipt_path.exists():return False  # Monitor checks its deadline before creating/submitting.
    receipt=json.loads(receipt_path.read_text())
    if receipt.get('state')=='finished':return True
    try:
        with connection(config['hermes_desktop']) as (rpc,_):
            cancelled=interrupt_owned(rpc,receipt.get('session_id'),receipt.get('stored_session_id'))
            # During submit, keep the monitor until it receives the RPC result
            # and performs its own deadline check; absence from active_list can
            # precede the backend accepting the already-sent prompt.
            return cancelled and receipt.get('state')=='submitted'
    except (OSError,ValueError,TimeoutError,ConnectionClosed,httpx.HTTPError):return False


def remember_driver(config, service, session):
    """Retain the native task ID before chat compression can rotate its key."""
    if not isinstance(config.get('hermes_desktop'),dict):return
    if native_driver_id(session):return
    try:
        with connection(config['hermes_desktop']) as (rpc,_):
            rows=rpc.call('session.active_list',{})['sessions']
        matches=[row['id'] for row in rows if row.get('session_key')==session['driver_id']]
        if len(matches)!=1:return
        with service.tx() as db:
            current=service._get(db,'application_sessions',session['id'])
            if current['ended_at'] or current['driver_id']!=session['driver_id']:return
            metadata=json.loads(current['metadata_json'])
            metadata['native_session_id']=matches[0]
            metadata['native_driver_id']=session['driver_id']
            db.execute('UPDATE application_sessions SET metadata_json=? WHERE id=?',
                       (json.dumps(metadata),session['id']))
    except (OSError,ValueError,TimeoutError,ConnectionClosed,httpx.HTTPError):return


def native_driver_id(session):
    """An explicit attach may replace the driver; never cancel its predecessor."""
    metadata=json.loads(session.get('metadata_json') or '{}')
    return metadata.get('native_session_id') if metadata.get('native_driver_id')==session['driver_id'] else None


def cancel_driver(config, driver_id, native_session_id=None):
    if not isinstance(config.get('hermes_desktop'),dict):return True
    try:
        with connection(config['hermes_desktop']) as (rpc,_):
            return interrupt_owned(rpc,session_id=native_session_id,stored_session_id=driver_id)
    except (OSError,ValueError,TimeoutError,ConnectionClosed,httpx.HTTPError):return False


def run_session(rpc, prompt, config, receipt_path, *, sleep=time.sleep, owner=None):
    options=config['hermes_desktop']
    from .application_deadline import Deadline
    deadline=Deadline(config.get('application_deadline'))
    receipt=json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    if receipt is None:
        if deadline.expired():
            receipt={'state':'finished','stop_reason':'application_time_limit'}
            write_receipt(receipt_path,receipt)
            return receipt
        params={'source':'desktop','cwd':str(REPOSITORY),'hidden':False,'close_on_disconnect':False}
        if options.get('profile'):params['profile']=options['profile']
        if config.get('application_model'):
            params.update(model=config['application_model'],provider=config.get('application_provider'))
            if config.get('application_effort'):params['reasoning_effort']=config['application_effort']
        created=rpc.call('session.create',params)
        receipt={key:created[key] for key in ('session_id','stored_session_id')}
        receipt.update(state='created',backend_owner=owner,dispatch_id=receipt_path.parent.name)
        write_receipt(receipt_path,receipt)
    if receipt.get('state')=='created':
        if options.get('yolo'):
            rpc.call('config.set',{'session_id':receipt['session_id'],'key':'yolo','value':'on','scope':'session'})
        skills=options.get('skills') or []
        prefix=('Read these installed skills for this task: '+', '.join(skills)+'.\n') if skills else ''
        prefix+=('Actual conversation ID: '+receipt['stored_session_id']+'. Use --driver-id '+
                 receipt['stored_session_id']+' for this application runtime request.\n\n')
        # Persist before sending: a lost reply must not submit the application task twice.
        import uuid
        receipt.update(state='submitting',original_marker='[JobBot task '+str(uuid.uuid4())+']')
        write_receipt(receipt_path,receipt)
        if deadline.expired():
            receipt.update(state='finished',stop_reason='application_time_limit')
            write_receipt(receipt_path,receipt)
            return receipt
        getattr(rpc,'terminal_events',{}).pop(receipt['session_id'],None)
        try:rpc.call('prompt.submit',{'session_id':receipt['session_id'],'text':receipt['original_marker']+' '+prefix+prompt,'surface':'desktop'})
        except RPCRejected:
            receipt['state']='created';write_receipt(receipt_path,receipt);raise
        receipt['state']='submitted'
        write_receipt(receipt_path,receipt)
    if receipt.get('state')=='finished':return receipt
    while True:
        active=session_active(rpc,receipt['session_id'],stored_session_id=receipt.get('stored_session_id'))
        if deadline.expired():
            receipt['stop_reason']='application_time_limit'
            write_receipt(receipt_path,receipt)
            if interrupt_owned(rpc,receipt['session_id'],receipt.get('stored_session_id')):break
            sleep(2);continue
        if active:sleep(2);continue
        snapshot=None
        if config.get('db_path'):
            snapshot=idle_snapshot(rpc,receipt);write_receipt(receipt_path,receipt)
        context=continuation_context(config,receipt)
        if context is None:break
        if context.get('terminal'):
            receipt['stop_reason']=context['terminal'];break
        state,replay=snapshot or idle_snapshot(rpc,receipt)
        write_receipt(receipt_path,receipt)
        if state.get('running') or context.get('wait') or replay.get('open_requests'):
            sleep(2);continue
        if (receipt.get('last_terminal') or {}).get('status')=='interrupted':break
        # A lost submit acknowledgement is reconciled through native turn evidence;
        # idle alone is never permission to submit the same continuation twice.
        if receipt.get('state') in ('continuing','submitting'):
            pending=receipt if receipt['state']=='continuing' else dict(receipt,continuation_marker=receipt.get('original_marker'))
            if not continuation_accepted(rpc,pending,state):
                receipt['ack_checks']=receipt.get('ack_checks',0)+1;write_receipt(receipt_path,receipt)
                sleep(min(30,2**min(receipt['ack_checks'],5)));continue
            receipt['state']='submitted';write_receipt(receipt_path,receipt)
        receipt['continuation_count']=receipt.get('continuation_count',0)+1
        sleep(min(30,2**min(receipt['continuation_count'],5)))
        if deadline.expired():continue
        # Re-read ownership/stop/answer state after backoff, before sending.
        refreshed=continuation_context(config,receipt)
        if refreshed is None:break
        if refreshed.get('terminal'):
            receipt['stop_reason']=refreshed['terminal'];break
        if refreshed.get('wait'):sleep(2);continue
        if session_active(rpc,receipt['session_id'],stored_session_id=receipt.get('stored_session_id')):continue
        if deadline.expired():continue
        import uuid
        receipt.update(state='continuing',continuation_marker='[JobBot continuation '+str(uuid.uuid4())+']')
        write_receipt(receipt_path,receipt)
        text=(receipt['continuation_marker']+' Continue the same owned application in this same conversation. The prior model turn ended '
              'without a recorded application outcome. Preserve the original application deadline and request. '
              'Do not create another conversation or restart completed actions. Retrieve the current owned '
              'session context, observe the actual page, and resume the next supported action. A model error '
              'is not an employer rejection. If startup was unfinished, use the original idempotent start request. '
              'Respect user stop, human input, confirmation evidence and existing submission permissions. '
              'Current durable checkpoint: '+json.dumps(refreshed))
        getattr(rpc,'terminal_events',{}).pop(receipt['session_id'],None)
        try:rpc.call('prompt.submit',{'session_id':receipt['session_id'],'text':text,'surface':'desktop'})
        except RPCRejected:
            receipt['state']='submitted';write_receipt(receipt_path,receipt);raise
        receipt.update(state='submitted',last_terminal=None);write_receipt(receipt_path,receipt)
    receipt['state']='finished'
    write_receipt(receipt_path,receipt)
    return receipt


def orphan_is_active(service, item, *, check_finished=False):
    """Recover a crashed monitor without stopping its still-running native turn."""
    # The queue already persists the exact dispatch config beside the task.
    # Config path is supplied by the same dispatcher, never inferred from a DB name.
    root=getattr(service,'desktop_dispatch_spool',None)
    if not root:return False
    receipt_path=Path(root)/'dispatch'/item['id']/'desktop-session.json'
    if not receipt_path.exists():return False
    receipt=json.loads(receipt_path.read_text())
    if receipt.get('state')=='finished' and not receipt.get('session_id'):return False
    # A user can resume the native conversation after its monitor has exited.
    # Retained replacement browsers require a fresh check, even for old receipts.
    if receipt['state']=='finished' and not check_finished:return False
    owner=receipt.get('backend_owner')
    if owner and not process_matches(owner) and not check_finished:return False
    config=json.loads(receipt_path.with_name('runtime.json').read_text())
    try:
        with connection(config['hermes_desktop']) as (rpc,_):
            return session_active(rpc,receipt['session_id'],stored_session_id=receipt.get('stored_session_id'))
    except (OSError,ValueError,TimeoutError,ConnectionClosed,httpx.HTTPError):
        return True  # A connection failure is not evidence that the native owner exited.


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prompt_file',type=Path)
    args=parser.parse_args(argv)
    config=json.loads(args.prompt_file.with_name('runtime.json').read_text())
    prompt=args.prompt_file.read_text()
    receipt_path=args.prompt_file.with_name('desktop-session.json')
    while True:
        try:
            with connection(config['hermes_desktop']) as (rpc,owner):
                run_session(rpc,prompt,config,receipt_path,owner=owner)
            return 0
        except (OSError,ValueError,TimeoutError,ConnectionClosed,httpx.HTTPError) as exc:
            if not receipt_path.exists():
                # An actionable private launch receipt; the queue retains its existing failure handling.
                write_receipt(args.prompt_file.with_name('desktop-error.json'),{'error':type(exc).__name__,
                    'detail':'Could not start a native session in the selected Hermes desktop backend.'})
                return 1
            receipt=json.loads(receipt_path.read_text())
            if receipt.get('backend_owner') and not process_matches(receipt['backend_owner']):return 1
            time.sleep(2)  # Reconnect to the same session; never recreate/replay its prompt.


if __name__=='__main__':raise SystemExit(main())
