"""Inspect the 3 problem areas on Ethos: preferred_name, resume upload, gov follow-ups."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    await asyncio.sleep(2)

    # 1. preferred_name
    pref = await page.evaluate(r"""
      (function(){
        var e=document.getElementById('preferred_name');
        if(!e) return {status:'MISSING'};
        return {val:(e.value||''), tag:e.tagName, type:e.type, req:e.required,
                cls:(e.className||'').toString().slice(0,40)};
      })()""")
    print("preferred_name:", pref)

    # 2. all file inputs + any uploaded-file chips
    files = await page.evaluate(r"""
      (function(){
        var fs=Array.prototype.slice.call(document.querySelectorAll('input[type=file]'));
        return fs.map(function(f){
          return {id:f.id||'', name:f.name||'', val:(f.value||''), accept:f.accept||'',
                  multiple:f.multiple, cls:(f.className||'').toString().slice(0,40)};
        });
      })()""")
    print("file inputs:", json.dumps(files))
    chips = await page.evaluate(r"""
      (function(){
        // Greenhouse shows uploaded files as text somewhere
        var body=document.body.innerText||'';
        var idx=body.indexOf('Rejo_Z_Mathew');
        return {foundResume:idx>=0, ctx: idx>=0? body.slice(Math.max(0,idx-40), idx+40):null};
      })()""")
    print("resume chip:", chips)

    # 3. gov-official follow-ups (text fields) + the select state
    gov = await page.evaluate(r"""
      (function(){
        function t(id){var e=document.getElementById(id);if(!e)return {id:id,status:'MISSING'};
          return {id:id, val:(e.value||''), type:e.type, req:e.required,
                  cls:(e.className||'').toString().slice(0,35),
                  disabled:e.disabled, hidden:e.offsetParent===null};}
        return [t('question_36662473002'),t('question_36662474002'),t('question_36662475002')];
      })()""")
    for g in gov: print("gov:", g)

    # 4. current committed values snapshot
    def committed(fid):
        pass
    await b._session.close()

asyncio.run(main())
