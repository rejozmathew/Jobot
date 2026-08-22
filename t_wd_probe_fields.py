"""Inspect the Region combobox + 'How Did You Hear About' dropdown + previous-worker
radio structure so we can fill them precisely."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS = r"""
(() => {
  const out = {};
  // All comboboxes / listbox triggers
  const combos = [...document.querySelectorAll('[data-automation-id*="Region"],[data-automation-id*="region"],[data-automation-id*="State"],[data-automation-id*="state"],[data-automation-id*="comboBox"],[data-automation-id*="ComboBox"],[data-automation-id*="promptSearch"],[data-automation-id*="select"],[aria-haspopup="listbox"]')].map(el => ({
    aid: el.getAttribute('data-automation-id'),
    tag: el.tagName, role: el.getAttribute('role'),
    text: (el.textContent||'').trim().slice(0,50),
    aria: el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || ''
  }));
  out.combos = combos.slice(0,12);
  // 'How Did You Hear' area: find the label, then the nearest combobox
  const labels = [...document.querySelectorAll('*')].filter(el => {
    const t = (el.textContent||'').trim();
    return t.startsWith('How Did You Hear') && el.children.length < 3;
  }).slice(0,3).map(el => ({ tag: el.tagName, aid: el.getAttribute('data-automation-id'), text: el.textContent.trim().slice(0,60) }));
  out.hearLabels = labels;
  // Previous worker radios
  const radios = [...document.querySelectorAll('input[type=radio],[role=radio],[data-automation-id*="radio"],[data-automation-id*="previous"]')].map(el => ({
    tag: el.tagName, aid: el.getAttribute('data-automation-id'),
    name: el.getAttribute('name')||'', val: el.getAttribute('value')||'',
    checked: el.checked || el.getAttribute('aria-checked'),
    text: (el.textContent||'').trim().slice(0,30)
  })).slice(0,12);
  out.radios = radios;
  // Any 'LinkedIn' text options currently in DOM (dropdowns may be closed)
  const hasLinkedIn = !!document.body.innerText.includes('LinkedIn');
  out.hasLinkedIn = hasLinkedIn;
  return JSON.stringify(out);
})()
"""

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    r = await page.evaluate(JS)
    print(r[:3000])
asyncio.run(main())
