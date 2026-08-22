"""Decisive test: what does the handler's click target resolve to, and does a TRUSTED click navigate?"""
import asyncio, json, sys
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

POST = ("https://fanniemae.wd1.myworkdayjobs.com/FannieMaeCareers/job/"
        "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677")
ART = "artifacts"

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    await page.goto(POST)
    await asyncio.sleep(6)

    # What does the handler's selector actually match, in order?
    matches = await page.evaluate("""
    () => Array.from(document.querySelectorAll("a[href*='apply']")).slice(0,8)
       .map((el,i)=>({i, t:(el.textContent||'').trim().slice(0,40), href:el.getAttribute('href')||'', da:el.getAttribute('data-automation-id')||'', vis:(()=>{const s=getComputedStyle(el);const r=el.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;})()}))
    """)
    print("a[href*='apply'] matches (in order):", flush=True)
    for m in matches:
        print("  ", json.dumps(m), flush=True)

    # What the real Apply button is
    real = await page.evaluate("""
    () => { const el = document.querySelector("[data-automation-id='adventureButton']") || Array.from(document.querySelectorAll('button,[role=button]')).find(b=>/apply/i.test(b.textContent||'')); if(!el) return null; const r=el.getBoundingClientRect(); return {tag:el.tagName, t:(el.textContent||'').trim().slice(0,40), da:el.getAttribute('data-automation-id')||'', href:el.getAttribute('href')||'', x:r.x+r.width/2, y:r.y+r.height/2, vis:r.width>0&&r.height>0}; }
    """)
    print("\nreal Apply button:", json.dumps(real), flush=True)

    # Now: trusted mouse click on the REAL apply button, watch for navigation or new tab
    before_url = page.url_current
    if real and real.get("x"):
        x, y = real["x"], real["y"]
        await cdp._session.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        await asyncio.sleep(0.3)
        await cdp._session.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await cdp._session.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    await asyncio.sleep(8)
    after_url = page.url_current
    print(f"\nbefore: {before_url}", flush=True)
    print(f"after : {after_url}", flush=True)
    print("NAVIGATED:", before_url != after_url, flush=True)

    # count tabs
    import urllib.request
    try:
        tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5))
        pages = [t for t in tabs if t["type"] == "page"]
        print("tab count:", len(pages), flush=True)
        for t in pages:
            print("  tab:", t["url"][:100], flush=True)
    except Exception as e:
        print("tab check failed:", e, flush=True)

    await cdp.screenshot(f"{ART}/wd_aftertrustedclick.png")
    print("screenshot ->", f"{ART}/wd_aftertrustedclick.png", flush=True)
    await cdp.close()

asyncio.run(main())
