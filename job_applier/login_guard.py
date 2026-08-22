"""Login-wait guard.

Detects a sign-in wall on the automation browser, waits (polling) until a
human completes auth in the visible window, then confirms the session is
live so the deterministic handler can proceed.

Exit codes:
    0  already authed, or auth completed within timeout
    2  login wall still present after timeout
    3  CDP browser unreachable

Usage:
    python -m job_applier.login_guard --url <job_or_tenant_url> [--timeout 600]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

WALL_DETECT_JS = r"""
() => {
  const t = (document.title || '').toLowerCase();
  const u = location.href || '';
  const bodyText = ((document.body && document.body.innerText) || '').toLowerCase();
  const hasPw = !!document.querySelector('input[type="password"]');
  const urlLogin = /\/(login|signin|sign-in|log-in|logon|log-on|auth|security|sso)(\/|$|\?)/i.test(u);
  const signInCue = /(sign in|log in|log on|create account|sign up|one-?time passcode)/.test(bodyText)
                    || /(sign in|log in|log on|create account)/.test(t);
  const wall = hasPw || (urlLogin && signInCue) || (hasPw && signInCue);
  return { url: u, title: (document.title||'').slice(0,120), hasPw, urlLogin, signInCue, wall };
}
"""

AUTH_OK_JS = r"""
() => {
  const u = location.href || '';
  const hasPw = !!document.querySelector('input[type="password"]');
  const urlLogin = /\/(login|signin|sign-in|log-in|logon|log-on|auth|security|sso)(\/|$|\?)/i.test(u);
  return { authed: !hasPw && !urlLogin, url: u, hasPw, urlLogin };
}
"""


def _print(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


async def _run(url: str, timeout_s: int) -> int:
    from .cdp_client import CDPBrowser

    cdp_url = os.environ.get("BROWSER_USE_CDP_URL", "").strip() or "http://127.0.0.1:9222"

    try:
        # Reuse the existing automation tab (about:blank). create_new=True
        # uses /json/new which this Brave build only allows via PUT; we don't
        # need a new tab, so connect to the current page.
        browser = await CDPBrowser.connect(cdp_url)
    except Exception as e:
        _print({"event": "cdp_unreachable", "cdp_url": cdp_url, "error": str(e)[:200]})
        return 3

    page = await browser.get_current_page()

    try:
        await page.goto(url)
    except Exception as e:
        _print({"event": "goto_failed", "url": url, "error": str(e)[:200]})
        return 3

    await asyncio.sleep(2.5)  # let redirects (auth bounce) settle

    state = await page.evaluate(WALL_DETECT_JS)
    state["event"] = "wall" if state.get("wall") else "clean"
    _print(state)

    if not state.get("wall"):
        await browser.stop()
        return 0

    deadline = time.monotonic() + timeout_s
    poll_every = 4
    last_url = state.get("url", "")
    while time.monotonic() < deadline:
        await asyncio.sleep(poll_every)
        try:
            cur = await page.evaluate(AUTH_OK_JS)
        except Exception:
            continue
        if cur.get("authed"):
            _print({"event": "auth_ok", "url": cur.get("url", ""),
                    "waited_s": int(time.monotonic() - (deadline - timeout_s))})
            await browser.stop()
            return 0
        if cur.get("url", "") != last_url:
            last_url = cur.get("url", "")
            _print({"event": "url_changed", "url": last_url,
                    "remaining_s": int(max(0, deadline - time.monotonic()))})

    _print({"event": "login_timeout", "url": last_url, "timeout_s": timeout_s})
    await browser.stop()
    return 2


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", required=True, help="Job URL (or tenant login page) to probe")
    p.add_argument("--timeout", type=int,
                   default=int(os.environ.get("JOB_APPLIER_LOGIN_WAIT", "600")),
                   help="Seconds to wait for human auth (default 600)")
    args = p.parse_args()
    return asyncio.run(_run(args.url, args.timeout))


if __name__ == "__main__":
    sys.exit(main())
