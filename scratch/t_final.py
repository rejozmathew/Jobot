"""ONE-PASS Brex Greenhouse fill + submit. Final.
Text fields (top) -> scoped-keyboard selects -> resume -> verify -> submit -> confirm.
Capital One = No. EID blank. Country-based = United States.
"""
import asyncio, sys, json, os
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

RESUME = r"C:\Users\rejoz\OneDrive\Documents\2026 Resume\AI balanced\Rejo_Z_Mathew_Resume.pdf"
FIRST, LAST = "Rejo", "Mathew"
EMAIL = "rejozacharia@gmail.com"
PHONE = "707-456-7356"
LINKEDIN = "https://www.linkedin.com/in/rejozacharia"   # profile.json
WEBSITE  = "https://www.rejozmathew.com"                # profile.json

LOG = []
def log(m): LOG.append(m); print(m, flush=True)

# ---- CDP primitives (proven) -------------------------------------------------
def sc(fid, expr):  # scope an expression to this select's control subtree
    return ("(function(){var el=document.getElementById('" + fid + "');"
            "if(!el)return null;var c=el.closest('.select__control')||el.parentElement.parentElement;"
            "return " + expr + "})()")

async def key(b, name, vk, text=None, mods=0):
    p = {"type":"keyDown","key":name,"windowsVirtualKeyCode":vk}
    if text: p["text"] = text
    if mods: p["modifiers"] = mods
    await b._session.call("Input.dispatchKeyEvent", p)
    await b._session.call("Input.dispatchKeyEvent",
        {"type":"keyUp","key":name,"windowsVirtualKeyCode":vk, **({"modifiers":mods} if mods else {})})

async def typechars(b, s):
    for ch in s:
        await key(b, ch, ord(ch) if ch.isalpha() else 0, text=ch)
        await asyncio.sleep(0.06)

async def clear(b):
    await key(b, "a", 65, mods=2)      # Ctrl+A select-all
    await asyncio.sleep(0.05)
    await key(b, "Delete", 46)          # delete

async def focus(b, page, fid):
    await page.evaluate("document.getElementById('" + fid + "').focus();true")
    await asyncio.sleep(0.2)

async def fill_text(b, page, fid, val):
    if not val: return True
    await focus(b, page, fid)
    await clear(b)
    await b.type_text(val)
    await asyncio.sleep(0.25)
    got = await page.evaluate("document.getElementById('" + fid + "').value")
    ok = (got or "").strip() == val
    log(f"  TEXT {fid} -> {val!r}  (got {got!r}) {'OK' if ok else 'MISMATCH'}")
    return ok

async def committed(b, page, fid):
    v = await page.evaluate(sc(fid,
        "(function(){var el=document.getElementById('" + fid + "');"
        "var v=el.closest('.select__control');v=v?v.querySelector('.select__single-value,.select__value-container'):null;"
        "return v?v.textContent.trim().slice(0,40):'';})()"))
    return v or ""

async def pick_select(b, page, fid, tokens):
    """tokens: ordered list of filter strings to try (e.g. ['No']).
    Opens the scoped select, types the first token, commits with Enter;
    retries with the next token if the value didn't commit. Returns (ok, value)."""
    last = ""
    for tok in tokens:
        try:
            await focus(b, page, fid)
            await key(b, "ArrowDown", 40)          # open menu
            await asyncio.sleep(1.1)
            if tok:
                await typechars(b, tok)             # filter
                await asyncio.sleep(1.6)            # allow remote load
            await key(b, "Enter", 13)               # commit highlighted
            await asyncio.sleep(0.8)
            val = await committed(b, page, fid)
            log(f"  SELECT {fid} tok={tok!r} -> committed {val!r}")
            if val and tok and (tok.lower() in val.lower() or val.lower() not in ("select...","")):
                return True, val
            last = val
        except Exception as e:
            log(f"  SELECT {fid} tok={tok!r} EXC {e}")
    return False, last

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    log("URL: " + (await page.evaluate("location.href"))[:80])

    # ---- 1. TOP TEXT FIELDS (the ones you said were empty) ------------------
    log("== TEXT ==")
    await fill_text(b, page, "first_name", FIRST)
    await fill_text(b, page, "last_name", LAST)
    await fill_text(b, page, "email", EMAIL)
    await fill_text(b, page, "phone", PHONE)
    await fill_text(b, page, "question_35441472002", LINKEDIN)   # LinkedIn
    if WEBSITE: await fill_text(b, page, "question_35441473002", WEBSITE)
    # pronouns (He/Him/His) - text field
    await fill_text(b, page, "question_35441474002", "He/Him/His")

    # ---- 2. SELECTS (scoped keyboard) --------------------------------------
    log("== SELECTS ==")
    # Location (City)  -> San Francisco
    ok,v = await pick_select(b, page, "candidate-location", ["San Francisco","San Fran","California"])
    log("   location ok" if ok else "   location FAIL")
    # What country are you based in? -> United States
    ok,v = await pick_select(b, page, "question_35441478002", ["United States","United","USA"])
    log("   based-country ok" if ok else "   based-country FAIL")
    # Authorized to work? -> Yes
    ok,v = await pick_select(b, page, "question_35441479002", ["Yes"])
    log("   authorized ok" if ok else "   authorized FAIL")
    # Relocate? -> Yes
    ok,v = await pick_select(b, page, "question_35441481002", ["Yes"])
    log("   relocate ok" if ok else "   relocate FAIL")
    # Consent -> Yes
    ok,v = await pick_select(b, page, "question_35441482002", ["Yes"])
    log("   consent ok" if ok else "   consent FAIL")
    # In-office ack -> Yes
    ok,v = await pick_select(b, page, "question_35686603002", ["Yes"])
    log("   in-office ok" if ok else "   in-office FAIL")
    # Capital One -> NO (critical)
    ok,v = await pick_select(b, page, "question_36313315002", ["No"])
    log("   capital-one ok (No)" if (ok and "no" in v.lower()) else "   capital-one FAIL "+v)

    # ---- 3. RESUME upload ---------------------------------------------------
    log("== RESUME ==")
    files = await page.query_selector_all("input[type=file]")
    log(f"  found {len(files)} file inputs")
    # resume is the primary one (not cover letter). Set on first file input.
    if files:
        try:
            await files[0].set_input_files(RESUME)
            await asyncio.sleep(2.5)
            # read back the visible filename
            fn = await page.evaluate("(function(){var s=document.querySelector('.file__name, [class*=file] , .attachment');return s?s.textContent.trim().slice(0,50):'';})()")
            log("  resume set -> " + (fn or "(set, no label)"))
        except Exception as e:
            log("  resume EXC " + str(e))

    # ---- 4. VERIFY all committed values -------------------------------------
    log("== VERIFY ==")
    for fid in ["first_name","last_name","email","phone",
                "candidate-location","question_35441478002","question_35441479002",
                "question_35441481002","question_35441482002","question_35686603002",
                "question_36313315002"]:
        if fid in ("first_name","last_name","email","phone"):
            v = await page.evaluate("document.getElementById('" + fid + "').value")
        else:
            v = await committed(b, page, fid)
        log(f"   {fid:22s} = {v!r}")

    # ---- 5. SUBMIT ----------------------------------------------------------
    log("== SUBMIT ==")
    sub = await page.evaluate("(function(){var bs=Array.from(document.querySelectorAll('button'));for(var i=0;i<bs.length;i++){if(/submit/i.test(bs[i].textContent))return bs[i].id||bs[i].textContent.trim();}return null;})()")
    log("  submit button: " + str(sub))
    await page.evaluate("(function(){var bs=document.querySelectorAll('button');for(var i=0;i<bs.length;i++){if(/submit/i.test(bs[i].textContent)){bs[i].scrollIntoView({block:'center'});bs[i].click();return true;}}return false;})()")
    await asyncio.sleep(4.5)
    url = await page.evaluate("location.href")
    log("  post-submit URL: " + url[:100])
    # confirmation / error detection
    body = await page.evaluate("(document.body?document.body.innerText:'')")
    low = body.lower()
    if "thank" in low or "application submitted" in low or "we've received" in low or "success" in low:
        log("  RESULT: SUBMITTED (confirmation detected)")
    elif "required" in low or "fix the following" in low or "error" in low:
        # capture the specific required-field errors
        errs = await page.evaluate("(function(){var r=[];var a=document.querySelectorAll('[class*=error],[role=alert],.form__error,[class*=invalid]');for(var i=0;i<a.length&&r.length<15;i++){var t=a[i].textContent.trim();if(t)r.push(t.slice(0,70));}return r;})()")
        log("  RESULT: REJECTED -> " + json.dumps(errs))
    else:
        log("  RESULT: UNKNOWN -> " + body[:300].replace("\n"," "))
    await page.screenshot("artifacts/after_submit.png")
    await b._session.close()

asyncio.run(main())
