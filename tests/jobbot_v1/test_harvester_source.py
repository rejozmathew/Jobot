"""Offline Harvester lead conversion: never enqueue unverified search results."""
import json

from job_applier.harvester_source import convert_export, main


def test_export_preserves_feed_identity_and_candidates_not_fit_verdicts():
    row = {'id': 'record-1', 'source': 'google_jobs', 'url': 'https://aggregator.test/job/1',
           'company': 'Example', 'title': 'Director Data', 'created_at': '2026-01-01T12:00:00',
           'posted_at': '2026-01-01T11:00:00', 'llm_score': 99, 'notes': 'private note',
           'serpapi_apply_options': json.dumps([{'title': 'Employer', 'link': 'https://employer.test/job/1'}])}
    result = convert_export({'items': [row, row], 'total': 20})
    assert len(result['leads']) == 1
    lead = result['leads'][0]
    assert lead['source_type'] == 'job_harvester:google_jobs'
    assert lead['source_id'] == 'record-1'
    assert lead['candidate_urls'] == ['https://aggregator.test/job/1', 'https://employer.test/job/1']
    assert lead['harvester_added_at'] == row['created_at']
    assert 'verdict' not in lead and 'url' not in lead and 'notes' not in lead
    assert lead['reported_posted_at'] == row['posted_at']
    assert result['received'] == 2 and result['duplicate_records'] == 1


def test_bad_rows_report_errors_without_losing_valid_leads():
    result = convert_export([None, {'id': 'broken', 'url': 'javascript:alert(1)'},
                             {'id': 'good', 'source': 'linkedin', 'url': 'https://example.test/job'}])
    assert len(result['errors']) == 2
    assert result['leads'][0]['source_type'] == 'job_harvester:linkedin'
    assert len(result['leads']) == 1


def test_cli_converts_local_export_without_connection_or_intake(tmp_path, monkeypatch):
    original = tmp_path/'export.json'
    output = tmp_path/'leads.json'
    original.write_text(json.dumps([{'id':'one','source':'google_jobs','url':'https://example.test/job'}]))
    monkeypatch.setattr('socket.create_connection', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('network')))
    assert main(['--input', str(original), '--output', str(output)]) == 0
    assert json.loads(output.read_text())['leads'][0]['source_id'] == 'one'


def test_invalid_export_does_not_replace_existing_output(tmp_path):
    original = tmp_path/'bad.json'
    output = tmp_path/'leads.json'
    original.write_text('{}')
    output.write_text('retained')
    assert main(['--input', str(original), '--output', str(output)]) == 2
    assert output.read_text() == 'retained'


def test_csv_export_without_internal_id_has_stable_source_reference(tmp_path):
    source = tmp_path/'export.csv'
    output = tmp_path/'leads.json'
    source.write_text('title,url,source,serpapi_job_id\nDirector,https://example.test/job,google_jobs,provider-1\n')
    assert main(['--input', str(source), '--output', str(output)]) == 0
    assert json.loads(output.read_text())['leads'][0]['source_id'] == 'provider-1'


def test_discovery_brief_can_consume_prepared_leads(tmp_path):
    from job_applier.harvest_runtime import harvest_brief
    from test_dispatch_queue import runtime_fixture
    s, _, _, _, cfg = runtime_fixture(tmp_path)
    cfg['harvest_leads_path'] = str(tmp_path/'leads.json')
    brief = harvest_brief(cfg, s, tmp_path/'records.json')
    assert cfg['harvest_leads_path'] in brief
    assert 'Preserve that source_type/source_id' in brief
    assert 'linkedin_alert_email' in brief
