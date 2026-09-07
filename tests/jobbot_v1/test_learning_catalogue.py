"""Offline tests for learning catalogue and verified browser helpers.

Covers:
1. lesson_observe creates candidate lessons with flexible scopes; default kind='procedure' vs candidate_fact.
2. lesson_set_status lifecycle (active/demoted/retired); candidate_fact cannot become active procedural lessons.
3. lessons_for_context filters active procedures by scope, isolates company/namespace, and caps limit <= 5.
4. lesson_record_outcome appends verification/failure history without mutating facts or policy.
5. helper_register creates immutable candidates referencing real tmp_path files with valid sha256; no code execution; duplicate differing content rejected.
6. helper_activate requires nonempty evidence and browser lease quiescence; helpers_for_context invalidates tampered files; persistence across fresh Service; unsupported policy mutations rejected.
"""
import hashlib
from pathlib import Path
import pytest

from job_applier.managed import Service, ProtocolError


@pytest.fixture
def service(tmp_path):
    db_path = tmp_path / "learning_test.db"
    s=Service.create(db_path, instance_id="test-learning-instance")
    # Supporting references must point to actual synthetic history, not invented IDs.
    from job_applier.database import DatabaseManager, ApplicationAttempt
    from datetime import datetime
    job=s.intake(url='https://history.example.test/synthetic',source_id='fixture-history')
    manager=DatabaseManager(str(db_path))
    ids=[101,102,103,104,105,201,202,301,302,303,*range(310,316),401,402,403,404,405]
    with manager.get_session() as db:
        for aid in ids:
            db.add(ApplicationAttempt(id=aid,job_id=job['id'],platform='fixture',workflow='synthetic_history',started_at=datetime(2026,1,1),completed_at=datetime(2026,1,1),outcome='blocked',evidence='Synthetic history fixture'))
        db.commit()
    manager.close()
    return s


@pytest.fixture
def sample_py_helper(tmp_path):
    helper_dir = tmp_path / "helpers"
    helper_dir.mkdir(parents=True, exist_ok=True)
    p = helper_dir / "workday_dropdown.py"
    content = "# Synthetic helper - no execution\ndef select_option(page, selector, value):\n    return True\n"
    p.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    return {"path": str(p), "sha256": digest, "file": p, "content": content}


@pytest.fixture
def sample_js_helper(tmp_path):
    helper_dir = tmp_path / "helpers"
    helper_dir.mkdir(parents=True, exist_ok=True)
    p = helper_dir / "scroll_helper.js"
    content = "// Synthetic helper - no execution\nfunction scrollIntoView(selector) { return true; }\n"
    p.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    return {"path": str(p), "sha256": digest, "file": p, "content": content}


@pytest.fixture
def with_browser_lease(service):
    def _set_lease(profile="synthetic-browser", state="active"):
        with service.tx() as db:
            db.execute(
                "INSERT INTO browser_leases (profile, attempt_id, worker_id, generation, expires_at, state) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(profile) DO UPDATE SET state=excluded.state, expires_at=excluded.expires_at",
                (profile, None, "synthetic-worker", 1, "2099-01-01T00:00:00+00:00", state),
            )
    return _set_lease


def test_lesson_observe_creates_candidate_with_flexible_scope(service):
    """lesson_observe creates candidates with flexible scopes (platform/namespace optional); kind='procedure' default."""
    # Scope with platform only
    c1 = service.lesson_observe(
        condition="input loses focus prematurely",
        action="re-focus before typing",
        scope={"platform": "workday"},
        expected_result="value typed successfully",
        attempt_ids=[101],
    )
    assert c1["status"] == "candidate"
    assert c1.get("kind", "procedure") == "procedure"
    assert c1["scope"] == {"platform": "workday"}

    # Scope with namespace only
    c2 = service.lesson_observe(
        condition="login banner covers submit",
        action="dismiss banner",
        scope={"namespace": "tenant_alpha"},
        expected_result="button clickable",
        attempt_ids=[102],
    )
    assert c2["status"] == "candidate"
    assert c2["scope"] == {"namespace": "tenant_alpha"}

    # Scope with both platform and namespace
    c3 = service.lesson_observe(
        condition="custom modal blocks iframe",
        action="close modal",
        scope={"platform": "greenhouse", "namespace": "tenant_beta"},
        expected_result="iframe accessible",
        attempt_ids=[103],
    )
    assert c3["status"] == "candidate"
    assert c3["scope"] == {"platform": "greenhouse", "namespace": "tenant_beta"}

    # Scope omitting both (global/empty)
    c4 = service.lesson_observe(
        condition="network spinner displayed",
        action="wait for spinner to disappear",
        scope={},
        expected_result="page interactive",
        attempt_ids=[104],
        kind="procedure",
    )
    assert c4["status"] == "candidate"
    assert c4["scope"] == {}

    # Candidate fact
    c5 = service.lesson_observe(
        condition="requires ssn field",
        action="fill ssn fact",
        scope={"platform": "workday"},
        expected_result="validation passed",
        attempt_ids=[105],
        kind="candidate_fact",
    )
    assert c5["status"] == "candidate"
    assert c5["kind"] == "candidate_fact"

    # None of these candidates should appear in active lessons_for_context
    assert service.lessons_for_context(platform="workday", namespace="tenant_alpha") == []


def test_lesson_status_lifecycle_and_candidate_fact_cannot_become_active_procedure(service):
    """lesson_set_status supports active/demoted/retired; candidate_fact cannot become active procedure."""
    cand = service.lesson_observe(
        condition="stale button reference",
        action="re-query element",
        scope={"platform": "workday", "namespace": "tenant_gamma"},
        expected_result="click succeeds",
        attempt_ids=[201],
        kind="procedure",
    )
    lesson_id = cand["id"]

    # Transition to active
    active = service.lesson_set_status(lesson_id, status="active", reason="verified in test run")
    assert active["status"] == "active"
    matched = service.lessons_for_context(platform="workday", namespace="tenant_gamma")
    assert any(item["id"] == lesson_id for item in matched)

    # Transition to demoted
    demoted = service.lesson_set_status(lesson_id, status="demoted", reason="flaky in latest run")
    assert demoted["status"] == "demoted"
    assert not any(item["id"] == lesson_id for item in service.lessons_for_context(platform="workday", namespace="tenant_gamma"))

    # Transition to retired
    retired = service.lesson_set_status(lesson_id, status="retired", reason="obsoleted by DOM update")
    assert retired["status"] == "retired"
    assert not any(item["id"] == lesson_id for item in service.lessons_for_context(platform="workday", namespace="tenant_gamma"))

    # Candidate fact MUST NOT become active procedural lesson
    fact = service.lesson_observe(
        condition="job requires security clearance",
        action="record clearance fact",
        scope={"platform": "workday"},
        expected_result="fact noted",
        attempt_ids=[202],
        kind="candidate_fact",
    )
    with pytest.raises((ProtocolError, ValueError)):
        service.lesson_set_status(fact["id"], status="active", reason="attempted procedural promotion")


def test_lessons_for_context_scoping_limits_and_company_isolation(service):
    """lessons_for_context filters by scope, isolates company/namespace, and caps limit <= 5."""
    # Lesson scoped to company_a on workday
    l_co_a = service.lesson_observe(
        condition="company_a terms checkbox",
        action="check terms",
        scope={"platform": "workday", "namespace": "company_a"},
        expected_result="terms accepted",
        attempt_ids=[301],
    )
    service.lesson_set_status(l_co_a["id"], "active", reason="verified")

    # Lesson scoped to company_b on workday
    l_co_b = service.lesson_observe(
        condition="company_b custom survey",
        action="answer survey",
        scope={"platform": "workday", "namespace": "company_b"},
        expected_result="survey completed",
        attempt_ids=[302],
    )
    service.lesson_set_status(l_co_b["id"], "active", reason="verified")

    # Lesson scoped platform-wide to workday
    l_platform = service.lesson_observe(
        condition="generic workday pagination",
        action="click next page",
        scope={"platform": "workday"},
        expected_result="page 2 loaded",
        attempt_ids=[303],
    )
    service.lesson_set_status(l_platform["id"], "active", reason="verified")

    # Company isolation: company_a lessons must never appear for company_b or global context
    co_a_results = service.lessons_for_context(platform="workday", namespace="company_a")
    co_a_ids = [l["id"] for l in co_a_results]
    assert l_co_a["id"] in co_a_ids
    assert l_platform["id"] in co_a_ids
    assert l_co_b["id"] not in co_a_ids

    co_b_results = service.lessons_for_context(platform="workday", namespace="company_b")
    co_b_ids = [l["id"] for l in co_b_results]
    assert l_co_b["id"] in co_b_ids
    assert l_platform["id"] in co_b_ids
    assert l_co_a["id"] not in co_b_ids

    # Querying a neutral or different namespace never leaks company_a or company_b
    neutral_results = service.lessons_for_context(platform="workday", namespace="other_company")
    neutral_ids = [l["id"] for l in neutral_results]
    assert l_co_a["id"] not in neutral_ids
    assert l_co_b["id"] not in neutral_ids
    assert l_platform["id"] in neutral_ids

    # Limit cap testing: create 6 active lessons
    for i in range(6):
        extra = service.lesson_observe(
            condition=f"extra condition {i}",
            action=f"extra action {i}",
            scope={"platform": "workday", "namespace": "company_a"},
            expected_result="success",
            attempt_ids=[310 + i],
        )
        service.lesson_set_status(extra["id"], "active", reason=f"verified extra {i}")

    # Default limit=3 returns at most 3
    default_limited = service.lessons_for_context(platform="workday", namespace="company_a")
    assert len(default_limited) == 3

    # Limit requested as 10 must be capped at <= 5
    capped = service.lessons_for_context(platform="workday", namespace="company_a", limit=10)
    assert len(capped) <= 5


def test_lesson_record_outcome_appends_history_without_mutating_facts_or_policy(service):
    """lesson_record_outcome appends verification/failure history; never edits candidate facts or policy."""
    l = service.lesson_observe(
        condition="captcha detection",
        action="notify operator",
        scope={"platform": "greenhouse"},
        expected_result="operator resolved",
        attempt_ids=[401],
    )
    service.lesson_set_status(l["id"], "active", reason="approved")

    # Record verification success
    o1 = service.lesson_record_outcome(
        lesson_id=l["id"],
        attempt_id=402,
        success=True,
        reason="operator responded promptly",
    )
    # Record verification failure
    o2 = service.lesson_record_outcome(
        lesson_id=l["id"],
        attempt_id=403,
        success=False,
        reason="operator timed out",
    )

    history = o2.get("history", []) if isinstance(o2, dict) else service.lessons_for_context("greenhouse", None)[0].get("history", [])
    assert any(h["attempt_id"] == 402 and h["success"] is True for h in history)
    assert any(h["attempt_id"] == 403 and h["success"] is False for h in history)

    # Invariants preserved: original condition, action, scope, expected_result immutable
    fresh_lesson = service.lessons_for_context("greenhouse", None)[0]
    assert fresh_lesson["condition"] == "captcha detection"
    assert fresh_lesson["action"] == "notify operator"
    assert fresh_lesson["expected_result"] == "operator resolved"

    # Candidate facts and settings policy remain untouched
    settings = service.settings_view()
    assert settings["values"]["submission_mode"] == "review"

    # Candidate facts cannot be mutated via outcome recording
    cand_fact = service.lesson_observe(
        condition="unverified salary fact",
        action="store fact",
        scope={"platform": "greenhouse"},
        expected_result="fact logged",
        attempt_ids=[404],
        kind="candidate_fact",
    )
    with pytest.raises((ProtocolError, ValueError)):
        service.lesson_record_outcome(
            lesson_id=cand_fact["id"],
            attempt_id=405,
            success=True,
            reason="attempting to mutate fact/policy",
        )


def test_helper_register_creates_immutable_candidate_and_validates_hash(service, sample_py_helper, sample_js_helper, tmp_path):
    """helper_register creates immutable candidate referencing real tmp_path files with valid sha256; no code executes."""
    # Sentinel file to verify that code NEVER executes
    sentinel_path = tmp_path / "sentinel_executed.txt"
    py_exec_test = tmp_path / "executable_probe.py"
    py_exec_test.write_text(
        f"from pathlib import Path\nPath('{sentinel_path.as_posix()}').write_text('executed')\n",
        encoding="utf-8",
    )
    py_exec_hash = hashlib.sha256(py_exec_test.read_bytes()).hexdigest()

    # Register candidate helper with real tmp_path .py file
    h_py = service.helper_register(
        helper_id="workday_dropdown",
        version="1.0.0",
        capability="select_dropdown",
        path=str(py_exec_test),
        sha256=py_exec_hash,
        scope={"platform": "workday"},
        preconditions=["element_present"],
        limitations=["single_select_only"],
        tests=[{"action": "test_select", "expected": True}],
    )
    assert h_py["status"] == "candidate"
    assert h_py["version"] == "1.0.0"
    # Sentinel MUST NOT have been created — no code executes!
    assert not sentinel_path.exists()

    # Register candidate helper with real tmp_path .js file
    h_js = service.helper_register(
        helper_id="scroll_page",
        version="1.0.0",
        capability="scroll_view",
        path=sample_js_helper["path"],
        sha256=sample_js_helper["sha256"],
        scope={"platform": "workday"},
        preconditions=["page_loaded"],
        limitations=[],
        tests=[],
    )
    assert h_js["status"] == "candidate"

    # Mismatched SHA256 rejected
    with pytest.raises((ProtocolError, ValueError)):
        service.helper_register(
            helper_id="bad_hash_helper",
            version="1.0.0",
            capability="select_dropdown",
            path=sample_py_helper["path"],
            sha256="0" * 64,
            scope={"platform": "workday"},
            preconditions=[],
            limitations=[],
            tests=[],
        )

    # Non-existent path rejected
    with pytest.raises((ProtocolError, ValueError, FileNotFoundError)):
        service.helper_register(
            helper_id="missing_file_helper",
            version="1.0.0",
            capability="select_dropdown",
            path=str(tmp_path / "does_not_exist.py"),
            sha256="a" * 64,
            scope={"platform": "workday"},
            preconditions=[],
            limitations=[],
            tests=[],
        )

    # Duplicate differing content for same version rejected (no silent overwrite)
    with pytest.raises((ProtocolError, ValueError)):
        service.helper_register(
            helper_id="workday_dropdown",
            version="1.0.0",
            capability="select_dropdown_altered",
            path=sample_js_helper["path"],
            sha256=sample_js_helper["sha256"],
            scope={"platform": "workday"},
            preconditions=[],
            limitations=[],
            tests=[],
        )


def test_helper_activate_and_helpers_for_context_quiescence_and_tamper_detection(service, sample_py_helper, with_browser_lease):
    """helper_activate requires evidence + lease quiescence; helpers_for_context invalidates tampered files; fresh Service reload."""
    # Register helper
    service.helper_register(
        helper_id="workday_clicker",
        version="1.0.0",
        capability="click_button",
        path=sample_py_helper["path"],
        sha256=sample_py_helper["sha256"],
        scope={"platform": "workday", "namespace": "tenant_1"},
        preconditions=["button_visible"],
        limitations=[],
        tests=[],
    )

    # Empty verification evidence rejected
    with pytest.raises((ProtocolError, ValueError)):
        service.helper_activate("workday_clicker", "1.0.0", verification_evidence="")
    with pytest.raises((ProtocolError, ValueError)):
        service.helper_activate("workday_clicker", "1.0.0", verification_evidence={})

    # Active browser lease blocks activation (must be quiescent)
    with_browser_lease(profile="test-browser", state="active")
    with pytest.raises((ProtocolError, ValueError)):
        service.helper_activate(
            "workday_clicker",
            "1.0.0",
            verification_evidence="tested on synthetic form",
        )

    # Resolve browser lease (state='released')
    with_browser_lease(profile="test-browser", state="released")
    activated = service.helper_activate(
        "workday_clicker",
        "1.0.0",
        verification_evidence="verified in headless test run",
    )
    assert activated["status"] == "active"

    # Context retrieval returns active matching version
    matched = service.helpers_for_context("workday", "tenant_1", capability="click_button")
    assert len(matched) == 1
    assert matched[0]["helper_id"] == "workday_clicker"
    assert matched[0]["version"] == "1.0.0"

    # Fresh Service instance retrieves the same version
    s_fresh = Service(service.db_path, instance_id=service.instance_id)
    matched_fresh = s_fresh.helpers_for_context("workday", "tenant_1")
    assert len(matched_fresh) == 1
    assert matched_fresh[0]["helper_id"] == "workday_clicker"

    # Mutation after verification: tampering with file must not remain usable
    target_file = sample_py_helper["file"]
    target_file.write_text("# tampered code\ndef rogue(): pass\n", encoding="utf-8")
    # Querying helpers after file modification must detect hash mismatch and exclude or reject it
    usable_after_tamper = service.helpers_for_context("workday", "tenant_1")
    assert not any(h["helper_id"] == "workday_clicker" for h in usable_after_tamper)

    # Unsupported facts/policy changes rejected instead of automatic shared mutation
    with pytest.raises((ProtocolError, ValueError)):
        service.helper_register(
            helper_id="unauthorized_policy_mutator",
            version="1.0.0",
            capability="policy_override",
            path=str(target_file),
            sha256=hashlib.sha256(target_file.read_bytes()).hexdigest(),
            scope={"unsupported_key": "arbitrary_mutation"},
            preconditions=[],
            limitations=[],
            tests=[],
        )
