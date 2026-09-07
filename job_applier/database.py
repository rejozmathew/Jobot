"""Database Layer - SQLite storage for job tracking and diagnostics."""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey, UniqueConstraint, Enum as SQLEnum, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from sqlalchemy.pool import StaticPool

# Base for all models
Base = declarative_base()


class JobStatus(str, Enum):
    """Status of a queued job."""
    QUEUED = "queued"
    RUNNING = "running"
    APPLIED = "applied"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class StepResult(str, Enum):
    """Result of an application step."""
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"
    SKIPPED = "skipped"


class ScreenshotType(str, Enum):
    """Type of screenshot captured."""
    STEP = "step"
    ERROR = "error"
    SUCCESS = "success"
    FINAL = "final"
    NEEDS_REVIEW = "needs_review"


# =============================================================================
# ORM Models
# =============================================================================

class Job(Base):
    """Core job queue table - replaces job_queue.json."""
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)  # UUID
    seq_id = Column(Integer, autoincrement=True, unique=True)  # Sequential display ID
    url = Column(Text, nullable=False)
    title = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    status = Column(String(20), default=JobStatus.QUEUED.value)
    priority = Column(Integer, default=0)
    notes = Column(Text, default="")
    error = Column(Text, default="")
    intervention_reason = Column(Text, nullable=True)
    screenshot_path = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)  # When processing began
    completed_at = Column(DateTime, nullable=True)  # When processing ended
    
    # Relationships
    steps = relationship("ApplicationStep", back_populates="job", cascade="all, delete-orphan")
    element_retries = relationship("ElementRetry", back_populates="job", cascade="all, delete-orphan")
    screenshots = relationship("Screenshot", back_populates="job", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "seq_id": self.seq_id,
            "url": self.url,
            "title": self.title,
            "company": self.company,
            "status": self.status,
            "priority": self.priority,
            "notes": self.notes,
            "error": self.error,
            "intervention_reason": self.intervention_reason,
            "screenshot_path": self.screenshot_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "step_count": len(self.steps) if self.steps else 0,
        }


class ApplicationStep(Base):
    """Tracks each step in the application process."""
    __tablename__ = "application_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    
    # Action details
    action_type = Column(String(50))  # 'click', 'input', 'scroll', 'navigate', etc.
    element_description = Column(Text)  # Human-readable description
    element_selector = Column(Text)  # CSS/XPath selector if available
    input_value = Column(Text)  # What was typed (masked for passwords)
    
    # Result tracking
    result = Column(String(20), default=StepResult.SUCCESS.value)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    screenshot_path = Column(Text, nullable=True)
    
    # Timing
    timestamp = Column(DateTime, default=datetime.utcnow)
    duration_ms = Column(Integer, nullable=True)
    
    # Page context
    page_url = Column(Text, nullable=True)
    page_title = Column(String(255), nullable=True)
    
    # Diagnostics
    step_memory = Column(Text, nullable=True)
    llm_thinking = Column(Text, nullable=True)
    next_goal = Column(Text, nullable=True)
    evaluation = Column(Text, nullable=True)
    
    # Relationships
    job = relationship("Job", back_populates="steps")

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "step_number": self.step_number,
            "action_type": self.action_type,
            "element_description": self.element_description,
            "element_selector": self.element_selector,
            "input_value": self.input_value,
            "result": self.result,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
            "screenshot_path": self.screenshot_path,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "duration_ms": self.duration_ms,
            "page_url": self.page_url,
            "page_title": self.page_title,
            "step_memory": self.step_memory,
            "llm_thinking": self.llm_thinking,
            "next_goal": self.next_goal,
            "evaluation": self.evaluation,
        }


class ElementRetry(Base):
    """Tracks elements that required multiple attempts."""
    __tablename__ = "element_retries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False)
    
    element_selector = Column(Text)
    element_description = Column(Text)
    attempt_count = Column(Integer, default=1)
    
    first_attempt_at = Column(DateTime, default=datetime.utcnow)
    last_attempt_at = Column(DateTime, default=datetime.utcnow)
    
    resolved = Column(Boolean, default=False)
    resolution_method = Column(String(50), nullable=True)  # 'success', 'skipped', 'manual'
    
    # Relationships
    job = relationship("Job", back_populates="element_retries")

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "element_selector": self.element_selector,
            "element_description": self.element_description,
            "attempt_count": self.attempt_count,
            "first_attempt_at": self.first_attempt_at.isoformat() if self.first_attempt_at else None,
            "last_attempt_at": self.last_attempt_at.isoformat() if self.last_attempt_at else None,
            "resolved": self.resolved,
            "resolution_method": self.resolution_method,
        }


class Screenshot(Base):
    """Stores screenshot metadata."""
    __tablename__ = "screenshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False)
    step_id = Column(Integer, ForeignKey("application_steps.id"), nullable=True)
    
    screenshot_type = Column(String(20))  # 'step', 'error', 'success', 'final'
    file_path = Column(Text, nullable=False)
    
    captured_at = Column(DateTime, default=datetime.utcnow)
    page_url = Column(Text, nullable=True)
    page_title = Column(String(255), nullable=True)
    
    # Relationships
    job = relationship("Job", back_populates="screenshots")

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "step_id": self.step_id,
            "screenshot_type": self.screenshot_type,
            "file_path": self.file_path,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
            "page_url": self.page_url,
            "page_title": self.page_title,
        }


class ApplicationAttempt(Base):
    """One end-to-end attempt to apply for a tracked job."""
    __tablename__ = "application_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False, index=True)
    platform = Column(String(50), nullable=False)
    workflow = Column(String(100), nullable=True)
    outcome = Column(String(50), nullable=True)
    evidence = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    meets_target = Column(Boolean, nullable=True)


class AttemptPhase(Base):
    """Measured phase within an application attempt."""
    __tablename__ = "attempt_phases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    attempt_id = Column(Integer, ForeignKey("application_attempts.id"), nullable=False, index=True)
    phase = Column(String(50), nullable=False)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    note = Column(Text, nullable=True)


class ApplicationHiccup(Base):
    """Portal-specific friction, its resolution, and reusable fix."""
    __tablename__ = "application_hiccups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    attempt_id = Column(Integer, ForeignKey("application_attempts.id"), nullable=False, index=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False, index=True)
    platform = Column(String(50), nullable=False, index=True)
    phase = Column(String(50), nullable=True)
    category = Column(String(100), nullable=False, index=True)
    field_label = Column(Text, nullable=True)
    description = Column(Text, nullable=False)
    resolution = Column(Text, nullable=True)
    reusable_fix = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="resolved")
    seconds_lost = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CompanyPortalAccount(Base):
    """Known candidate account for a company-specific ATS portal."""
    __tablename__ = "company_portal_accounts"
    __table_args__ = (UniqueConstraint("portal_key", "email", name="uq_portal_account_email"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_key = Column(String(255), nullable=False, index=True)
    company_name = Column(String(255), nullable=False)
    platform = Column(String(50), nullable=False, index=True)
    portal_key = Column(String(255), nullable=False, index=True)
    email = Column(String(320), nullable=False)
    status = Column(String(30), nullable=False, default="confirmed")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_successful_login_at = Column(DateTime, nullable=True)


# =============================================================================
# Database Manager
# =============================================================================

class DatabaseManager:
    """Manages database connections and provides helper methods."""

    def __init__(self, db_path: str = "./job_applier.db"):
        self.db_path = Path(db_path)
        self.db_url = f"sqlite:///{self.db_path.resolve()}"
        
        # Create engine with check_same_thread=False for async compatibility
        self.engine = create_engine(
            self.db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,  # Set to True for SQL debugging
        )
        
        # Session factory
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # Create tables
        self.init_db()

    @property
    def is_managed(self) -> bool:
        with self.engine.connect() as connection:
            return connection.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE type='table' AND name='instance'").first() is not None

    def require_legacy(self) -> None:
        if self.is_managed:
            from .managed_shared import ProtocolError
            raise ProtocolError('managed_worker_required')

    def init_db(self) -> None:
        """Create all tables if they don't exist."""
        Base.metadata.create_all(bind=self.engine)
        # Lightweight SQLite migration for older databases.
        with self.engine.begin() as conn:
            cols = conn.execute(text("PRAGMA table_info(application_steps)")).fetchall()
            col_names = {str(row[1]) for row in cols}
            if "llm_thinking" not in col_names:
                conn.execute(text("ALTER TABLE application_steps ADD COLUMN llm_thinking TEXT"))

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def close(self) -> None:
        """Close the database connection."""
        self.engine.dispose()


# =============================================================================
# Global database instance
# =============================================================================

_db_manager: Optional[DatabaseManager] = None


def get_db_manager(db_path: Optional[str] = None) -> DatabaseManager:
    """Get or create the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        path = db_path or os.getenv("JOB_APPLIER_DB_PATH", "./job_applier.db")
        _db_manager = DatabaseManager(db_path=path)
    return _db_manager


def get_session() -> Session:
    """Convenience function to get a session from the global manager."""
    return get_db_manager().get_session()
