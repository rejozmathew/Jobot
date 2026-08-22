"""Deep diagnostic on the Create Account form: button state, validation,
field values, error containers. Then attempt ONE clean click and capture
whether the page advances or an error appears.
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

PROFILE = json.loads(open("profile.json", encoding="utf-8").read())
ACC = PROFILE["accounts"]["default"]
EMAIL, PASSWORD = ACC["email"], ACC["password"]

DIAG = (
    "(function(){"
    " var btn = document.querySelector('[data-automation-id=\"createAccountSubmitButton\"]');"
    " var out = {};"
    " out.btn = btn ? {disabled: btn.disabled, cls: btn.className, "
    "   ariaDisabled: btn.getAttribute('aria-disabled'), rect: (function(){var r=btn.getBoundingClientRect();return {y:Math.round(r.y),h:Math.round(r.height),inView: r.top>=0&&r.bottom<=window.innerHeight};})()} : null;"
    " var errs = Array.from(document.querySelectorAll('[role=alert], [class*=error i], [class*=Error], .errorMessage, [aria-live]'))"
    "   .map(function(e){return (e.innerText||'').trim().slice(0,80);}).filter(Boolean);"
    " out.errors = errs.slice(0,8);"
    " var em = document.querySelector('[data-automation-id=\"email\"]');"
    " var pw = document.querySelector('[data-automation-id=\"password\"]');"
    " var vp = document.querySelector('[data-automation-id=\"verifyPassword\"]');"
    " out.values = {email: em?em.value:null, pw: pw?pw.value.length:0, vp: vp?vp.value.length:0, "
    "   emValid: em? em.validity.valid : null, emState: em? JSON.stringify(em.validity):null};"
    " out.formInvalid = (function(){var f=btn.closest('form'); return f? f.checkValidity() : null;})();"
    " out.formCheckValidity = (function(){var f=btn.closest('form');"
    "   if(!f) return null;"
    "   var bad = Array.from(f.elements).filter(function(e){return e.willValidate && !e.checkValidity();})"
    "     .map(function(e){return (e.getAttribute('data-automation-id')||e.name||e.id)+':'+JSON.stringify(e.validity);});"
    "   return bad.slice(0,6);})();"
    " return JSON.stringify(out);"
    "})()"
)

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    s = page._session

    print("BEFORE:", await page.evaluate(DIAG), flush=True)

    # Re-fill cleanly (React-safe), scoped to the real form fields.
    fill = (
        "(function(){"
        " var email=" + json.dumps(EMAIL) + ", pw=" + json.dumps(PASSWORD) + ";"
        " function setV(el,v){var d=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value');"
        " d.set.call(el,v); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); el.dispatchEvent(new Event('blur',{bubbles:true}));}"
        " var em=document.querySelector('[data-automation-id=\"email\"]');"
        " var pwEl=document.querySelector('[data-automation-id=\"password\"]');"
        " var vpEl=document.querySelector('[data-automation-id=\"verifyPassword\"]');"
        " if(em){em.focus(); setV(em,email);}"
        " if(pwEl){pwEl.focus(); setV(pwEl,pw);}"
        " if(vpEl){vpEl.focus(); setV(vpEl,pw);}"
        " return 'em='+em.value+' pwlen='+(pwEl?pwEl.value.length:0)+' vplen='+(vpEl?vpEl.value.length:0);"
        "})()"
    )
    print("FILL:", await page.evaluate(fill), flush=True)
    await asyncio.sleep(0.6)

    print("AFTER-FILL:", await page.evaluate(DIAG), flush=True)

    # One clean trusted click on the create button.
    btn = await page.evaluate(
        "(function(){var b=document.querySelector('[data-automation-id=\"createAccountSubmitButton\"]');"
        " b.scrollIntoView({block:'center'}); var r=b.getBoundingClientRect();"
        " return JSON.stringify({x:r.x+r.width/2, y:r.y+r.height/2, disabled:b.disabled});})()"
    )
    rc = json.loads(btn)
    if not rc["disabled"]:
        await s.call("Input.dispatchMouseEvent", {"type":"mouseMoved","x":rc["x"],"y":rc["y"]})
        await s.call("Input.dispatchMouseEvent", {"type":"mousePressed","x":rc["x"],"y":rc["y"],"button":"left","clickCount":1})
        await s.call("Input.dispatchMouseEvent", {"type":"mouseReleased","x":rc["x"],"y":rc["y"],"button":"left","clickCount":1})
        print("CLICKED create button", flush=True)
    else:
        print("BUTTON DISABLED - not clicking", flush=True)
    await asyncio.sleep(7)

    url = await page.evaluate("window.location.href")
    title = await page.evaluate("document.title")
    print("URL:", url)
    print("TITLE:", title)
    print("POST-CLICK DIAG:", await page.evaluate(DIAG), flush=True)
    body = await page.evaluate("document.body ? document.body.innerText.slice(0, 800) : 'N/A'")
    print("BODY:", repr(body))
    await cdp.close()

asyncio.run(main())
