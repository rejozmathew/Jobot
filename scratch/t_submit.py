"""FINAL verify-all + submit + confirm.
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
    print("== FINAL STATE ==")
    for fid, name in [
        ("first_name","First Name"),("last_name","Last Name"),("email","Email"),("phone","Phone"),
        ("candidate-location","Location(City)"),
        ("question_35441475002","How-heard"),("question_35441478002","Country-based"),
        ("question_35441479002","Authorized"),("question_35441481002","Relocate"),
        ("question_35441482002","Consent"),("question_35686603002","In-office"),
        ("question_36313315002","CapitalOne"),
    ]:
        v = await page.evaluate(val(fid))
        flag = "OK" if (v and v != "(empty)" and v != "Select...") else "MISSING"
        print(f"   {name:14s} = {v!r:45s} {flag}")
    # resume
    res = await page.evaluate("(function(){var s=document.querySelector('.file__name,[class*=file__name],[class*=attachment]');return s?s.textContent.trim().slice(0,50):'';})()")
    print("   resume         =", repr(res))

    print("== SUBMIT ==")
    await page.evaluate("(function(){var bs=document.querySelectorAll('button');for(var i=0;i<bs.length;i++){if(/submit/i.test(bs[i].textContent)){bs[i].scrollIntoView({block:'center'});bs[i].click();return true;}}return false;})()")
    await asyncio.sleep(5)
    url = await page.evaluate("location.href")
    print("  post URL:", url[:95])
    body = await page.evaluate("(document.body?document.body.innerText:'')")
    low = body.lower()
    if "thank" in low or "application submitted" in low or "we've received" in low or "successfully" in low:
        print("  RESULT: *** SUBMITTED ***")
    elif "required" in low or "fix the following" in low or "error" in low or "this field" in low:
        errs = await page.evaluate("(function(){var r=[];var a=document.querySelectorAll('[class*=error],[role=alert],.form__error,[class*=invalid],.field-error');for(var i=0;i<a.length&&r.length<20;i++){var t=a[i].textContent.trim();if(t)r.push(t.slice(0,70));}return r;})()")
        print("  RESULT: REJECTED ->", json.dumps(errs, ensure_ascii=False))
    else:
        print("  RESULT: UNKNOWN ->", body[:250].replace("\n"," "))
    await page.screenshot("artifacts/final.png")
    await b._session.close()

asyncio.run(main())
