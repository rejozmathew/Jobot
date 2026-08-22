"""Stability check: sample the form multiple times in ONE session."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    for i in range(6):
        url = await page.evaluate("location.href")
        n_in = await page.evaluate("document.querySelectorAll('input').length")
        n_sel = await page.evaluate("document.querySelectorAll('.select__input').length")
        has_first = await page.evaluate("!!document.getElementById('first_name')")
        body = (await page.evaluate("document.body.innerText.slice(0,60)")).replace("\n"," ")
        print(f"[{i}] in={n_in:3} sel={n_sel} first_name={has_first} | {body}")
        await asyncio.sleep(1.5)
    await b._session.close()

asyncio.run(main())
