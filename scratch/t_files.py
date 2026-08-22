"""Inspect the Attach / resume upload area thoroughly."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    # count + list ALL file inputs (any type)
    data = await page.evaluate(
        "(function(){var r=[];var a=document.querySelectorAll('input[type=file]');"
        "for(var i=0;i<a.length;i++){var e=a[i];"
        "var lab='';var l=e.closest('label');if(l)lab=l.textContent.trim().replace(/\\s+/g,' ');"
        "var sec=e.closest('[class*=section],[class*=attach],[class*=file]');"
        "r.push({idx:i,id:e.id,name:e.name,accept:e.accept,label:lab.slice(0,40),sec:sec?sec.className.slice(0,30):''});}"
        "return r;})()"
    )
    print("ALL FILE INPUTS (count=%d):" % len(data))
    for d in data: print("  ", d)
    # Any element with role=button or a <button> that says Attach / Resume / Upload
    btns = await page.evaluate(
        "(function(){var r=[];var a=document.querySelectorAll('button,[role=button],label');for(var i=0;i<a.length;i++){var t=a[i].textContent.trim().replace(/\\s+/g,' ');if(/resume|attach|upload|cover/i.test(t)&&t.length<40)r.push(t);}"
        "return Array.from(new Set(r));})()"
    )
    print("upload-ish buttons:", btns)
    await b._session.close()

asyncio.run(main())
