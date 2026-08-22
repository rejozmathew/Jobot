"""Inspect the Capital One section: both fields, full labels, real state."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    # full labels
    for fid in ["question_36313315002","question_36313323002"]:
        lab = await page.evaluate("(function(){var e=document.getElementById('" + fid + "-label')||document.getElementById('" + fid + "');var l=e?e.closest('label')||e.parentElement:null;return l?l.textContent.trim().replace(/\\s+/g,' '):'';})()")
        # react state value
        st = await page.evaluate("(function(){var e=document.getElementById('" + fid + "');if(!e)return '(noel)';var c=e.closest('.select__control');if(c){var v=c.querySelector('.select__single-value,.select__value-container');return (v?v.textContent.trim():'(empty)');}return 'text:'+(e.value||'');})()")
        print(f"[{fid}]")
        print(f"    label = {lab}")
        print(f"    state = {st!r}")
    # Is the follow-up a text input or select? required?
    t = await page.evaluate("(function(){var e=document.getElementById('question_36313323002');if(!e)return null;return {tag:e.tagName, type:e.type, req:e.required, cls:(e.className||'').slice(0,40)};})()")
    print("follow-up control:", json.dumps(t))
    # Does the follow-up have an error marker now?
    err = await page.evaluate("(function(){var e=document.getElementById('question_36313323002');var f=e?e.closest('[class*=error],[class*=invalid],label'):null;return f?f.textContent.trim().slice(0,80):'';})()")
    print("follow-up error text:", repr(err))
    await b._session.close()

asyncio.run(main())
