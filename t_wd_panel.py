"""Navigate to /apply and dump the entry panel options (signed-in state)."""
import asyncio, sys
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

BASE = ("https://fanniemae.wd1.myworkdayjobs.com/en-US/FannieMaeCareers/job/"
        "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677")

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    await page.goto(BASE + "/apply")
    await asyncio.sleep(8)
    url = await page.evaluate("location.href")
    print("URL:", url, flush=True)
    body = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,700)"))
    print("BODY:", body, flush=True)
    # All clickable controls in the entry panel.
    aids = await page.evaluate(
        "JSON.stringify(Array.from(document.querySelectorAll('button, a, [role=button]'))"
        ".filter(function(e){ return (e.innerText||'').trim().length>0 && (e.innerText||'').trim().length<60 })"
        ".slice(0,40).map(function(e){ return {t:(e.innerText||'').trim().replace(/\\n+/g,' '), aid:e.getAttribute('data-automation-id'), tag:e.tagName}; }))")
    print("CONTROLS:", aids, flush=True)
    await cdp.close()

asyncio.run(main())
