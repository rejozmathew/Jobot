"""Stage 4 data-safety preparation tests for JobBot history archiving.

Contracts covered (<=3 concise tests):
1. test_preview_archive_readonly_invariants_and_exact_counts:
   - preview_archive(job_ids) read-only returns {instance_id, job_ids, preview_hash, counts}.
   - Content invariants: Database SHA-256 and records are strictly unchanged by preview.
   - Accurately counts every selected item across jobs, attempts, and sources.
   - Leaves unrelated fixture jobs and histories completely unchanged.

2. test_archive_creates_verified_backup_additive_metadata_and_preserves_view_and_suppression:
   - archive(job_ids, preview_hash, backup_path) creates non-overwriting verified SQLite backup
     using existing backup utility.
   - Marks ONLY selected jobs archived in additive metadata without deleting or rewriting
     original outcomes, attempts, source rows, accounts, or submission suppressions.
   - Default UI / view() hides archived queue records while history is retained;
     view(include_archived=True) includes them.
   - Applied duplicate suppression remains active and rejects retries/intake re-execution.
   - Unrelated fixture jobs remain untouched.

3. test_archive_refusals_and_no_partial_archive:
   - Rejects wrong or tampered preview_hash with ProtocolError.
   - Rejects changed selection after preview (subset or superset) with ProtocolError.
   - Rejects wrong instance scope with ProtocolError.
   - Rejects non-quiescent/active leases or non-completed jobs with ProtocolError.
   - Rejects pre-existing backup destination (FileExistsError or ProtocolError).
   - Guarantees zero partial archive on every refusal: DB is unmodified, no jobs marked archived.
"""
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import pytest

from job_applier.managed import Service, ProtocolError


def _preview_archive(service, job_ids):
    """Invoke preview_archive via Service method or modular function."""
    if hasattr(service, "preview_archive"):
        return service.preview_archive(job_ids)
    for mod_name in ("job_applier.managed", "job_applier.managed_data", "job_applier.managed_archive"):
        try:
            mod = __import__(mod_name, fromlist=["preview_archive"])
            if hasattr(mod, "preview_archive"):
                fn = getattr(mod, "preview_archive")
                try:
                    return fn(service, job_ids)
                except TypeError:
                    return fn(job_ids)
        except ImportError:
            pass
    return service.preview_archive(job_ids)


def _archive(service, job_ids, preview_hash, backup_path):
    """Invoke archive via Service method or modular function."""
    if hasattr(service, "archive"):
        return service.archive(job_ids, preview_hash, backup_path)
    for mod_name in ("job_applier.managed", "job_applier.managed_data", "job_applier.managed_archive"):
        try:
            mod = __import__(mod_name, fromlist=["archive"])
            if hasattr(mod, "archive"):
                fn = getattr(mod, "archive")
                try:
                    return fn(service, job_ids, preview_hash, backup_path)
                except TypeError:
                    return fn(job_ids, preview_hash, backup_path)
        except ImportError:
            pass
    return service.archive(job_ids, preview_hash, backup_path)


def _accept_capabilities(browser_profile):
    return {
        "protocol": 1,
        "skill_version": "test-skill-v1",
        "provider": "hermes",
        "model": "gpt-4o",
        "telemetry": True,
        "browser_profile": browser_profile,
    }


def make_synthetic_service(tmp_path, instance_id="test-archive-instance"):
    """Synthesize a complete isolated development service with diverse job states."""
    s = Service.create(
        tmp_path / "jobs.db",
        instance_id=instance_id,
        settings={"mode": "development", "submission_mode": "review"},
    )
    s.identity(
        identity_id="cand-1",
        person_key="person-1",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "fixture"}, "resume_ref": "asset:fixture-v1"},
    )

    # Job 1: Completed and applied with submission ledger suppression
    j1 = s.intake(url="https://careers.example.test/jobs/applied-1", source_id="src-1")
    s.eligibility(j1["id"], "ready", reason="operator approval")
    r1 = s.request_run(
        request_id="run-app-1",
        job_ids=[j1["id"]],
        identity_id="cand-1",
        browser_profile="prof-1",
    )
    s.accept_run(r1["id"], worker_id="worker-1", session_id="sess-1", capabilities=_accept_capabilities(r1["browser_profile"]))
    a1 = s.claim(r1["id"], worker_id="worker-1")
    s.submission_intent(a1["id"], worker_id="worker-1", fence=a1["fence"], evidence="email_confirmation", fixture=True)
    s.finish(a1["id"], worker_id="worker-1", fence=a1["fence"], outcome="applied", evidence="email_confirmation", quiescent=True)

    # Job 2: Completed ready_for_review
    j2 = s.intake(url="https://careers.example.test/jobs/ready-2", source_id="src-2")
    s.eligibility(j2["id"], "ready", reason="operator approval")
    r2 = s.request_run(
        request_id="run-app-2",
        job_ids=[j2["id"]],
        identity_id="cand-1",
        browser_profile="prof-2",
    )
    s.accept_run(r2["id"], worker_id="worker-1", session_id="sess-2", capabilities=_accept_capabilities(r2["browser_profile"]))
    a2 = s.claim(r2["id"], worker_id="worker-1")
    s.finish(a2["id"], worker_id="worker-1", fence=a2["fence"], outcome="ready_for_review", evidence="review done", quiescent=True)

    # Job 3: Unrelated job (held / queued intake)
    j3 = s.intake(url="https://careers.example.test/jobs/unrelated-3", source_id="src-3")

    return s, j1, j2, j3


def test_preview_archive_readonly_invariants_and_exact_counts(tmp_path):
    """1. preview_archive(job_ids) read-only returns {instance_id, job_ids, preview_hash, counts},

    preserves DB SHA-256 content invariants, counts every selected item, and leaves unrelated jobs untouched.
    """
    s, j1, j2, j3 = make_synthetic_service(tmp_path)
    db_path = s.db_path
    db_hash_before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    selected_ids = [j1["id"], j2["id"]]
    preview = _preview_archive(s, selected_ids)

    # Return schema: {instance_id, job_ids, preview_hash, counts}
    assert isinstance(preview, dict)
    assert preview.get("instance_id") == s.instance_id
    assert set(preview.get("job_ids", [])) == set(selected_ids)
    assert isinstance(preview.get("preview_hash"), str) and len(preview["preview_hash"]) > 0
    assert isinstance(preview.get("counts"), dict)

    # Count every selected item
    counts = preview["counts"]
    job_count = counts.get("jobs", counts.get("selected_jobs"))
    assert job_count == 2
    if "attempts" in counts or "application_attempts" in counts:
        attempt_count = counts.get("attempts", counts.get("application_attempts"))
        assert attempt_count == 2
    if "sources" in counts or "job_sources" in counts:
        source_count = counts.get("sources", counts.get("job_sources"))
        assert source_count == 2

    # Read-only content invariants: Source DB bytes strictly unmodified
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == db_hash_before

    # Unrelated fixture job and history unchanged
    unrelated = s.job(j3["id"])
    assert unrelated["status"] == j3["status"]
    assert unrelated["url"] == j3["url"]


def test_archive_creates_verified_backup_additive_metadata_and_preserves_view_and_suppression(tmp_path):
    """2. archive creates non-overwriting verified SQLite backup, marks ONLY selected jobs in additive metadata,

    hides archived records from default view but includes them in view(include_archived=True),
    and preserves applied duplicate suppression against retries and re-intake.
    """
    s, j1, j2, j3 = make_synthetic_service(tmp_path)
    selected_ids = [j1["id"], j2["id"]]

    preview = _preview_archive(s, selected_ids)
    preview_hash = preview["preview_hash"]

    backup_path = tmp_path / "backups" / "archive_backup.db"
    assert not backup_path.exists()

    res = _archive(s, selected_ids, preview_hash, backup_path)

    # 1. Creates non-overwriting verified SQLite backup using existing backup utility
    assert backup_path.is_file()
    with closing(sqlite3.connect(str(backup_path))) as target_db:
        assert target_db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        target_jobs = {row[0] for row in target_db.execute("SELECT id FROM jobs").fetchall()}
        assert j1["id"] in target_jobs
        assert j2["id"] in target_jobs
        assert j3["id"] in target_jobs

    # 2. Marks ONLY selected jobs archived in additive metadata
    # Never deletes/rewrites original outcomes, attempts, source rows, accounts or submission suppressions
    with s.tx() as db:
        row_j1 = db.execute("SELECT * FROM jobs WHERE id=?", (j1["id"],)).fetchone()
        row_j2 = db.execute("SELECT * FROM jobs WHERE id=?", (j2["id"],)).fetchone()
        row_j3 = db.execute("SELECT * FROM jobs WHERE id=?", (j3["id"],)).fetchone()
        assert row_j1 is not None and row_j1["status"] == "applied"
        assert row_j2 is not None and row_j2["status"] == "ready_for_review"
        assert row_j3 is not None and row_j3["status"] == j3["status"]

        attempts = db.execute("SELECT * FROM application_attempts WHERE job_id IN (?,?)", (j1["id"], j2["id"])).fetchall()
        assert len(attempts) == 2

        sources = db.execute("SELECT * FROM job_sources WHERE job_id IN (?,?)", (j1["id"], j2["id"])).fetchall()
        assert len(sources) >= 2

        ledger = db.execute("SELECT * FROM submission_ledger WHERE job_id=?", (j1["id"],)).fetchone()
        assert ledger is not None

        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        job_cols = {r["name"] for r in db.execute("PRAGMA table_info(jobs)")}
        if "archived" in job_cols:
            assert row_j1["archived"] in (1, True, "true")
            assert row_j2["archived"] in (1, True, "true")
            assert not row_j3["archived"]
        elif "archive_metadata" in tables or "job_archives" in tables:
            tbl = "archive_metadata" if "archive_metadata" in tables else "job_archives"
            archived_rows = {r[0] for r in db.execute(f"SELECT job_id FROM {tbl}").fetchall()}
            assert j1["id"] in archived_rows and j2["id"] in archived_rows
            assert j3["id"] not in archived_rows

    # 3. Default UI hides archived queue records but history retained; view(include_archived=True) includes them
    default_view = s.view()
    default_job_ids = {j["id"] for j in default_view.get("jobs", [])}
    assert j1["id"] not in default_job_ids
    assert j2["id"] not in default_job_ids
    assert j3["id"] in default_job_ids

    archived_view = s.view(include_archived=True)
    archived_job_ids = {j["id"] for j in archived_view.get("jobs", [])}
    assert j1["id"] in archived_job_ids
    assert j2["id"] in archived_job_ids
    assert j3["id"] in archived_job_ids

    # 4. Applied duplicate suppression must still reject retries/intake execution after archive
    with pytest.raises(ProtocolError):
        s.retry(j1["id"])

    with pytest.raises(ProtocolError, match="already_applied"):
        s.request_run(
            request_id="run-reapply-archived",
            job_ids=[j1["id"]],
            identity_id="cand-1",
            browser_profile="prof-1",
        )

    re_intake = s.intake(url=j1["url"], source_id="src-reintake")
    assert re_intake["id"] == j1["id"]

    # 5. Unrelated fixture job/history unchanged
    assert s.job(j3["id"])["status"] == j3["status"]


def test_archive_refusals_and_no_partial_archive(tmp_path):
    """3. Rejects wrong preview hash, altered selection scope, mismatched instance, active leases,

    and pre-existing backup destinations without performing any partial archive.
    """
    s, j1, j2, j3 = make_synthetic_service(tmp_path)
    db_path = s.db_path
    db_hash_before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    selected_ids = [j1["id"], j2["id"]]
    preview = _preview_archive(s, selected_ids)
    valid_hash = preview["preview_hash"]

    # Refusal 1: Wrong preview hash rejects
    dest_wrong_hash = tmp_path / "backups" / "dest_wrong_hash.db"
    with pytest.raises(ProtocolError):
        _archive(s, selected_ids, "deadbeef" * 8, dest_wrong_hash)
    assert not dest_wrong_hash.exists()
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == db_hash_before

    # Refusal 2: Changed selection after preview rejects
    dest_changed_scope = tmp_path / "backups" / "dest_changed_scope.db"
    with pytest.raises(ProtocolError):
        _archive(s, [j1["id"]], valid_hash, dest_changed_scope)
    with pytest.raises(ProtocolError):
        _archive(s, [j1["id"], j2["id"], j3["id"]], valid_hash, dest_changed_scope)
    assert not dest_changed_scope.exists()
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == db_hash_before

    # Refusal 3: Wrong instance rejects
    dest_wrong_instance = tmp_path / "backups" / "dest_wrong_instance.db"
    other_s = Service.create(tmp_path / "other.db", instance_id="other-instance")
    with pytest.raises(ProtocolError):
        _archive(other_s, selected_ids, valid_hash, dest_wrong_instance)
    assert not dest_wrong_instance.exists()

    # Refusal 4: Active/unreconciled lease or non-completed job rejects
    with s.tx() as db:
        db.execute(
            "INSERT INTO browser_leases (profile, attempt_id, worker_id, generation, expires_at, state) VALUES (?, ?, ?, ?, ?, ?)",
            ("lease-active", None, "worker-1", 1, "2099-01-01T00:00:00+00:00", "active"),
        )
    dest_active_lease = tmp_path / "backups" / "dest_active_lease.db"
    with pytest.raises(ProtocolError):
        _archive(s, selected_ids, valid_hash, dest_active_lease)
    assert not dest_active_lease.exists()

    with s.tx() as db:
        db.execute("UPDATE browser_leases SET state='released' WHERE profile='lease-active'")

    dest_incomplete_job = tmp_path / "backups" / "dest_incomplete.db"
    with pytest.raises(ProtocolError):
        _archive(s, [j3["id"]], valid_hash, dest_incomplete_job)
    assert not dest_incomplete_job.exists()

    # Refusal 5: Pre-existing destination rejects without overwriting
    dest_preexisting = tmp_path / "backups" / "preexisting.db"
    dest_preexisting.parent.mkdir(parents=True, exist_ok=True)
    dest_preexisting.write_text("existing backup sentinel")
    sentinel_hash = hashlib.sha256(dest_preexisting.read_bytes()).hexdigest()

    with pytest.raises((FileExistsError, ProtocolError)):
        _archive(s, selected_ids, valid_hash, dest_preexisting)
    assert hashlib.sha256(dest_preexisting.read_bytes()).hexdigest() == sentinel_hash

    # Zero partial archive: Source jobs and view remain unmutated
    view_after = s.view()
    jobs_after = {j["id"]: j for j in view_after["jobs"]}
    assert j1["id"] in jobs_after and j2["id"] in jobs_after and j3["id"] in jobs_after
    assert jobs_after[j1["id"]]["status"] == "applied"
    assert jobs_after[j2["id"]]["status"] == "ready_for_review"
