"""From the /apply entry panel (signed-in), click 'Apply Manually' and
report where it lands. Goal: step 2 'My Information'."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

BASE = ("https://fanniemae.wd1.myworkdayjobs.com/en-US/FannieMaeCareers/job/"
        "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677")

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    sess = page._session

    await page.goto(BASE + "/apply")
    await asyncio.sleep(8)
    url = await page.evaluate("location.href")
    body = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,300)"))
    print("PANEL URL:", url, flush=True)
    print("PANEL:", body, flush=True)

    # Locate Apply Manually and click (trusted).
    tgt = await page.evaluate(
        "(function(){var a=document.querySelector('[data-automation-id=applyManually]');"
        " if(!a) return null; a.scrollIntoView({block:'center'}); var r=a.getBoundingClientRect();"
        " return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), text:a.innerText});})()")
    print("APPLY MANUALLY:", tgt, flush=True)
    if tgt:
        t = json.loads(tgt)
        await sess.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": t["x"], "y": t["y"]})
        await asyncio.sleep(0.15)
        await sess.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": t["x"], "y": t["y"], "button": "left", "clickCount": 1, "buttons": 1})
        await asyncio.sleep(0.2)
        await sess.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": t["x"], "y": t["y"], "button": "left", "clickCount": 1, "buttons": 0})
        print("CLICKED Apply Manually", flush=True)
    await asyncio.sleep(10)
    url2 = await page.evaluate("location.href")
    body2 = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,500)"))
    print("AFTER URL:", url2, flush=True)
    print("AFTER BODY:", body2, flush=True)
    step = "current step 2 of 7" in body2
    print("STEP2?", step, flush=True)
    await cdp.close()

asyncio.run(main())
