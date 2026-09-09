"""Opt-in real Windows/Chromium lifecycle proof on isolated local pages.

Set JOBBOT_BROWSER_TEST_EXE to the installed browser executable. No extension
activity here is represented as official Simplify acceptance.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time

import pytest

from job_applier.application_runtime import resolve_config, session_call, start
from job_applier.managed import Service, ProtocolError
from job_applier.workspace_host import call_host, workspace_record
from job_applier.workspace_process import process_matches


pytestmark=pytest.mark.skipif(os.name!='nt' or not os.environ.get('JOBBOT_BROWSER_TEST_EXE'),reason='Requires explicit installed browser for isolated Windows lifecycle test')


def free_port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def wait_for(fn, timeout=30):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        result=fn()
        if result:return result
        time.sleep(.1)
    raise AssertionError('Timed out waiting for observed lifecycle state')


def test_headed_cold_start_gap_parallel_stop_and_crash(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data=b'<html><head><title>Synthetic local lifecycle</title></head><body><h1>JobBot isolated fixture</h1><label>Fixture input<input id="fixture"></label></body></html>'
            self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def log_message(self,*a):pass
    web=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=web.serve_forever,daemon=True);thread.start()
    service=Service.create(tmp_path/'synthetic.db',instance_id='synthetic-cold-start')
    service.identity(identity_id='fixture',person_key='fixture-person',email='fixture@example.test',profile={'identity':{'email':'fixture@example.test'}})
    resume=tmp_path/'approved.pdf';resume.write_bytes(b'Only an isolated test document')
    asset=service.register_asset(identity_id='fixture',kind='resume',version='1',storage_ref=resume.as_uri(),sha256=hashlib.sha256(resume.read_bytes()).hexdigest(),provenance={'source':'synthetic'})
    workspaces=[]
    for i in range(2):
        profile=tmp_path/f'workspace-{i}';profile.mkdir()
        workspaces.append({'id':f'fixture-{i}','user_data_dir':str(profile),'browser_executable':os.environ['JOBBOT_BROWSER_TEST_EXE'],'cdp_url':f'http://127.0.0.1:{free_port()}','mode':'headed'})
    cfg={'instance_id':service.instance_id,'db_path':str(service.db_path),'transport':'local','identity_id':'fixture','resume_asset_id':asset['id'],
         'spool_dir':str(tmp_path/'spool'),'workspaces':workspaces,'concurrency_limit':2,'require_simplify':False,
         'authorize_requested_urls':True,'legacy_history_paths':[]}
    path=tmp_path/'app.json';path.write_text(json.dumps(cfg),encoding='utf-8');cfg=resolve_config(path)
    url=f'http://127.0.0.1:{web.server_port}/jobs/'
    sessions=[];observations={'http_server':'not started','api_token':'not configured','extension':'not tested'}
    env={k:v for k,v in os.environ.items() if not k.startswith('JOBBOT_')}
    began=time.monotonic()
    try:
        # The ordinary shell actually exits. Its detached host and headed browser persist.
        command=[sys.executable,'-m','job_applier.application_runtime','start',url+'a','--config',str(path),'--driver-id','fixture-driver-a']
        completed=subprocess.run(command,cwd=Path(__file__).resolve().parents[2],env=env,capture_output=True,text=True,timeout=60)
        assert completed.returncode==0,completed.stdout+completed.stderr
        a=json.loads(completed.stdout);sessions.append(a['session_id'])
        assert a['state']=='connected',a
        assert a['metadata']['readiness']['browser_mode']=='headed'
        again=start(cfg,url=url+'a',driver_id='fixture-driver-a')
        assert (again['session_id'],again['attempt_id'],again['target_id'])==(a['session_id'],a['attempt_id'],a['target_id'])
        b=start(cfg,url=url+'b',driver_id='fixture-driver-b');sessions.append(b['session_id'])
        assert b['state']=='connected',b
        assert a['workspace']['user_data_dir']!=b['workspace']['user_data_dir'] and a['workspace']['cdp_url']!=b['workspace']['cdp_url']
        c=start(cfg,url=url+'c',driver_id='fixture-driver-c');sessions.append(c['session_id'])
        assert c['state']=='capacity_wait' and c['capacity_limit']==2
        for item,value in ((a,'A'),(b,'B')):
            result=session_call(cfg,item['session_id'],'browser',{'method':'fill','selector':'#fixture','value':value},item['driver_id'])
            assert result['committed']
        before=service.session_status(a['session_id'])['last_verified_progress_at']
        time.sleep(65)  # Real elapsed time beyond the old 60-second lease, no heartbeat call.
        assert service.session_status(a['session_id'])['last_verified_progress_at']==before
        result=session_call(cfg,a['session_id'],'browser',{'method':'fill','selector':'#fixture','value':'after gap'},a['driver_id'])
        assert result['committed']
        assert service.session_status(a['session_id'])['last_verified_progress_at']>before
        observations['reasoning_gap_seconds']=65
        # Crash one actual host. Windows owns and kills its whole browser tree.
        record=workspace_record(service,a['workspace_id'])
        host=json.loads(record['host_identity_json']);browser=json.loads(record['browser_identity_json'])
        os.kill(host['pid'],signal.SIGTERM)
        wait_for(lambda:not process_matches(host) and not process_matches(browser),10)
        assert session_call(cfg,b['session_id'],'browser',{'method':'fill','selector':'#fixture','value':'B survives A'},b['driver_id'])['committed']
        with pytest.raises(ProtocolError,match='session_recovering'):
            session_call(cfg,a['session_id'],'browser',{'method':'snapshot'},a['driver_id'])
        wait_for(lambda:service.session(a['session_id'])['ended_at'])
        c=start(cfg,url=url+'c',driver_id='fixture-driver-c')
        assert c['state']=='connected' and c['workspace_id']==a['workspace_id'],c
        # Acknowledged pause kills B's old target before another driver attaches.
        paused=session_call(cfg,b['session_id'],'pause',driver_id=b['driver_id'])
        if paused.get('control_pending'):
            # The API can return while the owned process tree is still stopping.
            # Assert the real acknowledgement, not a timing-dependent first reply.
            wait_for(lambda:service.session(b['session_id'])['state']=='paused')
            paused=service.session(b['session_id'])
        assert paused['state']=='paused',paused
        with pytest.raises(ProtocolError):session_call(cfg,b['session_id'],'browser',{'method':'fill','selector':'#fixture','value':'forbidden'},b['driver_id'])
        session_call(cfg,b['session_id'],'attach',driver_id='replacement-driver-b')
        wait_for(lambda:service.session(b['session_id'])['state']=='connected')
        resumed=service.session(b['session_id'])
        assert resumed['target_id']!=b['target_id']
        with pytest.raises(ProtocolError,match='driver_owned_elsewhere'):
            session_call(cfg,b['session_id'],'browser',{'method':'snapshot'},b['driver_id'])
        assert session_call(cfg,b['session_id'],'browser',{'method':'fill','selector':'#fixture','value':'new driver'},'replacement-driver-b')['committed']
        stopped=session_call(cfg,c['session_id'],'stop',driver_id=c['driver_id'])
        assert stopped['state']=='stopped'
        assert session_call(cfg,b['session_id'],'browser',{'method':'snapshot'},'replacement-driver-b')['title']=='Synthetic local lifecycle'
        observations.update(cold_start_seconds=a['elapsed_seconds'],parallel_workspaces=[a['workspace_id'],b['workspace_id']],crash_isolation=True,pause_attach=True,stop_isolation=True,total_seconds=time.monotonic()-began)
    finally:
        for sid in sessions:
            current=service.session(sid)
            try:
                if not current['ended_at']:session_call(cfg,sid,'stop',driver_id=current['driver_id'])
            except Exception:pass
        for workspace in workspaces:
            with service.tx() as db:
                row=db.execute('SELECT * FROM application_sessions WHERE workspace_id=? ORDER BY requested_at DESC LIMIT 1',(workspace['id'],)).fetchone()
            if row:
                try:call_host(cfg,dict(row),'shutdown',{},row['driver_id'])
                except Exception:pass
        web.shutdown();web.server_close()
        (tmp_path/'lifecycle-evidence.json').write_text(json.dumps(observations,indent=2),encoding='utf-8')


def test_workday_auth_with_real_controls_and_shared_local_account_ledger(tmp_path):
    """Actual browser input/clicks, synthetic Workday-shaped form and private DB."""
    import asyncio
    from job_applier.cdp_client import CDPBrowser
    from job_applier.managed_client import LocalClient
    from job_applier.workday_fast import FastRunner
    html=b'''<!doctype html><title>Synthetic Workday authentication</title><main id="root"></main>
    <script>
    let exists=false,created=0,signedIn=0,consentCount=0;
    function render(mode){
      const create=mode==='create',label=create?'Create Account':'Sign In';
      root.innerHTML='<form onsubmit="return false"><h2>'+label+'</h2><input id="email" type="email" autocomplete="username">'+
        '<input id="pw" type="password">'+(create?'<input id="confirm" type="password"><label><input id="privacy" type="checkbox" required>I agree to the Privacy Policy</label><label><input id="marketing" type="checkbox">Send me job alerts</label>':'')+
        '<button id="submitAuth" disabled>'+label+'</button><a id="switch">'+(create?'Sign In':'Create Account')+'</a></form>';
      function validate(){submitAuth.disabled=!(email.value==='fixture@example.test'&&pw.value==='fixture-password'&&(!create||(document.getElementById('confirm').value===pw.value&&privacy.checked)));}
      root.oninput=validate;root.onchange=validate;
      document.getElementById('switch').onclick=()=>render(create?'signin':'create');
      if(create)privacy.onclick=()=>{consentCount++;validate();};
      submitAuth.onclick=()=>{if(create){if(marketing.checked)throw Error('Optional marketing was selected');exists=true;created++;render('signin');}
        else if(exists){signedIn++;root.innerHTML='<h2>My Information</h2><p>Application form</p>';}};
    }
    render('create');
    </script>'''
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(html)
        def log_message(self,*a):pass
    web=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=web.serve_forever,daemon=True).start()
    service=Service.create(tmp_path/'auth.db',instance_id='synthetic-auth')
    service.identity(identity_id='fixture',person_key='fixture',email='fixture@example.test',profile={'identity':{'email':'fixture@example.test'}})
    resume=tmp_path/'approved.pdf';resume.write_bytes(b'Synthetic asset')
    asset=service.register_asset(identity_id='fixture',kind='resume',version='1',storage_ref=resume.as_uri(),sha256=hashlib.sha256(resume.read_bytes()).hexdigest(),provenance={'source':'synthetic'})
    credentials=tmp_path/'credentials.json';credentials.write_text(json.dumps({'accounts':{'default':{'email':'fixture@example.test','password':'fixture-password'}}}))
    workspace={'id':'auth-fixture','user_data_dir':str(tmp_path/'profile'),'browser_executable':os.environ['JOBBOT_BROWSER_TEST_EXE'],'cdp_url':f'http://127.0.0.1:{free_port()}','mode':'headed'}
    cfg={'instance_id':service.instance_id,'db_path':str(service.db_path),'transport':'local','identity_id':'fixture','resume_asset_id':asset['id'],
        'credential_profile_path':str(credentials),'spool_dir':str(tmp_path/'spool'),'workspaces':[workspace],'concurrency_limit':1,
        'require_simplify':False,'authorize_requested_urls':True,'legacy_history_paths':[]}
    path=tmp_path/'app.json';path.write_text(json.dumps(cfg));cfg=resolve_config(path)
    session=None
    try:
        session=start(cfg,url=f'http://127.0.0.1:{web.server_port}/jobs/auth',driver_id='auth-test-driver')
        assert session['state']=='connected',session
        screenshot=session_call(cfg,session['session_id'],'browser',{'method':'screenshot'},session['driver_id'])
        shot=Path(screenshot['image_path'])
        assert shot.is_absolute() and shot.is_relative_to(tmp_path/'spool')
        assert shot.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        assert screenshot['target_id']==session['target_id']
        saved=service.session(session['session_id'])
        host_id=workspace_record(service,saved['workspace_id'])['host_id']
        client=LocalClient(cfg,service=service,authority=(saved['id'],saved['driver_id'],host_id))
        package=service.application_context(saved['attempt_id']);a=package['attempt']
        async def exercise():
            browser=await CDPBrowser.connect(workspace['cdp_url'],target_id=saved['target_id'],expected_mode='headed')
            try:
                page=await browser.get_current_page()
                async def advance_account(runner):
                    deadline=time.monotonic()+60
                    while True:
                        result=await runner.run(seconds=20)
                        if runner.state.get('authentication',{}).get('complete'):return result
                        # A time slice may end after the click but before its
                        # confirmation read. Continue without repeating auth.
                        assert result.get('status')=='waiting',result
                        assert time.monotonic()<deadline,(result,runner.state)
                runner=FastRunner(page,client.call,package,{'attempt_id':a['id'],'worker_id':a['worker_id'],'fence':a['fence']},
                    dict(cfg,cdp_url=workspace['cdp_url']),saved['target_id'],account_lock=lambda **kw:service.coordinate_account(saved['id'],**kw))
                result=await advance_account(runner)
                counts=await page.evaluate('({created,signedIn,consentCount})')
                assert counts=={'created':1,'signedIn':1,'consentCount':1},(result,counts)
                assert runner.state['authentication']['complete']
                assert 'fixture-password' not in json.dumps(runner.state)
                # A later invocation starts on Create Account with no helper state.
                # Its durable portal account must select Sign In and reuse the secret.
                await page.evaluate("render('create')")
                later=FastRunner(page,client.call,service.application_context(a['id']),runner.owner,runner.config,
                    saved['target_id'],account_lock=runner.account_lock)
                await advance_account(later)
                assert await page.evaluate('({created,signedIn,consentCount})')=={'created':1,'signedIn':2,'consentCount':1}
                assert later.state['authentication']['complete']
            finally:await browser.close()
        asyncio.run(exercise())
        strategy=service.account_strategy(namespace='127.0.0.1',identity_id='fixture')
        assert strategy['action']=='sign_in' and strategy['credential_ref']=='credential:profile/accounts/default'
        with service.tx() as db:
            rows=[json.loads(r[0]) for r in db.execute('SELECT payload_json FROM managed_events WHERE attempt_id=?',(a['id'],))]
            assert not db.execute('SELECT 1 FROM account_coordination').fetchone()
        assert any(e.get('status')=='confirmed' for e in rows)
        assert 'fixture-password' not in json.dumps(rows)
    finally:
        if session:
            try:session_call(cfg,session['session_id'],'stop',driver_id=session['driver_id'])
            finally:call_host(cfg,service.session(session['session_id']),'shutdown',{},session['driver_id'])
        web.shutdown();web.server_close()
