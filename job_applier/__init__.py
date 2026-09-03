"""Job Applier package with lazy imports for browser-heavy components."""

from .database import JobStatus, get_db_manager, get_session
from .db_queue import AddJobRequest, JobQueue, JobQueueDB, QueuedJob
from .migrate import check_migration_status, migrate_from_json
from .application_tracker import ApplicationTracker

__all__ = [
    "JobApplyAgent",
    "JobQueue",
    "JobQueueDB",
    "QueuedJob",
    "AddJobRequest",
    "JobStatus",
    "JobRunner",
    "get_db_manager",
    "get_session",
    "migrate_from_json",
    "check_migration_status",
    "ApplicationTracker",
]


def __getattr__(name):
    """Load browser-use components only for commands that actually apply."""
    if name == "JobApplyAgent":
        from .agent import JobApplyAgent

        return JobApplyAgent
    if name == "JobRunner":
        from .runner import JobRunner

        return JobRunner
    raise AttributeError(name)
