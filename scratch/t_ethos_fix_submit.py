"""ETHOS fix + submit. Fix preferred_name, gov-official follow-ups (N/A),
re-confirm resume, then submit + verify."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    await asyncio.sleep(2)

    async def fill_text(fid, text):
        await page.evaluate(f'document.getElementById("{fid}").focus()')
        await asyncio.sleep(0.15)
        await page.evaluate(f'document.getElementById("{fid}").value=""')
        await asyncio.sleep(0.05)
        await b.type_text(text)
        await b.press_key("Tab", 9)
        await asyncio.sleep(0.3)
        return await page.evaluate('document.getElementById("' + fid + '").value')

    async def live_errors():
        return await page.evaluate(r"""
          (function(){
            var seen={};var out=[];
            Array.prototype.slice.call(document.querySelectorAll('[class*=error],[class*=invalid],.form__error,.text-danger')).forEach(function(e){
              var t=(e.innerText||'').trim();
              if(t && t.length<120 && !seen[t]){seen[t]=1;out.push(t);}
            });
            return out.slice(0,12);
          })()""")

    async def gov_state():
        return await page.evaluate(r"""
          (function(){
            function t(id){var e=document.getElementById(id);if(!e)return null;
              return {id:id, val:(e.value||''), visible:e.offsetParent!==null};}
            return {sel:(function(){var e=document.getElementById('question_36662473002');
                    if(!e)return null;var c=e.closest('.select__control');
                    if(c){var s=c.querySelector('.select__single-value');return s?(s.textContent||'').trim():null;}
                    return e.value||'';})(),
              f1:t('question_36662474002'), f2:t('question_36662475002')};
          })()""")

    # --- FIX 1: preferred_name ---
    v = await fill_text("preferred_name", "Rejo")
    print("preferred_name =", repr(v))

    # --- FIX 2: gov-official ---
    gs = await gov_state()
    print("gov state BEFORE:", json.dumps(gs))
    # re-commit the select to No to retrigger conditional logic
    await page.evaluate('document.getElementById("question_36662473002").focus()')
    await asyncio.sleep(0.2)
    await b.press_key("ArrowDown", 40)
    await asyncio.sleep(1.2)
    await b.type_text("No")
    await asyncio.sleep(1.3)
    await b.press_key("Enter", 13)
    await asyncio.sleep(1.0)
    gs = await gov_state()
    print("gov state AFTER re-commit:", json.dumps(gs))
    # if follow-ups still visible, fill N/A
    for fid in ["question_36662474002", "question_36662475002"]:
        st = gs.get("f1" if fid.endswith("74002") else "f2")
        if st and st.get("visible"):
            v = await fill_text(fid, "N/A")
            print(f"  {fid} -> {v!r}")
    gs = await gov_state()
    print("gov state FINAL:", json.dumps(gs))

    # --- FIX 3: resume verify ---
    resume = await page.evaluate(r"""
      (function(){
        var body=document.body.innerText||'';var idx=body.indexOf('Rejo_Z_Mathew');
        var fi=document.querySelectorAll('input[type=file]').length;
        return {chip: idx>=0, fileInputs: fi, ctx: idx>=0? body.slice(Math.max(0,idx-30),idx+30):null};
      })()""")
    print("resume:", json.dumps(resume))

    # --- live errors now ---
    errs = await live_errors()
    print("LIVE ERRORS NOW:", errs if errs else "NONE")

    # --- SUBMIT ---
    print("SUBMITTING...")
    await page.evaluate(r"""
      (function(){
        var b=Array.prototype.slice.call(document.querySelectorAll('button, input[type=submit]'))
             .find(function(x){return /submit application/i.test((x.textContent||x.value||'').trim());});
        if(b) b.click(); return !!b;
      })()""")
    confirmed=False; final={}
    for _ in range(9):
        await asyncio.sleep(2.5)
        try:
            v=await page.evaluate(r"""
              (function(){
                var body=(document.body?document.body.innerText:'');var title=document.title||'';var url=location.href||'';
                var conf=/thank you for applying|application has been received|we'?ve received your|/confirmation\?|confirmation.*for=/i.test(body+' '+title+' '+url);
                var errs=Array.prototype.slice.call(document.querySelectorAll('[class*=error],.form__error,.text-danger,[class*=invalid]')).map(function(e){return (e.innerText||'').trim();}).filter(Boolean).slice(0,10);
                return {conf:conf,title:title.slice(0,120),url:url.slice(0,180),errs:errs};
              })()""")
            final=v
            if v.get("conf"): confirmed=True; break
            if v.get("errs"): break
        except Exception: break
    print("CONFIRMED:", confirmed)
    print("FINAL:", json.dumps(final))
    await b._session.close()

asyncio.run(main())
