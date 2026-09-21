"""Synthetic employers only: posting identity survives source and label changes."""
import pytest

from job_applier.managed import Service, ProtocolError
from job_applier.managed_identity import linked_jobs
from test_local_sessions import setup


@pytest.mark.parametrize('board,host', [('acme', 'careers.acme.example.test'), ('northstar', 'work.northstar.example.test')])
@pytest.mark.parametrize('source', ['employer_search', 'job_harvester:linkedin', 'manual'])
def test_rediscovery_uses_posting_not_changed_labels_or_requisition(tmp_path, board, host, source):
    service = Service.create(tmp_path / 'history.db', instance_id='fixture')
    first = service.intake(url=f'https://boards.greenhouse.io/{board}/jobs/12345',
        company=board, title='Director, Analytics', namespace=board,
        requisition_id='12345', identity_evidence='synthetic verified posting')
    with service.tx() as db:
        db.execute("UPDATE jobs SET status='applied' WHERE id=?", (first['id'],))
    again = service.intake(url=f'http://{host}/careers/jobs/12345?gh_jid=12345',
        company=board, title='Incorrect discovered title', namespace=board,
        requisition_id='987', identity_evidence='synthetic verified posting',
        source_type=source, source_id='unrelated-feed-reference')
    assert again['id'] == first['id']
    assert again['title'] == 'Director, Analytics'
    assert again['requisition_id'] == '12345'
    with pytest.raises(ProtocolError, match='already_applied'):
        service.retry(again['id'])
    assert len(service.sources(first['id'])) == 2


def test_source_posting_id_can_supply_board_without_company_name(tmp_path):
    service = Service.create(tmp_path / 'history.db', instance_id='fixture')
    first = service.intake(url='https://boards.greenhouse.io/acme/jobs/12345')
    again = service.intake(url='https://careers.example.test/openings?gh_jid=12345',
        source_type='different_feed', source_id='greenhouse:acme:12345')
    assert again['id'] == first['id']


def test_real_distinct_postings_and_employers_stay_distinct(tmp_path):
    service = Service.create(tmp_path / 'history.db', instance_id='fixture')
    rows = [service.intake(url=url, company='Same display name', title='Director',
        namespace=board, requisition_id='unreliable-shared-value', identity_evidence='synthetic')
        for board, url in [
            ('acme', 'https://boards.greenhouse.io/acme/jobs/12345'),
            ('acme', 'https://careers.example.test/careers/jobs/67890?gh_jid=67890'),
            ('northstar', 'https://boards.greenhouse.io/northstar/jobs/12345')]]
    assert len({row['id'] for row in rows}) == 3
    with service.tx() as db:
        assert all(linked_jobs(db, row['id']) == [row['id']] for row in rows)


@pytest.mark.parametrize('url,source_id', [
    ('https://other.example.test/careers?gh_jid=12345', 'generic-feed-item'),
    ('https://other.example.test/careers?gh_jid=12345', 'greenhouse:acme:67890'),
    ('https://other.example.test/careers/jobs/67890?gh_jid=12345', 'greenhouse:acme:12345'),
    ('https://other.example.test/careers/jobs/67890/apply?gh_jid=12345', 'greenhouse:acme:12345'),
    ('https://other.example.test/careers?gh_jid=12345&gh_jid=67890', 'greenhouse:acme:12345'),
])
def test_unknown_or_conflicting_identity_does_not_merge(tmp_path, url, source_id):
    service = Service.create(tmp_path / 'history.db', instance_id='fixture')
    first = service.intake(url='https://boards.greenhouse.io/acme/jobs/12345')
    other = service.intake(url=url, source_type='employer_search', source_id=source_id)
    assert other['id'] != first['id']


def test_unverified_namespace_alone_does_not_link_another_domain(tmp_path):
    service = Service.create(tmp_path / 'history.db', instance_id='fixture')
    first = service.intake(url='https://boards.greenhouse.io/acme/jobs/12345')
    other = service.intake(url='https://unverified.example.test/?gh_jid=12345', namespace='acme')
    assert other['id'] != first['id']


@pytest.mark.parametrize('first_url,second_url', [
    ('https://acme.myworkdayjobs.com/en-US/Careers/job/City/Director_R100',
     'https://acme.myworkdayjobs.com/en-GB/Careers/job/Elsewhere/Renamed_R100/apply'),
    ('https://www.linkedin.com/jobs/view/12345', 'https://www.linkedin.com/jobs/view/new-title-12345'),
    ('https://careers-acme.icims.com/jobs/12345/director/job',
     'https://careers-acme.icims.com/jobs/12345/login'),
])
def test_shared_identity_service_retains_other_ats_equivalence(tmp_path, first_url, second_url):
    service = Service.create(tmp_path / 'history.db', instance_id='fixture')
    first = service.intake(url=first_url, namespace='acme', requisition_id='first', identity_evidence='synthetic')
    second = service.intake(url=second_url, namespace='acme', requisition_id='changed', identity_evidence='synthetic',
        source_type='job_harvester:google_jobs', source_id='different-source')
    assert second['id'] == first['id']


def test_opaque_query_identity_is_retained(tmp_path):
    service = Service.create(tmp_path / 'history.db', instance_id='fixture')
    rows = [service.intake(url=f'https://careers.example.test/openings?gh_jid=12345&token={token}',
        namespace='acme', requisition_id='12345', identity_evidence='synthetic') for token in ('first', 'second')]
    assert rows[0]['id'] != rows[1]['id']


@pytest.mark.parametrize('status,disposition,expected', [('applied','active','already_applied'), ('blocked','canceled','canceled')])
def test_existing_duplicate_queue_is_settled_without_rewriting_history(tmp_path, status, disposition, expected):
    from job_applier.managed_migrations import migration_23
    service, asset, _, _, _ = setup(tmp_path)
    # Seed the two separate records exactly as a previous version could store them.
    first = service.intake(url='https://boards.greenhouse.io/acme/jobs/12345', namespace='acme',
        requisition_id='12345', identity_evidence='synthetic')
    other = service.intake(url='https://careers.example.test/careers/jobs/12345?gh_jid=12345')
    service.queue_enqueue(job_ids=[other['id']], identity_id='candidate', resume_asset_id=asset['id'], request_id='pending')
    with service.tx() as db:
        db.execute('UPDATE jobs SET status=?,disposition=? WHERE id=?', (status, disposition, first['id']))
        db.execute("UPDATE jobs SET namespace='acme',requisition_id='wrong' WHERE id=?", (other['id'],))
        migration_23(db)
        migration_23(db)  # additive and idempotent
        assert set(linked_jobs(db, first['id'])) == {first['id'], other['id']}
    service.queue_reconcile(identity_id='candidate', resume_asset_id=asset['id'])
    with service.tx() as db:
        row = db.execute("SELECT state,outcome FROM dispatch_queue WHERE request_id='pending'").fetchone()
        assert tuple(row) == ('finished', expected)
    assert service.job(first['id'])['status'] == status
    assert service.job(other['id'])['requisition_id'] == 'wrong'


def test_unsuccessful_history_still_allows_retry_across_sources(tmp_path):
    service, asset, _, _, _ = setup(tmp_path)
    first = service.intake(url='https://boards.greenhouse.io/acme/jobs/12345')
    with service.tx() as db:
        db.execute("UPDATE jobs SET status='submission_unknown' WHERE id=?", (first['id'],))
    other = service.intake(url='https://careers.example.test/openings?gh_jid=12345',
        source_type='job_harvester:google_jobs', source_id='greenhouse:acme:12345')
    assert other['id'] == first['id']
    queued = service.queue_enqueue(job_ids=[other['id']], identity_id='candidate', resume_asset_id=asset['id'], request_id='new-request')
    assert queued['items'][0]['state'] == 'queued'
