"""Bound disposable caches and verified backup copies, without pruning live history.

Dry-run by default. Linux user maintenance; no browser, worker or service restart.
Only the fixed cache paths and explicitly named backup copies below are eligible.
"""
import argparse
from datetime import datetime
import fnmatch
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import time

try:
    from cleanup_validation_fixtures import process_references
except ModuleNotFoundError:
    from scripts.cleanup_validation_fixtures import process_references


MiB = 1024**2
DAY = 86400
CACHE_RULES = (
    ('.cache/pip', 7, 64*MiB, 'downloads'),
    ('.cache/electron', 7, 64*MiB, 'downloads'),
    ('.cache/node-gyp', 14, 64*MiB, 'downloads'),
    ('.npm/_cacache', 7, 64*MiB, 'downloads'),
    ('.hermes/hermes-agent/.cache/desktop-inputs', 7, 128*MiB, 'build'),
    ('.hermes/hermes-agent/apps/desktop/build/packager', 7, 128*MiB, 'build'),
    ('.hermes/hermes-agent/apps/desktop/build/prepared-packaging-tools', 7, 64*MiB, 'build'),
    ('.cache/BraveSoftware/Brave-Browser', 7, 256*MiB, 'browser'),
)
BACKUP_NAMES = {'managed-before.db', 'ledger-before.sqlite3', 'before.db'}
ARCHIVE_VERSION = 1


def fingerprint(path):
    s = path.lstat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)


def regular_owned(path, uid):
    try:
        s = path.lstat()
        return stat.S_ISREG(s.st_mode) and s.st_uid == uid and path.resolve() == path
    except OSError:
        return False


def files_under(root, uid):
    """Never follow a symlink, including any component above the scan root."""
    if not root.is_dir() or root.resolve() != root or root.stat().st_uid != uid:
        return
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        dirs[:] = [n for n in dirs if not (parent/n).is_symlink()]
        for name in files:
            path = parent/name
            if regular_owned(path, uid):
                yield path


def backup_candidates(home, spool, db_path, uid):
    found = []
    for path in files_under(spool/'deployments', uid):
        base = path.name.removesuffix('.gz')
        if base in BACKUP_NAMES and path != db_path:
            found.append((path, 'jobbot_deployments'))
    for root, pattern, group in (
        (db_path.parent, db_path.name+'.before-local-*.db', 'jobbot_local'),
        (home/'.hermes', 'state.db.pre-update-*.bak', 'hermes_main'),
        (home/'.hermes/profiles/jobbot-discovery', 'state.db.pre-update-*.bak', 'hermes_discovery'),
    ):
        if not root.is_dir() or root.resolve() != root:
            continue
        for path in root.iterdir():
            if regular_owned(path, uid) and fnmatch.fnmatchcase(path.name.removesuffix('.gz'), pattern):
                found.append((path, group))
    return found


def activity(proc_root, uid):
    """Additional guards for cache consumers whose args need not name a cache."""
    browsers = builders = False
    for proc in proc_root.iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            if proc.stat().st_uid != uid:
                continue
            args = (proc/'cmdline').read_bytes().decode(errors='replace').split('\0')
            if not args or not args[0]:
                continue
            command = Path(args[0]).name.lower()
            browsers |= any(n in command for n in ('brave', 'chromium', 'chrome', 'firefox'))
            builders |= command in {'npm', 'npx', 'pnpm', 'yarn', 'pip', 'pip3', 'uv', 'gcc', 'g++', 'make', 'ninja'}
            builders |= '-m' in args and any(n in args for n in ('pip', 'build'))
            builders |= any('npm-cli.js' in a or 'electron-builder' in a or 'node-gyp' in a for a in args)
        except FileNotFoundError:
            continue
        except PermissionError:
            # The shared reference scanner also defers mutations on an unreadable command.
            builders = browsers = True
    return browsers, builders


def digest_stream(stream):
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(MiB), b''):
        h.update(chunk)
    return h.hexdigest()


def digest_file(path):
    with path.open('rb') as stream:
        return digest_stream(stream)


def verify_gzip(path, expected):
    with gzip.open(path, 'rb') as stream:
        return digest_stream(stream) == expected


def sync_directory(path):
    if os.name == 'posix':
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def compress_backup(path, group, uid):
    """Publish a verified archive and receipt before removing the original copy."""
    before = fingerprint(path)
    archive = path.with_name(path.name+'.gz')
    receipt = archive.with_name(archive.name+'.storage.json')
    if archive.exists() or archive.is_symlink() or receipt.exists() or receipt.is_symlink():
        raise ValueError('archive_already_exists')
    if path.stat().st_nlink != 1:
        raise ValueError('linked_backup')
    if shutil.disk_usage(path.parent).free < before[2]*1.02 + 128*MiB:
        raise ValueError('insufficient_compression_headroom')
    fd, temporary = tempfile.mkstemp(prefix='.storage-', suffix='.tmp', dir=path.parent)
    temp = Path(temporary)
    receipt_fd = receipt_temp = None
    try:
        h = hashlib.sha256()
        with os.fdopen(fd, 'wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', compresslevel=6, fileobj=raw, mtime=0) as output:
                with path.open('rb') as source:
                    for chunk in iter(lambda: source.read(MiB), b''):
                        h.update(chunk)
                        output.write(chunk)
            raw.flush()
            os.fsync(raw.fileno())
        if not verify_gzip(temp, h.hexdigest()):
            raise ValueError('archive_verification_failed')
        if not regular_owned(path, uid) or fingerprint(path) != before:
            raise ValueError('source_changed')
        record = {'version': ARCHIVE_VERSION, 'group': group, 'source_name': path.name,
                  'source_size': before[2], 'source_mtime_ns': before[3],
                  'source_sha256': h.hexdigest(), 'archive_sha256': digest_file(temp)}
        receipt_fd, receipt_name = tempfile.mkstemp(prefix='.storage-', suffix='.json.tmp', dir=path.parent)
        receipt_temp = Path(receipt_name)
        with os.fdopen(receipt_fd, 'w') as output:
            receipt_fd = None
            json.dump(record, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.utime(temp, ns=(before[3], before[3]))
        # link() is exclusive: never replace an existing archive/receipt.
        os.link(temp, archive)
        os.link(receipt_temp, receipt)
        sync_directory(path.parent)
        if not regular_owned(path, uid) or fingerprint(path) != before:
            raise ValueError('source_changed_before_unlink')
        path.unlink()
        sync_directory(path.parent)
        return {'path': str(path), 'archive': str(archive), 'bytes_saved': before[2]-archive.stat().st_size}
    finally:
        if receipt_fd is not None:
            os.close(receipt_fd)
        temp.unlink(missing_ok=True)
        if receipt_temp is not None:
            receipt_temp.unlink(missing_ok=True)


def registered_archive(path, group, uid):
    receipt = path.with_name(path.name+'.storage.json')
    if not regular_owned(receipt, uid):
        return None
    try:
        record = json.loads(receipt.read_text())
        if (record.get('version') != ARCHIVE_VERSION or record.get('group') != group
                or record.get('source_name') != path.name.removesuffix('.gz')
                or type(record.get('source_mtime_ns')) is not int):
            return None
        return record
    except (OSError, ValueError):
        return None


def maintain(home, spool, db_path, *, apply=False, proc_root=Path('/proc'), now=None):
    home, spool, db_path, proc_root = map(lambda p: Path(p).absolute(), (home, spool, db_path, proc_root))
    if home.resolve() != home or spool.resolve() != spool or db_path.resolve() != db_path:
        raise ValueError('symlinked_runtime_path')
    if not spool.is_relative_to(home) or not db_path.is_relative_to(home) or spool == home:
        raise ValueError('runtime_outside_home')
    uid = home.stat().st_uid
    now = time.time() if now is None else now
    result = {'dry_run': not apply, 'eligible_cache_files': 0, 'cache_bytes_removed': 0,
              'compressed': [], 'eligible_backups': [], 'expired': [], 'retained': [], 'errors': []}
    backups = backup_candidates(home, spool, db_path, uid)
    roots = [home/rel for rel, *_ in CACHE_RULES]
    targets = roots + [p for p, _ in backups]
    references, unreadable, _ = process_references(targets, proc_root, uid)
    if unreadable:
        result['retained'].append({'reason': 'unreadable_process_commands', 'count': len(unreadable)})
        return result
    browsers, builders = activity(proc_root, uid)
    for (rel, days, cap, kind), root in zip(CACHE_RULES, roots):
        if any(root == p or root.is_relative_to(p) or p.is_relative_to(root) for p in (spool, db_path)):
            result['retained'].append({'path': str(root), 'reason': 'overlaps_live_storage'})
            continue
        if root in references or builders or (kind == 'browser' and browsers):
            result['retained'].append({'path': str(root), 'reason': 'active_cache_consumer'})
            continue
        entries = sorted(((p, fingerprint(p)) for p in files_under(root, uid)), key=lambda row: row[1][3])
        total = sum(s[2] for _, s in entries)
        for path, saved in entries:
            if now-saved[3]/1e9 < days*DAY and total <= cap:
                continue
            result['eligible_cache_files'] += 1
            total -= saved[2]
            if apply:
                try:
                    if regular_owned(path, uid) and fingerprint(path) == saved:
                        path.unlink()
                        result['cache_bytes_removed'] += saved[2]
                except OSError as exc:
                    result['errors'].append({'path': str(path), 'reason': str(exc)})
    # Retention uses original snapshot age, never the compression date.
    ages = {}
    for path, group in backups:
        record = registered_archive(path, group, uid) if path.suffix == '.gz' else None
        if path.suffix == '.gz' and (not record or digest_file(path) != record.get('archive_sha256')):
            continue
        age = record['source_mtime_ns']/1e9 if record else path.stat().st_mtime
        original = path.with_name(path.name.removesuffix('.gz'))
        # A crash can leave both forms; they are one snapshot, not two backups.
        group_ages = ages.setdefault(group, {})
        group_ages[original] = max(group_ages.get(original, 0), age)
    protected = {path for entries in ages.values()
                 for path in sorted(entries, key=lambda p: (entries[p], str(p)), reverse=True)[:3]}
    for path, group in backups:
        try:
            if path in references:
                result['retained'].append({'path': str(path), 'reason': 'process_reference'})
                continue
            if path.suffix == '.gz':
                record = registered_archive(path, group, uid)
                original = path.with_name(path.name.removesuffix('.gz'))
                if not record or original in protected or now-record['source_mtime_ns']/1e9 < 30*DAY:
                    continue
                saved = fingerprint(path)
                if digest_file(path) != record['archive_sha256']:
                    result['retained'].append({'path': str(path), 'reason': 'archive_changed'})
                    continue
                if apply and regular_owned(path, uid) and fingerprint(path) == saved:
                    path.unlink()
                    path.with_name(path.name+'.storage.json').unlink()
                result['expired'].append(str(path))
            else:
                if now-path.stat().st_mtime < 2*DAY:
                    continue
                if any(path.with_name(path.name+s).exists() for s in ('-wal', '-shm', '-journal')):
                    result['retained'].append({'path': str(path), 'reason': 'sqlite_sidecar'})
                    continue
                if path.with_name(path.name+'.gz').exists():
                    result['retained'].append({'path': str(path), 'reason': 'archive_already_exists'})
                    continue
                result['eligible_backups'].append(str(path))
                if apply:
                    result['compressed'].append(compress_backup(path, group, uid))
        except (OSError, ValueError, KeyError) as exc:
            result['errors'].append({'path': str(path), 'reason': str(exc)})
    return result


def dispose_completed_output(home, spool, db_path, *, apply=False,
                             proc_root=Path('/proc'), now=None):
    """Opt-in removal of disposable output, never application/account records.

    Caller holds the discovery lock so a subsequent run cannot read a prior
    checkpoint while maintenance is scanning. Checkpoints and final intake
    records remain available; only terminal runs' scratch output is disposable.
    """
    home, spool, db_path = (Path(p).absolute() for p in (home, spool, db_path))
    if (any(p.resolve() != p for p in (home, spool, db_path))
            or not spool.is_relative_to(home) or spool == home
            or not db_path.is_relative_to(home)):
        raise ValueError('invalid_runtime_storage_path')
    uid = home.stat().st_uid
    now = time.time() if now is None else now
    result = {'eligible_files': 0, 'removed_files': 0, 'removed_bytes': 0,
              'retained': [], 'errors': []}
    with sqlite3.connect(db_path.as_uri()+'?mode=ro', uri=True) as db:
        runs = db.execute('SELECT id FROM discovery_runs WHERE ended_at IS NOT NULL').fetchall()
        starts = db.execute('SELECT requested_at FROM application_sessions WHERE ended_at IS NULL').fetchall()
    cutoff = now-DAY
    for (started,) in starts:
        # An unparsable active timestamp aborts this sweep, never guesses safety.
        cutoff = min(cutoff, datetime.fromisoformat(started).timestamp())
    roots = []
    for (run_id,) in runs:
        root = spool/'harvest'/run_id
        if root.parent == spool/'harvest' and root.resolve() == root:
            roots.append((root, 'discovery'))
    roots.append((spool/'screenshots', 'screenshots'))
    for profile in (home/'.hermes', home/'.hermes/profiles/jobbot-discovery'):
        for name in ('scratch', 'terminal-output', 'exec', 'web', 'browser-use',
                     'screenshots', 'spillover', 'delegation'):
            roots.append((profile/'cache'/name, 'hermes_cache'))
    references, unreadable, _ = process_references([p for p, _ in roots], Path(proc_root), uid)
    if unreadable:
        result['retained'].append({'reason': 'unreadable_process_commands'})
        return result
    for root, kind in roots:
        if root in references:
            result['retained'].append({'path': str(root), 'reason': 'process_reference'})
            continue
        for path in files_under(root, uid):
            if (kind == 'discovery' and path.parent == root and path.name in
                    {'records.json', 'checkpoint.json', 'result.json', 'model-selection.json'}):
                continue
            saved = fingerprint(path)
            limit = cutoff if kind == 'screenshots' else now-DAY
            if kind != 'discovery' and saved[3]/1e9 >= limit:
                continue
            if path.stat().st_nlink != 1:
                continue
            result['eligible_files'] += 1
            if apply:
                try:
                    if regular_owned(path, uid) and fingerprint(path) == saved:
                        path.unlink()
                        result['removed_files'] += 1
                        result['removed_bytes'] += saved[2]
                except OSError as exc:
                    result['errors'].append({'path': str(path), 'reason': str(exc)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-config', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--dispose-completed-output', action='store_true',
                        help='Delete terminal discovery scratch and inactive output older than one day')
    args = parser.parse_args()
    if os.name != 'posix':
        parser.error('This maintenance command requires Linux process inspection')
    config = json.loads(args.runtime_config.read_text())
    import fcntl
    state = Path.home()/'.local/state/jobbot-storage'
    if state.resolve() != state:
        parser.error('Storage result directory must not be symlinked')
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state/'maintenance.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'state': 'already_running'}))
            return 0
        result = maintain(Path.home(), config['spool_dir'], config['db_path'], apply=args.apply)
        if args.dispose_completed_output:
            from filelock import FileLock, Timeout
            try:
                with FileLock(str(config['db_path'])+'.harvest.lock', timeout=0):
                    disposed = dispose_completed_output(Path.home(), config['spool_dir'],
                                                        config['db_path'], apply=args.apply)
                    result['disposable_output'] = disposed
                    result['errors'].extend(disposed['errors'])
            except Timeout:
                result['disposable_output'] = {'retained': [{'reason': 'discovery_running'}]}
        usage = shutil.disk_usage(Path.home())
        result['available_bytes'] = usage.free
        result['low_space'] = usage.free < 4*1024**3
        result['checked_at'] = time.time()
        output = json.dumps(result, sort_keys=True)
        (state/'latest.json').write_text(output)
        print(output)
        return int(bool(result['errors']))


if __name__ == '__main__':
    raise SystemExit(main())
