"""Job Queue Management - Persistent queue for job applications."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Status of a queued job."""
    QUEUED = "queued"
    RUNNING = "running"
    APPLIED = "applied"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class QueuedJob(BaseModel):
    """A job in the application queue."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    title: Optional[str] = None
    company: Optional[str] = None
    status: JobStatus = JobStatus.QUEUED
    priority: int = 0  # Higher = more urgent
    notes: str = ""
    error: str = ""
    intervention_reason: Optional[str] = None
    screenshot_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def model_dump_json_safe(self) -> dict:
        """Convert to JSON-safe dict with datetime handling."""
        data = self.model_dump()
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        data["status"] = self.status.value
        return data


class AddJobRequest(BaseModel):
    """Request to add a job to the queue."""
    url: str
    title: Optional[str] = None
    company: Optional[str] = None
    priority: int = 0
    notes: Optional[str] = None


class JobQueue:
    """Persistent job queue with JSON file storage."""

    def __init__(self, path: str = "./job_queue.json"):
        self.path = Path(path)
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Create queue file if it doesn't exist."""
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._save([])

    def _load(self) -> List[dict]:
        """Load queue from file."""
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, data: List[dict]) -> None:
        """Save queue to file."""
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_all(self) -> List[QueuedJob]:
        """Get all jobs in the queue."""
        data = self._load()
        jobs = []
        for item in data:
            try:
                # Handle datetime parsing
                if isinstance(item.get("created_at"), str):
                    item["created_at"] = datetime.fromisoformat(item["created_at"])
                if isinstance(item.get("updated_at"), str):
                    item["updated_at"] = datetime.fromisoformat(item["updated_at"])
                jobs.append(QueuedJob.model_validate(item))
            except Exception:
                continue
        return jobs

    def list_by_status(self, status: JobStatus) -> List[QueuedJob]:
        """Get jobs with a specific status."""
        return [job for job in self.list_all() if job.status == status]

    def get(self, job_id: str) -> Optional[QueuedJob]:
        """Get a specific job by ID."""
        for job in self.list_all():
            if job.id == job_id:
                return job
        return None

    def add(self, request: AddJobRequest) -> QueuedJob:
        """Add a new job to the queue."""
        job = QueuedJob(
            url=request.url.strip(),
            title=request.title.strip() if request.title else None,
            company=request.company.strip() if request.company else None,
            priority=request.priority,
            notes=request.notes.strip() if request.notes else "",
        )
        data = self._load()
        data.append(job.model_dump_json_safe())
        self._save(data)
        return job

    def add_urls(self, urls: List[str]) -> List[QueuedJob]:
        """Add multiple URLs to the queue."""
        jobs = []
        data = self._load()
        for url in urls:
            url = url.strip()
            if not url:
                continue
            job = QueuedJob(url=url)
            data.append(job.model_dump_json_safe())
            jobs.append(job)
        self._save(data)
        return jobs

    def claim_next(self) -> Optional[QueuedJob]:
        """Claim the next queued job for processing (highest priority first)."""
        data = self._load()
        now = datetime.utcnow().isoformat()
        
        # Find queued jobs and sort by priority (descending)
        queued_indices = [
            (i, item) for i, item in enumerate(data) 
            if item.get("status") == JobStatus.QUEUED.value
        ]
        
        if not queued_indices:
            return None
        
        # Sort by priority (higher first), then by created_at (older first)
        queued_indices.sort(key=lambda x: (-x[1].get("priority", 0), x[1].get("created_at", "")))
        
        idx, item = queued_indices[0]
        item["status"] = JobStatus.RUNNING.value
        item["updated_at"] = now
        self._save(data)
        
        # Parse and return
        if isinstance(item.get("created_at"), str):
            item["created_at"] = datetime.fromisoformat(item["created_at"])
        if isinstance(item.get("updated_at"), str):
            item["updated_at"] = datetime.fromisoformat(item["updated_at"])
        return QueuedJob.model_validate(item)

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        notes: Optional[str] = None,
        error: Optional[str] = None,
        intervention_reason: Optional[str] = None,
        screenshot_path: Optional[str] = None,
    ) -> Optional[QueuedJob]:
        """Update job status and metadata."""
        data = self._load()
        now = datetime.utcnow().isoformat()
        
        for item in data:
            if item.get("id") == job_id:
                item["status"] = status.value
                item["updated_at"] = now
                if notes is not None:
                    item["notes"] = notes
                if error is not None:
                    item["error"] = error
                if intervention_reason is not None:
                    item["intervention_reason"] = intervention_reason
                if screenshot_path is not None:
                    item["screenshot_path"] = screenshot_path
                self._save(data)
                
                # Parse and return
                if isinstance(item.get("created_at"), str):
                    item["created_at"] = datetime.fromisoformat(item["created_at"])
                if isinstance(item.get("updated_at"), str):
                    item["updated_at"] = datetime.fromisoformat(item["updated_at"])
                return QueuedJob.model_validate(item)
        
        return None

    def delete(self, job_id: str) -> bool:
        """Remove a job from the queue."""
        data = self._load()
        original_len = len(data)
        data = [item for item in data if item.get("id") != job_id]
        if len(data) < original_len:
            self._save(data)
            return True
        return False

    def retry(self, job_id: str) -> Optional[QueuedJob]:
        """Reset a failed/needs_review job to queued status."""
        return self.update_status(
            job_id,
            JobStatus.QUEUED,
            error="",
            intervention_reason=None,
        )

    def get_stats(self) -> dict:
        """Get queue statistics."""
        jobs = self.list_all()
        return {
            "total": len(jobs),
            "queued": len([j for j in jobs if j.status == JobStatus.QUEUED]),
            "running": len([j for j in jobs if j.status == JobStatus.RUNNING]),
            "applied": len([j for j in jobs if j.status == JobStatus.APPLIED]),
            "needs_review": len([j for j in jobs if j.status == JobStatus.NEEDS_REVIEW]),
            "failed": len([j for j in jobs if j.status == JobStatus.FAILED]),
        }
