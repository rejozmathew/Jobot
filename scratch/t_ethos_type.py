"""Check the real type of the country field + other standard fields on Ethos."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    r = await page.evaluate(r"""
      (function(){
        function info(id){
          var e=document.getElementById(id); if(!e) return {id:id, status:'MISSING'};
          var c=e.closest('.select__control');
          return {id:id, tag:e.tagName, type:e.type, cls:(e.className||'').toString().slice(0,55), isSelect:!!c, haspop:e.getAttribute('aria-haspopup'), val:(e.value||'').slice(0,25)};
        }
        return [info('country'), info('first_name'), info('phone'), info('candidate-location'), info('question_36663097002')];
      })()
    """)
    for x in r:
        print(x)
    await b._session.close()

asyncio.run(main())
