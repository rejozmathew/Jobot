"""Keyboard-driven combobox selection with active-option detection.
focus -> Enter (open) -> ArrowDown loop, reading the active/highlighted option,
until it matches target -> Enter to commit. Then verify the button text."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

VK = {"Enter":13," ":32,"ArrowDown":40,"ArrowUp":38,"Escape":27}

async def key(page, k):
    sess = page._session
    text = {"Enter":"\r"," ":" "}.get(k)
    await sess.call("Input.dispatchKeyEvent", {"type":"keyDown","key":k,"code":k,"text":text,"windowsVirtualKeyCode":VK[k]})
    await asyncio.sleep(0.12)
    await sess.call("Input.dispatchKeyEvent", {"type":"keyUp","key":k,"code":k,"windowsVirtualKeyCode":VK[k]})

def norm(s): return (s or "").lower().replace("\xa0"," ").strip()

async def active_option_text(page):
    t = json.loads(await page.evaluate("""
    (() => {
      const btn = document.activeElement || document.querySelector('#address--countryRegion');
      // aria-activedescendant on the focused element
      const ad = btn && btn.getAttribute('aria-activedescendant');
      if (ad) {
        const e = document.getElementById(ad);
        if (e) return JSON.stringify({t:(e.textContent||'').trim(), via:'activedesc'});
      }
      // option with aria-selected or .active / highlighted
      for (const e of document.querySelectorAll("[aria-selected='true'], [class*='active'], [class*='highlight'], [class*='selected']")) {
        const t=(e.textContent||'').trim();
        if (t && t.length<60) return JSON.stringify({t, via:'class'});
      }
      // first option in an open listbox
      const lb = document.querySelector("[role='listbox']");
      if (lb) { const o = lb.querySelector('[role=option], li'); if (o) return JSON.stringify({t:(o.textContent||'').trim(), via:'first'}); }
      return JSON.stringify({t:null});
    })()
    """))
    return t.get("t"), t.get("via")

async def open_and_select(page, sel, targets, max_down=80):
    # focus
    ok = json.loads(await page.evaluate("""
    (() => { const el=document.querySelector('%s'); el.scrollIntoView({block:'center'}); el.focus(); return JSON.stringify(document.activeElement===el); })()
    """ % sel))
    if not ok: return False, "focus-failed"
    await asyncio.sleep(0.4)
    await key(page, "Enter"); await asyncio.sleep(0.9)
    await key(page, " "); await asyncio.sleep(0.6)  # some combos open on space
    tl = [norm(t) for t in targets]
    # read current active
    seen = set()
    for i in range(max_down):
        cur, via = await active_option_text(page)
        if cur and norm(cur) in tl:
            await key(page, "Enter"); await asyncio.sleep(0.9)
            return True, f"selected:{cur} after {i} downs (via {via})"
        if cur in seen and i>2:
            break  # looped back -> not in list
        seen.add(cur)
        await key(page, "ArrowDown"); await asyncio.sleep(0.28)
    # report what we saw
    return False, f"no-match; active sequence sampled"

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    ok1, n1 = await open_and_select(page, "#address--countryRegion", ["Illinois","IL","Illinois (IL)","Illinois, United States"])
    print("Region:", ok1, n1[:120])

    ok2, n2 = await open_and_select(page, "#source--source", ["LinkedIn","Linkedin","Linked In","LinkedIn (from a recruiter)"])
    print("Source:", ok2, n2[:120])

    v = json.loads(await page.evaluate("""
    (() => { const g=id=>{const e=document.querySelector('#'+id);return e?(e.textContent||'').trim().slice(0,50):null;};
    return JSON.stringify({region:g('address--countryRegion'), source:g('source--source'), first:g('name--legalName--firstName'), phone:g('phoneNumber--phoneNumber')}); })()
    """))
    print("VERIFIED:", v)
    await cdp.close()

asyncio.run(main())
