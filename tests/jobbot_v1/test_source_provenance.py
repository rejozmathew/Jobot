"""Source attribution and disposition times use retained evidence, not refresh time."""
from job_applier.managed import Service
from test_local_sessions import setup, reserve, connect
from test_dispatch_queue_ui import dashboard_check


def test_rediscovery_preserves_first_source_and_added_time(tmp_path):
    s = Service.create(tmp_path/'sources.db', instance_id='sources')
    s.now = lambda: '2026-09-14T12:00:00+00:00'
    job = s.intake(url='https://example.test/jobs/1', source_type='job_harvester:google_jobs', source_id='harvester-1')
    s.now = lambda: '2026-09-15T12:00:00+00:00'
    s.intake(url=job['url'], source_type='linkedin_alert_email', source_id='message-2:job-1')
    s.intake(url=job['url'], source_type='linkedin_alert_email', source_id='message-2:job-1')
    row = s.view()['jobs'][0]
    assert row['created_at'] == job['created_at']
    assert row['source_count'] == 2
    assert [r['source_type'] for r in row['sources']] == ['job_harvester:google_jobs', 'linkedin_alert_email']
    assert row['sources'][0]['discovered_at'] == job['created_at']
    assert row['last_disposition'] is None
    # Records imported before provenance tracking remain explicitly unknown.
    with s.tx() as db:
        db.execute('DELETE FROM job_sources')
    assert s.view()['jobs'][0]['sources'] == []


def test_last_disposition_survives_new_attempt_and_metadata_updates(tmp_path):
    s, asset, jobs, _, _ = setup(tmp_path)
    session = connect(s, reserve(s, asset, jobs))
    s.now = lambda: '2026-09-17T12:00:00+00:00'
    s.session_stopped(session['id'], reason='Fixture stopped', browser_stopped=True)
    ended = s.attempt(session['attempt_id'])
    s.now = lambda: '2026-09-18T12:00:00+00:00'
    s.intake(url=jobs[0]['url'], company='New label')
    s.set_job_disposition(job_ids=[jobs[0]['id']], disposition='canceled', reason='Fixture cleanup')
    row = next(j for j in s.view()['jobs'] if j['id'] == jobs[0]['id'])
    assert row['last_disposition'] == {'at': s.now(), 'value': 'canceled', 'source': 'operator'}
    s.now = lambda: '2026-09-19T12:00:00+00:00'
    s.set_job_disposition(job_ids=[jobs[0]['id']], disposition='active')
    row = next(j for j in s.view()['jobs'] if j['id'] == jobs[0]['id'])
    assert row['last_disposition']['value'] == 'active'
    # A newer running attempt must not hide a prior completed outcome.
    with s.tx() as db:
        db.execute('UPDATE jobs SET disposition_at=NULL WHERE id=?', (jobs[0]['id'],))
    connect(s, reserve(s, asset, jobs, request='second'))
    row = next(j for j in s.view()['jobs'] if j['id'] == jobs[0]['id'])
    assert row['last_disposition'] == {'at': ended['completed_at'], 'value': ended['outcome'], 'source': 'application'}


def test_dispatch_completion_is_a_disposition(tmp_path):
    s, asset, jobs, _, _ = setup(tmp_path)
    item = s.queue_enqueue(job_ids=[jobs[0]['id']], identity_id='candidate', resume_asset_id=asset['id'], request_id='source-test')['items'][0]
    s.queue_complete(item['id'], outcome='interrupted', detail='Executor exited')
    row = next(j for j in s.view()['jobs'] if j['id'] == jobs[0]['id'])
    assert row['last_disposition']['value'] == 'interrupted'
    assert row['last_disposition']['source'] == 'queue'


def test_queue_renders_sources_times_and_unknown_without_html_injection():
    dashboard_check(r'''
v.jobs=[{id:'one',company:'Example',status:'queued',created_at:'2026-09-15T12:00:00Z',
 sources:[{source_type:'job_harvester:google_jobs',source_id:'record-1',discovered_at:'2026-09-15T12:00:00Z'},
 {source_type:'linkedin_alert_email',source_id:'<img src=x onerror=alert(1)>',discovered_at:'2026-09-16T12:00:00Z'}],
 last_disposition:{at:'2026-09-17T12:00:00Z',value:'interrupted',source:'application'}},
 {id:'old',status:'queued',sources:[]}];
w.draw(v);
const rows=doc.querySelectorAll('#queue-rows tr');
assert(rows[0].cells.length===9,'Missing provenance columns');
assert(rows[0].cells[6].textContent.includes('Job Harvester / Google Jobs'),'Original source absent');
assert(rows[0].cells[6].textContent.includes('LinkedIn alert email'),'Additional source absent');
assert(rows[0].cells[6].textContent.includes('record-1'),'Source reference absent');
assert(!rows[0].querySelector('img'),'Source rendered as unsafe HTML');
assert(rows[0].cells[7].textContent!=='—','Added time absent');
assert(rows[0].cells[8].textContent.includes('Interrupted'),'Outcome absent');
assert(rows[1].cells[6].textContent.includes('Unknown'),'Invented historical source');
assert(rows[1].cells[8].textContent.includes('Not recorded'),'Invented disposition time');
''')
