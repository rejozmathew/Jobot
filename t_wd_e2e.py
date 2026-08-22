"""Single-session drive: from a clean /apply entry, upload resume, verify it
is registered in the file input, click Continue (same session, no reload).
If Continue doesn't advance, fall back to 'Apply Manually' -> step 2.
Goal: land on step 2 'My Information'.
"""
import asyncio, sys, json, os
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

RESUME = r"C:\Users\rejoz\OneDrive\Documents\2026 Resume\AI balanced\Rejo_Z_Mathew_Resume.pdf"
BASE = ("https://fanniemae.wd1.myworkdayjobs.com/en-US/FannieMaeCareers/job/"
        "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677")

async def main():
    assert os.path.exists(RESUME), "resume missing"
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    sess = page._session

    async def state():
        url = await page.evaluate("location.href")
        body = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,300)"))
        return url, body

    # 1) Go to the resume-upload step (signed-in, fresh).
    await page.goto(BASE + "/apply/autofillWithResume")
    await asyncio.sleep(10)
    url, body = await state()
    print("START:", url, flush=True)
    print("BODY:", body[:200], flush=True)

    # 2) Attach the resume via the file input node.
    doc = await sess.call("DOM.getDocument", {"depth": -1})
    root = doc.get("root", {}).get("nodeId")
    node = await sess.call("DOM.querySelector", {"nodeId": root,
        "selector": "[data-automation-id=file-upload-input-ref], input[type=file]"})
    node_id = node.get("nodeId")
    print("FILE NODE:", node_id, flush=True)
    if not node_id:
        print("NO FILE INPUT", flush=True); await cdp.close(); return
    await sess.call("DOM.setFileInputFiles", {"files": [os.path.abspath(RESUME)], "nodeId": node_id})
    print("ATTACHED", flush=True)
    await asyncio.sleep(6)

    # 3) Verify the upload registered (file input value + success chip).
    val = await page.evaluate(
        "(function(){var i=document.querySelector('input[type=file]');"
        " return i ? (i.files && i.files.length) + ' files | val=' + (i.value||'') : 'no input';})()")
    chip = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ')"))
    uploaded = ("Successfully Uploaded" in chip) or ("successfully uploaded" in chip.lower())
    print("FILE INPUT:", val, "| success chip:", uploaded, flush=True)

    # 4) Click Continue (trusted) in the SAME session.
    async def trusted_click(sel):
        t = await page.evaluate(
            "(function(){var e=document.querySelector('" + sel + "');"
            " if(!e) return null; e.scrollIntoView({block:'center'});"
            " var r=e.getBoundingClientRect();"
            " return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)});})()")
        if not t:
            return False
        p = json.loads(t)
        await sess.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": p["x"], "y": p["y"]})
        await asyncio.sleep(0.15)
        await sess.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": p["x"], "y": p["y"], "button": "left", "clickCount": 1, "buttons": 1})
        await asyncio.sleep(0.25)
        await sess.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": p["x"], "y": p["y"], "button": "left", "clickCount": 1, "buttons": 0})
        return True

    before = await page.evaluate("location.href")
    ok = await trusted_click("[data-automation-id=pageFooterNextButton]")
    print("CONTINUE CLICKED:", ok, flush=True)
    await asyncio.sleep(10)
    url2, body2 = await state()
    advanced = (url2 != before) or ("current step 2 of 7" in body2)
    print("ADVANCED:", advanced, "| URL:", url2, flush=True)
    print("BODY2:", body2[:250], flush=True)

    # 5) Fallback: if not advanced, go to entry panel and click Apply Manually.
    if not advanced:
        print("FALLBACK: Apply Manually", flush=True)
        await page.goto(BASE + "/apply")
        await asyncio.sleep(9)
        ok2 = await trusted_click("[data-automation-id=applyManually]")
        print("APPLY MANUALLY CLICKED:", ok2, flush=True)
        await asyncio.sleep(10)
        url3, body3 = await state()
        print("URL3:", url3, flush=True)
        print("BODY3:", body3[:300], flush=True)
    await cdp.close()

asyncio.run(main())
