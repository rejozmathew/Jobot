"""Step 1: upload the resume via CDP DOM.setFileInputFiles, then click Continue.
"""
import asyncio, sys, json, os
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

RESUME = r"C:\Users\rejoz\OneDrive\Documents\2026 Resume\AI balanced\Rejo_Z_Mathew_Resume.pdf"

async def main():
    assert os.path.exists(RESUME), f"resume missing: {RESUME}"
    print("RESUME:", RESUME, os.path.getsize(RESUME), "bytes", flush=True)

    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    sess = page._session

    # Resolve the file input node.
    r = await sess.call("Runtime.querySelector", {
        "expression": "",  # placeholder
    }) if False else None

    # Use DOM.querySelector against the main frame document.
    doc = await sess.call("DOM.getDocument", {"depth": -1})
    root = doc.get("root", {}).get("nodeId")
    node = await sess.call("DOM.querySelector", {
        "nodeId": root,
        "selector": "[data-automation-id=file-upload-input-ref], input[type=file]",
    })
    node_id = node.get("nodeId")
    print("FILE INPUT NODE:", node_id, flush=True)
    if not node_id:
        print("NO FILE INPUT FOUND", flush=True)
        return

    await sess.call("DOM.setFileInputFiles", {
        "files": [os.path.abspath(RESUME)],
        "nodeId": node_id,
    })
    print("RESUME ATTACHED", flush=True)
    await asyncio.sleep(3)

    # Check if the UI reflects the uploaded file (some text near the drop zone).
    txt = await page.evaluate(
        "(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,600)")
    print("BODY:", txt, flush=True)

    # Click Continue (trusted).
    btn = await page.evaluate(
        "(function(){"
        " var b=document.querySelector('[data-automation-id=pageFooterNextButton]');"
        " if(!b) return null; b.scrollIntoView({block:'center'}); var r=b.getBoundingClientRect();"
        " return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2),"
        " text:(b.innerText||'').trim()});"
        "})()")
    print("CONTINUE BTN:", btn, flush=True)
    if btn:
        b = json.loads(btn)
        await sess.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": b["x"], "y": b["y"]})
        await asyncio.sleep(0.1)
        await sess.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": b["x"], "y": b["y"], "button": "left", "clickCount": 1})
        await asyncio.sleep(0.15)
        await sess.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": b["x"], "y": b["y"], "button": "left", "clickCount": 1})
        print("CLICKED Continue", flush=True)
        await asyncio.sleep(8)
        url = await page.evaluate("location.href")
        title = await page.evaluate("document.title")
        print("URL:", url, flush=True)
        print("TITLE:", title, flush=True)
        body2 = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,500)"))
        print("BODY2:", body2, flush=True)
    await cdp.close()

asyncio.run(main())
