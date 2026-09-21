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


def migration_8(db):
    add_columns(db,'managed_actions',{'writes_browser':'INTEGER NOT NULL DEFAULT 1'})
    db.execute('CREATE UNIQUE INDEX one_browser_writer ON managed_actions(attempt_id) WHERE ended_at IS NULL AND writes_browser=1')


def migration_9(db):
    db.execute('CREATE TABLE settings_revisions (version INTEGER PRIMARY KEY,values_json TEXT NOT NULL,values_hash TEXT NOT NULL,created_at TEXT NOT NULL)')


def migration_10(db):
    statements=[
        'CREATE TABLE lessons (id TEXT PRIMARY KEY,kind TEXT NOT NULL,condition TEXT NOT NULL,action TEXT NOT NULL,scope_json TEXT NOT NULL,expected_result TEXT NOT NULL,attempt_ids_json TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL)',
        'CREATE TABLE lesson_history (id INTEGER PRIMARY KEY,lesson_id TEXT NOT NULL REFERENCES lessons(id),attempt_id INTEGER REFERENCES application_attempts(id),success INTEGER,status TEXT,reason TEXT NOT NULL,created_at TEXT NOT NULL)',
        'CREATE TABLE helper_versions (helper_id TEXT NOT NULL,version TEXT NOT NULL,capability TEXT NOT NULL,path TEXT NOT NULL,sha256 TEXT NOT NULL,scope_json TEXT NOT NULL,preconditions_json TEXT NOT NULL,limitations_json TEXT NOT NULL,tests_json TEXT NOT NULL,status TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(helper_id,version))',
        'CREATE TABLE helper_history (id TEXT PRIMARY KEY,helper_id TEXT NOT NULL,version TEXT NOT NULL,status TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL,FOREIGN KEY(helper_id,version) REFERENCES helper_versions(helper_id,version))',
        'CREATE TABLE document_assets (id TEXT PRIMARY KEY,identity_id TEXT NOT NULL REFERENCES candidates(id),kind TEXT NOT NULL,version TEXT NOT NULL,storage_ref TEXT NOT NULL,sha256 TEXT NOT NULL,provenance_json TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(identity_id,kind,version))',
        'CREATE TABLE document_selections (id TEXT PRIMARY KEY,asset_id TEXT NOT NULL REFERENCES document_assets(id),job_id TEXT NOT NULL REFERENCES jobs(id),attempt_id INTEGER REFERENCES application_attempts(id),status TEXT NOT NULL,created_at TEXT NOT NULL)',
        'CREATE TABLE document_uploads (id TEXT PRIMARY KEY,asset_id TEXT NOT NULL REFERENCES document_assets(id),attempt_id INTEGER NOT NULL REFERENCES application_attempts(id),status TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL)',
        'CREATE TABLE match_assessments (id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES jobs(id),jd_hash TEXT NOT NULL,resume_hash TEXT NOT NULL,profile_hash TEXT NOT NULL,evaluator TEXT NOT NULL,model TEXT NOT NULL,rubric TEXT NOT NULL,score REAL,scale_min REAL NOT NULL,scale_max REAL NOT NULL,recommendation TEXT NOT NULL,reasons_json TEXT NOT NULL,evaluated_at TEXT NOT NULL,recorded_at TEXT NOT NULL)',
    ]
    for statement in statements:db.execute(statement)
    for table in ('lesson_history','helper_history','document_uploads','match_assessments'):
        for action in ('UPDATE','DELETE'):
            db.execute(f"CREATE TRIGGER immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable history'); END")


def migration_11(db):
    db.execute('CREATE TABLE account_namespace_aliases (alias TEXT PRIMARY KEY,canonical TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL)')
    add_columns(db,'company_portal_accounts',{'last_confirmed_at':'DATETIME'})
    db.execute('CREATE TABLE budget_extensions (id TEXT PRIMARY KEY,attempt_id INTEGER NOT NULL REFERENCES application_attempts(id),seconds REAL NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL)')
    db.execute('CREATE TABLE owned_targets (id TEXT PRIMARY KEY,attempt_id INTEGER NOT NULL REFERENCES application_attempts(id),profile TEXT NOT NULL,target_id TEXT NOT NULL,url TEXT NOT NULL,state TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(attempt_id,target_id))')
    db.execute('CREATE TABLE target_history (id TEXT PRIMARY KEY,target_record_id TEXT NOT NULL REFERENCES owned_targets(id),state TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL)')
    for table in ('account_namespace_aliases','budget_extensions','target_history'):
        for action in ('UPDATE','DELETE'):
            db.execute(f"CREATE TRIGGER immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable history'); END")


def migration_12(db):
    db.execute('CREATE TABLE attempt_mail_requests (request_id TEXT PRIMARY KEY REFERENCES mail_requests(id),attempt_id INTEGER NOT NULL REFERENCES application_attempts(id))')


def migration_13(db):
    db.execute('CREATE TABLE job_archives (job_id TEXT PRIMARY KEY REFERENCES jobs(id),archived_at TEXT NOT NULL,preview_hash TEXT NOT NULL,backup_path TEXT NOT NULL,backup_sha256 TEXT NOT NULL)')
    for action in ('UPDATE','DELETE'):
        db.execute(f"CREATE TRIGGER immutable_job_archives_{action.lower()} BEFORE {action} ON job_archives BEGIN SELECT RAISE(ABORT,'immutable archive'); END")


def migration_14(db):
    add_columns(db,'account_requests',{'attempt_id':'INTEGER REFERENCES application_attempts(id)'})
    add_columns(db,'managed_actions',{'semantic_context_json':"TEXT NOT NULL DEFAULT '{}'"})
    add_columns(db,'owned_targets',{'identity_key':'TEXT'})


def migration_15(db):
    db.execute('''CREATE TABLE browser_workspaces (
        id TEXT PRIMARY KEY, config_json TEXT NOT NULL, host_id TEXT,
        host_identity_json TEXT, host_seen_at TEXT, state TEXT NOT NULL DEFAULT 'offline',
        reason TEXT, browser_identity_json TEXT, updated_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE application_sessions (
        id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, request_key TEXT NOT NULL,
        job_id TEXT NOT NULL REFERENCES jobs(id), identity_id TEXT NOT NULL REFERENCES candidates(id),
        driver_id TEXT NOT NULL, workspace_id TEXT REFERENCES browser_workspaces(id),
        run_id TEXT REFERENCES runs(id), attempt_id INTEGER REFERENCES application_attempts(id),
        target_id TEXT, state TEXT NOT NULL, reason TEXT, requested_at TEXT NOT NULL,
        preparing_at TEXT, connected_at TEXT, ended_at TEXT, driver_seen_at TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}')''')
    db.execute('CREATE TABLE workspace_profile_aliases (profile TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES browser_workspaces(id))')
    db.execute("CREATE UNIQUE INDEX one_workspace_session ON application_sessions(workspace_id) WHERE ended_at IS NULL AND workspace_id IS NOT NULL")
    db.execute("CREATE UNIQUE INDEX one_local_job ON application_sessions(job_id) WHERE ended_at IS NULL")
    # Old in-memory/API workers cannot acquire a locally reserved job or profile.
    # These guards also cover the interval before readiness creates an attempt.
    db.execute('''CREATE TRIGGER local_reserved_attempt BEFORE INSERT ON application_attempts
        WHEN NEW.workflow != 'local-session-v1' AND (EXISTS (
            SELECT 1 FROM application_sessions s WHERE s.ended_at IS NULL AND s.job_id=NEW.job_id)
            OR EXISTS (SELECT 1 FROM workspace_profile_aliases WHERE profile=NEW.browser_profile))
        BEGIN SELECT RAISE(ABORT,'local_runtime_upgrade_required'); END''')
    for action in ('INSERT', 'UPDATE'):
        db.execute(f'''CREATE TRIGGER local_reserved_lease_{action.lower()} BEFORE {action} ON browser_leases
            WHEN NEW.state != 'released' AND EXISTS (
                SELECT 1 FROM application_sessions s WHERE s.workspace_id=NEW.profile
                AND s.ended_at IS NULL AND (s.attempt_id IS NULL OR s.attempt_id!=NEW.attempt_id))
            BEGIN SELECT RAISE(ABORT,'local_runtime_upgrade_required'); END''')
        db.execute(f'''CREATE TRIGGER legacy_workspace_lease_{action.lower()} BEFORE {action} ON browser_leases
            WHEN NEW.state!='released' AND EXISTS(SELECT 1 FROM workspace_profile_aliases WHERE profile=NEW.profile)
            BEGIN SELECT RAISE(ABORT,'local_runtime_upgrade_required'); END''')
    db.execute('''CREATE TABLE account_coordination (
        person_key TEXT NOT NULL, namespace TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES application_sessions(id),
        acquired_at TEXT NOT NULL, PRIMARY KEY(person_key,namespace))''')


def migration_16(db):
    db.execute('''CREATE TABLE application_questions (
        id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES jobs(id),identity_id TEXT NOT NULL REFERENCES candidates(id),
        first_attempt_id INTEGER NOT NULL REFERENCES application_attempts(id),last_attempt_id INTEGER NOT NULL REFERENCES application_attempts(id),
        question_key TEXT NOT NULL,field TEXT NOT NULL,question TEXT NOT NULL,kind TEXT NOT NULL,
        options_json TEXT NOT NULL,context_json TEXT NOT NULL,state TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0,
        answer_json TEXT,answer_source TEXT,answered_at TEXT,created_at TEXT NOT NULL,last_seen_at TEXT NOT NULL,
        UNIQUE(job_id,identity_id,question_key))''')
    db.execute('''CREATE TABLE application_question_answers (
        question_id TEXT NOT NULL REFERENCES application_questions(id),revision INTEGER NOT NULL,
        answer_json TEXT NOT NULL,source TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL,
        PRIMARY KEY(question_id,revision))''')
    for action in ('UPDATE','DELETE'):
        db.execute(f"CREATE TRIGGER immutable_question_answers_{action.lower()} BEFORE {action} ON application_question_answers BEGIN SELECT RAISE(ABORT,'immutable answer history'); END")
    db.execute('''CREATE TABLE answer_retry_requests (
        id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES jobs(id),identity_id TEXT NOT NULL REFERENCES candidates(id),
        state TEXT NOT NULL,requested_at TEXT NOT NULL,session_id TEXT REFERENCES application_sessions(id),started_at TEXT)''')
    db.execute("CREATE UNIQUE INDEX one_queued_answer_retry ON answer_retry_requests(job_id,identity_id) WHERE state='queued'")


def migration_17(db):
    # Requests may share a posting. Browser profile allocation is independent.
    db.execute('DROP INDEX IF EXISTS uq_managed_active_job')
    db.execute('DROP INDEX IF EXISTS one_local_job')
    db.execute('DROP TRIGGER IF EXISTS local_reserved_attempt')
    db.execute('''CREATE TRIGGER local_reserved_attempt BEFORE INSERT ON application_attempts
        WHEN NEW.workflow != 'local-session-v1' AND EXISTS (
            SELECT 1 FROM workspace_profile_aliases WHERE profile=NEW.browser_profile)
        BEGIN SELECT RAISE(ABORT,'local_runtime_upgrade_required'); END''')


def migration_18(db):
    db.execute('''CREATE TABLE dispatch_queue (
        id TEXT PRIMARY KEY,request_id TEXT NOT NULL,job_id TEXT NOT NULL REFERENCES jobs(id),
        identity_id TEXT NOT NULL REFERENCES candidates(id),resume_asset_id TEXT NOT NULL REFERENCES document_assets(id),
        state TEXT NOT NULL,created_at TEXT NOT NULL,started_at TEXT,ended_at TEXT,
        executor_identity_json TEXT,session_id TEXT REFERENCES application_sessions(id),outcome TEXT,detail TEXT,
        UNIQUE(request_id,job_id))''')
    db.execute("CREATE UNIQUE INDEX one_queued_job_identity ON dispatch_queue(job_id,identity_id) WHERE state!='finished'")
    db.execute('''CREATE TABLE dispatch_control (
        id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL DEFAULT 0,
        wake_requested INTEGER NOT NULL DEFAULT 0,heartbeat_at TEXT,worker_identity_json TEXT,
        current_item TEXT,detail TEXT,next_automatic_at TEXT)''')
    db.execute('INSERT INTO dispatch_control(id) VALUES (1)')


def migration_19(db):
    # Operator disposition is independent of immutable application evidence.
    add_columns(db, 'jobs', {'disposition': "TEXT NOT NULL DEFAULT 'active'",
                            'disposition_reason': 'TEXT', 'disposition_at': 'TEXT'})


def migration_20(db):
    db.execute('''CREATE TABLE discovery_runs (
        id TEXT PRIMARY KEY,started_at TEXT NOT NULL,ended_at TEXT,
        process_identity_json TEXT NOT NULL,batch_size INTEGER NOT NULL,
        enqueue_authorized INTEGER NOT NULL,executor_exit_code INTEGER,
        record_file_exists INTEGER,error TEXT)''')
    db.execute('CREATE TABLE discovery_control (id INTEGER PRIMARY KEY,last_checked_at TEXT)')
    db.execute('INSERT INTO discovery_control(id) VALUES (1)')


def migration_21(db):
    # Optional provenance only: old sources and queue outcomes remain unchanged.
    db.execute('''CREATE TABLE source_observations (
        id TEXT PRIMARY KEY,source_record_id TEXT NOT NULL REFERENCES job_sources(id),
        producer TEXT,discovery_run_id TEXT,discovery_profile TEXT,recorded_at TEXT NOT NULL)''')
    db.execute('CREATE INDEX observations_by_source ON source_observations(source_record_id)')
    add_columns(db, 'dispatch_queue', {'enqueue_origin':'TEXT', 'producer':'TEXT',
                                      'discovery_run_id':'TEXT', 'discovery_profile':'TEXT'})


def migration_22(db):
    add_columns(db, 'dispatch_queue', {'immediate_requested_at': 'TEXT'})
    # Remember every operator request even when it promotes an existing queue item.
    db.execute('''CREATE TABLE dispatch_immediate_requests (
        request_id TEXT NOT NULL,job_id TEXT NOT NULL REFERENCES jobs(id),
        item_id TEXT NOT NULL REFERENCES dispatch_queue(id),requested_at TEXT NOT NULL,
        PRIMARY KEY(request_id,job_id))''')


def migration_23(db):
    from .managed_identity import retain_posting_aliases
    retain_posting_aliases(db)


MIGRATIONS = [(1, migration_1), (2, migration_2), (3, migration_3), (4, migration_4), (5, migration_5), (6, migration_6), (7, migration_7), (8, migration_8), (9, migration_9), (10, migration_10), (11, migration_11), (12, migration_12), (13, migration_13), (14, migration_14), (15, migration_15), (16, migration_16), (17, migration_17), (18, migration_18), (19, migration_19), (20, migration_20), (21, migration_21), (22, migration_22), (23, migration_23)]


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
