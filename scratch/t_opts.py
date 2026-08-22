"""For each select: label + scoped options (open via ArrowDown, read, Escape)."""
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

SELECTS = [
    "question_35441478002","question_35441479002","question_35441481002",
    "question_35441482002","question_35686603002","question_36313315002",
    "candidate-location","gender","hispanic_ethnicity","veteran_status","disability_status",
]

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    for fid in SELECTS:
        lab = await page.evaluate("(function(){var e=document.getElementById('" + fid + "');if(!e)return '?';var l=e.closest('label')||e.parentElement;return l.textContent.trim().replace(/\\s+/g,' ').slice(0,60);})()")
        cur = await page.evaluate(sc(fid, "(function(){var v=c.querySelector('.select__single-value,.select__value-container');return v?v.textContent.trim().slice(0,30):'(empty)';})()"))
        # open
        await page.evaluate(sc(fid, "document.getElementById('" + fid + "').focus();true"))
        await key(b, "ArrowDown", 40)
        await asyncio.sleep(1.4)
        opts = await page.evaluate(sc(fid, "(function(){var l=c.querySelectorAll('[role=listbox]');var r=[];for(var i=0;i<l.length;i++){for(var j=0;j<l[i].children.length;j++){var t=l[i].children[j].textContent.trim();if(t)r.push(t);}}return r;})()"))
        print(f"[{fid}] {lab}\n    CUR={cur}  OPTS={opts}")
        await key(b, "Escape", 27)
        await asyncio.sleep(0.5)
    await b._session.close()

asyncio.run(main())
