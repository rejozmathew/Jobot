"""Read the exact inline validation errors + Capital One state after the failed submit."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    # all visible error-like text
    errs = await page.evaluate(
        "(function(){var r=[];var a=document.querySelectorAll('[class*=error],[class*=invalid],[role=alert],.field-error,[aria-invalid=true]');"
        "for(var i=0;i<a.length;i++){var t=a[i].textContent.trim().replace(/\\s+/g,' ');if(t&&t.length<90)r.push({cls:(a[i].className||'').slice(0,25),t:t});}"
        "return r;})()")
    print("ERRORS:")
    for e in errs: print("   ", e)
    # Capital One committed value (scoped)
    co = await page.evaluate(
        "(function(){var e=document.getElementById('question_36313315002');var c=e.closest('.select__control');var v=c.querySelector('.select__single-value,.select__value-container');return v?v.textContent.trim():'(empty)';})()")
    print("CapitalOne committed:", repr(co))
    # Is the follow-up EID input currently required (aria)?
    eid = await page.evaluate(
        "(function(){var e=document.getElementById('question_36313323002');return {req:e.required, aria:e.getAttribute('aria-required'), ariaInv:e.getAttribute('aria-invalid'), cls:(e.className||'').slice(0,40)};})()")
    print("EID field:", json.dumps(eid))
    await b._session.close()

asyncio.run(main())
