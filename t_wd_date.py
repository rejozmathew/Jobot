"""Fill the Workday disability-form Date field (MM/DD/YYYY) with proper React
commit (focus -> select-all -> clear -> type -> input/change/blur per segment),
then advance to Review and click Submit."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser
from job_applier.bu_compat import make_bu_session

PFX = "selfIdentifiedDisabilityData--dateSignedOn-"
SEGS = [("dateSectionMonth-input", "08"),
        ("dateSectionDay-input", "20"),
        ("dateSectionYear-input", "2026")]

async def fill_seg(raw, sel, val):
    # focus, select-all, clear, type via CDP, commit events
    await raw.evaluate(f"(() => {{ const el=document.querySelector('{sel}'); el.scrollIntoView({{block:'center'}}); el.focus(); return true; }})()")
    await asyncio.sleep(0.15)
    # select all + clear
    await raw.evaluate(f"(() => {{ const el=document.querySelector('{sel}'); el.select(); const d=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value'); d.set.call(el,''); el.dispatchEvent(new Event('input',{{bubbles:true}})); return true; }})()")
    await asyncio.sleep(0.12)
    await cdp.type_text(val)
    await asyncio.sleep(0.15)
    await raw.evaluate(f"(() => {{ const el=document.querySelector('{sel}'); el.dispatchEvent(new Event('change',{{bubbles:true}})); el.dispatchEvent(new Event('blur',{{bubbles:true}})); el.dispatchEvent(new Event('focusout',{{bubbles:true}})); return el.value; }})()")
    await asyncio.sleep(0.2)

async def main():
    global cdp
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    for sel, val in SEGS:
        await fill_seg(page, f"#{PFX}{sel}", val)
    await asyncio.sleep(0.5)

    vals = {}
    for sel, _ in SEGS:
        e = await page.evaluate(f"document.querySelector('#{PFX}{sel}').value")
        vals[sel] = e
    print("DATE VALUES:", vals)

    # advance
    await page.evaluate('(() => { const b=[...document.querySelectorAll("button")].find(x=>/save and continue/i.test(x.textContent||"")); if(b)b.click(); })()')
    await asyncio.sleep(6)
    s = await page.evaluate('''
    (() => {
      const cur=[...document.querySelectorAll("*")].filter(el=>el.children.length===0 && /current step/i.test(el.textContent||"")).map(e=>e.textContent.trim());
      const h=[...document.querySelectorAll("h1,h2,h3")].map(x=>x.textContent.trim());
      const errs=[...document.querySelectorAll("[role=alert],[class*=error],[class*=Error]")].map(e=>(e.textContent||"").trim()).filter(t=>t&&t.length<150);
      return JSON.stringify({cur, h:h.slice(0,4), errs:[...new Set(errs)].slice(0,4)});
    })()
    ''')
    print("NEXT:", s)
    await cdp.close()

asyncio.run(main())
