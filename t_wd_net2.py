"""Hook window.fetch + XHR in-page, click Continue, then read the captured
request log to see what the click triggers (and any failed requests).
"""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

HOOK = r"""
(function(){
  if (window.__netlog) return 'already';
  window.__netlog = [];
  var of = window.fetch;
  window.fetch = function(input, opts){
    var url = (typeof input==='string') ? input : (input && input.url) || '';
    var rec = {t:'fetch', m:(opts&&opts.method)||'GET', u:url, ts:Date.now()};
    window.__netlog.push(rec);
    var p = of.apply(this, arguments);
    p.then(function(r){ rec.s = r.status; }, function(e){ rec.err = String(e); });
    return p;
  };
  var oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m, u){ this.__m=m; this.__u=u; return oo.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function(){
    var rec = {t:'xhr', m:this.__m, u:this.__u, ts:Date.now()};
    window.__netlog.push(rec);
    this.addEventListener('loadend', function(){ rec.s = this.status; });
    this.addEventListener('error', function(){ rec.err='net'; });
    return os.apply(this, arguments);
  };
  return 'hooked';
})()
"""

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    sess = page._session

    print("HOOK:", await page.evaluate(HOOK), flush=True)

    c2 = await page.evaluate(
        "(function(){var b=document.querySelector('[data-automation-id=pageFooterNextButton]');"
        " b.scrollIntoView({block:'center'}); var r=b.getBoundingClientRect();"
        " return JSON.stringify({cx:Math.round(r.x+r.width/2), cy:Math.round(r.y+r.height/2)});})()")
    c2 = json.loads(c2)
    await sess.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": c2["cx"], "y": c2["cy"]})
    await asyncio.sleep(0.15)
    await sess.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": c2["cx"], "y": c2["cy"], "button": "left", "clickCount": 1, "buttons": 1})
    await asyncio.sleep(0.2)
    await sess.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": c2["cx"], "y": c2["cy"], "button": "left", "clickCount": 1, "buttons": 0})
    print("CLICKED, waiting 10s...", flush=True)
    await asyncio.sleep(10)

    log = await page.evaluate("JSON.stringify(window.__netlog||[], null, 1)")
    print("NETLOG:", log, flush=True)
    url = await page.evaluate("location.href")
    print("URL:", url, flush=True)
    await cdp.close()

asyncio.run(main())
