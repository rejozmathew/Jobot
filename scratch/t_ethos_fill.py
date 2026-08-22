"""ETHOS LIFE — fill + submit (v2). Remote-search selects: type filter -> verify
first option contains query -> Enter -> verify committed. Standard text: focus/type.
Answers from profile.json. Idempotent (clears fields first).
"""
import asyncio, sys, json, os
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

RESUME   = r"C:\Users\rejoz\OneDrive\Documents\2026 Resume\AI balanced\Rejo_Z_Mathew_Resume.pdf"
FIRST    = "Rejo"; LAST = "Mathew"; EMAIL = "rejozacharia@gmail.com"; PHONE = "707-456-7356"
LOCATION = "Wheeling"            # filter; Greenhouse suggests "Wheeling, IL, United States"
COUNTRY  = "United States"       # filter; dialer suggests "United States +1"
LINKEDIN = "https://www.linkedin.com/in/rejo-z-mathew"

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    await asyncio.sleep(2)

    async def committed(fid):
        v = await page.evaluate(r'''
          (function(){
            var e=document.getElementById("%s"); if(!e) return null;
            var c=e.closest('.select__control');
            if(c){var s=c.querySelector('.select__single-value');return s?(s.textContent||'').trim():null;}
            return e.value||'';
          })()''' % fid)
        return v

    async def fill_text(fid, text):
        await page.evaluate(f'document.getElementById("{fid}").focus()')
        await asyncio.sleep(0.15)
        await page.evaluate(f'document.getElementById("{fid}").value=""')
        await asyncio.sleep(0.05)
        await b.type_text(text)
        await b.press_key("Tab", 9)
        await asyncio.sleep(0.3)

    async def commit_select(fid, query):
        """focus -> open -> type filter -> ensure first option matches -> Enter -> verify."""
        if not await page.evaluate(f'document.getElementById("{fid}") !== null'):
            return None
        await page.evaluate(f'document.getElementById("{fid}").focus()')
        await asyncio.sleep(0.2)
        await b.press_key("ArrowDown", 40)
        await asyncio.sleep(1.3)
        await b.type_text(query)
        await asyncio.sleep(1.4)
        # read first option; if it doesn't contain the query, still try Enter (typed-text commit)
        first = await page.evaluate(r'''
          (function(){
            var m=document.querySelector('[role=listbox]');
            if(!m) return null;
            var o=m.querySelector('[role=option]');
            return o?(o.textContent||'').trim():null;
          })()''')
        await b.press_key("Enter", 13)
        await asyncio.sleep(0.9)
        v = await committed(fid)
        if v:
            return v
        # second attempt: re-open, type again, Enter
        await b.press_key("ArrowDown", 40)
        await asyncio.sleep(1.2)
        await b.type_text(query)
        await asyncio.sleep(1.4)
        await b.press_key("Enter", 13)
        await asyncio.sleep(0.9)
        return await committed(fid)

    # 1. standard text fields
    print("[1] text fields")
    for fid,val in [("first_name",FIRST),("last_name",LAST),("email",EMAIL),("phone",PHONE)]:
        await fill_text(fid,val)
        cur = await page.evaluate('document.getElementById("' + fid + '").value')
        print(f"   {fid:18s}={cur}")

    # 2. remote-search selects
    print("[2] selects (remote-search)")
    plan = [
        ("country",                 COUNTRY, "country-dialer"),
        ("candidate-location",      LOCATION,"location"),
        ("question_36662472002",    "Yes",   "sponsorship"),
        ("question_36662473002",    "No",    "gov-official"),
        ("question_36663096002",    "Yes",   "10y-analytic"),
        ("question_36663097002",    "Yes",   "AI"),
        ("question_36663098002",    "Yes",   "SQL"),
    ]
    for fid,ans,name in plan:
        v = await commit_select(fid, ans)
        print(f"   {name:15s} -> {v!r}")
        await b.press_key("Escape",27); await asyncio.sleep(0.3)

    # 3. LinkedIn
    print("[3] linkedin")
    await fill_text("question_36662476002", LINKEDIN)
    print("   linkedin =", (await page.evaluate('document.getElementById("question_36662476002").value'))[:60])

    # 4. resume
    print("[4] resume")
    try:
        els = await page.query_selector_all("input[type=file]")
        if els:
            await els[0].set_input_files(RESUME); await asyncio.sleep(2.5)
            print("   uploaded:", RESUME.split("\\")[-1])
        else: print("   NO FILE INPUT")
    except Exception as e: print("   ERR", str(e)[:120])

    # 5. pre-submit state
    print("[5] pre-submit state")
    st = {}
    for fid in ["first_name","last_name","email","phone","country","candidate-location",
                "question_36662472002","question_36662473002","question_36663096002",
                "question_36663097002","question_36663098002","question_36662476002"]:
        st[fid] = await committed(fid)
    st["resume"] = await page.evaluate('(document.querySelector("input[type=file]")||{}).value||null')
    for k,v in st.items(): print(f"   {k:24s} = {v!r}")
    empty=[k for k,v in st.items() if not v]
    print("EMPTY:", empty if empty else "NONE ✓")

    # 6. SUBMIT
    print("[6] SUBMIT")
    await page.evaluate(r'''
      (function(){
        var b=Array.prototype.slice.call(document.querySelectorAll('button, input[type=submit]'))
             .find(function(x){return /submit application/i.test((x.textContent||x.value||'').trim());});
        if(b) b.click(); return !!b;
      })()''')
    confirmed=False; final={}
    for _ in range(8):
        await asyncio.sleep(2.5)
        try:
            v=await page.evaluate(r'''
              (function(){
                var body=(document.body?document.body.innerText:'');var title=document.title||'';var url=location.href||'';
                var conf=/thank you for applying|application has been received|application.*submitted|we'?ve received|confirmation|/confirmation\?/i.test(body+' '+title+' '+url);
                var errs=Array.prototype.slice.call(document.querySelectorAll('[class*=error],.form__error,.text-danger')).map(function(e){return (e.innerText||'').trim();}).filter(Boolean).slice(0,8);
                return {conf:conf,title:title.slice(0,110),url:url.slice(0,160),errs:errs};
              })()''')
            final=v
            if v.get("conf"): confirmed=True; break
            if v.get("errs"): break
        except Exception: break
    print("CONFIRMED:", confirmed)
    print("FINAL:", json.dumps(final))
    await b._session.close()

asyncio.run(main())
