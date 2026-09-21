"""Isolated browser proof for native activation; no employer pages or profiles."""
import asyncio
import json
import os
from pathlib import Path
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest

from job_applier.cdp_client import CDPBrowser
from job_applier.workspace_process import OwnedProcess
from job_applier.workday_fast import FastRunner, WORKDAY_OBSERVE, WORKDAY_CLICK


def test_native_runner_click_delivers_trusted_event(tmp_path):
    executable=os.environ.get('JOBBOT_BROWSER_TEST_EXE')
    if not executable:pytest.skip('Explicit browser executable required')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data=b'<html><body><button id="account">Create Account</button></body></html>'
            self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    fixture_url=f'http://127.0.0.1:{server.server_port}/'
    profile=tmp_path/'isolated-browser';profile.mkdir()
    process=OwnedProcess.launch([executable,'--headless=new','--disable-gpu','--no-first-run',
        '--remote-debugging-port=0','--user-data-dir='+str(profile),fixture_url],
        stdout_path=tmp_path/'browser.out',stderr_path=tmp_path/'browser.err')
    try:
        portfile=profile/'DevToolsActivePort'
        deadline=time.monotonic()+10
        while not portfile.exists() and time.monotonic()<deadline:time.sleep(.05)
        port=int(portfile.read_text().splitlines()[0]);endpoint=f'http://127.0.0.1:{port}'
        with urllib.request.urlopen(endpoint+'/json/list') as response:tabs=json.load(response)
        target=next(t['id'] for t in tabs if t['type']=='page')
        async def check():
            browser=await CDPBrowser.connect(endpoint,target_id=target,expected_mode='headless')
            try:
                page=await browser.get_current_page()
                deadline=time.monotonic()+5
                while not await page.evaluate("!!document.getElementById('account')"):
                    if time.monotonic()>deadline:raise AssertionError('Fixture did not load')
                    await asyncio.sleep(.05)
                await page.evaluate("document.body.innerHTML='<button id=account>Create Account</button>';window.accepted=0;document.querySelector('button').onclick=e=>{if(e.isTrusted)window.accepted++}")
                observed=await page.evaluate_function(WORKDAY_OBSERVE,{'page_signature':'fixture'})
                observed['native']['auth_submit']=observed['native']['create_account']
                await page.evaluate("document.querySelector('button').click()")
                assert await page.evaluate('window.accepted')==0
                package={'attempt':{'settings_json':{},'profile_json':{}},'job':{'url':'about:blank'}}
                runner=FastRunner(page,lambda *a,**k:None,package,{}, {},target)
                assert await runner.click('native_auth_submit',observed)
                assert await page.evaluate('window.accepted')==1
                await page.evaluate("const cover=document.createElement('div');cover.style='position:fixed;inset:0;z-index:999;background:white';document.body.append(cover)")
                result=await page.click_observed(WORKDAY_CLICK,{'selector':'#account','expected_url':fixture_url})
                assert result['execution']=='not_executed'
                assert await page.evaluate('window.accepted')==1
            finally:await browser.close()
        asyncio.run(check())
    finally:process.stop();server.shutdown();server.server_close()
