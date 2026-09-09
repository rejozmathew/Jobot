"""Gemini-authored synthetic regressions, reviewed by the coordinator."""
import pytest
from job_applier.managed import Service
from job_applier.managed_identity import is_same_application_scope, same_job_url
from job_applier.managed_shared import ProtocolError


def test_scope_accepts_custom_employer_posting_to_detailed_and_form():
    posting_dup = "https://careers.example.test/jobs?gh_jid=12345&gh_jid=12345"
    posting_single = "https://careers.example.test/jobs?gh_jid=12345"
    detailed = "https://careers.example.test/jobs/sales/director/12345?gh_jid=12345"
    form = "https://careers.example.test/form?gh_jid=12345"

    assert is_same_application_scope(posting_dup, detailed) is True
    assert is_same_application_scope(posting_dup, form) is True
    assert is_same_application_scope(posting_single, detailed) is True
    assert is_same_application_scope(posting_single, form) is True
    assert is_same_application_scope(detailed, form) is True


def test_scope_rejects_conflicting_or_different_gh_jid():
    posting = "https://careers.example.test/jobs?gh_jid=12345"
    conflicting_posting = "https://careers.example.test/jobs?gh_jid=12345&gh_jid=67890"
    detailed = "https://careers.example.test/jobs/sales/director/12345?gh_jid=12345"
    conflicting_form = "https://careers.example.test/form?gh_jid=12345&gh_jid=67890"
    different_form = "https://careers.example.test/form?gh_jid=67890"
    missing_param_form = "https://careers.example.test/form"

    assert is_same_application_scope(conflicting_posting, detailed) is False
    assert is_same_application_scope(posting, conflicting_form) is False
    assert is_same_application_scope(posting, different_form) is False
    assert is_same_application_scope(posting, missing_param_form) is False


def test_scope_rejects_terminal_id_contradiction():
    posting = "https://careers.example.test/jobs?gh_jid=12345"
    contradicting_detailed = "https://careers.example.test/jobs/sales/director/99999?gh_jid=12345"
    form = "https://careers.example.test/form?gh_jid=12345"

    assert is_same_application_scope(posting, contradicting_detailed) is False
    assert is_same_application_scope(contradicting_detailed, form) is False


def test_scope_rejects_different_host_and_sensitive_urls():
    posting = "https://careers.example.test/jobs?gh_jid=12345"
    different_host_form = "https://other.example.test/form?gh_jid=12345"
    different_host_detailed = "https://other.example.test/jobs/sales/director/12345?gh_jid=12345"

    assert is_same_application_scope(posting, different_host_form) is False
    assert is_same_application_scope(posting, different_host_detailed) is False

    assert is_same_application_scope(posting, "https://careers.example.test/reset-password?gh_jid=12345") is False
    assert is_same_application_scope(posting, "https://careers.example.test/password-reset?gh_jid=12345") is False
    assert is_same_application_scope(posting, "https://careers.example.test/verify-email?gh_jid=12345") is False
    assert is_same_application_scope(posting, "https://careers.example.test/oauth/callback?gh_jid=12345") is False
    assert is_same_application_scope(posting, "https://careers.example.test/signin/callback?gh_jid=12345") is False

    assert is_same_application_scope(posting, "https://careers.example.test/form?gh_jid=12345&access_token=secret") is False
    assert is_same_application_scope(posting, "https://careers.example.test/form?gh_jid=12345&refresh_token=secret") is False
    assert is_same_application_scope(posting, "https://careers.example.test/form?gh_jid=12345&otp=123456") is False
    assert is_same_application_scope(posting, "https://careers.example.test/form?gh_jid=12345&password=secret") is False
    assert is_same_application_scope(posting, "https://careers.example.test/form?gh_jid=12345&reset_token=secret") is False
    assert is_same_application_scope(posting, "https://careers.example.test/form?gh_jid=12345&authorization_code=secret") is False


def test_scope_does_not_relax_unknown_opaque_query_parameters():
    posting_custom = "https://careers.example.test/jobs?custom_token=abc"
    form_custom = "https://careers.example.test/form?custom_token=abc"
    assert is_same_application_scope(posting_custom, form_custom) is False
    assert is_same_application_scope("https://careers.example.test/jobs?req=101", "https://careers.example.test/jobs?req=202") is False


def test_same_job_url_custom_employer_aliases():
    u_dup = "https://careers.example.test/jobs?gh_jid=12345&gh_jid=12345"
    u_single = "https://careers.example.test/jobs?gh_jid=12345"
    u_detailed = "https://careers.example.test/jobs/sales/director/12345?gh_jid=12345"
    u_form = "https://careers.example.test/form?gh_jid=12345"

    assert same_job_url(u_dup, u_detailed) is True
    assert same_job_url(u_detailed, u_dup) is True
    assert same_job_url(u_dup, u_form) is True
    assert same_job_url(u_form, u_dup) is True
    assert same_job_url(u_single, u_detailed) is True
    assert same_job_url(u_single, u_form) is True
    assert same_job_url(u_detailed, u_form) is True


def test_same_job_url_rejects_conflicting_different_and_invalid_aliases():
    u_valid = "https://careers.example.test/jobs?gh_jid=12345"
    u_conflicting_dup = "https://careers.example.test/jobs?gh_jid=12345&gh_jid=67890"
    u_diff_id = "https://careers.example.test/form?gh_jid=67890"
    u_contradicting_terminal = "https://careers.example.test/jobs/sales/director/99999?gh_jid=12345"
    u_missing_param = "https://careers.example.test/form"
    u_diff_host = "https://other.example.test/form?gh_jid=12345"

    assert same_job_url(u_conflicting_dup, u_valid) is False
    assert same_job_url(u_valid, u_conflicting_dup) is False
    assert same_job_url(u_valid, u_diff_id) is False
    assert same_job_url(u_valid, u_contradicting_terminal) is False
    assert same_job_url(u_valid, u_missing_param) is False
    assert same_job_url(u_valid, u_diff_host) is False

    assert same_job_url(u_valid, "https://careers.example.test/reset-password?gh_jid=12345") is False
    assert same_job_url(u_valid, "https://careers.example.test/form?gh_jid=12345&access_token=secret") is False
    assert same_job_url("https://careers.example.test/jobs?custom_token=abc", "https://careers.example.test/form?custom_token=abc") is False
    assert same_job_url("https://careers.example.test/jobs?custom_token=abc", "https://careers.example.test/jobs?custom_token=def") is False


def test_same_job_url_preserves_workday_behavior():
    w1 = "https://acme.myworkdayjobs.com/en-US/Careers/job/City/Director_R-12345"
    w1_case = "https://acme.myworkdayjobs.com/en-us/careers/job/city/director_r-12345"
    w2 = "https://acme.myworkdayjobs.com/en-US/Careers/job/City/Director_R-67890"

    assert same_job_url(w1, w1_case) is True
    assert same_job_url(w1, w2) is False
    assert is_same_application_scope(w1, "https://acme.myworkdayjobs.com/en-US/Careers/job/City/Director_R-12345/apply") is True
    assert is_same_application_scope(w1, "https://acme.myworkdayjobs.com/en-US/Careers/job/City/Director_R-67890/apply") is False


def test_greenhouse_spelling_equivalence_preserved():
    gh_board = "https://boards.greenhouse.io/acme/jobs/12345"
    gh_jobboard = "https://job-boards.greenhouse.io/acme/jobs/12345"
    gh_other = "https://job-boards.greenhouse.io/acme/jobs/67890"

    assert same_job_url(gh_board, gh_jobboard) is True
    assert same_job_url(gh_board, gh_other) is False
    assert is_same_application_scope(gh_board, gh_jobboard) is True
    assert is_same_application_scope(gh_board, "https://job-boards.greenhouse.io/acme/jobs/12345/apply") is True
    assert is_same_application_scope(gh_board, "https://job-boards.greenhouse.io/acme/jobs/67890/apply") is False


def test_service_intake_deduplicates_posting_and_form_aliases(tmp_path):
    db_path = tmp_path / "test_intake.db"
    service = Service.create(db_path, instance_id="fixture")

    posting = service.intake(
        url="https://careers.example.test/jobs?gh_jid=12345&gh_jid=12345",
        title="Director of Sales",
        company="Example Corp",
    )
    assert posting["id"]

    form = service.intake(
        url="https://careers.example.test/form?gh_jid=12345",
        company="Example Corp",
    )
    assert form["id"] == posting["id"], "Form URL must deduplicate to posting job ID"

    detailed = service.intake(
        url="https://careers.example.test/jobs/sales/director/12345?gh_jid=12345",
    )
    assert detailed["id"] == posting["id"], "Detailed route with matching ID must deduplicate to posting job ID"


def test_service_intake_distinct_hosts_and_requisitions_never_deduplicate(tmp_path):
    db_path = tmp_path / "test_distinct.db"
    service = Service.create(db_path, instance_id="fixture")

    job1 = service.intake(
        url="https://careers.example.test/jobs?gh_jid=12345",
        title="Role 1",
    )

    job_other_host = service.intake(
        url="https://other.example.test/jobs?gh_jid=12345",
        title="Role at other employer",
    )
    assert job_other_host["id"] != job1["id"], "Distinct employer hosts must not deduplicate"

    job_other_req = service.intake(
        url="https://careers.example.test/jobs?gh_jid=67890",
        title="Role 2",
    )
    assert job_other_req["id"] != job1["id"], "Distinct requisitions must not deduplicate"

    job_other_form = service.intake(
        url="https://careers.example.test/form?gh_jid=67890",
    )
    assert job_other_form["id"] == job_other_req["id"]
    assert job_other_form["id"] != job1["id"]


def test_service_intake_rejects_sensitive_urls_and_contradictions_without_deduplicating(tmp_path):
    db_path = tmp_path / "test_security.db"
    service = Service.create(db_path, instance_id="fixture")

    job = service.intake(url="https://careers.example.test/jobs?gh_jid=12345")

    with pytest.raises(ProtocolError):
        service.intake(url="https://careers.example.test/form?gh_jid=12345&access_token=secret_token")

    with pytest.raises(ProtocolError):
        service.intake(url="https://careers.example.test/reset-password?gh_jid=12345")

    with pytest.raises(ProtocolError):
        service.intake(url="https://careers.example.test/oauth/callback?gh_jid=12345")

    try:
        contradicting = service.intake(
            url="https://careers.example.test/jobs/sales/director/99999?gh_jid=12345"
        )
        assert contradicting["id"] != job["id"], "Contradicting terminal ID route must never deduplicate to job"
    except ProtocolError:
        pass

    try:
        conflicting = service.intake(
            url="https://careers.example.test/jobs?gh_jid=12345&gh_jid=67890"
        )
        assert conflicting["id"] != job["id"], "Conflicting duplicate gh_jid must never deduplicate to job"
    except ProtocolError:
        pass


def test_service_intake_greenhouse_and_workday_equivalence_deduplication(tmp_path):
    db_path = tmp_path / "test_standard_ats.db"
    service = Service.create(db_path, instance_id="fixture")

    gh1 = service.intake(url="https://boards.greenhouse.io/acme/jobs/12345")
    gh2 = service.intake(url="https://job-boards.greenhouse.io/acme/jobs/12345")
    assert gh1["id"] == gh2["id"], "Greenhouse boards.greenhouse.io and job-boards.greenhouse.io must deduplicate"

    w1 = service.intake(url="https://acme.myworkdayjobs.com/en-US/Careers/job/City/Role_R-100")
    w2 = service.intake(url="https://acme.myworkdayjobs.com/en-us/careers/job/city/role_r-100")
    assert w1["id"] == w2["id"], "Workday case variations must deduplicate in intake"

    w_other = service.intake(url="https://acme.myworkdayjobs.com/en-US/Careers/job/City/Role_R-200")
    assert w_other["id"] != w1["id"], "Distinct Workday requisitions must not deduplicate"


def test_confirmation_rejects_a_conflicting_query_requisition():
    from job_applier.managed_identity import is_post_submit_scope
    assert is_post_submit_scope('https://careers.example.test/form?gh_jid=12345',
        'https://careers.example.test/form/confirmation?gh_jid=12345')
    assert not is_post_submit_scope('https://careers.example.test/form?gh_jid=12345',
        'https://careers.example.test/form/confirmation?gh_jid=67890')


def test_readonly_history_recognizes_custom_embed_aliases(tmp_path):
    from job_applier.application_runtime import history_matches
    service=Service.create(tmp_path/'history.db',instance_id='fixture')
    job=service.intake(url='https://careers.example.test/jobs?gh_jid=12345')
    with service.tx() as db:db.execute("UPDATE jobs SET status='applied' WHERE id=?",(job['id'],))
    matches=history_matches([service.db_path],'https://careers.example.test/form?gh_jid=12345')
    assert len(matches)==1 and matches[0]['job_id']==job['id']
