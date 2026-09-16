"""Operator cleanup preserves posting identity, evidence and portal accounts."""
import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from job_applier.managed import ProtocolError
from job_applier.managed_api import create_app
from test_local_sessions import setup, reserve, connect
from test_dispatch_queue import enqueue
from test_workday_dom import ROOT, JSDOM


@pytest.mark.parametrize('reason', ['Test job', 'Manually applied'])
def test_cancel_preserves_history_accounts_and_rediscovery_then_restores(tmp_path, reason):
    s, asset, jobs, _, _ = setup(tmp_path)
    session = connect(s, reserve(s, asset, jobs))
    s.session_stopped(session['id'], reason='Synthetic failed attempt', browser_stopped=True)
    s.account_update(namespace='employer0.example.test', identity_id='candidate', state='confirmed',
                     credential_ref='credential:fixture/account', request_id='account-fixture', evidence='Synthetic sign-in')
    before = s.attempt(session['attempt_id'])
    account = s.account_strategy(namespace='employer0.example.test', identity_id='candidate')
    enqueue(s, asset, jobs)
    legacy = s.request_run(request_id='legacy', job_ids=[jobs[0]['id'], jobs[1]['id']],
                           identity_id='candidate', browser_profile='legacy-fixture')
    with s.tx() as db:
        db.execute("INSERT INTO answer_retry_requests(id,job_id,identity_id,state,requested_at) VALUES ('answer',?,'candidate','queued',?)", (jobs[0]['id'], s.now()))
    result = s.set_job_disposition(job_ids=[jobs[0]['id']], disposition='canceled', reason=reason)
    assert result['jobs'][0]['disposition'] == 'canceled'
    assert result['jobs'][0]['disposition_reason'] == reason
    assert s.attempt(session['attempt_id']) == before
    assert s.account_strategy(namespace='employer0.example.test', identity_id='candidate') == account
    again = s.intake(url=jobs[0]['url'] + '?utm_source=rediscovery')
    assert again['id'] == jobs[0]['id'] and again['disposition'] == 'canceled'
    assert s.job(jobs[0]['id'])['status'] == before['outcome']
    with s.tx() as db:
        assert db.execute("SELECT state FROM answer_retry_requests WHERE id='answer'").fetchone()[0] == 'canceled'
        assert db.execute('SELECT state FROM run_jobs WHERE run_id=? AND job_id=?', (legacy['id'], jobs[0]['id'])).fetchone()[0] == 'skipped'
        assert db.execute('SELECT state FROM run_jobs WHERE run_id=? AND job_id=?', (legacy['id'], jobs[1]['id'])).fetchone()[0] == 'pending'
    for action in (lambda: enqueue(s, asset, [jobs[0]], request='new', retry=True),
                   lambda: reserve(s, asset, jobs, request='new-session')):
        with pytest.raises(ProtocolError, match='job_canceled'): action()
    assert s.queue_take()['job_id'] == jobs[1]['id']
    s.set_job_disposition(job_ids=[jobs[0]['id']], disposition='active')
    assert s.job(jobs[0]['id'])['status'] == before['outcome']
    assert not any(q['job_id'] == jobs[0]['id'] and q['state'] == 'queued' for q in s.queue_status()['items'])
    assert enqueue(s, asset, [jobs[0]], request='restored', retry=True)['items'][0]['state'] == 'queued'


def test_cancel_requests_existing_stop_without_claiming_browser_closed(tmp_path):
    s, asset, jobs, _, _ = setup(tmp_path)
    session = connect(s, reserve(s, asset, jobs))
    before = s.attempt(session['attempt_id'])
    result = s.set_job_disposition(job_ids=[jobs[0]['id']], disposition='canceled', reason='Unable to complete')
    assert result['stop_requested_run_ids'] == [session['run_id']]
    with s.tx() as db:
        assert db.execute('SELECT control FROM runs WHERE id=?', (session['run_id'],)).fetchone()[0] == 'stop_requested'
    assert s.session(session['id'])['ended_at'] is None
    assert s.attempt(session['attempt_id']) == before


def test_cancel_and_restore_do_not_clear_submission_suppression(tmp_path):
    s, _, jobs, _, _ = setup(tmp_path)
    s.set_job_disposition(job_ids=[jobs[0]['id']], disposition='canceled', reason='Test job')
    # An in-flight confirmation may arrive after the cancellation request.
    with s.tx() as db: db.execute("UPDATE jobs SET status='applied' WHERE id=?", (jobs[0]['id'],))
    s.set_job_disposition(job_ids=[jobs[0]['id']], disposition='active')
    with s.tx() as db:
        with pytest.raises(ProtocolError, match='already_applied'): s._assert_not_suppressed(db, jobs[0]['id'])


def test_bulk_cancel_rechecks_final_dispositions_inside_transaction(tmp_path):
    s, _, jobs, _, _ = setup(tmp_path)
    s.set_job_disposition(job_ids=[jobs[0]['id']], disposition='canceled', reason='Posting closed')
    canceled = s.job(jobs[0]['id'])
    # Model a successful submission arriving after the operator selected the rows.
    with s.tx() as db: db.execute("UPDATE jobs SET status='applied' WHERE id=?", (jobs[1]['id'],))
    result = s.set_job_disposition(job_ids=[j['id'] for j in jobs], disposition='canceled', reason='Test job')
    assert [j['id'] for j in result['jobs']] == [jobs[2]['id']]
    assert set(result['skipped_job_ids']) == {jobs[0]['id'], jobs[1]['id']}
    assert s.job(jobs[0]['id']) == canceled
    assert s.job(jobs[1]['id'])['disposition'] == 'active'


def test_disposition_batch_is_atomic_and_operator_only(tmp_path):
    s, _, jobs, _, _ = setup(tmp_path)
    with pytest.raises(ProtocolError):
        s.set_job_disposition(job_ids=[jobs[0]['id'], 'missing'], disposition='canceled', reason='Test job')
    assert s.job(jobs[0]['id'])['disposition'] == 'active'
    app = create_app(s, operator_token='synthetic-operator-token-32chars', worker_tokens={'synthetic-worker-token-32chars': 'worker'})
    client = TestClient(app, base_url='http://127.0.0.1')
    payload = {'job_ids': [jobs[0]['id']], 'disposition': 'canceled', 'reason': 'Posting closed'}
    headers = {'X-JobBot-Instance': s.instance_id, 'Authorization': 'Bearer synthetic-worker-token-32chars'}
    assert client.post('/v1/set_job_disposition', json=payload, headers=headers).status_code == 403
    headers['Authorization'] = 'Bearer synthetic-operator-token-32chars'
    assert client.post('/v1/set_job_disposition', json=payload, headers=headers).status_code == 200
    assert next(j for j in s.view()['jobs'] if j['id'] == jobs[0]['id'])['disposition_reason'] == 'Posting closed'


def test_cancel_linked_posting_and_capacity_wait_without_touching_other_jobs(tmp_path):
    s, asset, jobs, _, _ = setup(tmp_path)
    reserve(s, asset, jobs, index=0)
    reserve(s, asset, jobs, index=1)
    waiting = reserve(s, asset, jobs, index=2)
    assert waiting['state'] == 'capacity_wait'
    with s.tx() as db:
        for job in jobs[1:]:
            db.execute('INSERT INTO job_identity_keys VALUES (?,?,?)', ('fixture-linked', job['id'], 'Synthetic verified identity'))
    result = s.set_job_disposition(job_ids=[jobs[2]['id']], disposition='canceled', reason='Test job')
    assert {j['id'] for j in result['jobs']} == {j['id'] for j in jobs[1:]}
    assert s.session(waiting['id'])['ended_at']
    assert s.job(jobs[0]['id'])['disposition'] == 'active'
    s.set_job_disposition(job_ids=[jobs[1]['id']], disposition='active')
    assert s.job(jobs[2]['id'])['disposition'] == 'active'


def test_dashboard_history_filters_and_selection_survive_polling():
    if not JSDOM.exists(): pytest.skip('optional jsdom fixture dependency not installed')
    harness = r'''
const fs=require('fs'),{JSDOM}=require(process.argv[1]),d=JSON.parse(fs.readFileSync(0,'utf8'));
const w=new JSDOM(d.html,{url:'http://localhost/',runScripts:'outside-only'}).window;
w.setInterval=()=>0;w.fetch=()=>new Promise(()=>{});
w.eval(d.script+'\nwindow.draw=v=>{state.view=v;renderQueue(v)};');
const v={jobs:[{id:'open',company:'Acme',title:'Engineer',status:'blocked',disposition:'active'},
 {id:'cancel',company:'Old Test',title:'Analyst',status:'failed',disposition:'canceled',disposition_reason:'Test job'},
 {id:'submitted',company:'Submitted Co',title:'Manager',status:'applied',disposition:'active'}],
 candidates:[],assets:[],answer_queue:{groups:[]},dispatch_queue:{items:[]},
 local_runtime:{workspaces:[{}],sessions:[...Array.from({length:15},(_,i)=>({id:'old'+i,job_id:'cancel',state:'stopped',ended_at:'2026-09-01T00:00:00Z'})),{id:'live',job_id:'open',state:'connected'}]}};
w.draw(v);
const doc=w.document, history=doc.getElementById('session-history');
if(!history||history.open)throw Error('History must start collapsed');
if(!doc.querySelector('[data-progress-key="live:application"]'))throw Error('Current work hidden by old sessions');
if(doc.getElementById('queue-rows').textContent.includes('Old Test'))throw Error('Canceled visible in active list');
doc.querySelector('#queue-rows input').click();
const filter=doc.getElementById('job-filter');filter.value='canceled';filter.dispatchEvent(new w.Event('change'));
if(!doc.getElementById('queue-rows').textContent.includes('Test job'))throw Error('Canceled reason missing');
if(!doc.getElementById('selection').textContent.includes('No jobs'))throw Error('Hidden selection retained');
if(!doc.getElementById('start-application-btn').disabled)throw Error('Canceled jobs queueable');
doc.querySelector('#queue-rows input').click();
if(doc.getElementById('restore-selected').disabled)throw Error('Restore unavailable');
doc.getElementById('session-history').open=true;doc.getElementById('session-history').scrollTop=120;w.draw(v);
if(!doc.getElementById('session-history').open)throw Error('Polling collapsed opened history');
if(doc.getElementById('session-history').scrollTop!==120)throw Error('Polling reset history scroll');
filter.value='all';filter.dispatchEvent(new w.Event('change'));
doc.getElementById('select-unfinished').click();
const checked=[...doc.querySelectorAll('#queue-rows input:checked')];
if(checked.length!==1||!checked[0].getAttribute('aria-label').includes('Acme'))throw Error('Bulk selection includes submitted or canceled');
v.jobs.push({id:'startup-failure',company:'Startup Failure',status:'queued',disposition:'active'});
v.dispatch_queue.items.push({job_id:'startup-failure',state:'finished',outcome:'failed',detail:'Executor did not start'});
filter.value='attention';filter.dispatchEvent(new w.Event('change'));
if(!doc.getElementById('queue-rows').textContent.includes('Startup Failure'))throw Error('Queue startup failure missing from Needs attention');
const search=doc.getElementById('job-search');search.value='acme';search.dispatchEvent(new w.Event('input'));
if(doc.querySelectorAll('#queue-rows tr').length!==1||!doc.getElementById('queue-rows').textContent.includes('Acme'))throw Error('Search did not filter jobs');
const reason=doc.getElementById('cancel-reason');reason.value='Manually applied';
if(reason.value!=='Manually applied')throw Error('Manually applied reason unavailable');
doc.getElementById('select-unfinished').click();
let sent;
w.fetch=(url,options)=>{sent={url,body:JSON.parse(options.body)};return new Promise(()=>{});};
doc.getElementById('cancel-selected').click();
if(sent?.url!=='/v1/set_job_disposition'||sent.body.reason!=='Manually applied'||sent.body.disposition!=='canceled'||JSON.stringify(sent.body.job_ids)!=='["open"]')throw Error('Manual application reason was not sent for the selected job');
console.log('Dashboard cleanup controls passed');w.close();
'''
    result = subprocess.run(['node', '-e', harness, str(JSDOM)], input=json.dumps({
        'html': (ROOT/'job_applier/static/jobbot.html').read_text(encoding='utf-8'),
        'script': (ROOT/'job_applier/static/jobbot.js').read_text(encoding='utf-8')}),
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr
