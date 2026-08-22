"""Instrumented Workday dry-run: full state/step trace to a log file."""
import asyncio, json, os, sys, datetime
sys.path.insert(0, ".")
os.environ["JOB_APPLIER_DRY_RUN"] = "1"
os.environ["JOB_APPLIER_WORKDAY_FALLBACK_LLM"] = "false"

from job_applier.cdp_client import CDPBrowser
from job_applier.bu_compat import make_bu_session
from job_applier.platform_handlers.workday import WorkdayHandler

URL = ("https://fanniemae.wd1.myworkdayjobs.com/FannieMaeCareers/job/"
       "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677")
LOG = "artifacts/wd_trace.log"
os.makedirs("artifacts", exist_ok=True)
loglines = []

def trace_hook(data):
    ev = data.get("event", "?")
    rest = {k: v for k, v in data.items() if k not in ("event", "platform")}
    line = f"{datetime.datetime.utcnow().strftime('%H:%M:%S')} {ev} " + " ".join(f"{k}={v}" for k, v in rest.items())
    loglines.append(line)
    print(line, flush=True)

def load_profile():
    with open("profile.json", encoding="utf-8") as f:
        return json.load(f)

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    await page.goto(URL)
    await asyncio.sleep(6)
    print(f"[driver] navigated title={await page.title()!r} url={page.url_current}", flush=True)

    bu = make_bu_session(cdp)
    handler = WorkdayHandler(browser_session=bu, profile=load_profile(), job_url=URL, trace_hook=trace_hook)
    outcome = await handler.run()

    print("\n===== OUTCOME =====", flush=True)
    print("result:", outcome.result, flush=True)
    print("state :", outcome.state, flush=True)
    print("message:", outcome.message, flush=True)
    print("blocker:", outcome.blocker_code, flush=True)
    print("steps :", len(handler.steps), flush=True)
    print("\n===== STEP TRACE =====", flush=True)
    for s in handler.steps:
        print("  ", s, flush=True)
    try:
        await cdp.screenshot("artifacts/wd_final2.png")
        print("[driver] screenshot -> artifacts/wd_final2.png", flush=True)
    except Exception as e:
        print("[driver] screenshot failed:", e, flush=True)
    await cdp.close()

    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(loglines) + "\n\n===== OUTCOME =====\nresult=" + str(outcome.result) +
                "\nstate=" + str(outcome.state) + "\nmessage=" + str(outcome.message) +
                "\n\n===== STEPS =====\n" + "\n".join(handler.steps) + "\n")
    print(f"[driver] trace -> {LOG}", flush=True)

try:
    asyncio.run(main())
except Exception as e:
    import traceback
    traceback.print_exc()
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[driver] EXCEPTION: {e}\n")
    except Exception:
        pass
    print(f"[driver] EXCEPTION: {e} (trace -> {LOG})", flush=True)
