"""FINAL SUBMIT: EID -> 'N/A' (honest not-applicable, not a fake ID), then submit + confirm.
All other fields already committed per user instructions (Capital One = No).
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

def val(fid):
    return ("(function(){var e=document.getElementById('" + fid + "');"
            "if(!e)return '(noel)';"
            "var c=e.closest('.select__control');"
            "if(c){var v=c.querySelector('.select__single-value,.select__value-container');if(v&&v.textContent.trim())return v.textContent.trim();return '(empty)';}"
            "return e.value?e.value:'(empty)';})()")

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()

    # Set EID to N/A
    eid = "question_36313323002"
    await page.evaluate("document.getElementById('" + eid + "').focus();true")
    await asyncio.sleep(0.3)
    await page.evaluate("document.getElementById('" + eid + "').select();true")
    await asyncio.sleep(0.2)
    await b.type_text("N/A")
    await asyncio.sleep(0.5)
    await page.evaluate("document.getElementById('" + eid + "').blur();true")
    await asyncio.sleep(0.8)
    print("EID value now:", await page.evaluate("document.getElementById('" + eid + "').value"))

    print("== FINAL STATE ==")
    fields = [
        ("first_name","First Name"),("last_name","Last Name"),("email","Email"),("phone","Phone"),
        ("candidate-location","Location"),
        ("question_35441475002","How-heard"),("question_35441478002","Country-based"),
        ("question_35441479002","Authorized"),("question_35441481002","Relocate"),
        ("question_35441482002","Consent"),("question_35686603002","In-office"),
        ("question_36313315002","CapitalOne"),
    ]
    for fid, name in fields:
        v = await page.evaluate(val(fid))
        print(f"   {name:13s} = {v!r}")
    print("   CapitalOne-EID =", repr(await page.evaluate("document.getElementById('question_36313323002').value")))
    res = await page.evaluate("(function(){var s=document.querySelector('.file__name,[class*=file__name],[class*=attachment]');return s?s.textContent.trim().slice(0,55):'';})()")
    print("   resume        =", repr(res))

    print("== SUBMIT ==")
    clicked = await page.evaluate("(function(){var bs=document.querySelectorAll('button');for(var i=0;i<bs.length;i++){if(/submit/i.test(bs[i].textContent)){bs[i].scrollIntoView({block:'center'});bs[i].click();return true;}}return false;})()")
    print("  submit clicked:", clicked)
    await asyncio.sleep(5)
    url = await page.evaluate("location.href")
    print("  post URL:", url[:95])
    body = await page.evaluate("(document.body?document.body.innerText:'')")
    low = body.lower()
    if "thank" in low or "application submitted" in low or "we've received" in low or "successfully" in low or "application has been" in low or "you're all set" in low:
        print("  RESULT: *** SUBMITTED ***")
    elif "required" in low or "fix the following" in low or "this field" in low or "error" in low:
        errs = await page.evaluate("(function(){var r=[];var a=document.querySelectorAll('[class*=error],[role=alert],.form__error,[class*=invalid],.field-error,.helper-text');for(var i=0;i<a.length&&r.length<20;i++){var t=a[i].textContent.trim();if(t)r.push(t.slice(0,70));}return r;})()")
        print("  RESULT: REJECTED ->", json.dumps(errs, ensure_ascii=False))
    else:
        print("  RESULT: UNKNOWN ->", body[:250].replace("\n"," "))
    await page.screenshot("artifacts/submitted.png")
    await b._session.close()

asyncio.run(main())
