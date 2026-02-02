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
import os
import sys
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from job_applier.queue import JobQueue, AddJobRequest
from job_applier.runner import JobRunner


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


def cmd_apply(args):
    """Add URL to queue and process immediately."""
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
    
    result = runner.run_one_sync()
    
    if result:
        status = result.get("status", "unknown")
        print(f"\n{'✅' if status == 'applied' else '⚠️' if status == 'needs_review' else '❌'} Result: {status}")
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
    queue = JobQueue(os.getenv("JOB_APPLIER_QUEUE_PATH", "./job_queue.json"))
    
    jobs = queue.add_urls(args.urls)
    print(f"✅ Added {len(jobs)} job(s) to queue:")
    for job in jobs:
        print(f"   - {job.id[:8]}... {job.url}")


def cmd_run_all(args):
    """Process all queued jobs."""
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
    queue = JobQueue(os.getenv("JOB_APPLIER_QUEUE_PATH", "./job_queue.json"))
    
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
                }.get(job.status.value, "❓")
                print(f"   {status_emoji} [{job.status.value}] {job.url}")
                if job.notes:
                    print(f"      Notes: {job.notes[:80]}...")


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
    apply_parser.set_defaults(func=cmd_apply)
    
    # add command
    add_parser = subparsers.add_parser("add", help="Add URLs to queue")
    add_parser.add_argument("urls", nargs="+", help="Job URLs to add")
    add_parser.set_defaults(func=cmd_add)
    
    # run-all command
    run_parser = subparsers.add_parser("run-all", help="Process all queued jobs")
    run_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    run_parser.set_defaults(func=cmd_run_all)
    
    # status command
    status_parser = subparsers.add_parser("status", help="Show queue status")
    status_parser.add_argument("-v", "--verbose", action="store_true", help="Show all jobs")
    status_parser.set_defaults(func=cmd_status)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
