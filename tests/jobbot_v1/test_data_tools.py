"""Data tools acceptance tests for JobBot managed fresh starts, migrations, and backups.

Verifies:
1) preview_new:
   - Returns {'allowed': True} when DB and sidecars are absent.
   - Returns {'allowed': False} (or False) when DB or sidecars (-wal, -shm, -journal) exist.
   - Does not create or delete files.
   - Rejects relative paths with ProtocolError.
2) migrate_copy:
   - Synthesizes legacy source DB using original DatabaseManager with an applied job, attempt, and account.
   - Rejects mismatched expected source sha256 before copying.
   - Rejects pre-existing destination.
   - Rejects repeated runs against the same destination.
   - Preserves source hash unchanged.
   - Produces usable managed Service at destination.
   - Populates suppression ledger to protect old applied status against retry/re-apply.
3) backup:
   - Validates exact instance ID match; rejects mismatch.
   - Rejects pre-existing destination.
   - Rejects backup when an active browser lease is held.
   - Preserves record counts and integrity on fresh managed service fixtures.
   - Leaves source DB unchanged.
"""
import hashlib
from pathlib import Path
import pytest

from job_applier.database import (
    DatabaseManager,
    Job,
    ApplicationAttempt,
    CompanyPortalAccount,
)
from job_applier.managed import Service, ProtocolError
from job_applier.managed_data import preview_new, migrate_copy, backup


def test_preview_new_checks_sidecars_and_rejects_relative(tmp_path):
    # 1. Target path does not exist and sidecars absent -> allowed
    target = tmp_path / "fresh" / "target.db"
    res = preview_new(target)
    is_allowed = res.get("allowed") if isinstance(res, dict) else res
    assert is_allowed is True
    # Verify no file was created
    assert not target.exists()

    # 2. Target file already exists -> disallowed, file preserved
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    res_exist = preview_new(target)
    is_allowed_exist = res_exist.get("allowed") if isinstance(res_exist, dict) else res_exist
    assert is_allowed_exist is False
    assert target.exists()  # Not deleted

    # 3. Sidecars exist (-wal, -shm, -journal) -> disallowed
    target_sidecar = tmp_path / "fresh_sidecar.db"
    wal_file = tmp_path / "fresh_sidecar.db-wal"
    wal_file.touch()
    res_wal = preview_new(target_sidecar)
    is_allowed_wal = res_wal.get("allowed") if isinstance(res_wal, dict) else res_wal
    assert is_allowed_wal is False
    assert wal_file.exists()  # Not deleted

    # 4. Relative paths -> ProtocolError
    with pytest.raises(ProtocolError):
        preview_new("relative_path.db")
    with pytest.raises(ProtocolError):
        preview_new(Path("relative_path.db"))


def test_migrate_copy_with_hash_suppression_and_rejections(tmp_path):
    # 1. Synthesize legacy source DB using original DatabaseManager
    source_path = tmp_path / "legacy_source.db"
    mgr = DatabaseManager(str(source_path))
    session = mgr.get_session()
    legacy_job = Job(
        id="legacy-job-applied-1",
        url="https://careers.example.test/jobs/legacy-1",
        title="Legacy Staff Engineer",
        company="Legacy Tech",
        status="applied",
    )
    session.add(legacy_job)
    legacy_attempt = ApplicationAttempt(
        job_id="legacy-job-applied-1",
        platform="greenhouse",
        outcome="applied",
        evidence="legacy_confirmation_email",
    )
    session.add(legacy_attempt)
    legacy_account = CompanyPortalAccount(
        company_key="legacy-tech",
        company_name="Legacy Tech",
        platform="greenhouse",
        portal_key="legacy-tech-portal",
        email="candidate@example.test",
        status="confirmed",
    )
    session.add(legacy_account)
    session.commit()
    session.close()
    mgr.close()

    source_bytes = source_path.read_bytes()
    expected_hash = hashlib.sha256(source_bytes).hexdigest()

    # 2. Wrong expected source hash rejects before copying; destination not created
    dest_wrong_hash = tmp_path / "never_created.db"
    with pytest.raises(ProtocolError):
        migrate_copy(
            source_path,
            dest_wrong_hash,
            instance_id="fixture-migrated",
            expected_source_sha256="0000000000000000000000000000000000000000000000000000000000000000",
        )
    assert not dest_wrong_hash.exists()

    # 3. Pre-existing destination rejects
    dest_preexisting = tmp_path / "preexisting.db"
    dest_preexisting.touch()
    with pytest.raises((FileExistsError, ProtocolError)):
        migrate_copy(
            source_path,
            dest_preexisting,
            instance_id="fixture-migrated",
            expected_source_sha256=expected_hash,
        )

    # 4. Valid migrate_copy execution
    dest_path = tmp_path / "migrated.db"
    migrate_copy(
        source_path,
        dest_path,
        instance_id="fixture-migrated",
        expected_source_sha256=expected_hash,
    )

    # 5. Source hash unchanged
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == expected_hash

    # 6. Re-run on same target refuses
    with pytest.raises((FileExistsError, ProtocolError)):
        migrate_copy(
            source_path,
            dest_path,
            instance_id="fixture-migrated",
            expected_source_sha256=expected_hash,
        )

    # 7. Destination migrated service is usable
    migrated_service = Service(dest_path, instance_id="fixture-migrated")
    assert migrated_service.health()["instance_id"] == "fixture-migrated"
    migrated_job = migrated_service.job("legacy-job-applied-1")
    assert migrated_job["status"] == "applied"

    # 8. Suppression ledger protects old applied status against retry and re-run
    with migrated_service.tx() as db:
        ledger_row = db.execute(
            "SELECT * FROM submission_ledger WHERE job_id=?",
            ("legacy-job-applied-1",),
        ).fetchone()
        assert ledger_row is not None

    with pytest.raises(ProtocolError, match="already_applied"):
        migrated_service.retry("legacy-job-applied-1")

    migrated_service.identity(
        identity_id="cand-new",
        person_key="person-1",
        email="new@example.test",
        profile={"facts": {"auth": "ok"}},
    )
    with pytest.raises(ProtocolError, match="already_applied"):
        migrated_service.request_run(
            request_id="req-reapply",
            job_ids=["legacy-job-applied-1"],
            identity_id="cand-new",
            browser_profile="prof-1",
        )


def test_backup_preserves_counts_and_rejects_mismatch_and_leases(tmp_path):
    # 1. Fresh source service with two jobs and no active run
    source_path = tmp_path / "backup_src.db"
    s = Service.create(
        source_path,
        instance_id="backup-fixture",
        settings={"mode": "development"},
    )
    j1 = s.intake(url="https://careers.example.test/jobs/b1", source_id="src-b1")
    j2 = s.intake(url="https://careers.example.test/jobs/b2", source_id="src-b2")
    source_hash_before = hashlib.sha256(source_path.read_bytes()).hexdigest()

    # 2. Instance ID mismatch rejects; destination not created
    dest_mismatch = tmp_path / "dest_mismatch.db"
    with pytest.raises(ProtocolError):
        backup(source_path, dest_mismatch, instance_id="wrong-instance-id")
    assert not dest_mismatch.exists()

    # 3. Pre-existing destination rejects
    dest_preexisting = tmp_path / "dest_preexisting.db"
    dest_preexisting.touch()
    with pytest.raises((FileExistsError, ProtocolError)):
        backup(source_path, dest_preexisting, instance_id="backup-fixture")

    # 4. Active browser lease in source rejects backup
    with s.tx() as db:
        db.execute(
            "INSERT INTO browser_leases (profile, attempt_id, worker_id, generation, expires_at, state) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("lease-profile-1", None, "worker-1", 1, "2099-01-01T00:00:00+00:00", "active"),
        )
    dest_active_lease = tmp_path / "dest_active_lease.db"
    with pytest.raises(ProtocolError):
        backup(source_path, dest_active_lease, instance_id="backup-fixture")
    assert not dest_active_lease.exists()

    # Clear active lease to test successful backup
    with s.tx() as db:
        db.execute("UPDATE browser_leases SET state='released' WHERE profile=?", ("lease-profile-1",))

    # Re-calculate hash after clearing lease
    source_hash_clean = hashlib.sha256(source_path.read_bytes()).hexdigest()

    # 5. Successful backup
    dest_success = tmp_path / "backup_success.db"
    backup(source_path, dest_success, instance_id="backup-fixture")

    # Source hash unchanged
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_hash_clean

    # Backup destination preserves counts and records
    b_service = Service(dest_success, instance_id="backup-fixture")
    assert b_service.job(j1["id"])["url"] == j1["url"]
    assert b_service.job(j2["id"])["url"] == j2["url"]
    with b_service.tx() as db:
        count = db.execute("SELECT count(*) FROM jobs").fetchone()[0]
        assert count == 2
