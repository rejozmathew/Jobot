"""Debug: for the two failing selects, after ArrowDown check aria-expanded
and search GLOBALY for any listbox/option elements on the page.
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

def sc(fid, expr):
    return ("(function(){var el=document.getElementById('" + fid + "');"
            "if(!el)return null;var c=el.closest('.select__control')||el.parentElement.parentElement;"
            "return " + expr + "})()")

async def key(b, name, vk, text=None):
    p = {"type":"keyDown","key":name,"windowsVirtualKeyCode":vk}
    if text: p["text"] = text
    await b._session.call("Input.dispatchKeyEvent", p)
    await b._session.call("Input.dispatchKeyEvent", {"type":"keyUp","key":name,"windowsVirtualKeyCode":vk})

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    for fid in ["question_35441478002","question_35441482002"]:
        print("="*60, fid)
        # current committed value
        print("  current:", await page.evaluate(sc(fid, "(function(){var c=document.getElementById('"+fid+"').closest('.select__control');var v=c.querySelector('.select__single-value,.select__value-container');return v?v.textContent.trim():'(empty)';})()")))
        await page.evaluate(sc(fid, "document.getElementById('" + fid + "').focus();true"))
        await asyncio.sleep(0.3)
        await key(b, "ArrowDown", 40)
        await asyncio.sleep(1.6)
        exp = await page.evaluate("document.getElementById('" + fid + "').getAttribute('aria-expanded')")
        print("  aria-expanded:", exp)
        # GLOBAL search for open menus
        g = await page.evaluate(
            "(function(){var r=[];var m=document.querySelectorAll('[role=listbox]');"
            "for(var i=0;i<m.length;i++){var kids=[];for(var j=0;j<m[i].children.length&&kids.length<8;j++){var t=m[i].children[j].textContent.trim();if(t)kids.push(t);}r.push({n:m[i].children.length, sample:kids, cls:m[i].className.slice(0,30)});}"
            "return r;})()")
        print("  GLOBAL listboxes:", json.dumps(g)[:400])
        # also any element with .select__menu visible
        menus = await page.evaluate("(function(){var r=[];var m=document.querySelectorAll('.select__menu, [class*=menu], [class*=option]');for(var i=0;i<m.length&&r.length<6;i++){var s=getComputedStyle(m[i]);if(s.display!=='none'&&s.visibility!=='hidden'&&m[i].textContent.trim().length<120){r.push(m[i].className.slice(0,25)+': '+m[i].textContent.trim().slice(0,50));}}return r;})()")
        print("  visible menus/options:", menus)
        await key(b, "Escape", 27)
        await asyncio.sleep(0.4)
    await b._session.close()

asyncio.run(main())
