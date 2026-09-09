"""Real local dashboard save/retry integration, using synthetic records only."""
import asyncio
import json
import socket
import threading
import time

import uvicorn

from job_applier.managed_api import create_app
from test_answer_queue import QUESTION
from test_local_sessions import setup,connect,own
from test_embedded_forms import fixture_browser


def test_dashboard_saves_drafts_and_queues_answered_applications(tmp_path):
    service,asset,_,_,_=setup(tmp_path/'ledger')
    job=service.intake(url='https://careers.example.test/jobs/qa-1',company='Example Systems',title='Engineering Manager')
    service.eligibility(job['id'],'ready',reason='Synthetic UI fixture')
    session=service.reserve_session(request_id='ui-fixture',job_id=job['id'],identity_id='candidate',driver_id='ui-driver',
        workspace_ids=['workspace-0'],concurrency_limit=1,resume_asset_id=asset['id'])
    session=connect(service,session);owner=own(service,session)
    first=service.request_question(**owner,**QUESTION)
    second=service.request_question(**owner,**dict(QUESTION,field='start_date',question='When could you start?',kind='text',options=[]))
    service.park_questions(**owner)
    service.session_stopped(session['id'],reason='Synthetic browser stopped for answers',browser_stopped=True)
    app=create_app(service,operator_token='fixture-operator-'+('x'*30),worker_tokens={'fixture-worker-'+('y'*30):'worker'})
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    deadline=time.monotonic()+5
    while not server.started:
        assert time.monotonic()<deadline
        time.sleep(.02)
    async def check():
        async with fixture_browser(tmp_path,entry_url=f'http://127.0.0.1:{port}/') as (page,_,__):
            await page._session.call('Emulation.setDeviceMetricsOverride',{'width':1280,'height':1000,'deviceScaleFactor':1,'mobile':False})
            deadline=time.monotonic()+8
            while not await page.evaluate("!!document.querySelector('.answer-application')"):
                assert time.monotonic()<deadline
                await asyncio.sleep(.05)
            await page.evaluate("document.querySelector('[data-tab=answers]').click()")
            assert await page.evaluate("document.getElementById('answer-count').textContent")=='(2)'
            await page.screenshot(str(tmp_path/'answer-queue-before.png'))
            await page.evaluate_function('''args=>{const field=document.getElementById('answer-'+args.id);
                field.value=JSON.stringify(args.value);field.dispatchEvent(new Event('input',{bubbles:true}));}''',{'id':first['id'],'value':['yes','Yes']})
            await page.evaluate_function('''args=>{const field=document.getElementById('answer-'+args.id);
                field.value=args.value;field.dispatchEvent(new Event('input',{bubbles:true}));}''',{'id':second['id'],'value':'After two weeks notice'})
            await page.evaluate('refresh()')
            assert await page.evaluate_function('id=>document.getElementById("answer-"+id).value',second['id'])=='After two weeks notice'
            await page.evaluate("document.querySelector('.answer-actions button').click()")
            deadline=time.monotonic()+5
            while service.answer_queue()['groups'][0]['pending_count']:
                assert time.monotonic()<deadline,await page.evaluate("document.getElementById('notice').textContent")
                await asyncio.sleep(.05)
            assert service.answer_retries(identity_id='candidate')['requests']==[],'Save must not launch or queue work'
            await page.evaluate('refresh()')
            await page.evaluate_function('''id=>{const field=document.getElementById('answer-'+id);
                field.value=JSON.stringify(['no','No']);field.dispatchEvent(new Event('input',{bubbles:true}));}''',first['id'])
            service.answer_questions(answers=[{'question_id':first['id'],'answer':'yes','expected_revision':1}])
            await page.evaluate('saveAnswerGroup(state.view.answer_queue.groups[0],false)')
            assert await page.evaluate_function('id=>JSON.parse(document.getElementById("answer-"+id).value)',first['id'])==['yes','Yes']
            assert 'changed elsewhere' in await page.evaluate("document.getElementById('notice').textContent")
            await page.evaluate("document.getElementById('queue-answered-batch').click()")
            deadline=time.monotonic()+5
            while not service.answer_retries(identity_id='candidate')['requests']:
                assert time.monotonic()<deadline
                await asyncio.sleep(.05)
            await page.evaluate('refresh()')
            await page.screenshot(str(tmp_path/'answer-queue-after.png'))
            assert service.session(session['id'])['ended_at'],'Queueing must not adopt a stopped browser'
            await page.evaluate('showLogin()')
            assert await page.evaluate("document.getElementById('answer-groups').childElementCount")==0
    try:asyncio.run(check())
    finally:
        server.should_exit=True;thread.join(timeout=5);sock.close()
