"""Candidate Home is a same-site read-only confirmation surface, not another job."""
from job_applier import managed_identity as identity

JOB='https://tenant.wd1.myworkdayjobs.com/en-US/Jobs/job/City/Role_R1'


def test_candidate_home_is_read_scope_only():
    assert hasattr(identity,'is_workday_candidate_home')
    assert identity.is_workday_candidate_home(JOB,'https://tenant.wd1.myworkdayjobs.com/en-US/Jobs/candidateHome')
    assert not identity.is_same_application_scope(JOB,'https://tenant.wd1.myworkdayjobs.com/en-US/Jobs/candidateHome')


def test_other_site_host_and_sensitive_redirect_not_confirmation_scope():
    assert hasattr(identity,'is_workday_candidate_home')
    for url in ['https://tenant.wd1.myworkdayjobs.com/en-US/Other/candidateHome',
                'https://other.wd1.myworkdayjobs.com/en-US/Jobs/candidateHome',
                'https://tenant.wd1.myworkdayjobs.com/en-US/Jobs/candidateHome?access_token=secret']:
        assert not identity.is_workday_candidate_home(JOB,url)
