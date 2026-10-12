"""Synthetic Rippling posting identities; no personal data or live applications."""
import pytest

from job_applier.managed_identity import application_match, is_same_application_scope, job_key

JOB = 'https://ats.rippling.com/en-US/synthetic/jobs/11111111-2222-4333-8444-555555555555'
FORM = JOB.replace('/en-US/', '/')


@pytest.mark.parametrize('locale', ['en-US', 'fr-CA', 'de-DE'])
@pytest.mark.parametrize('suffix', ['', '/apply', '?src=synthetic'])
def test_same_tenant_uuid_locale_transition_remains_owned(locale, suffix):
    posting = JOB.replace('en-US', locale) + suffix
    form = FORM + suffix
    assert is_same_application_scope(posting, form)
    assert is_same_application_scope(form, posting)
    assert application_match(posting, form) == {'status': 'same_job'}
    # Comparison equivalence does not rewrite stored intake/history keys.
    assert job_key(posting) != job_key(form)


@pytest.mark.parametrize('other', [
    FORM.replace('synthetic', 'other-tenant'),
    FORM.replace('555555555555', '666666666666'),
    FORM.replace('ats.rippling.com', 'other.example.test'),
    FORM.replace('/synthetic/', '/en-US/other-tenant/'),
    FORM + '?src=other',
    FORM + '?reset_token=synthetic',
    FORM.replace('/synthetic/', '/synthetic%2fother/'),
])
def test_locale_equivalence_does_not_merge_tenant_job_or_opaque_query(other):
    expected = JOB + '?src=synthetic' if '?src=other' in other else JOB
    assert not is_same_application_scope(expected, other)


def test_locale_prefix_on_unrecognized_host_remains_significant():
    assert not is_same_application_scope(JOB.replace('ats.rippling.com', 'jobs.example.test'),
                                         FORM.replace('ats.rippling.com', 'jobs.example.test'))
