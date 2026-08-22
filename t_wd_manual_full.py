"""Single-session Fannie Mae JR2677 driver: navigate to the My Information
form directly, fill it with the handler's proven methods, and advance through
the 6-step wizard to Submit. Avoids the flaky resume-upload step.
"""
import asyncio, sys, json, os
sys.path.insert(0, ".")
os.environ.setdefault("JOB_APPLIER_DRY_RUN", "false")
os.environ.setdefault("JOB_APPLIER_WORKDAY_FALLBACK_LLM", "false")

from job_applier.cdp_client import CDPBrowser
from job_applier.platform_handlers.base import HandlerResult, HandlerOutcome, safe_navigate
from job_applier.platform_handlers.workday import WorkdayHandler

MANUAL = ("https://fanniemae.wd1.myworkdayjobs.com/FannieMaeCareers/job/"
          "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677/apply/applyManually")

def dump(label, o):
    try:
        print(f"[{label}] {o!r}"[:260], flush=True)
    except Exception:
        print(f"[{label}] <unprintable>", flush=True)

async def main():
    profile = json.loads(open("profile.json", encoding="utf-8").read())
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    h = WorkdayHandler(browser_session=cdp, profile=profile,
                       job_url=MANUAL, trace_hook=None)

    # Land directly on the My Information form.
    ok, reason = await safe_navigate(page, MANUAL)
    print(f"[nav] ok={ok} reason={reason}", flush=True)
    await asyncio.sleep(4)

    max_iters = 60
    for i in range(max_iters):
        snap = await h._snapshot()
        if not snap:
            print(f"[iter {i}] no snapshot; break", flush=True); break
        state = h._state(snap)
        url = str(snap.get("url") or "")[:120]
        print(f"[iter {i}] state={state} required_empty={snap.get('required_empty')} url={url}", flush=True)

        if state == "SUBMITTED":
            print("=== SUBMITTED DETECTED ===", flush=True); break

        # Guard: don't loop forever on one state.
        acted, note = await h._action(state, snap)
        print(f"    acted={acted} note={note}", flush=True)
        h.total_steps += 1
        if acted:
            await asyncio.sleep(2.0)
            continue
        # No deterministic action: capture + try one recovery pass.
        rec = await h.recover({"note": note})
        print(f"    recover={rec.result!r} note={rec.note!r}", flush=True)
        if rec.result in (HandlerResult.SUBMITTED,):
            break
        if rec.result == HandlerResult.PROGRESSED:
            await asyncio.sleep(2.0); continue
        # Stuck: save state and break to avoid infinite hammering.
        print(f"    STUCK on {state} -> breaking", flush=True)
        break

    # Final state.
    final = await page.evaluate(
        "() => JSON.stringify({u: location.href, t: document.title, "
        "hasSub: !!document.querySelector('[data-automation-id=\"submitApplicationButton\"],button[type=submit][data-automation-id*=submit i]')})")
    dump("FINAL", final)
    await page.screenshot("artifacts/wd_manual_full_final.png")
    print("DONE", flush=True)

asyncio.run(main())
