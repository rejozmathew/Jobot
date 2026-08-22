"""Probe the live Fannie Mae Workday posting (read-only)."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

URL = ("https://fanniemae.wd1.myworkdayjobs.com/FannieMaeCareers/job/Reston-VA/"
       "Senior-Director-of-Modeling-and-Analytics--Platforms--and-Products_JR2677")

async def main():
    sess = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await sess.get_current_page()
    await page.goto(URL)
    await page.evaluate("new Promise(r=>setTimeout(r,4500))", None)
    snap = await page.evaluate(r"""() => {
      const norm = s => (s||'').toLowerCase().replace(/\s+/g,' ').trim();
      const text = norm(document.body ? document.body.innerText : '');
      const btns = Array.from(document.querySelectorAll('button, a[role=button], [data-automation-id]'))
        .map(e => ({t: norm(e.textContent||e.value||e.getAttribute('aria-label')||'').slice(0,40),
                    da: e.getAttribute && e.getAttribute('data-automation-id')}))
        .filter(x => x.t && x.t.length > 1).slice(0, 40);
      const inputs = Array.from(document.querySelectorAll('input, select, textarea'))
        .map(e => (e.getAttribute('name')||e.getAttribute('data-automation-id')||e.type||e.tagName).toString().slice(0,40));
      return {
        url: location.href.slice(0,200), title: document.title.slice(0,120), host: location.host,
        body_head: text.slice(0, 500),
        has_apply: /apply now/i.test(text), has_signin: /sign in|log in/i.test(text),
        has_create: /create account|create my account/i.test(text),
        has_captcha: /captcha|verify you are human|recaptcha/i.test(text),
        already_applied: /already applied|you have already/i.test(text),
        btns, inputs: inputs.slice(0,25)
      };
    }""", None)
    print(json.dumps(snap, indent=2))
    await sess.close()

asyncio.run(main())
