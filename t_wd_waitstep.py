"""Check current state after resume upload; look for parse dialogs / progress.
Click Continue again if still on step 1 and the button is enabled."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    sess = page._session

    for i in range(6):
        await asyncio.sleep(5)
        url = await page.evaluate("location.href")
        body = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,700)"))
        print(f"--- poll {i} URL: {url}", flush=True)
        print("BODY:", body, flush=True)
        if "current step 2 of 7" in body or "/apply/myInformation" in url or "My Information" in url:
            print("ADVANCED TO STEP 2", flush=True)
            break

        # If still on step 1 and a modal/dialog is present, report it.
        dialogs = await page.evaluate(
            "JSON.stringify(Array.from(document.querySelectorAll('[role=dialog], .wd-Modal, [class*=Modal], [class*=modal]')).map(function(d){return (d.innerText||'').slice(0,200)}))")
        print("DIALOGS:", dialogs, flush=True)
    await cdp.close()

asyncio.run(main())
