"""Job Runner - Orchestrates queue processing and agent execution."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Dict, Any, Optional

from dotenv import load_dotenv

from .queue import JobQueue, JobStatus, QueuedJob
from .agent import JobApplyAgent

load_dotenv()


class JobRunner:
    """Orchestrates job queue processing."""

    def __init__(
        self,
        queue_path: Optional[str] = None,
        profile_path: Optional[str] = None,
        artifacts_dir: Optional[str] = None,
        max_steps: Optional[int] = None,
        max_history_items: Optional[int] = None,
        headless: bool = False,
    ):
        self.queue = JobQueue(
            path=queue_path or os.getenv("JOB_APPLIER_QUEUE_PATH", "./job_queue.json")
        )
        self.profile_path = profile_path or os.getenv("JOB_APPLIER_PROFILE_PATH", "./profile.json")
        self.artifacts_dir = artifacts_dir or os.getenv("JOB_APPLIER_ARTIFACTS_DIR", "./artifacts")
        self.max_steps = max_steps or int(os.getenv("JOB_APPLIER_MAX_STEPS", "30"))
        self.max_history_items = max_history_items or int(os.getenv("JOB_APPLIER_MAX_HISTORY", "10"))
        self.headless = headless
        self._running = False
        self._current_job: Optional[QueuedJob] = None

    @property
    def is_running(self) -> bool:
        """Check if runner is currently processing a job."""
        return self._running

    @property
    def current_job(self) -> Optional[QueuedJob]:
        """Get the currently processing job."""
        return self._current_job

    def _create_agent(self) -> JobApplyAgent:
        """Create a new agent instance."""
        return JobApplyAgent(
            profile_path=self.profile_path,
            artifacts_dir=self.artifacts_dir,
            max_steps=self.max_steps,
            max_history_items=self.max_history_items,
            headless=self.headless,
        )

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
        return {
            "is_running": self._running,
            "current_job": self._current_job.model_dump_json_safe() if self._current_job else None,
            "queue_stats": stats,
        }
