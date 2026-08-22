"""Try direct navigation to step 2 (My Information) via candidate slugs."""
import asyncio, sys
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

BASE = ("https://fanniemae.wd1.myworkdayjobs.com/en-US/FannieMaeCareers/job/"
        "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677/apply")
SLUGS = ["myInformation", "personalInformation", "contactInformation",
         "my-info", "info", "contact", "autofillWithResume"]

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    for slug in SLUGS:
        url = BASE + "/" + slug
        try:
            await page.goto(url)
        except Exception as e:
            print("goto err", slug, e, flush=True)
        await asyncio.sleep(6)
        cur = await page.evaluate("location.href")
        body = (await page.evaluate(
            "(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,240)"))
        step2 = ("current step 2 of 7" in body) or ("My Information" in body and "current step 2" in body)
        print("TRY", slug, "->", cur, "| step2?:", step2, flush=True)
        print("   ", body[:150], flush=True)
        if step2:
            print("*** ADVANCED via", slug, flush=True)
            break
    # final state
    url = await page.evaluate("location.href")
    body = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,400)"))
    print("FINAL URL:", url, flush=True)
    print("FINAL BODY:", body, flush=True)
    await cdp.close()

asyncio.run(main())
