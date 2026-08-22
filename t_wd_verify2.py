"""Robust legal-name commit: toggle verify button, clear+type name, blur, advance."""
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
    raw = await cdp.get_current_page()

    # 1) Try clicking the "I verify" button to set it (in case it's the real gate)
    vb = await page.evaluate("""
    (() => { const b=[...document.querySelectorAll("button")].find(x=>/I verify/i.test(x.textContent||"")); if(b){b.click(); return b.textContent.trim().slice(0,20);} return "gone"; })()
    """)
    print("VERIFY BTN AFTER CLICK:", vb)
    await asyncio.sleep(0.6)

    # 2) Clear textarea via React setter, type via CDP, then blur to commit
    els = await page.get_elements_by_css_selector(f"#{TID}")
    el = els[0]
    await el.evaluate("(el)=>{ el.scrollIntoView({block:'center'}); el.focus(); return true; }")
    await asyncio.sleep(0.2)
    # clear
    await el.evaluate("""
    (el)=>{ var d=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value"); d.set.call(el,""); el.dispatchEvent(new Event("input",{bubbles:true})); return true; }
    """)
    await asyncio.sleep(0.15)
    # type via real keyboard
    await cdp.type_text(LEGAL)
    await asyncio.sleep(0.15)
    # commit: blur + change + input
    await el.evaluate("""
    (el)=>{ el.dispatchEvent(new Event("input",{bubbles:true})); el.dispatchEvent(new Event("change",{bubbles:true})); el.blur(); el.dispatchEvent(new Event("blur",{bubbles:true})); el.dispatchEvent(new Event("focusout",{bubbles:true})); return el.value; }
    """)
    await asyncio.sleep(0.8)
    val = await el.evaluate("(el)=>el.value")
    print("TA VALUE:", repr(val))
    print("TA invalid:", await el.evaluate("(el)=>el.getAttribute('aria-invalid')"))

    # 3) Advance
    r = await page.evaluate("""
    (() => { const b=[...document.querySelectorAll("button")].find(x=>/save and continue/i.test(x.textContent||"")); if(b){b.click();return true;} return false; })()
    """)
    print("ADVANCE:", r)
    await asyncio.sleep(5.5)
    nxt = await page.evaluate("""
    (() => {
      const cur=document.querySelector("[class*=current]");
      const h=[...document.querySelectorAll("h1,h2,h3")].map(x=>x.textContent.trim());
      const body=document.body.innerText.slice(0,260);
      const errs=[...document.querySelectorAll("[role=alert],[class*=error],[class*=Error]")].map(e=>(e.textContent||"").trim()).filter(t=>t&&t.length<150);
      return JSON.stringify({cur:cur?cur.textContent.trim().slice(0,25):null, h:h.slice(0,4), errs:[...new Set(errs)].slice(0,3), body});
    })()
    """)
    print("NEXT:", nxt)
    await cdp.close()

asyncio.run(main())
