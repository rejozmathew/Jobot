"""Test the handler's element-based el_select_combobox (DOM clicks, works
below the fold) on the Region field of the already-loaded My Info form."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser
from job_applier.platform_handlers.workday import WorkdayHandler, WD_SEL

PROFILE = json.loads(open("profile.json", encoding="utf-8").read())
URL = ("https://fanniemae.wd1.myworkdayjobs.com/FannieMaeCareers/job/"
       "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677")

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    h = WorkdayHandler(browser_session=cdp, profile=PROFILE, job_url=URL)

    # Confirm we're on the My Information form
    url = await page.evaluate("window.location.href")
    print("URL:", url)
    print("state_dropdown selectors:", WD_SEL.get("state_dropdown"))

    # Try the handler's element-based combobox selection for Region -> Illinois
    ok, note = await h.el_select_combobox(
        WD_SEL["state_dropdown"],
        h._state_option_candidates("IL"),
        state_key="CONTACT",
        field_hints=["state", "province", "region"],
    )
    print("Region el_select_combobox:", ok, note)

    # verify
    v = json.loads(await page.evaluate("""
    (() => { const e=document.querySelector('#address--countryRegion'); return e?(e.textContent||'').trim().slice(0,40):null; })()
    """))
    print("Region now:", v)
    await cdp.close()

asyncio.run(main())
