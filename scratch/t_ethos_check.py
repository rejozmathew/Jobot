"""Check post-submit state of the Ethos form."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    await asyncio.sleep(2)
    url = await page.evaluate("location.href")
    title = await page.evaluate("document.title")
    body = await page.evaluate("document.body ? document.body.innerText.slice(0,900) : ''")
    print("URL:", url)
    print("TITLE:", title)
    print("BODY:", body.replace("\n"," | ")[:700])
    # any inline errors?
    errs = await page.evaluate(r"""
      (function(){
        return Array.prototype.slice.call(document.querySelectorAll('[class*=error], .form__error, .text-danger, [class*=invalid]'))
          .map(function(e){return (e.innerText||'').trim();}).filter(Boolean).slice(0,10);
      })()""")
    print("ERRORS:", errs)
    await b._session.close()

asyncio.run(main())
