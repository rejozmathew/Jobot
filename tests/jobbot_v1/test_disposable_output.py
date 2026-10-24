"""Synthetic disposable output: no production records or browser dependencies."""
import datetime
import sqlite3

import pytest
from test_runtime_storage import NOW, DAY, put, site, fake_process, storage, SCRIPT


def prepare(site):
    home, spool, db, proc = site
    db.unlink()
    with sqlite3.connect(db) as c:
        c.execute('create table discovery_runs(id text, ended_at text)')
        c.execute('create table application_sessions(requested_at text, ended_at text)')
        c.executemany('insert into discovery_runs values (?,?)', [('done', 'ended'), ('live', None)])
    return home, spool, db, proc


def cleanup(site, **kwargs):
    home, spool, db, proc = site
    return storage.dispose_completed_output(home, spool, db, proc_root=proc, now=NOW, **kwargs)


def test_completed_scratch_removed_records_and_live_recovery_preserved(site):
    home, spool, db, proc = prepare(site)
    scratch = put(spool/'harvest/done/history.json', age=0)
    archive = put(spool/'harvest/done/old.json.gz')
    records = put(spool/'harvest/done/records.json')
    checkpoint = put(spool/'harvest/done/checkpoint.json')
    live = put(spool/'harvest/live/bulk.json')
    unknown = put(spool/'harvest/unregistered/bulk.json')
    cache = put(home/'.hermes/profiles/jobbot-discovery/cache/scratch/bulk.json')
    recent = put(home/'.hermes/cache/exec/current.txt', age=0)
    history = put(home/'.hermes/state.db')
    before = db.read_bytes()
    preview = cleanup(site)
    assert preview['eligible_files'] == 3 and scratch.exists()
    result = cleanup(site, apply=True)
    assert result['removed_files'] == 3
    assert not scratch.exists() and not archive.exists() and not cache.exists()
    assert all(p.exists() for p in (records, checkpoint, live, unknown, recent, history))
    assert db.read_bytes() == before


def test_active_application_screenshots_and_process_referenced_output_survive(site):
    home, spool, db, proc = prepare(site)
    start = datetime.datetime.fromtimestamp(NOW-3*DAY, datetime.timezone.utc).isoformat()
    with sqlite3.connect(db) as c:
        c.execute('insert into application_sessions values (?,NULL)', (start,))
    active = put(spool/'screenshots/recovery.png', age=2)
    old = put(spool/'screenshots/finished.png', age=4)
    scratch = put(spool/'harvest/done/still-open.json')
    fake_process(proc, (str(scratch)+'\0').encode())
    cleanup(site, apply=True)
    assert active.exists() and scratch.exists() and not old.exists()


def test_outside_run_id_and_symlinks_cannot_expand_deletion_scope(site):
    home, spool, db, proc = prepare(site)
    outside = put(spool/'outside/private.json')
    with sqlite3.connect(db) as c:
        c.execute('insert into discovery_runs values (?,?)', ('../outside', 'ended'))
    cleanup(site, apply=True)
    assert outside.exists()


def test_unreadable_processes_defer_deletion(site, monkeypatch):
    home, spool, db, proc = prepare(site)
    scratch = put(spool/'harvest/done/bulk.json')
    monkeypatch.setattr(storage, 'process_references', lambda *a: (set(), [123], []))
    result = cleanup(site, apply=True)
    assert scratch.exists() and result['removed_files'] == 0


@pytest.mark.skipif(__import__('os').name != 'posix', reason='Linux maintenance entry point')
@pytest.mark.parametrize('discovery_busy', [False, True])
def test_cli_runs_with_only_stdlib_and_preserves_active_discovery(site, discovery_busy):
    import fcntl
    import json
    import os
    import subprocess
    import sys
    home, spool, db, proc = prepare(site)
    scratch = put(spool/'harvest/done/bulk.json')
    config = home/'runtime.json'
    config.write_text(json.dumps({'spool_dir':str(spool),'db_path':str(db)}))
    environment = dict(os.environ, HOME=str(home), PYTHONPATH='')
    with open(str(db)+'.harvest.lock', 'a') as lock:
        if discovery_busy:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run([sys.executable, '-S', str(SCRIPT),
                                 '--runtime-config', str(config), '--apply', '--dispose-completed-output'],
                                capture_output=True, text=True, env=environment, timeout=20)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert (home/'.local/state/jobbot-storage/latest.json').is_file()
    assert not output['errors']
    if discovery_busy:
        assert output['disposable_output']['retained'] == [{'reason':'discovery_running'}]
        assert scratch.exists()
    else:
        assert output['disposable_output']['removed_files'] == 1
        assert not scratch.exists()
