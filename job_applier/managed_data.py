"""Explicit, non-overwriting development data tools. Sources are opened read-only."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from .managed_migrations import migrate
from .managed_shared import ProtocolError, dumps


def absolute(path):
    path=Path(path)
    if not path.is_absolute():raise ProtocolError('absolute_db_path_required')
    if path.is_symlink():raise ProtocolError('symlink_target_refused')
    return path.resolve()


def preview_new(path):
    path=absolute(path)
    blockers=[str(Path(str(path)+s)) for s in ('','-wal','-shm','-journal') if Path(str(path)+s).exists()]
    return {'allowed':not blockers,'target':str(path),'blockers':blockers}


def open_source(path):
    path=absolute(path)
    if not path.is_file():raise ProtocolError('source_not_found')
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10)
    db.row_factory=sqlite3.Row
    return db


def _verify_source(db, instance_id=None):
    if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ProtocolError('source_integrity_failed')
    tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if instance_id:
        if 'instance' not in tables:raise ProtocolError('instance_not_initialized')
        row=db.execute('SELECT id FROM instance').fetchone()
        if not row or row[0]!=instance_id:raise ProtocolError('instance_mismatch')
    if 'browser_leases' in tables and db.execute("SELECT 1 FROM browser_leases WHERE state!='released'").fetchone():raise ProtocolError('runtime_not_quiescent')
    if 'jobs' not in tables:raise ProtocolError('unsupported_source_schema')
    if db.execute("SELECT 1 FROM jobs WHERE status='running'").fetchone():raise ProtocolError('runtime_not_quiescent')
    return {table:db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] for table in ('jobs','application_attempts','company_portal_accounts') if table in tables}


def _copy(db, destination):
    path=absolute(destination)
    if not preview_new(path)['allowed']:raise FileExistsError(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb'):pass
    with closing(sqlite3.connect(path)) as target:
        db.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ProtocolError('backup_integrity_failed')
    return path


def backup(source,destination,*,instance_id):
    source=absolute(source)
    with closing(open_source(source)) as db:
        db.execute('BEGIN')
        counts=_verify_source(db,instance_id)
        path=_copy(db,destination)
    with closing(open_source(path)) as copied:
        if _verify_source(copied,instance_id)!=counts:raise ProtocolError('backup_count_mismatch')
    return {'destination':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'counts':counts,'instance_id':instance_id}


def migrate_copy(source,destination,*,instance_id,expected_source_sha256):
    source=absolute(source)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=expected_source_sha256:raise ProtocolError('source_hash_mismatch')
    with closing(open_source(source)) as db:
        db.execute('BEGIN')
        counts=_verify_source(db)
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='instance'").fetchone():raise ProtocolError('already_managed_source')
        path=_copy(db,destination)
    # All mutations are on the new verified snapshot, never the source.
    migrate(path)
    from .managed import canonical_url
    with closing(sqlite3.connect(path)) as db:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        settings={'mode':'development','submission_mode':'review','worker':'external','autofill':'simplify','screenshots':False,'timezone':'UTC'}
        db.execute('INSERT INTO instance VALUES (?,?,?)',(instance_id,dumps(settings),datetime.now(timezone.utc).isoformat()))
        # Keep legacy identity unknown; hold every imported job until assessed/reconciled.
        for row in db.execute('SELECT id,url FROM jobs').fetchall():
            try:canonical=canonical_url(row['url'])
            except ProtocolError:continue
            identity_key=hashlib.sha256(dumps([canonical]).encode()).hexdigest()
            conflict=db.execute('SELECT id FROM jobs WHERE identity_key=?',(identity_key,)).fetchone()
            if conflict:continue  # Preserve both historical rows; never merge by deletion.
            db.execute("UPDATE jobs SET identity_key=?,eligibility='held' WHERE id=?",(identity_key,row['id']))
        db.commit()
        migrated={table:db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] for table in counts}
        if migrated!=counts:raise ProtocolError('migration_count_mismatch')
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ProtocolError('migration_integrity_failed')
    return {'destination':str(path),'instance_id':instance_id,'counts':counts,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
