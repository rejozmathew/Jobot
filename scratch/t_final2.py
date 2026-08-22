"""FINAL: self-heal any empty required field, then Submit + confirm.
Known-good tokens: country=USA, consent=Consent. Everything else already committed.
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
    return ("(function(){var e=document.getElementById('" + fid + "');"
            "if(!e)return '(noel)';"
            "var c=e.closest('.select__control');"
            "if(c){var v=c.querySelector('.select__single-value,.select__value-container');if(v&&v.textContent.trim())return v.textContent.trim();return '(empty)';}"
            "return e.value?e.value:'(empty)';})()")

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()

    async def heal(fid, token):
        cur = await page.evaluate(val(fid))
        if cur and cur not in ("(empty)","(noel)","Select..."):
            return True, cur
        # repair
        await page.evaluate(sc(fid, "document.getElementById('" + fid + "').focus();true"))
        await asyncio.sleep(0.3)
        await key(b, "ArrowDown", 40); await asyncio.sleep(0.9)
        if token:
            await typechars(b, token); await asyncio.sleep(1.8)
        await key(b, "Enter", 13); await asyncio.sleep(0.9)
        cur = await page.evaluate(val(fid))
        print(f"   HEAL {fid}: {cur!r}")
        return (cur not in ("(empty)","(noel)","Select...")), cur

    # ensure the two that flake
    await heal("question_35441478002", "USA")
    await heal("question_35441482002", "")

    print("== FINAL STATE ==")
    fields = [
        ("first_name","First Name"),("last_name","Last Name"),("email","Email"),("phone","Phone"),
        ("candidate-location","Location(City)"),
        ("question_35441475002","How-heard"),("question_35441478002","Country-based"),
        ("question_35441479002","Authorized"),("question_35441481002","Relocate"),
        ("question_35441482002","Consent"),("question_35686603002","In-office"),
        ("question_36313315002","CapitalOne"),
    ]
    missing = []
    for fid, name in fields:
        v = await page.evaluate(val(fid))
        ok = (v and v not in ("(empty)","(noel)","Select..."))
        print(f"   {name:14s} = {v!r:45s} {'OK' if ok else 'MISSING'}")
        if not ok: missing.append((fid, name))

    # text fields auto-heal (should already be set)
    textfix = {
        "first_name":"Rejo","last_name":"Mathew","email":"rejozacharia@gmail.com","phone":"707-456-7356",
    }
    for fid in list(textfix):
        if (fid, [n for n,_ in fields if n].count(fid)) or True:
            pass
    for fid, namev in textfix.items():
        cur = await page.evaluate("document.getElementById('" + fid + "').value")
        if not cur:
            await page.evaluate("document.getElementById('" + fid + "').focus();true")
            await key(b,"a",65);  # can't easily ctrl; use select-all via JS
            await page.evaluate("document.getElementById('" + fid + "').select();true")
            await b.type_text(namev)
            await asyncio.sleep(0.3)
            print(f"   TEXTFIX {fid} -> {namev}")

    res = await page.evaluate("(function(){var s=document.querySelector('.file__name,[class*=file__name],[class*=attachment]');return s?s.textContent.trim().slice(0,50):'';})()")
    print("   resume         =", repr(res))

    print("== SUBMIT ==")
    await page.evaluate("(function(){var bs=document.querySelectorAll('button');for(var i=0;i<bs.length;i++){if(/submit/i.test(bs[i].textContent)){bs[i].scrollIntoView({block:'center'});bs[i].click();return true;}}return false;})()")
    await asyncio.sleep(5)
    url = await page.evaluate("location.href")
    print("  post URL:", url[:95])
    body = await page.evaluate("(document.body?document.body.innerText:'')")
    low = body.lower()
    if "thank" in low or "application submitted" in low or "we've received" in low or "successfully" in low or "application has been" in low:
        print("  RESULT: *** SUBMITTED ***")
    elif "required" in low or "fix the following" in low or "this field" in low or "error" in low:
        errs = await page.evaluate("(function(){var r=[];var a=document.querySelectorAll('[class*=error],[role=alert],.form__error,[class*=invalid],.field-error');for(var i=0;i<a.length&&r.length<20;i++){var t=a[i].textContent.trim();if(t)r.push(t.slice(0,70));}return r;})()")
        print("  RESULT: REJECTED ->", json.dumps(errs, ensure_ascii=False))
    else:
        print("  RESULT: UNKNOWN ->", body[:250].replace("\n"," "))
    await page.screenshot("artifacts/final.png")
    await b._session.close()

asyncio.run(main())
