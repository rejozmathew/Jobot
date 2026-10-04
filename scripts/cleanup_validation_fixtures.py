"""Remove registered, completed synthetic fixtures; retain reports and live data.

This maintenance command is separate from application execution. It never scans
browser profiles, databases, the private spool, or arbitrary cache directories.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time


FIXTURE_NAME = re.compile(
    r'j(?:[0-9]+c?[bt](?:-[a-z0-9_]+)?|w-[a-z0-9_]+|v[bt]-[a-z0-9_]+|'
    r'b[ad]-(?:base|tmp)-(?:20260927|0927a))'
)


def process_references(targets, proc_root, uid):
    references = set()
    unreadable_commands = []
    partial_metadata = []
    for proc in proc_root.iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            if proc.stat().st_uid != uid:
                continue
            status = (proc / 'status').read_text()
            if re.search(r'^State:\s+Z\b', status, re.M):
                continue
            command = (proc / 'cmdline').read_bytes()
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            unreadable_commands.append(int(proc.name))
            continue
        parts = [command]
        hidden = []
        for field in ('environ', 'maps'):
            try:
                parts.append((proc / field).read_bytes())
            except (FileNotFoundError, ProcessLookupError):
                pass
            except PermissionError:
                hidden.append(field)
        for field in ('cwd', 'root'):
            try:
                parts.append(os.readlink(proc / field).encode())
            except (FileNotFoundError, ProcessLookupError):
                pass
            except PermissionError:
                hidden.append(field)
        try:
            for fd in (proc / 'fd').iterdir():
                try:
                    parts.append(os.readlink(fd).encode())
                except (FileNotFoundError, ProcessLookupError):
                    pass
                except PermissionError:
                    hidden.append('fd')
        except (FileNotFoundError, ProcessLookupError):
            pass
        except PermissionError:
            hidden.append('fd')
        if hidden:
            partial_metadata.append({'pid': int(proc.name), 'fields': sorted(set(hidden))})
            # Chromium sandboxes and system daemons commonly protect these
            # fields. Keep the readable command and other evidence; a protected
            # optional field does not mean an unrelated completed test is live.
        joined = b'\0'.join(parts)
        references.update(path for path in targets if str(path).encode() in joined)
    return references, unreadable_commands, partial_metadata


def identity(path):
    info = path.lstat()
    return {'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid}


def cleanup(records_dir, cache_root, *, apply=False, now=None, min_age_hours=24,
            proc_root=Path('/proc'), uid=None):
    records_dir = Path(records_dir).resolve()
    cache_root = Path(cache_root).resolve()
    proc_root = Path(proc_root)
    uid = cache_root.stat().st_uid if uid is None else uid
    now = time.time() if now is None else now
    result = {'eligible': [], 'removed': [], 'retained': [], 'invalid_records': []}
    candidates = {}
    for manifest in sorted(records_dir.glob('*-fixtures.json')):
        try:
            if manifest.is_symlink() or manifest.stat().st_uid != uid:
                raise ValueError('record_ownership')
            record = json.loads(manifest.read_text())
            if record.get('phase') != 'completed' or not isinstance(record.get('pytest_exit'), int):
                raise ValueError('validation_not_completed')
            default_report = manifest.with_name(manifest.name.removesuffix('-fixtures.json') + '.xml')
            report = Path(record.get('report_path', default_report))
            if report.parent != records_dir or report.suffix != '.xml' or report.is_symlink():
                raise ValueError('report_outside_records')
            if hashlib.sha256(report.read_bytes()).hexdigest() != record.get('report_sha256'):
                raise ValueError('report_changed')
            directories = record['directories']
            if not isinstance(directories, dict):
                raise ValueError('invalid_directories')
            for value, expected in directories.items():
                target = Path(value)
                if target.parent != cache_root or not FIXTURE_NAME.fullmatch(target.name):
                    result['retained'].append({'path': value, 'reason': 'outside_fixture_scope'})
                    continue
                try:
                    info = target.lstat()
                except FileNotFoundError:
                    continue
                if (not stat.S_ISDIR(info.st_mode) or target.resolve() != target
                        or info.st_uid != uid or identity(target) != expected):
                    result['retained'].append({'path': value, 'reason': 'ownership_changed'})
                    continue
                if now - max(info.st_mtime, manifest.stat().st_mtime) < min_age_hours * 3600:
                    result['retained'].append({'path': value, 'reason': 'recent_fixture'})
                    continue
                candidates[target] = expected
        except (OSError, ValueError, KeyError, TypeError) as exc:
            result['invalid_records'].append({'record': str(manifest), 'reason': str(exc)})
    references, unreadable, partial = process_references(candidates, proc_root, uid)
    result.update(unreadable_commands=unreadable, partial_metadata=partial)
    for target, expected in candidates.items():
        if target in references or unreadable:
            result['retained'].append({'path': str(target), 'reason':
                                      'process_reference' if target in references else 'unreadable_command'})
            continue
        # Recheck identity immediately before removing the registered root.
        if target.is_symlink() or identity(target) != expected:
            result['retained'].append({'path': str(target), 'reason': 'ownership_changed'})
            continue
        result['eligible'].append(str(target))
        if apply:
            shutil.rmtree(target)
            result['removed'].append(str(target))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records-dir', required=True, type=Path)
    parser.add_argument('--cache-root', type=Path, default=Path.home() / '.cache')
    parser.add_argument('--min-age-hours', type=float, default=24)
    parser.add_argument('--apply', action='store_true', help='Otherwise only report eligible directories')
    args = parser.parse_args()
    if args.min_age_hours < 0:
        parser.error('--min-age-hours must be nonnegative')
    result = cleanup(args.records_dir, args.cache_root, apply=args.apply,
                     min_age_hours=args.min_age_hours)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
