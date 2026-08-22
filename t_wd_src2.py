"""Select Source = LinkedIn (open, wait, click) + verify the full My Info form."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS_OPEN_SOURCE = """
(() => {
  const btn = document.querySelector('#source--source');
  if (!btn) return JSON.stringify({err:'no-btn'});
  btn.click();
  return JSON.stringify({opened:true, text:btn.textContent});
})()
"""

JS_LISTBOXES = """
(() => {
  const lbs = [...document.querySelectorAll("[role='listbox']")];
  return JSON.stringify(lbs.map((lb,i) => {
    const r = lb.getBoundingClientRect();
    return {i, h:Math.round(r.height), vis:r.height>5, n:lb.querySelectorAll('li,[role=option],[class*=option]').length};
  }));
})()
"""

JS_CLICK_LINKEDIN = """
(() => {
  // Only click LinkedIn in a VISIBLE listbox
  const lbs = [...document.querySelectorAll("[role='listbox']")];
  for (const lb of lbs) {
    const r = lb.getBoundingClientRect();
    if (r.height < 5) continue;  // skip hidden/collapsed
    const items = [...lb.querySelectorAll('li, [role=option], [class*=option]')];
    for (const it of items) {
      const ir = it.getBoundingClientRect();
      if (ir.height < 2) continue;
      const t = (it.textContent||'').trim();
      if (t.toLowerCase() === 'linkedin') { it.click(); return JSON.stringify({selected:t, inListbox:h}); }
    }
  }
  return JSON.stringify({err:'not-found'});
})()
""".replace("inListbox:h","inListbox:r.height")

JS_VERIFY = """
(() => {
  const g = (id) => { const e = document.querySelector('#'+id); return e ? (e.textContent||'').trim().slice(0,50) : null; };
  return JSON.stringify({
    first: g('name--legalName--firstName'),
    last: g('name--legalName--lastName'),
    region: g('address--countryRegion'),
    city: g('address--city'),
    zip: g('address--postalCode'),
    street: g('address--addressLine1'),
    phone: g('phoneNumber--phoneNumber'),
    source: g('source--source')
  });
})()
"""

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    print("Open Source:", await page.evaluate(JS_OPEN_SOURCE))
    await asyncio.sleep(1.8)
    print("Listboxes:", await page.evaluate(JS_LISTBOXES))
    print("Click LinkedIn:", await page.evaluate(JS_CLICK_LINKEDIN))
    await asyncio.sleep(1.0)

    v = json.loads(await page.evaluate(JS_VERIFY))
    print("\n=== MY INFORMATION (verified) ===")
    for k,val in v.items(): print(f"  {k:8}: {val}")
    await cdp.close()

asyncio.run(main())
