"""Enumerate all automation-id elements + inputs on the current page."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS_AID = (
    "JSON.stringify(Array.from(document.querySelectorAll('[data-automation-id]')).map(function(e){"
    " return {tag:e.tagName, id:e.id, aid:e.getAttribute('data-automation-id'),"
    "   text:(e.innerText||'').trim().slice(0,25), form: !!e.closest('form')};}))"
)
JS_INPUTS = (
    "JSON.stringify(Array.from(document.querySelectorAll('input')).map(function(e){"
    " return {type:e.type, name:e.name, id:e.id,"
    "   aid:(e.getAttribute('data-automation-id')||e.getAttribute('name')||''),"
    "   form: !!e.closest('form'), vlen:(e.value||'').length, ph:e.placeholder||''};}))"
)

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    print("AID:", await page.evaluate(JS_AID), flush=True)
    print("INPUTS:", await page.evaluate(JS_INPUTS), flush=True)
    await cdp.close()

asyncio.run(main())
