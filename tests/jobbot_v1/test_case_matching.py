"""Case changes must not change Workday scope or candidate email identity."""
from job_applier.application_runtime import history_key
from job_applier.managed_identity import is_workday_candidate_home
from job_applier.managed_hermes_worker import confirmation_verified
from test_accounts import new_service

JOB = 'https://tenant.wd1.myworkdayjobs.com/en-US/Careers/job/City/Director_R123'


def test_workday_history_and_confirmation_ignore_case():
    assert history_key(JOB) == history_key(JOB.upper())
    assert is_workday_candidate_home(JOB, 'https://TENANT.wd1.myworkdayjobs.com/CAREERS/CANDIDATEHOME')
    assert confirmation_verified(JOB, JOB.upper() + '/CONFIRMATION', 'Application submitted')
    assert not confirmation_verified(JOB, JOB.replace('R123', 'R124'), 'Application submitted')


def test_case_changes_reuse_candidate_and_match_mail(tmp_path):
    s = new_service(tmp_path)
    imported = s.import_profile({'identity': {'email': 'Candidate@EXAMPLE.TEST'}}, identity_id='candidate')
    assert imported['identity_id'] == 'candidate'
    req = s.mail_request(identity_id='candidate', namespace='tenant.wd1.myworkdayjobs.com/Careers',
        purpose='email_verification', requested_at='2026-09-08T12:00:00+00:00', expected_sender='Hiring@Example.Test')
    message = dict(id='mail-1', recipient='CANDIDATE@example.test', sender='hiring@example.test',
        namespace='TENANT.wd1.myworkdayjobs.com/CAREERS', purpose='email_verification', received_at='2026-09-08T12:01:00+00:00')
    assert s.match_mail(req['id'], messages=[message]) == {'message_id': 'mail-1'}
    message['recipient'] = 'someone-else@example.test'
    assert s.match_mail(req['id'], messages=[message]) is None


def test_case_changes_reuse_job_and_account(tmp_path):
    s = new_service(tmp_path)
    job = s.intake(url=JOB)
    assert s.intake(url=JOB.upper())['id'] == job['id']
    s.account_update(namespace='tenant.wd1.myworkdayjobs.com/Careers', identity_id='candidate',
        state='confirmed', credential_ref='vault:fixture', request_id='account-1', evidence='Synthetic confirmation')
    assert s.account_strategy(namespace='TENANT.WD1.MYWORKDAYJOBS.COM/CAREERS', identity_id='candidate')['action'] == 'sign_in'
