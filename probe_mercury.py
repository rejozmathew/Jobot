import asyncio, json
from job_applier.cdp_client import CDPBrowser

URL = "https://job-boards.greenhouse.io/mercury/jobs/6141014004"

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    p = await b.get_current_page()
    await p.goto(URL, timeout=45)
    await asyncio.sleep(5)

    # focus country
    await p.evaluate("""
    (() => { const el=document.getElementById('country')||document.querySelector('[name="country"]');
      el.scrollIntoView({block:'center'}); el.focus(); return true; })()
    """)
    await asyncio.sleep(0.3)
    # CDP open (real key)
    await b.press_key("ArrowDown", 40)
    await asyncio.sleep(1.5)
    # type to filter
    await b.type_text("United States")
    await asyncio.sleep(3.0)
    # read filtered options
    opts = await p.evaluate("""
    (() => Array.from(document.querySelectorAll('[role="option"], li[role="option"]'))
      .slice(0,6).map(o=>(o.textContent||'').trim().slice(0,40)).filter(Boolean) )()
    """)
    print("FILTERED:", json.dumps(opts))
    # CDP Enter (real key)
    await b.press_key("Enter", 13)
    await asyncio.sleep(1.5)
    val = await p.evaluate("""
    (() => { const el=document.getElementById('country')||document.querySelector('[name="country"]');
      const single=(document.querySelector('.select__single-value,[class*="single-value"]')||{}).textContent;
      return {value:el?el.value:null, single:(single||'').trim()}; })()
    """)
    print("COMMITTED:", json.dumps(val))

asyncio.run(main())
