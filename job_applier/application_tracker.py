"""Unified SQLite tracking for jobs, attempts, phases, and hiccups."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func

from .database import (
    ApplicationAttempt,
    ApplicationHiccup,
    AttemptPhase,
    CompanyPortalAccount,
    DatabaseManager,
    Job,
    JobStatus,
)

TARGET_SECONDS = 5 * 60
_TRACKING_QUERY_KEYS = {
    "gh_src",
    "source",
    "src",
    "trackingid",
    "ref",
    "referrer",
}


def canonical_job_url(url: str) -> str:
    """Remove fragments and known tracking parameters without changing job identity."""
    clean = str(url or "").strip()
    parts = urlsplit(clean)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    ]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def canonical_company_key(company: str) -> str:
    return "".join(ch for ch in str(company or "").lower() if ch.isalnum())


def portal_key(url: str) -> str:
    return urlsplit(str(url or "").strip()).netloc.lower()


def infer_platform(url: str) -> str:
    value = str(url or "").lower()
    if "myworkdayjobs.com" in value or "workday.com" in value:
        return "workday"
    if "greenhouse.io" in value:
        return "greenhouse"
    if "icims.com" in value:
        return "icims"
    return "generic"


from .managed_shared import legacy_writer


class ApplicationTracker:
    """Use the existing job database as the application system of record."""

    def __init__(
        self,
        db_path: str | Path = "./job_applier.db",
        *,
        now_fn: Callable[[], datetime] = datetime.utcnow,
        target_seconds: int = TARGET_SECONDS,
    ) -> None:
        self.db = DatabaseManager(str(db_path))
        self.now_fn = now_fn
        self.target_seconds = int(target_seconds)

    def _find_job(self, session, url: str) -> Optional[Job]:
        canonical = canonical_job_url(url)
        exact = session.query(Job).filter(Job.url == canonical).first()
        if exact:
            return exact
        for job in session.query(Job).all():
            if canonical_job_url(job.url) == canonical:
                return job
        return None

    @legacy_writer
    def start_attempt(
        self,
        *,
        url: str,
        company: str,
        title: str,
        platform: str,
        workflow: str = "simplify",
    ) -> dict:
        strategy = self.account_strategy(company=company, platform=platform, url=url)
        now = self.now_fn()
        canonical = canonical_job_url(url)
        session = self.db.get_session()
        try:
            job = self._find_job(session, canonical)
            if job is None:
                next_seq = (session.query(func.max(Job.seq_id)).scalar() or 0) + 1
                job = Job(
                    id=str(uuid.uuid4()),
                    seq_id=next_seq,
                    url=canonical,
                    company=company.strip() or None,
                    title=title.strip() or None,
                    status=JobStatus.RUNNING.value,
                    created_at=now,
                    updated_at=now,
                    started_at=now,
                )
                session.add(job)
                session.flush()
            else:
                job.url = canonical
                if company.strip():
                    job.company = company.strip()
                if title.strip():
                    job.title = title.strip()
                job.status = JobStatus.RUNNING.value
                job.started_at = now
                job.completed_at = None
                job.updated_at = now

            attempt = ApplicationAttempt(
                job_id=job.id,
                platform=platform.strip().lower(),
                workflow=workflow.strip(),
                started_at=now,
            )
            session.add(attempt)
            session.flush()
            session.add(AttemptPhase(attempt_id=attempt.id, phase="preflight", started_at=now))
            session.commit()
            return {
                "job_id": job.id,
                "seq_id": job.seq_id,
                "attempt_id": attempt.id,
                "account_strategy": strategy,
            }
        finally:
            session.close()

    def account_strategy(self, *, company: str, platform: str, url: str) -> dict:
        """Choose sign-in versus account creation from explicit and inferred history."""
        platform_name = str(platform or "").strip().lower() or infer_platform(url)
        portal = portal_key(url)
        if platform_name == "greenhouse":
            return {
                "action": "not_required",
                "source": "platform",
                "account_status": "not_applicable",
                "portal_key": portal,
                "email": None,
            }

        session = self.db.get_session()
        try:
            account = (
                session.query(CompanyPortalAccount)
                .filter(
                    CompanyPortalAccount.platform == platform_name,
                    CompanyPortalAccount.portal_key == portal,
                    CompanyPortalAccount.status.in_(["confirmed", "created", "signed_in"]),
                )
                .order_by(CompanyPortalAccount.updated_at.desc())
                .first()
            )
            if account:
                return {
                    "action": "sign_in",
                    "source": "company_portal_account",
                    "account_status": account.status,
                    "portal_key": portal,
                    "email": account.email,
                }

            company_key = canonical_company_key(company)
            for job in session.query(Job).filter(Job.status == JobStatus.APPLIED.value).all():
                if canonical_company_key(job.company or "") != company_key:
                    continue
                if infer_platform(job.url) != platform_name or portal_key(job.url) != portal:
                    continue
                return {
                    "action": "sign_in_first",
                    "source": "prior_application",
                    "account_status": "inferred",
                    "portal_key": portal,
                    "email": None,
                }
            return {
                "action": "create_account_or_sign_in",
                "source": "no_history",
                "account_status": "unknown",
                "portal_key": portal,
                "email": None,
            }
        finally:
            session.close()

    @legacy_writer
    def set_company_account(
        self,
        *,
        company: str,
        platform: str,
        url: str,
        email: str,
        status: str = "confirmed",
        note: str = "",
    ) -> dict:
        """Record a reusable portal account without storing its password."""
        now = self.now_fn()
        platform_name = str(platform or "").strip().lower() or infer_platform(url)
        portal = portal_key(url)
        session = self.db.get_session()
        try:
            account = (
                session.query(CompanyPortalAccount)
                .filter(CompanyPortalAccount.portal_key == portal, CompanyPortalAccount.email == email.strip())
                .first()
            )
            if account is None:
                account = CompanyPortalAccount(
                    company_key=canonical_company_key(company),
                    company_name=company.strip(),
                    platform=platform_name,
                    portal_key=portal,
                    email=email.strip(),
                    created_at=now,
                )
                session.add(account)
            account.company_key = canonical_company_key(company)
            account.company_name = company.strip()
            account.platform = platform_name
            account.status = status.strip().lower()
            account.notes = note.strip() or None
            account.updated_at = now
            if account.status in {"confirmed", "signed_in"}:
                account.last_successful_login_at = now
            session.commit()
            return {
                "account_id": account.id,
                "company": account.company_name,
                "platform": account.platform,
                "portal_key": account.portal_key,
                "email": account.email,
                "status": account.status,
            }
        finally:
            session.close()

    def _attempt(self, session, attempt_id: int) -> ApplicationAttempt:
        attempt = session.query(ApplicationAttempt).filter(ApplicationAttempt.id == int(attempt_id)).first()
        if attempt is None:
            raise ValueError(f"application attempt not found: {attempt_id}")
        return attempt

    def _open_phase(self, session, attempt_id: int) -> Optional[AttemptPhase]:
        return (
            session.query(AttemptPhase)
            .filter(AttemptPhase.attempt_id == int(attempt_id), AttemptPhase.ended_at.is_(None))
            .order_by(AttemptPhase.id.desc())
            .first()
        )

    @staticmethod
    def _close_phase(phase: Optional[AttemptPhase], now: datetime) -> None:
        if phase is None:
            return
        phase.ended_at = now
        phase.duration_seconds = round(max(0.0, (now - phase.started_at).total_seconds()), 1)

    @legacy_writer
    def transition_phase(self, attempt_id: int, phase: str, *, note: str = "") -> dict:
        now = self.now_fn()
        session = self.db.get_session()
        try:
            attempt = self._attempt(session, attempt_id)
            if attempt.completed_at is not None:
                raise ValueError(f"application attempt already completed: {attempt_id}")
            self._close_phase(self._open_phase(session, attempt_id), now)
            next_phase = AttemptPhase(
                attempt_id=attempt.id,
                phase=phase.strip(),
                note=note.strip() or None,
                started_at=now,
            )
            session.add(next_phase)
            session.commit()
            return {"attempt_id": attempt.id, "phase": next_phase.phase}
        finally:
            session.close()

    @legacy_writer
    def record_hiccup(
        self,
        attempt_id: int,
        *,
        category: str,
        description: str,
        field_label: str = "",
        resolution: str = "",
        reusable_fix: str = "",
        status: Optional[str] = None,
        seconds_lost: Optional[float] = None,
    ) -> dict:
        now = self.now_fn()
        session = self.db.get_session()
        try:
            attempt = self._attempt(session, attempt_id)
            current_phase = self._open_phase(session, attempt_id)
            resolved_status = status or ("resolved" if resolution.strip() else "open")
            hiccup = ApplicationHiccup(
                attempt_id=attempt.id,
                job_id=attempt.job_id,
                platform=attempt.platform,
                phase=current_phase.phase if current_phase else None,
                category=category.strip(),
                field_label=field_label.strip() or None,
                description=description.strip(),
                resolution=resolution.strip() or None,
                reusable_fix=reusable_fix.strip() or None,
                status=resolved_status,
                seconds_lost=float(seconds_lost) if seconds_lost is not None else None,
                created_at=now,
            )
            session.add(hiccup)
            session.commit()
            return {"hiccup_id": hiccup.id, "attempt_id": attempt.id, "status": hiccup.status}
        finally:
            session.close()

    def _phase_summary(self, session, attempt_id: int) -> tuple[dict[str, float], Optional[str]]:
        rows = (
            session.query(AttemptPhase)
            .filter(AttemptPhase.attempt_id == int(attempt_id))
            .order_by(AttemptPhase.id)
            .all()
        )
        breakdown: dict[str, float] = {}
        for row in rows:
            seconds = float(row.duration_seconds or 0)
            breakdown[row.phase] = round(breakdown.get(row.phase, 0.0) + seconds, 1)
        slowest = max(breakdown, key=breakdown.get) if breakdown else None
        return breakdown, slowest

    @legacy_writer
    def finish_attempt(
        self,
        attempt_id: int,
        *,
        outcome: str,
        evidence: str = "",
        note: str = "",
    ) -> dict:
        now = self.now_fn()
        session = self.db.get_session()
        try:
            attempt = self._attempt(session, attempt_id)
            self._close_phase(self._open_phase(session, attempt_id), now)
            attempt.completed_at = now
            attempt.duration_seconds = round(max(0.0, (now - attempt.started_at).total_seconds()), 1)
            attempt.outcome = outcome.strip().lower()
            attempt.evidence = evidence.strip() or None
            attempt.notes = note.strip() or None
            attempt.meets_target = attempt.duration_seconds <= self.target_seconds

            job = session.query(Job).filter(Job.id == attempt.job_id).first()
            terminal_statuses = {
                "applied": JobStatus.APPLIED.value,
                "blocked": JobStatus.BLOCKED.value,
                "skipped": JobStatus.SKIPPED.value,
                "failed": JobStatus.FAILED.value,
                "needs_review": JobStatus.NEEDS_REVIEW.value,
            }
            job.status = terminal_statuses.get(attempt.outcome, attempt.outcome)
            job.notes = note.strip() or evidence.strip() or job.notes
            job.error = "" if attempt.outcome == "applied" else job.error
            job.updated_at = now
            job.completed_at = now
            session.flush()
            breakdown, slowest = self._phase_summary(session, attempt.id)
            hiccup_rows = (
                session.query(ApplicationHiccup)
                .filter(ApplicationHiccup.attempt_id == attempt.id)
                .order_by(ApplicationHiccup.id)
                .all()
            )
            hiccups = [
                {
                    "category": row.category,
                    "phase": row.phase,
                    "field_label": row.field_label,
                    "description": row.description,
                    "resolution": row.resolution,
                    "reusable_fix": row.reusable_fix,
                    "status": row.status,
                    "seconds_lost": row.seconds_lost,
                }
                for row in hiccup_rows
            ]
            improvement_candidates = []
            for row in hiccup_rows:
                if row.reusable_fix and row.reusable_fix not in improvement_candidates:
                    improvement_candidates.append(row.reusable_fix)
            session.commit()
            return {
                "job_id": job.id,
                "seq_id": job.seq_id,
                "attempt_id": attempt.id,
                "outcome": attempt.outcome,
                "duration_seconds": attempt.duration_seconds,
                "meets_target": attempt.meets_target,
                "phase_breakdown_seconds": breakdown,
                "slowest_phase": slowest,
                "hiccups": hiccups,
                "improvement_candidates": improvement_candidates,
                "evidence": attempt.evidence,
                "note": attempt.notes,
            }
        finally:
            session.close()

    def job_history(self, *, status: Optional[str] = None) -> list[dict]:
        session = self.db.get_session()
        try:
            query = session.query(Job)
            if status:
                query = query.filter(Job.status == status)
            jobs = query.order_by(Job.seq_id.desc()).all()
            output = []
            for job in jobs:
                attempts = (
                    session.query(ApplicationAttempt)
                    .filter(ApplicationAttempt.job_id == job.id)
                    .order_by(ApplicationAttempt.id.desc())
                    .all()
                )
                latest = attempts[0] if attempts else None
                output.append({
                    "job_id": job.id,
                    "seq_id": job.seq_id,
                    "company": job.company,
                    "title": job.title,
                    "url": job.url,
                    "status": job.status,
                    "attempt_count": len(attempts),
                    "latest_attempt_id": latest.id if latest else None,
                    "latest_duration_seconds": latest.duration_seconds if latest else None,
                    "latest_outcome": latest.outcome if latest else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                })
            return output
        finally:
            session.close()

    def company_history(self) -> list[dict]:
        """Aggregate roles and prior applications by canonical company."""
        session = self.db.get_session()
        try:
            grouped: dict[str, dict] = {}
            for job in session.query(Job).order_by(Job.seq_id.desc()).all():
                key = canonical_company_key(job.company or "") or f"unknown-{job.id}"
                item = grouped.setdefault(key, {
                    "company": job.company or "?",
                    "role_count": 0,
                    "applied_count": 0,
                    "statuses": {},
                    "platforms": [],
                    "latest_completed_at": None,
                })
                item["role_count"] += 1
                if job.status == JobStatus.APPLIED.value:
                    item["applied_count"] += 1
                item["statuses"][job.status] = item["statuses"].get(job.status, 0) + 1
                platform = infer_platform(job.url)
                if platform not in item["platforms"]:
                    item["platforms"].append(platform)
                completed = job.completed_at.isoformat() if job.completed_at else None
                if completed and (item["latest_completed_at"] is None or completed > item["latest_completed_at"]):
                    item["latest_completed_at"] = completed
            for key, item in grouped.items():
                item["account_count"] = session.query(CompanyPortalAccount).filter(
                    CompanyPortalAccount.company_key == key,
                    CompanyPortalAccount.status.in_(["confirmed", "created", "signed_in"]),
                ).count()
                item["platforms"].sort()
            return sorted(grouped.values(), key=lambda item: (-item["applied_count"], -item["role_count"], item["company"].lower()))
        finally:
            session.close()

    def hiccup_summary(self, *, platform: Optional[str] = None) -> list[dict]:
        session = self.db.get_session()
        try:
            query = session.query(ApplicationHiccup)
            if platform:
                query = query.filter(ApplicationHiccup.platform == platform.lower())
            rows = query.order_by(ApplicationHiccup.id).all()
            grouped: dict[tuple[str, str], dict] = {}
            for row in rows:
                key = (row.platform, row.category)
                item = grouped.setdefault(key, {
                    "platform": row.platform,
                    "category": row.category,
                    "count": 0,
                    "seconds_lost": 0.0,
                    "open_count": 0,
                    "reusable_fixes": [],
                })
                item["count"] += 1
                item["seconds_lost"] = round(item["seconds_lost"] + float(row.seconds_lost or 0), 1)
                if row.status == "open":
                    item["open_count"] += 1
                if row.reusable_fix and row.reusable_fix not in item["reusable_fixes"]:
                    item["reusable_fixes"].append(row.reusable_fix)
            return sorted(grouped.values(), key=lambda item: (-item["seconds_lost"], -item["count"], item["platform"], item["category"]))
        finally:
            session.close()
