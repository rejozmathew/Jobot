"""READ-ONLY probe: list all fields + dump every select's option list.
No filling, no submit. Safe to run while you watch.
NOTE: cdp evaluate only forwards arg when it's a dict/list.
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def click_xy(browser, x, y):
    s = browser._session
    for ty in ("mouseDown", "mouseUp"):
        await s.call("Input.dispatchMouseEvent",
            {"type": ty, "x": int(x), "y": int(y), "button": "left",
             "clickCount": 1, "pointerType": "mouse"})
    await asyncio.sleep(0.15)

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222", page_url_substring="brex.com")
    page = await b.get_current_page()
    print("URL:", (await page.evaluate("location.href"))[:90])

    JS_ENUM = r"""
    () => {
      const out = []; const seen = new Set();
      const els = Array.from(document.querySelectorAll('input[id], select[id]'));
      for (const el of els) {
        const id = el.id; if (!id || seen.has(id)) continue; seen.add(id);
        let label = el.getAttribute('aria-label') || '';
        if (!label) { const lab = document.querySelector('label[for="'+id+'"]'); if (lab) label = lab.textContent.trim(); }
        let kind='text';
        if (el.type==='checkbox') kind='checkbox';
        else if (el.classList && el.classList.contains('select__input')) kind='select';
        else if (el.getAttribute('aria-haspopup')) kind='select';
        else if (el.type==='file') kind='file';
        out.push({id, kind, label:(label||'').slice(0,60), req: el.required===true});
      }
      return out;
    }
    """
    fields = await page.evaluate(JS_ENUM)
    print("\n=== ALL FIELDS ===")
    for f in fields:
        print(f"  [{f['kind']:8s}] req={str(f['req'])[0]:1s} {f['id']:24s} | {f['label']}")

    print("\n=== SELECT OPTIONS ===")
    for f in fields:
        if f["kind"] != "select": continue
        r = await page.evaluate(r"""
          (p) => { const el=document.getElementById(p.id); if(!el) return {err:'no el'};
            el.scrollIntoView({block:'center'});
            const c = el.closest('.select__control') || el;
            const b2 = c.getBoundingClientRect();
            return {x:b2.left+b2.width/2, y:b2.top+b2.height/2, vis:b2.top>=0&&b2.bottom<=innerHeight}; }
        """, arg={"id": f["id"]})
        if not r or not r.get("vis"):
            print(f"  {f['id']}  ({f['label']}): NOT IN VIEWPORT or err={r}")
            continue
        await click_xy(b, r["x"], r["y"])
        await asyncio.sleep(1.1)
        opts = await page.evaluate(r"""
          () => Array.from(document.querySelectorAll('[role=listbox] li, .select__option'))
               .map(x=>x.textContent.trim()).slice(0,15)
        """)
        print(f"  {f['id']}  ({f['label']})")
        print(f"      -> {opts}")
        await b.press_key("Escape", 27)
        await asyncio.sleep(0.4)
    await b._session.close()

asyncio.run(main())
