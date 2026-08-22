"""Inspect what's blocking Continue: loading spinners, error toasts, modals,
button internal state, and any validation messages near the footer."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    sess = page._session

    probe = await page.evaluate(
        "(function(){"
        " var out={ };"
        " out.spinner = document.querySelectorAll('.wd-LoadingPanel, [class*=loading], [class*=spinner], [role=progressbar]').length;"
        " out.toasts = Array.from(document.querySelectorAll('[role=alert], .wd-Alert, [class*=toast], [class*=Toast], [aria-live]')).map(function(e){return (e.innerText||'').slice(0,120)}).filter(Boolean);"
        " out.modals = Array.from(document.querySelectorAll('[role=dialog], .wd-Modal, [class*=Modal]')).length;"
        " var b=document.querySelector('[data-automation-id=pageFooterNextButton]');"
        " out.btn = b ? {dis:b.disabled, ariaDis:b.getAttribute('aria-disabled'), cls:b.className, text:(b.innerText||'').trim()} : null;"
        " var foot=document.querySelector('[data-automation-id=pageFooter]');"
        " out.footerText = foot ? (foot.innerText||'').replace(/\\n+/g,' | ') : null;"
        " var err = Array.from(document.querySelectorAll('[class*=error], [class*=Error], [class*=invalid], [class*=Invalid], [class*=required]')).map(function(e){return (e.innerText||'').slice(0,100)}).filter(Boolean);"
        " out.errors = err.slice(0,8);"
        " return JSON.stringify(out);"
        "})()")
    print("PROBE:", probe, flush=True)

    # Check the body for any inline validation near the file upload.
    txt = await page.evaluate(
        "(function(){ var el=document.querySelector('[data-automation-id=resumeUpload]'); return el? (el.parentElement? el.parentElement.innerText:'').replace(/\\n+/g,' | ').slice(0,400) : 'n/a'; })()")
    print("UPLOAD AREA:", txt, flush=True)

    # Try a JS click as a fallback signal (Workday may intercept; if it advances, great).
    # First check whether the click handler is bound by dispatching and observing.
    before = await page.evaluate("location.href")
    await page.evaluate("(function(){ var b=document.querySelector('[data-automation-id=pageFooterNextButton]'); if(b) b.click(); })()")
    await asyncio.sleep(6)
    after = await page.evaluate("location.href")
    print("JS-CLICK before==after:", before == after, flush=True)
    print("AFTER URL:", after, flush=True)
    body = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,500)"))
    print("BODY:", body, flush=True)
    await cdp.close()

asyncio.run(main())
