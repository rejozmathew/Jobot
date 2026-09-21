"""Enrich stored navigator routes from a new owned tab; never open application forms.

Uses the bridge's selected config and protected environment, plus the existing
JobBot browser. Navigation/DOM reads stay on the created target. Application
execution always has priority; a new active session ends this enrichment slice.
"""
import argparse
import asyncio
from contextlib import suppress
import json
from pathlib import Path
import sqlite3
import sys
import time
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen


def destination(href):
    """Decode observed LinkedIn wrappers and the observed DoubleClick URL query."""
    for _ in range(4):
        p = urlsplit(href)
        host = (p.hostname or '').lower()
        if host == 'linkedin.com' or host.endswith('.linkedin.com'):
            nested = parse_qs(p.query).get('url', [])
            if not nested:
                return None
            href = nested[0]
        elif host == 'doubleclick.net' or host.endswith('.doubleclick.net'):
            nested = unquote(p.query)
            if not nested.startswith(('https://', 'http://')):
                return None
            href = nested
        else:
            return href if p.scheme in ('https', 'http') and p.hostname and not p.username and not p.password else None
    return None


OBSERVE = """JSON.stringify({url:location.href,title:document.title,
 controls:[...document.querySelectorAll('button,a')].filter(e => {
 const r=e.getBoundingClientRect();return r.width&&r.height&&
 /^(easy apply|apply)$/i.test(e.innerText.trim())&&e.getAttribute('aria-disabled')!=='true'
 }).map(e=>({text:e.innerText.trim(),href:e.href||null,label:e.getAttribute('aria-label')}))})"""


def classify(observed, expected_id):
    import re
    parsed = urlsplit(observed.get('url', ''))
    host = parsed.hostname or ''
    if host != 'linkedin.com' and not host.endswith('.linkedin.com'):
        return None
    path = parsed.path
    if not re.fullmatch(r'/jobs/view/(?:[^/]*-)?' + re.escape(expected_id) + r'/?', path):
        return None
    controls = observed.get('controls', [])
    if any(c.get('text', '').lower() == 'easy apply' for c in controls):
        return {'application_type': 'linkedin_easy_apply', 'application_url': None}
    urls = {destination(c['href']) for c in controls if c.get('href')}
    urls.discard(None)
    if len(urls) == 1:
        return {'application_type': 'external', 'application_url': urls.pop()}
    return None


def route_priority(source_id, fit_status, seen):
    """Inspect new matching roles first; rotate failed reads behind unseen rows."""
    return (source_id in seen, fit_status != 'eligible', seen.get(source_id, 0))


async def enrich(args):
    sys.path.insert(0, args.bridge_root)
    from jobnavigator_bridge.config import Config, Preferences
    from jobnavigator_bridge.selection import select
    from jobnavigator_bridge.lock import ProcessLock
    import os
    cfg = Config.load(args.config)
    sys.path.insert(0, cfg.jobbot_checkout)
    from job_applier.cdp_client import CDPBrowser
    from job_applier.workspace_host import browser_command
    from job_applier.queue_runtime import private_write
    runtime = json.loads(Path(cfg.jobbot_config).read_text())
    jobdb = sqlite3.connect(Path(runtime['db_path']).as_uri() + '?mode=ro', uri=True)
    bridge = sqlite3.connect(Path(cfg.state_database).as_uri() + '?mode=ro', uri=True)
    bridge.row_factory = sqlite3.Row
    progress = Path(cfg.state_database).with_name('route-enrichment.json')
    seen = json.loads(progress.read_text()) if progress.exists() else {}
    prefs = Preferences.load(cfg.profile_path)
    pending = []
    fit_status = {}
    for row in bridge.execute("SELECT source_id,snapshot FROM records WHERE present=1 AND reason IN ('awaiting_application_type','awaiting_external_url_resolution')"):
        job = json.loads(row['snapshot'])
        fit = select(job, cfg, prefs, availability=('unknown','availability_unverified'))
        if fit.status in ('excluded', 'rejected', 'unavailable'):
            continue
        pending.append((row['source_id'],job))
        fit_status[row['source_id']] = fit.status
    pending.sort(key=lambda entry: route_priority(entry[0], fit_status[entry[0]], seen))
    workspace = next(w for w in runtime['workspaces'] if w.get('cdp_url'))
    base = workspace['cdp_url'].rstrip('/')
    counts = {'pending': len(pending), 'inspected': 0, 'resolved': 0, 'unresolved': 0, 'errors': 0}
    active = lambda: jobdb.execute('SELECT 1 FROM application_sessions WHERE ended_at IS NULL').fetchone() or jobdb.execute("SELECT 1 FROM dispatch_queue WHERE state='dispatched'").fetchone()
    if active():
        return dict(counts, state='application_active')
    # This lock belongs only to route enrichment, never to application execution.
    with ProcessLock(str(progress)):
        for source_id, job in pending[:args.limit]:
            if active():
                break
            import re
            source_url = job.get('source_url') or job['url']
            match = re.search(r'/jobs/view/(?:[^/]*-)?(\d+)', source_url)
            if not match:
                continue
            host = urlsplit(source_url).hostname or ''
            if host != 'linkedin.com' and not host.endswith('.linkedin.com'):
                continue
            target = None
            browser = None
            try:
                # Create our own target; never select or navigate an existing tab.
                target = (await browser_command(base, 'Target.createTarget',
                    {'url':'about:blank','background':True}))['targetId']
                browser = await CDPBrowser.connect(base, target_id=target)
                page = await browser.get_current_page()
                await page.goto(source_url)
                route = None
                for _ in range(8):
                    await asyncio.sleep(1)
                    if active():
                        break
                    observed = json.loads(await page.evaluate(OBSERVE))
                    route = classify(observed, match[1])
                    if route:
                        break
                counts['inspected'] += 1
                seen[source_id] = time.time()
                if route:
                    payload = dict(route, linkedin_job_id=match[1], evidence_source='jobbot_owned_browser_apply_control')
                    request = Request(cfg.jobnavigator_base_url.rstrip('/')+'/api/jobs/'+job['id']+'/application-route',
                                      data=json.dumps(payload).encode(),method='POST',headers={
                                          'Content-Type':'application/json','X-API-Key':os.environ[cfg.jobnavigator_api_key_env]})
                    with urlopen(request,timeout=20) as response:
                        result=json.load(response)
                    counts['resolved'] += result.get('resolution_status') in ('resolved','not_required')
                else:
                    counts['unresolved'] += 1
            except Exception:
                # One unavailable posting must not starve the remaining backlog.
                # Rotate it to a later pass; never store private page/error text.
                counts['errors'] += 1
                seen[source_id] = time.time()
            finally:
                if browser:
                    with suppress(Exception):
                        await browser.close()
                if target:
                    with suppress(Exception):
                        with urlopen(base+'/json/close/'+target,timeout=5):
                            pass
                private_write(progress,json.dumps(seen))
    jobdb.close()
    bridge.close()
    return dict(counts,state='completed')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--bridge-root',default='/opt/jobnavigator-bridge')
    parser.add_argument('--limit',type=int,default=10)
    args=parser.parse_args()
    try:
        print(json.dumps(asyncio.run(enrich(args))))
    except Exception as exc:
        print(json.dumps({'error':type(exc).__name__}))
        raise SystemExit(1)
