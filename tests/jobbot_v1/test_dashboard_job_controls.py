"""Synthetic dashboard sorting/filtering and URL corrections preserve job history."""
import pytest
from fastapi.testclient import TestClient

from job_applier.managed import Service, ProtocolError
from test_dispatch_queue_ui import dashboard_check
from test_operator_ui import make_test_environment, BASE_URL, OPERATOR_TOKEN, WORKER_TOKEN
from test_dispatch_queue import runtime_fixture, enqueue


def test_url_correction_retains_identity_sources_and_added_time(tmp_path):
    s = Service.create(tmp_path/'jobs.db', instance_id='url-edit')
    original = s.intake(url='https://example.test/jobs/old', source_id='original')
    sources = s.sources(original['id'])
    with s.tx() as db:
        db.execute("UPDATE jobs SET status='applied' WHERE id=?", (original['id'],))
    edited = s.update_job_url(job_id=original['id'], url='https://example.test/jobs/correct?utm_source=test', expected_url=original['url'])
    assert edited['url'] == 'https://example.test/jobs/correct'
    assert (edited['id'], edited['seq_id'], edited['created_at'], edited['status']) == (original['id'], original['seq_id'], original['created_at'], 'applied')
    assert s.sources(original['id']) == sources
    assert s.intake(url=original['url'])['id'] == original['id']
    assert s.intake(url=edited['url'])['id'] == original['id']
    assert s.job(original['id'])['url'] == edited['url']
    with pytest.raises(ProtocolError, match='job_url_changed'):
        s.update_job_url(job_id=original['id'], url='https://example.test/jobs/third', expected_url=original['url'])


def test_url_edit_uses_operator_api_and_existing_url_validation(tmp_path):
    s, _, app = make_test_environment(tmp_path)
    job = s.view()['jobs'][0]
    other = s.intake(url='https://example.test/jobs/other')
    client = TestClient(app, base_url=BASE_URL)
    payload = {'job_id': job['id'], 'url': 'https://example.test/jobs/correct', 'expected_url': job['url']}
    headers = {'X-JobBot-Instance': s.instance_id, 'Authorization': 'Bearer '+WORKER_TOKEN}
    assert client.post('/v1/update_job_url', json=payload, headers=headers).status_code == 403
    headers['Authorization'] = 'Bearer '+OPERATOR_TOKEN
    assert client.post('/v1/update_job_url', json=payload, headers=headers).status_code == 200
    with pytest.raises(ProtocolError, match='job_url_in_use'):
        s.update_job_url(job_id=job['id'], url=other['url'], expected_url=payload['url'])
    with pytest.raises(ProtocolError, match='invalid_job_url'):
        s.update_job_url(job_id=job['id'], url='javascript:alert(1)', expected_url=payload['url'])


def test_sort_filters_and_stable_sequence_numbers():
    dashboard_check(r'''
doc.getElementById('job-filter').value='all';
v.jobs=[{id:'a',seq_id:2,company:'Zulu',status:'queued',created_at:'2026-09-15T12:00:00Z',metadata:{country:'US'},assessment:{recommendation:'Apply'},sources:[{source_type:'manual',source_id:'ref-a'}]},
 {id:'b',seq_id:10,company:'Alpha',status:'applied',created_at:'2026-09-17T12:00:00Z',metadata:{country:'CA'},sources:[{source_type:'linkedin_alert_email',source_id:'ref-b'}],application_timing:{elapsed_seconds:120}},
 {id:'c',seq_id:3,company:'Beta',status:'applied',created_at:'2026-09-16T12:00:00Z',metadata:{country:'US'},assessment:{recommendation:'Apply'},sources:[{source_type:'manual',source_id:'ref-c'}],application_timing:{elapsed_seconds:20}}];
w.draw(v);
const ids=()=>[...doc.querySelectorAll('#queue-rows tr')].map(r=>r.dataset.jobId);
assert(ids().join()==='b,c,a','Default added-date order incorrect');
doc.querySelector('[data-job-sort="sequence"]').click();
assert(ids().join()==='a,c,b','Sequence must sort numerically');
doc.querySelector('[data-job-sort="sequence"]').click();
assert(ids().join()==='b,c,a','Descending sort missing');
doc.querySelector('[data-job-sort="duration"]').click();
assert(ids().join()==='c,b,a','Duration sort or missing-last order incorrect');
doc.getElementById('job-source-filter').value='manual';doc.getElementById('job-source-filter').onchange();
doc.getElementById('job-country-filter').value='United States';doc.getElementById('job-country-filter').onchange();
doc.getElementById('job-assessment-filter').value='Apply';doc.getElementById('job-assessment-filter').onchange();
doc.getElementById('job-added-from').value='2026-09-16';doc.getElementById('job-added-from').onchange();
assert(ids().join()==='c','Combined filters not applied');
assert(doc.querySelector('#queue-rows tr').cells[0].textContent.includes('#3'),'Sequence renumbered by filtering');
doc.getElementById('job-reset-filters').click();
doc.getElementById('job-search').value='ref-b';doc.getElementById('job-search').oninput();
assert(ids().join()==='b','Source reference search missing');
''')


def test_url_editor_keeps_draft_during_refresh_and_saves_explicitly():
    dashboard_check(r'''
v.jobs=[{id:'one',seq_id:1,company:'Example',status:'queued',url:'https://example.test/old'}];
const dialog=doc.getElementById('job-url-dialog');
dialog.showModal=()=>dialog.setAttribute('open','');dialog.close=()=>dialog.removeAttribute('open');
w.draw(v);w.noRefresh();
doc.querySelector('[data-edit-job-url]').click();
doc.getElementById('job-edit-url').value='https://example.test/correct';
v.jobs[0].title='Updated label';w.draw(v);
assert(doc.getElementById('job-edit-url').value==='https://example.test/correct','Polling erased URL draft');
let call;w.fetch=async(path,options)=>{call=[path,JSON.parse(options.body)];return {ok:true,status:200,json:async()=>({...v.jobs[0],url:'https://example.test/correct'})};};
await doc.getElementById('job-url-form').onsubmit({preventDefault(){}});
assert(call[0]==='/v1/update_job_url'&&call[1].job_id==='one','Wrong job update');
assert(call[1].url==='https://example.test/correct'&&call[1].expected_url==='https://example.test/old','Edit not saved with original version');
assert(!dialog.hasAttribute('open'),'Successful save did not close dialog');
''')


def test_manual_batch_reuses_queue_and_keeps_requested_order_across_restart(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    s.now = lambda: '2026-09-17T12:00:00+00:00'
    enqueue(s, asset, jobs)
    running = s.queue_take()
    enqueue(s, asset, [jobs[1]], request='earlier', retry=True, start_now=True)
    ordered = [jobs[2], jobs[1], jobs[0]]  # current job stays running; others are reordered
    first = enqueue(s, asset, ordered, request='selection', retry=True, start_now=True)
    assert len(s.queue_status()['items']) == 3
    assert s.queue_take() is None
    assert enqueue(s, asset, ordered, request='selection', retry=True, start_now=True)['items'] == first['items']
    fresh = Service(s.db_path, instance_id=s.instance_id)
    fresh.now = s.now
    fresh.queue_complete(running['id'], outcome='ready_for_review')
    next_item = fresh.queue_take()
    assert next_item['job_id'] == jobs[2]['id']
    fresh.queue_complete(next_item['id'], outcome='ready_for_review')
    assert fresh.queue_take()['job_id'] == jobs[1]['id']


def test_select_all_tracks_filtered_rows_partial_selection_and_refresh():
    dashboard_check(r'''
v.jobs=[{id:'first',company:'Match First',status:'queued'},
 {id:'second',company:'Match Second',status:'failed'},
 {id:'other',company:'Other',status:'queued'},
 {id:'done',company:'Match Done',status:'applied'},
 {id:'canceled',company:'Match Canceled',status:'queued',disposition:'canceled'}];
doc.getElementById('job-filter').value='all';w.draw(v);
const all=doc.getElementById('select-all-jobs');
assert(all,'Table header needs a select-all checkbox');
assert(doc.getElementById('select-unfinished').textContent==='Select all','Bulk selection label is unclear');
doc.getElementById('job-search').value='Match';doc.getElementById('job-search').oninput();
all.click();
const checked=()=>[...doc.querySelectorAll('#queue-rows input:checked')].map(n=>n.closest('tr').dataset.jobId).sort().join();
assert(checked()==='first,second','Select all must select only unfinished filtered jobs');
assert(all.checked&&!all.indeterminate,'Full selection not reflected in header');
assert(!doc.getElementById('queue-selected-jobs').disabled,'Bulk selection cannot be queued');
doc.querySelector('#queue-rows tr[data-job-id="first"] input').click();
assert(!all.checked&&all.indeterminate,'Partial selection not reflected in header');
w.draw(v);
assert(all.indeterminate&&checked()==='second','Polling lost partial selection');
doc.getElementById('select-unfinished').click();
assert(all.checked&&checked()==='first,second','Toolbar and header selection disagree');
all.click();
assert(checked()===''&&!all.indeterminate,'Header uncheck did not clear selection');
doc.getElementById('job-search').value='Missing';doc.getElementById('job-search').oninput();
assert(all.disabled&&!all.checked&&!all.indeterminate,'Empty view has an active selection checkbox');
doc.getElementById('job-search').value='';doc.getElementById('job-filter').value='canceled';doc.getElementById('job-filter').onchange();
all.click();
assert(checked()==='canceled'&&!doc.getElementById('restore-selected').disabled,'Canceled view bulk restore broken');
doc.getElementById('clear-selection').click();
assert(!all.checked&&!all.indeterminate,'Clear selection left stale header');
doc.getElementById('job-filter').value='submitted';doc.getElementById('job-filter').onchange();
assert(all.disabled,'Submitted-only view must have no queue selection');
''')


def test_queue_selected_uses_table_order_and_one_atomic_request():
    dashboard_check(r'''
v.jobs=[{id:'old',seq_id:1,company:'Old',status:'queued',created_at:'2026-09-15T12:00:00Z'},
 {id:'new',seq_id:2,company:'New',status:'queued',created_at:'2026-09-17T12:00:00Z'}];
v.candidates=[{id:'candidate',email:'fixture@example.test',state:'active'}];
v.assets=[{id:'resume',identity_id:'candidate',kind:'resume',status:'available',storage_ref:'fixture.pdf'}];
v.settings={values:{submission_mode:'review'}};
doc.getElementById('candidate').append(new w.Option('Fixture','candidate'));
doc.getElementById('main-submission-mode').value='review';w.draw(v);w.noRefresh();
doc.getElementById('select-all-jobs').click();
let calls=[],finish;
w.fetch=async(path,options)=>{calls.push([path,JSON.parse(options.body)]);await new Promise(r=>finish=r);return {ok:true,status:200,json:async()=>({items:[{},{}],queue:{worker_online:true}})};};
const pending=doc.getElementById('queue-selected-jobs').onclick();
await doc.getElementById('queue-selected-jobs').onclick();
assert(calls.length===1,'Double click sent duplicate queue requests');
assert(calls[0][1].job_ids.join()==='new,old','Queue ignored displayed order');
assert(calls[0][1].start_now===true&&calls[0][1].retry===true,'Selection does not wake/promote jobs');
finish();await pending;
assert(doc.getElementById('notice').textContent.includes('table order'),'Missing ordered queue receipt');
''')
