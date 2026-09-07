"""Document selection, timing uncertainty, and application context gaps (expected RED).

Primary Windows Hermes owns implementation.
Covers:
1. documents_status(job_id, identity_id, attempt_id=None) resolves one effective latest
   selection per kind, preferring matching attempt-specific selection over job-wide selection;
   another attempt's private selection never satisfies current required_documents.
2. Replacing a job-wide selected resume chooses latest selected version, while preserving
   all old selection/upload rows.
3. select_asset without explicit attempt_id must not attach a different candidate's asset
   to a currently claimed job. Preserve valid existing upload transitions.
4. attempt_report preserves persisted uncertain_duration after reconciliation even when outcome
   becomes blocked/applied and tool spans are otherwise complete; backward wall clock clamps
   reported elapsed but exposes uncertainty, not false precision. Core screenshot/secret policy unchanged.
5. Native worker must see missing required docs via application_context and cannot submission_intent
   if required selection is missing.
"""
import hashlib
import pytest

from job_applier.managed import Service, ProtocolError

SYNTHETIC_RESUME_HASH_V1 = hashlib.sha256(b"synthetic_resume_candidate_1_v1").hexdigest()
SYNTHETIC_RESUME_HASH_V2 = hashlib.sha256(b"synthetic_resume_candidate_1_v2").hexdigest()
SYNTHETIC_COVER_HASH_V1 = hashlib.sha256(b"synthetic_cover_letter_candidate_1_v1").hexdigest()


def test_documents_status_attempt_scoping_and_cross_attempt_isolation(tmp_path):
    """1. documents_status resolves one selection per kind, prefers attempt-specific over job-wide, isolates private attempts."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-doc-timing-gaps")
    s.identity(identity_id="cand-1", person_key="p1", email="c1@example.test", profile={"facts": {}})
    res_v1 = s.register_asset(
        identity_id="cand-1",
        kind="resume",
        version="v1",
        storage_ref="storage://cand-1/resume-v1.pdf",
        sha256=SYNTHETIC_RESUME_HASH_V1,
        provenance={"source": "upload"},
    )
    res_v2 = s.register_asset(
        identity_id="cand-1",
        kind="resume",
        version="v2",
        storage_ref="storage://cand-1/resume-v2.pdf",
        sha256=SYNTHETIC_RESUME_HASH_V2,
        provenance={"source": "upload"},
    )
    cov_v1 = s.register_asset(
        identity_id="cand-1",
        kind="cover_letter",
        version="v1",
        storage_ref="storage://cand-1/cover-v1.pdf",
        sha256=SYNTHETIC_COVER_HASH_V1,
        provenance={"source": "upload"},
    )
    job = s.intake(
        url="https://careers.example.test/jobs/scoping-1",
        source_id="sc-1",
        required_documents=["resume", "cover_letter"],
    )
    s.eligibility(job["id"], "ready", reason="approved")

    # Select resume v1 job-wide (attempt_id=None)
    s.select_asset(asset_id=res_v1["id"], job_id=job["id"])

    # Attempt 1 claimed
    r1 = s.request_run(request_id="req-1", job_ids=[job["id"]], identity_id="cand-1", browser_profile="bp-1")
    s.accept_run(
        r1["id"],
        worker_id="w-1",
        session_id="s-1",
        capabilities={"protocol": 1, "skill_version": "v1", "browser_profile": "bp-1", "provider": "p", "model": "m", "telemetry": True},
    )
    a1 = s.claim(r1["id"], worker_id="w-1")

    # In attempt 1, cover letter is selected specifically for attempt 1
    s.select_asset(asset_id=cov_v1["id"], job_id=job["id"], attempt_id=a1["id"])

    # For attempt 1, status has resume v1 (job-wide) and cover letter v1 (attempt-specific)
    st1 = s.documents_status(job["id"], "cand-1", attempt_id=a1["id"])
    assert st1["ready"] is True
    assert st1["missing"] == []

    # Finish attempt 1 as failed
    s.finish(a1["id"], worker_id="w-1", fence=a1["fence"], outcome="failed", evidence="portal_unavailable", quiescent=True)

    # Attempt 2 claimed after new run
    r2 = s.request_run(request_id="req-2", job_ids=[job["id"]], identity_id="cand-1", browser_profile="bp-1")
    s.accept_run(
        r2["id"],
        worker_id="w-1",
        session_id="s-2",
        capabilities={"protocol": 1, "skill_version": "v1", "browser_profile": "bp-1", "provider": "p", "model": "m", "telemetry": True},
    )
    a2 = s.claim(r2["id"], worker_id="w-1")

    # Gap check 1: another attempt's private selection (cov_v1 on a1) never satisfies current required_documents for a2
    st2_before = s.documents_status(job["id"], "cand-1", attempt_id=a2["id"])
    assert st2_before["ready"] is False
    assert "cover_letter" in st2_before["missing"]
    assert not any(a["id"] == cov_v1["id"] for a in st2_before["assets"])

    # Gap check 2: resolve one effective latest selection per kind, preferring matching attempt-specific selection over job-wide selection
    # For a2, select resume v2 specifically
    s.select_asset(asset_id=res_v2["id"], job_id=job["id"], attempt_id=a2["id"])
    st2_after = s.documents_status(job["id"], "cand-1", attempt_id=a2["id"])
    resume_assets = [a for a in st2_after["assets"] if a["kind"] == "resume"]
    assert len(resume_assets) == 1
    assert resume_assets[0]["id"] == res_v2["id"]
    assert resume_assets[0]["version"] == "v2"


def test_replacing_job_wide_selected_resume_chooses_latest_and_preserves_history(tmp_path):
    """2. Replacing a job-wide selected resume chooses latest selected version, while preserving all old selection/upload rows."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-doc-timing-gaps")
    s.identity(identity_id="cand-1", person_key="p1", email="c1@example.test", profile={"facts": {}})
    res_v1 = s.register_asset(
        identity_id="cand-1",
        kind="resume",
        version="v1",
        storage_ref="storage://cand-1/resume-v1.pdf",
        sha256=SYNTHETIC_RESUME_HASH_V1,
        provenance={"source": "candidate_upload"},
    )
    res_v2 = s.register_asset(
        identity_id="cand-1",
        kind="resume",
        version="v2",
        storage_ref="storage://cand-1/resume-v2.pdf",
        sha256=SYNTHETIC_RESUME_HASH_V2,
        provenance={"source": "candidate_upload"},
    )
    job = s.intake(url="https://careers.example.test/jobs/replace-1", source_id="rep-1", required_documents=["resume"])
    s.eligibility(job["id"], "ready", reason="approved")

    # Select resume v1 job-wide
    s.select_asset(asset_id=res_v1["id"], job_id=job["id"])

    # Claim attempt and record an upload transition for v1
    r = s.request_run(request_id="req-rep-1", job_ids=[job["id"]], identity_id="cand-1", browser_profile="bp-1")
    s.accept_run(
        r["id"],
        worker_id="w-1",
        session_id="s-1",
        capabilities={"protocol": 1, "skill_version": "v1", "browser_profile": "bp-1", "provider": "p", "model": "m", "telemetry": True},
    )
    a = s.claim(r["id"], worker_id="w-1")

    up = s.report_upload(
        attempt_id=a["id"],
        worker_id="w-1",
        fence=a["fence"],
        asset_id=res_v1["id"],
        status="upload_attempted",
        evidence="opened_upload_dialog",
    )
    assert up["status"] == "upload_attempted"

    # Replace job-wide selection with resume v2
    s.select_asset(asset_id=res_v2["id"], job_id=job["id"])

    # documents_status resolves latest selected version per kind (v2 only, not both)
    st = s.documents_status(job["id"], "cand-1")
    assert st["ready"] is True
    resumes = [asset for asset in st["assets"] if asset["kind"] == "resume"]
    assert len(resumes) == 1
    assert resumes[0]["id"] == res_v2["id"]
    assert resumes[0]["version"] == "v2"

    # Preserves all old selection and upload rows
    with s.tx() as db:
        selections = db.execute(
            "SELECT asset_id, status FROM document_selections WHERE job_id=? ORDER BY created_at",
            (job["id"],),
        ).fetchall()
        assert len(selections) == 2
        assert {row["asset_id"] for row in selections} == {res_v1["id"], res_v2["id"]}

        uploads = db.execute(
            "SELECT asset_id, status, evidence FROM document_uploads WHERE attempt_id=?",
            (a["id"],),
        ).fetchall()
        assert len(uploads) == 1
        assert uploads[0]["asset_id"] == res_v1["id"]
        assert uploads[0]["status"] == "upload_attempted"


def test_select_asset_without_attempt_id_rejects_cross_candidate_on_claimed_job(tmp_path):
    """3. select_asset without explicit attempt_id must not attach different candidate's asset to claimed job; upload transitions preserved."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-doc-timing-gaps")
    s.identity(identity_id="cand-1", person_key="p1", email="c1@example.test", profile={"facts": {}})
    s.identity(identity_id="cand-2", person_key="p2", email="c2@example.test", profile={"facts": {}})

    asset_c1 = s.register_asset(
        identity_id="cand-1",
        kind="resume",
        version="v1",
        storage_ref="storage://cand-1/resume-v1.pdf",
        sha256=SYNTHETIC_RESUME_HASH_V1,
        provenance={"source": "manual"},
    )
    asset_c2 = s.register_asset(
        identity_id="cand-2",
        kind="resume",
        version="v1",
        storage_ref="storage://cand-2/resume-v1.pdf",
        sha256=SYNTHETIC_RESUME_HASH_V2,
        provenance={"source": "manual"},
    )

    job = s.intake(url="https://careers.example.test/jobs/claimed-1", source_id="cl-1", required_documents=["resume"])
    s.eligibility(job["id"], "ready", reason="approved")

    # Claim job for cand-1
    r = s.request_run(request_id="req-cl-1", job_ids=[job["id"]], identity_id="cand-1", browser_profile="bp-1")
    s.accept_run(
        r["id"],
        worker_id="w-1",
        session_id="s-1",
        capabilities={"protocol": 1, "skill_version": "v1", "browser_profile": "bp-1", "provider": "p", "model": "m", "telemetry": True},
    )
    a = s.claim(r["id"], worker_id="w-1")
    assert a["identity_id"] == "cand-1"

    # select_asset without explicit attempt_id MUST NOT attach different candidate's asset (cand-2) to cand-1's claimed job
    with pytest.raises(ProtocolError):
        s.select_asset(asset_id=asset_c2["id"], job_id=job["id"])

    # Preserve valid existing upload transitions for candidate 1's selected asset
    s.select_asset(asset_id=asset_c1["id"], job_id=job["id"])
    att = s.report_upload(
        attempt_id=a["id"],
        worker_id="w-1",
        fence=a["fence"],
        asset_id=asset_c1["id"],
        status="upload_attempted",
        evidence="file_picker_opened",
    )
    assert att["status"] == "upload_attempted"

    conf = s.report_upload(
        attempt_id=a["id"],
        worker_id="w-1",
        fence=a["fence"],
        asset_id=asset_c1["id"],
        status="upload_confirmed",
        evidence="file_input_verified",
    )
    assert conf["status"] == "upload_confirmed"
    assert conf["version"] == asset_c1["version"]
    assert conf["sha256"] == asset_c1["sha256"]


def test_attempt_report_preserves_uncertain_duration_and_backward_clock_uncertainty(tmp_path):
    """4. attempt_report preserves persisted uncertain_duration after reconciliation and backward wall clock uncertainty."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-doc-timing-gaps")
    s.identity(identity_id="cand-1", person_key="p1", email="c1@example.test", profile={"facts": {}})
    job1 = s.intake(url="https://careers.example.test/jobs/timing-1", source_id="tm-1")
    job2 = s.intake(url="https://careers.example.test/jobs/timing-2", source_id="tm-2")
    s.eligibility(job1["id"], "ready", reason="approved")
    s.eligibility(job2["id"], "ready", reason="approved")

    r1 = s.request_run(request_id="req-tm-1", job_ids=[job1["id"]], identity_id="cand-1", browser_profile="bp-1")
    s.accept_run(
        r1["id"],
        worker_id="w-1",
        session_id="s-1",
        capabilities={"protocol": 1, "skill_version": "v1", "browser_profile": "bp-1", "provider": "p", "model": "m", "telemetry": True},
    )
    a1 = s.claim(r1["id"], worker_id="w-1")

    # Set started_at so tool span [12:00:10Z .. 12:00:20Z] is strictly inside [started_at .. completed_at] (complete, unclipped)
    with s.tx() as db:
        db.execute("UPDATE application_attempts SET started_at='2026-09-07T12:00:00Z' WHERE id=?", (a1["id"],))

    s.event(
        attempt_id=a1["id"],
        worker_id="w-1",
        fence=a1["fence"],
        event_id="act-1",
        event_type="tool_finished",
        observed_at="2026-09-07T12:00:20Z",
        duration_seconds=10.0,
        payload={"tool_name": "form_fill", "status": "success"},
    )

    # Reconcile attempt to applied; reconciliation sets persisted uncertain_duration=1
    s.reconcile(a1["id"], outcome="applied", evidence="email_confirmation_receipt", browser_quiescent=True)
    with s.tx() as db:
        db.execute("UPDATE application_attempts SET completed_at='2026-09-07T12:00:30Z' WHERE id=?", (a1["id"],))
        row = db.execute("SELECT uncertain_duration, outcome FROM application_attempts WHERE id=?", (a1["id"],)).fetchone()
        assert row["uncertain_duration"] == 1
        assert row["outcome"] == "applied"

    # attempt_report must preserve persisted uncertain_duration even though outcome is applied and tool spans are complete
    rep1 = s.attempt_report(a1["id"])
    assert rep1["timing"]["uncertainty"] is True
    assert rep1["attempt"]["uncertain_duration"] is True

    # Core screenshot/secret policy unchanged: timeline payloads contain no raw secrets or screenshot dumps
    for evt in rep1["timeline"]:
        assert "password" not in str(evt.get("payload", {}))
        assert "screenshot_bytes" not in str(evt.get("payload", {}))

    # Backward wall clock on attempt 2: completed_at earlier than started_at
    r2 = s.request_run(request_id="req-tm-2", job_ids=[job2["id"]], identity_id="cand-1", browser_profile="bp-2")
    s.accept_run(
        r2["id"],
        worker_id="w-1",
        session_id="s-2",
        capabilities={"protocol": 1, "skill_version": "v1", "browser_profile": "bp-2", "provider": "p", "model": "m", "telemetry": True},
    )
    a2 = s.claim(r2["id"], worker_id="w-1")

    # Simulate backward clock skew: completed_at < started_at
    with s.tx() as db:
        db.execute(
            "UPDATE application_attempts SET started_at=?, completed_at=?, outcome=? WHERE id=?",
            ("2026-09-07T12:00:20Z", "2026-09-07T12:00:10Z", "ready_for_review", a2["id"]),
        )

    rep2 = s.attempt_report(a2["id"])
    # Backward wall clock clamps reported elapsed to 0, but exposes uncertainty rather than false precision
    assert rep2["timing"]["wall_seconds"] == 0.0
    assert rep2["attempt"]["elapsed_seconds"] == 0.0
    assert rep2["attempt"]["uncertain_duration"] is True


def test_native_worker_application_context_and_missing_doc_blocks_submission_intent(tmp_path):
    """5. Native worker sees missing required docs via application_context and cannot submission_intent if required selection missing."""
    s = Service.create(tmp_path / "jobs.db", instance_id="test-doc-timing-gaps")
    s.identity(identity_id="cand-1", person_key="p1", email="c1@example.test", profile={"facts": {}})
    res_v1 = s.register_asset(
        identity_id="cand-1",
        kind="resume",
        version="v1",
        storage_ref="storage://cand-1/resume-v1.pdf",
        sha256=SYNTHETIC_RESUME_HASH_V1,
        provenance={"source": "candidate_upload"},
    )
    # Job requires both resume and cover_letter
    job = s.intake(url="https://careers.example.test/jobs/ctx-req-1", source_id="ctx-1", required_documents=["resume", "cover_letter"])
    s.eligibility(job["id"], "ready", reason="approved")

    # Only resume is selected; cover_letter remains missing
    s.select_asset(asset_id=res_v1["id"], job_id=job["id"])

    r = s.request_run(request_id="req-ctx-1", job_ids=[job["id"]], identity_id="cand-1", browser_profile="bp-1")
    s.accept_run(
        r["id"],
        worker_id="w-1",
        session_id="s-1",
        capabilities={"protocol": 1, "skill_version": "v1", "browser_profile": "bp-1", "provider": "p", "model": "m", "telemetry": True},
    )
    a = s.claim(r["id"], worker_id="w-1")

    # Native worker must see missing required docs via application_context
    ctx = s.application_context(a["id"], worker_id="w-1")
    assert isinstance(ctx, dict)
    assert "documents" in ctx
    assert ctx["documents"]["ready"] is False
    assert "cover_letter" in ctx["documents"]["missing"]

    # Worker cannot submission_intent if required selection is missing
    with pytest.raises(ProtocolError):
        s.submission_intent(a["id"], worker_id="w-1", fence=a["fence"], evidence="submitting_fixture", fixture=True)
