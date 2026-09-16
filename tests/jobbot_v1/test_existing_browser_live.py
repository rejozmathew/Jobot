"""Opt-in real Brave proof against localhost only, with a disposable profile."""
import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import threading

import pytest

from job_applier.application_runtime import resolve_config, session_call, start
from job_applier.cdp_client import CDPBrowser
from job_applier.managed import Service
from job_applier.workspace_host import browser_command, endpoint_info, ensure_host, workspace_record
from job_applier.workspace_process import process_matches
from tests.jobbot_v1.test_local_browser_lifecycle import free_port, wait_for


pytestmark=pytest.mark.skipif(not os.environ.get('JOBBOT_BROWSER_TEST_EXE'),reason='Explicit browser needed for isolated existing-browser fixture')


def test_real_existing_browser_flag_tabs_retry_restart_and_crash(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data=b'<title>Local shared-browser fixture</title><input id="answer"><p>Synthetic application</p><button id="popup" onclick="window.open(\'/popup\',\'fixture-popup\')">Open fixture popup</button>'
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(data)
        def log_message(self,*args):pass
    web=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=web.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{web.server_port}'
    service=Service.create(tmp_path/'managed.db',instance_id='shared-browser-fixture')
    service.identity(identity_id='fixture',person_key='fixture',email='fixture@example.test',profile={'identity':{'email':'fixture@example.test'}})
    resume=tmp_path/'resume.pdf';resume.write_bytes(b'Synthetic fixture document')
    asset=service.register_asset(identity_id='fixture',kind='resume',version='1',storage_ref=resume.as_uri(),sha256=hashlib.sha256(resume.read_bytes()).hexdigest(),provenance={'source':'synthetic'})
    profile=tmp_path/'profile';profile.mkdir()
    workspace={'id':'shared','user_data_dir':str(profile),'browser_executable':os.environ['JOBBOT_BROWSER_TEST_EXE'],
               'cdp_url':f'http://127.0.0.1:{free_port()}','mode':'headed','connection_mode':'existing'}
    cfg={'instance_id':service.instance_id,'db_path':str(service.db_path),'transport':'local','identity_id':'fixture',
         'resume_asset_id':asset['id'],'spool_dir':str(tmp_path/'spool'),'workspaces':[workspace],
         'require_simplify':False,'authorize_requested_urls':True,'legacy_history_paths':[]}
    path=tmp_path/'runtime.json';path.write_text(json.dumps(cfg));cfg=resolve_config(path)
    # Deliberately independent of JobBot's browser launcher: this represents the
    # user opening their browser, with no --enable-automation or property spoof.
    process=subprocess.Popen([workspace['browser_executable'],'--user-data-dir='+str(profile),
        '--remote-debugging-address=127.0.0.1','--remote-debugging-port='+workspace['cdp_url'].rsplit(':',1)[1],
        '--no-first-run','--no-default-browser-check',base+'/dashboard',base+'/mail'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    endpoint=workspace['cdp_url'];sessions=[];checks={}
    def command(method,params=None):return asyncio.run(browser_command(endpoint,method,params))
    def pages():return [t for t in command('Target.getTargets')['targetInfos'] if t['type']=='page']
    def evaluate(target,expression):
        async def read():
            browser=await CDPBrowser.connect(endpoint,target_id=target)
            try:return await (await browser.get_current_page()).evaluate(expression)
            finally:await browser.close()
        return asyncio.run(read())
    def available():
        try:return len(pages())==2
        except Exception:return False
    def assert_baseline():
        assert {t['targetId']:t['url'] for t in pages()}==baseline
        assert process.poll() is None
        assert evaluate(dashboard,'document.cookie')=='fixture=retained'
    def apply(request):
        result=start(cfg,url=base+'/jobs/fixture',driver_id='fixture-driver',request_id=request)
        sessions.append(result['session_id'])
        assert result['state']=='connected',result
        assert result['metadata']['readiness']['navigator_webdriver'] is False
        assert evaluate(result['target_id'],'navigator.webdriver') is False
        return result
    try:
        wait_for(available)
        baseline={t['targetId']:t['url'] for t in pages()}
        dashboard=next(t for t,u in baseline.items() if u.endswith('/dashboard'))
        wait_for(lambda:evaluate(dashboard,'document.readyState==="complete" && location.pathname==="/dashboard"'))
        checks['before_attach']=evaluate(dashboard,'navigator.webdriver')
        assert checks['before_attach'] is False
        evaluate(dashboard,"document.cookie='fixture=retained; path=/'")
        a=apply('first')
        checks['after_attach']=evaluate(dashboard,'navigator.webdriver')
        checks['application_tab']=evaluate(a['target_id'],'navigator.webdriver')
        assert checks['after_attach'] is False and checks['application_tab'] is False
        repeat=start(cfg,url=base+'/jobs/fixture',driver_id='fixture-driver',request_id='first')
        assert repeat['target_id']==a['target_id'] and len(pages())==3
        assert session_call(cfg,a['session_id'],'browser',{'method':'fill','selector':'#answer','value':'synthetic'},'fixture-driver')['committed']
        assert evaluate(a['target_id'],'navigator.webdriver') is False
        session_call(cfg,a['session_id'],'browser',{'method':'click','selector':'#popup'},'fixture-driver')
        wait_for(lambda:len(pages())==4)
        session_call(cfg,a['session_id'],'finish',{'outcome':'blocked','evidence':'Synthetic missing code','quiescent':True},'fixture-driver')
        wait_for(lambda:service.session(a['session_id'])['ended_at'])
        assert_baseline()
        b=apply('retry')
        assert b['attempt_id']!=a['attempt_id']
        assert b['metadata']['readiness']['employer_storage']['status']=='retained'
        session_call(cfg,b['session_id'],'pause',driver_id='fixture-driver')
        wait_for(lambda:service.session(b['session_id'])['state']=='paused')
        assert_baseline()
        session_call(cfg,b['session_id'],'attach',driver_id='fixture-driver')
        wait_for(lambda:service.session(b['session_id'])['state']=='connected')
        checks['after_resume']=evaluate(service.session(b['session_id'])['target_id'],'navigator.webdriver')
        assert checks['after_resume'] is False
        session_call(cfg,b['session_id'],'restart',{},'fixture-driver')
        wait_for(lambda:service.session(b['session_id'])['state']=='connected')
        replacement=service.session(b['session_id'])
        assert replacement['attempt_id']==b['attempt_id'] and replacement['target_id']!=b['target_id']
        checks['after_restart']=evaluate(replacement['target_id'],'navigator.webdriver')
        assert checks['after_restart'] is False and len(pages())==3
        # Host death cannot kill the user's browser. The next host retires only
        # the durably recorded abandoned application tab before releasing it.
        host=json.loads(workspace_record(service,'shared')['host_identity_json'])
        os.kill(host['pid'],signal.SIGTERM)
        wait_for(lambda:not process_matches(host))
        assert process.poll() is None
        ensure_host(cfg,'shared')
        wait_for(lambda:service.session(b['session_id'])['ended_at'])
        assert_baseline()
        c=apply('stop')
        session_call(cfg,c['session_id'],'stop',driver_id='fixture-driver')
        wait_for(lambda:service.session(c['session_id'])['ended_at'])
        assert_baseline()
        d=apply('manual-close')
        command('Target.closeTarget',{'targetId':d['target_id']})
        wait_for(lambda:service.session(d['session_id'])['ended_at'])
        assert_baseline()
        (tmp_path/'automation-flag-evidence.json').write_text(json.dumps(checks,indent=2))
    finally:
        for sid in sessions:
            try:
                if not service.session(sid)['ended_at']:session_call(cfg,sid,'stop',driver_id='fixture-driver')
            except Exception:pass
        # Test owns only this disposable fixture browser; production host never
        # issues Browser.close against an existing/shared browser.
        try:command('Browser.close')
        except Exception:pass
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)
        web.shutdown();web.server_close()
