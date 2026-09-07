"""Documents and assessments contracts (expected RED).

Primary Windows Hermes owns implementation.
Covers:
1. register_asset(identity_id, kind, version, storage_ref, sha256, provenance)
   stores immutable resume|cover_letter metadata, status available; rejects conflicting
   same asset version and malformed hashes; no generation or remote fetching.
2. select_asset(asset_id, job_id, attempt_id=None) creates selected linkage;
   cannot attach another candidate's asset to a claimed attempt.
3. documents_status(job_id, identity_id) -> {ready, missing, assets}; explicit job
   metadata required_documents=['cover_letter'] is missing until selected;
   do not treat available as selected/confirmed.
4. report_upload(attempt_id, worker_id, fence, asset_id, status, evidence)
   transitions upload_attempted -> upload_confirmed; confirmation without attempted/selection
   refused; exact asset/version/hash preserved; unauthorized owner transitions rejected.
5. register_assessment(job_id, jd_hash, resume_hash, profile_hash, evaluator, model,
   rubric, score, scale_min, scale_max, recommendation, reasons, evaluated_at) accepts
   externally produced versioned assessment; range validation finite score in scale;
   allowed recommendations Strong apply/Apply/Apply with caveats/Skip; rejects malformed hashes.
6. None/missing assessment remains unassessed, never zero. View job exposes latest registered
   assessment but eligibility/status remains unchanged.
"""
import hashlib
import pytest

from job_applier.managed import Service, ProtocolError

SYNTHETIC_RESUME_HASH = hashlib.sha256(b"synthetic_resume_candidate_1_v1").hexdigest()
SYNTHETIC_COVER_LETTER_HASH = hashlib.sha256(b"synthetic_cover_letter_candidate_1_v1").hexdigest()
SYNTHETIC_JD_HASH = hashlib.sha256(b"synthetic_job_description_body_201").hexdigest()
SYNTHETIC_PROFILE_HASH = hashlib.sha256(b"synthetic_profile_facts_cand1").hexdigest()

ALLOWED_RECOMMENDATIONS = ("Strong apply", "Apply", "Apply with caveats", "Skip")


def test_register_asset_stores_immutable_metadata_and_rejects_conflicts(tmp_path):
    """1. register_asset stores immutable metadata, status available, rejects conflicts/malformed hashes."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-doc-assess")
    s.identity(
        identity_id="cand-1",
        person_key="person-1",
        email="cand1@example.test",
        profile={"facts": {}},
    )

    # Valid registration of resume and cover letter
    res = s.register_asset(
        identity_id="cand-1",
        kind="resume",
        version="v1",
        storage_ref="storage://synthetic/cand-1/resume-v1.pdf",
        sha256=SYNTHETIC_RESUME_HASH,
        provenance={"source": "candidate_upload"},
    )
    assert isinstance(res, dict)
    assert res["identity_id"] == "cand-1"
    assert res["kind"] == "resume"
    assert res["version"] == "v1"
    assert res["storage_ref"] == "storage://synthetic/cand-1/resume-v1.pdf"
    assert res["sha256"] == SYNTHETIC_RESUME_HASH
    assert res["status"] == "available"

    cov = s.register_asset(
        identity_id="cand-1",
        kind="cover_letter",
        version="v1",
        storage_ref="storage://synthetic/cand-1/cover-v1.pdf",
        sha256=SYNTHETIC_COVER_LETTER_HASH,
        provenance={"source": "synthetic_generator"},
    )
    assert isinstance(cov, dict)
    assert cov["kind"] == "cover_letter"
    assert cov["status"] == "available"

    # Conflicting same asset version rejected
    with pytest.raises(ProtocolError):
        s.register_asset(
            identity_id="cand-1",
            kind="resume",
            version="v1",
            storage_ref="storage://synthetic/cand-1/resume-v1-modified.pdf",
            sha256=hashlib.sha256(b"conflicting_bytes").hexdigest(),
            provenance={"source": "overwrite_attempt"},
        )

    # Reject malformed hashes
    for bad_hash in ("not_a_hash", "12345", "g" * 64, ""):
        with pytest.raises(ProtocolError):
            s.register_asset(
                identity_id="cand-1",
                kind="cover_letter",
                version="v2",
                storage_ref="storage://synthetic/cand-1/cover-v2.pdf",
                sha256=bad_hash,
                provenance={"source": "candidate_upload"},
            )


def test_select_asset_linkage_and_cross_candidate_isolation(tmp_path):
    """2. select_asset creates linkage and prevents cross-candidate asset attachment to claimed attempt."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-doc-assess")
    s.identity(identity_id="cand-1", person_key="p1", email="c1@example.test", profile={"facts": {}})
    s.identity(identity_id="cand-2", person_key="p2", email="c2@example.test", profile={"facts": {}})

    asset1 = s.register_asset(
        identity_id="cand-1",
        kind="resume",
        version="v1",
        storage_ref="storage://cand-1/resume-v1.pdf",
        sha256=SYNTHETIC_RESUME_HASH,
        provenance={"source": "manual"},
    )
    asset2 = s.register_asset(
        identity_id="cand-2",
        kind="resume",
        version="v1",
        storage_ref="storage://cand-2/resume-v1.pdf",
        sha256=hashlib.sha256(b"cand2_resume").hexdigest(),
        provenance={"source": "manual"},
    )

    job = s.intake(url="https://careers.example.test/jobs/select-1", source_id="s1")
    s.eligibility(job["id"], "ready", reason="operator approved")

    linkage = s.select_asset(asset_id=asset1["id"], job_id=job["id"])
    assert isinstance(linkage, dict)
    assert linkage.get("selected_asset_id") == asset1["id"] or linkage.get("asset_id") == asset1["id"]
    assert linkage["job_id"] == job["id"]

    r = s.request_run(
        request_id="req-sel-1",
        job_ids=[job["id"]],
        identity_id="cand-1",
        browser_profile="fixture-profile",
    )
    s.accept_run(
        r["id"],
        worker_id="worker-1",
        session_id="session-1",
        capabilities={
            "protocol": 1,
            "skill_version": "test-skill",
            "browser_profile": "fixture-profile",
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )
    attempt = s.claim(r["id"], worker_id="worker-1")

    # Cannot attach another candidate's asset to a claimed attempt
    with pytest.raises(ProtocolError):
        s.select_asset(asset_id=asset2["id"], job_id=job["id"], attempt_id=attempt["id"])


def test_documents_status_requires_explicit_selection_not_just_availability(tmp_path):
    """3. documents_status marks required document missing until selected; available is not selected."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-doc-assess")
    s.identity(identity_id="cand-1", person_key="p1", email="c1@example.test", profile={"facts": {}})

    job = s.intake(
        url="https://careers.example.test/jobs/doc-req-1",
        source_id="s-doc-1",
        required_documents=["cover_letter"],
    )

    status_before = s.documents_status(job_id=job["id"], identity_id="cand-1")
    assert isinstance(status_before, dict)
    assert status_before["ready"] is False
    assert "cover_letter" in status_before["missing"]

    letter_asset = s.register_asset(
        identity_id="cand-1",
        kind="cover_letter",
        version="v1",
        storage_ref="storage://cand-1/letter-v1.pdf",
        sha256=SYNTHETIC_COVER_LETTER_HASH,
        provenance={"source": "manual"},
    )
    # Available is NOT treated as selected/confirmed
    status_avail = s.documents_status(job_id=job["id"], identity_id="cand-1")
    assert status_avail["ready"] is False
    assert "cover_letter" in status_avail["missing"]

    # Once selected, linkage is established and missing is cleared
    s.select_asset(asset_id=letter_asset["id"], job_id=job["id"])
    status_selected = s.documents_status(job_id=job["id"], identity_id="cand-1")
    assert status_selected["ready"] is True
    assert "cover_letter" not in status_selected["missing"]
    assert any(a["id"] == letter_asset["id"] for a in status_selected["assets"])


def test_report_upload_lifecycle_transitions_and_fence_validation(tmp_path):
    """4. report_upload transitions upload_attempted -> upload_confirmed; rejects unselected and unauthorized owners."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-doc-assess")
    s.identity(identity_id="cand-1", person_key="p1", email="c1@example.test", profile={"facts": {}})
    asset = s.register_asset(
        identity_id="cand-1",
        kind="resume",
        version="v1",
        storage_ref="storage://cand-1/resume-v1.pdf",
        sha256=SYNTHETIC_RESUME_HASH,
        provenance={"source": "manual"},
    )
    job = s.intake(url="https://careers.example.test/jobs/upload-1", source_id="up-1")
    s.eligibility(job["id"], "ready", reason="approved")
    r = s.request_run(
        request_id="req-up-1",
        job_ids=[job["id"]],
        identity_id="cand-1",
        browser_profile="fixture-profile",
    )
    s.accept_run(
        r["id"],
        worker_id="worker-1",
        session_id="session-1",
        capabilities={
            "protocol": 1,
            "skill_version": "test-skill",
            "browser_profile": "fixture-profile",
            "provider": "fixture",
            "model": "fixture",
            "telemetry": True,
        },
    )
    attempt = s.claim(r["id"], worker_id="worker-1")

    # Confirmation without attempted/selection refused
    with pytest.raises(ProtocolError):
        s.report_upload(
            attempt_id=attempt["id"],
            worker_id="worker-1",
            fence=attempt["fence"],
            asset_id=asset["id"],
            status="upload_confirmed",
            evidence="file_input_set",
        )

    # First select asset and report upload_attempted
    s.select_asset(asset_id=asset["id"], job_id=job["id"], attempt_id=attempt["id"])
    attempted = s.report_upload(
        attempt_id=attempt["id"],
        worker_id="worker-1",
        fence=attempt["fence"],
        asset_id=asset["id"],
        status="upload_attempted",
        evidence="file_dialog_opened",
    )
    assert isinstance(attempted, dict)
    assert attempted["status"] == "upload_attempted"

    # Unauthorized owner transition: wrong worker_id or stale fence refused
    with pytest.raises(ProtocolError):
        s.report_upload(
            attempt_id=attempt["id"],
            worker_id="imposter-worker",
            fence=attempt["fence"],
            asset_id=asset["id"],
            status="upload_confirmed",
            evidence="file_input_confirmed",
        )
    with pytest.raises(ProtocolError):
        s.report_upload(
            attempt_id=attempt["id"],
            worker_id="worker-1",
            fence=attempt["fence"] + 99,
            asset_id=asset["id"],
            status="upload_confirmed",
            evidence="file_input_confirmed",
        )

    # Transitions upload_attempted -> upload_confirmed; exact asset/version/hash preserved
    confirmed = s.report_upload(
        attempt_id=attempt["id"],
        worker_id="worker-1",
        fence=attempt["fence"],
        asset_id=asset["id"],
        status="upload_confirmed",
        evidence="file_input_confirmed",
    )
    assert isinstance(confirmed, dict)
    assert confirmed["status"] == "upload_confirmed"
    assert confirmed["asset_id"] == asset["id"]
    assert confirmed["version"] == asset["version"]
    assert confirmed["sha256"] == SYNTHETIC_RESUME_HASH


def test_register_assessment_validates_hashes_range_and_allowed_recommendations(tmp_path):
    """5. register_assessment validates finite score in scale, allowed recommendations, and opaque hashes."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-doc-assess")
    job = s.intake(url="https://careers.example.test/jobs/assess-1", source_id="as-1")

    # Range validation: finite score in scale
    with pytest.raises(ProtocolError):
        s.register_assessment(
            job_id=job["id"],
            jd_hash=SYNTHETIC_JD_HASH,
            resume_hash=SYNTHETIC_RESUME_HASH,
            profile_hash=SYNTHETIC_PROFILE_HASH,
            evaluator="external_agent",
            model="gemini-3.8-flash",
            rubric="standard_rubric_v1",
            score=150.0,
            scale_min=0.0,
            scale_max=100.0,
            recommendation="Apply",
            reasons=["Score exceeds scale_max"],
            evaluated_at="2026-09-07T12:00:00Z",
        )
    with pytest.raises(ProtocolError):
        s.register_assessment(
            job_id=job["id"],
            jd_hash=SYNTHETIC_JD_HASH,
            resume_hash=SYNTHETIC_RESUME_HASH,
            profile_hash=SYNTHETIC_PROFILE_HASH,
            evaluator="external_agent",
            model="gemini-3.8-flash",
            rubric="standard_rubric_v1",
            score=float("nan"),
            scale_min=0.0,
            scale_max=100.0,
            recommendation="Apply",
            reasons=["NaN score"],
            evaluated_at="2026-09-07T12:00:00Z",
        )

    # Allowed recommendations: Strong apply, Apply, Apply with caveats, Skip
    for allowed in ALLOWED_RECOMMENDATIONS:
        record = s.register_assessment(
            job_id=job["id"],
            jd_hash=SYNTHETIC_JD_HASH,
            resume_hash=SYNTHETIC_RESUME_HASH,
            profile_hash=SYNTHETIC_PROFILE_HASH,
            evaluator="external_agent",
            model="gemini-3.8-flash",
            rubric="standard_rubric_v1",
            score=85.0,
            scale_min=0.0,
            scale_max=100.0,
            recommendation=allowed,
            reasons=[f"Valid evaluation recommendation {allowed}"],
            evaluated_at="2026-09-07T12:00:00Z",
        )
        assert isinstance(record, dict)
        assert record["recommendation"] == allowed
        assert record["score"] == 85.0

    # Disallowed recommendation rejected
    with pytest.raises(ProtocolError):
        s.register_assessment(
            job_id=job["id"],
            jd_hash=SYNTHETIC_JD_HASH,
            resume_hash=SYNTHETIC_RESUME_HASH,
            profile_hash=SYNTHETIC_PROFILE_HASH,
            evaluator="external_agent",
            model="gemini-3.8-flash",
            rubric="standard_rubric_v1",
            score=85.0,
            scale_min=0.0,
            scale_max=100.0,
            recommendation="Definite hire",
            reasons=["Disallowed recommendation"],
            evaluated_at="2026-09-07T12:00:00Z",
        )

    # Reject malformed hashes
    with pytest.raises(ProtocolError):
        s.register_assessment(
            job_id=job["id"],
            jd_hash="short_malformed_hash",
            resume_hash=SYNTHETIC_RESUME_HASH,
            profile_hash=SYNTHETIC_PROFILE_HASH,
            evaluator="external_agent",
            model="gemini-3.8-flash",
            rubric="standard_rubric_v1",
            score=85.0,
            scale_min=0.0,
            scale_max=100.0,
            recommendation="Apply",
            reasons=["Malformed hash"],
            evaluated_at="2026-09-07T12:00:00Z",
        )


def test_unassessed_job_is_none_and_view_job_exposes_latest_without_mutating_status(tmp_path):
    """6. None/missing assessment remains unassessed; view exposes latest assessment; status/eligibility unchanged."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-doc-assess")
    job = s.intake(url="https://careers.example.test/jobs/view-test-1", source_id="v1")
    init_status = job["status"]
    init_eligibility = job["eligibility"]

    # None/missing assessment remains unassessed, never zero
    view_data = s.view()
    job_view = next(j for j in view_data["jobs"] if j["id"] == job["id"])
    assert job_view["assessment"] is None
    assert job_view["assessment"] != 0
    assert job_view["assessment"] != "0"

    # Register first assessment
    s.register_assessment(
        job_id=job["id"],
        jd_hash=SYNTHETIC_JD_HASH,
        resume_hash=SYNTHETIC_RESUME_HASH,
        profile_hash=SYNTHETIC_PROFILE_HASH,
        evaluator="external_agent",
        model="model-1",
        rubric="r1",
        score=70.0,
        scale_min=0.0,
        scale_max=100.0,
        recommendation="Apply with caveats",
        reasons=["First evaluation"],
        evaluated_at="2026-09-07T12:00:00Z",
    )

    # Register newer assessment
    s.register_assessment(
        job_id=job["id"],
        jd_hash=SYNTHETIC_JD_HASH,
        resume_hash=SYNTHETIC_RESUME_HASH,
        profile_hash=SYNTHETIC_PROFILE_HASH,
        evaluator="external_agent",
        model="model-2",
        rubric="r2",
        score=92.0,
        scale_min=0.0,
        scale_max=100.0,
        recommendation="Strong apply",
        reasons=["Latest updated evaluation"],
        evaluated_at="2026-09-07T12:30:00Z",
    )

    # View job exposes latest registered assessment
    refreshed_job = s.job(job["id"])
    assert refreshed_job["assessment"] is not None
    assert refreshed_job["assessment"]["score"] == 92.0
    assert refreshed_job["assessment"]["recommendation"] == "Strong apply"

    # View projection also exposes latest registered assessment
    view_after = s.view()
    job_in_view = next(j for j in view_after["jobs"] if j["id"] == job["id"])
    assert job_in_view["assessment"] is not None
    assert job_in_view["assessment"]["score"] == 92.0
    assert job_in_view["assessment"]["recommendation"] == "Strong apply"

    # Eligibility and status remain unchanged
    assert refreshed_job["status"] == init_status
    assert refreshed_job["eligibility"] == init_eligibility
