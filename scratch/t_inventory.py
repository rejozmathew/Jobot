"""COMPLETE field inventory: label, required, value, + scoped select options.
Read-only (opens each select to read options, presses Escape to close).
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

def sc(fid, expr):
    return ("(function(){var el=document.getElementById('" + fid + "');"
            "if(!el)return null;var c=el.closest('.select__control')||el.parentElement.parentElement;"
            "return " + expr + "})()")

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    ids = await page.evaluate("(function(){var r=[];var a=document.querySelectorAll('input[id],select[id]');for(var i=0;i<a.length;i++){r.push(a[i].id);}return r;})()")
    for fid in ids:
        # label
        lab = await page.evaluate("(function(){var e=document.getElementById('" + fid + "');if(!e)return '';var l=e.closest('label');if(l)return l.textContent.trim();var p=e.parentElement;var n=p?p.querySelector('label'):null;return n?n.textContent.trim():'';})()")
        typ = await page.evaluate("(function(){var e=document.getElementById('" + fid + "');return e?e.tagName.toLowerCase()+'.'+(e.type||''):'?';})()")
        req = await page.evaluate("(function(){var e=document.getElementById('" + fid + "');var f=e?e.closest('label'):null;return f? /\\*\\s*$/.test(f.textContent) : false;})()")
        kind = "select" if (await page.evaluate("(function(){var e=document.getElementById('" + fid + "');return e&&(e.className||'').indexOf('select__input')>=0;})()")) else typ
        line = f"[{fid}] req={req} kind={kind} :: {lab[:48]}"
        if kind == "select":
            cur = await page.evaluate(sc(fid, "(function(){var v=c.querySelector('.select__single-value,.select__value-container');return v?v.textContent.trim().slice(0,30):'(empty)';})()"))
            line += " CUR=" + cur
        print(line)
    print("--- URL:", (await page.evaluate("location.href"))[:80])
    await b._session.close()

asyncio.run(main())
