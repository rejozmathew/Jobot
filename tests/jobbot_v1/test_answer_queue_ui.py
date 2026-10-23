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
            while not await page.evaluate("!!document.querySelector('.answer-bulk-row')"):
                assert time.monotonic()<deadline
                await asyncio.sleep(.05)
            await page.evaluate("document.querySelector('[data-tab=answers]').click()")
            assert await page.evaluate("document.getElementById('answer-bulk-toggle').textContent")=='Focus on one question'
            await page.evaluate("document.getElementById('answer-bulk-toggle').click()")
            assert await page.evaluate("document.getElementById('answer-count').textContent")=='(2)'
            assert await page.evaluate("document.querySelector('#answer-groups .answer-context').textContent.includes('Example Systems')")
            assert await page.evaluate("document.querySelector('#answer-groups .answer-context').textContent.includes('Engineering Manager')")
            await page.evaluate("""window.answerUxOriginal=state.view;window.answerUxRefresh=refresh;refresh=async()=>{};
                const snapshot=JSON.parse(JSON.stringify(state.view)),base=snapshot.answer_queue.clusters[0];
                snapshot.answer_queue.clusters=Array.from({length:35},(_,i)=>({...base,id:'ux-'+i,question:'Question '+i+' about this position',kind:'text',options:[],
                  requests:[{...base.requests[0],question_id:'ux-question-'+i,company:i===0?'Example Systems':'Employer '+i,title:i===0?'Engineering Manager':'Leadership role '+i}],request_count:1}));
                state.view=snapshot;state.answerSelections={};state.answerKey=null;renderAnswers(snapshot);""")
            assert await page.evaluate("document.querySelectorAll('#answer-list .answer-list-item').length")==12
            assert await page.evaluate("document.querySelectorAll('#answer-groups form').length")==1
            await asyncio.sleep(.2)
            assert await page.evaluate("const button=document.querySelector('#answer-groups [type=submit]').getBoundingClientRect(),panel=document.getElementById('answer-groups').getBoundingClientRect();button.bottom<=panel.bottom&&button.top>=panel.top"),'Save action is outside the visible editor'
            assert await page.evaluate("document.querySelector('#answer-groups .answer-field select').getBoundingClientRect().bottom<=document.querySelector('#answer-groups .answer-save-bar').getBoundingClientRect().top"),'Sticky Save action hides the reuse scope'
            await page.screenshot(str(tmp_path/'answer-workspace-desktop.png'))
            await page.evaluate("document.querySelector('#answer-pagination [data-page=next]').click()")
            assert await page.evaluate("document.querySelector('#answer-pagination').textContent.includes('13–24 of 35')")
            await page._session.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
            await asyncio.sleep(.2)
            await page.screenshot(str(tmp_path/'answer-workspace-mobile.png'))
            assert await page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"),'Mobile layout overflows horizontally'
            assert await page.evaluate("document.getElementById('answer-picker').getBoundingClientRect().height>0"),'Mobile question picker is hidden'
            await page.evaluate("const picker=document.getElementById('answer-picker');picker.selectedIndex=1;picker.dispatchEvent(new Event('change'));")
            assert await page.evaluate("document.querySelector('#answer-groups .answer-context').textContent.includes('Employer 13')")
            await page._session.call('Emulation.setDeviceMetricsOverride',{'width':1920,'height':1080,'deviceScaleFactor':1,'mobile':False})
            await page.evaluate("document.querySelector('#answer-pagination [data-page=previous]').click()")
            await asyncio.sleep(.2)
            await page.screenshot(str(tmp_path/'answer-workspace-wide.png'))
            await page._session.call('Emulation.setDeviceMetricsOverride',{'width':1280,'height':1000,'deviceScaleFactor':1,'mobile':False})
            await page.evaluate("refresh=window.answerUxRefresh;state.view=window.answerUxOriginal;state.answerSelections={};state.answerKey=null;renderAnswers(state.view);delete window.answerUxOriginal;delete window.answerUxRefresh;")
            async def select_question(identifier):
                await page.evaluate_function("""id=>{const cluster=state.view.answer_queue.clusters.find(c=>c.requests.some(r=>r.question_id===id));
                    document.querySelector('[data-answer-id="'+cluster.id+'"]').click();}""",identifier)
            await select_question(first['id'])
            await asyncio.sleep(.2)
            await page.screenshot(str(tmp_path/'answer-queue-before.png'))
            await page.evaluate_function('''args=>{const field=document.getElementById('answer-'+args.id);
                field.value=JSON.stringify(args.value);field.dispatchEvent(new Event('input',{bubbles:true}));}''',{'id':first['id'],'value':['yes','Yes']})
            await select_question(second['id'])
            await page.evaluate_function('''args=>{const field=document.getElementById('answer-'+args.id);
                field.value=args.value;field.dispatchEvent(new Event('input',{bubbles:true}));}''',{'id':second['id'],'value':'After two weeks notice'})
            await page.evaluate('refresh()')
            assert await page.evaluate_function('id=>document.getElementById("answer-"+id).value',second['id'])=='After two weeks notice'
            await page.evaluate("document.querySelector('#answer-groups form').requestSubmit()")
            deadline=time.monotonic()+5
            while next(q for q in service.questions_for_attempt(owner['attempt_id'])['questions'] if q['id']==second['id'])['state']=='pending':
                assert time.monotonic()<deadline
                await asyncio.sleep(.05)
            await page.evaluate('refresh()')
            await select_question(first['id'])
            assert await page.evaluate_function('id=>JSON.parse(document.getElementById("answer-"+id).value)',first['id'])==['yes','Yes'],'Switching questions lost an unsaved draft'
            await page.evaluate("document.querySelector('#answer-groups form').requestSubmit()")
            deadline=time.monotonic()+5
            while service.answer_queue()['groups'][0]['pending_count']:
                assert time.monotonic()<deadline,await page.evaluate("document.getElementById('notice').textContent")
                await asyncio.sleep(.05)
            assert service.answer_retries(identity_id='candidate')['requests']==[],'Save must not launch or queue work'
            await page.evaluate('refresh()')
            assert service.answer_library()['entries']==[], 'Human saves must not become raw learned answers'
            def generalize(payload):
                source=payload['sources'][0]
                return dict(reusable=True,question='Start availability?' if 'start' in source['question'] else 'Work authorization?',
                    answer=source['answer'],scope='global',scope_key='',conditions=source['conditions'],source_equivalent=True,
                    existing_entry_id=None,evidence_quotes=[str(source['answer'])])
            service.learn_answers(generator=generalize);service.learn_answers(generator=generalize)
            await page.evaluate('refresh()')
            await page.evaluate("document.querySelector('#answer-receipt button').click();document.querySelector('[data-learned-mode=current]').click()")
            assert await page.evaluate("!document.getElementById('tab-learned').hidden")
            assert await page.evaluate("document.querySelectorAll('#learned-list .answer-list-item').length")==2
            await asyncio.sleep(.2)
            await page.screenshot(str(tmp_path/'learned-answers.png'))
            await page.evaluate("document.querySelector('nav [data-tab=answers]').click();document.querySelector('[data-answer-mode=ready]').click()")
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
            await asyncio.sleep(.2)
            await page.screenshot(str(tmp_path/'answer-queue-after.png'))
            assert service.session(session['id'])['ended_at'],'Queueing must not adopt a stopped browser'
            await page.evaluate('showLogin()')
            assert await page.evaluate("document.getElementById('answer-groups').childElementCount")==0
            assert await page.evaluate("document.getElementById('learned-detail').childElementCount")==0
    try:asyncio.run(check())
    finally:
        server.should_exit=True;thread.join(timeout=5);sock.close()
