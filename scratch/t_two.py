"""Read the exact option lists for the two failing selects.
78002 = What country are you based in (remote search)
82002 = Consent
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
        await asyncio.sleep(0.05)

def opts_js(fid):
    return sc(fid, "(function(){var l=c.querySelectorAll('[role=listbox],[role=option],ul,li');var r=[];var seen={};for(var i=0;i<l.length;i++){var n=l[i];if(n.tagName!=='LI'&&n.getAttribute&&n.getAttribute('role')!=='option')continue;var t=n.textContent.trim();if(t&&!seen[t]&&t.length<40){seen[t]=1;r.push(t);}}return r;})()")

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    for fid, tok in [("question_35441478002","United States"),
                     ("question_35441478002","United"),
                     ("question_35441478002","USA"),
                     ("question_35441482002","")]:
        await page.evaluate(sc(fid, "document.getElementById('" + fid + "').focus();true"))
        await key(b, "ArrowDown", 40)
        await asyncio.sleep(0.9)
        if tok:
            await typechars(b, tok)
            await asyncio.sleep(2.2)   # allow remote load
        o = await page.evaluate(opts_js(fid))
        print(f"[{fid}] filter={tok!r} -> {o[:15]}")
        await key(b, "Escape", 27)
        await asyncio.sleep(0.5)
    await b._session.close()

asyncio.run(main())
