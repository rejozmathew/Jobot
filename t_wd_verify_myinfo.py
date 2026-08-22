"""Select Source = LinkedIn, verify ALL My Information fields, screenshot."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS_SELECT_LINKEDIN = """
(() => {
  const btn = document.querySelector('#source--source');
  if (!btn) return JSON.stringify({err:'no-btn'});
  btn.click();
  return JSON.stringify({opened:true});
})()
"""

JS_CLICK_LINKEDIN = """
(() => {
  const lbs = [...document.querySelectorAll("[role='listbox']")];
  for (const lb of lbs) {
    const r = lb.getBoundingClientRect();
    if (r.height < 5) continue;
    const items = [...lb.querySelectorAll('[role=option], li, [class*=option]')];
    for (const it of items) {
      const t = (it.textContent||'').trim();
      const ir = it.getBoundingClientRect();
      if (ir.height < 2) continue;
      if (t.toLowerCase() === 'linkedin') { it.click(); return JSON.stringify({selected:t}); }
    }
  }
  return JSON.stringify({err:'not-found'});
})()
"""

JS_VERIFY_ALL = """
(() => {
  const g = (id) => { const e = document.querySelector('#'+id); return e ? (e.value || (e.textContent||'').trim()).slice(0,60) : null; };
  const chk = (id) => { const e = document.querySelector('#'+id); return e ? (e.checked ? 'ON' : 'off') : null; };
  // Previous worker radios: find the checked one among the radio group
  const prevRadios = [...document.querySelectorAll('input[name="candidateIsPreviousWorker"]')];
  const prevChecked = prevRadios.find(r => r.checked);
  return JSON.stringify({
    first: g('name--legalName--firstName'),
    last: g('name--legalName--lastName'),
    prevworker_checked: prevChecked ? prevChecked.value : 'none',
    prevworker_count: prevRadios.length,
    region: g('address--countryRegion'),
    city: g('address--city'),
    zip: g('address--postalCode'),
    street: g('address--addressLine1'),
    phone: g('phoneNumber--phoneNumber'),
    phone_code: g('phoneNumber--countryPhoneCode'),
    source: g('source--source')
  });
})()
"""

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    # Open Source combobox
    r1 = await page.evaluate(JS_SELECT_LINKEDIN)
    print("Open Source:", r1)
    await asyncio.sleep(1.5)

    # Click LinkedIn
    r2 = await page.evaluate(JS_CLICK_LINKEDIN)
    print("Select LinkedIn:", r2)
    await asyncio.sleep(1.0)

    # Verify all fields
    v = json.loads(await page.evaluate(JS_VERIFY_ALL))
    print("\n=== MY INFORMATION FORM (verified) ===")
    for k, val in v.items():
        print(f"  {k:20}: {val}")

    # Screenshot
    try:
        cdp_url = "http://127.0.0.1:9222"
        import urllib.request
        tabs = json.loads(urllib.request.urlopen(f"{cdp_url}/json").read())
        target = next(t for t in tabs if "fanniemae" in t.get("url",""))
        ws_url = target["webSocketDebuggerUrl"]
        # Use CDP Page.captureScreenshot
        # For simplicity, just log that we'd screenshot
        print("\nScreenshot: (use browser tool to capture)")
    except Exception as e:
        print(f"\nScreenshot note: {e}")

    await cdp.close()

asyncio.run(main())
