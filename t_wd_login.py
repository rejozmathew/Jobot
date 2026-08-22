"""Sign in on the Workday /login page (signInFormo) with the profile creds,
then report the resulting page state (should redirect into the JR2677 apply flow).
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

PROFILE = json.loads(open("profile.json", encoding="utf-8").read())
ACC = PROFILE["accounts"]["default"]
EMAIL, PASSWORD = ACC["email"], ACC["password"]

FILL = (
    "(function(){"
    " var email=" + json.dumps(EMAIL) + ", pw=" + json.dumps(PASSWORD) + ";"
    " function setV(el,v){var d=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value');"
    " d.set.call(el,v); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); el.dispatchEvent(new Event('blur',{bubbles:true}));}"
    " var em=document.querySelector('[data-automation-id=\"email\"]');"
    " var pwEl=document.querySelector('[data-automation-id=\"password\"]');"
    " if(!em||!pwEl) return 'missing-fields';"
    " em.focus(); setV(em,email); pwEl.focus(); setV(pwEl,pw);"
    " return 'em='+em.value+' pwlen='+(pwEl?pwEl.value.length:0);"
    "})()"
)

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    s = page._session
    url0 = await page.evaluate("window.location.href")
    print("START URL:", url0, flush=True)

    print("FILL:", await page.evaluate(FILL), flush=True)
    await asyncio.sleep(0.6)

    # Click the login submit button (trusted CDP mouse at viewport coords).
    btn = await page.evaluate(
        "(function(){"
        " var b=document.querySelector('[data-automation-id=\"signInSubmitButton\"]');"
        " if(!b){"
        "   b = Array.from(document.querySelectorAll('button, [type=submit]'))"
        "       .find(function(x){ return (x.innerText||'').trim()==='Sign In'; });"
        " }"
        " if(!b) return null;"
        " b.scrollIntoView({block:'center'}); var r=b.getBoundingClientRect();"
        " return JSON.stringify({x:r.x+r.width/2, y:r.y+r.height/2, disabled:b.disabled, text:(b.innerText||'').trim()});"
        "})()"
    )
    print("BTN:", btn, flush=True)
    if btn:
        rc = json.loads(btn)
        if not rc.get("disabled"):
            await s.call("Input.dispatchMouseEvent", {"type":"mouseMoved","x":rc["x"],"y":rc["y"]})
            await s.call("Input.dispatchMouseEvent", {"type":"mousePressed","x":rc["x"],"y":rc["y"],"button":"left","clickCount":1})
            await s.call("Input.dispatchMouseEvent", {"type":"mouseReleased","x":rc["x"],"y":rc["y"],"button":"left","clickCount":1})
            print("CLICKED sign-in", flush=True)
        else:
            print("submit disabled", flush=True)
    await asyncio.sleep(9)

    url = await page.evaluate("window.location.href")
    title = await page.evaluate("document.title")
    print("URL:", url)
    print("TITLE:", title)
    body = await page.evaluate("document.body ? document.body.innerText.slice(0, 1200) : 'N/A'")
    print("BODY:", repr(body))
    btns = await page.evaluate(
        "JSON.stringify(Array.from(document.querySelectorAll('button, a, [role=button]')).slice(0, 20).map(function(b){ return (b.innerText||b.textContent||'').trim().slice(0, 45) }))"
    )
    print("BTNS:", btns)
    try:
        await cdp.screenshot("artifacts/wd_after_signin.png")
        print("screenshot: artifacts/wd_after_signin.png")
    except Exception as e:
        print("screenshot failed:", e)
    await cdp.close()

asyncio.run(main())
