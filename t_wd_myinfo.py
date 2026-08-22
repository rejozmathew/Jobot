"""Navigate to /apply/applyManually (My Information step) and dump the form
fields + any conflict/dialog, so we know exactly what to fill and resolve."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

MANUAL = ("https://fanniemae.wd1.myworkdayjobs.com/en-US/FannieMaeCareers/job/"
          "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677/apply/applyManually")

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    await page.goto(MANUAL)
    await asyncio.sleep(7)
    url = page.url
    print("URL:", url)
    # dump all inputs/textareas/selects
    fields = json.loads(await page.evaluate(
        "JSON.stringify(Array.from(document.querySelectorAll('input,textarea,select')).map(function(e){"
        " return {tag:e.tagName, type:e.type||null, aid:e.getAttribute('data-automation-id'),"
        " id:e.id, name:e.name, ph:e.getAttribute('placeholder'), val:(e.value||'').slice(0,40)};"
        "}))"
    ))
    print("FIELDS:")
    for f in fields: print("  ", json.dumps(f))
    # step indicator + any conflict text
    info = json.loads(await page.evaluate(
        "JSON.stringify({"
        " step: (document.body.innerText.match(/step \\d+ of \\d+/g)||[]).slice(0,3),"
        " conflict: (document.body.innerText.match(/[Cc]onflict|already exists|[Pp]revious [Ww]orker|[Pp]revious [Aa]pplication/g)||[]),"
        " buttons: Array.from(document.querySelectorAll('button,a,[role=button]')).filter(e=>{var t=(e.innerText||'').trim();return t&&t.length<30&&(t.match(/continue|back|submit|yes|no|update|proceed|review|start|apply|save/i))}).map(e=>({aid:e.getAttribute('data-automation-id'),txt:(e.innerText||'').trim().slice(0,25)}))"
        "})"
    ))
    print("INFO:", json.dumps(info, indent=1))
    await cdp.close()

asyncio.run(main())
