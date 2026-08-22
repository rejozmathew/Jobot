"""Dump the Figma posting form's real field structure."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    if "figma/jobs/6130865004" not in (page.url or ""):
        await page.goto("https://boards.greenhouse.io/figma/jobs/6130865004")
        await asyncio.sleep(6)
    data = await page.evaluate(r"""
      (function(){
        var out = [];
        var els = Array.prototype.slice.call(document.querySelectorAll('input,select,textarea'));
        els.forEach(function(el){
          var name = el.name || el.id || '';
          var type = el.type || el.tagName.toLowerCase();
          var req = el.required || (el.getAttribute('aria-required')==='true');
          var cls = (el.className||'').toString().slice(0,40);
          // find label
          var lbl = '';
          if(el.id){ var l=document.querySelector('label[for="'+el.id+'"]'); if(l) lbl=l.textContent.trim().slice(0,50); }
          if(!lbl && el.name){ var l2=document.querySelector('label[for="'+el.name+'"]'); if(l2) lbl=l2.textContent.trim().slice(0,50); }
          out.push({name:name, type:type, req:req, cls:cls, lbl:lbl, val:(el.value||'').slice(0,20)});
        });
        return out;
      })()""")
    print("=== Figma form fields:", len(data), "===")
    for d in data:
        print(f"  name={d['name']!r:34} type={d['type']:10} req={d['req']!s:5} val={d['val']!r}")
    # any select__* (react-select) markers?
    n_rs = await page.evaluate("(function(){return document.querySelectorAll('.select__single-value,.select__control,[class*=select__]').length;})()")
    print("react-select markers:", n_rs)
    # is there an apply button vs submit?
    btns = await page.evaluate(r"""
      (function(){
        var out=[];
        Array.prototype.slice.call(document.querySelectorAll('button,[type=submit]')).forEach(function(e){
          out.push((e.tagName+': '+(e.textContent||'').trim().slice(0,30))+' '+(e.type||''));
        });
        return out.slice(0,15);
      })()""")
    print("buttons:", json.dumps(btns))
    await b._session.close()

asyncio.run(main())
