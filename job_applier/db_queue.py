"""Database-backed Job Queue - SQLite implementation replacing JSON storage."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from .database import (
    get_db_manager, get_session,
    Job, ApplicationStep, Screenshot,
    JobStatus, ScreenshotType, StepResult
)


# =============================================================================
# Pydantic Models for API compatibility
# =============================================================================

class QueuedJob(BaseModel):
    """A job in the application queue - Pydantic model for API responses."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    seq_id: Optional[int] = None
    url: str
    title: Optional[str] = None
    company: Optional[str] = None
    status: str = JobStatus.QUEUED.value
    priority: int = 0
    notes: str = ""
    error: str = ""
    intervention_reason: Optional[str] = None
    screenshot_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    step_count: int = 0

    class Config:
        from_attributes = True

    def model_dump_json_safe(self) -> dict:
        """Convert to JSON-safe dict with datetime handling."""
        data = self.model_dump()
        data["created_at"] = self.created_at.isoformat() if self.created_at else None
        data["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        data["started_at"] = self.started_at.isoformat() if self.started_at else None
        data["completed_at"] = self.completed_at.isoformat() if self.completed_at else None
        return data

    @classmethod
    def from_db(cls, job: Job) -> "QueuedJob":
        """Create from database model."""
        return cls(
            id=job.id,
            seq_id=job.seq_id,
            url=job.url,
            title=job.title,
            company=job.company,
            status=job.status,
            priority=job.priority,
            notes=job.notes or "",
            error=job.error or "",
            intervention_reason=job.intervention_reason,
            screenshot_path=job.screenshot_path,
            created_at=job.created_at or datetime.utcnow(),
            updated_at=job.updated_at or datetime.utcnow(),
            started_at=job.started_at,
            completed_at=job.completed_at,
            step_count=len(job.steps) if job.steps else 0,
        )


class AddJobRequest(BaseModel):
    """Request to add a job to the queue."""
    url: str
    title: Optional[str] = None
    company: Optional[str] = None
    priority: int = 0
    notes: Optional[str] = None


# =============================================================================
# Database-backed Job Queue
# =============================================================================

class JobQueueDB:
    """Database-backed job queue replacing JSON file storage."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize with optional custom database path."""
        self.db_manager = get_db_manager(db_path)

    def _get_next_seq_id(self, session) -> int:
        """Get the next sequential ID for a job."""
        from sqlalchemy import func
        max_seq = session.query(func.max(Job.seq_id)).scalar()
        return (max_seq or 0) + 1

    def list_all(self) -> List[QueuedJob]:
        """Get all jobs in the queue."""
        session = get_session()
        try:
            jobs = session.query(Job).order_by(Job.created_at.desc()).all()
            return [QueuedJob.from_db(job) for job in jobs]
        finally:
            session.close()

    def list_by_status(self, status: JobStatus) -> List[QueuedJob]:
        """Get jobs with a specific status."""
        session = get_session()
        try:
            jobs = session.query(Job).filter(Job.status == status.value).all()
            return [QueuedJob.from_db(job) for job in jobs]
        finally:
            session.close()

    def get(self, job_id: str) -> Optional[QueuedJob]:
        """Get a specific job by ID."""
        session = get_session()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            return QueuedJob.from_db(job) if job else None
        finally:
            session.close()

    def get_by_seq_id(self, seq_id: int) -> Optional[QueuedJob]:
        """Get a specific job by sequential ID."""
        session = get_session()
        try:
            job = session.query(Job).filter(Job.seq_id == seq_id).first()
            return QueuedJob.from_db(job) if job else None
        finally:
            session.close()

    def add(self, request: AddJobRequest) -> QueuedJob:
        """Add a new job to the queue."""
        session = get_session()
        try:
            seq_id = self._get_next_seq_id(session)
            job = Job(
                id=str(uuid.uuid4()),
                seq_id=seq_id,
                url=request.url.strip(),
                title=request.title.strip() if request.title else None,
                company=request.company.strip() if request.company else None,
                priority=request.priority,
                notes=request.notes.strip() if request.notes else "",
                status=JobStatus.QUEUED.value,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            return QueuedJob.from_db(job)
        finally:
            session.close()

    def add_urls(self, urls: List[str]) -> List[QueuedJob]:
        """Add multiple URLs to the queue."""
        session = get_session()
        try:
            jobs = []
            next_seq_id = self._get_next_seq_id(session)
            for url in urls:
                url = url.strip()
                if not url:
                    continue
                job = Job(
                    id=str(uuid.uuid4()),
                    seq_id=next_seq_id,
                    url=url,
                    status=JobStatus.QUEUED.value,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(job)
                jobs.append(job)
                next_seq_id += 1
            session.commit()
            
            # Refresh to get all fields
            for job in jobs:
                session.refresh(job)
            
            return [QueuedJob.from_db(job) for job in jobs]
        finally:
            session.close()

    def claim_next(self) -> Optional[QueuedJob]:
        """Claim the next queued job for processing (highest priority first)."""
        session = get_session()
        try:
            # Find highest priority queued job
            job = (
                session.query(Job)
                .filter(Job.status == JobStatus.QUEUED.value)
                .order_by(Job.priority.desc(), Job.created_at.asc())
                .first()
            )
            
            if not job:
                return None
            
            # Mark as running
            job.status = JobStatus.RUNNING.value
            job.updated_at = datetime.utcnow()
            job.started_at = datetime.utcnow()
            session.commit()
            session.refresh(job)
            
            return QueuedJob.from_db(job)
        finally:
            session.close()

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
        session = get_session()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None
            
            job.status = status.value
            job.updated_at = datetime.utcnow()
            
            # Set completed_at for terminal states
            if status in [JobStatus.APPLIED, JobStatus.FAILED, JobStatus.NEEDS_REVIEW]:
                job.completed_at = datetime.utcnow()
            
            if notes is not None:
                job.notes = notes
            if error is not None:
                job.error = error
            if intervention_reason is not None:
                job.intervention_reason = intervention_reason
            if screenshot_path is not None:
                job.screenshot_path = screenshot_path
            
            session.commit()
            session.refresh(job)
            return QueuedJob.from_db(job)
        finally:
            session.close()

    def delete(self, job_id: str) -> bool:
        """Remove a job from the queue."""
        session = get_session()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return False
            session.delete(job)
            session.commit()
            return True
        finally:
            session.close()

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
        session = get_session()
        try:
            total = session.query(Job).count()
            queued = session.query(Job).filter(Job.status == JobStatus.QUEUED.value).count()
            running = session.query(Job).filter(Job.status == JobStatus.RUNNING.value).count()
            applied = session.query(Job).filter(Job.status == JobStatus.APPLIED.value).count()
            needs_review = session.query(Job).filter(Job.status == JobStatus.NEEDS_REVIEW.value).count()
            failed = session.query(Job).filter(Job.status == JobStatus.FAILED.value).count()
            
            return {
                "total": total,
                "queued": queued,
                "running": running,
                "applied": applied,
                "needs_review": needs_review,
                "failed": failed,
            }
        finally:
            session.close()

    def cleanup_stuck_jobs(self) -> int:
        """Reset jobs stuck in 'running' state to 'failed' on startup."""
        session = get_session()
        try:
            stuck_jobs = session.query(Job).filter(Job.status == JobStatus.RUNNING.value).all()
            count = 0
            for job in stuck_jobs:
                job.status = JobStatus.FAILED.value
                job.error = "System restart/crash during execution"
                count += 1
            session.commit()
            return count
        except Exception as e:
            print(f"Error cleaning stuck jobs: {e}")
            return 0
        finally:
            session.close()

    # =========================================================================
    # Step Management
    # =========================================================================

    def add_step(
        self, 
        job_id: str, 
        step_number: int, 
        action_type: str, 
        element_description: str,
        element_selector: Optional[str] = None,
        input_value: Optional[str] = None,
        result: str = "success",
        error_message: Optional[str] = None,
        page_url: Optional[str] = None,
        step_memory: Optional[str] = None,
        llm_thinking: Optional[str] = None,
        next_goal: Optional[str] = None,
        evaluation: Optional[str] = None,
    ) -> ApplicationStep:
        """Add a step to the database."""
        session = get_session()
        try:
            step = ApplicationStep(
                job_id=job_id,
                step_number=step_number,
                action_type=action_type,
                element_description=element_description,
                element_selector=element_selector,
                input_value=input_value,
                result=result,
                error_message=error_message,
                page_url=page_url,
                step_memory=step_memory,
                llm_thinking=llm_thinking,
                next_goal=next_goal,
                evaluation=evaluation,
                timestamp=datetime.utcnow(),
            )
            session.add(step)
            session.commit()
            session.refresh(step)
            return step
        finally:
            session.close()

    def update_step(
        self, 
        step_id: int, 
        result: str, 
        error_message: Optional[str] = None, 
        duration_ms: Optional[int] = None
    ) -> None:
        """Update the result of an existing step."""
        session = get_session()
        try:
            step = session.query(ApplicationStep).filter(ApplicationStep.id == step_id).first()
            if step:
                step.result = result
                if error_message is not None:
                    step.error_message = error_message
                if duration_ms is not None:
                    step.duration_ms = duration_ms
                session.commit()
        finally:
            session.close()

    def get_steps(self, job_id: str) -> List[dict]:
        """Get all steps for a job."""
        session = get_session()
        try:
            steps = (
                session.query(ApplicationStep)
                .filter(ApplicationStep.job_id == job_id)
                .order_by(ApplicationStep.step_number)
                .all()
            )
            return [step.to_dict() for step in steps]
        finally:
            session.close()

    def clear_steps(self, job_id: str) -> None:
        """Delete all steps for a given job to prepare for retry."""
        session = get_session()
        try:
            session.query(ApplicationStep).filter(ApplicationStep.job_id == job_id).delete()
            session.commit()
        except Exception as e:
            print(f"Error clearing steps for job {job_id}: {e}")
        finally:
            session.close()

    def increment_step_retry(self, job_id: str, step_number: int) -> int:
        """Increment retry count for a step, return new count."""
        session = get_session()
        try:
            step = (
                session.query(ApplicationStep)
                .filter(ApplicationStep.job_id == job_id, ApplicationStep.step_number == step_number)
                .first()
            )
            if step:
                step.retry_count += 1
                step.result = StepResult.RETRY.value
                session.commit()
                return step.retry_count
            return 0
        finally:
            session.close()

    # =========================================================================
    # Screenshot Methods
    # =========================================================================

    def add_screenshot(
        self,
        job_id: str,
        file_path: str,
        screenshot_type: str = ScreenshotType.STEP.value,
        step_id: Optional[int] = None,
        page_url: Optional[str] = None,
        page_title: Optional[str] = None,
    ) -> Screenshot:
        """Add a screenshot record."""
        session = get_session()
        try:
            screenshot = Screenshot(
                job_id=job_id,
                step_id=step_id,
                screenshot_type=screenshot_type,
                file_path=file_path,
                captured_at=datetime.utcnow(),
                page_url=page_url,
                page_title=page_title,
            )
            session.add(screenshot)
            session.commit()
            session.refresh(screenshot)
            return screenshot
        finally:
            session.close()

    def get_screenshots(self, job_id: str) -> List[dict]:
        """Get all screenshots for a job."""
        session = get_session()
        try:
            screenshots = (
                session.query(Screenshot)
                .filter(Screenshot.job_id == job_id)
                .order_by(Screenshot.captured_at)
                .all()
            )
            return [s.to_dict() for s in screenshots]
        finally:
            session.close()


# =============================================================================
# Backwards Compatibility Alias
# =============================================================================

# Use this as a drop-in replacement for the old JobQueue
JobQueue = JobQueueDB
