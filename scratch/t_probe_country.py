"""Probe: open the standard Country select, dump options + react fiber value."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = CDPBrowser("http://127.0.0.1:9222"); await b.connect()
    page = await b.get_current_page()
    print("URL:", (await page.evaluate("location.href"))[:80])

    async def click_xy(x, y):
        s = b._session
        for t, ty in [("mousePressed","mouseDown"),("mouseReleased","mouseUp")]:
            await s.call("Input.dispatchMouseEvent",
                {"type": ty, "x": int(x), "y": int(y), "button": "left",
                 "clickCount": 1, "pointerType": "mouse"})
        await asyncio.sleep(0.15)

    async def geom():
        r = await page.evaluate(
            "(id)=>{const el=document.getElementById(id);const r=el.getBoundingClientRect();"
            "return{x:r.left+r.width/2,y:r.top+r.height/2,vis:r.top>=0&&r.bottom<=innerHeight}}",
            arg="country")
        return r

    # Try clicking control center to open; if closed already (aria-expanded true), skip
    async def expanded():
        return (await page.evaluate(
            "(id)=>document.getElementById(id).getAttribute('aria-expanded')", arg="country"))

    # First: does a menu already exist?
    opts0 = await page.evaluate(
        "()=>Array.from(document.querySelectorAll('[role=listbox] li, .select__option'))"
        ".map(x=>x.textContent.trim()).slice(0,20)")
    print("existing options:", opts0)

    if (await expanded()) != "true":
        g = await geom()
        print("geom:", g)
        if g.get("vis"):
            await click_xy(g["x"], g["y"])
            await asyncio.sleep(1.2)
            print("after open aria-expanded:", await expanded())
            opts = await page.evaluate(
                "()=>Array.from(document.querySelectorAll('[role=listbox] li, .select__option'))"
                ".map(x=>x.textContent.trim()).slice(0,30)")
            print("options after open:", opts)
            # look for USA specifically
            usa = await page.evaluate(
                "()=>Array.from(document.querySelectorAll('[role=listbox] li, .select__option'))"
                ".filter(x=>/USA|United/i.test(x.textContent))"
                ".map(x=>x.textContent.trim()).slice(0,10)")
            print("USA-ish options:", usa)
    await b.close()

asyncio.run(main())
