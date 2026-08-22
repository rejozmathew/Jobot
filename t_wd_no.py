import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS = r'''
(() => {
  const cks = [...document.querySelectorAll("input[type=checkbox]")];
  const labelOf = (c) => { const l = document.querySelector('label[for="' + c.id + '"]'); return l ? (l.textContent || "") : ""; };
  cks.forEach(c => { if (/I do not want to answer/i.test(labelOf(c))) { c.click(); } });
  const no = cks.find(c => /No, I do not have a disability/i.test(labelOf(c)));
  if (no) { no.click(); }
  const states = cks.map(c => ({ t: labelOf(c).slice(0, 30), c: c.checked }));
  const btn = [...document.querySelectorAll("button")].find(x => /save and continue/i.test(x.textContent || ""));
  return JSON.stringify({ states, btnDisabled: btn ? btn.disabled : null });
})()
'''

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    r = await page.evaluate(JS)
    print("STATE:", r)
    await asyncio.sleep(1)
    await cdp.close()

asyncio.run(main())
