import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.cleanup_validation_fixtures import cleanup


def fixture_record(tmp_path):
    cache = tmp_path / 'cache'
    cache.mkdir()
    target = cache / 'j8b-synthetic'
    target.mkdir()
    (target / 'browser-profile').mkdir()
    records = tmp_path / 'records'
    records.mkdir()
    report = records / 'validation.xml'
    report.write_text('<testsuite tests="1" failures="0"/>')
    st = target.stat()
    record = {
        'phase': 'completed', 'pytest_exit': 0,
        'report_path': str(report),
        'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(),
        'directories': {str(target): {'device': st.st_dev, 'inode': st.st_ino, 'uid': st.st_uid}},
    }
    manifest = records / 'validation-fixtures.json'
    manifest.write_text(json.dumps(record))
    proc = tmp_path / 'proc'
    proc.mkdir()
    return cache, target, records, manifest, record, proc


def process(proc, command=b'/usr/lib/systemd/systemd\0--user\0', state='S'):
    pid = proc / '999999'
    pid.mkdir()
    (pid / 'status').write_text(f'State:\t{state}\n')
    (pid / 'cmdline').write_bytes(command)
    (pid / 'environ').write_bytes(b'')
    (pid / 'maps').write_bytes(b'')
    (pid / 'fd').mkdir()
    return pid


def run(data, **kwargs):
    cache, target, records, _, _, proc = data
    return cleanup(records, cache, proc_root=proc, uid=target.stat().st_uid,
                   min_age_hours=0, **kwargs)


def test_hidden_optional_metadata_of_unrelated_process_does_not_leak_fixtures(tmp_path, monkeypatch):
    data = fixture_record(tmp_path)
    pid = process(data[-1])
    original = Path.read_bytes

    def protected(path):
        if path.parent == pid and path.name in ('environ', 'maps'):
            raise PermissionError('protected unrelated process')
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', protected)
    result = run(data, apply=True)
    assert result['removed'] == [str(data[1])]
    assert not data[1].exists()
    assert data[3].exists() and (data[2] / 'validation.xml').exists()


@pytest.mark.parametrize('source', ['cmdline', 'environ', 'maps', 'cwd', 'fd'])
def test_referenced_fixture_is_preserved(tmp_path, source):
    data = fixture_record(tmp_path)
    pid = process(data[-1])
    target = data[1]
    if source in ('cwd', 'fd'):
        link = pid / 'cwd' if source == 'cwd' else pid / 'fd' / '3'
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip('symlink privilege unavailable')
    else:
        (pid / source).write_bytes(str(target).encode())
    result = run(data, apply=True)
    assert not result['removed']
    assert result['retained'][0]['reason'] == 'process_reference'
    assert target.exists()


@pytest.mark.parametrize('change', ['running', 'report', 'identity', 'outside', 'recent'])
def test_unverified_or_recent_fixture_is_preserved(tmp_path, change):
    data = fixture_record(tmp_path)
    cache, target, records, manifest, record, proc = data
    kwargs = {}
    if change == 'running':
        record['phase'] = 'running'
    elif change == 'report':
        record['report_sha256'] = 'wrong'
    elif change == 'identity':
        record['directories'][str(target)]['inode'] += 1
    elif change == 'outside':
        outside = tmp_path / 'personal-browser'
        outside.mkdir()
        record['directories'] = {str(outside): record['directories'][str(target)]}
    else:
        kwargs['now'] = target.stat().st_mtime - 1
    manifest.write_text(json.dumps(record))
    result = run(data, apply=True, **kwargs)
    assert not result['removed']
    assert target.exists()


def test_unreadable_command_preserves_fixtures(tmp_path, monkeypatch):
    data = fixture_record(tmp_path)
    pid = process(data[-1])
    original = Path.read_bytes

    def protected(path):
        if path == pid / 'cmdline':
            raise PermissionError('unknown live process')
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', protected)
    result = run(data, apply=True)
    assert not result['removed'] and data[1].exists()
    assert result['unreadable_commands'] == [999999]


def test_zombies_and_dry_run(tmp_path):
    data = fixture_record(tmp_path)
    process(data[-1], command=str(data[1]).encode(), state='Z')
    result = run(data)
    assert result['eligible'] == [str(data[1])]
    assert not result['removed'] and data[1].exists()
    assert run(data, apply=True)['removed'] == [str(data[1])]


def test_symlink_fixture_is_preserved(tmp_path):
    data = fixture_record(tmp_path)
    target = data[1]
    target.rename(target.with_name('personal-browser'))
    try:
        target.symlink_to(target.with_name('personal-browser'), target_is_directory=True)
    except OSError:
        pytest.skip('symlink privilege unavailable')
    assert not run(data, apply=True)['removed']
    assert target.with_name('personal-browser').exists()
