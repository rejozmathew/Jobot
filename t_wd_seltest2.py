"""Test each WD_SEL selector against the live page using the handler's exact
method (page.get_elements_by_css_selector), reporting hit count for each."""
import asyncio, sys
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser
from job_applier.platform_handlers.workday import WD_SEL

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    for key in ["first_name","last_name","address_line1","city","postal_code","phone_number","state_dropdown","phone_code_dropdown","phone_type_dropdown","continue_button","previous_worker_no","source_dropdown"]:
        sels = WD_SEL.get(key, [])
        if not sels:
            print(f"{key:18}: (no selectors)")
            continue
        report = []
        for s in sels:
            try:
                els = await page.get_elements_by_css_selector(s)
                n = len(els) if els else 0
                if n:
                    report.append(f"  {s}  ->  {n}")
                    break
            except Exception as e:
                report.append(f"  {s}  ->  ERR {str(e)[:30]}")
        print(f"{key:18}: " + ("HIT: " + report[0] if report else "MISS (tried %d)" % len(sels)))
    await cdp.close()

asyncio.run(main())
