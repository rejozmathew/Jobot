#!/usr/bin/env python3
"""
Job Applier - Main entry point for automated job applications.

Usage:
    # Start the web server and UI
    python run_applier.py serve
    
    # Add a URL and apply immediately
    python run_applier.py apply https://example.com/job/123
    
    # Add URLs to queue
    python run_applier.py add https://example.com/job/123 https://another.com/job/456
    
    # Process all queued jobs
    python run_applier.py run-all
    
    # Show queue status
    python run_applier.py status
"""

import argparse
import asyncio
import io
import json
import os
import sys
import webbrowser
from pathlib import Path

from dotenv import load_dotenv


def _configure_console_encoding() -> None:
    """Ensure Unicode log output works on Windows terminals."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
                continue
        except Exception:
            pass
        try:
            buffer = getattr(stream, "buffer", None)
            if buffer is None:
                continue
            setattr(
                sys,
                stream_name,
                io.TextIOWrapper(
                    buffer,
                    encoding="utf-8",
                    errors="replace",
                    line_buffering=True,
                ),
            )
        except Exception:
            # Keep original stream if reconfiguration is not supported.
            pass


_configure_console_encoding()

# Load environment variables
load_dotenv()

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from job_applier.db_queue import JobQueue
from job_applier.database import JobStatus
from job_applier.migrate import migrate_from_json, check_migration_status
from job_applier.application_tracker import ApplicationTracker


def cmd_serve(args):
    """Start the FastAPI server with web UI."""
    import uvicorn
    
    port = int(os.getenv("JOB_APPLIER_PORT", "8000"))
    host = args.host or "127.0.0.1"
    
    print(f"\n🚀 Starting Job Applier server at http://{host}:{port}")
    print(f"   Open http://{host}:{port} in your browser\n")
    
    # Open browser automatically
    if not args.no_browser:
        webbrowser.open(f"http://{host}:{port}")
    
    uvicorn.run(
        "job_applier.api:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


def _set_platform(args):
    plat = getattr(args, "platform", "auto")
    if plat and plat != "auto":
        import os as _os
        _os.environ["JOB_APPLIER_PLATFORM"] = plat


def _set_flags(args):
    """Thread --dry-run / --submit through to handlers via env vars."""
    import os as _os
    if getattr(args, "dry_run", False):
        _os.environ["JOB_APPLIER_DRY_RUN"] = "true"
        _os.environ["JOB_APPLIER_GH_DRY_RUN"] = "true"
        _os.environ["JOB_APPLIER_GH_SKIP_SUBMIT"] = "true"
    elif getattr(args, "submit", False):
        _os.environ["JOB_APPLIER_DRY_RUN"] = "false"
        _os.environ["JOB_APPLIER_GH_DRY_RUN"] = "false"
        _os.environ["JOB_APPLIER_GH_SKIP_SUBMIT"] = "false"


def cmd_apply(args):
    """Apply immediately and track the same job/attempt in SQLite."""
    from job_applier.runner import JobRunner
    from job_applier.platform_handlers.registry import detect_platform

    _set_platform(args)
    _set_flags(args)
    runner = JobRunner(headless=args.headless)
    tracker = _application_tracker()
    platform = args.platform if args.platform != "auto" else detect_platform(args.url)
    tracked = tracker.start_attempt(
        url=args.url,
        company=args.company or "",
        title=args.title or "",
        platform=platform,
        workflow="deterministic-dry-run" if args.dry_run else "deterministic",
    )
    job = runner.queue.get(tracked["job_id"])
    if job is None:
        raise RuntimeError(f"Tracked job missing from queue: {tracked['job_id']}")
    attempt_id = tracked["attempt_id"]
    print(f"✅ Tracking job #{tracked['seq_id']} / attempt #{attempt_id} - {args.url}")
    account = tracked.get("account_strategy") or {}
    print(f"   Account strategy: {account.get('action', 'unknown')} ({account.get('source', 'unknown')})")

    tracker.transition_phase(attempt_id, "handler", note="run_applier apply")
    print(f"\n🔄 Starting application process...")
    print(f"   Browser headless: {args.headless}")
    print(f"   Watch the browser window for progress\n")

    result = runner.run_specific_sync(job.id)
    status = result.get("status", "failed") if result else "failed"
    message = result.get("message", "") if result else "No result returned"
    error = result.get("error", "") if result else "No result returned"
    if status == "applied":
        icon = "✅"
    elif status == "dry_run":
        icon = "🧪"
    elif status == "needs_review":
        icon = "⚠️"
    else:
        icon = "❌"
    print(f"\n{icon} Result: {status}")
    if message:
        print(f"   Message: {message}")
    if error:
        print(f"   Error: {error}")
    if result and result.get("intervention_reason"):
        print(f"   Intervention needed: {result['intervention_reason']}")

    if status != "applied":
        tracker.record_hiccup(
            attempt_id,
            category="handler_outcome",
            description=error or message or f"Handler ended as {status}",
            status="open" if status in {"failed", "needs_review"} else "resolved",
            reusable_fix="Review the portal-specific handler or continue with Simplify residual filling",
        )
    tracker.transition_phase(attempt_id, "verification", note="confirm terminal outcome")
    terminal_outcome = status if status in {"applied", "blocked", "skipped", "failed", "needs_review"} else (
        "needs_review" if status == "dry_run" else "failed"
    )
    tracking_result = tracker.finish_attempt(
        attempt_id,
        outcome=terminal_outcome,
        evidence=message if status == "applied" else "",
        note=message or error,
    )
    print(f"\n📈 Tracking:\n{json.dumps(tracking_result, indent=2)}")


def cmd_add(args):
    """Add URLs to queue without processing."""
    queue = JobQueue()  # Uses SQLite database
    
    jobs = queue.add_urls(args.urls)
    print(f"✅ Added {len(jobs)} job(s) to queue:")
    for job in jobs:
        print(f"   - #{job.seq_id or '?'} {job.id[:8]}... {job.url}")


def cmd_run_all(args):
    """Process all queued jobs."""
    from job_applier.runner import JobRunner

    _set_platform(args)
    runner = JobRunner(headless=args.headless)
    
    stats = runner.queue.get_stats()
    queued = stats.get("queued", 0)
    
    if queued == 0:
        print("📭 Queue is empty")
        return
    
    print(f"\n🔄 Processing {queued} job(s)...")
    print(f"   Browser headless: {args.headless}\n")
    
    results = runner.run_all_sync()
    
    print(f"\n📊 Results:")
    for result in results:
        status = result.get("status", "unknown")
        url = result.get("url", "unknown")
        emoji = "✅" if status == "applied" else "⚠️" if status == "needs_review" else "❌"
        print(f"   {emoji} {status}: {url}")


def cmd_status(args):
    """Show queue status."""
    queue = JobQueue()  # Uses SQLite database
    
    stats = queue.get_stats()
    print("\n📊 Queue Status:")
    print(f"   Total:        {stats['total']}")
    print(f"   Queued:       {stats['queued']}")
    print(f"   Running:      {stats['running']}")
    print(f"   Applied:      {stats['applied']}")
    print(f"   Needs Review: {stats['needs_review']}")
    print(f"   Failed:       {stats['failed']}")
    print(f"   Blocked:      {stats.get('blocked', 0)}")
    print(f"   Skipped:      {stats.get('skipped', 0)}")
    
    if args.verbose:
        jobs = queue.list_all()
        if jobs:
            print("\n📝 Jobs:")
            for job in jobs:
                status_emoji = {
                    "queued": "⏳",
                    "running": "🔄",
                    "applied": "✅",
                    "needs_review": "⚠️",
                    "failed": "❌",
                    "blocked": "⛔",
                    "skipped": "⏭️",
                }.get(job.status, "❓")
                seq_label = f"#{job.seq_id}" if job.seq_id else ""
                print(f"   {status_emoji} [{job.status}] {seq_label} {job.url}")
                if job.notes:
                    print(f"      Notes: {job.notes[:80]}...")
                if job.intervention_reason:
                    print(f"      Reason: {job.intervention_reason[:80]}...")


def _application_tracker() -> ApplicationTracker:
    return ApplicationTracker(os.getenv("JOB_APPLIER_DB_PATH", "./job_applier.db"))


def cmd_track_start(args):
    result = _application_tracker().start_attempt(
        url=args.url,
        company=args.company,
        title=args.title,
        platform=args.platform,
        workflow=args.workflow,
    )
    print(json.dumps(result, indent=2))


def cmd_track_phase(args):
    result = _application_tracker().transition_phase(args.attempt_id, args.phase, note=args.note)
    print(json.dumps(result, indent=2))


def cmd_track_hiccup(args):
    result = _application_tracker().record_hiccup(
        args.attempt_id,
        category=args.category,
        description=args.description,
        field_label=args.field,
        resolution=args.resolution,
        reusable_fix=args.reusable_fix,
        status=args.status,
        seconds_lost=args.seconds_lost,
    )
    print(json.dumps(result, indent=2))


def cmd_track_end(args):
    result = _application_tracker().finish_attempt(
        args.attempt_id,
        outcome=args.outcome,
        evidence=args.evidence,
        note=args.note,
    )
    print(json.dumps(result, indent=2))


def cmd_history(args):
    rows = _application_tracker().job_history(status=args.status)
    print(f"{'id':>5} {'status':13} {'attempts':>8} {'seconds':>8}  company / title")
    for row in rows:
        seconds = row.get("latest_duration_seconds")
        print(
            f"{str(row.get('seq_id') or '-'):>5} {str(row.get('status') or '-')[:13]:13} "
            f"{row.get('attempt_count', 0):>8} {str(round(seconds, 1) if seconds is not None else '-'):>8}  "
            f"{row.get('company') or '?'} / {row.get('title') or '?'}"
        )


def cmd_hiccups(args):
    rows = _application_tracker().hiccup_summary(platform=args.platform)
    print(f"{'platform':12} {'category':24} {'count':>5} {'lost_s':>8} {'open':>5}  reusable fix")
    for row in rows:
        fixes = "; ".join(row.get("reusable_fixes") or [])
        print(
            f"{row['platform'][:12]:12} {row['category'][:24]:24} {row['count']:>5} "
            f"{row['seconds_lost']:>8.1f} {row['open_count']:>5}  {fixes}"
        )


def cmd_account_check(args):
    result = _application_tracker().account_strategy(
        company=args.company,
        platform=args.platform,
        url=args.url,
    )
    print(json.dumps(result, indent=2))


def cmd_account_set(args):
    result = _application_tracker().set_company_account(
        company=args.company,
        platform=args.platform,
        url=args.url,
        email=args.email,
        status=args.status,
        note=args.note,
    )
    print(json.dumps(result, indent=2))


def cmd_companies(args):
    rows = _application_tracker().company_history()
    if args.applied_only:
        rows = [row for row in rows if row.get("applied_count", 0) > 0]
    print(f"{'company':28} {'roles':>5} {'applied':>7} {'platforms':20} account state")
    for row in rows:
        print(
            f"{row['company'][:28]:28} {row['role_count']:>5} {row['applied_count']:>7} "
            f"{','.join(row['platforms'])[:20]:20} sign-in accounts: {row['account_count']}"
        )


def cmd_migrate(args):
    """Migrate from JSON to SQLite database."""
    if args.check:
        # Just check status
        status = check_migration_status(json_path=args.json_path)
        print("\n🔍 Migration Status:")
        print(f"   JSON file exists: {status['json_file_exists']}")
        print(f"   JSON job count:   {status['json_job_count']}")
        print(f"   Database jobs:    {status['db_job_count']}")
        print(f"   Database path:    {status['db_path']}")
        print(f"   Migration needed: {status['migration_needed']}")
        return
    
    # Run migration
    print(f"\n🔄 Migrating from {args.json_path} to SQLite database...")
    
    result = migrate_from_json(
        json_path=args.json_path,
        backup=not args.no_backup,
    )
    
    if result['status'] == 'skipped':
        print(f"⏭️  Skipped: {result['message']}")
    elif result['status'] == 'error':
        print(f"❌ Error: {result['message']}")
    else:
        print(f"✅ {result['message']}")
        if result.get('backup_path'):
            print(f"   Backup saved to: {result['backup_path']}")
        if result.get('errors'):
            print("   Errors:")
            for err in result['errors']:
                print(f"      - {err}")


def main():
    parser = argparse.ArgumentParser(
        description="Job Applier - Automated job applications with browser-use",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start web server and UI")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    serve_parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    serve_parser.set_defaults(func=cmd_serve)
    
    # apply command
    apply_parser = subparsers.add_parser("apply", help="Add URL and apply immediately")
    apply_parser.add_argument("url", help="Job URL to apply to")
    apply_parser.add_argument("--title", help="Job title")
    apply_parser.add_argument("--company", help="Company name")
    apply_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    apply_parser.add_argument("--platform", choices=["auto","workday","greenhouse","generic"], default="auto",
                              help="Force a platform handler (e.g. greenhouse for company sites that embed Greenhouse)")
    apply_parser.add_argument("--dry-run", action="store_true",
                              help="Fill the form and stop before Submit (default for Greenhouse)")
    apply_parser.add_argument("--submit", action="store_true",
                              help="Click Submit (overrides profile skip_submit/dry_run)")
    apply_parser.set_defaults(func=cmd_apply)
    
    # add command
    add_parser = subparsers.add_parser("add", help="Add URLs to queue")
    add_parser.add_argument("urls", nargs="+", help="Job URLs to add")
    add_parser.add_argument("--platform", choices=["auto","workday","greenhouse","generic"], default="auto",
                            help="Force a platform handler for all URLs")
    add_parser.set_defaults(func=cmd_add)
    
    # run-all command
    run_parser = subparsers.add_parser("run-all", help="Process all queued jobs")
    run_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    run_parser.add_argument("--platform", choices=["auto","workday","greenhouse","generic"], default="auto",
                            help="Force a platform handler for all jobs")
    run_parser.set_defaults(func=cmd_run_all)
    
    # status command
    status_parser = subparsers.add_parser("status", help="Show queue status")
    status_parser.add_argument("-v", "--verbose", action="store_true", help="Show all jobs")
    status_parser.set_defaults(func=cmd_status)

    # Unified application tracking commands (same SQLite database as the queue).
    track_start = subparsers.add_parser("track-start", help="Start a timed application attempt")
    track_start.add_argument("url", help="Official job URL")
    track_start.add_argument("--company", required=True)
    track_start.add_argument("--title", required=True)
    track_start.add_argument("--platform", required=True)
    track_start.add_argument("--workflow", default="simplify")
    track_start.set_defaults(func=cmd_track_start)

    track_phase = subparsers.add_parser("track-phase", help="Move an attempt to a measured phase")
    track_phase.add_argument("attempt_id", type=int)
    track_phase.add_argument("phase")
    track_phase.add_argument("--note", default="")
    track_phase.set_defaults(func=cmd_track_phase)

    track_hiccup = subparsers.add_parser("track-hiccup", help="Record portal friction and its reusable fix")
    track_hiccup.add_argument("attempt_id", type=int)
    track_hiccup.add_argument("category")
    track_hiccup.add_argument("--description", required=True)
    track_hiccup.add_argument("--field", default="")
    track_hiccup.add_argument("--resolution", default="")
    track_hiccup.add_argument("--reusable-fix", default="")
    track_hiccup.add_argument("--status", choices=["open", "resolved"], default=None)
    track_hiccup.add_argument("--seconds-lost", type=float, default=None)
    track_hiccup.set_defaults(func=cmd_track_hiccup)

    track_end = subparsers.add_parser("track-end", help="Finish an attempt and update job status")
    track_end.add_argument("attempt_id", type=int)
    track_end.add_argument("outcome", choices=["applied", "blocked", "skipped", "failed", "needs_review"])
    track_end.add_argument("--evidence", default="")
    track_end.add_argument("--note", default="")
    track_end.set_defaults(func=cmd_track_end)

    history = subparsers.add_parser("history", help="List tracked jobs and application outcomes")
    history.add_argument("--status", default=None)
    history.set_defaults(func=cmd_history)

    hiccups = subparsers.add_parser("hiccups", help="Summarize recurring friction by portal")
    hiccups.add_argument("--platform", default=None)
    hiccups.set_defaults(func=cmd_hiccups)

    account_check = subparsers.add_parser("account-check", help="Choose sign-in versus account creation")
    account_check.add_argument("--company", required=True)
    account_check.add_argument("--platform", required=True)
    account_check.add_argument("--url", required=True)
    account_check.set_defaults(func=cmd_account_check)

    account_set = subparsers.add_parser("account-set", help="Record a confirmed company portal account")
    account_set.add_argument("--company", required=True)
    account_set.add_argument("--platform", required=True)
    account_set.add_argument("--url", required=True)
    account_set.add_argument("--email", required=True)
    account_set.add_argument("--status", choices=["confirmed", "created", "signed_in", "failed"], default="confirmed")
    account_set.add_argument("--note", default="")
    account_set.set_defaults(func=cmd_account_set)

    companies = subparsers.add_parser("companies", help="Summarize prior roles and reusable accounts by company")
    companies.add_argument("--applied-only", action="store_true", help="Show only companies with an applied job")
    companies.set_defaults(func=cmd_companies)
    
    # migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Migrate from JSON to SQLite database")
    migrate_parser.add_argument("--json-path", default="./job_queue.json", help="Path to JSON queue file")
    migrate_parser.add_argument("--no-backup", action="store_true", help="Don't backup JSON file")
    migrate_parser.add_argument("--check", action="store_true", help="Only check migration status")
    migrate_parser.set_defaults(func=cmd_migrate)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
