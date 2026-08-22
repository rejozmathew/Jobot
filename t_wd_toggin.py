"""Switch the Create-Account form to Sign-In mode via signInLink, then
enumerate the sign-in fields + submit button so we can fill and submit.
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    s = page._session

    # Click the FORM's "Sign In" toggle (signInLink), not the header nav button.
    r = await page.evaluate(
        "(function(){"
        " var btn = document.querySelector('[data-automation-id=\"signInLink\"]');"
        " if(!btn) return 'no-signinlink';"
        " btn.scrollIntoView({block:'center'});"
        " btn.click();"
        " return 'clicked';"
        "})()"
    )
    print("toggle:", r, flush=True)
    await asyncio.sleep(2.0)

    # Re-enumerate: automation-id elements + inputs after the toggle.
    aid = await page.evaluate(
        "JSON.stringify(Array.from(document.querySelectorAll('[data-automation-id]')).map(function(e){"
        " return {tag:e.tagName, aid:e.getAttribute('data-automation-id'),"
        "   text:(e.innerText||'').trim().slice(0,22), form:!!e.closest('form')};}))"
    )
    print("AID:", aid, flush=True)
    inputs = await page.evaluate(
        "JSON.stringify(Array.from(document.querySelectorAll('input')).map(function(e){"
        " return {type:e.type, id:e.id, aid:(e.getAttribute('data-automation-id')||''),"
        "   form:!!e.closest('form'), vlen:(e.value||'').length, ph:e.placeholder||''};}))"
    )
    print("INPUTS:", inputs, flush=True)
    body = await page.evaluate("document.body ? document.body.innerText.slice(0, 900) : 'N/A'")
    print("TEXT:", repr(body))
    await cdp.close()

asyncio.run(main())
