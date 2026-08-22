"""Ethos: classify each question_* field: text vs select vs file, with class evidence."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    await asyncio.sleep(1)
    r = await page.evaluate(r"""
      (function(){
        var out=[];
        var labs=Array.prototype.slice.call(document.querySelectorAll('label[id^="question_"]'));
        for (var i=0;i<labs.length;i++){
          var lab=labs[i];
          var num=lab.id.replace(/-label$/,'');
          var c=document.getElementById(num);
          if(!c){ out.push({id:num, lab:(lab.textContent||'').trim().slice(0,55), status:'NO_CTRL'}); continue; }
          out.push({
            id:num,
            lab:(lab.textContent||'').trim().slice(0,55),
            tag:c.tagName, type:c.type,
            cls:(c.className||'').toString().slice(0,60),
            haspop:c.getAttribute('aria-haspopup'),
            req:c.required
          });
        }
        return out;
      })()
    """)
    for x in r:
        print(f"{x['id']:22s} {x['tag']:8s} {str(x['type']):10s} pop={str(x['haspop']):5s} req={str(x['req']):5s} {x['lab']}")
        print(f"{'':22s}   cls={x['cls']}")
    await b._session.close()

asyncio.run(main())
