"""Keyboard-driven combobox fill: focus button, open via Enter/Space, then
ArrowDown to the target + Enter. Also dumps the listbox DOM after opening."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def key(page, k, code=None):
    sess = page._session
    await sess.call("Input.dispatchKeyEvent", {"type":"keyDown", "key":k, "code":code or k, "text":({"Enter":"\\r"," ":" "}.get(k)) or None, "windowsVirtualKeyCode": {"Enter":13," ":32,"ArrowDown":40,"ArrowUp":38}.get(k,0)})
    await asyncio.sleep(0.15)
    await sess.call("Input.dispatchKeyEvent", {"type":"keyUp", "key":k, "code":code or k, "windowsVirtualKeyCode": {"Enter":13," ":32,"ArrowDown":40,"ArrowUp":38}.get(k,0)})

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    # Focus the Region button
    r = json.loads(await page.evaluate("""
    (() => {
      const el = document.querySelector('#address--countryRegion');
      el.scrollIntoView({block:'center'});
      el.focus();
      return JSON.stringify({focused: document.activeElement===el, tag:el.tagName});
    })()
    """))
    print("focused:", r)
    await asyncio.sleep(0.5)
    # Open via Enter then Space
    await key(page, "Enter")
    await asyncio.sleep(0.8)
    # Dump any listbox/popup that appeared
    lst = json.loads(await page.evaluate("""
    (() => {
      const out = [];
      const cands = document.querySelectorAll("[role='listbox'], ul[role='listbox'], [class*='listbox'], [class*='popup'], [class*='dropdown-menu'], [class*='menu']");
      for (const e of cands) {
        const rc = e.getBoundingClientRect();
        const cs = getComputedStyle(e);
        out.push({cls:(e.className||'').toString().slice(0,50), role:e.getAttribute('role'), display:cs.display, vis:cs.visibility, offP:e.offsetParent!==null, h:Math.round(rc.height), n:[...e.querySelectorAll('li, [role=option]')].length});
      }
      return JSON.stringify(out.slice(0,20));
    })()
    """))
    print("listboxes after Enter:", lst)
    await cdp.close()

asyncio.run(main())
