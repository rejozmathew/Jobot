"""Ethos step 1: load posting, find apply link, open the form."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    await asyncio.sleep(6)
    url = await page.evaluate("location.href")
    print("URL:", url[:100])
    print("TITLE:", (await page.evaluate("document.title"))[:80])
    # find the apply link
    apply_url = await page.evaluate(r"""
      (function(){
        var as = Array.prototype.slice.call(document.querySelectorAll('a'));
        for (var i=0;i<as.length;i++){
          var t=(as[i].textContent||'').trim();
          if (/apply|how to apply|start application/i.test(t) && /job_app|greenhouse/i.test(as[i].href||'')){
            return as[i].href;
          }
        }
        // fallback: any link with job_app
        for (var j=0;j<as.length;j++){ if (/job_app/.test(as[j].href||'')) return as[j].href; }
        return null;
      })()
    """)
    print("APPLY_URL:", apply_url)
    await b._session.close()

asyncio.run(main())
