"""Fill the two comboboxes: Region -> Illinois, How Did You Hear -> LinkedIn.
Click trigger by ID, wait for option list, click matching option.
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

TRIGGER_JS = """
(() => {
  const el = document.querySelector('%s');
  if (!el) return JSON.stringify({err:'no-trigger'});
  el.scrollIntoView({block:'center'});
  const r = el.getBoundingClientRect();
  if (r.width<1||r.height<1) return JSON.stringify({err:'zero-size', rect:[r.x,r.y,r.width,r.height]});
  return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), tag:el.tagName, text:(el.textContent||'').trim().slice(0,40)});
})()
"""

OPTIONS_JS = """
(() => {
  const out = [];
  const sel = "[role='option'], li[role='option'], [data-automation-id*='option'], [class*='menuItem'], [class*='listItem'], ul[class*='menu'] li";
  for (const e of document.querySelectorAll(sel)) {
    const t = (e.textContent||'').trim();
    if (t && t.length < 80) {
      const r = e.getBoundingClientRect();
      out.push({t, x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)});
    }
  }
  return JSON.stringify(out.slice(0,120));
})()
"""

async def click_xy(page, x, y):
    sess = page._session
    await sess.call("Input.dispatchMouseEvent", {"type":"mouseMoved","x":x,"y":y})
    await asyncio.sleep(0.05)
    await sess.call("Input.dispatchMouseEvent", {"type":"mousePressed","x":x,"y":y,"button":"left","clickCount":1})
    await asyncio.sleep(0.05)
    await sess.call("Input.dispatchMouseEvent", {"type":"mouseReleased","x":x,"y":y,"button":"left","clickCount":1})

async def pick_option(page, trigger_sel, target_texts):
    btn = json.loads(await page.evaluate(TRIGGER_JS % trigger_sel))
    if 'err' in btn:
        return False, f"trigger-error:{btn}"
    await click_xy(page, btn["x"], btn["y"])
    await asyncio.sleep(1.2)
    opts = json.loads(await page.evaluate(OPTIONS_JS))
    if not opts:
        return False, "no-options-list-opened"
    # prefer exact, then substring
    tl_targets = [t.lower() for t in target_texts]
    chosen = None
    for o in opts:
        tl = o['t'].lower().replace('\xa0',' ').strip()
        if tl in tl_targets:
            chosen = o; break
    if not chosen:
        for o in opts:
            tl = o['t'].lower().replace('\xa0',' ').strip()
            if any(tt in tl for tt in tl_targets):
                chosen = o; break
    if not chosen:
        return False, f"no-match (had {len(opts)}): {[o['t'] for o in opts[:10]]}"
    await click_xy(page, chosen["x"], chosen["y"])
    await asyncio.sleep(0.8)
    return True, f"selected:{chosen['t']}"

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    ok1, n1 = await pick_option(page, "#address--countryRegion", ["Illinois", "IL", "Illinois (IL)"])
    print("Region:", ok1, n1[:90])

    ok2, n2 = await pick_option(page, "#source--source", ["LinkedIn", "Linkedin", "Linked In", "LinkedIn"])
    print("Source:", ok2, n2[:90])

    v = json.loads(await page.evaluate("""
    (() => {
      const g = (id) => { const e=document.querySelector('#'+id); return e?(e.textContent||'').trim().slice(0,50):null; };
      return JSON.stringify({region: g('address--countryRegion'), source: g('source--source')});
    })()
    """))
    print("VERIFIED:", v)
    await cdp.close()

asyncio.run(main())
