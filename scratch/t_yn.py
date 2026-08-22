"""Test remote-search select: open, type filter, read SCOPED filtered opts, commit."""
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

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    FID = "question_35441478002"   # a yes/no question (authorized to work?)
    await page.evaluate(sc(FID, "document.getElementById('" + FID + "').focus();true"))
    await key(b, "ArrowDown", 40)
    await asyncio.sleep(0.8)
    print("after open, scoped opts:", await page.evaluate(sc(FID, "(function(){var l=c.querySelectorAll('[role=listbox]');var r=[];for(var i=0;i<l.length;i++){for(var j=0;j<l[i].children.length;j++){var t=l[i].children[j].textContent.trim();if(t)r.push(t);}}return r;})()")))
    await typechars(b, "Yes")
    await asyncio.sleep(2.0)
    print("after type 'Yes', scoped opts:", await page.evaluate(sc(FID, "(function(){var l=c.querySelectorAll('[role=listbox]');var r=[];for(var i=0;i<l.length;i++){for(var j=0;j<l[i].children.length;j++){var t=l[i].children[j].textContent.trim();if(t)r.push(t);}}return r;})()")))
    print("search input value now:", await page.evaluate(sc(FID, "(function(){var e=document.getElementById('" + FID + "');return e.value;})()")))
    await key(b, "Enter", 13)
    await asyncio.sleep(0.8)
    print("committed:", await page.evaluate(sc(FID, "(function(){var v=c.querySelector('.select__single-value,.select__value-container');return v?v.textContent.trim().slice(0,30):'(none)';})()")))
    await b._session.close()

asyncio.run(main())
