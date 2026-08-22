"""Dump the exact input selectors (by aria-label) for the My Information text fields."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS = r"""
(() => {
  const inputs = [...document.querySelectorAll('input:not([type=hidden]):not([type=radio]):not([type=checkbox]),textarea')].map(el => ({
    tag: el.tagName,
    type: el.type||'',
    aid: el.getAttribute('data-automation-id'),
    id: el.id||'',
    name: el.name||'',
    aria: el.getAttribute('aria-label')||'',
    ph: el.placeholder||'',
    val: (el.value||'').slice(0,30),
    required: el.required||el.getAttribute('aria-required')
  }));
  return JSON.stringify(inputs);
})()
"""
async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    print(await page.evaluate(JS))
asyncio.run(main())
