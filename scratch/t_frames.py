"""Probe: find where the form fields actually live (page vs iframe)."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    print("MAIN URL:", (await page.evaluate("location.href"))[:100])
    frames = await page.evaluate(r"""
      () => Array.from(document.querySelectorAll('iframe')).map(f=>({
        src:(f.src||'').slice(0,90), id:f.id, name:f.name,
        w:f.offsetWidth, h:f.offsetHeight}))
    """)
    print("IFRAMES on main page:", json.dumps(frames, indent=1))
    n_inputs = await page.evaluate("document.querySelectorAll('input').length")
    n_body = await page.evaluate("document.body ? document.body.innerText.length : 0")
    print("inputs on main doc:", n_inputs, "| body text len:", n_body)
    print("body snippet:", (await page.evaluate("document.body.innerText.slice(0,200)")))
    await b._session.close()

asyncio.run(main())
