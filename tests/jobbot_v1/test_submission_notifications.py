"""Notification fixtures never send Discord messages or mutate production history."""
import json
import subprocess
from datetime import datetime, timedelta, timezone

from test_local_sessions import setup, reserve, connect, own


def fixture(tmp_path):
    service, asset, jobs, _, config = setup(tmp_path)
    clock = [datetime(2026, 10, 1, tzinfo=timezone.utc)]
    service.now = lambda: clock[0].isoformat()
    config.update(spool_dir=str(tmp_path/'private'), submission_notifications={
        'target': 'discord:123456789', 'hermes_executable': 'fixture-hermes',
        'profile_home': str(tmp_path/'hermes')})
    with service.tx() as db:
        db.execute('UPDATE jobs SET company=?,title=? WHERE id=?',
                   ('Fixture Company', 'Software Engineer', jobs[0]['id']))
    return service, asset, jobs, config, clock


def complete(service, asset, jobs, *, outcome='applied', index=0):
    session = connect(service, reserve(service, asset, jobs, index=index))
    owner = own(service, session)
    if outcome == 'applied':
        service.submission_intent(**owner, evidence='Synthetic final control', fixture=True)
    result = service.finish(**owner, outcome=outcome, evidence='Synthetic employer confirmation')
    service.session_stopped(session['id'], reason='Synthetic browser stopped', browser_stopped=True)
    return result


def test_confirmed_submission_sends_company_and_role_once_across_restart(tmp_path):
    from job_applier.hermes_notifications import poll
    service, asset, jobs, config, clock = fixture(tmp_path)
    sent = []
    send = lambda cfg, text: sent.append(text) or {'message_id': 'message-1'}
    assert poll(config, service, sender=send)['initialized']
    complete(service, asset, jobs)
    assert poll(config, service, sender=send)['sent'] == 1
    assert sent == ['Application submitted\nCompany: Fixture Company\nRole: Software Engineer']
    from job_applier.managed import Service
    restarted = Service(service.db_path, instance_id=service.instance_id, now_fn=service.now)
    assert poll(config, restarted, sender=send)['sent'] == 0
    assert len(sent) == 1


def test_start_skips_history_and_only_confirmed_applied_is_alerted(tmp_path):
    from job_applier.hermes_notifications import poll
    service, asset, jobs, config, clock = fixture(tmp_path)
    complete(service, asset, jobs)
    sent = []
    send = lambda cfg, text: sent.append(text) or {}
    assert poll(config, service, sender=send)['initialized']
    assert poll(config, service, sender=send)['sent'] == 0
    complete(service, asset, jobs, index=1, outcome='already_applied')
    complete(service, asset, jobs, index=2, outcome='submission_unknown')
    assert poll(config, service, sender=send)['sent'] == 0
    assert sent == []


def test_delivery_failure_retries_after_restart_without_changing_success(tmp_path):
    from job_applier.hermes_notifications import poll
    service, asset, jobs, config, clock = fixture(tmp_path)
    poll(config, service)
    attempt = complete(service, asset, jobs)
    def fail(cfg, text):
        raise TimeoutError('private error text must not enter state')
    assert poll(config, service, sender=fail)['failed'] == 1
    assert service.attempt(attempt['id'])['outcome'] == 'applied'
    sent = []
    send = lambda cfg, text: sent.append(text) or {}
    assert poll(config, service, sender=send)['sent'] == 0
    clock[0] += timedelta(minutes=6)
    assert poll(config, service, sender=send)['sent'] == 1
    assert len(sent) == 1
    state = json.loads((tmp_path/'private/notifications/submissions.json').read_text())
    assert 'private error' not in json.dumps(state)


def test_disabled_notifications_do_not_consume_submissions(tmp_path):
    from job_applier.hermes_notifications import poll
    service, asset, jobs, config, clock = fixture(tmp_path)
    poll(config, service)
    complete(service, asset, jobs)
    disabled = dict(config, submission_notifications={})
    assert poll(disabled, service)['enabled'] is False
    assert poll(config, service, sender=lambda cfg, text: {})['sent'] == 1


def test_confirmed_manual_reconciliation_is_not_lost(tmp_path):
    from job_applier.hermes_notifications import poll
    service, asset, jobs, config, clock = fixture(tmp_path)
    poll(config, service)
    attempt = complete(service, asset, jobs, outcome='submission_unknown')
    assert poll(config, service, sender=lambda cfg, text: {})['sent'] == 0
    service.reconcile(attempt['id'], outcome='applied', evidence='Synthetic receipt', browser_quiescent=True)
    assert poll(config, service, sender=lambda cfg, text: {})['sent'] == 1


def test_hermes_sender_reuses_profile_and_stdin_with_no_model(monkeypatch):
    from job_applier.hermes_notifications import send_hermes
    seen = []
    def run(argv, **kwargs):
        seen.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, '{"success":true,"message_id":"sent-1"}', '')
    monkeypatch.setattr(subprocess, 'run', run)
    assert send_hermes({'hermes_executable':'hermes', 'profile_home':'/private/hermes',
                        'target':'discord:123'}, 'Application submitted')['message_id'] == 'sent-1'
    argv, kwargs = seen[0]
    assert argv == ['hermes','send','--to','discord:123','--file','-','--json']
    assert kwargs['input'] == 'Application submitted'
    assert kwargs['env']['HERMES_HOME'] == '/private/hermes'
    assert kwargs['timeout'] <= 30


def test_sender_requires_delivery_acknowledgement(monkeypatch):
    import pytest
    from job_applier.hermes_notifications import send_hermes
    for result in (subprocess.CompletedProcess([], 1, '', 'secret'),
                   subprocess.CompletedProcess([], 0, '{"success":false,"error":"secret"}', ''),
                   subprocess.CompletedProcess([], 0, 'not-json', '')):
        monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: result)
        with pytest.raises(RuntimeError) as exc:
            send_hermes({'target':'discord:123'}, 'Application submitted')
        assert 'secret' not in str(exc.value)


def test_external_titles_cannot_trigger_mentions_or_media(tmp_path):
    from job_applier.hermes_notifications import poll
    service, asset, jobs, config, clock = fixture(tmp_path)
    poll(config, service)
    with service.tx() as db:
        db.execute('UPDATE jobs SET company=?,title=? WHERE id=?',
                   ('@everyone', 'MEDIA:/private/file [[as_document]]', jobs[0]['id']))
    complete(service, asset, jobs)
    sent = []
    poll(config, service, sender=lambda cfg, text: sent.append(text) or {})
    assert '@everyone' not in sent[0] and 'MEDIA:' not in sent[0]
    assert '[[as_document]]' not in sent[0]


def test_one_delivery_failure_does_not_hold_other_confirmations(tmp_path):
    from job_applier.hermes_notifications import poll
    service, asset, jobs, config, clock = fixture(tmp_path)
    poll(config, service)
    complete(service, asset, jobs)
    complete(service, asset, jobs, index=1)
    calls = []
    def send(cfg, text):
        calls.append(text)
        if 'Fixture Company' in text:
            raise OSError('network unavailable')
        return {}
    assert poll(config, service, sender=send) == {
        'enabled': True, 'initialized': False, 'sent': 1, 'failed': 1}
    assert len(calls) == 2


def test_intent_failed_and_review_outcomes_do_not_generate_alerts(tmp_path):
    from job_applier.hermes_notifications import poll
    service, asset, jobs, config, clock = fixture(tmp_path)
    poll(config, service)
    session = connect(service, reserve(service, asset, jobs))
    service.submission_intent(**own(service, session), evidence='Synthetic final control', fixture=True)
    sent = []
    sender = lambda cfg, text: sent.append(text) or {}
    assert poll(config, service, sender=sender)['sent'] == 0
    complete(service, asset, jobs, index=1, outcome='failed')
    complete(service, asset, jobs, index=2, outcome='ready_for_review')
    assert poll(config, service, sender=sender)['sent'] == 0 and sent == []


def test_delivery_lock_prevents_parallel_pollers(tmp_path):
    import pytest
    from job_applier.hermes_notifications import poll
    from job_applier.workspace_process import FileLock
    from job_applier.managed_shared import ProtocolError
    service, asset, jobs, config, clock = fixture(tmp_path)
    poll(config, service)
    complete(service, asset, jobs)
    with FileLock(tmp_path/'private/notifications/submissions.lock'):
        with pytest.raises(ProtocolError, match='local_lock_busy'):
            poll(config, service, sender=lambda cfg, text: pytest.fail('Parallel send'))


def test_blank_company_and_role_use_explicit_fallbacks(tmp_path):
    from job_applier.hermes_notifications import poll
    service, asset, jobs, config, clock = fixture(tmp_path)
    poll(config, service)
    with service.tx() as db:
        db.execute('UPDATE jobs SET company=?,title=? WHERE id=?', ('  ', None, jobs[0]['id']))
    complete(service, asset, jobs)
    sent = []
    poll(config, service, sender=lambda cfg, text: sent.append(text) or {})
    assert sent == ['Application submitted\nCompany: Company unavailable\nRole: Role unavailable']
