"""Wait for Workday to come back from maintenance, then check the Fannie Mae
application status via Candidate Home."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def state(page):
    url = await page.evaluate("window.location.href")
    maint = "maintenance" in url or "unavailable" in url
    return url, maint

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    deadline = asyncio.get_event_loop().time() + 150  # up to 150s
    while True:
        url, maint = await state(page)
        if not maint:
            break
        await asyncio.sleep(10)
        url, maint = await state(page)
        if asyncio.get_event_loop().time() > deadline:
            print("STILL_IN_MAINTENANCE:", url)
            await cdp.close(); return
    print("WORKDAY_BACK:", url)
    # go to Candidate Home
    await cdp.goto("https://community.workday.com/candidate/home")
    await asyncio.sleep(6)
    body = await page.evaluate("document.body.innerText.slice(0, 2500)")
    print("CANDIDATE_HOME:")
    print(body)
    await cdp.close()

asyncio.run(main())
