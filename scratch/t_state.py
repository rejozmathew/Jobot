"""Final pre-fill dump: id, required, current value for every field."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    data = await page.evaluate(r"""
      (function(){
        var all = document.querySelectorAll('input,select,textarea');
        var out = [];
        for (var i=0;i<all.length;i++){
          var el=all[i];
          var label='';
          if(el.id){var lb=document.querySelector('label[for="'+el.id+'"]');if(lb)label=lb.textContent.trim();}
          if(!label)label=el.getAttribute('aria-label')||'';
          var val='';
          if(el.classList && el.classList.contains('select__input')){
            var c=el.closest('.select__control')||el;var s=c.querySelector('.select__single-value');
            val=s?s.textContent.trim():'';
          } else if(el.type==='checkbox'){ val=el.checked?'checked':''; }
          else if(el.type==='file'){ val=el.files.length?('FILE: '+el.files[0].name):''; }
          else { val=el.value||''; }
          out.push({id:el.id||'(none)', req:el.required, type:el.type||el.tagName,
                    label:label.slice(0,60), val:(val||'').slice(0,40)});
        }
        return out;
      })()
    """)
    print(f"{'ID':26} {'REQ':4} {'TYPE':10} {'VALUE':22} LABEL")
    print("-"*110)
    for d in data:
        print(f"{d['id']:26} {str(d['req'])[0]:4} {d['type']:10} {d['val']:22} {d['label']}")
    await b._session.close()

asyncio.run(main())
