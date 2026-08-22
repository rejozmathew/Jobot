"""ONE-PASS Brex fill + submit (v2 — corrected JS, proven IIFE style)."""
import asyncio, sys, json, os
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

RESUME = r"C:\Users\rejoz\OneDrive\Documents\2026 Resume\AI balanced\Rejo_Z_Mathew_Resume.pdf"

TEXT = [
    ("first_name",            "Rejo"),
    ("last_name",             "Mathew"),
    ("email",                 "rejozacharia@gmail.com"),
    ("phone",                 "707-456-7356"),
    ("candidate-location",    "Wheeling, IL"),
    ("question_35441472002",  "https://www.linkedin.com/in/rejozacharia"),
    ("question_35441473002",  "https://www.rejozmathew.com"),
    ("question_35441474002",  "He/Him"),
]

SELECTS = [
    ("question_35441475002", ["career page"]),
    ("question_35441478002", ["usa", "united states"]),
    ("question_35441479002", ["yes"]),
    ("question_35441481002", ["yes"]),
    ("question_35441482002", ["yes"]),
    ("question_35686603002", ["yes"]),
    ("question_36313315002", ["no"]),
]

def norm(s): return " ".join(s.lower().split())

async def key(b, name, vk, ctrl=False):
    base = {"type": "keyDown", "key": name, "windowsVirtualKeyCode": vk}
    if ctrl: base["modifiers"] = 2
    if name not in ("ArrowDown", "ArrowUp", "Enter", "Escape", "Tab", "Backspace", "a"):
        base["text"] = name
    await b._session.call("Input.dispatchKeyEvent", base)
    await b._session.call("Input.dispatchKeyEvent", dict(base, type="keyUp"))

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    print("URL:", (await page.evaluate("location.href"))[:80])

    async def focus(fid):
        await page.evaluate("(function(){var el=document.getElementById('" + fid + "');"
                            "if(!el)return 'missing';el.scrollIntoView({block:'center'});el.focus();"
                            "return 'ok';})()")
        await asyncio.sleep(0.3)

    async def committed(fid):
        return await page.evaluate(
            "(function(){var el=document.getElementById('" + fid + "');if(!el)return '(missing)';"
            "if(el.classList.contains('select__input')){"
            " var c=el.closest('.select__control')||el;var s=c.querySelector('.select__single-value');"
            " return s?s.textContent.trim():(el.value||'(empty)');}"
            "if(el.type==='file')return el.files.length?('FILE: '+el.files[0].name):'(empty)';"
            "return el.value||'(empty)';})()")

    print("\n--- text fields ---")
    for fid, val in TEXT:
        r = await focus(fid)
        if r == "missing":
            print(f"  {fid:24} MISSING"); continue
        await b.type_text(val)
        await asyncio.sleep(0.15)
        await key(b, "Tab", 9)
        await asyncio.sleep(0.15)
        print(f"  {fid:24} -> {val!r:38} now={await committed(fid)!r}")

    print("\n--- selects ---")
    for fid, cands in SELECTS:
        present = await page.evaluate("document.getElementById('" + fid + "') ? 'y' : 'n'")
        if present == "n":
            print(f"  {fid:24} MISSING, skip"); continue
        await focus(fid)
        await key(b, "ArrowDown", 40)
        await asyncio.sleep(0.7)
        picked = None; last_opts = []
        for i, want in enumerate(cands):
            if i > 0:
                await key(b, "a", 65, ctrl=True); await asyncio.sleep(0.1)
                await key(b, "Backspace", 8); await asyncio.sleep(0.3)
            await b.type_text(want)
            await asyncio.sleep(0.9)
            opts = await page.evaluate(
                "Array.from(document.querySelectorAll('[role=listbox] li, .select__option'))"
                ".slice(0,10).map(function(x){return x.textContent.trim()})")
            last_opts = opts
            best = None
            for o in opts:
                if norm(want) in norm(o): best = o; break
            if best is None and want in ("usa", "united states"):
                for o in opts:
                    if any(h in norm(o) for h in ("usa", "united states", "u.s.")):
                        best = o; break
            if best:
                await key(b, "Enter", 13)
                await asyncio.sleep(0.5)
                picked = best
                break
        if picked is None:
            await key(b, "Escape", 27)
            print(f"  {fid:24} FAILED opts={last_opts[:6]}")
        else:
            print(f"  {fid:24} -> {picked!r:32} now={await committed(fid)!r}")
        await asyncio.sleep(0.2)

    print("\n--- resume ---")
    files = await page.query_selector_all("input[type=file]")
    print(f"  file inputs: {len(files)}")
    if files:
        await files[0].set_input_files(RESUME)
        await asyncio.sleep(1.5)
        print(f"  resume -> {await committed('resume')!r}")

    rc = await page.evaluate("(document.getElementById('g-recaptcha-response-100000')||{}).value || ''")
    print(f"\n--- recaptcha: {len(rc)} chars ---")
    if not rc:
        print("  waiting for invisible recaptcha token...")
        for _ in range(10):
            await asyncio.sleep(1.5)
            rc = await page.evaluate("(document.getElementById('g-recaptcha-response-100000')||{}).value || ''")
            if rc: break
        print(f"  recaptcha now: {len(rc)} chars")

    print("\n--- pre-submit verification ---")
    required = ["first_name","last_name","email","candidate-location",
                "question_35441475002","question_35441478002","question_35441479002",
                "question_35441481002","question_35441482002","question_35686603002",
                "question_36313315002","resume"]
    missing = []
    for fid in required:
        v = await committed(fid)
        ok = bool(v) and "(empty)" not in v and v != "(missing)"
        print(f"  {'OK ' if ok else 'MISS'} {fid:24} = {v!r}")
        if not ok: missing.append(fid)

    if missing:
        print(f"\n*** NOT SUBMITTING - missing: {missing}")
        await b.screenshot("artifacts/brex_not_submitted.png")
        await b._session.close(); return

    print("\n--- SUBMITTING ---")
    clicked = await page.evaluate(
        "(function(){var bs=document.querySelectorAll('button,[type=submit]');"
        "for(var i=0;i<bs.length;i++){if(/submit/i.test(bs[i].textContent)){"
        "bs[i].scrollIntoView({block:'center'});bs[i].click();return bs[i].textContent.trim();}}"
        "return null;})()")
    print(f"  clicked button: {clicked!r}")
    await asyncio.sleep(6)

    url = await page.evaluate("location.href")
    title = await page.evaluate("document.title")
    body = (await page.evaluate("document.body.innerText.slice(0,600)"))
    errs = await page.evaluate(
        "Array.from(document.querySelectorAll('.error,[class*=error],.field__error,[class*=Error]'))"
        ".map(function(e){return e.textContent.trim()}).filter(Boolean).slice(0,10)")
    print("\n=== OUTCOME ===")
    print("  URL:", url)
    print("  TITLE:", title)
    print("  ERRORS:", errs)
    print("  BODY:", body[:500].replace("\n", " | "))
    await b.screenshot("artifacts/brex_outcome.png")
    await b._session.close()

asyncio.run(main())
