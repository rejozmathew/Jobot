"""Check current state after the timed-out submit: URL + body + confirmation."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    url = await page.evaluate("location.href")
    print("URL:", url[:120])
    try:
        title = await page.evaluate("document.title")
        print("TITLE:", title)
    except Exception as e:
        print("title EXC", e)
    body = await page.evaluate("(document.body?document.body.innerText:'')")
    low = body.lower()
    print("BODY[0:600]:")
    print(body[:600])
    if "thank" in low or "submitted" in low or "we've received" in low or "successfully" in low or "all set" in low or "application has been" in low:
        print("\n>>> CONFIRMATION DETECTED <<<")
    elif "required" in low or "fix the following" in low or "this field" in low:
        print("\n>>> STILL REJECTED <<<")
    else:
        print("\n>>> NEEDS INSPECTION <<<")
    await b._session.close()

asyncio.run(main())
