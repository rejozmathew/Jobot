"""Full field map + country options, using the PROVEN plain-expression style."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def click_xy(b, x, y):
    s = b._session
    for ty in ("mouseDown","mouseUp"):
        await s.call("Input.dispatchMouseEvent",
            {"type":ty,"x":int(x),"y":int(y),"button":"left","clickCount":1,"pointerType":"mouse"})
    await asyncio.sleep(0.15)

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()

    # 1. map id -> label (via label[for] or aria-label)
    ids = await page.evaluate("Array.from(document.querySelectorAll('input,select,textarea')).map(function(e){return e.id})")
    labels = await page.evaluate(
        "Array.from(document.querySelectorAll('input,select,textarea')).map(function(e){"
        " var l=''; if(e.id){var lb=document.querySelector('label[for=\"'+e.id+'\"]'); if(lb)l=lb.textContent.trim();}"
        " if(!l)l=e.getAttribute('aria-label')||''; if(!l){var p=e.closest('.field,[class*=field]');if(p){var l2=p.querySelector('label');if(l2)l=l2.textContent.trim();}}"
        " return (e.id||'')+' || '+(e.type||e.tagName.toLowerCase())+' || '+l;})")
    print("=== FIELD MAP ===")
    for L in labels:
        print("  ", L)

    # 2. country: find it, scroll, click control, read options
    print("\n=== COUNTRY OPTIONS ===")
    r = await page.evaluate(
        "(function(){var el=document.getElementById('country');if(!el)return null;"
        " el.scrollIntoView({block:'center'});var c=el.closest('.select__control')||el;"
        " var bb=c.getBoundingClientRect();return {x:bb.left+bb.width/2,y:bb.top+bb.height/2,"
        " vis:bb.top>=0&&bb.bottom<=innerHeight, expanded:el.getAttribute('aria-expanded')};})()")
    print("  country geom:", r)
    if r and r.get("vis") and r.get("expanded")!="true":
        await click_xy(b, r["x"], r["y"])
        await asyncio.sleep(1.2)
    opts = await page.evaluate(
        "Array.from(document.querySelectorAll('[role=listbox] li, .select__option')).map(function(x){return x.textContent.trim()})")
    print("  options count:", len(opts))
    for o in opts[:40]:
        print("    -", o)
    # specifically USA / United
    usa = [o for o in opts if "usa" in o.lower() or "united" in o.lower() or "u.s" in o.lower() or o.strip()=="US"]
    print("  USA-ish:", usa)
    await page.press_key("Escape", 27)
    await b._session.close()

asyncio.run(main())
