"""Commit the two failing selects by FILTERING to a single option then Enter.
78002 country-based -> type 'USA' (filters list to USA) -> Enter
82002 consent       -> single option 'Consent' -> just open + Enter
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

async def typechars(b, s):
    for ch in s:
        await key(b, ch, ord(ch) if ch.isalpha() else 0, text=ch)
        await asyncio.sleep(0.06)

def val(fid):
    return sc(fid, "(function(){var c=document.getElementById('"+fid+"').closest('.select__control');var v=c.querySelector('.select__single-value,.select__value-container');return v?v.textContent.trim():'(empty)';})()")

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()

    # --- country-based: open, filter 'USA', Enter ---
    fid = "question_35441478002"
    await page.evaluate(sc(fid, "document.getElementById('" + fid + "').focus();true"))
    await asyncio.sleep(0.3)
    await key(b, "ArrowDown", 40); await asyncio.sleep(0.9)
    await typechars(b, "USA"); await asyncio.sleep(1.8)
    # verify filtered menu now shows USA only
    filt = await page.evaluate("(function(){var m=document.querySelector('.select__menu-list');if(!m)return 'none';var r=[];for(var i=0;i<m.children.length;i++){var t=m.children[i].textContent.trim();if(t)r.push(t);}return r;})()")
    print("78002 after filter 'USA':", filt)
    await key(b, "Enter", 13); await asyncio.sleep(0.9)
    print("78002 COMMITTED:", await page.evaluate(val(fid)))

    # --- consent: open, single option, Enter ---
    fid = "question_35441482002"
    await page.evaluate(sc(fid, "document.getElementById('" + fid + "').focus();true"))
    await asyncio.sleep(0.3)
    await key(b, "ArrowDown", 40); await asyncio.sleep(1.2)
    await key(b, "Enter", 13); await asyncio.sleep(0.9)
    print("82002 COMMITTED:", await page.evaluate(val(fid)))
    await b._session.close()

asyncio.run(main())
