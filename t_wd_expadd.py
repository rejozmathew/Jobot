"""Identify the 'Add' buttons by section, then open Work Experience add form."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS_ADDS = """
(() => {
  const adds = [...document.querySelectorAll('button, a[role=button], [class*=addButton]')].filter(b=>/add/i.test((b.textContent||'').trim()));
  return JSON.stringify(adds.map((b,i)=>{
    // find nearest section heading
    let sec = null;
    let n = b.closest('section, [class*=card], [class*=section], [class*=panel]');
    if (n) {
      const h = n.querySelector('h2,h3,h4,[class*=title],[class*=heading]');
      sec = h ? h.textContent.trim().slice(0,40) : null;
    }
    return {i, text:(b.textContent||'').trim().slice(0,20), sec, daid:b.getAttribute('data-automation-id')||''};
  }));
})()
"""

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    print("ADD BUTTONS:")
    adds = json.loads(await page.evaluate(JS_ADDS))
    for a in adds:
        print(f"  [{a['i']}] '{a['text']}' section={a['sec']!r} daid={a['daid']!r}")

    # Click the first Work Experience Add (index 0 typically)
    # Find the Add button within the Work Experience section specifically
    r = await page.evaluate("""
    (() => {
      // Find headings, then the Add button in the same container
      const headings = [...document.querySelectorAll('h2,h3,h4,[class*=title]')];
      for (const h of headings) {
        if (/work experience/i.test(h.textContent||'')) {
          let cont = h.closest('section, [class*=card], [class*=panel], [class*=section]') || h.parentElement;
          const add = cont && cont.querySelector('button, a[role=button]');
          const adds = cont ? [...cont.querySelectorAll('button, a[role=button]')] : [];
          const addBtn = adds.find(b=>/add/i.test(b.textContent||''));
          if (addBtn) { addBtn.click(); return JSON.stringify({clicked:'workexp-add', text:addBtn.textContent.trim()}); }
        }
      }
      return JSON.stringify({err:'no-workexp-add'});
    })()
    """)
    print("\nClick Work Experience Add:", r)
    await asyncio.sleep(2.0)

    # Read the new form fields
    fields = json.loads(await page.evaluate("""
    (() => {
      const f = [];
      document.querySelectorAll('input, textarea, select').forEach(el=>{
        if (el.type==='hidden'||el.type==='radio'||el.type==='checkbox') return;
        if (el.type==='file') return;
        let lab='';
        if (el.id){const l=document.querySelector('label[for="'+el.id+'"]'); if(l)lab=l.textContent.trim().slice(0,50);}
        lab = lab || el.getAttribute('aria-label')||'';
        f.push({id:el.id||'', type:el.type||'', label:lab});
      });
      return JSON.stringify(f);
    })()
    """))
    print("\nWORK EXPERIENCE FORM FIELDS:")
    for f in fields:
        print(f"  id={f['id']!r} type={f['type']!r} label={f['label']!r}")
    await cdp.close()

asyncio.run(main())
