"""Offline JobBot acceptance — no credentials, employers or live browsers."""
import importlib.util
import sqlite3
import pytest


def new_service(tmp_path):
    assert importlib.util.find_spec('job_applier.managed') is not None, 'managed service is not implemented'
    from job_applier.managed import Service
    return Service.create(tmp_path/'synthetic.db', instance_id='synthetic-windows', settings={'mode':'development'})


def test_D1_new_instance_and_Q1_shared_intake(tmp_path):
    service = new_service(tmp_path)
    first = service.intake(url='https://careers.example.test/job/42?utm_source=manual&rx_job=42', source_type='manual', source_id='m1', company='Fixture Company')
    second = service.intake(url='https://careers.example.test/job/42?rx_job=42&utm_source=other', source_type='discovery', source_id='d1')
    assert first['id'] == second['id']
    assert len(service.sources(first['id'])) == 2
    assert service.job(first['id'])['eligibility'] == 'held'
    assert service.health()['instance_id'] == 'synthetic-windows'
    assert service.health()['submission_mode'] == 'review'
    with sqlite3.connect(service.db_path) as db:
        assert db.execute('select count(*) from jobs').fetchone()[0] == 1
        assert db.execute('select max(version) from schema_migrations').fetchone()[0] >= 1
    with pytest.raises(FileExistsError):
        type(service).create(service.db_path, instance_id='overwritten', settings={})


def test_Q2_conservative_identity_and_verified_aliases(tmp_path):
    service = new_service(tmp_path)
    a = service.intake(url='https://careers.example.test/apply?token=jobA&rx_job=1', source_id='a')
    b = service.intake(url='https://careers.example.test/apply?token=jobB&rx_job=2', source_id='b')
    assert a['id'] != b['id']
    c = service.intake(url='https://careers.example.test/requisition/9', source_id='c', namespace='example:tenant/site', requisition_id='9', identity_evidence='official_job_metadata')
    d = service.intake(url='https://apply.example.test/role/9', source_id='d', namespace='example:tenant/site', requisition_id='9', identity_evidence='official_job_metadata')
    assert c['id'] == d['id']
    with pytest.raises(ValueError):
        service.intake(url='https://careers.example.test/reset-password?token=secret', source_id='e')
