"""Explicit runtime/database ownership and legacy suppression, without migration."""
import importlib.util
import json
import sqlite3
from pathlib import Path
import pytest


def module():
    assert importlib.util.find_spec('job_applier.application_runtime'), 'Portable runtime must exist'
    from job_applier import application_runtime
    return application_runtime


def old_db(path):
    c=sqlite3.connect(path); c.execute('CREATE TABLE jobs(id TEXT,url TEXT,status TEXT)')
    c.execute('INSERT INTO jobs VALUES (?,?,?)',('old-id','https://tenant.wd1.myworkdayjobs.com/en-US/Jobs/job/City/Role_R1','applied'))
    c.commit(); c.close()


def test_legacy_suppression_is_readonly_and_matches_workday_locale_apply_variant(tmp_path):
    m=module(); p=tmp_path/'legacy.db'; old_db(p); before=p.read_bytes()
    hits=m.history_matches([str(p)],'https://tenant.wd1.myworkdayjobs.com/Jobs/job/City/Role_R1/apply')
    assert hits[0]['status']=='applied'
    assert p.read_bytes()==before
    assert not m.history_matches([str(p)],'https://other.wd1.myworkdayjobs.com/Jobs/job/City/Role_R1/apply')


def test_missing_history_does_not_create_empty_sqlite_file(tmp_path):
    m=module(); p=tmp_path/'missing.db'
    with pytest.raises(ValueError,match='history_unavailable'):m.history_matches([str(p)],'https://example.test/job')
    assert not p.exists()


def test_doctor_rejects_wrong_instance_without_writes(tmp_path):
    m=module(); p=tmp_path/'managed.db'; c=sqlite3.connect(p)
    c.execute('CREATE TABLE instance(id TEXT)');c.execute("INSERT INTO instance VALUES ('actual')");c.commit();c.close()
    config=tmp_path/'config.json';config.write_text(json.dumps({'db_path':str(p),'instance_id':'wrong','cdp_url':'http://127.0.0.1:9223'}))
    before=p.read_bytes()
    with pytest.raises(ValueError,match='instance_mismatch'):m.inspect_runtime(str(config))
    assert p.read_bytes()==before


def test_relative_database_is_never_resolved_from_cwd(tmp_path):
    m=module(); p=tmp_path/'config.json';p.write_text(json.dumps({'db_path':'job_applier.db','instance_id':'x','cdp_url':'http://127.0.0.1:9223'}))
    with pytest.raises(ValueError,match='absolute_database_required'):m.inspect_runtime(str(p))


def test_portable_advance_refuses_legacy_duplicate_before_browser(tmp_path):
    m=module(); from job_applier import workday_fast
    assert hasattr(workday_fast,'advance'), 'Portable managed advance must exist'
    p=tmp_path/'legacy.db';old_db(p)
    class Client:
        def call(self,op,**kw):
            if op=='health': return {'instance_id':'test','db_path':str(tmp_path/'new.db')}
            if op=='application_context':return {'job':{'url':'https://tenant.wd1.myworkdayjobs.com/en-US/Jobs/job/City/Role_R1'},'attempt':{'worker_id':'w','fence':1}}
            pytest.fail('No browser or writer call permitted for legacy duplicate: '+op)
    result=workday_fast.advance({'instance_id':'test','db_path':str(tmp_path/'new.db'),'legacy_history_paths':[str(p)]},Client(),{'attempt_id':1,'worker_id':'w','fence':1},{'target_id':'tab'})
    assert result['reason']=='legacy_history_suppression'


def test_portable_advance_requires_owned_target_and_matching_worker():
    m=module(); from job_applier import workday_fast
    assert hasattr(workday_fast,'advance')
    with pytest.raises(ValueError,match='invalid_fast_parameters'):
        workday_fast.advance({},None,{}, {'target_id':'tab','javascript':'anything'})
