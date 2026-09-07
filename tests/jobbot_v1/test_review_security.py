"""Targeted security regression tests for independent review S1/S2 (expected RED).

Primary Windows Hermes retains all implementation/architecture/job logic/integration.
These tests define and assert security and redaction contracts for:
1) Rejected or redacted secret-bearing settings (Service.create with extra api_key, nested credentials).
2) Intake metadata containing secrets ({'password': 'SYNTHETIC_SENTINEL'}).
3) Accepted-run capabilities containing credentials/secrets extra.
4) No secret can appear in ordinary DB fields across any SQLite table.
5) Finish blocked evidence='password=SYNTHETIC_SENTINEL' must reject or evidence AND finish_key exclude sentinel.
6) Quoted JSON credential strings ('{"password":"SYNTHETIC_SENTINEL"}') in event safe evidence and account notes must not persist sentinel.

Rules:
- Either ProtocolError rejection or inspected persisted rows with sentinel absent.
- Unexpected AttributeError / TypeError is not pass.
- No prod edits; source remains unchanged until primary reviews RED findings.
"""
import json
import sqlite3
import pytest
from job_applier.managed import Service, ProtocolError
from test_ownership import ready, accept


def assert_sentinel_absent_from_db(db, sentinel):
    """Inspect all text fields across all tables to guarantee sentinel does not appear in ordinary DB fields."""
    cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cursor.fetchall()]
    for table in tables:
        tbl_cursor = db.execute(f'SELECT * FROM "{table}"')
        rows = tbl_cursor.fetchall()
        for row in rows:
            for idx, col_name in enumerate(row.keys()):
                val = row[idx]
                if isinstance(val, str):
                    assert sentinel not in val, (
                        f"Secret sentinel '{sentinel}' leaked into table '{table}', column '{col_name}': {val}"
                    )


# ---------------------------------------------------------------------------
# S1 / S2 Scenario 1: Secret-bearing settings (create with extra api_key)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    'settings_payload,sentinel',
    [
        ({'api_key': 'SYNTHETIC_SENTINEL_SETTING_KEY'}, 'SYNTHETIC_SENTINEL_SETTING_KEY'),
        ({'api-key': 'SYNTHETIC_SENTINEL_SETTING_DASHKEY'}, 'SYNTHETIC_SENTINEL_SETTING_DASHKEY'),
        ({'credentials': {'api_key': 'SYNTHETIC_SENTINEL_SETTING_NESTED'}}, 'SYNTHETIC_SENTINEL_SETTING_NESTED'),
        ({'auth': {'password': 'SYNTHETIC_SENTINEL_SETTING_PW'}}, 'SYNTHETIC_SENTINEL_SETTING_PW'),
    ],
    ids=['extra_api_key', 'extra_dash_key', 'nested_credentials', 'nested_password'],
)
def test_secret_bearing_settings_rejected_or_redacted(tmp_path, settings_payload, sentinel):
    """Service.create with secret-bearing settings must reject or redact sentinel from DB fields."""
    db_path = tmp_path / 'sec_settings.db'
    try:
        s = Service.create(db_path, instance_id='inst-sec-settings', settings=settings_payload)
    except ProtocolError:
        # Valid contract rejection
        return

    # If creation succeeded without rejection, verify sentinel was not persisted in DB
    with s.tx() as db:
        inst_row = db.execute("SELECT settings_json FROM instance WHERE id='inst-sec-settings'").fetchone()
        assert inst_row is not None
        assert sentinel not in inst_row['settings_json'], (
            f"Sentinel leaked into instance.settings_json: {inst_row['settings_json']}"
        )
        assert_sentinel_absent_from_db(db, sentinel)

    # Verify run request and claimed attempt do not inherit the secret into runs or attempts
    s.identity(
        identity_id='candidate',
        person_key='person-1',
        email='candidate@example.test',
        profile={'facts': {'work_authorization': 'fixture'}, 'resume_ref': 'asset:fixture-v1'},
    )
    job = s.intake(url='https://careers.example.test/jobs/settings-sec-1', source_id='settings-sec-1')
    s.eligibility(job['id'], 'ready', reason='synthetic operator approval')
    r = s.request_run(
        request_id='run-sec-settings-1',
        job_ids=[job['id']],
        identity_id='candidate',
        browser_profile='fixture-browser',
    )
    with s.tx() as db:
        run_row = db.execute("SELECT settings_json FROM runs WHERE id=?", (r['id'],)).fetchone()
        assert sentinel not in run_row['settings_json'], (
            f"Sentinel leaked into runs.settings_json: {run_row['settings_json']}"
        )

    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')
    with s.tx() as db:
        attempt_row = db.execute("SELECT settings_json FROM application_attempts WHERE id=?", (a['id'],)).fetchone()
        assert sentinel not in attempt_row['settings_json'], (
            f"Sentinel leaked into application_attempts.settings_json: {attempt_row['settings_json']}"
        )
        assert_sentinel_absent_from_db(db, sentinel)


# ---------------------------------------------------------------------------
# S1 / S2 Scenario 2: Intake metadata {'password':'SYNTHETIC_SENTINEL'}
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    'metadata,sentinel',
    [
        ({'password': 'SYNTHETIC_SENTINEL_INTAKE_PW'}, 'SYNTHETIC_SENTINEL_INTAKE_PW'),
        ({'credentials': {'password': 'SYNTHETIC_SENTINEL_INTAKE_NESTED_PW'}}, 'SYNTHETIC_SENTINEL_INTAKE_NESTED_PW'),
        ({'api_key': 'SYNTHETIC_SENTINEL_INTAKE_KEY'}, 'SYNTHETIC_SENTINEL_INTAKE_KEY'),
        ({'auth': {'token': 'SYNTHETIC_SENTINEL_INTAKE_TOKEN'}}, 'SYNTHETIC_SENTINEL_INTAKE_TOKEN'),
    ],
    ids=['metadata_password', 'metadata_nested_password', 'metadata_api_key', 'metadata_nested_token'],
)
def test_intake_metadata_secrets_rejected_or_redacted(tmp_path, metadata, sentinel):
    """Intake metadata bearing secrets must reject or redact sentinel from DB fields."""
    s = Service.create(tmp_path / 'sec_intake.db', instance_id='inst-sec-intake')
    try:
        job = s.intake(
            url='https://careers.example.test/jobs/sec-intake',
            source_id='sec-intake-1',
            **metadata,
        )
    except ProtocolError:
        # Valid contract rejection
        return

    # If intake succeeded without rejection, verify sentinel was not persisted
    with s.tx() as db:
        job_row = db.execute("SELECT metadata_json, notes, error FROM jobs WHERE id=?", (job['id'],)).fetchone()
        assert job_row is not None
        assert sentinel not in job_row['metadata_json'], (
            f"Sentinel leaked into jobs.metadata_json: {job_row['metadata_json']}"
        )
        assert sentinel not in (job_row['notes'] or '')
        assert sentinel not in (job_row['error'] or '')
        assert_sentinel_absent_from_db(db, sentinel)


# ---------------------------------------------------------------------------
# S1 / S2 Scenario 3: Accepted-run capabilities credentials extra
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    'extra_caps,sentinel',
    [
        ({'api_key': 'SYNTHETIC_SENTINEL_CAP_KEY'}, 'SYNTHETIC_SENTINEL_CAP_KEY'),
        ({'credentials': {'password': 'SYNTHETIC_SENTINEL_CAP_PW'}}, 'SYNTHETIC_SENTINEL_CAP_PW'),
        ({'access_token': 'SYNTHETIC_SENTINEL_CAP_TOKEN'}, 'SYNTHETIC_SENTINEL_CAP_TOKEN'),
        ({'worker_auth': {'secret': 'SYNTHETIC_SENTINEL_CAP_SECRET'}}, 'SYNTHETIC_SENTINEL_CAP_SECRET'),
    ],
    ids=['caps_api_key', 'caps_nested_password', 'caps_access_token', 'caps_nested_secret'],
)
def test_accepted_run_capabilities_credentials_rejected_or_redacted(tmp_path, extra_caps, sentinel):
    """Accepted-run capabilities with credentials extra must reject or redact sentinel from DB fields."""
    s, r, ids = ready(tmp_path, count=1)
    base_caps = {
        'protocol': 1,
        'skill_version': 'test-skill',
        'browser_profile': 'fixture-browser',
        'provider': 'fixture',
        'model': 'fixture',
        'telemetry': True,
    }
    caps = {**base_caps, **extra_caps}

    try:
        s.accept_run(r['id'], worker_id='worker', session_id='session-1', capabilities=caps)
    except ProtocolError:
        # Valid contract rejection
        return

    # If accepted, verify sentinel is not persisted in runs.capabilities_json
    with s.tx() as db:
        run_row = db.execute("SELECT capabilities_json FROM runs WHERE id=?", (r['id'],)).fetchone()
        assert run_row is not None
        assert sentinel not in run_row['capabilities_json'], (
            f"Sentinel leaked into runs.capabilities_json: {run_row['capabilities_json']}"
        )
        assert_sentinel_absent_from_db(db, sentinel)

    # When claimed, versions_json snapshot in application_attempts must also exclude sentinel
    a = s.claim(r['id'], worker_id='worker')
    with s.tx() as db:
        attempt_row = db.execute("SELECT versions_json FROM application_attempts WHERE id=?", (a['id'],)).fetchone()
        assert attempt_row is not None
        assert sentinel not in attempt_row['versions_json'], (
            f"Sentinel leaked into application_attempts.versions_json: {attempt_row['versions_json']}"
        )
        assert_sentinel_absent_from_db(db, sentinel)


# ---------------------------------------------------------------------------
# S1 / S2 Scenario 4: Finish blocked evidence='password=SYNTHETIC_SENTINEL'
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    'outcome,evidence_val,sentinel',
    [
        ('blocked', 'password=SYNTHETIC_SENTINEL_FINISH_PW', 'SYNTHETIC_SENTINEL_FINISH_PW'),
        ('blocked', 'page error: password=SYNTHETIC_SENTINEL_FINISH_PAGE', 'SYNTHETIC_SENTINEL_FINISH_PAGE'),
        ('blocked', 'api_key=SYNTHETIC_SENTINEL_FINISH_KEY', 'SYNTHETIC_SENTINEL_FINISH_KEY'),
        ('failed', 'worker error: password=SYNTHETIC_SENTINEL_FINISH_FAIL', 'SYNTHETIC_SENTINEL_FINISH_FAIL'),
    ],
    ids=['blocked_pw', 'blocked_page_pw', 'blocked_api_key', 'failed_pw'],
)
def test_finish_blocked_evidence_secret_rejection_or_redaction(tmp_path, outcome, evidence_val, sentinel):
    """Finish blocked evidence with secret must reject or evidence AND finish_key exclude sentinel."""
    s, r, ids = ready(tmp_path, count=1)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')

    try:
        s.finish(
            a['id'],
            worker_id='worker',
            fence=a['fence'],
            outcome=outcome,
            evidence=evidence_val,
            quiescent=True,
        )
    except ProtocolError:
        # Valid contract rejection
        return

    # If finish was accepted, evidence AND finish_key must exclude sentinel
    with s.tx() as db:
        attempt_row = db.execute(
            "SELECT outcome, evidence, finish_key FROM application_attempts WHERE id=?",
            (a['id'],),
        ).fetchone()
        assert attempt_row is not None
        assert sentinel not in (attempt_row['evidence'] or ''), (
            f"Sentinel leaked into application_attempts.evidence: {attempt_row['evidence']}"
        )
        assert sentinel not in (attempt_row['finish_key'] or ''), (
            f"Sentinel leaked into application_attempts.finish_key: {attempt_row['finish_key']}"
        )
        assert_sentinel_absent_from_db(db, sentinel)


# ---------------------------------------------------------------------------
# S1 / S2 Scenario 5: Quoted JSON credential string in event safe evidence
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    'json_evidence,sentinel',
    [
        ('{"password":"SYNTHETIC_SENTINEL_EV_PW"}', 'SYNTHETIC_SENTINEL_EV_PW'),
        ('{"credentials":{"password":"SYNTHETIC_SENTINEL_EV_NESTED_PW"}}', 'SYNTHETIC_SENTINEL_EV_NESTED_PW'),
        ('{"auth":{"token":"SYNTHETIC_SENTINEL_EV_TOKEN"}}', 'SYNTHETIC_SENTINEL_EV_TOKEN'),
        ('{"api_key":"SYNTHETIC_SENTINEL_EV_KEY"}', 'SYNTHETIC_SENTINEL_EV_KEY'),
    ],
    ids=['flat_json_pw', 'nested_json_pw', 'nested_json_token', 'flat_json_api_key'],
)
def test_quoted_json_credential_as_event_safe_evidence_not_persisted(tmp_path, json_evidence, sentinel):
    """Quoted JSON credential string as event safe evidence must not persist sentinel in managed_events."""
    s, r, ids = ready(tmp_path, count=1)
    accept(s, r)
    a = s.claim(r['id'], worker_id='worker')
    event_id = f'ev-sec-{sentinel[:12]}'

    try:
        s.event(
            a['id'],
            worker_id='worker',
            fence=a['fence'],
            event_id=event_id,
            action_id='act-sec-1',
            event_type='field_verified',
            observed_at='2026-09-06T12:00:01+00:00',
            duration_seconds=1.0,
            payload={'evidence': json_evidence},
        )
    except ProtocolError:
        # Valid contract rejection
        return

    with s.tx() as db:
        ev_row = db.execute("SELECT payload_json FROM managed_events WHERE id=?", (event_id,)).fetchone()
        assert ev_row is not None
        assert sentinel not in ev_row['payload_json'], (
            f"Sentinel leaked into managed_events.payload_json: {ev_row['payload_json']}"
        )
        assert_sentinel_absent_from_db(db, sentinel)


# ---------------------------------------------------------------------------
# S1 / S2 Scenario 6: Quoted JSON credential string in account notes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    'json_evidence,sentinel',
    [
        ('{"password":"SYNTHETIC_SENTINEL_ACC_PW"}', 'SYNTHETIC_SENTINEL_ACC_PW'),
        ('{"portal_account":{"password":"SYNTHETIC_SENTINEL_ACC_NESTED_PW"}}', 'SYNTHETIC_SENTINEL_ACC_NESTED_PW'),
        ('{"token":"SYNTHETIC_SENTINEL_ACC_TOKEN"}', 'SYNTHETIC_SENTINEL_ACC_TOKEN'),
        ('{"auth":{"api_key":"SYNTHETIC_SENTINEL_ACC_KEY"}}', 'SYNTHETIC_SENTINEL_ACC_KEY'),
    ],
    ids=['flat_json_pw', 'nested_json_pw', 'flat_json_token', 'nested_json_api_key'],
)
def test_quoted_json_credential_as_account_notes_not_persisted(tmp_path, json_evidence, sentinel):
    """Quoted JSON credential string as account notes must not persist sentinel in company_portal_accounts."""
    s = Service.create(tmp_path / 'sec_account.db', instance_id='inst-sec-account')
    s.identity(
        identity_id='candidate',
        person_key='person-1',
        email='candidate@example.test',
        profile={'facts': {'work_authorization': 'fixture'}, 'resume_ref': 'asset:fixture-v1'},
    )
    req_id = f'acc-req-{sentinel[:12]}'

    try:
        s.account_update(
            namespace='careers.example.test',
            identity_id='candidate',
            state='confirmed',
            credential_ref='vault:ref-1',
            request_id=req_id,
            evidence=json_evidence,
        )
    except ProtocolError:
        # Valid contract rejection
        return

    with s.tx() as db:
        acc_row = db.execute(
            "SELECT notes FROM company_portal_accounts WHERE namespace=? AND identity_id=?",
            ('careers.example.test', 'candidate'),
        ).fetchone()
        if acc_row:
            assert sentinel not in (acc_row['notes'] or ''), (
                f"Sentinel leaked into company_portal_accounts.notes: {acc_row['notes']}"
            )

        req_row = db.execute("SELECT response_json FROM account_requests WHERE id=?", (req_id,)).fetchone()
        if req_row:
            assert sentinel not in req_row['response_json'], (
                f"Sentinel leaked into account_requests.response_json: {req_row['response_json']}"
            )

        assert_sentinel_absent_from_db(db, sentinel)
