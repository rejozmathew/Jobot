"""Accounts slice API tests (expected RED).

Primary Windows Hermes retains all implementation/architecture/job logic/integration.
These tests define and assert contracts for:
A1) Account confirmed survives failed application finish.
A2) Account states (creation_pending, confirmed, reconciliation_required, disabled), idempotence, and evidence requirements.
A3) Isolation across namespaces and candidate identities.
A4) Mail request metadata correlation, filtering, and ambiguity rejection.
"""
import pytest
from job_applier.managed import Service, ProtocolError


def new_service(tmp_path):
    s = Service.create(tmp_path / 'accounts.db', instance_id='test-accounts')
    s.identity(
        identity_id='candidate',
        person_key='person-1',
        email='candidate@example.test',
        profile={'facts': {'work_authorization': 'fixture'}, 'resume_ref': 'asset:fixture-v1'},
    )
    return s


def test_A1_account_confirmed_survives_failed_application_finish(tmp_path):
    """A1: Account created/verified but application fails -> account remains available for next role."""
    s = new_service(tmp_path)
    acc = s.account_update(
        namespace='careers.example.test',
        identity_id='candidate',
        state='confirmed',
        credential_ref='vault:fixture-1',
        request_id='registration-1',
        evidence='fixture account verified',
    )
    assert isinstance(acc, dict)
    assert acc['state'] == 'confirmed'
    assert acc['namespace'] == 'careers.example.test'
    assert acc['identity_id'] == 'candidate'
    assert acc['credential_ref'] == 'vault:fixture-1'

    strategy = s.account_strategy(namespace='careers.example.test', identity_id='candidate')
    assert isinstance(strategy, dict)
    assert strategy['action'] == 'sign_in'

    # Intake a job, claim, and finish as failed
    job = s.intake(url='https://careers.example.test/jobs/101', source_id='m1')
    s.eligibility(job['id'], 'ready', reason='synthetic operator approval')
    r = s.request_run(
        request_id='run-acc-1',
        job_ids=[job['id']],
        identity_id='candidate',
        browser_profile='fixture-browser',
    )
    s.accept_run(
        r['id'],
        worker_id='worker',
        session_id='session-1',
        capabilities={
            'protocol': 1,
            'skill_version': 'test-skill',
            'browser_profile': 'fixture-browser',
            'provider': 'fixture',
            'model': 'fixture',
            'telemetry': True,
        },
    )
    a = s.claim(r['id'], worker_id='worker')
    s.finish(
        a['id'],
        worker_id='worker',
        fence=a['fence'],
        outcome='failed',
        evidence='fixture failure',
        quiescent=True,
    )

    # Confirmed account must survive failed application finish
    strategy_after = s.account_strategy(namespace='careers.example.test', identity_id='candidate')
    assert strategy_after['action'] == 'sign_in'


def test_A2_account_states_idempotence_and_reconciliation(tmp_path):
    """A2: Crash around account creation response; stored request/credential reference

    supports reconciliation; no blind new account; idempotent replay.
    """
    s = new_service(tmp_path)

    # Absent account -> action == 'unknown'
    absent = s.account_strategy(namespace='absent.example.test', identity_id='candidate')
    assert absent['action'] == 'unknown'

    # Creation pending: evidence may be empty
    pending = s.account_update(
        namespace='careers.example.test',
        identity_id='candidate',
        state='creation_pending',
        credential_ref='vault:fixture-pending',
        request_id='reg-pending-1',
        evidence='',
    )
    assert pending['state'] == 'creation_pending'
    assert pending['namespace'] == 'careers.example.test'
    assert pending['identity_id'] == 'candidate'
    assert pending['credential_ref'] == 'vault:fixture-pending'
    assert s.account_strategy(namespace='careers.example.test', identity_id='candidate')['action'] == 'reconcile'

    # Idempotent repeated same request/content
    pending_retry = s.account_update(
        namespace='careers.example.test',
        identity_id='candidate',
        state='creation_pending',
        credential_ref='vault:fixture-pending',
        request_id='reg-pending-1',
        evidence='',
    )
    assert pending_retry == pending

    # Unknown outcome must stay reconciliation_required not auto create
    rec = s.account_update(
        namespace='careers.example.test',
        identity_id='candidate',
        state='reconciliation_required',
        credential_ref='vault:fixture-pending',
        request_id='reg-unknown-1',
        evidence='unknown crash during creation',
    )
    assert rec['state'] == 'reconciliation_required'
    assert s.account_strategy(namespace='careers.example.test', identity_id='candidate')['action'] == 'reconcile'

    # Disabled -> operator_required
    dis = s.account_update(
        namespace='careers.example.test',
        identity_id='candidate',
        state='disabled',
        credential_ref='vault:fixture-pending',
        request_id='reg-dis-1',
        evidence='fixture disabled',
    )
    assert dis['state'] == 'disabled'
    assert s.account_strategy(namespace='careers.example.test', identity_id='candidate')['action'] == 'operator_required'

    # Confirmed requires evidence
    with pytest.raises(ProtocolError):
        s.account_update(
            namespace='careers.example.test',
            identity_id='candidate',
            state='confirmed',
            credential_ref='vault:fixture-1',
            request_id='reg-no-evidence',
            evidence='',
        )

    # No password input supported
    with pytest.raises((ProtocolError, TypeError)):
        s.account_update(
            namespace='careers.example.test',
            identity_id='candidate',
            state='confirmed',
            credential_ref='vault:fixture-1',
            request_id='reg-with-pass',
            evidence='fixture verified',
            password='SENTINEL_PASSWORD',
        )


def test_A3_namespace_and_identity_isolation(tmp_path):
    """A3: Legacy/new emails and same/similar employers across namespaces.

    Same company / different namespaces OR same namespace / different identity must not reuse.
    """
    s = new_service(tmp_path)
    s.identity(
        identity_id='candidate-other',
        person_key='person-2',
        email='other@example.test',
        profile={'facts': {'work_authorization': 'fixture'}},
    )

    # Candidate registers confirmed account on Workday namespace
    s.account_update(
        namespace='example.myworkdayjobs.com',
        identity_id='candidate',
        state='confirmed',
        credential_ref='vault:workday-cand1',
        request_id='reg-wd-1',
        evidence='verified for candidate',
    )
    strat = s.account_strategy(namespace='example.myworkdayjobs.com', identity_id='candidate')
    assert strat['action'] == 'sign_in'

    # Same company, different namespace (e.g. Greenhouse board for same company)
    strat_other_ns = s.account_strategy(namespace='job-boards.greenhouse.io/example', identity_id='candidate')
    assert strat_other_ns['action'] == 'unknown'

    # Same namespace, different identity
    strat_other_id = s.account_strategy(namespace='example.myworkdayjobs.com', identity_id='candidate-other')
    assert strat_other_id['action'] == 'unknown'


def test_A4_mail_metadata_correlation_and_ambiguity_rejection(tmp_path):
    """A4: Unrelated/newest OTP versus correlated request.

    Only correct recipient/purpose/portal/time-matched message used; no code logged;
    multiple matches raise ProtocolError('ambiguous_mail').
    """
    s = new_service(tmp_path)

    # Mail request returns dict id
    req = s.mail_request(
        identity_id='candidate',
        namespace='careers.example.test',
        purpose='email_verification',
        requested_at='2026-09-06T12:00:00+00:00',
        expected_sender='security@example.test',
    )
    assert isinstance(req, dict)
    assert 'id' in req or 'request_id' in req
    req_id = req.get('id') or req.get('request_id')

    # Matching message: metadata correlation ONLY, returns {'message_id': 'm1'}
    matching_msg = {
        'id': 'm1',
        'recipient': 'candidate@example.test',
        'namespace': 'careers.example.test',
        'purpose': 'email_verification',
        'sender': 'security@example.test',
        'received_at': '2026-09-06T12:00:10+00:00',
        'code': 'SYNTHETIC_OTP',
    }
    match_result = s.match_mail(req_id, messages=[matching_msg])
    assert match_result == {'message_id': 'm1'}
    # No code or body persisted or returned
    assert 'code' not in match_result
    assert 'body' not in match_result

    # No matches returns None
    assert s.match_mail(req_id, messages=[]) is None

    # Ignore newest wrong recipient
    wrong_recipient = {
        **matching_msg,
        'id': 'm-wrong-recipient',
        'recipient': 'other@example.test',
        'received_at': '2026-09-06T12:00:20+00:00',
    }
    assert s.match_mail(req_id, messages=[wrong_recipient]) is None

    # Ignore newest wrong purpose
    wrong_purpose = {
        **matching_msg,
        'id': 'm-wrong-purpose',
        'purpose': 'password_reset',
        'received_at': '2026-09-06T12:00:20+00:00',
    }
    assert s.match_mail(req_id, messages=[wrong_purpose]) is None

    # Ignore newest wrong namespace
    wrong_namespace = {
        **matching_msg,
        'id': 'm-wrong-namespace',
        'namespace': 'other.example.test',
        'received_at': '2026-09-06T12:00:20+00:00',
    }
    assert s.match_mail(req_id, messages=[wrong_namespace]) is None

    # Ignore newest wrong sender
    wrong_sender = {
        **matching_msg,
        'id': 'm-wrong-sender',
        'sender': 'phishing@example.test',
        'received_at': '2026-09-06T12:00:20+00:00',
    }
    assert s.match_mail(req_id, messages=[wrong_sender]) is None

    # Ignore out-of-window (received before requested_at)
    out_of_window = {
        **matching_msg,
        'id': 'm-out-of-window',
        'received_at': '2026-09-06T11:59:50+00:00',
    }
    assert s.match_mail(req_id, messages=[out_of_window]) is None

    # Mixed list with wrong messages + one matching message returns the matching message
    mixed_messages = [wrong_recipient, wrong_purpose, wrong_namespace, wrong_sender, out_of_window, matching_msg]
    assert s.match_mail(req_id, messages=mixed_messages) == {'message_id': 'm1'}

    # Multiple matching messages -> ProtocolError ambiguous_mail, never guess newest
    second_matching = {
        'id': 'm2',
        'recipient': 'candidate@example.test',
        'namespace': 'careers.example.test',
        'purpose': 'email_verification',
        'sender': 'security@example.test',
        'received_at': '2026-09-06T12:00:15+00:00',
        'code': 'SYNTHETIC_OTP_2',
    }
    with pytest.raises(ProtocolError, match='ambiguous_mail'):
        s.match_mail(req_id, messages=[matching_msg, second_matching])
