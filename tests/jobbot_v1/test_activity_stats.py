"""Application statistics use disposable history, independent of current job status."""
from fastapi.testclient import TestClient
import pytest

from job_applier.managed_api import create_app
from job_applier.managed_shared import ProtocolError
from test_ownership import ready
from test_dispatch_queue_ui import dashboard_check


def history(tmp_path):
    service, _, jobs = ready(tmp_path, count=3, settings={'timezone': 'America/Chicago'})
    service.now = lambda: '2026-10-03T17:00:00+00:00'
    asset = service.register_asset(identity_id='candidate', kind='resume', version='fixture',
        storage_ref='asset:fixture', sha256='a'*64, provenance={'source': 'synthetic'})
    rows = [
        (560, jobs[0], '2026-10-03T05:00:00Z', 'applied', '2026-10-04T01:00:00Z'),
        (562, jobs[0], '2026-10-03T01:00:00-05:00', 'applied', '2026-10-03T07:00:00Z'),
        (563, jobs[1], '2026-10-03 08:00:00', 'already_applied', '2026-10-03T09:00:00Z'),
        (564, jobs[1], '2026-10-03T10:00:00Z', 'blocked', '2026-10-03T11:00:00Z'),
        (565, jobs[2], '2026-10-03T12:00:00Z', None, None),
        (559, jobs[2], '2026-10-03T04:59:59Z', 'interrupted', '2026-10-03T10:00:00Z'),
        (558, jobs[2], '2026-09-26T05:00:00Z', 'submission_unknown', '2026-10-03T11:00:00Z'),
        (557, jobs[2], '2026-09-04T05:00:00Z', 'failed', '2026-09-04T06:00:00Z'),
        (556, jobs[2], '2026-09-03T05:00:00Z', 'skipped', '2026-09-03T06:00:00Z'),
        (600, jobs[2], '2026-10-05T05:00:00Z', 'applied', '2026-10-05T06:00:00Z'),
    ]
    with service.tx() as db:
        db.executemany('INSERT INTO application_attempts(id,job_id,platform,started_at,outcome,completed_at) VALUES (?,?,\'fixture\',?,?,?)', rows)
        db.execute("UPDATE jobs SET disposition='canceled' WHERE id=?", (jobs[1],))
        db.execute('INSERT INTO job_archives VALUES (?,?,?,?,?)', (jobs[2], service.now(), 'synthetic', 'synthetic', 'synthetic'))
        for i, start in enumerate(['2026-10-03T06:00:00Z', '2026-10-03T07:00:00Z', None, '2026-10-03T04:59:59Z']):
            db.execute('INSERT INTO dispatch_queue(id,request_id,job_id,identity_id,resume_asset_id,state,created_at,started_at) VALUES (?,?,?,?,?,?,?,?)',
                (f'd{i}', f'q{i}', jobs[0], 'candidate', asset['id'], 'finished' if start else 'queued', '2026-10-01T00:00:00Z', start))
    return service


def test_start_day_cohort_counts_retries_and_distinct_successes(tmp_path):
    service = history(tmp_path)
    stats = service.activity_stats(period='1d')
    assert stats['timezone'] == 'America/Chicago'
    assert stats['start_date'] == stats['end_date'] == '2026-10-03'
    assert stats['attempts'] == 5
    assert stats['attempt_ids'] == {'first': 560, 'last': 565}
    assert stats['jobs'] == 3  # Includes canceled/archived jobs and all retries.
    assert stats['dispatches'] == 2  # Started in cohort; queued-only is excluded.
    assert stats['outcomes'] == {'applied': 2, 'already_applied': 1, 'blocked': 1, 'active': 1}
    assert stats['submitted_jobs'] == 1
    assert stats['submission_rate_per_attempt'] == 40
    assert stats['submission_rate_per_job'] == pytest.approx(100/3)
    assert stats['recent_attempts'][0]['id'] == 565
    assert 'profile_json' not in stats['recent_attempts'][0]


def test_periods_custom_dates_empty_and_pagination(tmp_path):
    service = history(tmp_path)
    assert service.activity_stats(period='7d')['attempts'] == 6
    assert service.activity_stats(period='30d')['attempts'] == 8
    assert service.activity_stats(period='lifetime')['attempts'] == 9
    day = service.activity_stats(period='custom', start_date='2026-09-26', end_date='2026-09-26')
    assert day['outcomes'] == {'submission_unknown': 1}
    empty = service.activity_stats(period='custom', start_date='2026-08-01', end_date='2026-08-01')
    assert empty['attempts'] == empty['jobs'] == 0
    assert empty['submission_rate_per_job'] is None
    assert empty['submission_rate_per_attempt'] is None
    assert empty['attempt_ids'] == {'first': None, 'last': None}
    first = service.activity_stats(period='lifetime', limit=2)
    second = service.activity_stats(period='lifetime', limit=2, offset=2)
    assert first['attempts'] == second['attempts'] == 9
    assert [a['id'] for a in first['recent_attempts']] == [565, 564]
    assert [a['id'] for a in second['recent_attempts']] == [563, 562]
    for kwargs in ({'period': 'bad'}, {'period': 'custom', 'start_date': 'bad', 'end_date': '2026-10-03'},
                   {'period': 'custom', 'start_date': '2026-10-04', 'end_date': '2026-10-03'}, {'offset': -1}):
        with pytest.raises(ProtocolError):
            service.activity_stats(**kwargs)


def test_calendar_day_boundary_at_daylight_saving_transition(tmp_path):
    service, _, jobs = ready(tmp_path, count=1, settings={'timezone': 'America/Chicago'})
    service.now = lambda: '2026-11-02T12:00:00Z'
    with service.tx() as db:
        for i, start in enumerate(['2026-11-01T04:59:59Z', '2026-11-01T05:00:00Z', '2026-11-02T05:59:59Z', '2026-11-02T06:00:00Z']):
            db.execute("INSERT INTO application_attempts(job_id,platform,started_at) VALUES (?,'fixture',?)", (jobs[0], start))
    assert service.activity_stats(period='custom', start_date='2026-11-01', end_date='2026-11-01')['attempts'] == 2


def test_aggregates_are_not_truncated_to_history_page_and_keep_all_outcomes(tmp_path):
    service, _, jobs = ready(tmp_path, count=1)
    service.now = lambda: '2026-10-03T17:00:00Z'
    with service.tx() as db:
        for i in range(105):
            db.execute("INSERT INTO application_attempts(job_id,platform,started_at,completed_at,outcome) VALUES (?,'fixture',?,?,?)",
                (jobs[0], '2026-10-03T01:00:00Z', '2026-10-03T02:00:00Z', 'ready_for_review' if i%2 else None))
    stats = service.activity_stats(period='1d')
    assert stats['attempts'] == 105
    assert stats['outcomes'] == {'unrecorded': 53, 'ready_for_review': 52}
    assert len(stats['recent_attempts']) == 25
    assert stats['jobs'] == 1
    assert stats['submission_rate_per_job'] == 0


def test_stats_operator_endpoint(tmp_path):
    service = history(tmp_path)
    client = TestClient(create_app(service, operator_token='o'*24, worker_tokens={'w'*24: 'worker'}), base_url='http://localhost')
    headers = {'Authorization': 'Bearer '+'o'*24, 'X-JobBot-Instance': service.instance_id}
    result = client.post('/v1/activity_stats', headers=headers, json={'period': '1d'})
    assert result.status_code == 200
    assert result.json()['attempts'] == 5
    headers['Authorization'] = 'Bearer '+'w'*24
    assert client.post('/v1/activity_stats', headers=headers, json={}).status_code == 403


def test_activity_ui_keeps_useful_work_and_history_and_switches_cohorts():
    dashboard_check(r'''
const activity=doc.getElementById('tab-run');
assert(activity.contains(doc.getElementById('local-sessions-card')),'Current applications remain outside Activity');
assert(activity.querySelector('details.run-diagnostics'),'Legacy diagnostics are not collapsed');
let calls=[];
const stats={timezone:'America/Chicago',start_date:'2026-10-03',end_date:'2026-10-03',attempts:187,jobs:74,dispatches:186,
 attempt_ids:{first:560,last:746},outcomes:{applied:32,already_applied:3,blocked:125,interrupted:25,submission_unknown:2},
 submitted_jobs:32,submission_rate_per_attempt:32/187*100,submission_rate_per_job:32/74*100,
 offset:0,limit:25,recent_attempts:[{id:746,job_id:'fixture',company:'Example',title:'Engineer',started_at:'2026-10-03T12:00:00Z',outcome:'blocked',completed_at:'2026-10-03T13:00:00Z'}]};
w.fetch=async(path,options)=>{calls.push([path,JSON.parse(options.body)]);return {ok:true,status:200,json:async()=>stats};};
doc.querySelector('nav [data-tab=run]').click();
await new Promise(resolve=>w.setTimeout(resolve,0));
assert(doc.getElementById('activity-metrics').textContent.includes('187'),'Attempt count absent');
assert(doc.getElementById('activity-metrics').textContent.includes('17.1%'),'Per-attempt rate absent');
assert(doc.getElementById('activity-metrics').textContent.includes('43.2%'),'Distinct-job rate absent');
assert(doc.getElementById('activity-cohort').textContent.includes('#560–746'),'Attempt ID span absent');
assert(doc.getElementById('activity-outcomes').textContent.includes('Submission unknown'),'Unknown outcome hidden');
assert(doc.querySelector('#activity-attempt-rows button').textContent.includes('746'),'Attempt history missing');
const period=doc.getElementById('activity-period');period.value='7d';await period.onchange();
assert(calls.at(-1)[1].period==='7d','Period selection not requested');
assert(doc.getElementById('activity-period').value==='7d','Selection reset');
await doc.getElementById('activity-next').onclick();
assert(calls.at(-1)[1].offset===25,'History does not page independently');
period.value='custom';await period.onchange();
assert(!doc.getElementById('activity-custom').hidden,'Custom day selection missing');
doc.getElementById('activity-from').value='2026-09-26';doc.getElementById('activity-to').value='2026-09-26';
await doc.getElementById('activity-custom').onsubmit({preventDefault(){}});
assert(calls.at(-1)[1].start_date==='2026-09-26'&&calls.at(-1)[1].offset===0,'Custom cohort wrong');
// Rapid selection changes must not allow an older response to replace the new cohort.
const pending=[];w.fetch=(path,options)=>new Promise(resolve=>pending.push({resolve,payload:JSON.parse(options.body)}));
period.value='30d';const slow=period.onchange();period.value='lifetime';const fast=period.onchange();
pending[1].resolve({ok:true,status:200,json:async()=>({...stats,attempts:900})});await fast;
pending[0].resolve({ok:true,status:200,json:async()=>stats});await slow;
assert(doc.getElementById('activity-metrics').textContent.includes('900'),'Stale request overwrote lifetime stats');
''')
