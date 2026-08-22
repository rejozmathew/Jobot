"""Read the full question_* labels (they live in label[id^=question_-label])."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    # All labels whose id ends with -label
    data = await page.evaluate(
        "(function(){"
        "var r=[];var ls=document.querySelectorAll('label[id$=\"-label\"], label[id^=\"question_\"]');"
        "for(var i=0;i<ls.length;i++){r.push({id:ls[i].id, text:ls[i].textContent.trim().replace(/\\s+/g,' ')});}"
        "return r;})()"
    )
    for d in data:
        print(f"[{d['id']}]  {d['text'][:90]}")
    print("=== ALL labels in form (text) ===")
    labs = await page.evaluate(
        "(function(){var r=[];var ls=document.querySelectorAll('label');for(var i=0;i<ls.length;i++){var t=ls[i].textContent.trim().replace(/\\s+/g,' ');if(t)r.push(t);}return r;})()"
    )
    for t in labs:
        print("   *", t[:95])
    await b._session.close()

asyncio.run(main())
