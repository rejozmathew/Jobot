"""Check where we landed after Save & Continue: URL, heading, step, any errors."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS_STATE = """
(() => {
  const h = document.querySelector('h1, h2');
  const active = [...document.querySelectorAll('[aria-current], [class*=active]')].map(e=>(e.textContent||'').trim()).filter(t=>t&&t.length<40);
  const err = [...document.querySelectorAll('[role=alert], [class*=error], [class*=alert], [class*=banner]')].map(x=>(x.textContent||'').trim()).filter(t=>t&&t.length<160);
  const body = (document.body.innerText||'').slice(0,400);
  return JSON.stringify({
    url: location.href,
    heading: h ? h.textContent.trim().slice(0,80) : null,
    active: active.slice(0,4),
    errors: err.slice(0,5),
    bodyhead: body
  });
})()
"""

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    print(json.dumps(json.loads(await page.evaluate(JS_STATE)), indent=2))
    await cdp.close()

asyncio.run(main())
