"""Versioned additive SQLite migrations; only called on explicitly selected instances."""
import sqlite3
from pathlib import Path


def connect(path):
    db = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    return db


def add_columns(db, table, columns):
    # All identifiers are static source declarations, never external data.
    existing = {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
    for name, declaration in columns.items():
        if name not in existing:
            db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')


def migration_1(db):
    add_columns(db, 'jobs', {'identity_key':'TEXT', 'namespace':'TEXT', 'requisition_id':'TEXT', 'eligibility':"TEXT NOT NULL DEFAULT 'held'", 'metadata_json':"TEXT NOT NULL DEFAULT '{}'"})
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_identity ON jobs(identity_key) WHERE identity_key IS NOT NULL')
    db.execute('CREATE TABLE IF NOT EXISTS instance (id TEXT PRIMARY KEY, settings_json TEXT NOT NULL, created_at TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS job_sources (id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), source_type TEXT NOT NULL, source_id TEXT NOT NULL, original_url TEXT NOT NULL, discovered_at TEXT NOT NULL, UNIQUE(source_type,source_id,original_url))')


def migration_2(db):
    add_columns(db, 'application_attempts', {
        'run_id':'TEXT REFERENCES runs(id)', 'identity_id':'TEXT', 'worker_id':'TEXT',
        'session_id':'TEXT', 'browser_profile':'TEXT', 'fence':'INTEGER',
        'heartbeat_at':'TEXT', 'progress_at':'TEXT', 'activity':"TEXT DEFAULT 'preflight'",
        'settings_json':"TEXT DEFAULT '{}'", 'profile_json':"TEXT DEFAULT '{}'",
        'versions_json':"TEXT DEFAULT '{}'", 'submit_intent_at':'TEXT',
        'finish_key':'TEXT', 'uncertain_duration':'INTEGER DEFAULT 0',
    })
    statements = [
        'CREATE TABLE candidates (id TEXT PRIMARY KEY, person_key TEXT NOT NULL, email TEXT NOT NULL, state TEXT NOT NULL, profile_json TEXT NOT NULL, profile_hash TEXT NOT NULL)',
        'CREATE TABLE runs (id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, request_key TEXT NOT NULL, identity_id TEXT NOT NULL REFERENCES candidates(id), browser_profile TEXT NOT NULL, state TEXT NOT NULL, control TEXT NOT NULL DEFAULT \'running\', requested_at TEXT NOT NULL, accepted_at TEXT, started_at TEXT, ended_at TEXT, worker_id TEXT, session_id TEXT, settings_json TEXT NOT NULL, capabilities_json TEXT NOT NULL DEFAULT \'{}\', checkpoint_json TEXT NOT NULL DEFAULT \'{}\')',
        'CREATE TABLE run_jobs (run_id TEXT NOT NULL REFERENCES runs(id), job_id TEXT NOT NULL REFERENCES jobs(id), position INTEGER NOT NULL, state TEXT NOT NULL DEFAULT \'pending\', PRIMARY KEY(run_id,job_id), UNIQUE(run_id,position))',
        'CREATE TABLE browser_leases (profile TEXT PRIMARY KEY, attempt_id INTEGER REFERENCES application_attempts(id), worker_id TEXT, generation INTEGER NOT NULL, expires_at TEXT, state TEXT NOT NULL)',
        'CREATE UNIQUE INDEX uq_managed_active_job ON application_attempts(job_id) WHERE run_id IS NOT NULL AND completed_at IS NULL',
        'CREATE TABLE submission_ledger (job_id TEXT PRIMARY KEY REFERENCES jobs(id), person_key TEXT, evidence TEXT NOT NULL, recorded_at TEXT NOT NULL)',
        'CREATE TABLE managed_events (id TEXT PRIMARY KEY, attempt_id INTEGER REFERENCES application_attempts(id), run_id TEXT REFERENCES runs(id), action_id TEXT, actor TEXT NOT NULL, event_type TEXT NOT NULL, observed_at TEXT NOT NULL, recorded_at TEXT NOT NULL, duration_seconds REAL, stale INTEGER NOT NULL DEFAULT 0, payload_json TEXT NOT NULL, request_hash TEXT NOT NULL)',
        "CREATE TRIGGER immutable_events_update BEFORE UPDATE ON managed_events BEGIN SELECT RAISE(ABORT, 'immutable_event'); END",
        "CREATE TRIGGER immutable_events_delete BEFORE DELETE ON managed_events BEGIN SELECT RAISE(ABORT, 'immutable_event'); END",
    ]
    for sql in statements: db.execute(sql)
    # A migration preserves evidence without inferring an account or a candidate email.
    db.execute("INSERT OR IGNORE INTO submission_ledger(job_id,evidence,recorded_at) SELECT id,'legacy_applied_status',COALESCE(completed_at,CURRENT_TIMESTAMP) FROM jobs WHERE status='applied'")


def migration_3(db):
    add_columns(db, 'application_attempts', {'writer_state':"TEXT NOT NULL DEFAULT 'idle'"})
    db.execute('CREATE TABLE managed_actions (id TEXT PRIMARY KEY, attempt_id INTEGER NOT NULL REFERENCES application_attempts(id), tool_name TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT, status TEXT, duration_seconds REAL, uncertainty INTEGER NOT NULL DEFAULT 0)')


def migration_4(db):
    add_columns(db,'company_portal_accounts',{'identity_id':'TEXT REFERENCES candidates(id)', 'namespace':'TEXT', 'credential_ref':'TEXT'})
    db.execute('CREATE UNIQUE INDEX uq_account_namespace_identity ON company_portal_accounts(namespace,identity_id) WHERE identity_id IS NOT NULL')
    db.execute('CREATE TABLE account_requests (id TEXT PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES company_portal_accounts(id), request_hash TEXT NOT NULL, response_json TEXT NOT NULL, created_at TEXT NOT NULL)')
    db.execute('CREATE TABLE mail_requests (id TEXT PRIMARY KEY, identity_id TEXT NOT NULL REFERENCES candidates(id), namespace TEXT NOT NULL, purpose TEXT NOT NULL, requested_at TEXT NOT NULL, expires_at TEXT NOT NULL, expected_sender TEXT NOT NULL)')


def migration_5(db):
    db.execute('CREATE TABLE run_checkpoints (id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES runs(id),worker_id TEXT NOT NULL,session_id TEXT NOT NULL,data_json TEXT NOT NULL,created_at TEXT NOT NULL)')
    db.execute("CREATE TRIGGER immutable_checkpoint_update BEFORE UPDATE ON run_checkpoints BEGIN SELECT RAISE(ABORT,'immutable_checkpoint'); END")
    db.execute("CREATE TRIGGER immutable_checkpoint_delete BEFORE DELETE ON run_checkpoints BEGIN SELECT RAISE(ABORT,'immutable_checkpoint'); END")
    db.execute('CREATE TABLE run_sessions (id INTEGER PRIMARY KEY,run_id TEXT NOT NULL REFERENCES runs(id),worker_id TEXT NOT NULL,session_id TEXT NOT NULL,started_at TEXT NOT NULL,ended_at TEXT)')


def migration_6(db):
    from .managed_identity import job_key
    from .managed_shared import ProtocolError
    db.execute('CREATE TABLE job_identity_keys (identity_key TEXT NOT NULL,job_id TEXT NOT NULL REFERENCES jobs(id),evidence TEXT NOT NULL,PRIMARY KEY(identity_key,job_id))')
    for row in db.execute('SELECT id,url,identity_key,namespace,requisition_id FROM jobs').fetchall():
        keys={row['identity_key']} if row['identity_key'] else set()
        try:
            keys.add(job_key(row['url']))
            if row['namespace'] and row['requisition_id']:keys.add(job_key(row['url'],row['namespace'],row['requisition_id']))
        except ProtocolError:
            pass  # Preserve malformed legacy record without inventing a repaired identity.
        for key in keys:
            db.execute('INSERT OR IGNORE INTO job_identity_keys VALUES (?,?,?)',(key,row['id'],'legacy_identity_reference'))


def migration_7(db):
    # The legacy tracker could overwrite jobs.status on a later failed attempt.
    # Preserve original rows/statuses; recover suppression from completed history.
    # Store an evidence pointer, never duplicate private confirmation text.
    db.execute("""INSERT OR IGNORE INTO submission_ledger
        (job_id,person_key,evidence,recorded_at)
        SELECT a.job_id,c.person_key,'legacy_completed_attempt:'||a.id,a.completed_at
        FROM application_attempts a LEFT JOIN candidates c ON c.id=a.identity_id
        WHERE a.outcome IN ('applied','already_applied') AND a.completed_at IS NOT NULL
        AND TRIM(COALESCE(a.evidence,''))<>'' ORDER BY a.completed_at,a.id""")


MIGRATIONS = [(1, migration_1), (2, migration_2), (3, migration_3), (4, migration_4), (5, migration_5), (6, migration_6), (7, migration_7)]


def migrate(path):
    db = connect(path)
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        versions={r[0] for r in db.execute('SELECT version FROM schema_migrations')}
        for version, fn in MIGRATIONS:
            if version not in versions:
                fn(db)
                db.execute('INSERT INTO schema_migrations(version) VALUES (?)',(version,))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
