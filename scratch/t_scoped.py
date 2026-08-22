"""Scoped select test: open + read + commit ONLY within the target control."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

FID = "question_35441475002"   # How did you hear about us

def sc(expr):
    # evaluate expr within the target select's control subtree
    return ("(function(){var el=document.getElementById('" + FID + "');"
            "var c=el.closest('.select__control')||el.parentElement.parentElement;"
            "return " + expr + "})()")

async def key(b, name, vk, text=None):
    p = {"type":"keyDown","key":name,"windowsVirtualKeyCode":vk}
    if text: p["text"] = text
    await b._session.call("Input.dispatchKeyEvent", p)
    await b._session.call("Input.dispatchKeyEvent", {"type":"keyUp","key":name,"windowsVirtualKeyCode":vk})

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    await page.evaluate(sc("document.getElementById('" + FID + "').focus()") + ";true")
    await key(b, "ArrowDown", 40)
    await asyncio.sleep(1.3)
    opened = await page.evaluate(sc("document.getElementById('" + FID + "').getAttribute('aria-expanded')"))
    opts = await page.evaluate(sc("(function(){var l=c.querySelectorAll('[role=listbox]');var r=[];for(var i=0;i<l.length;i++){for(var j=0;j<l[i].children.length;j++){var t=l[i].children[j].textContent.trim();if(t)r.push(t);}}return r;})()"))
    print("SCOPED opened:", opened, "opts:", opts)
    # commit first opt
    await key(b, "Enter", 13)
    await asyncio.sleep(0.8)
    val = await page.evaluate(sc("(function(){var v=c.querySelector('.select__single-value,.select__value-container');return v? v.textContent.trim().slice(0,40):'(none)';})()"))
    print("SCOPED committed value:", repr(val))
    await b._session.close()

asyncio.run(main())
