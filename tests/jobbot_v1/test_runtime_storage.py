"""Synthetic storage only: never point maintenance tests at a real home/profile."""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'maintain_runtime_storage.py'
spec = importlib.util.spec_from_file_location('runtime_storage', SCRIPT)
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)
NOW = 2_000_000_000
DAY = 86400


def put(path, data=b'payload', age=10):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (NOW-age*DAY, NOW-age*DAY))
    return path


@pytest.fixture
def site(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    spool = home / '.local/share/jobbot/private-spool'
    spool.mkdir(parents=True)
    db = put(home / '.local/share/jobbot/managed.db', b'important history')
    proc = tmp_path / 'proc'
    proc.mkdir()
    return home, spool, db, proc


def run(site, **kwargs):
    home, spool, db, proc = site
    return storage.maintain(home, spool, db, proc_root=proc, now=NOW, **kwargs)


def test_dry_run_keeps_cache_and_live_history(site):
    home, _, db, _ = site
    cache = put(home / '.cache/pip/http-v2/old', age=10)
    profile = put(home / '.config/BraveSoftware/Brave-Browser/Default/Cookies')
    history = put(home / '.hermes/state.db', b'conversation history')
    result = run(site)
    assert result['eligible_cache_files'] == 1
    assert cache.exists() and profile.exists() and history.exists()
    assert db.read_bytes() == b'important history'


def test_only_allowlisted_cache_is_pruned(site):
    home, spool, _, _ = site
    old = put(home / '.cache/pip/http-v2/old', age=10)
    recent = put(home / '.cache/pip/http-v2/recent', age=1)
    evidence = put(spool / 'screenshots/old.png', age=200)
    output = put(home / '.hermes/cache/terminal-output/old.txt', age=200)
    release = put(home / '.hermes/hermes-agent/apps/desktop/release/linux-unpacked/Hermes', age=200)
    run(site, apply=True)
    assert not old.exists()
    assert all(p.exists() for p in (recent, evidence, output, release))


def test_cache_cap_evicts_oldest_even_when_recent(site, monkeypatch):
    home, _, _, _ = site
    monkeypatch.setattr(storage, 'CACHE_RULES', (('.cache/pip', 7, 8, 'downloads'),))
    older = put(home / '.cache/pip/older', b'123456', age=2)
    newer = put(home / '.cache/pip/newer', b'123456', age=1)
    run(site, apply=True)
    assert not older.exists() and newer.exists()


def fake_process(proc, command, pid='12345'):
    folder = proc / pid
    folder.mkdir()
    (folder/'cmdline').write_bytes(command)
    (folder/'status').write_text('State:\tS (sleeping)\n')
    return folder


def test_active_download_tool_retains_caches(site):
    home, _, _, proc = site
    old = put(home / '.cache/pip/old', age=20)
    fake_process(proc, b'/usr/bin/python\0-m\0pip\0install\0package\0')
    run(site, apply=True)
    assert old.exists()


def test_live_browser_retains_browser_cache(site):
    home, _, _, proc = site
    old = put(home / '.cache/BraveSoftware/Brave-Browser/Default/Cache/data', age=20)
    fake_process(proc, b'/opt/brave.com/brave/brave\0--profile-directory=Default\0')
    run(site, apply=True)
    assert old.exists()


def test_referenced_backup_is_retained(site):
    _, spool, _, proc = site
    backup = put(spool / 'deployments/old/managed-before.db', b'backup'*100)
    fake_process(proc, b'/usr/bin/restore\0'+os.fsencode(backup)+b'\0')
    run(site, apply=True)
    assert backup.exists() and not backup.with_name(backup.name+'.gz').exists()


def test_backup_compression_is_verified_and_idempotent(site):
    _, spool, db, _ = site
    backup = put(spool / 'deployments/old/managed-before.db', b'backup history'*1000)
    original = backup.read_bytes()
    result = run(site, apply=True)
    archive = backup.with_name(backup.name+'.gz')
    assert len(result['compressed']) == 1 and not backup.exists()
    assert gzip.decompress(archive.read_bytes()) == original
    metadata = json.loads(archive.with_name(archive.name+'.storage.json').read_text())
    assert metadata['source_sha256'] == hashlib.sha256(original).hexdigest()
    assert db.read_bytes() == b'important history'
    assert not run(site, apply=True)['compressed']


@pytest.mark.parametrize('sidecar', ['-wal', '-shm', '-journal'])
def test_sqlite_sidecar_prevents_compression(site, sidecar):
    _, spool, _, _ = site
    backup = put(spool / 'deployments/old/managed-before.db', b'backup'*100)
    put(backup.with_name(backup.name+sidecar))
    run(site, apply=True)
    assert backup.exists()


def test_recent_backup_and_unknown_database_are_retained(site):
    _, spool, _, _ = site
    recent = put(spool / 'deployments/recent/managed-before.db', b'x'*1000, age=1)
    unknown = put(spool / 'deployments/unknown/production.db', b'x'*1000, age=100)
    run(site, apply=True)
    assert recent.exists() and unknown.exists()


def test_conflicting_archive_never_overwritten(site):
    _, spool, _, _ = site
    backup = put(spool / 'deployments/old/managed-before.db', b'x'*1000)
    archive = put(backup.with_name(backup.name+'.gz'), b'existing archive')
    run(site, apply=True)
    assert backup.exists() and archive.read_bytes() == b'existing archive'


def test_expiry_keeps_three_newest_and_never_prunes_unregistered_archive(site):
    _, spool, _, _ = site
    originals = [put(spool / f'deployments/{i}/managed-before.db', bytes([i])*1000, age=40+i) for i in range(5)]
    unregistered = put(spool / 'deployments/unknown/before.db.gz', b'keep', age=100)
    run(site, apply=True)
    run(site, apply=True)
    assert [p.with_name(p.name+'.gz').exists() for p in originals] == [True, True, True, False, False]
    assert unregistered.exists()


def test_modified_archive_is_not_expired(site):
    _, spool, _, _ = site
    originals = [put(spool / f'deployments/{i}/managed-before.db', b'x'*1000, age=40+i) for i in range(4)]
    run(site, apply=True)
    archive = originals[-1].with_name(originals[-1].name+'.gz')
    # First pass compresses; expiration applies to pre-existing verified archives.
    assert archive.exists()
    archive.write_bytes(b'do not delete a modified archive')
    run(site, apply=True)
    assert archive.exists()


def test_interrupted_compression_pair_does_not_count_as_two_retained_backups(site):
    _, spool, _, _ = site
    originals = [put(spool / f'deployments/{i}/managed-before.db', b'x'*1000, age=40+i) for i in range(4)]
    run(site, apply=True)
    # A crash after publishing the archive can leave its raw source too.
    put(originals[0], b'x'*1000, age=40)
    run(site, apply=True)
    assert [p.with_name(p.name+'.gz').exists() for p in originals] == [True, True, True, False]


def test_symlinked_cache_root_is_not_followed(site, tmp_path):
    home, _, _, _ = site
    external = put(tmp_path / 'outside/data', age=100)
    root = home / '.cache/pip'
    root.parent.mkdir(parents=True)
    try: root.symlink_to(external.parent, target_is_directory=True)
    except OSError: pytest.skip('symlinks unavailable')
    run(site, apply=True)
    assert external.exists()


def test_verification_failure_preserves_original(site, monkeypatch):
    _, spool, _, _ = site
    backup = put(spool / 'deployments/old/managed-before.db', b'x'*1000)
    monkeypatch.setattr(storage, 'verify_gzip', lambda *args: False)
    result = run(site, apply=True)
    assert backup.exists() and result['errors']
    assert not backup.with_name(backup.name+'.gz').exists()
