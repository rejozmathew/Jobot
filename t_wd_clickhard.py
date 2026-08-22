"""Find what's at the Continue button's center point + try alternative activation
paths: elementFromPoint check, focus+Enter, and a full pointer-event sequence."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    sess = page._session

    # 1. What's at the button center?
    center = await page.evaluate(
        "(function(){var b=document.querySelector('[data-automation-id=pageFooterNextButton]');"
        " if(!b) return null; var r=b.getBoundingClientRect();"
        " return JSON.stringify({cx:r.x+r.width/2, cy:r.y+r.height/2});})()")
    c = json.loads(center)
    at = await page.evaluate(
        "(function(){var e=document.elementFromPoint(" + str(c["cx"]) + "," + str(c["cy"]) + ");"
        " return e ? (e.tagName + '.' + (e.className||'') + ' aid=' + (e.getAttribute('data-automation-id')||'')) : 'null';})()")
    print("AT POINT:", at, flush=True)

    # 2. Is the button the target itself?
    btn = await page.evaluate(
        "(function(){var b=document.querySelector('[data-automation-id=pageFooterNextButton]');"
        " var e=document.elementFromPoint(" + str(c["cx"]) + "," + str(c["cy"]) + ");"
        " return (e===b) || b.contains(e);})()")
    print("BTN AT POINT:", btn, flush=True)

    # 3. Full pointer sequence (pointerover/move/down + mouse + pointerup) at the point.
    async def click_at(x, y, kind="mouse"):
        if kind == "pointer":
            await sess.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
            await asyncio.sleep(0.1)
        await sess.call("Input.dispatchMouseEvent",
                        {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1, "buttons": 1})
        await asyncio.sleep(0.2)
        await sess.call("Input.dispatchMouseEvent",
                        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1, "buttons": 0})

    before = await page.evaluate("location.href")
    # scroll the button into view first
    await page.evaluate("(function(){var b=document.querySelector('[data-automation-id=pageFooterNextButton]'); b.scrollIntoView({block:'center',inline:'center'});})()")
    await asyncio.sleep(1)
    c2 = await page.evaluate(
        "(function(){var b=document.querySelector('[data-automation-id=pageFooterNextButton]');"
        " var r=b.getBoundingClientRect(); return JSON.stringify({cx:r.x+r.width/2, cy:r.y+r.height/2});})()")
    c2 = json.loads(c2)
    at2 = await page.evaluate(
        "(function(){var e=document.elementFromPoint(" + str(c2["cx"]) + "," + str(c2["cy"]) + ");"
        " return e ? (e.tagName + '.' + (e.className||'') + ' aid=' + (e.getAttribute('data-automation-id')||'')) : 'null';})()")
    print("AT POINT (after scroll):", at2, flush=True)
    click_at(c2["cx"], c2["cy"])
    await asyncio.sleep(10)
    after = await page.evaluate("location.href")
    body = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,200)"))
    print("ADVANCED:", before != after, flush=True)
    print("URL:", after, flush=True)
    print("BODY:", body, flush=True)

    if before == after:
        # 4. Try focus + Enter key
        await page.evaluate("(function(){var b=document.querySelector('[data-automation-id=pageFooterNextButton]'); b.focus();})()")
        await asyncio.sleep(0.5)
        await sess.call("Input.dispatchKeyEvent",
                        {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        await sess.call("Input.dispatchKeyEvent",
                        {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        await asyncio.sleep(8)
        after2 = await page.evaluate("location.href")
        body2 = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,200)"))
        print("ENTER-ADVANCED:", before != after2, flush=True)
        print("URL2:", after2, flush=True)
        print("BODY2:", body2, flush=True)
    await cdp.close()

asyncio.run(main())
