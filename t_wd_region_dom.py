"""Dump the Region field's DOM structure to find the true clickable trigger."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS = """
(() => {
  const el = document.querySelector('#address--countryRegion');
  if (!el) return JSON.stringify({err:'none'});
  const out = {
    tag: el.tagName,
    role: el.getAttribute('role'),
    aid: el.getAttribute('data-automation-id'),
    cls: (el.className||'').toString().slice(0,80),
    txt: (el.textContent||'').trim().slice(0,60),
    rect: (r=>[Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)])(el.getBoundingClientRect()),
    parentTag: el.parentElement?el.parentElement.tagName:null,
    parentAid: el.parentElement?el.parentElement.getAttribute('data-automation-id'):null,
    parentCls: el.parentElement?(el.parentElement.className||'').toString().slice(0,80):null,
    children: [...el.children].map(c=>({tag:c.tagName, role:c.getAttribute('role'), aid:c.getAttribute('data-automation-id'), cls:(c.className||'').toString().slice(0,40), txt:(c.textContent||'').trim().slice(0,30), clickable:c.tagName==='BUTTON'||c.getAttribute('role')==='button'||c.getAttribute('role')==='combobox'||c.getAttribute('role')==='listbox'})),
    outer: el.outerHTML.slice(0, 600)
  };
  return JSON.stringify(out);
})()
"""

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    print(await page.evaluate(JS))
    await cdp.close()

asyncio.run(main())
