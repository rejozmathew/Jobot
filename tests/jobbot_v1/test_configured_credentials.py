"""Ordinary harness shells resolve explicit private references, never discover secrets."""
import json
from pathlib import Path
import pytest
from job_applier.managed_cli import credential
from job_applier.managed_shared import ProtocolError


def configured(tmp_path):
    store=tmp_path/'private-auth.json'
    store.write_text(json.dumps({'worker':'synthetic-worker-secret','operator':'synthetic-operator-secret'}))
    return {'credential_files':{'TEST_WORKER':{'path':str(store),'key':'worker'}}}


def test_envless_shell_resolves_only_explicit_named_file(tmp_path,monkeypatch):
    monkeypatch.delenv('TEST_WORKER',raising=False)
    assert credential('TEST_WORKER',configured(tmp_path))=='synthetic-worker-secret'


def test_launcher_environment_keeps_precedence(tmp_path,monkeypatch):
    monkeypatch.setenv('TEST_WORKER','synthetic-env-secret')
    assert credential('TEST_WORKER',configured(tmp_path))=='synthetic-env-secret'


@pytest.mark.parametrize('reference',[{}, {'path':'relative.json','key':'worker'}, {'path':'/missing/auth.json','key':'worker'}])
def test_missing_or_invalid_reference_fails_closed(reference,monkeypatch):
    monkeypatch.delenv('TEST_WORKER',raising=False)
    with pytest.raises(ProtocolError,match='credential_unavailable'):
        credential('TEST_WORKER',{'credential_files':{'TEST_WORKER':reference}})


def test_unconfigured_name_does_not_borrow_operator_token(tmp_path,monkeypatch):
    monkeypatch.delenv('OTHER_WORKER',raising=False)
    with pytest.raises(ProtocolError,match='credential_unavailable'):
        credential('OTHER_WORKER',configured(tmp_path))


def test_invalid_secret_value_is_not_reported(tmp_path,monkeypatch,capsys):
    monkeypatch.delenv('TEST_WORKER',raising=False)
    cfg=configured(tmp_path)
    Path(cfg['credential_files']['TEST_WORKER']['path']).write_text('{"worker":{"secret":"synthetic-do-not-print"}}')
    with pytest.raises(ProtocolError,match='credential_unavailable'):
        credential('TEST_WORKER',cfg)
    assert 'synthetic-do-not-print' not in capsys.readouterr().out


def test_doctor_recognizes_configured_token_without_environment(tmp_path,monkeypatch):
    import sqlite3
    from job_applier.application_runtime import inspect_runtime
    monkeypatch.delenv('TEST_WORKER',raising=False)
    db=tmp_path/'managed.db'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE instance(id TEXT)');con.execute("INSERT INTO instance VALUES('fixture')")
    cfg=dict(configured(tmp_path),worker_token_env='TEST_WORKER',db_path=str(db),instance_id='fixture',cdp_url='http://127.0.0.1:9223')
    p=tmp_path/'config.json';p.write_text(json.dumps(cfg))
    result=inspect_runtime(str(p))
    assert result['worker_token_available'] is True
    assert 'synthetic-worker-secret' not in json.dumps(result)


def test_portable_advance_uses_file_reference_without_launching_agent(tmp_path,monkeypatch,capsys):
    from job_applier import workday_fast,application_runtime,managed_client
    monkeypatch.delenv('TEST_WORKER',raising=False)
    cfg=dict(configured(tmp_path),worker_token_env='TEST_WORKER',worker_id='fixture',base_url='http://127.0.0.1:9999',instance_id='fixture')
    p=tmp_path/'config.json';p.write_text(json.dumps(cfg))
    class Client:
        def __init__(self,url,instance,token):assert token=='synthetic-worker-secret'
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(managed_client,'Client',Client)
    monkeypatch.setattr(application_runtime,'inspect_runtime',lambda *a:{})
    monkeypatch.setattr(workday_fast,'advance',lambda *a:{'status':'fixture_only'})
    assert workday_fast.main(['advance','--config',str(p),'--attempt-id','1','--fence','1','--target-id','fixture-tab'])==0
    output=capsys.readouterr().out
    assert 'fixture_only' in output and 'synthetic-worker-secret' not in output
