"""Job Runner - Orchestrates queue processing and agent execution."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Dict, Any, Optional

from dotenv import load_dotenv

from .db_queue import JobQueue, QueuedJob
from .database import JobStatus
from .agent import JobApplyAgent

load_dotenv()


class JobRunner:
    """Orchestrates job queue processing."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        profile_path: Optional[str] = None,
        artifacts_dir: Optional[str] = None,
        max_steps: Optional[int] = None,
        max_history_items: Optional[int] = None,
        headless: bool = False,
    ):
        # Use database-backed queue
        self.queue = JobQueue(
            db_path=db_path or os.getenv("JOB_APPLIER_DB_PATH")
        )
        self.profile_path = profile_path or os.getenv("JOB_APPLIER_PROFILE_PATH", "./profile.json")
        self.artifacts_dir = artifacts_dir or os.getenv("JOB_APPLIER_ARTIFACTS_DIR", "./artifacts")
        self.max_steps = max_steps or int(os.getenv("JOB_APPLIER_MAX_STEPS", "30"))
        self.max_history_items = max_history_items or int(os.getenv("JOB_APPLIER_MAX_HISTORY", "10"))
        self.headless = headless
        self._running = False
        self._current_job: Optional[QueuedJob] = None
        self._current_agent: Optional[JobApplyAgent] = None
        self._current_task: Optional[asyncio.Task] = None
        
        # Cleanup stuck jobs from previous run
        cleaned = self.queue.cleanup_stuck_jobs()
        if cleaned > 0:
            print(f"🧹 Cleaned up {cleaned} stuck jobs from previous session")

    @property
    def is_running(self) -> bool:
        """Check if runner is currently processing a job."""
        return self._running

    @property
    def current_job(self) -> Optional[QueuedJob]:
        """Get the currently processing job."""
        return self._current_job
    
    def pause_current(self):
        """Pause the currently running agent."""
        if self._current_agent:
            self._current_agent.pause()

    def resume_current(self):
        """Resume the currently running agent."""
        if self._current_agent:
            self._current_agent.resume()

    def stop_current(self):
        """Stop the currently running agent immediately."""
        if self._current_task:
            print("🛑 Force stopping current task...")
            self._current_task.cancel()

    def _create_agent(self) -> JobApplyAgent:
        """Create a new agent instance with step tracking."""
        return JobApplyAgent(
            profile_path=self.profile_path,
            artifacts_dir=self.artifacts_dir,
            max_steps=self.max_steps,
            max_history_items=self.max_history_items,
            headless=self.headless,
            db_queue=self.queue,  # Pass queue for step tracking
        )

    async def run_specific(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Process a specific job by ID."""
        if self._running:
            return {"error": "Already processing a job", "job": None}

        # Claim specific job
        # We manually get it and update status
        job = self.queue.get(job_id)
        if not job:
            return None
        
        # Force status to running
        self._running = True
        self._current_job = job
        self.queue.update_status(job.id, JobStatus.RUNNING)
        
        # Track the task for cancellation
        self._current_task = asyncio.current_task()

        try:
            agent = self._create_agent()
            self._current_agent = agent
            result = await agent.apply(
                job_url=job.url,
                job_id=job.id,
                job_title=job.title,
                job_company=job.company,
            )
            # ... update status based on result (same as run_one) ...
            # Reuse logic by extraction? Or copy paste for now to save time
            status_map = {
                "applied": JobStatus.APPLIED,
                "needs_review": JobStatus.NEEDS_REVIEW,
                "failed": JobStatus.FAILED,
            }
            new_status = status_map.get(result.get("status", "failed"), JobStatus.FAILED)

            self.queue.update_status(
                job_id=job.id,
                status=new_status,
                notes=result.get("message", ""),
                error=result.get("error", ""),
                intervention_reason=result.get("intervention_reason"),
                screenshot_path=result.get("screenshot_path"),
            )
            return {
                "job_id": job.id,
                "url": job.url,
                "status": new_status.value,
                "message": result.get("message", ""),
                "error": result.get("error", ""),
            }
        except asyncio.CancelledError:
            print("⚠️ Task cancelled.")
            self.queue.update_status(job.id, JobStatus.FAILED, error="Stopped by user")
            return {"status": "stopped"}
        except Exception as e:
            self.queue.update_status(job.id, JobStatus.FAILED, error=str(e))
            return {"status": "failed", "error": str(e)}
        finally:
            self._running = False
            self._current_job = None
            self._current_agent = None
            self._current_task = None

    async def run_one(self) -> Optional[Dict[str, Any]]:
        """
        Process a single job from the queue.
        
        Returns:
            Dict with job result, or None if queue is empty
        """
        if self._running:
            return {"error": "Already processing a job", "job": None}

        # Claim next job
        job = self.queue.claim_next()
        if not job:
            return None

        self._running = True
        self._current_job = job

        try:
            agent = self._create_agent()
            self._current_agent = agent
            result = await agent.apply(
                job_url=job.url,
                job_id=job.id,
                job_title=job.title,
                job_company=job.company,
            )

            # Update job status based on result
            status_map = {
                "applied": JobStatus.APPLIED,
                "needs_review": JobStatus.NEEDS_REVIEW,
                "failed": JobStatus.FAILED,
            }
            new_status = status_map.get(result.get("status", "failed"), JobStatus.FAILED)

            self.queue.update_status(
                job_id=job.id,
                status=new_status,
                notes=result.get("message", ""),
                error=result.get("error", ""),
                intervention_reason=result.get("intervention_reason"),
                screenshot_path=result.get("screenshot_path"),
            )

            return {
                "job_id": job.id,
                "url": job.url,
                "status": new_status.value,
                "message": result.get("message", ""),
                "error": result.get("error", ""),
                "intervention_reason": result.get("intervention_reason"),
            }

        except Exception as e:
            # Mark job as failed
            self.queue.update_status(
                job_id=job.id,
                status=JobStatus.FAILED,
                error=str(e),
            )
            return {
                "job_id": job.id,
                "url": job.url,
                "status": "failed",
                "error": str(e),
            }
        finally:
            self._running = False
            self._current_job = None
            self._current_agent = None

    def run_one_sync(self) -> Optional[Dict[str, Any]]:
        """Synchronous wrapper for run_one()."""
        return asyncio.run(self.run_one())

    async def run_all(self) -> list[Dict[str, Any]]:
        """
        Process all queued jobs.
        
        Returns:
            List of results for each processed job
        """
        results = []
        while True:
            result = await self.run_one()
            if result is None:
                break
            results.append(result)
            
            # Small delay between jobs to avoid overwhelming
            await asyncio.sleep(1)
        
        return results

    def run_all_sync(self) -> list[Dict[str, Any]]:
        """Synchronous wrapper for run_all()."""
        return asyncio.run(self.run_all())

    def get_status(self) -> Dict[str, Any]:
        """Get current runner status."""
        stats = self.queue.get_stats()
        # Check if paused
        is_paused = False
        if self._current_agent and not self._current_agent.pause_event.is_set():
            is_paused = True
            
        return {
            "is_running": self._running,
            "is_paused": is_paused,
            "current_job": self._current_job.model_dump_json_safe() if self._current_job else None,
            "queue_stats": stats,
        }
