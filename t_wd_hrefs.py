"""Get hrefs of the three entry-panel anchors + click applyManually and
capture destination."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

ENTRY = ("https://fanniemae.wd1.myworkdayjobs.com/FannieMaeCareers/job/"
         "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677/apply")

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    await page.goto(ENTRY)
    await asyncio.sleep(5)
    hrefs = json.loads(await page.evaluate(
        "JSON.stringify(['autofillWithResume','applyManually','useMyLastApplication'].map(function(id){"
        " var el=document.querySelector('[data-automation-id='+JSON.stringify(id)+']');"
        " return {id:id, tag: el?el.tagName:null, href: el?el.getAttribute('href'):null,"
        " onclick: el?String(el.onclick).slice(0,80):null};"
        "}))"
    ))
    print("HREFS:", json.dumps(hrefs, indent=1))
    await cdp.close()

asyncio.run(main())
