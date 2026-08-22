"""Drive WorkdayHandler on the fast raw-CDP path (no browser-use watchdog).

This bypasses browser-use's Browser.start() (which hangs on a multi-tab real
browser) by feeding the handler a BUSession shim over CDPBrowser.

Usage:
    PYTHONPATH= BROWSER_USE_CDP_URL=http://127.0.0.1:9222 \
    JOB_APPLIER_DRY_RUN=true \
    JOB_APPLIER_WORKDAY_FALLBACK_LLM=false \
    .venv/Scripts/python.exe t_wd_run.py
"""
import asyncio, json, os, sys, time

sys.path.insert(0, ".")
os.environ.setdefault("BROWSER_USE_CDP_URL", "http://127.0.0.1:9222")
os.environ.setdefault("JOB_APPLIER_DRY_RUN", "true")
os.environ.setdefault("JOB_APPLIER_WORKDAY_FALLBACK_LLM", "false")

from job_applier.cdp_client import CDPBrowser
from job_applier.bu_compat import make_bu_session
from job_applier.platform_handlers.workday import WorkdayHandler
from job_applier.platform_handlers.base import HandlerResult

URL = sys.argv[1] if len(sys.argv) > 1 else (
    "https://fanniemae.wd1.myworkdayjobs.com/FannieMaeCareers/job/"
    "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677"
)
DRY = os.environ.get("JOB_APPLIER_DRY_RUN", "true").lower() in ("1", "true", "yes", "on")

def load_profile():
    p = json.loads(open("profile.json", encoding="utf-8").read())
    return p

async def main():
    print("[1] Connecting to CDP browser ...", flush=True)
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    print(f"    connected, current URL: {page.url}", flush=True)

    print(f"[2] Navigating to posting: {URL}", flush=True)
    await page.goto(URL, timeout=30)
    await asyncio.sleep(5)
    title = await page.title()
    print(f"    page title: {title}", flush=True)

    print("[3] Building BUSession shim ...", flush=True)
    bu_session = make_bu_session(cdp)

    profile = load_profile()
    print(f"    profile loaded: {profile.get('identity',{}).get('full_name','?')}", flush=True)

    print("[4] Creating WorkdayHandler (dry_run=true) ...", flush=True)
    events = []
    def trace(event_dict):
        ev = event_dict.get("event", "?")
        detail = event_dict.get("state", event_dict.get("step", event_dict.get("message", "")))
        print(f"    [trace] {ev}: {str(detail)[:120]}", flush=True)
        events.append(event_dict)

    handler = WorkdayHandler(
        browser_session=bu_session,
        profile=profile,
        job_url=URL,
        trace_hook=trace,
    )
    print(f"    dry_run={handler.dry_run}", flush=True)
    print(f"    creds email={handler.creds.email}", flush=True)

    print("[5] Running WorkdayHandler.run() ...", flush=True)
    t0 = time.time()
    outcome = await handler.run()
    elapsed = time.time() - t0
    print(f"\n{'='*60}", flush=True)
    print(f"RESULT: {outcome.result.value}", flush=True)
    print(f"STATE:  {outcome.state}", flush=True)
    print(f"MESSAGE: {outcome.message[:300]}", flush=True)
    print(f"STEPS ({len(outcome.steps)}):", flush=True)
    for s in outcome.steps[-20:]:
        print(f"  - {s[:150]}", flush=True)
    print(f"ELAPSED: {elapsed:.1f}s", flush=True)
    print(f"{'='*60}", flush=True)

    # Save trace for debugging
    trace_path = "artifacts/wd_trace.json"
    os.makedirs("artifacts", exist_ok=True)
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, default=str)
    print(f"trace saved to {trace_path}", flush=True)

    # Screenshot of final state
    try:
        shot = "artifacts/wd_final.png"
        await cdp.screenshot(shot)
        print(f"screenshot saved to {shot}", flush=True)
    except Exception as e:
        print(f"screenshot failed: {e}", flush=True)

    await cdp.close()

if __name__ == "__main__":
    asyncio.run(main())
