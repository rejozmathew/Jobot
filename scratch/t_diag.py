"""Diagnose which iteration style works on this page."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    tests = {
        "A input.len":            "document.querySelectorAll('input').length",
        "B list.len":             "document.querySelectorAll('input,select,textarea').length",
        "C from.forEach":         r"(function(){var n=0;var a=Array.from(document.querySelectorAll('input'));a.forEach(function(){n++});return n;})()",
        "D from.for":             r"(function(){var n=0;var a=Array.from(document.querySelectorAll('input'));for(var i=0;i<a.length;i++){n++}return n;})()",
        "E direct.forEach":       r"(function(){var n=0;document.querySelectorAll('input').forEach(function(){n++});return n;})()",
        "F byId.first":           "document.getElementById('first_name')?document.getElementById('first_name').tagName:'null'",
        "G form.len":             "document.querySelectorAll('form').length",
        "H inputs[0].id":         "(function(){var a=document.querySelectorAll('input');return a.length?a[0].id||a[0].name||a[0].type:'none';})()",
    }
    for name, expr in tests.items():
        try:
            v = await page.evaluate(expr)
            print(f"  {name:18} = {v}")
        except Exception as e:
            print(f"  {name:18} = ERROR {str(e)[:80]}")
    await b._session.close()

asyncio.run(main())
