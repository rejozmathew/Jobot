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

from job_applier.db_queue import JobQueue, AddJobRequest
from job_applier.database import JobStatus
from job_applier.runner import JobRunner
from job_applier.migrate import migrate_from_json, check_migration_status


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
    """Add URL to queue and process immediately."""
    _set_platform(args)
    _set_flags(args)
    runner = JobRunner(headless=args.headless)
    
    # Add to queue
    request = AddJobRequest(
        url=args.url,
        title=args.title,
        company=args.company,
    )
    job = runner.queue.add(request)
    print(f"✅ Added job: {job.id[:8]}... - {args.url}")
    
    # Run immediately
    print(f"\n🔄 Starting application process...")
    print(f"   Browser headless: {args.headless}")
    print(f"   Watch the browser window for progress\n")
    
    result = runner.run_specific_sync(job.id)
    
    if result:
        status = result.get("status", "unknown")
        if status == "applied":
            icon = "✅"
        elif status == "dry_run":
            icon = "🧪"
        elif status == "needs_review":
            icon = "⚠️"
        else:
            icon = "❌"
        print(f"\n{icon} Result: {status}")
        if result.get("message"):
            print(f"   Message: {result['message']}")
        if result.get("error"):
            print(f"   Error: {result['error']}")
        if result.get("intervention_reason"):
            print(f"   Intervention needed: {result['intervention_reason']}")
    else:
        print("❌ No result returned")


def cmd_add(args):
    """Add URLs to queue without processing."""
    queue = JobQueue()  # Uses SQLite database
    
    jobs = queue.add_urls(args.urls)
    print(f"✅ Added {len(jobs)} job(s) to queue:")
    for job in jobs:
        print(f"   - #{job.seq_id or '?'} {job.id[:8]}... {job.url}")


def cmd_run_all(args):
    """Process all queued jobs."""
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
                }.get(job.status, "❓")
                seq_label = f"#{job.seq_id}" if job.seq_id else ""
                print(f"   {status_emoji} [{job.status}] {seq_label} {job.url}")
                if job.notes:
                    print(f"      Notes: {job.notes[:80]}...")
                if job.intervention_reason:
                    print(f"      Reason: {job.intervention_reason[:80]}...")


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
