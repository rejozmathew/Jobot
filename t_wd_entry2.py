"""Investigate the signed-in /apply entry panel: all buttons + their exact
data-automation-ids, and test clicking 'Apply Manually' via BOTH trusted-mouse
and JS .click() to see which advances (and capture the destination URL)."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

BASE = "https://fanniemae.wd1.myworkdayjobs.com/FannieMaeCareers/job/Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677"
ENTRY = BASE + "/apply"

def click_xy(sess, x, y):
    return asyncio.gather(
        sess.call("Input.dispatchMouseEvent", {"type":"mouseMoved","x":x,"y":y}),
        sess.call("Input.dispatchMouseEvent", {"type":"mousePressed","x":x,"y":y,"button":"left","buttons":1,"clickCount":1}),
        sess.call("Input.dispatchMouseEvent", {"type":"mouseReleased","x":x,"y":y,"button":"left","buttons":0,"clickCount":1}),
    )

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    await page.goto(ENTRY)
    await asyncio.sleep(5)
    url = page.url
    # all clickable candidates
    cands = json.loads(await page.evaluate(
        "JSON.stringify(Array.from(document.querySelectorAll('a,button,[role=button]')).filter(e=>{var t=(e.innerText||'').trim();return t.length>0&&t.length<40}).map(e=>({aid:e.getAttribute('data-automation-id'),tag:e.tagName,txt:(e.innerText||'').trim().slice(0,35),x:Math.round(e.getBoundingClientRect().x),y:Math.round(e.getBoundingClientRect().y)})))"
    ))
    print("URL:", url)
    print("ENTRY PANEL CANDIDATES:")
    for c in cands: print("  ", json.dumps(c))
    await cdp.close()

asyncio.run(main())
