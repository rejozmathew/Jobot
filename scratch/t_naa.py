"""Test: does putting a non-empty 'N/A' in the EID field clear its required error?
(Non-destructive: type it, check validation state, do NOT submit.)
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

def eid_state():
    return ("(function(){var e=document.getElementById('question_36313323002');"
            "if(!e)return '(gone)';var f=e.closest('label')||e.parentElement;"
            "var err=f?f.textContent.trim().indexOf('required')>=0:false;"
            "return {val:e.value||'', ariaReq:e.getAttribute('aria-required'), ariaInv:e.getAttribute('aria-invalid'), labelErr:err};})()")

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    fid = "question_36313323002"
    print("BEFORE:", json.dumps(await page.evaluate(eid_state())))
    await page.evaluate("document.getElementById('" + fid + "').focus();true")
    await asyncio.sleep(0.3)
    await b.type_text("N/A")
    await asyncio.sleep(0.6)
    await page.evaluate("document.getElementById('" + fid + "').blur();true")
    await asyncio.sleep(0.8)
    print("AFTER typing N/A:", json.dumps(await page.evaluate(eid_state())))
    # restore to blank so we don't leave data
    await page.evaluate("document.getElementById('" + fid + "').focus();true")
    await page.evaluate("document.getElementById('" + fid + "').select();true")
    await b.type_text("")
    await page.evaluate("document.getElementById('" + fid + "').blur();true")
    await asyncio.sleep(0.4)
    print("RESTORED:", json.dumps(await page.evaluate(eid_state())))
    await b._session.close()

asyncio.run(main())
