"""Open the 'How Did You Hear About Us' combobox via JS click and list options."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS_CLICK_SOURCE = """
(() => {
  const btn = document.querySelector('#source--source');
  if (!btn) return JSON.stringify({err:'no-btn'});
  btn.click();
  return JSON.stringify({clicked:true, text:btn.textContent});
})()
"""

JS_FIND_OPTIONS = """
(() => {
  const out = [];
  const lbs = [...document.querySelectorAll("[role='listbox']")];
  for (const lb of lbs) {
    const r = lb.getBoundingClientRect();
    if (r.height < 5) continue;
    const items = [...lb.querySelectorAll('[role=option], li, [class*=option]')];
    for (const it of items) {
      const ir = it.getBoundingClientRect();
      if (ir.height < 2) continue;
      out.push((it.textContent||'').trim().slice(0,60));
    }
  }
  return JSON.stringify(out);
})()
"""

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    print("Click Source:", await page.evaluate(JS_CLICK_SOURCE))
    await asyncio.sleep(1.5)
    opts = json.loads(await page.evaluate(JS_FIND_OPTIONS))
    print(f"Options: {len(opts)}")
    for o in opts[:30]:
        print("  ", o)
    await cdp.close()

asyncio.run(main())
