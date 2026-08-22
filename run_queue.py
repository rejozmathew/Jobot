"""Queue runner — apply to a list of job URLs, one by one, and report a summary.

Reads a queue file (JSON: list of {"url": ...} or a list of URL strings),
dedupes against already-applied jobs in the DB, runs each job through the
existing JobRunner (deterministic handlers), and prints a machine- and
human-readable summary.

Login-walled jobs:
    Before running each job, we probe the URL for a sign-in wall. If one is
    present and JOB_APPLIER_LOGIN_WAIT > 0, we wait (polling) for a human to
    complete auth in the visible browser, then continue. If auth doesn't
    complete in time, the job is marked "needs_login" and we move on.

Usage:
    python run_queue.py <queue_file.json> [--timeout 600] [--dry-run]
    python run_queue.py --urls "https://a.com/job/1" "https://b.com/job/2"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make the package importable when run as a script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from job_applier.runner import JobRunner  # noqa: E402
from job_applier.db_queue import JobQueue  # noqa: E402
from job_applier.database import JobStatus  # noqa: E402
from job_applier.login_guard import _run as login_guard_run  # noqa: E402
import asyncio  # noqa: E402


def _load_queue(path: str) -> List[Dict[str, str]]:
    """Load a queue file. Accepts:
    - JSON list of strings  -> [{"url": s}, ...]
    - JSON list of objects  -> [{"url": ..., "title": ..., "company": ...}, ...]
    - a plain .txt file with one URL per line
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8").strip()
    if p.suffix.lower() in (".txt", ".url", ".urls"):
        urls = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
        return [{"url": u} for u in urls]
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("jobs") or data.get("urls") or [data]
    out: List[Dict[str, str]] = []
    for item in data:
        if isinstance(item, str):
            out.append({"url": item})
        elif isinstance(item, dict) and item.get("url"):
            out.append({
                "url": item["url"],
                "title": item.get("title", ""),
                "company": item.get("company", ""),
            })
    return out


def _already_applied(queue: JobQueue, url: str) -> bool:
    """Check the DB for an existing APPLIED job with this URL."""
    try:
        jobs = queue.list_all()
        for j in jobs:
            if j.url == url and j.status == JobStatus.APPLIED:
                return True
            if url in (j.url or "") and j.status == JobStatus.APPLIED:
                return True
    except Exception:
        pass
    return False


async def _probe_login(url: str, timeout_s: int) -> str:
    """Return 'authed' | 'wall' | 'cdp_unreachable' for a URL.

    If a wall is found and timeout_s > 0, waits for human auth and returns
    'authed' on success, 'wall' on timeout.
    """
    code = await login_guard_run(url, timeout_s)
    if code == 0:
        return "authed"
    if code == 3:
        return "cdp_unreachable"
    return "wall"


def _fmt_summary(results: List[Dict[str, Any]]) -> str:
    applied = [r for r in results if r.get("status") == "applied"]
    dry = [r for r in results if r.get("status") == "dry_run"]
    needs_review = [r for r in results if r.get("status") == "needs_review"]
    needs_login = [r for r in results if r.get("status") == "needs_login"]
    skipped = [r for r in results if r.get("status") == "skipped_applied"]
    failed = [r for r in results if r.get("status") == "failed"]

    lines = []
    lines.append("=" * 60)
    lines.append("  JOB APPLICATION SUMMARY")
    lines.append("=" * 60)
    lines.append(f"  Total:        {len(results)}")
    lines.append(f"  Applied:      {len(applied)}")
    if dry:
        lines.append(f"  Dry-run:      {len(dry)}")
    if needs_login:
        lines.append(f"  Need login:   {len(needs_login)}")
    if needs_review:
        lines.append(f"  Need review:  {len(needs_review)}")
    if skipped:
        lines.append(f"  Skipped:      {len(skipped)}  (already applied)")
    lines.append(f"  Failed:       {len(failed)}")
    lines.append("-" * 60)

    icon = {
        "applied": "✅", "dry_run": "🧪", "needs_review": "⚠️",
        "needs_login": "🔐", "skipped_applied": "⏭️", "failed": "❌",
    }
    for r in results:
        st = r.get("status", "?")
        lines.append(f"  {icon.get(st, '❓')} [{st}]  {r.get('url', '?')}")
        msg = r.get("message") or r.get("error") or ""
        if msg:
            lines.append(f"        {msg[:110]}")
    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("queue_file", nargs="?", help="Path to a JSON/TXT queue file")
    src.add_argument("--urls", nargs="+", help="Job URLs to apply to")
    p.add_argument("--timeout", type=int, default=int(os.environ.get("JOB_APPLIER_LOGIN_WAIT", "600")),
                   help="Seconds to wait for human login (default 600). 0 = don't wait.")
    p.add_argument("--dry-run", action="store_true", help="Fill form but stop before Submit")
    p.add_argument("--submit", action="store_true", help="Click Submit (override dry_run)")
    p.add_argument("--skip-login-check", action="store_true",
                   help="Skip the pre-flight login wall probe for each job")
    args = p.parse_args()

    # Resolve queue
    if args.queue_file:
        queue_items = _load_queue(args.queue_file)
    else:
        queue_items = [{"url": u} for u in args.urls]

    if not queue_items:
        print("Queue is empty. Nothing to do.")
        return 0

    # Flags
    if args.dry_run:
        os.environ["JOB_APPLIER_DRY_RUN"] = "true"
        os.environ["JOB_APPLIER_GH_DRY_RUN"] = "true"
        os.environ["JOB_APPLIER_GH_SKIP_SUBMIT"] = "true"
    elif args.submit:
        os.environ["JOB_APPLIER_DRY_RUN"] = "false"
        os.environ["JOB_APPLIER_GH_DRY_RUN"] = "false"
        os.environ["JOB_APPLIER_GH_SKIP_SUBMIT"] = "false"

    runner = JobRunner(headless=False)
    queue = runner.queue
    results: List[Dict[str, Any]] = []

    print(f"\n📋 Queue: {len(queue_items)} job(s)")
    print(f"   Login wait timeout: {args.timeout}s per walled job\n")

    for i, item in enumerate(queue_items, 1):
        url = item["url"]
        print(f"\n[{i}/{len(queue_items)}] {url}")

        # Dedupe
        if _already_applied(queue, url):
            print("   ⏭️  Already applied — skipping.")
            results.append({"url": url, "status": "skipped_applied", "message": "Already applied (dedupe)"})
            continue

        # Login wall probe
        if not args.skip_login_check:
            state = asyncio.run(_probe_login(url, args.timeout if args.timeout > 0 else 0))
            if state == "cdp_unreachable":
                print("   ❌ CDP browser unreachable — aborting queue.")
                results.append({"url": url, "status": "failed", "message": "CDP browser unreachable"})
                break
            if state == "wall":
                print(f"   🔐 Login wall still present after {args.timeout}s — marking needs_login, moving on.")
                results.append({"url": url, "status": "needs_login",
                                "message": f"Login required. Re-run after authenticating in the browser."})
                continue
            print("   🔓 Authed (or no wall). Proceeding.")

        # Add to queue and run
        from job_applier.db_queue import AddJobRequest
        req = AddJobRequest(
            url=url,
            title=item.get("title") or None,
            company=item.get("company") or None,
        )
        job = queue.add(req)
        print(f"   🔄 Running application...")
        result = runner.run_specific_sync(job.id)

        st = result.get("status", "failed") if result else "failed"
        msg = (result or {}).get("message") or (result or {}).get("error") or ""
        print(f"   Result: {st}  {msg[:100]}")
        results.append({"url": url, "status": st, "message": msg,
                        "job_seq_id": (result or {}).get("job_seq_id")})
        time.sleep(1)

    print()
    print(_fmt_summary(results))

    # Save summary next to the queue file for the record.
    if args.queue_file:
        out = Path(args.queue_file).with_suffix(".summary.json")
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n📄 Summary saved: {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
