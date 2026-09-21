"""Acceptance and contract tests for harvest handoff and intake_results publishing.

Contracts under test:
1) intake_results.py API:
   - publish(client, records, *, dry_run=False) -> dict with:
     - received (int: total input records count)
     - canonical_jobs (int: distinct canonical job rows created/referenced)
     - results (list: exactly one result item per input record)
     - failed (int: count of failed/invalid records)
   - Record allowed fields:
     url, company, title, location, verdict, source_type, source_id, namespace,
     requisition_id, identity_evidence
   - Explicit source_type and source_id required; missing/empty values fail validation.
   - Preserves identifiers exactly (source_id, requisition_id, namespace).
   - Validates required strings and official HTTP/HTTPS URL.
   - Strips/drops unknown fields (raw_email, password, mail_body, secret extras) BEFORE sending.
   - Never calls eligibility approval, request_run, accept_run, claim, or submission methods.
   - Uses real Service / create_app in-process operator Client.
   - Deduplicates tracking variants and aliases to real canonical rows.
   - Preserves applied suppression (existing applied jobs remain applied).
   - dry_run=True returns validated preview without writing to the database.
   - Invalid records produce sanitized error per item without dropping valid records.
   - Per-item invalid accounting accurately reflected in counts.

2) ats_probe.py API:
   - classify(html, url=None) evaluates offline HTML fixtures.
   - Never makes network calls or invokes get().
   - Classifies Greenhouse, Workday, WAF/Cloudflare challenge, and login barriers.

Missing staged files/modules are expected RED during test-only stage (Primary authors staged copies).
"""

from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
import re
from typing import Any
import pytest
import httpx
from fastapi.testclient import TestClient

from job_applier.managed import Service
from job_applier.managed_api import create_app
from job_applier.managed_client import Client

REPO_ROOT = Path(__file__).resolve().parents[2]
INTAKE_RESULTS_PATH = REPO_ROOT / "skills" / "job-posting-harvest" / "scripts" / "intake_results.py"
ATS_PROBE_PATH = REPO_ROOT / "skills" / "job-posting-harvest" / "scripts" / "ats_probe.py"

OPERATOR_TOKEN = "synthetic-operator-harvest-token-32chars"
WORKER_TOKEN = "synthetic-worker-harvest-token-32chars"
WORKER_ID = "harvest-worker-1"
BASE_URL = "http://127.0.0.1:8769"

ALLOWED_RECORD_FIELDS = frozenset({
    "url",
    "company",
    "title",
    "location",
    "verdict",
    "source_type",
    "source_id",
    "namespace",
    "requisition_id",
    "identity_evidence",
    "country",
    "posted_at",
})


# ---------------------------------------------------------------------------
# Module Loaders (Expected RED if missing)
# ---------------------------------------------------------------------------


def get_intake_results_module():
    """Load intake_results staged script or fail with clear RED notice."""
    assert INTAKE_RESULTS_PATH.is_file(), (
        f"Staged script not found: {INTAKE_RESULTS_PATH.relative_to(REPO_ROOT)} "
        "(expected RED in test-only stage; Primary owns authoring staged copies)"
    )
    spec = importlib.util.spec_from_file_location("staged_intake_results", INTAKE_RESULTS_PATH)
    assert spec and spec.loader, f"Cannot create module spec for {INTAKE_RESULTS_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_ats_probe_module():
    """Load ats_probe staged script or fail with clear RED notice."""
    assert ATS_PROBE_PATH.is_file(), (
        f"Staged script not found: {ATS_PROBE_PATH.relative_to(REPO_ROOT)} "
        "(expected RED in test-only stage; Primary owns authoring staged copies)"
    )
    spec = importlib.util.spec_from_file_location("staged_ats_probe", ATS_PROBE_PATH)
    assert spec and spec.loader, f"Cannot create module spec for {ATS_PROBE_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Network Guard (Zero External Network Calls Allowed)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def forbid_external_network(monkeypatch: pytest.MonkeyPatch):
    """Ensure tests and helpers never make outbound network calls to real ATS or web."""
    import socket

    orig_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise RuntimeError(f"External network connection forbidden in offline tests: {address}")
        return orig_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


# ---------------------------------------------------------------------------
# Real In-Process Service & Client Fixture with Call Spy
# ---------------------------------------------------------------------------


class ClientCallSpy:
    """Wraps Client.call to record operations and payloads sent to JobBot API."""

    def __init__(self, client: Client):
        self.client = client
        self.orig_call = client.call
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, operation: str, **kwargs):
        self.calls.append((operation, dict(kwargs)))
        return self.orig_call(operation, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self.client, name)


@pytest.fixture
def managed_env(tmp_path: Path):
    """Initializes a real Service, create_app, and in-process operator Client."""
    db_path = tmp_path / "harvest_managed.db"
    service = Service.create(
        db_path,
        instance_id="synthetic-harvest-instance",
        settings={"mode": "development", "submission_mode": "review"},
    )
    app = create_app(
        service,
        operator_token=OPERATOR_TOKEN,
        worker_tokens={WORKER_TOKEN: WORKER_ID},
    )
    test_client = TestClient(app, base_url=BASE_URL)

    class InProcessTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            result = test_client.request(
                request.method,
                request.url.path,
                headers=dict(request.headers),
                content=request.content,
            )
            return httpx.Response(
                result.status_code,
                headers=result.headers,
                content=result.content,
            )

    client = Client(
        base_url=BASE_URL,
        instance_id=service.instance_id,
        token=OPERATOR_TOKEN,
        transport=InProcessTransport(),
    )
    spy = ClientCallSpy(client)
    yield service, spy
    client.close()


# ---------------------------------------------------------------------------
# HTML Fixtures for ats_probe (No Network Calls)
# ---------------------------------------------------------------------------

GREENHOUSE_FIXTURE_HTML = """<!DOCTYPE html>
<html>
<head><title>Staff Data Engineer - Acme Corp</title></head>
<body>
  <div id="wrapper">
    <div id="application_form" class="greenhouse-form">
      <h1>Acme Careers</h1>
      <form id="apply_app" action="https://boards.greenhouse.io/acmecorp/jobs/55443322/apply" method="post">
        <input type="text" name="first_name" id="first_name" />
        <input type="text" name="last_name" id="last_name" />
        <input type="email" name="email" id="email" />
        <button type="submit" id="submit_app">Submit Application</button>
      </form>
    </div>
  </div>
</body>
</html>"""

WORKDAY_FIXTURE_HTML = """<!DOCTYPE html>
<html>
<head><title>Director of Analytics - Global Corp</title></head>
<a href="https://fixture.wd1.myworkdayjobs.com/External">Official board</a>
<body>
  <div class="wd-LoadingPanel"></div>
  <div data-automation-id="workdayApplication">
    <div data-automation-id="pageFooter">
      <button data-automation-id="pageFooterNextButton">Next</button>
    </div>
  </div>
</body>
</html>"""

WAF_CHALLENGE_FIXTURE_HTML = """<!DOCTYPE html>
<html>
<head><title>Just a moment...</title></head>
<body>
  <div class="cf-challenge">
    <span>Verify you are human to continue</span>
    <div id="cf-turnstile"></div>
  </div>
</body>
</html>"""

LOGIN_WALL_FIXTURE_HTML = """<!DOCTYPE html>
<html>
<head><title>Sign In - Careers Portal</title></head>
<body>
  <form id="login-form">
    <h2>Sign In to Apply for this Position</h2>
    <input type="text" name="username" placeholder="Email" />
    <input type="password" name="password" placeholder="Password" />
    <button type="submit">Sign In</button>
  </form>
</body>
</html>"""

GENERIC_PAGE_FIXTURE_HTML = """<!DOCTYPE html>
<html>
<head><title>Engineering Blog - Life at Acme</title></head>
<body>
  <article>
    <h1>Building Scalable Pipelines</h1>
    <p>Read about our latest technology stack updates and team culture.</p>
  </article>
</body>
</html>"""


# ---------------------------------------------------------------------------
# intake_results.py Contract Tests
# ---------------------------------------------------------------------------


def test_intake_results_module_and_publish_signature() -> None:
    """intake_results.py must export publish(client, records, *, dry_run=False)."""
    mod = get_intake_results_module()
    assert hasattr(mod, "publish"), "intake_results module must define a publish() function"
    publish_fn = getattr(mod, "publish")
    assert callable(publish_fn), "publish must be callable"

    sig = inspect.signature(publish_fn)
    params = list(sig.parameters.values())
    assert len(params) >= 2, f"publish must accept at least client and records, got {sig}"
    assert params[0].name == "client", f"First param must be 'client', got {params[0].name}"
    assert params[1].name == "records", f"Second param must be 'records', got {params[1].name}"
    assert "dry_run" in sig.parameters, "publish must accept 'dry_run' keyword argument"
    assert sig.parameters["dry_run"].default is False, "dry_run must default to False"


def test_discovery_retains_country_and_posting_date(managed_env):
    service, spy = managed_env
    mod = get_intake_results_module()
    record = {'url': 'https://employer.example.test/dates/1', 'source_type': 'harvest',
              'source_id': 'dates-1', 'country': 'US', 'posted_at': '2026-09-10'}
    initial = mod.publish(spy, [{k:v for k,v in record.items() if k not in ('country','posted_at')}])
    result = mod.publish(spy, [record])
    assert result['results'][0]['job_id'] == initial['results'][0]['job_id']
    job = service.job(result['results'][0]['job_id'])
    metadata = json.loads(job['metadata_json'])
    assert metadata['country'] == 'US' and metadata['posted_at'] == '2026-09-10'


def test_publish_happy_path_all_allowed_fields_and_preserved_ids(managed_env) -> None:
    """publish ingests records with all allowed fields, preserving identifiers exactly."""
    service, spy = managed_env
    mod = get_intake_results_module()

    records = [
        {
            "url": "https://careers.example.test/jobs/gh-101",
            "company": "Acme Corp",
            "title": "Principal Data Architect",
            "location": "Remote - US",
            "verdict": "supported",
            "source_type": "harvest",
            "source_id": "gh_job_101",
            "namespace": "acme:greenhouse",
            "requisition_id": "REQ-101",
            "identity_evidence": "official_job_metadata",
        },
        {
            "url": "https://careers.example.test/jobs/wd-202",
            "company": "Beta Tech",
            "title": "Director of Machine Learning",
            "location": "Chicago, IL",
            "verdict": "supported",
            "source_type": "harvest",
            "source_id": "wd_job_202",
            "namespace": "beta:workday",
            "requisition_id": "REQ-202",
            "identity_evidence": "official_job_metadata",
        },
    ]

    out = mod.publish(spy, records, dry_run=False)

    # 1. Output structure contract
    assert isinstance(out, dict), "publish must return a dictionary"
    assert out.get("received") == 2, f"Expected received=2, got {out.get('received')}"
    assert out.get("canonical_jobs") == 2, f"Expected canonical_jobs=2, got {out.get('canonical_jobs')}"
    assert out.get("failed") == 0, f"Expected failed=0, got {out.get('failed')}"
    results = out.get("results")
    assert isinstance(results, list) and len(results) == 2, f"Expected 2 results, got {results}"

    # 2. Results per-record
    for res in results:
        assert res.get("status") in ("ok", "success", "intaked", "queued"), f"Unexpected result status: {res}"
        assert res.get("job_id"), f"Result missing job_id: {res}"

    # 3. Database persistence & exact identifier preservation
    with service.tx() as db:
        jobs = db.execute("SELECT * FROM jobs ORDER BY id").fetchall()
        assert len(jobs) == 2

        sources = db.execute("SELECT * FROM job_sources ORDER BY source_id").fetchall()
        assert len(sources) == 2
        source_ids = {s["source_id"] for s in sources}
        assert source_ids == {"gh_job_101", "wd_job_202"}, "Source IDs must be preserved exactly"

        req_ids = {j["requisition_id"] for j in jobs}
        assert req_ids == {"REQ-101", "REQ-202"}, "Requisition IDs must be preserved exactly"


def test_publish_explicit_source_type_and_source_id_required(managed_env) -> None:
    """Missing or empty source_type or source_id must be rejected as invalid record."""
    service, spy = managed_env
    mod = get_intake_results_module()

    records = [
        {
            "url": "https://careers.example.test/jobs/missing-source-type",
            "company": "Acme",
            "title": "Engineer",
            "source_id": "src-1",
            # source_type missing
        },
        {
            "url": "https://careers.example.test/jobs/empty-source-id",
            "company": "Acme",
            "title": "Engineer",
            "source_type": "harvest",
            "source_id": "",  # empty source_id
        },
        {
            "url": "https://careers.example.test/jobs/valid-record",
            "company": "Acme",
            "title": "Engineer",
            "source_type": "harvest",
            "source_id": "src-3",
        },
    ]

    out = mod.publish(spy, records, dry_run=False)

    assert out["received"] == 3
    assert out["failed"] == 2
    assert out["canonical_jobs"] == 1
    assert len(out["results"]) == 3

    assert out["results"][0]["status"] in ("error", "failed", "invalid")
    assert "source_type" in out["results"][0].get("error", "").lower()

    assert out["results"][1]["status"] in ("error", "failed", "invalid")
    assert "source_id" in out["results"][1].get("error", "").lower()

    assert out["results"][2]["status"] in ("ok", "success", "intaked", "queued")


def test_publish_validates_official_url_and_required_strings(managed_env) -> None:
    """publish validates that url is a valid HTTP/HTTPS URL and required strings are valid."""
    service, spy = managed_env
    mod = get_intake_results_module()

    invalid_records = [
        {
            "url": "javascript:alert(1)",
            "source_type": "harvest",
            "source_id": "inv-1",
        },
        {
            "url": "not-a-valid-url",
            "source_type": "harvest",
            "source_id": "inv-2",
        },
        {
            "url": "",
            "source_type": "harvest",
            "source_id": "inv-3",
        },
    ]

    out = mod.publish(spy, invalid_records, dry_run=False)

    assert out["received"] == 3
    assert out["failed"] == 3
    assert out["canonical_jobs"] == 0
    assert len(out["results"]) == 3

    for item in out["results"]:
        assert item["status"] in ("error", "failed", "invalid")
        assert "url" in item.get("error", "").lower()


def test_publish_strips_unknown_fields_before_sending(managed_env) -> None:
    """Unknown/secret fields (raw_email, password, mail_body) must be stripped BEFORE calling client."""
    service, spy = managed_env
    mod = get_intake_results_module()

    records = [
        {
            "url": "https://careers.example.test/jobs/sensitive-fields",
            "company": "Acme",
            "title": "Engineer",
            "source_type": "harvest",
            "source_id": "src-sens",
            # Secret / unallowed fields to be stripped:
            "raw_email": "candidate@example.test",
            "password": "SuperSecretPassword123!",
            "mail_body": "Subject: Job Alert\nBody content...",
            "session_token": "tok_xyz_secret",
            "internal_debug": {"raw_headers": ["Authorization: Bearer test"]},
        }
    ]

    out = mod.publish(spy, records, dry_run=False)

    assert out["failed"] == 0
    assert out["canonical_jobs"] == 1

    # Verify spy intercepted calls: NO stripped fields sent over client.call
    assert len(spy.calls) > 0
    for op, kwargs in spy.calls:
        if op == "intake":
            for disallowed in ("raw_email", "password", "mail_body", "session_token", "internal_debug"):
                assert disallowed not in kwargs, f"Disallowed field '{disallowed}' was not stripped before calling client"
            # Assert only allowed fields are present
            for k in kwargs:
                assert k in ALLOWED_RECORD_FIELDS, f"Unexpected unallowed field '{k}' sent to intake"


def test_publish_no_eligibility_approval_or_run_submission_calls(managed_env) -> None:
    """publish must NEVER call eligibility, request_run, accept_run, claim, or submission methods."""
    service, spy = managed_env
    mod = get_intake_results_module()

    records = [
        {
            "url": "https://careers.example.test/jobs/safe-intake",
            "company": "Acme",
            "title": "Engineer",
            "source_type": "harvest",
            "source_id": "src-safe",
        }
    ]

    mod.publish(spy, records, dry_run=False)

    forbidden_ops = {
        "eligibility",
        "request_run",
        "accept_run",
        "claim",
        "submission_intent",
        "finish",
        "control",
        "action_start",
        "action_end",
    }

    called_ops = [op for op, _ in spy.calls]
    for op in called_ops:
        assert op not in forbidden_ops, f"publish called forbidden operation: '{op}'"

    # In DB: eligibility remains 'held' (review-only, no auto-apply)
    with service.tx() as db:
        job = db.execute("SELECT * FROM jobs WHERE url LIKE '%safe-intake%'").fetchone()
        assert job is not None
        assert job["eligibility"] == "held", "New intake job must remain in held eligibility"
        assert job["status"] == "queued", "New intake job status must be queued, not running or applied"


def test_publish_dedupes_aliases_and_duplicates(managed_env) -> None:
    """Duplicate tracking URLs dedupe into a single canonical row with multiple sources."""
    service, spy = managed_env
    mod = get_intake_results_module()

    records = [
        {
            "url": "https://careers.example.test/jobs/role-99?utm_source=linkedin&utm_medium=feed",
            "company": "Acme",
            "title": "Data Architect",
            "source_type": "harvest",
            "source_id": "feed-99",
        },
        {
            "url": "https://careers.example.test/jobs/role-99?utm_source=email_alert&rx_campaign=99",
            "company": "Acme",
            "title": "Data Architect",
            "source_type": "harvest",
            "source_id": "alert-99",
        },
    ]

    out = mod.publish(spy, records, dry_run=False)

    assert out["received"] == 2
    assert out["canonical_jobs"] == 1, "Repeated canonical URL must dedupe to 1 canonical job"
    assert out["failed"] == 0
    assert len(out["results"]) == 2

    # Database state: 1 job row, 2 source rows
    with service.tx() as db:
        jobs = db.execute("SELECT * FROM jobs").fetchall()
        assert len(jobs) == 1

        sources = db.execute("SELECT * FROM job_sources WHERE job_id=?", (jobs[0]["id"],)).fetchall()
        assert len(sources) == 2
        source_ids = {s["source_id"] for s in sources}
        assert source_ids == {"feed-99", "alert-99"}


def test_publish_preserves_applied_suppression(managed_env) -> None:
    """Ingesting an already applied job URL preserves applied status and suppression."""
    service, spy = managed_env
    mod = get_intake_results_module()

    applied_url = "https://careers.example.test/jobs/already-applied-role"
    # Pre-populate DB with applied job
    prior_job = service.intake(
        url=applied_url,
        source_type="manual",
        source_id="prior-1",
        company="Acme",
    )
    with service.tx() as db:
        db.execute("UPDATE jobs SET status='applied' WHERE id=?", (prior_job["id"],))

    records = [
        {
            "url": applied_url,
            "company": "Acme",
            "title": "Engineer",
            "source_type": "harvest",
            "source_id": "harvest-dup",
        }
    ]

    out = mod.publish(spy, records, dry_run=False)

    assert out["received"] == 1
    assert out["failed"] == 0

    # Job status must remain 'applied' (never downgraded to queued or re-applied)
    with service.tx() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (prior_job["id"],)).fetchone()
        assert job["status"] == "applied", "Already-applied job status must not be modified"


def test_publish_dry_run_returns_preview_without_writes(managed_env) -> None:
    """dry_run=True returns validated preview dict without mutating the database."""
    service, spy = managed_env
    mod = get_intake_results_module()

    records = [
        {
            "url": "https://careers.example.test/jobs/dryrun-1",
            "company": "Acme",
            "title": "ML Engineer",
            "source_type": "harvest",
            "source_id": "dry-1",
        },
        {
            "url": "https://careers.example.test/jobs/dryrun-2",
            "company": "Beta",
            "title": "Data Scientist",
            "source_type": "harvest",
            "source_id": "dry-2",
        },
    ]

    with service.tx() as db:
        jobs_before = db.execute("SELECT count(*) FROM jobs").fetchone()[0]
        sources_before = db.execute("SELECT count(*) FROM job_sources").fetchone()[0]

    out = mod.publish(spy, records, dry_run=True)

    # Output structure
    assert out["received"] == 2
    assert out["failed"] == 0
    assert out["canonical_jobs"] == 2
    assert len(out["results"]) == 2
    for r in out["results"]:
        assert r.get("dry_run") is True or r.get("status") in ("preview", "valid", "ok")

    # DB unchanged
    with service.tx() as db:
        jobs_after = db.execute("SELECT count(*) FROM jobs").fetchone()[0]
        sources_after = db.execute("SELECT count(*) FROM job_sources").fetchone()[0]

    assert jobs_before == jobs_after == 0, "dry_run must not insert any rows into jobs"
    assert sources_before == sources_after == 0, "dry_run must not insert any rows into job_sources"


def test_publish_invalid_record_sanitized_error_per_item_accounting(managed_env) -> None:
    """An invalid record produces a sanitized error for that item without dropping valid records."""
    service, spy = managed_env
    mod = get_intake_results_module()

    records = [
        {
            "url": "https://careers.example.test/jobs/valid-item-1",
            "company": "Acme",
            "title": "Valid One",
            "source_type": "harvest",
            "source_id": "val-1",
        },
        {
            "url": "https://careers.example.test/jobs/invalid-secret",
            "company": "Acme",
            "source_type": "",  # invalid: empty source_type
            "source_id": "",    # invalid: empty source_id
            "leaked_secret": "SENSITIVE_SECRET_TOKEN_DO_NOT_LOG",
        },
        {
            "url": "https://careers.example.test/jobs/valid-item-2",
            "company": "Acme",
            "title": "Valid Two",
            "source_type": "harvest",
            "source_id": "val-2",
        },
    ]

    out = mod.publish(spy, records, dry_run=False)

    assert out["received"] == 3
    assert out["failed"] == 1
    assert out["canonical_jobs"] == 2
    assert len(out["results"]) == 3

    # Item 0: valid
    assert out["results"][0]["status"] in ("ok", "success", "intaked", "queued")

    # Item 1: invalid, sanitized error (no leaked_secret in error string)
    err_res = out["results"][1]
    assert err_res["status"] in ("error", "failed", "invalid")
    err_msg = str(err_res.get("error", ""))
    assert "SENSITIVE_SECRET_TOKEN_DO_NOT_LOG" not in err_msg, "Error message must be sanitized"

    # Item 2: valid, not dropped by previous failure
    assert out["results"][2]["status"] in ("ok", "success", "intaked", "queued")

    # Verify DB has exactly the 2 valid jobs
    with service.tx() as db:
        jobs = db.execute("SELECT * FROM jobs").fetchall()
        assert len(jobs) == 2


# ---------------------------------------------------------------------------
# ats_probe.py Contract Tests (Offline HTML Fixtures Only)
# ---------------------------------------------------------------------------


def test_ats_probe_module_and_classify_signature() -> None:
    """ats_probe.py must export classify(html, ...) and never call get()."""
    mod = get_ats_probe_module()
    assert hasattr(mod, "classify"), "ats_probe must define classify() function"
    classify_fn = getattr(mod, "classify")
    assert callable(classify_fn), "classify must be callable"

    sig = inspect.signature(classify_fn)
    params = list(sig.parameters.values())
    assert len(params) >= 1, f"classify must accept at least HTML string/tree, got {sig}"


@pytest.mark.parametrize(
    ("fixture_html", "expected_token"),
    [
        (GREENHOUSE_FIXTURE_HTML, "greenhouse"),
        (WORKDAY_FIXTURE_HTML, "workday"),
        (WAF_CHALLENGE_FIXTURE_HTML, "waf"),
        (LOGIN_WALL_FIXTURE_HTML, "login"),
        (GENERIC_PAGE_FIXTURE_HTML, "generic"),
    ],
    ids=["greenhouse", "workday", "waf_challenge", "login_wall", "generic_page"],
)
def test_ats_probe_classify_fixtures_never_calls_get(
    monkeypatch: pytest.MonkeyPatch, fixture_html: str, expected_token: str
) -> None:
    """ats_probe.classify() must classify offline HTML fixtures without making HTTP requests."""
    mod = get_ats_probe_module()

    # Poison any get() or HTTP method on mod or urllib/requests/httpx
    if hasattr(mod, "get"):
        monkeypatch.setattr(mod, "get", lambda *args, **kwargs: pytest.fail("ats_probe.get() must NEVER be called"))

    import urllib.request
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("urllib.request.urlopen forbidden during classify()"),
    )

    result = mod.classify(fixture_html)

    # Preserve the inspected existing classifier contract, not an invented new
    # WAF/login classifier. Barriers without an ATS fingerprint remain unknown.
    ats, workday_candidates, greenhouse_candidates = result
    if expected_token in ('waf', 'login', 'generic'):
        assert ats == set()
        assert workday_candidates == greenhouse_candidates == []
    else:
        assert expected_token in ats
