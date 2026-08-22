"""Dump all inputs — using Array.from + for loop (page shims NodeList.forEach)."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    data = await page.evaluate(r"""
      () => {
        const all = Array.from(document.querySelectorAll('input, select, textarea'));
        const out = [];
        for (let i = 0; i < all.length; i++) {
          const el = all[i];
          let label = '';
          if (el.id) { const l=document.querySelector('label[for="'+el.id+'"]'); if(l) label=l.textContent.trim(); }
          if (!label) label = el.getAttribute('aria-label') || '';
          if (!label) { const p=el.closest('.field, [class*="field"]'); if(p){const l=p.querySelector('label'); if(l) label=l.textContent.trim();} }
          out.push({
            n:i, tag:el.tagName.toLowerCase(), type:el.type||'',
            id:el.id||'', name:el.name||'', cls:String(el.className||'').slice(0,40),
            label:(label||'').slice(0,55), req:el.required
          });
        }
        return out;
      }
    """)
    print(f"TOTAL INPUTS: {len(data)}")
    for d in data:
        print(f"{d['n']:3} {d['tag']:4} {d['type']:12} {d['id'][:24]:24} | {d['label']:40} | {d['cls']}")
    await b._session.close()

asyncio.run(main())
