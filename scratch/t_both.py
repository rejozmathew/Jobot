"""Back-to-back: stable check + raw input dump in ONE session."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()

    # stability
    for i in range(3):
        n = await page.evaluate("document.querySelectorAll('input').length")
        print(f"[stable {i}] inputs={n}")
        await asyncio.sleep(0.5)

    # now the multi-selector
    print("\n[multi] input,select,textarea =",
          await page.evaluate("document.querySelectorAll('input,select,textarea').length"))

    # raw: grab first 5 inputs' ids via a plain expression (no IIFE)
    print("\n[raw1] inputs[0..4] ids:")
    r = await page.evaluate("Array.from(document.querySelectorAll('input')).slice(0,5).map(function(e){return (e.id||'')+' | '+(e.name||'')+' | '+(e.type||'')})")
    print("   ", r)

    await b._session.close()

asyncio.run(main())
