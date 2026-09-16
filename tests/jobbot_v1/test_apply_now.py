"""Immediate operator requests use synthetic queue records, never live applications."""
import pytest

from job_applier.managed import Service, ProtocolError
from test_dispatch_queue import runtime_fixture, enqueue
from test_dispatch_queue_ui import dashboard_check


def test_apply_now_prioritizes_selected_job_and_is_idempotent(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    enqueue(s, asset, jobs)
    first = enqueue(s, asset, [jobs[2]], request='now', retry=True, start_now=True)
    assert first['queue']['immediate_count'] == 1
    assert first['queue']['wake_requested'] == 1
    assert first['queue']['enabled'] is False
    assert enqueue(s, asset, [jobs[2]], request='now', retry=True, start_now=True)['items'] == first['items']
    assert len(s.queue_status()['items']) == 3
    taken = s.queue_take()
    assert taken['job_id'] == jobs[2]['id']
    assert s.queue_take() is None
    s.queue_complete(taken['id'], outcome='failed')
    assert enqueue(s, asset, [jobs[2]], request='now', retry=True, start_now=True)['items'][0]['state'] == 'finished'
    assert s.queue_status()['immediate_count'] == 0
    assert s.queue_take()['job_id'] == jobs[0]['id']


def test_apply_now_promotes_delayed_retry_without_rewriting_history(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    s.now = lambda: '2026-09-16T10:00:00+00:00'
    enqueue(s, asset, jobs)
    old = s.queue_take()
    s.queue_complete(old['id'], outcome='submission_unknown', detail='Retained uncertainty')
    s.queue_reconcile(identity_id='candidate', resume_asset_id=asset['id'])
    retry = s.queue_status()['latest_by_job'][jobs[0]['id']]
    assert retry['waiting_for_retry']
    response = enqueue(s, asset, [jobs[0]], request='now', retry=True, start_now=True)
    assert response['items'][0]['id'] == retry['id']
    fresh = Service(s.db_path, instance_id=s.instance_id)
    fresh.now = s.now
    status = fresh.queue_status()
    promoted = status['latest_by_job'][jobs[0]['id']]
    assert not promoted['waiting_for_retry']
    assert promoted['attempt_number'] == retry['attempt_number']
    assert promoted['request_id'] == retry['request_id']
    assert promoted['created_at'] == retry['created_at']
    assert status['ready_count'] == 3 and status['scheduled_count'] == 0
    assert fresh.queue_take()['id'] == retry['id']
    history = next(q for q in status['items'] if q['id'] == old['id'])
    assert history['outcome'] == 'submission_unknown' and history['detail'] == 'Retained uncertainty'


def test_paused_worker_retains_each_manual_request_during_an_application(tmp_path, monkeypatch):
    from job_applier.queue_runtime import watch
    s, asset, jobs, _, cfg = runtime_fixture(tmp_path)
    enqueue(s, asset, jobs)
    enqueue(s, asset, [jobs[2]], request='first', retry=True, start_now=True)
    observed = []
    class Finished(Exception):
        pass
    def dispatch(config, service):
        item = service.queue_take()
        observed.append(item['job_id'])
        if len(observed) == 1:
            enqueue(s, asset, [jobs[1]], request='during-run', retry=True, start_now=True)
            assert service.queue_take() is None
        service.queue_complete(item['id'], outcome='ready_for_review')
        return {'state': 'finished'}
    ticks = []
    def tick(seconds):
        ticks.append(seconds)
        if len(ticks) == 3:
            raise Finished()
    monkeypatch.setattr('job_applier.queue_runtime.dispatch_one', dispatch)
    monkeypatch.setattr('job_applier.queue_runtime.time.sleep', tick)
    with pytest.raises(Finished):
        watch(cfg, s)
    assert observed == [jobs[2]['id'], jobs[1]['id']]
    assert s.queue_status()['counts']['queued'] == 1
    assert s.queue_status()['enabled'] is False


@pytest.mark.parametrize('disposition,error', [('canceled', 'job_canceled'), ('applied', 'already_applied')])
def test_apply_now_preserves_existing_operator_and_submission_rules(tmp_path, disposition, error):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    if disposition == 'canceled':
        s.set_job_disposition(job_ids=[jobs[0]['id']], disposition='canceled', reason='Fixture')
    else:
        with s.tx() as db:
            db.execute("UPDATE jobs SET status='applied' WHERE id=?", (jobs[0]['id'],))
    with pytest.raises(ProtocolError, match=error):
        enqueue(s, asset, [jobs[0]], request='now', retry=True, start_now=True)
    assert s.queue_status()['items'] == []


def test_apply_now_button_targets_its_row_and_reports_worker_state():
    dashboard_check(r'''
v.jobs=[{id:'older',company:'Older',status:'queued'}, {id:'chosen',company:'Chosen',status:'queued'}];
v.candidates=[{id:'candidate',email:'fixture@example.test',state:'active'}];
v.assets=[{id:'resume',identity_id:'candidate',kind:'resume',status:'available',storage_ref:'fixture.pdf'}];
v.settings={values:{submission_mode:'review'}};
doc.getElementById('candidate').append(new w.Option('Fixture','candidate'));
doc.getElementById('main-submission-mode').value='review';
w.draw(v);w.noRefresh();
const button=doc.querySelectorAll('#queue-rows tr')[1].querySelector('button[data-apply-now]');
assert(button&&button.textContent==='Apply now','No per-job immediate action');
let calls=[],response={items:[{job_id:'chosen',state:'queued'}],queue:{worker_online:true,counts:{dispatched:1}}};
w.fetch=async(path,options)=>{calls.push([path,JSON.parse(options.body)]);return {ok:true,status:200,json:async()=>response};};
await button.onclick();
assert(calls.length===1&&calls[0][0]==='/v1/queue_enqueue','Must enqueue and wake atomically');
assert(calls[0][1].job_ids.join(',')==='chosen'&&calls[0][1].start_now===true&&calls[0][1].retry===true,'Clicked job not prioritized');
assert(calls[0][1].identity_id==='candidate'&&calls[0][1].resume_asset_id==='resume','Selected materials missing');
assert(doc.getElementById('notice').textContent.includes('Chosen')&&doc.getElementById('notice').textContent.includes('current application'),'No job-specific busy feedback');
response.queue={worker_online:false,counts:{}};
await button.onclick();
assert(doc.getElementById('notice').textContent.includes('offline'),'Offline worker falsely reported as started');
response.queue={worker_online:true,counts:{}};
await button.onclick();
assert(doc.getElementById('notice').textContent.includes('worker'),'Ready request not acknowledged');
v.dispatch_queue.latest_by_job={chosen:{state:'dispatched'}};w.draw(v);
assert(doc.querySelectorAll('#queue-rows tr')[1].querySelector('button[data-apply-now]').textContent==='In progress','Running application offered another start');
assert(doc.getElementById('queue-run-help').textContent.includes('oldest ready job'),'Global control still unexplained');
''')
