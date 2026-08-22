"""Call the handler's own _action(CONTACT) and capture the detailed
not-found reason. Also run _has_field for each key selector to find the gap."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser
from job_applier.platform_handlers.workday import WorkdayHandler, WD_SEL
from job_applier.platform_handlers.base import HandlerResult, HandlerOutcome

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    h = WorkdayHandler(cdp, page, dry_run=False)

    # Which selectors does _has_field resolve?
    for key in ["first_name","last_name","address_line1","city","postal_code","phone_number","state_dropdown","phone_code_dropdown","phone_type_dropdown","source_dropdown","continue_button","previous_worker_no"]:
        sels = WD_SEL.get(key, [])
        if not sels:
            print(f"{key:18}: (no selectors in WD_SEL)")
            continue
        hits = []
        for s in sels:
            try:
                n = await page._session.call("Runtime.evaluate", {"expression": f"document.querySelectorAll('{s}').length", "returnByValue": True})
                val = n.get("result", {}).get("value")
                if val and val != 0:
                    hits.append((s, val))
                    break
            except Exception:
                pass
        print(f"{key:18}: {'HIT ' + hits[0][0] + ' ('+str(hits[0][1])+')' if hits else 'MISS (tried ' + str(len(sels)) + ')'}")

    await cdp.close()

asyncio.run(main())
