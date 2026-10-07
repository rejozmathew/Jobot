"""Discovery producers and enqueue actors are separate, retained evidence."""
import json
from pathlib import Path

from job_applier.managed import Service
from test_dispatch_queue import runtime_fixture, enqueue
from test_dispatch_queue_ui import dashboard_check
from test_harvest_handoff import get_intake_results_module


def test_source_observations_preserve_runs_and_do_not_relabel_history(tmp_path):
    s = Service.create(tmp_path/'sources.db', instance_id='sources')
    fields = dict(url='https://example.test/jobs/1', source_type='linkedin_alert_email', source_id='message:job')
    job = s.intake(**fields)
    assert s.view()['jobs'][0]['sources'][0]['observations'] == []
    for run in ['run-one', 'run-one', 'run-two']:
        s.intake(**fields, producer='hermes_scheduled_discovery', discovery_run_id=run,
                 discovery_profile='jobbot-discovery')
    row = s.view()['jobs'][0]
    assert row['created_at'] == job['created_at']
    assert row['source_count'] == 1
    observations = row['sources'][0]['observations']
    assert [r['discovery_run_id'] for r in observations] == ['run-one', 'run-two']
    assert all(r['producer'] == 'hermes_scheduled_discovery' for r in observations)
    assert all(r['discovery_profile'] == 'jobbot-discovery' for r in observations)
    assert 'producer' not in json.loads(s.job(job['id'])['metadata_json'])


def test_enqueue_origin_is_preserved_when_another_process_rediscovers(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    original = enqueue(s, asset, [jobs[0]], producer='hermes_scheduled_discovery',
                       enqueue_origin='discovery', discovery_run_id='run-one')['items'][0]
    repeated = enqueue(s, asset, [jobs[0]], request='later', producer='dashboard',
                       enqueue_origin='manual_retry')['items'][0]
    assert repeated == original
    assert original['producer'] == 'hermes_scheduled_discovery'
    latest = s.queue_status()['latest_by_job'][jobs[0]['id']]
    assert latest['enqueue_origin'] == 'discovery'
    assert latest['discovery_run_id'] == 'run-one'
    s.queue_complete(original['id'], outcome='interrupted')
    s.queue_reconcile(identity_id='candidate', resume_asset_id=asset['id'])
    retry = s.queue_status()['latest_by_job'][jobs[0]['id']]
    assert retry['enqueue_origin'] == 'automatic_retry'
    assert retry['producer'] == 'queue_worker'
    assert retry['discovery_run_id'] is None
    assert s.queue_status()['latest_by_job'][jobs[1]['id']]['enqueue_origin'] == 'automatic_intake'


def test_harvest_cli_supplies_process_context_to_intake_and_enqueue(tmp_path):
    s, _, jobs, _, cfg = runtime_fixture(tmp_path)
    path = tmp_path/'records.json'
    path.write_text(json.dumps([dict(url=jobs[0]['url'], source_type='linkedin_alert_email',
        source_id='message:1', verdict='Apply', producer='page-instruction-forgery')]))
    module = get_intake_results_module()
    args = ['--config', cfg['config_path'], '--input', str(path), '--enqueue',
            '--producer', 'hermes_scheduled_discovery', '--discovery-run-id', 'run-one',
            '--discovery-profile', 'jobbot-discovery']
    assert module.main(args) == 0
    assert module.main(args) == 0
    source = next(x for x in s.view()['jobs'] if x['id'] == jobs[0]['id'])['sources'][-1]
    assert len(source['observations']) == 1
    assert source['observations'][0]['producer'] == 'hermes_scheduled_discovery'
    item = s.queue_status()['items'][0]
    assert item['producer'] == 'hermes_scheduled_discovery'
    assert item['discovery_run_id'] == 'run-one'
    assert item['discovery_profile'] == 'jobbot-discovery'
    assert item['enqueue_origin'] == 'discovery'


def test_scheduled_brief_includes_actual_run_and_profile(tmp_path):
    from job_applier.harvest_runtime import run_harvest
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    cfg['harvest_hermes_command'] = ['hermes', '--profile', 'jobbot-discovery', 'chat', '--query-file', '{prompt_file}']
    # Use a synthetic selection rather than inheriting the machine's Hermes profile.
    s.configure({'application_model_override': True, 'reasoning_provider': 'fixture',
                 'reasoning_model': 'fixture-model'}, expected_version=s.settings_view()['version'])
    def launch(command, **kwargs):
        task = Path(command[command.index('--query-file')+1])
        text = task.read_text(encoding='utf-8')
        assert '--producer' in text and 'hermes_scheduled_discovery' in text
        assert '--discovery-run-id' in text and task.parent.name in text
        assert '--discovery-profile' in text and 'jobbot-discovery' in text
        return type('Done', (), {'returncode': 0})()
    run_harvest(cfg, s, scheduled=True, enqueue=True, launcher=launch)


def test_dashboard_shows_source_process_and_separate_enqueue_actor():
    dashboard_check(r'''
v.jobs=[{id:'one',company:'Example',status:'queued',sources:[{source_type:'linkedin_alert_email',
 source_id:'message:1',observations:[{producer:'hermes_scheduled_discovery',discovery_run_id:'run-one',
 discovery_profile:'jobbot-discovery',recorded_at:'2026-09-16T12:00:00Z'}]}]},
 {id:'old',status:'queued',sources:[{source_type:'greenhouse'}]}];
v.dispatch_queue.latest_by_job={one:{state:'queued',enqueue_origin:'automatic_intake',producer:'queue_worker'}};
w.draw(v);
let rows=doc.querySelectorAll('#queue-rows tr');
const first=rows[0].cells[6].textContent;
assert(first.includes('LinkedIn alert email'),'Feed missing');
assert(first.includes('Hermes scheduled discovery'),'Discovery process missing');
assert(first.includes('jobbot-discovery')&&first.includes('run-one'),'Run/profile missing');
assert(first.includes('Automatic pickup')&&first.includes('Queue worker'),'Enqueue actor missing');
assert(first.includes('Latest queue entry:')&&!first.includes('First queued:'),'Latest-only response mislabeled as original queue entry');
assert(rows[1].cells[6].textContent.includes('Not recorded'),'Historical process invented');
v.jobs[0].queue_origins=[{producer:'hermes_scheduled_discovery',enqueue_origin:'discovery'},
 {producer:'queue_worker',enqueue_origin:'automatic_retry'}];
w.draw(v);rows=doc.querySelectorAll('#queue-rows tr');
assert(rows[0].cells[6].textContent.includes('First queued: Discovery handoff'),'Original queue actor hidden by retry');
assert(rows[0].cells[6].textContent.includes('Automatic retry'),'Retry history missing');
v.jobs[0].sources[0].observations[0].producer='<img src=x onerror=alert(1)>';
w.draw(v);assert(!doc.querySelector('#queue-rows img'),'Producer rendered as HTML');
''')


def test_migration_preserves_old_sources_and_queue_rows_without_guessing(tmp_path):
    from job_applier.managed_migrations import migrate
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    item = enqueue(s, asset, [jobs[0]])['items'][0]
    old_sources = s.sources(jobs[0]['id'])
    with s.tx() as db:
        db.execute('DROP TABLE source_observations')
        for column in ('enqueue_origin','producer','discovery_run_id','discovery_profile'):
            db.execute('ALTER TABLE dispatch_queue DROP COLUMN '+column)
        db.execute('DELETE FROM schema_migrations WHERE version=21')
    migrate(s.db_path)
    assert s.sources(jobs[0]['id']) == old_sources
    assert s.queue_status()['items'][0]['producer'] is None
    assert s.queue_status()['items'][0]['id'] == item['id']
    assert s.view()['jobs']


def test_uuid_links_and_optional_missing_metadata_are_nonblocking(tmp_path):
    s, asset, jobs, _, _ = runtime_fixture(tmp_path)
    run = '12345678-1234-1234-1234-123456789012'
    s.intake(url=jobs[0]['url'], producer='external_import', discovery_run_id=run)
    assert s.sources(jobs[0]['id'])[0]['observations'][0]['discovery_run_id'] == run
    item = enqueue(s, asset, [jobs[0]], discovery_run_id=run)['items'][0]
    assert item['discovery_run_id'] == run and item['producer'] is None
    s.intake(url=jobs[1]['url'], producer={'unsupported': 'object'})
    assert s.sources(jobs[1]['id'])[0]['observations'] == []
    s.intake(url=jobs[2]['url'], producer='token=private-value')
    assert s.sources(jobs[2]['id'])[0]['observations'][0]['producer'] == '[REDACTED]'


def test_managed_cli_records_its_boundary_and_preserves_supplied_producer(tmp_path):
    from job_applier.managed_cli import main
    s, _, jobs, _, cfg = runtime_fixture(tmp_path)
    args = ['call', '--config', cfg['config_path'], '--operation', 'intake', '--payload']
    assert main(args+[json.dumps({'url':jobs[0]['url']})]) == 0
    assert s.sources(jobs[0]['id'])[0]['observations'][0]['producer'] == 'managed_cli'
    assert main(args+[json.dumps({'url':jobs[0]['url'], 'producer':'external_feed'})]) == 0
    assert [r['producer'] for r in s.sources(jobs[0]['id'])[0]['observations']] == ['managed_cli','external_feed']


def test_dashboard_intake_sends_its_process():
    dashboard_check(r'''
w.noRefresh();let sent;
w.fetch=async(path,options)=>{sent=JSON.parse(options.body);return {ok:true,status:200,json:async()=>({id:'new'})};};
doc.getElementById('job-url').value='https://example.test/job/1';
await doc.getElementById('intake-form').onsubmit({preventDefault(){}});
assert(sent.producer==='dashboard'&&sent.source_type==='manual','Dashboard omitted its provenance');
''')
