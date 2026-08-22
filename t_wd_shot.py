"""Capture a full-page screenshot of the current My Information form via CDP."""
import asyncio, sys, json, base64
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser
import urllib.request

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    # Make sure the form is scrolled to top and no listbox is open
    await page.evaluate("window.scrollTo(0,0)")
    await asyncio.sleep(0.3)
    try:
        await page.evaluate("document.activeElement && document.activeElement.blur()")
    except: pass
    await asyncio.sleep(0.3)

    # Use CDP directly to capture a full-page PNG
    session = page._session
    # Get metrics
    metrics = await session.call("Page.getLayoutMetrics")
    css = metrics.get("cssContentSize") or metrics.get("contentSize")
    width = int(css.get("width", 1200)); height = int(css.get("height", 1700))
    # Override device metrics to full page height
    await session.call("Emulation.setDeviceMetricsOverride",
                       {"width": 1280, "height": min(height, 4000), "deviceScaleFactor": 1, "mobile": False})
    await asyncio.sleep(0.4)
    shot = await session.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
    b64 = shot.get("data", "")
    out = "C:/GitClone/auto-job-applier/artifacts/wd_myinfo_filled.png"
    with open(out, "wb") as f:
        f.write(base64.b64decode(b64))
    # reset metrics
    await session.call("Emulation.clearDeviceMetricsOverride")
    print("SAVED:", out, "size", width, "x", height)
    await cdp.close()

asyncio.run(main())
