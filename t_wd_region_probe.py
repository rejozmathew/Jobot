"""Precise probe: click Region trigger, then dump ONLY visible option-like
elements (rect>0, offsetParent!=null), with positions + which list container."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

def click_xy(sess, x, y):
    pass

async def click_xy(page, x, y):
    sess = page._session
    await sess.call("Input.dispatchMouseEvent", {"type":"mouseMoved","x":x,"y":y})
    await asyncio.sleep(0.05)
    await sess.call("Input.dispatchMouseEvent", {"type":"mousePressed","x":x,"y":y,"button":"left","clickCount":1})
    await asyncio.sleep(0.05)
    await sess.call("Input.dispatchMouseEvent", {"type":"mouseReleased","x":x,"y":y,"button":"left","clickCount":1})

TRIGGER_JS = """
(() => {
  const el = document.querySelector('%s');
  if (!el) return JSON.stringify({err:'no-trigger'});
  el.scrollIntoView({block:'center'});
  const r = el.getBoundingClientRect();
  return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), tag:el.tagName, txt:(el.textContent||'').trim().slice(0,40), aid:el.getAttribute('data-automation-id')});
})()
"""

VISIBLE_OPTS_JS = """
(() => {
  const out = [];
  const cands = document.querySelectorAll("[role='option'], li[role='option'], [class*='menuItem'], [class*='listItem'], [class*='optionItem'], ul li");
  for (const e of cands) {
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    const visible = (r.width>0 && r.height>0 && cs.display!=='none' && cs.visibility!=='hidden' && e.offsetParent!==null);
    if (!visible) continue;
    const t = (e.textContent||'').trim();
    if (t && t.length<60) out.push({t, x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), role:e.getAttribute('role'), cls:(e.className||'').toString().slice(0,40)});
  }
  return JSON.stringify(out.slice(0,120));
})()
"""

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    btn = json.loads(await page.evaluate(TRIGGER_JS % "#address--countryRegion"))
    print("trigger:", btn)
    await click_xy(page, btn["x"], btn["y"])
    await asyncio.sleep(1.5)
    opts = json.loads(await page.evaluate(VISIBLE_OPTS_JS))
    print(f"visible options: {len(opts)}")
    for o in opts[:40]:
        print("  ", o['t'], o['x'], o['y'], o.get('role'), o.get('cls'))
    await cdp.close()

asyncio.run(main())
