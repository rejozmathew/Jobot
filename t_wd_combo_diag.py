"""Clean diagnostic: reset viewport, open the Region combobox (JS click +
trusted click both), wait for lazy options, dump ALL listboxes + their options."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    # Reset any device-metrics override to natural size
    try:
        await page._session.call("Emulation.clearDeviceMetricsOverride")
        await asyncio.sleep(0.5)
    except Exception as e:
        print("clear metrics err:", e)

    # Scroll Region into view and report position
    pos = json.loads(await page.evaluate("""
    (() => {
      const el = document.querySelector('#address--countryRegion');
      el.scrollIntoView({block:'center'});
      const r = el.getBoundingClientRect();
      return JSON.stringify({y:Math.round(r.y), h:Math.round(r.height), iw:window.innerWidth, ih:window.innerHeight});
    })()
    """))
    print("Region pos after scroll:", pos)

    # Open via JS .click() (React-friendly)
    opened = await page.evaluate("""
    (() => {
      const el = document.querySelector('#address--countryRegion');
      if (!el) return 'no-el';
      el.click();
      return 'clicked';
    })()
    """)
    print("js click:", opened)
    await asyncio.sleep(2.0)

    # Dump ALL listboxes + their options (visible or not)
    dump = json.loads(await page.evaluate("""
    (() => {
      const lbs = [...document.querySelectorAll("[role='listbox'], ul[role='listbox'], [class*='listbox'], [class*='menu-list']")];
      const out = lbs.map((lb,i) => {
        const r = lb.getBoundingClientRect();
        const cs = getComputedStyle(lb);
        const opts = [...lb.querySelectorAll('[role=option], li, [class*=option]')];
        return {
          i, cls:(lb.className||'').toString().slice(0,40),
          visible: (r.height>0 && cs.display!=='none' && cs.visibility!=='hidden' && lb.offsetParent!==null),
          h:Math.round(r.height), n:opts.length,
          first5: opts.slice(0,5).map(o=>(o.textContent||'').trim().slice(0,30)),
          hasIL: opts.some(o=>/illinois/i.test(o.textContent||''))
        };
      });
      return JSON.stringify(out);
    })()
    """))
    print("listboxes:", json.dumps(dump, indent=1))

    # Also: is there a search input now visible inside a combobox?
    search = json.loads(await page.evaluate("""
    (() => {
      const ins = [...document.querySelectorAll('input[type=search], input[placeholder], [role=combobox] input, [class*=search] input')];
      return JSON.stringify(ins.map(i=>({ph:i.placeholder||null, type:i.type, vis:i.offsetParent!==null, id:i.id, aria:i.getAttribute('aria-label')})).slice(0,15));
    })()
    """))
    print("search inputs:", search)

    await cdp.close()

asyncio.run(main())
