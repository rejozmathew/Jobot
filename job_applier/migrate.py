"""Migration utilities - Convert from JSON to SQLite database."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .database import get_db_manager, Job, JobStatus


def migrate_from_json(
    json_path: str = "./job_queue.json",
    db_path: Optional[str] = None,
    backup: bool = True,
) -> dict:
    """
    Migrate jobs from job_queue.json to SQLite database.
    
    Args:
        json_path: Path to the JSON queue file
        db_path: Optional custom database path
        backup: If True, rename JSON file to .json.bak after migration
    
    Returns:
        Dict with migration statistics
    """
    json_file = Path(json_path)
    
    if not json_file.exists():
        return {
            "status": "skipped",
            "message": f"No JSON file found at {json_path}",
            "migrated": 0,
            "failed": 0,
        }
    
    # Load JSON data
    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to parse JSON: {e}",
            "migrated": 0,
            "failed": 0,
        }
    
    if not data or not isinstance(data, list):
        return {
            "status": "skipped",
            "message": "JSON file is empty or not a list",
            "migrated": 0,
            "failed": 0,
        }
    
    # Initialize database
    db_manager = get_db_manager(db_path)
    session = db_manager.get_session()
    
    migrated = 0
    failed = 0
    errors = []
    
    try:
        for item in data:
            try:
                # Parse datetime fields
                created_at = item.get("created_at")
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)
                elif not created_at:
                    created_at = datetime.utcnow()
                
                updated_at = item.get("updated_at")
                if isinstance(updated_at, str):
                    updated_at = datetime.fromisoformat(updated_at)
                elif not updated_at:
                    updated_at = datetime.utcnow()
                
                # Check if job already exists
                existing = session.query(Job).filter(Job.id == item.get("id")).first()
                if existing:
                    # Update existing job
                    existing.status = item.get("status", JobStatus.QUEUED.value)
                    existing.notes = item.get("notes", "")
                    existing.error = item.get("error", "")
                    existing.intervention_reason = item.get("intervention_reason")
                    existing.screenshot_path = item.get("screenshot_path")
                    existing.updated_at = updated_at
                else:
                    # Create new job
                    job = Job(
                        id=item.get("id"),
                        url=item.get("url", ""),
                        title=item.get("title"),
                        company=item.get("company"),
                        status=item.get("status", JobStatus.QUEUED.value),
                        priority=item.get("priority", 0),
                        notes=item.get("notes", ""),
                        error=item.get("error", ""),
                        intervention_reason=item.get("intervention_reason"),
                        screenshot_path=item.get("screenshot_path"),
                        created_at=created_at,
                        updated_at=updated_at,
                    )
                    session.add(job)
                
                migrated += 1
                
            except Exception as e:
                failed += 1
                errors.append(f"Job {item.get('id', 'unknown')}: {e}")
        
        session.commit()
        
    finally:
        session.close()
    
    # Backup JSON file if requested
    if backup and migrated > 0:
        backup_path = json_file.with_suffix(".json.bak")
        json_file.rename(backup_path)
        
        # Create empty JSON file to prevent old code from breaking
        json_file.write_text("[]", encoding="utf-8")
    
    return {
        "status": "success" if failed == 0 else "partial",
        "message": f"Migrated {migrated} jobs, {failed} failed",
        "migrated": migrated,
        "failed": failed,
        "errors": errors if errors else None,
        "backup_path": str(backup_path) if backup and migrated > 0 else None,
    }


def check_migration_status(
    json_path: str = "./job_queue.json",
    db_path: Optional[str] = None,
) -> dict:
    """
    Check if migration is needed.
    
    Returns:
        Dict with status information
    """
    json_file = Path(json_path)
    db_manager = get_db_manager(db_path)
    
    # Check JSON file
    json_count = 0
    if json_file.exists():
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            json_count = len(data) if isinstance(data, list) else 0
        except Exception:
            json_count = -1  # Error reading
    
    # Check database
    session = db_manager.get_session()
    try:
        db_count = session.query(Job).count()
    finally:
        session.close()
    
    return {
        "json_file_exists": json_file.exists(),
        "json_job_count": json_count,
        "db_job_count": db_count,
        "migration_needed": json_count > 0 and db_count == 0,
        "db_path": str(db_manager.db_path),
    }


if __name__ == "__main__":
    # Run migration if executed directly
    import sys
    
    print("Checking migration status...")
    status = check_migration_status()
    print(f"  JSON jobs: {status['json_job_count']}")
    print(f"  DB jobs: {status['db_job_count']}")
    print(f"  DB path: {status['db_path']}")
    
    if status["migration_needed"]:
        print("\nMigration needed. Running migration...")
        result = migrate_from_json()
        print(f"  Status: {result['status']}")
        print(f"  Message: {result['message']}")
        if result.get("backup_path"):
            print(f"  Backup: {result['backup_path']}")
    else:
        print("\nNo migration needed.")
