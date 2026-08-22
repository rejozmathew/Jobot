"""Re-locate the Continue button after upload and click it (trusted)."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    sess = page._session

    # List footer buttons + state.
    info = await page.evaluate(
        "(function(){"
        " var btns=Array.from(document.querySelectorAll('[data-automation-id=pageFooterNextButton], button'));"
        " return JSON.stringify(btns.filter(function(b){return /continue|skip|next|upload|done/i.test((b.innerText||''))})"
        "   .map(function(b){ var r=b.getBoundingClientRect();"
        "     return {aid:b.getAttribute('data-automation-id'), text:(b.innerText||'').trim(),"
        "     dis:b.disabled, x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2),"
        "     w:Math.round(r.width), h:Math.round(r.height)}; }));"
        "})()")
    print("BTNS:", info, flush=True)

    btn = await page.evaluate(
        "(function(){"
        " var b=document.querySelector('[data-automation-id=pageFooterNextButton]');"
        " if(!b) return null; b.scrollIntoView({block:'center'}); var r=b.getBoundingClientRect();"
        " return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2),"
        " text:(b.innerText||'').trim(), dis:b.disabled});"
        "})()")
    print("TARGET:", btn, flush=True)
    if not btn:
        print("no target", flush=True)
        return
    b = json.loads(btn)
    if b.get("dis"):
        print("button DISABLED - cannot proceed", flush=True)
        return
    await sess.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": b["x"], "y": b["y"]})
    await asyncio.sleep(0.15)
    await sess.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": b["x"], "y": b["y"], "button": "left", "clickCount": 1})
    await asyncio.sleep(0.2)
    await sess.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": b["x"], "y": b["y"], "button": "left", "clickCount": 1})
    print("CLICKED Continue", flush=True)
    await asyncio.sleep(12)
    url = await page.evaluate("location.href")
    body = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,700)"))
    print("URL:", url, flush=True)
    print("BODY:", body, flush=True)
    await cdp.close()

asyncio.run(main())
