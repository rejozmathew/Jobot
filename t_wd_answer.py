"""Answer all 7 Application Question selects."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

ANSWERS = [
    ("primaryQuestionnaire--bbdfc74454f31001b82f1ce870a50000", "Yes"),  # work auth
    ("primaryQuestionnaire--bbdfc74454f31001b82f1ce870a50003", "Yes"),  # sponsorship
    ("primaryQuestionnaire--bbdfc74454f31001b82f1d825f0c0000", "No"),   # Fannie Mae before
    ("primaryQuestionnaire--bbdfc74454f31001b82f1d825f0c0006", "No"),   # family at FM
    ("primaryQuestionnaire--bbdfc74454f31001b82f1d825f0c000a", "No"),   # non-compete
    ("primaryQuestionnaire--bbdfc74454f31001b82f1e1c667d0002", "Yes"),  # 18+
    ("primaryQuestionnaire--bbdfc74454f31001b82f1e1c667d0005", "No"),   # outside employment
]

async def pick(page, button_id, answer):
    # open
    await page.evaluate(f"""(() => {{ const b = document.querySelector('#{button_id}'); if(b) b.click(); }})()""")
    await asyncio.sleep(0.8)
    # click the matching option (exact text)
    r = json.loads(await page.evaluate("""
    (() => {
      const ans = %s;
      const o = [...document.querySelectorAll("[role=option], [class*=option], li[class*=item], [class*=item]")];
      // find an option whose trimmed text exactly matches the answer
      let m = o.find(x => (x.textContent||"").trim() === ans);
      if (!m) m = o.find(x => new RegExp("^"+ans+"$", "i").test((x.textContent||"").trim()));
      if (m) { m.click(); return JSON.stringify({picked: m.textContent.trim().slice(0,20)}); }
      // list available for debug
      return JSON.stringify({err:"no-opt", opts:o.map(x=>(x.textContent||"").trim().slice(0,15)).slice(0,8)});
    })()
    """ % json.dumps(answer)))
    await asyncio.sleep(0.6)
    # close dropdown if still open
    await page.evaluate("document.body.click()")
    await asyncio.sleep(0.3)
    # verify
    cur = await page.evaluate(f"""(() => {{ const b = document.querySelector('#{button_id}'); return b ? b.textContent.trim().slice(0,20) : 'gone'; }})()""")
    return {"id": button_id[-6:], "answer": answer, "pick": r, "now": cur}

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    for bid, ans in ANSWERS:
        print(" ", await pick(page, bid, ans))
    await asyncio.sleep(0.5)
    # check for a final verify checkbox
    v = await page.evaluate("""
    (() => {
      const cks = [...document.querySelectorAll("input[type=checkbox], [role=checkbox]")];
      return JSON.stringify(cks.map(c => ({id: c.id||"", checked: c.checked, lbl: (c.getAttribute("aria-label")||"").slice(0,40)})));
    })()
    """)
    print("\nCHECKBOXES:", v)
    await cdp.close()

asyncio.run(main())
