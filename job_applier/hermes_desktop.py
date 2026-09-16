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
from websockets.exceptions import ConnectionClosed

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


class RPC:
    def __init__(self, socket):
        self.socket=socket
        self.sequence=0

    def call(self, method, params):
        self.sequence+=1
        rid=self.sequence
        self.socket.send(json.dumps({'jsonrpc':'2.0','id':rid,'method':method,'params':params}))
        deadline=time.monotonic()+60
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Hermes desktop RPC response timed out')
            frame=self.socket.recv(timeout=remaining)
            for line in frame.splitlines():
                message=json.loads(line)
                if message.get('id')!=rid:continue
                if 'error' in message:
                    # Do not copy arbitrary server payloads (which can contain private prompts).
                    raise ValueError('Hermes desktop RPC failed: '+method+' ('+str(message['error'].get('code'))+')')
                return message['result']


@contextmanager
def connection(options):
    url,owner=discover_backend(options)
    with httpx.Client(trust_env=False,timeout=15) as client:
        response=client.get(url+'/')
        response.raise_for_status()
    # Same short-lived loopback bootstrap credential used by the installed desktop.
    match=re.search(r'window\.__HERMES_SESSION_TOKEN__\s*=\s*("[^"\n]+")',response.text)
    if not match:raise ValueError('Hermes desktop bootstrap credential is unavailable')
    token=json.loads(match.group(1))
    websocket_url='ws'+url[4:]+'/api/ws?'+urlencode({'token':token})
    with connect(websocket_url,proxy=None,max_size=None,open_timeout=15) as socket:
        yield RPC(socket),owner


def write_receipt(path, receipt):
    from .queue_runtime import private_write
    temporary=path.with_suffix('.tmp')
    private_write(temporary,json.dumps(receipt,indent=2))
    temporary.replace(path)


def session_active(rpc, session_id):
    rows=rpc.call('session.active_list',{})['sessions']
    row=next((row for row in rows if row['id']==session_id),None)
    return row is not None and row['status']!='idle'


def run_session(rpc, prompt, config, receipt_path, *, sleep=time.sleep, owner=None):
    options=config['hermes_desktop']
    receipt=json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    if receipt is None:
        params={'source':'desktop','cwd':str(REPOSITORY),'hidden':False,'close_on_disconnect':False}
        if options.get('profile'):params['profile']=options['profile']
        created=rpc.call('session.create',params)
        receipt={key:created[key] for key in ('session_id','stored_session_id')}
        receipt.update(state='created',backend_owner=owner)
        write_receipt(receipt_path,receipt)
        if options.get('yolo'):
            rpc.call('config.set',{'session_id':receipt['session_id'],'key':'yolo','value':'on','scope':'session'})
        skills=options.get('skills') or []
        prefix=('Read these installed skills for this task: '+', '.join(skills)+'.\n') if skills else ''
        prefix+=('Actual conversation ID: '+receipt['stored_session_id']+'. Use --driver-id '+
                 receipt['stored_session_id']+' for this application runtime request.\n\n')
        # Persist before sending: a lost reply must not submit the application task twice.
        receipt['state']='submitting'
        write_receipt(receipt_path,receipt)
        rpc.call('prompt.submit',{'session_id':receipt['session_id'],'text':prefix+prompt,'surface':'desktop'})
        receipt['state']='submitted'
        write_receipt(receipt_path,receipt)
    while session_active(rpc,receipt['session_id']):
        sleep(2)
    receipt['state']='finished'
    write_receipt(receipt_path,receipt)
    return receipt


def orphan_is_active(service, item):
    """Recover a crashed monitor without stopping its still-running native turn."""
    # The queue already persists the exact dispatch config beside the task.
    # Config path is supplied by the same dispatcher, never inferred from a DB name.
    root=getattr(service,'desktop_dispatch_spool',None)
    if not root:return False
    receipt_path=Path(root)/'dispatch'/item['id']/'desktop-session.json'
    if not receipt_path.exists():return False
    receipt=json.loads(receipt_path.read_text())
    if receipt['state']=='finished':return False
    owner=receipt.get('backend_owner')
    if owner and not process_matches(owner):return False
    config=json.loads(receipt_path.with_name('runtime.json').read_text())
    try:
        with connection(config['hermes_desktop']) as (rpc,_):
            return session_active(rpc,receipt['session_id'])
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
