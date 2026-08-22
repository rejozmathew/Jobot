"""Check Ethos post-submit state — is it on the confirmation page?"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    await asyncio.sleep(2)
    url = await page.evaluate("location.href")
    title = await page.evaluate("document.title")
    body = await page.evaluate("document.body ? document.body.innerText.slice(0,700) : ''")
    print("URL:", url)
    print("TITLE:", title)
    print("BODY:", body.replace("\n"," | ")[:600])
    await b._session.close()

asyncio.run(main())
