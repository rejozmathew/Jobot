"""Probe current Workday page state: URL, title, buttons, text."""
import asyncio, sys
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    url = await page.evaluate("window.location.href")
    title = await page.evaluate("document.title")
    print("URL:", url)
    print("TITLE:", title)
    text = await page.evaluate(
        "document.body ? document.body.innerText.slice(0, 900) : 'N/A'"
    )
    print("TEXT:", repr(text))
    btns = await page.evaluate(
        "JSON.stringify(Array.from(document.querySelectorAll('button, a, [role=button]'))"
        ".slice(0, 14).map(function(b){ return (b.innerText||b.textContent||'').trim().slice(0,45) }))"
    )
    print("BTNS:", btns)
    await cdp.close()

asyncio.run(main())
