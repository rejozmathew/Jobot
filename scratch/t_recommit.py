"""Re-commit Capital One 'No' cleanly, then check if the EID field's required
flag clears (Greenhouse conditional-logic test).
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

def eid_state():
    return ("(function(){var e=document.getElementById('question_36313323002');"
            "if(!e)return '(gone)';var f=e.closest('label')||e.parentElement;"
            "var err=f?f.textContent.trim().indexOf('required')>=0:false;"
            "return {ariaReq:e.getAttribute('aria-required'), ariaInv:e.getAttribute('aria-invalid'), "
            "labelErr:err, labelStar:/\\*$/.test(f.textContent.trim())};})()")

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    fid = "question_36313315002"

    print("EID state BEFORE:", json.dumps(await page.evaluate(eid_state())))

    # Re-commit "No": focus, open, type No, Enter
    await page.evaluate(sc(fid, "document.getElementById('" + fid + "').focus();true"))
    await asyncio.sleep(0.3)
    await key(b, "ArrowDown", 40); await asyncio.sleep(0.9)
    # read current options to be sure
    opts = await page.evaluate("(function(){var m=document.querySelector('.select__menu-list');if(!m)return[];var r=[];for(var i=0;i<m.children.length;i++){var t=m.children[i].textContent.trim();if(t)r.push(t);}return r;})()")
    print("Capital One options:", opts)
    await typechars(b, "No"); await asyncio.sleep(1.2)
    await key(b, "Enter", 13); await asyncio.sleep(1.0)
    co = await page.evaluate(sc(fid, "(function(){var c=document.getElementById('"+fid+"').closest('.select__control');var v=c.querySelector('.select__single-value,.select__value-container');return v?v.textContent.trim():'(empty)';})()"))
    print("Capital One committed:", repr(co))

    # Wait for conditional logic to re-evaluate
    await asyncio.sleep(1.5)
    print("EID state AFTER : ", json.dumps(await page.evaluate(eid_state())))
    await b._session.close()

asyncio.run(main())
