"""Legacy handlers use the same extension boundary and keep AI recovery available."""
import asyncio
import json

import pytest


def test_legacy_refs_survive_shared_observation(tmp_path, monkeypatch):
    from job_applier import browser_controls, managed_hermes_worker as worker
    from test_form_audit import fixture_html, icims_browser
    import test_embedded_forms as fixture
    monkeypatch.setattr(fixture, 'FORM_HTML', fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page, package, _):
            old = await page.evaluate(worker.INVENTORY)
            email = next(item for item in old['items'] if item.get('type') == 'email')
            observed = await browser_controls.observe(page, package)
            assert observed['inventory']
            result = await page.evaluate(worker.REF, {'ref': email['ref'], 'operation': 'focus'})
            assert result['type'] == 'email'
    asyncio.run(run())


@pytest.mark.parametrize('actor',[False,True])
def test_handler_boundary_runs_bulk_fill_then_returns_fresh_form(tmp_path,monkeypatch,actor):
    from job_applier.platform_handlers.base import BasePlatformHandler
    from test_form_audit import fixture_html,icims_browser
    import test_embedded_forms as fixture
    monkeypatch.setattr(fixture,'FORM_HTML',fixture_html())
    async def run():
        async with icims_browser(tmp_path) as (page,package,_):
            await page.evaluate("window.bulkCount=0;document.querySelector('.simplify-jobs-shadow-root').shadowRoot.querySelector('button').addEventListener('click',()=>{bulkCount++;setTimeout(()=>fixture.setSimplify('needs_review'),250)})")
            class Actor:
                async def evaluate(self,script):
                    return json.dumps(await page.evaluate_function(script,None))
            handler=BasePlatformHandler(browser_session=None,profile={},job_url=package['job']['url'])
            port=Actor() if actor else page
            first=await handler.simplify_before_native(port)
            assert first['execution']=='clicked' and first['native_takeover_authorized'],first
            repeat=await handler.simplify_before_native(port)
            assert repeat['execution']=='not_executed' and repeat['native_takeover_authorized']
            assert await page.evaluate('bulkCount')==1
            handler.settings={'autofill':'native'}
            await page.evaluate('fixture.screening()')
            assert (await handler.simplify_before_native(port))['execution']=='not_executed'
            assert await page.evaluate('bulkCount')==1
    asyncio.run(run())


@pytest.mark.parametrize('recovery',[False,True])
def test_workday_legacy_form_runs_simplify_before_native_helper(monkeypatch,recovery):
    from job_applier.platform_handlers.workday import WorkdayHandler
    from job_applier.platform_handlers.base import HandlerResult
    class Session:
        async def get_current_page(self):return object()
    h=WorkdayHandler(browser_session=Session(),profile={},job_url='https://tenant.myworkdayjobs.com/Jobs/job/Role_R1')
    snap={'url':h.job_url+'/apply','required_empty':1,'has_continue':True}
    events=[]
    async def bulk(page):events.append('autofill');return {'execution':'clicked','native_takeover_authorized':True}
    async def native(*args,**kwargs):events.append('native');return True,'native'
    async def snapshot():return snap
    h.simplify_before_native=bulk;h._snapshot=snapshot;h._state=lambda s:'CONTACT';h._blocked=lambda *a:None
    h.js_fix_referral_source=native;h.js_autofill_required_fields=native;h.el_click=native
    if recovery:
        result=asyncio.run(h.recover({}))
        assert result.result==HandlerResult.PROGRESSED
    else:
        assert asyncio.run(h._action('CONTACT',snap))[0]
    assert events==['autofill']
