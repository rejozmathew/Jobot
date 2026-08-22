"""Dump the Region + 'How Did You Hear' field triggers by label, with exact
selectors, plus all combobox-ish controls on the page."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS = r"""
(() => {
  const out = {region:null, hear:null, comboboxes:[]};
  // Find label elements and their associated controls
  const labels = [...document.querySelectorAll('label')];
  for (const lb of labels) {
    const t = (lb.textContent||'').trim();
    if (/region/i.test(t) && !out.region) {
      // The control is usually a sibling button
      let el = lb.closest('[data-automation-id], div');
      const btn = el ? el.querySelector('button, [role=combobox], [role=button]') : null;
      out.region = {label:t, btn_aid: btn?btn.getAttribute('data-automation-id'):null, btn_id: btn?btn.id:null, btn_text: btn?(btn.textContent||'').trim().slice(0,50):null};
    }
    if (/hear about/i.test(t) && !out.hear) {
      let el = lb.closest('[data-automation-id], div');
      const btn = el ? el.querySelector('button, [role=combobox], [role=button]') : null;
      out.hear = {label:t, btn_aid: btn?btn.getAttribute('data-automation-id'):null, btn_id: btn?btn.id:null, btn_text: btn?(btn.textContent||'').trim().slice(0,50):null};
    }
  }
  // All combobox-ish controls
  for (const c of document.querySelectorAll('[role=combobox], button[data-automation-id*=combobox], button[data-automation-id*=region], button[data-automation-id*=source]')) {
    out.comboboxes.push({aid:c.getAttribute('data-automation-id'), id:c.id, text:(c.textContent||'').trim().slice(0,50)});
  }
  return JSON.stringify(out);
})()
"""

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    print(await page.evaluate(JS))
    cdp.close()

asyncio.run(main())
