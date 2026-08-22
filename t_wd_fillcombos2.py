"""Set a tall CDP viewport so the whole My Information form is in view, then
fill Region -> Illinois and Source -> LinkedIn (clicks now land correctly)."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def click_xy(page, x, y):
    sess = page._session
    await sess.call("Input.dispatchMouseEvent", {"type":"mouseMoved","x":x,"y":y})
    await asyncio.sleep(0.05)
    await sess.call("Input.dispatchMouseEvent", {"type":"mousePressed","x":x,"y":y,"button":"left","clickCount":1})
    await asyncio.sleep(0.05)
    await sess.call("Input.dispatchMouseEvent", {"type":"mouseReleased","x":x,"y":y,"button":"left","clickCount":1})

async def scroll_into_view_and_rect(page, sel):
    r = json.loads(await page.evaluate("""
    (() => {
      const el = document.querySelector('%s');
      if (!el) return JSON.stringify({err:'none'});
      el.scrollIntoView({block:'center', behavior:'instant'});
      // force-scroll any scrollable ancestors to center the element
      let node = el.parentElement;
      while (node && node !== document.documentElement) {
        const cs = getComputedStyle(node);
        if (/(auto|scroll)/.test(cs.overflowY) || /(auto|scroll)/.test(cs.overflow)) {
          const nr = node.getBoundingClientRect();
          const er = el.getBoundingClientRect();
          node.scrollTop += (er.top + er.height/2) - (nr.top + nr.height/2);
        }
        node = node.parentElement;
      }
      window.scrollTo(0,0);
      const rr = el.getBoundingClientRect();
      return JSON.stringify({x:Math.round(rr.x+rr.width/2), y:Math.round(rr.y+rr.height/2), tag:el.tagName});
    })()
    """ % sel))
    return r

TRIGGER_REMEASURE = """
(() => {
  const el = document.querySelector('%s');
  const r = el.getBoundingClientRect();
  return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), tag:el.tagName});
})()
"""

VISIBLE_OPTS_JS = """
(() => {
  const vh = window.innerHeight, vw = window.innerWidth;
  const out = [];
  const cands = document.querySelectorAll("[role='option'], li[role='option'], [class*='menuItem'], [class*='listItem'], [class*='optionItem'], [class*='dropdown'] li, ul[class*='list'] li");
  for (const e of cands) {
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    const visible = (r.width>2 && r.height>2 && r.top>=-5 && r.top<vh && r.left>=-5 && r.left<vw && cs.display!=='none' && cs.visibility!=='hidden' && e.offsetParent!==null);
    if (!visible) continue;
    const t = (e.textContent||'').trim();
    if (t && t.length<60) out.push({t, x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)});
  }
  return JSON.stringify(out.slice(0,150));
})()
"""

async def pick(page, sel, targets):
    await scroll_into_view_and_rect(page, sel)
    await asyncio.sleep(0.4)
    btn = json.loads(await page.evaluate(TRIGGER_REMEASURE % sel))
    if 'err' in btn: return False, f"no-trigger"
    # ensure in viewport
    if btn['y'] < 40 or btn['y'] > 1560: 
        # still out of the tall viewport; report
        pass
    await click_xy(page, btn["x"], btn["y"])
    await asyncio.sleep(1.3)
    opts = json.loads(await page.evaluate(VISIBLE_OPTS_JS))
    tl = [t.lower() for t in targets]
    chosen = None
    for o in opts:
        if o['t'].lower().replace('\xa0',' ').strip() in tl: chosen = o; break
    if not chosen:
        for o in opts:
            if any(tt in o['t'].lower() for tt in tl): chosen = o; break
    if not chosen:
        return False, f"no-match of {len(opts)} visible: {[o['t'] for o in opts[:12]]}"
    await click_xy(page, chosen['x'], chosen['y'])
    await asyncio.sleep(0.9)
    return True, f"selected:{chosen['t']} (trigger@{btn['x']},{btn['y']}; {len(opts)} opts)"

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    # Tall viewport so the full form is visible
    await page._session.call("Emulation.setDeviceMetricsOverride",
                             {"width":1200, "height":1700, "deviceScaleFactor":1, "mobile":False})
    await asyncio.sleep(0.8)

    ok1, n1 = await pick(page, "#address--countryRegion", ["Illinois", "IL", "Illinois (IL)"])
    print("Region:", ok1, n1[:120])

    ok2, n2 = await pick(page, "#source--source", ["LinkedIn", "Linkedin", "Linked In"])
    print("Source:", ok2, n2[:120])

    v = json.loads(await page.evaluate("""
    (() => {
      const g = (id) => { const e=document.querySelector('#'+id); return e?(e.textContent||'').trim().slice(0,50):null; };
      return JSON.stringify({region: g('address--countryRegion'), source: g('source--source'), phone: g('phoneNumber--phoneNumber')});
    })()
    """))
    print("VERIFIED:", v)
    await cdp.close()

asyncio.run(main())
