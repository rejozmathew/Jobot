"""Test the Workday entry panel: click 'Apply Manually', observe what appears."""
import asyncio, json, sys
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

POST = ("https://fanniemae.wd1.myworkdayjobs.com/FannieMaeCareers/job/"
        "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677")
APPLY = POST + "/apply"
ART = "artifacts"

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    # Step 1: entry panel
    await page.goto(APPLY)
    await asyncio.sleep(6)
    await cdp.screenshot(f"{ART}/wd_1_entry.png")
    entry = await page.evaluate("""
    () => ({
      url: location.href,
      buttons: Array.from(document.querySelectorAll('button,a,[role="button"]')).filter(el=>{
        const st=getComputedStyle(el); const r=el.getBoundingClientRect();
        return st.display!=='none'&&st.visibility!=='hidden'&&r.width>0&&r.height>0;
      }).map(el=>({t:(el.textContent||'').trim().slice(0,50), id:el.getAttribute('id')||'', da:el.getAttribute('data-automation-id')||''})),
    })
    """)
    print("ENTRY url:", entry["url"], flush=True)
    for b in entry["buttons"]:
        print("  btn:", json.dumps(b), flush=True)

    # Step 2: click Apply Manually via trusted mouse
    el = await page.evaluate("""
    () => {
      const a = document.querySelector(\"[data-automation-id='applyManually'], button[data-automation-id*='applyManually']\");
      if (!a) return null;
      a.scrollIntoView({block:'center'});
      const r = a.getBoundingClientRect();
      return {x: r.x + r.width/2, y: r.y + r.height/2};
    }
    """)
    print("\nApplyManually center:", el, flush=True)
    if el:
        x, y = el["x"], el["y"]
        await cdp._session.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        await cdp._session.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await cdp._session.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    await asyncio.sleep(7)
    await cdp.screenshot(f"{ART}/wd_2_aftermanual.png")
    after = await page.evaluate("""
    () => ({
      url: location.href,
      title: document.title,
      body_head: ((document.body||{}).innerText||'').slice(0,400),
      automation_ids: Array.from(document.querySelectorAll('[data-automation-id]')).slice(0,25).map(e=>e.getAttribute('data-automation-id')),
      fields: Array.from(document.querySelectorAll('input,select,textarea')).slice(0,15).map(e=>({t:e.tagName,type:e.getAttribute('type')||'',name:e.getAttribute('name')||'',id:e.getAttribute('id')||'',da:e.getAttribute('data-automation-id')||''})),
    })
    """)
    print("\nAFTER ApplyManually url:", after["url"], flush=True)
    print("title:", after["title"], flush=True)
    print("body:", after["body_head"], flush=True)
    print("automation_ids:", after["automation_ids"], flush=True)
    print("fields:", json.dumps(after["fields"], indent=1), flush=True)
    await cdp.close()

asyncio.run(main())
