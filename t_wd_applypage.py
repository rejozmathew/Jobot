"""Navigate directly to the Workday /apply URL (where the Apply link points) and inspect the real application page."""
import asyncio, json
import sys; sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

APPLY_URL = ("https://fanniemae.wd1.myworkdayjobs.com/FannieMaeCareers/job/"
             "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677/apply")

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    await page.goto(APPLY_URL)
    await asyncio.sleep(6)  # let Workday render the application
    print("URL:", await page.evaluate("location.href"))
    print("TITLE:", await page.evaluate("document.title"))
    data = await page.evaluate(r"""(() => {
      const out={inputs:[],buttons:[],labels:[],body_head:'',iframes:[]};
      out.inputs=[...document.querySelectorAll('input,textarea,select')].slice(0,40).map(e=>({
        tag:e.tagName, type:e.getAttribute('type')||'', name:e.getAttribute('name')||'',
        aid:e.getAttribute('data-automation-id')||'', ph:e.getAttribute('placeholder')||'',
        vis:e.getBoundingClientRect().width>0
      }));
      out.buttons=[...document.querySelectorAll('button,[role=button],a[data-automation-id]')].slice(0,25).map(b=>({
        text:(b.innerText||b.getAttribute('aria-label')||'').trim().slice(0,40),
        aid:b.getAttribute('data-automation-id')||b.getAttribute('name')||''
      }));
      out.labels=[...document.querySelectorAll('label')].slice(0,30).map(l=>(l.innerText||'').trim().slice(0,50));
      out.iframes=[...document.querySelectorAll('iframe')].map(f=>f.src);
      out.body_head=(document.body.innerText||'').replace(/\s+/g,' ').slice(0,700);
      return out;
    })()""", None, None)
    print(json.dumps(data, indent=1))
    await cdp.close()

asyncio.run(main())
