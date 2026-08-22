"""One-pass Brex Greenhouse fill + submit.
Order: top contact text fields -> selects -> consent -> resume -> submit -> verify.
CDP clicks use VIEWPORT coords; window is short so we always scrollIntoView + check visibility.
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

RESUME = r"C:\Users\rejoz\OneDrive\Documents\2026 Resume\AI balanced\Rejo_Z_Mathew_Resume.pdf"

IDENTITY = {
    "first":  "Rejo",
    "last":   "Mathew",
    "email":  "rejozacharia@gmail.com",
    "phone":  "707-456-7356",
    "linkedin": "https://www.linkedin.com/in/rejozacharia",
    "website":  "https://www.rejozmathew.com",
    "github":   "https://github.com/rejozmathew",
    "pronouns": "He/Him",
}

# label-substring -> value  (text fields, case-insensitive)
TEXT_MAP = [
    ("first name",  IDENTITY["first"]),
    ("last name",   IDENTITY["last"]),
    ("email",       IDENTITY["email"]),
    ("phone",       IDENTITY["phone"]),
    ("linkedin",    IDENTITY["linkedin"]),
    ("website",     IDENTITY["website"]),
    ("github",      IDENTITY["github"]),
    ("pronoun",     IDENTITY["pronouns"]),
]

# label-substring -> option-text-substring (selects)
SELECT_MAP = [
    ("how did you hear", "career page"),
    ("authorized to work", "yes"),
    ("sponsorship", "yes"),
    ("relocate", "yes"),
    ("in-office", "yes"),
    ("three days", "yes"),
    ("capital one", "no"),
    ("discover", "no"),
]

# country-ish fields: match any option that is United States / USA
COUNTRY_HINTS = ("united states", "usa", "u.s.", "us")

async def click_xy(browser, x, y):
    s = browser._session
    for ty in ("mouseDown", "mouseUp"):
        await s.call("Input.dispatchMouseEvent",
            {"type": ty, "x": int(x), "y": int(y), "button": "left",
             "clickCount": 1, "pointerType": "mouse"})
    await asyncio.sleep(0.15)

async def main():
    browser = CDPBrowser("http://127.0.0.1:9222"); await browser.connect()
    page = await browser.get_current_page()

    # ---- enumerate every field: id, kind, label, required ----
    JS_ENUM = r"""
    () => {
      const out = [];
      const els = Array.from(document.querySelectorAll(
        'input[id], select[id], [id^="question_"]'));
      const seen = new Set();
      for (const el of els) {
        const id = el.id; if (!id || seen.has(id)) continue; seen.add(id);
        let label = el.getAttribute('aria-label') || '';
        if (!label) {
          const lab = document.querySelector('label[for="'+id+'"]');
          if (lab) label = lab.textContent.trim();
        }
        if (!label) {
          const wrap = el.closest('[id$="-label"], .question, .field');
          if (wrap) { const l=wrap.querySelector('label'); if(l) label=l.textContent.trim(); }
        }
        let kind='text';
        if (el.type==='checkbox') kind='checkbox';
        else if (el.classList && el.classList.contains('select__input')) kind='select';
        else if (el.getAttribute('aria-haspopup')) kind='select';
        else if (el.type==='file') kind='file';
        out.push({id, kind, label:(label||'').slice(0,80),
                  required: el.required===true});
      }
      return out;
    }
    """
    fields = await page.evaluate(JS_ENUM)
    print("=== FIELDS ===")
    for f in fields:
        print(f"  [{f['kind']:8s}] req={str(f['required'])[0]:1s} {f['id']:26s} | {f['label']}")
    print()

    results = []

    async def fill_text(fid, value):
        # real CDP type into the input
        await page.evaluate(f"document.getElementById({json.dumps(fid)}).focus()")
        await asyncio.sleep(0.1)
        await browser.type_text(value)
        await asyncio.sleep(0.1)
        # commit with Tab
        await browser.press_key("Tab", 9)
        await asyncio.sleep(0.2)

    async def fill_select(fid, want):
        """Open menu via CDP click at viewport coords, pick matching option."""
        # scroll into view + get viewport rect
        r = await page.evaluate(r"""
          (id) => { const el=document.getElementById(id);
            el.scrollIntoView({block:'center', behavior:'instant'});
            const c = el.closest('.select__control') || el;
            const b = c.getBoundingClientRect();
            return {x:b.left+b.width/2, y:b.top+b.height/2,
                    vis: b.top>=0 && b.bottom<=innerHeight}; }
        """, arg=fid)
        if not r.get("vis"):
            # force center again
            await page.evaluate(f"document.getElementById({json.dumps(fid)}).scrollIntoView({{block:'center'}})")
            await asyncio.sleep(0.3)
            r = await page.evaluate(r"""
              (id) => { const el=document.getElementById(id);
                const c = el.closest('.select__control') || el;
                const b = c.getBoundingClientRect();
                return {x:b.left+b.width/2, y:b.top+b.height/2,
                        vis: b.top>=0 && b.bottom<=innerHeight}; }
            """, arg=fid)
        await click_xy(browser, r["x"], r["y"])
        await asyncio.sleep(0.8)
        # if remote (no options), type to search
        async def options():
            return await page.evaluate(r"""
              () => Array.from(document.querySelectorAll('[role=listbox] li, .select__option'))
                       .map(x => x.textContent.trim())
            """)
        opts = await options()
        if len(opts) < 1 and want and want.lower() in ("united states","usa","us"):
            await browser.type_text("United")
            await asyncio.sleep(1.5)
            opts = await options()
        # find best option
        def norm(s): return " ".join(s.lower().split())
        target = norm(want)
        chosen = None
        for o in opts:
            if target in norm(o) or norm(o) in target:
                chosen = o; break
        if not chosen and target in ("united states","usa","us","u.s."):
            for o in opts:
                if any(h in norm(o) for h in COUNTRY_HINTS):
                    chosen = o; break
        if chosen is None and opts:
            chosen = opts[0]
        if chosen is None:
            return False, opts[:5]
        # click the chosen option at viewport coords
        oc = await page.evaluate(r"""
          (txt) => { const els=Array.from(document.querySelectorAll('[role=listbox] li, .select__option'));
            const el = els.find(e => e.textContent.trim() === txt);
            if (!el) return null;
            el.scrollIntoView({block:'center'});
            const b = el.getBoundingClientRect();
            return {x:b.left+b.width/2, y:b.top+b.height/2, vis:b.top>=0&&b.bottom<=innerHeight}; }
        """, arg=chosen)
        if oc and oc.get("vis"):
            await click_xy(browser, oc["x"], oc["y"])
        else:
            # fallback: enter
            await browser.press_key("Enter", 13)
        await asyncio.sleep(0.6)
        sv = await page.evaluate(r"""
          (id) => { const el=document.getElementById(id);
            const c = el.closest('.select__control') || el.closest('[id$="-label"]') || el;
            const s = c.querySelector('.select__single-value');
            return s ? s.textContent.trim() : ''; }
        """, arg=fid)
        return (sv == chosen), (sv or "EMPTY", opts[:5])

    # ---- 1. TEXT FIELDS (top of form first) ----
    for f in fields:
        if f["kind"] != "text": continue
        lab = f["label"].lower()
        for key, val in TEXT_MAP:
            if key in lab and val:
                await fill_text(f["id"], val)
                results.append(("TEXT", f["id"], f["label"], f"-> {val}"))
                break
    # ---- 2. SELECTS ----
    for f in fields:
        if f["kind"] != "select": continue
        lab = f["label"].lower()
        # country-ish?
        is_country = any(h in lab for h in ("country","location (city)","city")) or \
                     ("country" in lab) or ("location" in lab and "city" in lab)
        chosen_val = None
        for key, opt in SELECT_MAP:
            if key in lab:
                chosen_val = opt; break
        if chosen_val is None and is_country:
            chosen_val = "United States"
        if chosen_val is None:
            continue
        ok, detail = await fill_select(f["id"], chosen_val)
        results.append(("SELECT", f["id"], f["label"], f"want={chosen_val} ok={ok} now={detail[0]}"))
        await asyncio.sleep(0.2)
    # ---- 3. CONSENT / CHECKBOX ----
    for f in fields:
        if f["kind"] == "checkbox":
            lab = f["label"].lower()
            if any(h in lab for h in ("process","consent","agree","permission","brex")):
                # click it if not already checked
                cur = await page.evaluate(f"document.getElementById({json.dumps(f['id'])}).checked")
                if not cur:
                    await click_xy(browser, *(await page.evaluate(r"""
                      (id)=>{const el=document.getElementById(id);el.scrollIntoView({block:'center'});
                      const b=el.getBoundingClientRect();return[b.left+b.width/2,b.top+b.height/2];}
                    """, arg=f["id"])))
                results.append(("CHECKBOX", f["id"], f["label"], "toggled"))
    # ---- 4. RESUME UPLOAD ----
    files = await page.query_selector_all("input[type=file]")
    if files:
        target = RESUME
        try:
            await files[0].set_input_files(target)
            await asyncio.sleep(1.0)
            results.append(("FILE", files[0].id, "resume", RESUME))
        except Exception as e:
            results.append(("FILE", "resume", "ERROR", str(e)[:100]))

    print("\n=== RESULTS ===")
    for r in results:
        print("  ", r)

    # ---- 5. FINAL STATE DUMP ----
    print("\n=== FINAL STATE (before submit) ===")
    state = await page.evaluate(r"""
      () => {
        const g = id => { const el=document.getElementById(id); if(!el) return null;
          if (el.classList && el.classList.contains('select__input')) {
            const c = el.closest('.select__control') || el;
            const s = c.querySelector('.select__single-value');
            return s ? s.textContent.trim() : (el.value||'');
          }
          if (el.type==='checkbox') return el.checked?'[checked]':'[unchecked]';
          if (el.type==='file') return el.files.length? '[file: '+el.files[0].name+']' : '[EMPTY]';
          return el.value || '';
        };
        const out={};
        for (const id of ['first_name','last_name','email','phone','candidate-location','country',
          'question_35441467002','question_35441475002','question_35441476002','question_35441477002',
          'question_35441478002','question_35441479002','question_35441480002','question_35441481002',
          'question_35441482002']) { out[id]=g(id); }
        return out;
      }
    """)
    for k,v in state.items():
        print(f"  {k:26s} = {v!r}")

    # ---- 6. SUBMIT ----
    print("\n=== SUBMITTING ===")
    btn = await page.evaluate(r"""
      () => { const b = Array.from(document.querySelectorAll('button,[type=submit]'))
                 .find(x=>/submit/i.test(x.textContent)); if(!b) return null;
        b.scrollIntoView({block:'center'}); const r=b.getBoundingClientRect();
        return {x:r.left+r.width/2, y:r.top+r.height/2, txt:b.textContent.trim()}; }
    """)
    print("  submit button:", btn)
    if btn and btn.get("y") is not None:
        await click_xy(browser, btn["x"], btn["y"])
        await asyncio.sleep(4.0)
    # verify
    ver = await page.evaluate(r"""
      () => ({
        url: location.href,
        title: document.title,
        body: (document.body.innerText||'').slice(0,400),
        errors: Array.from(document.querySelectorAll('.error, [class*="error"], .field__error'))
                     .map(e=>e.textContent.trim()).filter(Boolean).slice(0,10)
      })
    """)
    print("\n=== POST-SUBMIT ===")
    print("  URL:", ver["url"])
    print("  TITLE:", ver["title"])
    print("  ERRORS:", ver["errors"])
    print("  BODY:", ver["body"][:300])
    await browser.screenshot("artifacts/brex_final.png")
    print("\n  screenshot -> artifacts/brex_final.png")
    await browser.close()

asyncio.run(main())
