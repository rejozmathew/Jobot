"""Click the EXACT form submit button signInSubmitButton via a TRUSTED CDP
mouse event (Input.dispatchMouseEvent), then report whether the login advanced.
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    # Confirm the form values are still present.
    vals = await page.evaluate(
        "JSON.stringify({em:(document.querySelector('[data-automation-id=email]')||{}).value,"
        " pw:(document.querySelector('[data-automation-id=password]')||{}).value ?"
        " document.querySelector('[data-automation-id=password]').value.length : 0})"
    )
    print("FILL:", vals, flush=True)

    # Locate the exact submit button (viewport coords after centering).
    btn = await page.evaluate(
        "(function(){"
        " var b=document.querySelector('[data-automation-id=\"signInSubmitButton\"]');"
        " if(!b) return null;"
        " b.scrollIntoView({block:'center'}); var r=b.getBoundingClientRect();"
        " return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2),"
        " disabled:b.disabled, text:(b.innerText||'').trim()});"
        "})()"
    )
    print("BTN:", btn, flush=True)
    if not btn:
        print("NO SUBMIT BUTTON", flush=True)
        return

    b = json.loads(btn)
    sess = page._session
    await sess.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": b["x"], "y": b["y"]})
    await asyncio.sleep(0.1)
    await sess.call("Input.dispatchMouseEvent",
                    {"type": "mousePressed", "x": b["x"], "y": b["y"], "button": "left", "clickCount": 1})
    await asyncio.sleep(0.15)
    await sess.call("Input.dispatchMouseEvent",
                    {"type": "mouseReleased", "x": b["x"], "y": b["y"], "button": "left", "clickCount": 1})
    print("CLICKED signInSubmitButton (trusted)", flush=True)
    await asyncio.sleep(10)

    url = await page.evaluate("location.href")
    title = await page.evaluate("document.title")
    body = (await page.evaluate(
        "(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,500)"))
    print("URL:", url, flush=True)
    print("TITLE:", title, flush=True)
    print("BODY:", body, flush=True)
    await cdp.close()

asyncio.run(main())
