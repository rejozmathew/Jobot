"""Fill AvePoint react-select via KEYBOARD (typeahead + ArrowDown + Enter).

react-select ignores synthetic .click()/mousePressed; it commits on real
keyboard: focus -> type to filter -> ArrowDown to highlight -> Enter to pick.
"""
import asyncio, sys, json
sys.path.insert(0, r"C:\GitClone\auto-job-applier")
from job_applier.cdp_client import CDPBrowser
CDP = "http://127.0.0.1:9222"


async def fill_kb(sel_id: str, query: str) -> str:
    b = await CDPBrowser.connect(CDP)
    page = await b.get_current_page()
    await page.evaluate(f"document.getElementById({json.dumps(sel_id)}).focus()")
    await asyncio.sleep(0.25)
    for ch in query:
        await b.type_text(ch); await asyncio.sleep(0.06)
    await asyncio.sleep(0.8)
    # highlight first visible option, then commit with Enter
    await b.press_key("ArrowDown", 40); await asyncio.sleep(0.15)
    await b.press_key("Enter", 13); await asyncio.sleep(0.6)
    val = await page.evaluate(f"(document.getElementById({json.dumps(sel_id)})||{{}}).value")
    inv = await page.evaluate(f"(document.getElementById({json.dumps(sel_id)})||{{}}).getAttribute('aria-invalid')")
    await b.close()
    return f"val={val!r} invalid={inv}"


async def main():
    print("country:", await fill_kb("country", "United States"))
    print("work-auth:", await fill_kb("question_68514559", "Yes"))
    print("sponsorship:", await fill_kb("question_68514560", "Yes"))
    print("location:", await fill_kb("candidate-location", "Chicago"))


asyncio.run(main())
