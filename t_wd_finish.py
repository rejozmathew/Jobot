"""Resume the Fannie Mae draft, advance through all remaining steps to Review,
click Submit, handle a confirm dialog if any, then verify via Candidate Home."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser
from job_applier.bu_compat import make_bu_session

APPLY_URL = ("https://fanniemae.wd1.myworkdayjobs.com/FannieMaeCareers/job/"
             "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677/apply")

JS_STATE = '''
(() => {
  const cur = Array.from(document.querySelectorAll("*")).filter(el=>el.children.length===0 && /current step/i.test(el.textContent||"")).map(e=>e.textContent.trim());
  const btns = Array.from(document.querySelectorAll("button")).map(b=>(b.textContent||"").trim()).filter(t=>t);
  const errs = Array.from(document.querySelectorAll("[role=alert],[class*=error],[class*=Error]")).map(e=>(e.textContent||"").trim()).filter(t=>t&&t.length<150);
  const saved = (()=>{const b=Array.from(document.querySelectorAll("button")).find(x=>/save and continue/i.test(x.textContent||"")); return b?{disabled:b.disabled}:null;})();
  return JSON.stringify({cur, btns, errs:[...new Set(errs)].slice(0,4), saved});
})()
'''

JS_STEP5_FIX = '''
(() => {
  const cks = Array.from(document.querySelectorAll("input[type=checkbox]"));
  const labelOf = (c) => { const l=document.querySelector('label[for="'+c.id+'"]'); return l?(l.textContent||""):""; };
  const no = cks.find(c=>/No, I do not have a disability/i.test(labelOf(c)));
  if(no && !no.checked) no.click();
  return JSON.stringify(cks.map(c=>({t:labelOf(c).slice(0,30),c:c.checked})));
})()
'''

async def trusted_click(page, text):
    btns = await page.get_elements_by_css_selector("button")
    for b in btns:
        txt = await b.evaluate("(el)=>el.textContent")
        if txt and text in txt.lower():
            await b.evaluate('(el)=>{el.scrollIntoView({block:"center"});return true;}')
            await asyncio.sleep(0.3)
            await b.click()
            return True
    return False

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    bu = make_bu_session(cdp)
    page = await bu.get_current_page()

    url = await page.evaluate("window.location.href")
    if "userHome" in url or "/apply" not in url:
        await page.goto(APPLY_URL)
        await asyncio.sleep(8)
    url = await page.evaluate("window.location.href")
    print("ON:", url)

    for i in range(30):
        info = json.loads(await page.evaluate(JS_STATE))
        cur = " ".join(info["cur"])
        print(f"[{i}] {cur} | saved={info['saved']} | errs={info['errs']}")
        if not info["cur"]:
            print("NO_STEP_INDICATOR — page may have changed; body:")
            print((await page.evaluate("document.body.innerText.slice(0,800)")))
            break
        if "step 6 of 6" in cur:
            ok = await trusted_click(page, "submit")
            print("SUBMIT_CLICKED:", ok)
            await asyncio.sleep(8)
            # handle confirm dialog if present
            body = await page.evaluate("document.body.innerText.slice(0,900)")
            print("AFTER_SUBMIT_BODY:", body)
            if any(k in body.lower() for k in ["are you sure", "confirm", "this action cannot be undone"]):
                if await trusted_click(page, "confirm") or await trusted_click(page, "yes"):
                    print("CONFIRM_CLICKED")
                    await asyncio.sleep(8)
                    print("FINAL_BODY:", await page.evaluate("document.body.innerText.slice(0,900)"))
            break
        ok = await trusted_click(page, "save and continue")
        if not ok:
            print("BTN disabled/missing — applying step-5 fix (disability 'No')")
            await page.evaluate(JS_STEP5_FIX)
            await asyncio.sleep(1)
            ok = await trusted_click(page, "save and continue")
            if not ok:
                print("STUCK: no save-and-continue found")
                print((await page.evaluate("document.body.innerText.slice(0,800)")))
                break
        await asyncio.sleep(7)
        info2 = json.loads(await page.evaluate(JS_STATE))
        if info2["errs"] and any(("required" in e.lower()) or e.startswith("Error") for e in info2["errs"]):
            print("ERRORS REMAIN:", info2["errs"])
            print((await page.evaluate("document.body.innerText.slice(0,800)")))
            break

    # verify via Candidate Home
    await asyncio.sleep(2)
    ch = await page.evaluate('''
    (() => { const e=Array.from(document.querySelectorAll("a,button")).find(x=>(x.textContent||"").trim()==="Candidate Home"); if(e)e.click(); return !!e; })()
    ''')
    await asyncio.sleep(7)
    body = await page.evaluate("document.body.innerText.slice(0,1500)")
    print("CANDIDATE_HOME_VERIFY:")
    print(body)
    await cdp.close()

asyncio.run(main())
