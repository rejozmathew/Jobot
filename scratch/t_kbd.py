"""Test PURE-KEYBOARD react-select commit on the country field.
focus -> ArrowDown(open) -> type filter -> Enter(commit) -> read committed value.
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def key(b, name, vk):
    base = {"type":"keyDown","key":name,"windowsVirtualKeyCode":vk}
    if name not in ("ArrowDown","ArrowUp","Enter","Escape","Tab"):
        base["text"] = name
    await b._session.call("Input.dispatchKeyEvent", base)
    await b._session.call("Input.dispatchKeyEvent", dict(base, type="keyUp"))

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    ID = "country"

    async def committed():
        return await page.evaluate(
            "(function(){var el=document.getElementById('%s');if(!el)return 'no-el';"
            " var c=el.closest('.select__control')||el;var s=c.querySelector('.select__single-value');"
            " return s?s.textContent.trim():(el.value||'');})()" % ID)

    print("before:", await committed())
    # focus + scroll into view
    await page.evaluate("(function(){var el=document.getElementById('%s');el.scrollIntoView({block:'center'});el.focus();return el===document.activeElement;})()" % ID)
    await asyncio.sleep(0.3)
    focused = await page.evaluate("document.activeElement && document.activeElement.id")
    print("focused element:", focused)

    # ArrowDown to open
    await key(b, "ArrowDown", 40)
    await asyncio.sleep(0.5)
    expanded = await page.evaluate("document.getElementById('%s').getAttribute('aria-expanded')" % ID)
    n_opt = await page.evaluate("document.querySelectorAll('[role=listbox] li, .select__option').length")
    print("after ArrowDown: expanded=%s options=%d" % (expanded, n_opt))

    # type to filter (country -> United States)
    await b.type_text("United")
    await asyncio.sleep(1.0)
    opts = await page.evaluate("Array.from(document.querySelectorAll('[role=listbox] li, .select__option')).map(function(x){return x.textContent.trim()})")
    print("options after typing 'United':", opts[:12])

    # Enter to commit highlighted
    await key(b, "Enter", 13)
    await asyncio.sleep(0.6)
    print("after Enter committed:", repr(await committed()))

    await b._session.close()

asyncio.run(main())
