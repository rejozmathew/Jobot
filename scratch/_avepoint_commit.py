"""Commit react-select comboboxes on AvePoint Greenhouse using REAL CDP input.

The handler's heal only JS-clicks the combobox (opens menu) and never picks
an option. react-select commits via real keyboard events on its hidden input.
This script, for each target: focus combobox -> type the value (real
insertText, filters list) -> press ArrowDown (real keyDown/Up) -> press Enter
(real keyDown/Up). Then reports the combobox's rendered text + aria-invalid.

Targets (all should be 'Yes' or 'United States'):
  country        -> United States  (phone-code iti)
  candidate-location -> Chicago
  question_68514559 (work auth) -> Yes
  question_68514560 (sponsorship) -> Yes
  question_68515738 (SaaS exp) -> Yes
  question_68515739 (strategy) -> Yes
  question_68515740 (governance) -> Yes
"""
import sys
sys.path.insert(0, r"C:\GitClone\auto-job-applier")
import asyncio, json, time
from job_applier.cdp_client import CDPBrowser

CDP = "http://127.0.0.1:9222"

TARGETS = [
    ("country", "United States"),
    ("candidate-location", "Chicago"),
    ("question_68514559", "Yes"),
    ("question_68514560", "Yes"),
    ("question_68515738", "Yes"),
    ("question_68515739", "Yes"),
    ("question_68515740", "Yes"),
]

async def commit(b, page, field_id, value):
    # Focus the combobox (real CDP mouse click at its center first)
    box = await page.evaluate(f"""(() => {{
      const e = document.getElementById('{field_id}');
      if (!e) return null;
      e.scrollIntoView({{block:'center'}});
      const r = e.getBoundingClientRect();
      return {{x: r.x + r.width/2, y: r.y + r.height/2}};
    }})()""")
    if not box:
        return f"{field_id}: NOT FOUND"
    await page.evaluate(f"document.getElementById('{field_id}').focus()")
    await asyncio.sleep(0.25)
    # Type the value to filter (real insertText)
    await b.type_text(value)
    await asyncio.sleep(0.5)
    # ArrowDown to select first filtered option
    await b.press_key("ArrowDown")
    await asyncio.sleep(0.15)
    # Enter to commit
    await b.press_key("Enter")
    await asyncio.sleep(0.5)
    # Read rendered state
    state = await page.evaluate(f"""(() => {{
      const e = document.getElementById('{field_id}');
      return {{txt: (e.textContent||'').trim().slice(0,40), inv: e.getAttribute('aria-invalid'),
              val: e.value||''}};
    }})()""")
    return f"{field_id}: {state}"

async def main():
    b = await CDPBrowser.connect(CDP)
    page = await b.get_current_page()
    for fid, val in TARGETS:
        try:
            print(await commit(b, page, fid, val))
        except Exception as e:
            print(f"{fid}: ERROR {e}")
        await asyncio.sleep(0.3)
    await b.close()

asyncio.run(main())
