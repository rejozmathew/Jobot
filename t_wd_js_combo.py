"""Test get_elements_by_css_selector on the Region button + JS .click() to open
the list + find Illinois option + JS click it. Pure DOM, no coordinates."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS_TEST_SELECTORS = """
(() => {
  const out = {};
  const test = (sel) => {
    try {
      const els = document.querySelectorAll(sel);
      out[sel] = els.length;
    } catch(e) { out[sel] = 'ERR'; }
  };
  test("button[id*='region' i]");
  test("#address--countryRegion");
  test("button[id='address--countryRegion']");
  test("[id*='countryRegion' i]");
  return JSON.stringify(out);
})()
"""

JS_CLICK_REGION = """
(() => {
  const btn = document.querySelector('#address--countryRegion');
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
      out.push({t:(it.textContent||'').trim().slice(0,50), h:Math.round(ir.height)});
    }
  }
  return JSON.stringify(out);
})()
"""

JS_CLICK_ILLINOIS = """
(() => {
  const lbs = [...document.querySelectorAll("[role='listbox']")];
  for (const lb of lbs) {
    const items = [...lb.querySelectorAll('[role=option], li, [class*=option]')];
    for (const it of items) {
      const t = (it.textContent||'').trim();
      if (t.toLowerCase().includes('illinois')) { it.click(); return JSON.stringify({clicked:t}); }
    }
  }
  return JSON.stringify({err:'not-found'});
})()
"""

JS_VERIFY_REGION = """
(() => {
  const e = document.querySelector('#address--countryRegion');
  return e ? (e.textContent||'').trim().slice(0,40) : null;
})()
"""

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    print("Selector tests:", await page.evaluate(JS_TEST_SELECTORS))

    print("JS click Region:", await page.evaluate(JS_CLICK_REGION))
    await asyncio.sleep(2.0)

    opts = json.loads(await page.evaluate(JS_FIND_OPTIONS))
    print(f"Visible options: {len(opts)}")
    for o in opts[:30]:
        print("  ", o['t'])
    illinois = [o for o in opts if 'illinois' in o['t'].lower()]
    print("Illinois options:", illinois)

    if illinois:
        clicked = await page.evaluate(JS_CLICK_ILLINOIS)
        print("Clicked:", clicked)
        await asyncio.sleep(1.0)
        v = await page.evaluate(JS_VERIFY_REGION)
        print("Region now:", v)

    await cdp.close()

asyncio.run(main())
