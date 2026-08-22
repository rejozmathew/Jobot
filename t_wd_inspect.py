"""Inspect the real Apply control + what a[href*='apply'] matches."""
import asyncio, json
import sys; sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    print("URL:", await page.evaluate("location.href"))
    print("TITLE:", await page.evaluate("document.title"))
    data = await page.evaluate(r"""(() => {
      const out = {a_apply:[], buttons:[], all_apply_els:[], body_head:''};
      out.a_apply = [...document.querySelectorAll("a[href*='apply']")].map(a=>({
        text:(a.innerText||'').trim().slice(0,40), href:a.getAttribute('href'),
        rect:(r=>r?{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),vis:r.width>0&&r.height>0}:(0))(a.getBoundingClientRect())
      }));
      out.buttons = [...document.querySelectorAll("button,[role=button]")].map(b=>({
        text:(b.innerText||b.getAttribute('aria-label')||'').trim().slice(0,40),
        tag:b.tagName, aid:b.getAttribute('data-automation-id'),
        rect:(r=>r?{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),vis:r.width>0&&r.height>0}:null)(b.getBoundingClientRect())
      }));
      out.all_apply_els = [...document.querySelectorAll("*")].filter(e=>{
        const t=(e.innerText||'').trim(); return t==='Apply' && e.children.length===0;
      }).slice(0,8).map(e=>({tag:e.tagName, cls:(e.className||'').slice(0,50), aid:e.getAttribute('data-automation-id')}));
      out.body_head=(document.body.innerText||'').replace(/\s+/g,' ').slice(0,400);
      return out;
    })()""", None, None)
    print(json.dumps(data, indent=1))
    await cdp.close()

asyncio.run(main())
