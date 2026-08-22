"""Ethos step 2: inventory the form fields (id, label, kind, required, value)."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    await asyncio.sleep(4)
    r = await page.evaluate(r"""
      (function(){
        var out=[];
        var els=Array.prototype.slice.call(document.querySelectorAll('input, select, textarea'));
        for (var i=0;i<els.length;i++){
          var e=els[i];
          var lab='';
          var l=e.closest('label');
          if(!l){
            var labEl=document.querySelector('label[for="'+e.id+'"]');
            if(labEl) lab=labEl.textContent;
            else {
              var wrap=e.closest('.field, .question, .form-group, [class*=question], [class*=field]');
              if(wrap){ var h=wrap.querySelector('label, .question-label, [class*=label]'); if(h) lab=h.textContent; }
            }
          } else lab=l.textContent;
          out.push({
            id: e.id||'',
            name: e.name||'',
            type: e.type||e.tagName.toLowerCase(),
            req: e.required||false,
            val: (e.value||'').substring(0,40),
            lab: (lab||'').trim().substring(0,70)
          });
        }
        var btns=Array.prototype.slice.call(document.querySelectorAll('button, input[type=submit]'));
        var bt=btns.map(function(b){return (b.textContent||b.value||'').trim().substring(0,40);}).filter(function(t){return t;});
        return {n: out.length, fields: out, buttons: bt.slice(0,10),
                hasSelect: !!document.querySelector('.select__control'),
                body: (document.body.innerText||'').substring(0,200)};
      })()
    """)
    print("URL:", (await page.evaluate("location.href"))[:110])
    print("FIELDS:", r["n"], "hasSelectControl:", r["hasSelect"])
    print("BUTTONS:", r["buttons"])
    print("BODY:", r["body"].replace("\n"," | "))
    print()
    for f in r["fields"]:
        print(f"  [{f['type']:12s}] req={str(f['req']):5s} id={f['id'][:28]:28s} val={f['val'][:22]!r:24s} lab={f['lab'][:52]!r}")
    await b._session.close()

asyncio.run(main())
