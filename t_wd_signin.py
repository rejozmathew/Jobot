"""Sign in to the existing Workday account (target the Sign In form specifically),
then report the resulting page state so we can resume the JR2677 application.

Two forms coexist on this page (Create Account + Sign In). We scope to the form
containing the Sign In submit button so we don't fill the wrong panel.
"""
import asyncio, json, sys
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

PROFILE = json.loads(open("profile.json", encoding="utf-8").read())
ACC = PROFILE["accounts"]["default"]
EMAIL = ACC["email"]
PASSWORD = ACC["password"]

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    s = page._session

    # Locate the Sign In submit button and tag it so we can scope to its form.
    info = await page.evaluate(
        "(function(){"
        " var btn = document.querySelector('[data-automation-id*=\"signIn\" i], #signInSubmitButton');"
        " if(!btn){"
        "   btn = Array.from(document.querySelectorAll('button, a, [role=button]'))"
        "          .find(function(b){ return (b.innerText||'').trim()==='Sign In' && b.offsetParent!==null; });"
        " }"
        " if(!btn) return JSON.stringify({ok:false});"
        " var form = btn.closest('form');"
        " var scope = form || btn.parentElement.parentElement;"
        " btn.setAttribute('data-hs-target','1');"
        " return JSON.stringify({ok:true, hasForm:!!form,"
        "   emails: scope.querySelectorAll('input[type=email]').length,"
        "   pwds: scope.querySelectorAll('input[type=password]').length,"
        "   btnText:(btn.innerText||'').trim()});"
        "})()"
    )
    print("signin-scope:", info, flush=True)
    if not info.startswith('{"ok": true') and '"ok":false' in info.replace(" ", ""):
        print("ABORT: sign-in button not found", flush=True)
        await cdp.close()
        return

    # Fill the sign-in form (scoped) using the React-safe native setter.
    fill_expr = (
        "(function(){"
        " var email = " + json.dumps(EMAIL) + ";\n"
        " var pw = " + json.dumps(PASSWORD) + ";\n"
        " var btn = document.querySelector('[data-hs-target=\"1\"]');"
        " var scope = btn.closest('form') || btn.parentElement.parentElement;"
        " var em = scope.querySelector('input[type=email]');"
        " var pwEl = scope.querySelector('input[type=password]');"
        " if(!em || !pwEl) return 'missing-fields';"
        " function setV(el, v){"
        "   var d = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');"
        "   d.set.call(el, v);"
        "   el.dispatchEvent(new Event('input', {bubbles:true}));"
        "   el.dispatchEvent(new Event('change', {bubbles:true}));"
        " }"
        " em.focus(); setV(em, email);"
        " pwEl.focus(); setV(pwEl, pw);"
        " return 'filled em=' + em.value + ' pw=' + (pwEl.value ? 'set' : 'EMPTY');"
        "})()"
    )
    result = await s.call("Runtime.evaluate", {"expression": fill_expr, "returnByValue": True})
    val = result.get("result", {}).get("value") if isinstance(result, dict) else None
    print("fill-result:", val, flush=True)

    # Click the sign-in button with a trusted CDP mouse event at viewport coords.
    await asyncio.sleep(0.5)
    rect = await page.evaluate(
        "(function(){"
        " var btn = document.querySelector('[data-hs-target=\"1\"]');"
        " btn.scrollIntoView({block:'center'});"
        " var r = btn.getBoundingClientRect();"
        " return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});"
        "})()"
    )
    rc = json.loads(rect)
    await s.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": rc["x"], "y": rc["y"]})
    await s.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": rc["x"], "y": rc["y"], "button": "left", "clickCount": 1})
    await s.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": rc["x"], "y": rc["y"], "button": "left", "clickCount": 1})
    print("clicked sign-in", flush=True)
    await asyncio.sleep(9)

    url = await page.evaluate("window.location.href")
    title = await page.evaluate("document.title")
    text = await page.evaluate("document.body ? document.body.innerText.slice(0, 1400) : 'N/A'")
    print("URL:", url)
    print("TITLE:", title)
    print("TEXT:", repr(text))
    btns = await page.evaluate(
        "JSON.stringify(Array.from(document.querySelectorAll('button, a, [role=button]')).slice(0, 18).map(function(b){ return (b.innerText||b.textContent||'').trim().slice(0, 45) }))"
    )
    print("BTNS:", btns)
    try:
        await cdp.screenshot("artifacts/wd_signedin.png")
        print("screenshot: artifacts/wd_signedin.png")
    except Exception as e:
        print("screenshot failed:", e)
    await cdp.close()

asyncio.run(main())
