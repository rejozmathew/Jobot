"""Fill the Workday legal-name verify textarea using the CDP-backed BU shim
(real keyboard events = React-accepted), then advance to step 4."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser
from job_applier.bu_compat import make_bu_session

TID = "primaryQuestionnaire--bbdfc74454f31001b82f1e1c667d0008"
LEGAL = "Rejo Z Mathew"

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    bu = make_bu_session(cdp)
    page = await bu.get_current_page()

    els = await page.get_elements_by_css_selector(f"#{TID}")
    if not els:
        print("TEXTAREA NOT FOUND"); await cdp.close(); return
    el = els[0]
    # scroll into view + focus
    await el.evaluate("(el)=>{ el.scrollIntoView({block:'center'}); el.focus(); return true; }")
    await asyncio.sleep(0.3)
    await el.fill(LEGAL)
    await asyncio.sleep(0.6)
    val = await el.evaluate("(el)=>el.value")
    print("TEXTAREA VALUE AFTER FILL:", repr(val))

    # advance
    r = await page.evaluate("""
    (() => { const b=[...document.querySelectorAll("button")].find(x=>/save and continue/i.test(x.textContent||"")); if(b){b.click();return true;} return false; })()
    """)
    print("ADVANCE CLICKED:", r)
    await asyncio.sleep(5.5)
    nxt = await page.evaluate("""
    (() => {
      const cur=document.querySelector("[class*=current]");
      const body=document.body.innerText.slice(0,280);
      const errs=[...document.querySelectorAll("[role=alert],[class*=error],[class*=Error]")].map(e=>(e.textContent||"").trim()).filter(t=>t&&t.length<150);
      return JSON.stringify({cur:cur?cur.textContent.trim().slice(0,25):null, errs:[...new Set(errs)].slice(0,3), body});
    })()
    """)
    print("NEXT:", nxt)
    await cdp.close()

asyncio.run(main())
