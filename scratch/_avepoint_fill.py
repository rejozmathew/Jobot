"""Fill AvePoint react-select comboboxes with REAL CDP mouse+key events.

react-select ignores synthetic .click(); it needs Input.dispatchMouseEvent
(click) on the option plus Input.insertText for the typeahead. We connect
to the SAME top-level form page the handler uses (the only 'page' target).
"""
import asyncio, sys, os, json
sys.path.insert(0, r"C:\GitClone\auto-job-applier")
from job_applier.cdp_client import CDPBrowser

CDP = "http://127.0.0.1:9222"


async def mouse_click(session, x, y):
    await session.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    await session.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})


async def fill_combobox(sel_id: str, query: str) -> str:
    b = await CDPBrowser.connect(CDP)
    page = await b.get_current_page()
    sess = b._session

    # 1) focus + open via real key events
    await page.evaluate(f"document.getElementById({json.dumps(sel_id)}).focus()")
    await asyncio.sleep(0.2)
    # open dropdown: react-select opens on mousedown/click
    box = await page.evaluate(f"""(function(){{const e=document.getElementById({json.dumps(sel_id)}); const r=e.getBoundingClientRect(); return {{x:r.x+r.width/2, y:r.y+r.height/2}};}})()""")
    await mouse_click(sess, box["x"], box["y"])
    await asyncio.sleep(0.5)

    # 2) type query (real keystrokes) to filter
    for ch in query:
        await b.type_text(ch)
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.8)

    # 3) find the matching visible option and mouse-click it
    res = await page.evaluate(f"""(function(){{
      var q = {json.dumps(query)};
      const opts = Array.from(document.querySelectorAll('[role=option]'));
      const m = opts.find(o => o.textContent.trim().toLowerCase().indexOf(q.toLowerCase()) !== -1 && o.offsetParent !== null);
      if (!m) return null;
      const r = m.getBoundingClientRect();
      return {{x: r.x + r.width/2, y: r.y + r.height/2, txt: m.textContent.trim()}};
    }})()""")
    if res is None:
        # no visible match — read what options are actually visible
        vis = await page.evaluate("Array.from(document.querySelectorAll('[role=option]')).filter(o=>o.offsetParent!==null).map(o=>o.textContent.trim()).slice(0,10)")
        await b.close()
        return f"NO_VISIBLE_MATCH (visible={vis})"
    await mouse_click(sess, res["x"], res["y"])
    await asyncio.sleep(0.6)

    val = await page.evaluate(f"(document.getElementById({json.dumps(sel_id)})||{{}}).value")
    inv = await page.evaluate(f"(document.getElementById({json.dumps(sel_id)})||{{}}).getAttribute('aria-invalid')")
    await b.close()
    return f"chosen={res['txt']!r} value={val!r} invalid={inv}"


async def main():
    for sel_id, q in [
        ("country", "United States"),
        ("question_68514559", "Yes"),
        ("question_68514560", "Yes"),
    ]:
        print(f"{sel_id} <- {q}: ", end="")
        print(await fill_combobox(sel_id, q))
    # Location: free text typeahead
    print("candidate-location <- Chicago: ", end="")
    b = await CDPBrowser.connect(CDP)
    page = await b.get_current_page(); sess = b._session
    await page.evaluate("document.getElementById('candidate-location').focus()")
    await asyncio.sleep(0.2)
    box = await page.evaluate("(() => {const e=document.getElementById('candidate-location'); const r=e.getBoundingClientRect(); return {x:r.x+r.width/2, y:r.y+r.height/2};})()")
    await mouse_click(sess, box["x"], box["y"]); await asyncio.sleep(0.4)
    for ch in "Chicago":
        await b.type_text(ch); await asyncio.sleep(0.05)
    await asyncio.sleep(0.9)
    opt = await page.evaluate("""(function(){const o=Array.from(document.querySelectorAll('[role=option]')).find(x=>/chicago/i.test(x.textContent)&&x.offsetParent!==null); if(!o)return null; const r=o.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2,txt:o.textContent.trim()};})()""")
    if opt:
        await mouse_click(sess, opt["x"], opt["y"]); await asyncio.sleep(0.5)
    loc = await page.evaluate("(document.getElementById('candidate-location')||{}).value")
    inv = await page.evaluate("(document.getElementById('candidate-location')||{}).getAttribute('aria-invalid')")
    await b.close()
    print(f"chosen={opt and opt['txt']} value={loc!r} invalid={inv}")


asyncio.run(main())
