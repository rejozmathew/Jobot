import asyncio, json
from job_applier.cdp_client import CDPBrowser

OPTS_JS = r"""
(function(){
  var m=document.querySelector('[role=listbox]');
  if(!m) return [];
  return Array.from(m.querySelectorAll('[role=option]')).map(function(o){return (o.textContent||'').trim();}).slice(0,18);
})()
"""

async def main():
    b=await CDPBrowser.connect("http://127.0.0.1:9222"); page=await b.get_current_page()
    url=await page.evaluate("location.href") or ""
    if "gusto" not in url.lower():
        await page.goto("https://job-boards.greenhouse.io/gusto/jobs/7948318"); await asyncio.sleep(8)
    ids=["605","606","607","608","609","610","1012"]
    for fid in ids:
        await page.evaluate("(function(){var e=document.getElementById(%r);if(e)e.focus();return !!e;})()" % fid)
        await asyncio.sleep(0.4)
        await b.press_key("ArrowDown",40); await asyncio.sleep(1.8)
        opts=await page.evaluate(OPTS_JS)
        await b.press_key("Escape",27); await asyncio.sleep(0.5)
        print("[%s] %s" % (fid, json.dumps(opts)))
asyncio.run(main())
