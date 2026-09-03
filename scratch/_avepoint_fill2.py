"""AvePoint Greenhouse combobox filler — REAL CDP input (robust).

The handler's heal JS-clicks the combobox (opens menu) but never selects an
option; react-select commits only on genuine user-level input. This drives
each field with:
  focus -> type filter value (Input.insertText) -> wait for option ->
  scroll option into viewport -> real CDP mouse sequence (move/pressed/released).

react-select listens for mousedown on the option to commit, so a real
mousePressed+mouseReleased at the option's center is the reliable path.
"""
import sys
sys.path.insert(0, r"C:\GitClone\auto-job-applier")
import asyncio, json
from job_applier.cdp_client import CDPBrowser

CDP = "http://127.0.0.1:9222"
# (field id, value to type as filter, exact option text to click)
TARGETS = [
    ("country", "United States", "United States+1"),
    ("candidate-location", "Chicago", "Chicago"),
    ("question_68514559", "Yes", "Yes"),   # work auth
    ("question_68514560", "Yes", "Yes"),   # sponsorship
    ("question_68515738", "Yes", "Yes"),   # SaaS exp
    ("question_68515739", "Yes", "Yes"),   # strategy
    ("question_68515740", "Yes", "Yes"),   # governance
]

async def mouse_click(sess, x, y):
    x, y = int(x), int(y)
    await sess.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    await sess.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    await sess.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})

async def fill(sess, page, field_id, filter_val, option_text):
    # 1) focus + open menu
    await page.evaluate(f"document.getElementById('{field_id}').focus()")
    await asyncio.sleep(0.2)
    await page.evaluate(f"document.getElementById('{field_id}').click()")
    await asyncio.sleep(0.4)
    # 2) type to filter
    await sess.call("Input.insertText", {"text": filter_val})
    await asyncio.sleep(0.6)
    # 3) locate option
    def opt_rect(text):
        return (
            f"(() => {{ const o = Array.from(document.querySelectorAll('[role=option]'))"
            f".find(e => e.textContent.trim() === {json.dumps(text)});"
            f" if(!o) return null; o.scrollIntoView({{block:'center'}});"
            f" const r = o.getBoundingClientRect();"
            f" return {{x: r.x + r.width/2, y: r.y + r.height/2, h: r.height, inView: r.top>0 && r.bottom<window.innerHeight}}; }})()"
        )
    rect = await page.evaluate(opt_rect(option_text))
    if not rect:
        return f"{field_id}: OPTION NOT FOUND for {option_text!r}"
    await asyncio.sleep(0.3)
    # re-read after scroll
    rect = await page.evaluate(opt_rect(option_text))
    if not rect:
        return f"{field_id}: OPTION LOST after scroll"
    # 4) real mouse click
    await mouse_click(sess, rect["x"], rect["y"])
    await asyncio.sleep(0.5)
    # 5) read rendered state
    state = await page.evaluate(
        f"(() => {{ const e = document.getElementById('{field_id}');"
        f" return {{txt:(e.textContent||'').trim().slice(0,30), inv:e.getAttribute('aria-invalid')}}; }})()"
    )
    return f"{field_id}: {state}"

async def main():
    b = await CDPBrowser.connect(CDP)
    page = await b.get_current_page()
    sess = b._session
    results = []
    for fid, fv, ot in TARGETS:
        try:
            r = await fill(sess, page, fid, fv, ot)
        except Exception as e:
            r = f"{fid}: ERROR {e}"
        print(r, flush=True)
        results.append(r)
        await asyncio.sleep(0.3)
    # final snapshot of all targets
    snap = await page.evaluate("""(() => {
      const ids = ['country','candidate-location','question_68514559','question_68514560','question_68515738','question_68515739','question_68515740'];
      return ids.map(id => { const e = document.getElementById(id); return {id, txt:(e.textContent||'').trim().slice(0,25), inv:e.getAttribute('aria-invalid')}; });
    })()""")
    print("SNAPSHOT:", json.dumps(snap, ensure_ascii=False))
    await b.close()

asyncio.run(main())
