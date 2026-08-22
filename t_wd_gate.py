"""Dump ALL form controls (checkboxes/radios/inputs/buttons) + full step-1 text,
to find the silent required-field gate blocking Continue."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    # Full visible text of the main apply region.
    full = await page.evaluate(
        "(function(){var m=document.querySelector('[data-automation-id=applyFlowPage]');"
        " return m? (m.innerText||'').replace(/\\n+/g,' | ').slice(0,900) : document.body.innerText.slice(0,900);})()")
    print("FULL TEXT:", full, flush=True)

    # All interactive controls with state.
    ctrls = await page.evaluate(
        "JSON.stringify(Array.from(document.querySelectorAll('input, button, [role=checkbox], [role=radio], [role=switch], select'))"
        ".map(function(e){ return {tag:e.tagName, type:e.type||'', aid:e.getAttribute('data-automation-id'),"
        " checked:e.checked!==undefined?e.checked:null, dis:e.disabled||null, req:e.required||null,"
        " name:e.name||'', txt:(e.innerText||e.value||'').toString().slice(0,40)}; }))")
    print("CONTROLS:", ctrls, flush=True)

    # Any form element + its novalidate state + aria-invalid children.
    forms = await page.evaluate(
        "JSON.stringify(Array.from(document.querySelectorAll('form')).map(function(f){"
        " return {action:f.action||'', novalidate:f.novalidate||null, name:f.name||''};}))")
    print("FORMS:", forms, flush=True)

    # aria-invalid / aria-required elements.
    invalid = await page.evaluate(
        "JSON.stringify(Array.from(document.querySelectorAll('[aria-invalid=true],[aria-required=true]'))"
        ".map(function(e){return {tag:e.tagName, aid:e.getAttribute('data-automation-id'), txt:(e.innerText||'').slice(0,60)}}))")
    print("ARIA-REQUIRED/INVALID:", invalid, flush=True)
    await cdp.close()

asyncio.run(main())
