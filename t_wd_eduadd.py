"""Add Education entry (MBA Kelley 2009) + verify fields."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def fill_field(page, sel, value):
    js = """
    (() => {
      const sel = %s, value = %s;
      const e = document.querySelector('#' + CSS.escape(sel));
      if (!e) return JSON.stringify({sel, err:'no-el'});
      e.focus();
      const proto = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      setter.call(e, value);
      e.dispatchEvent(new Event('input', {bubbles:true}));
      e.dispatchEvent(new Event('change', {bubbles:true}));
      e.dispatchEvent(new Event('blur', {bubbles:true}));
      return JSON.stringify({sel, ok: e.value === value});
    })()
    """ % (json.dumps(sel), json.dumps(value))
    r = await page.evaluate(js)
    return json.loads(r) if isinstance(r, str) else r

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    # Click Education Add
    r = json.loads(await page.evaluate("""
    (() => {
      const heads = [...document.querySelectorAll('h2,h3,h4,[class*=title]')];
      for (const h of heads) {
        if (/education/i.test(h.textContent||'')) {
          let cont = h.closest('section,[class*=card],[class*=panel],[class*=section]') || h.parentElement;
          const adds = cont ? [...cont.querySelectorAll('button,[role=button]')] : [];
          const b = adds.find(x=>/add/i.test(x.textContent||''));
          if (b) { b.click(); return JSON.stringify({clicked:'edu-add'}); }
        }
      }
      return JSON.stringify({err:'no-edu-add'});
    })()
    """))
    print("Edu Add:", r)
    await asyncio.sleep(1.5)

    # Read the education form fields
    fields = json.loads(await page.evaluate("""
    (() => {
      const f = [];
      document.querySelectorAll('input, textarea, select').forEach(el=>{
        if (el.type==='hidden'||el.type==='radio'||el.type==='checkbox'||el.type==='file') return;
        if (!el.id || !el.id.includes('education')) return;
        let lab='';
        const l=document.querySelector('label[for="'+el.id+'"]'); if(l)lab=l.textContent.trim().slice(0,50);
        f.push({id:el.id, type:el.type||'', label:lab});
      });
      return JSON.stringify(f);
    })()
    """))
    print("\nEDUCATION FIELDS:")
    for f in fields:
        print(f"  id={f['id']!r} type={f['type']!r} label={f['label']!r}")
    await cdp.close()

asyncio.run(main())
