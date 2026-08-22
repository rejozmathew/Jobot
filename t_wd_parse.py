"""Instrumented: hook network, attach resume, watch upload+parse lifecycle,
wait for parse to settle, THEN click Continue. Single session.
"""
import asyncio, sys, json, os
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

RESUME = r"C:\Users\rejoz\OneDrive\Documents\2026 Resume\AI balanced\Rejo_Z_Mathew_Resume.pdf"
BASE = ("https://fanniemae.wd1.myworkdayjobs.com/en-US/FannieMaeCareers/job/"
        "Reston-VA/Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677")

HOOK = r"""
(function(){
  if (window.__netlog) return 'already';
  window.__netlog = [];
  var log = function(rec){ window.__netlog.push(rec); };
  var of = window.fetch;
  window.fetch = function(input, opts){
    var url = (typeof input==='string') ? input : (input && input.url) || '';
    var rec = {t:'fetch', m:(opts&&opts.method)||'GET', u:url, ts:Date.now(), s:null};
    log(rec);
    var p = of.apply(this, arguments);
    p.then(function(r){ rec.s = r.status; }, function(e){ rec.err = String(e); });
    return p;
  };
  var oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m, u){ this.__m=m; this.__u=u; return oo.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function(){
    var rec = {t:'xhr', m:this.__m, u:this.__u, ts:Date.now(), s:null};
    log(rec);
    var self=this;
    this.addEventListener('loadend', function(){ rec.s = self.status; });
    this.addEventListener('error', function(){ rec.err='net'; });
    return os.apply(this, arguments);
  };
  return 'hooked';
})()
"""

async def main():
    assert os.path.exists(RESUME)
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    sess = page._session

    await page.goto(BASE + "/apply/autofillWithResume")
    await asyncio.sleep(10)

    # Install network hook BEFORE any interaction.
    print("HOOK:", await page.evaluate(HOOK), flush=True)

    # Attach resume.
    doc = await sess.call("DOM.getDocument", {"depth": -1})
    root = doc.get("root", {}).get("nodeId")
    node = await sess.call("DOM.querySelector", {"nodeId": root,
        "selector": "[data-automation-id=file-upload-input-ref], input[type=file]"})
    node_id = node.get("nodeId")
    print("FILE NODE:", node_id, flush=True)
    await sess.call("DOM.setFileInputFiles", {"files": [os.path.abspath(RESUME)], "nodeId": node_id})
    print("ATTACHED at t0", flush=True)

    # Watch the upload + parse requests settle.
    for i in range(12):
        await asyncio.sleep(5)
        log = await page.evaluate("JSON.stringify(window.__netlog||[])")
        body = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ')"))
        uploaded = "uccessfully Uploaded" in body or "successfully uploaded" in body.lower()
        entries = json.loads(log)
        done = all(e.get("s") or e.get("err") for e in entries)
        print(f"poll {i}: entries={len(entries)} settled={done} uploaded={uploaded}", flush=True)
        for e in entries[-6:]:
            print("   ", e.get("t"), e.get("m"), str(e.get("u"))[:110], "status=", e.get("s"), e.get("err",""), flush=True)
        if uploaded and done and i >= 2:
            print("UPLOAD+PARSE SETTLED, proceeding", flush=True)
            break

    # Check button gate state (aria-disabled, react internal disabled).
    gate = await page.evaluate(
        "(function(){var b=document.querySelector('[data-automation-id=pageFooterNextButton]');"
        " return JSON.stringify({dis:b.disabled, ariaDis:b.getAttribute('aria-disabled'),"
        " cls:b.className, type:b.type});})()")
    print("GATE:", gate, flush=True)

    # Click Continue (trusted).
    t = await page.evaluate(
        "(function(){var e=document.querySelector('[data-automation-id=pageFooterNextButton]');"
        " e.scrollIntoView({block:'center'}); var r=e.getBoundingClientRect();"
        " return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)});})()")
    p = json.loads(t)
    await sess.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": p["x"], "y": p["y"]})
    await asyncio.sleep(0.15)
    await sess.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": p["x"], "y": p["y"], "button": "left", "clickCount": 1, "buttons": 1})
    await asyncio.sleep(0.25)
    await sess.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": p["x"], "y": p["y"], "button": "left", "clickCount": 1, "buttons": 0})
    print("CLICKED Continue", flush=True)
    await asyncio.sleep(12)

    url = await page.evaluate("location.href")
    body = (await page.evaluate("(document.body.innerText||'').replace(/\\n+/g,' | ').slice(0,400)"))
    print("URL:", url, flush=True)
    print("BODY:", body, flush=True)
    log = await page.evaluate("JSON.stringify(window.__netlog||[])")
    print("FINAL NETLOG:", log[:1500], flush=True)
    step2 = "current step 2 of 7" in (await page.evaluate("(document.body.innerText||'')"))
    print("STEP2?", step2, flush=True)
    await cdp.close()

asyncio.run(main())
