"""Capture network activity around a Continue click to see what fires / fails."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

events = []

async def on_message(msg):
    # CDP events arrive as {'method':..., 'params':...}
    m = msg.get("method") if isinstance(msg, dict) else None
    if m in ("Network.requestWillBeSent", "Network.responseReceived",
             "Network.loadingFailed", "Log.entryAdded"):
        events.append((m, msg.get("params", {})))

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    sess = page._session

    await sess.enable("Network")
    await sess.enable("Log")
    if hasattr(sess, "on_message"):
        sess.on_message(on_message)

    # Click Continue (trusted)
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
    print("CLICKED, waiting 10s for network...", flush=True)
    await asyncio.sleep(10)

    url = await page.evaluate("location.href")
    print("URL:", url, flush=True)

    print(f"\n=== {len(events)} network/log events ===")
    for m, p in events[:40]:
        if m == "Network.requestWillBeSent":
            print("REQ", p.get("request", {}).get("method"), p.get("request", {}).get("url", "")[:140], flush=True)
        elif m == "Network.responseReceived":
            print("RES", p.get("response", {}).get("status"), p.get("response", {}).get("url", "")[:140], flush=True)
        elif m == "Network.loadingFailed":
            print("FAIL", p.get("errorText"), p.get("requestId", "")[:40], flush=True)
        elif m == "Log.entryAdded":
            e = p.get("entry", {})
            print("LOG", e.get("level"), (e.get("url", "") or "")[:100], e.get("text", "")[:200], flush=True)
    await cdp.close()

asyncio.run(main())
