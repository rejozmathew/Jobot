"""Dashboard queue feedback uses synthetic records and the shipped JavaScript."""
import json
import subprocess

import pytest

from test_workday_dom import JSDOM, ROOT


def dashboard_check(check):
    if not JSDOM.exists():
        pytest.skip('optional jsdom fixture dependency not installed')
    harness = r'''
const fs=require('fs'),{JSDOM}=require(process.argv[1]),d=JSON.parse(fs.readFileSync(0,'utf8'));
const w=new JSDOM(d.html,{url:'http://localhost/',runScripts:'outside-only'}).window;
w.setInterval=()=>0;w.fetch=()=>new Promise(()=>{});
w.eval(d.script+'\nwindow.draw=v=>{state.view=v;renderQueue(v)};window.noRefresh=()=>{refresh=async()=>{}};');
const doc=w.document;
const v={jobs:[],candidates:[],assets:[],answer_queue:{groups:[]},
 dispatch_queue:{installed:true,worker_online:true,enabled:true,counts:{},items:[]},
 local_runtime:{workspaces:[{}],sessions:[]}};
function assert(ok,reason){if(!ok)throw Error(reason);}
(async()=>{CHECK})().then(()=>w.close()).catch(e=>{console.error(e);w.close();process.exitCode=1;});
'''.replace('CHECK', check)
    result = subprocess.run(['node', '-e', harness, str(JSDOM)], input=json.dumps({
        'html': (ROOT/'job_applier/static/jobbot.html').read_text(encoding='utf-8'),
        'script': (ROOT/'job_applier/static/jobbot.js').read_text(encoding='utf-8')}),
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr


def test_saved_jobs_and_interrupted_requests_are_not_waiting_to_run():
    dashboard_check(r'''
v.jobs=[{id:'saved',company:'Saved Role',status:'queued'},
 {id:'held',company:'Review Role',status:'queued',eligibility:'held'},
 {id:'retry',company:'Interrupted Role',status:'queued'}];
v.dispatch_queue.items=[{job_id:'retry',state:'finished',outcome:'interrupted',detail:'Executor stopped'}];
w.draw(v);
let rows=[...doc.querySelectorAll('#queue-rows tr')];
assert(rows[0].cells[2].textContent.includes('Not queued'),'Saved intake incorrectly claims to be queued');
assert(rows[1].cells[2].textContent.includes('Not queued'),'Review-only intake claims to be queued');
assert(rows[2].cells[2].textContent.includes('Interrupted'),'Interrupted request hidden');
assert(rows[2].cells[2].textContent.includes('Queue selected'),'Interrupted request has no retry guidance');
assert(doc.getElementById('dispatcher-status').textContent.includes('Queue selected'),'Empty queue has no next action');
v.dispatch_queue.items.unshift({job_id:'retry',state:'queued'});
v.dispatch_queue.counts={queued:1,finished:1};w.draw(v);
rows=[...doc.querySelectorAll('#queue-rows tr')];
assert(rows[2].cells[2].querySelector('.badge').textContent==='Queued','Fresh retry still shows interrupted');
v.dispatch_queue.items[0].state='dispatched';v.dispatch_queue.counts={dispatched:1};w.draw(v);
assert(doc.querySelectorAll('#queue-rows tr')[2].cells[2].querySelector('.badge').textContent==='In progress','Live dispatch hidden');
v.dispatch_queue.latest_by_job={saved:{state:'queued'},retry:{state:'finished',outcome:'interrupted'}};
w.draw(v);
assert(doc.querySelectorAll('#queue-rows tr')[0].cells[2].querySelector('.badge').textContent==='Queued','Queue entry outside recent history hidden');
assert(doc.querySelectorAll('#queue-rows tr')[2].cells[2].querySelector('.badge').textContent==='Interrupted','Latest request ignored in favor of history');
''')


def test_run_next_feedback_uses_fresh_server_counts_without_blocking_request():
    dashboard_check(r'''
w.draw(v);w.noRefresh();
let calls=[];
let response={installed:true,worker_online:true,counts:{}};
w.fetch=async(path,options)=>{calls.push([path,JSON.parse(options.body)]);return {ok:true,status:200,json:async()=>response};};
// Stale UI claims queued work; the actual command response says empty.
v.dispatch_queue.counts={queued:2};w.draw(v);
await doc.getElementById('queue-run-next').onclick();
assert(calls.length===1&&calls[0][1].command==='run_next','UI blocked or changed the existing wake request');
assert(doc.getElementById('notice').textContent.includes('No jobs are waiting'),'Empty queue falsely promises a launch');
assert(doc.getElementById('notice').textContent.includes('Queue selected'),'Missing enqueue guidance');
response={worker_online:false,counts:{queued:1}};
await doc.getElementById('queue-run-next').onclick();
assert(doc.getElementById('notice').textContent.includes('offline'),'Offline worker falsely promises a launch');
response={worker_online:true,counts:{dispatched:1}};
await doc.getElementById('queue-run-next').onclick();
assert(doc.getElementById('notice').textContent.includes('already in progress'),'Active request falsely treated as pending work');
response={worker_online:true,counts:{queued:1,dispatched:1}};
await doc.getElementById('queue-run-next').onclick();
assert(doc.getElementById('notice').textContent.includes('current application'),'Busy worker lacks waiting explanation');
response={worker_online:true,counts:{queued:1}};
await doc.getElementById('queue-run-next').onclick();
assert(doc.getElementById('notice').textContent.includes('Request saved'),'Queued request not acknowledged');
''')
