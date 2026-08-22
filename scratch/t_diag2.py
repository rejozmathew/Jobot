"""Diag: which tab is the handler attached to, and what's on the Figma posting page?"""
import asyncio, sys, json, urllib.request
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

targets = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=5))
pages = [t for t in targets if t["type"] == "page"]
print("=== CDP page targets (handler picks about:blank-first, else pages[0]) ===")
for i, t in enumerate(pages):
    print(f"  [{i}] {t['url'][:110]}")

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    print("\n=== handler's chosen tab ===")
    print("  url:", page.url)
    # navigate to the figma posting
    await page.goto("https://boards.greenhouse.io/figma/jobs/6130865004")
    await asyncio.sleep(8)
    print("  after goto:", (await page.evaluate("location.href"))[:120])
    print("  title:", (await page.evaluate("document.title"))[:90])
    links = await page.evaluate(r"""
      (function(){
        var out=[];
        Array.prototype.slice.call(document.querySelectorAll('a,button')).forEach(function(e){
          var t=(e.textContent||'').trim();
          if(/apply/i.test(t) && t.length<40) out.push((e.tagName)+': '+t+ (e.href?(' -> '+e.href.slice(0,60)):''));
        });
        return out.slice(0,12);
      })()""")
    print("  apply-like elements:", json.dumps(links, indent=1))
    nfields = await page.evaluate(r"""
      (function(){
        return Array.prototype.slice.call(document.querySelectorAll('input,select,textarea')).length;
      })()""")
    print("  inputs/selects/textareas:", nfields)
    await b._session.close()

asyncio.run(main())
