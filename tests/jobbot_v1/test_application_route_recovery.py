"""Shared route continuity: synthetic postings only, no employer traffic."""
import asyncio
import json

import pytest

from job_applier import managed_identity as identity
from test_apply_target_handoff import connected


API = 'https://boards-api.greenhouse.io/v1/boards/example/jobs/123'
FORM = 'https://job-boards.greenhouse.io/example/jobs/123'
WORKDAY = 'https://example.wd1.myworkdayjobs.com/en-US/Careers/job/Remote/Director_R123/apply'


def test_greenhouse_api_and_form_share_exact_board_and_posting():
    assert identity.ats_posting_key(API) == identity.ats_posting_key(FORM)
    assert identity.is_same_application_scope(API, FORM)
    assert not identity.is_same_application_scope(API, FORM.replace('/123', '/124'))
    assert not identity.is_same_application_scope(API, FORM.replace('/example/', '/other/'))


def test_api_startup_url_is_a_form_without_rewriting_original_url():
    assert identity.application_start_url(API) == FORM
    ordinary = 'https://careers.example.test/job/123?opaque=keep'
    assert identity.application_start_url(ordinary) == ordinary


def test_accepted_route_survives_context_refresh_and_account_events(tmp_path):
    service, session, owner, _ = connected(tmp_path)
    service.handoff_target(**owner, current_target_id='linkedin', new_target_id='workday',
                          url=WORKDAY, expected_url=WORKDAY, evidence='Synthetic owned Apply')
    package = service.application_context(owner['attempt_id'], worker_id=owner['worker_id'])
    assert package['job']['url'] == WORKDAY
    assert package['job']['posting_url'].startswith('https://www.linkedin.com/')
    assert package['namespace'] == 'example.wd1.myworkdayjobs.com'
    service.record_account_event(**owner, namespace=package['namespace'], state='confirmed',
        credential_ref='credential:profile/accounts/default', request_id='confirmed',
        evidence='Synthetic employer opened authenticated application')
    refreshed = service.application_context(owner['attempt_id'], worker_id=owner['worker_id'])
    assert refreshed['job']['url'] == WORKDAY
    assert refreshed['account']['action'] == 'sign_in'
    # ATS runners rebind their existing owned target after refreshing context.
    assert service.bind_target(**owner,target_id='workday',url=refreshed['job']['url'])['target_id']=='workday'
    assert service.job(session['job_id'])['url'].startswith('https://www.linkedin.com/')


def test_network_navigation_tracks_only_owned_main_document_chain():
    from job_applier.cdp_client import NavigationTrace
    trace = NavigationTrace('main', 'https://careers.example.test/jobs/123')
    trace.request({'type': 'Document', 'frameId': 'child', 'requestId': 'x',
                   'request': {'url': 'https://unrelated.test/'}})
    assert not trace.accepts('https://unrelated.test/')
    trace.request({'type': 'Document', 'frameId': 'main', 'requestId': 'one',
                   'request': {'url': 'https://careers.example.test/apply/123'}})
    trace.request({'type': 'Document', 'frameId': 'main', 'requestId': 'one',
                   'redirectResponse': {'url': 'https://careers.example.test/apply/123'},
                   'request': {'url': FORM}})
    assert trace.accepts(FORM)
    assert not trace.accepts(FORM.replace('/123', '/999'))


def test_observed_redirect_can_transfer_scope_without_trusting_arbitrary_url(tmp_path):
    service, _, owner, _ = connected(tmp_path)
    source = service.application_context(owner['attempt_id'])['job']['url']
    service.handoff_target(**owner, current_target_id='linkedin', new_target_id='linkedin',
        source_url=source, url=FORM, navigation_chain=[source, FORM],
        evidence='Host observed owned main document Apply redirect')
    assert service.application_context(owner['attempt_id'])['job']['url'] == FORM


def test_redirect_rejects_conflicting_same_portal_requisition(tmp_path):
    from job_applier.managed_shared import ProtocolError
    service, _, owner, _ = connected(tmp_path)
    service.handoff_target(**owner, current_target_id='linkedin', new_target_id='linkedin',
        url=FORM, expected_url=FORM, evidence='Synthetic accepted destination')
    other = FORM.replace('/123', '/999')
    with pytest.raises(ProtocolError, match='target_job_mismatch'):
        service.handoff_target(**owner, current_target_id='linkedin', new_target_id='linkedin',
            source_url=FORM, url=other, navigation_chain=[FORM, other],
            evidence='Synthetic wrong posting navigation')


def test_new_workday_account_starts_from_sign_in_then_creates(tmp_path,monkeypatch):
    from test_workday_credentials import AuthHarness
    from job_applier import workday_auth
    h=AuthHarness(tmp_path)
    h.observation=h.auth('sign_in')
    assert asyncio.run(workday_auth.advance_auth(h.runner,h.observation))['status']=='progress'
    assert h.clicks==['native_auth_switch_create_account']
    h.observation=h.auth('create_account')
    async def fill(*args):return {'values_committed':True,'credential_ref':'credential:profile/accounts/default'}
    monkeypatch.setattr(workday_auth,'fill_page_credentials',fill)
    assert asyncio.run(workday_auth.advance_auth(h.runner,h.observation))['status']=='progress'
    assert h.clicks[-1]=='native_auth_submit'


def test_explicit_absent_account_reconciles_pending_creation(tmp_path):
    from test_workday_credentials import AuthHarness
    from job_applier import workday_auth
    h=AuthHarness(tmp_path,'reconcile')
    h.package['account'].update(state='creation_pending',credential_ref='credential:profile/accounts/default')
    h.observation=h.auth('sign_in')
    h.observation['auth_ui'].update(account_absent=True,credential_rejected=True)
    # Model the authoritative account strategy after the new recorded outcome.
    original=h.runner.call
    def call(op,**kw):
        if op=='record_account_event' and kw['state']=='account_absent':
            h.calls.append((op,kw));h.package['account'].update(state='account_absent',action='create_account')
            return {}
        return original(op,**kw)
    h.runner.call=call
    assert asyncio.run(workday_auth.advance_auth(h.runner,h.observation))['status']=='progress'
    assert h.clicks==['native_auth_switch_create_account']
    assert any(op=='record_account_event' and kw['state']=='account_absent' for op,kw in h.calls)


def test_ambiguous_rejection_does_not_infer_account_absent(tmp_path):
    from test_workday_credentials import AuthHarness
    from job_applier import workday_auth
    h=AuthHarness(tmp_path,'reconcile')
    h.package['account'].update(state='creation_pending',credential_ref='credential:profile/accounts/default')
    h.observation=h.auth('sign_in');h.observation['auth_ui']['credential_rejected']=True
    assert asyncio.run(workday_auth.advance_auth(h.runner,h.observation))['reason']=='workday_credentials_rejected'
    assert h.package['account']['state']=='creation_pending'
    assert not h.clicks


def test_auth_absence_requires_current_form_error_not_job_description():
    from test_workday_dom import observe
    form='<form><input type="email"><input type="password"><button>Sign In</button>{}</form>'
    assert observe(form.format('<div role="alert">No account found for this email</div>'))['auth_ui']['account_absent']
    assert not observe('<p>No account found</p>'+form.format(''))['auth_ui']['account_absent']
    assert not observe(form.format('<div role="alert">Invalid email or password</div>'))['auth_ui']['account_absent']


def test_persistent_creation_rejection_is_recorded_once_without_replaying(tmp_path):
    from test_workday_credentials import AuthHarness
    from job_applier import workday_auth
    h=AuthHarness(tmp_path,'reconcile')
    h.package['account'].update(state='creation_pending',credential_ref='credential:profile/accounts/default')
    h.observation=h.auth('create_account');h.observation['auth_ui'].update(creation_rejected=True,credential_rejected=True)
    original=h.runner.call
    def call(op,**kw):
        if op=='record_account_event' and kw['state']=='creation_rejected':
            h.calls.append((op,kw));h.package['account'].update(state='creation_rejected',action='create_account');return {}
        return original(op,**kw)
    h.runner.call=call
    for _ in range(3):
        assert asyncio.run(workday_auth.advance_auth(h.runner,h.observation))['reason']=='workday_account_creation_rejected'
    assert len([kw for op,kw in h.calls if op=='record_account_event'])==1
    assert not h.clicks


def test_cached_frame_router_uses_fresh_verified_route():
    from job_applier.browser_frames import router_for
    class Page:pass
    page=Page();original={'job':{'url':'https://example.test/jobs/1'}}
    router=asyncio.run(router_for(page,original))
    updated={'job':{'url':FORM,'posting_url':original['job']['url']}}
    assert asyncio.run(router_for(page,updated)) is router
    assert router.package is updated


def test_real_cdp_tracks_redirect_and_spa_navigation_in_owned_main_frame(tmp_path):
    from test_embedded_forms import fixture_browser
    from job_applier.cdp_client import NavigationTrace
    import base64
    async def check():
        async with fixture_browser(tmp_path,'top') as (page,_,__):
            source='https://careers.example.test/jobs/123'
            redirect='https://careers.example.test/apply/123'
            destination='https://applications.example.test/jobs/123'
            pending=set()
            async def fulfill(event):
                url=event['request']['url'];headers=[];code=200
                if url==redirect:code=302;headers=[{'name':'Location','value':destination}]
                await page._session.call('Fetch.fulfillRequest',{'requestId':event['requestId'],
                    'responseCode':code,'responseHeaders':headers,
                    'body':base64.b64encode(b'<html><body>Synthetic application</body></html>').decode()})
            def paused(event):
                task=asyncio.create_task(fulfill(event));pending.add(task);task.add_done_callback(pending.discard)
            remove=page._session.subscribe('Fetch.requestPaused',paused)
            # Fulfill every request locally: no external website is contacted.
            await page._session.call('Fetch.enable',{'patterns':[{'urlPattern':'*'}]})
            trace=None
            try:
                await page.goto(source)
                for _ in range(100):
                    if await page.evaluate('location.href')==source:break
                    await asyncio.sleep(.02)
                trace=await NavigationTrace.start(page,source)
                await page.evaluate('location.href='+json.dumps(redirect))
                for _ in range(150):
                    if await page.evaluate('location.href')==destination:break
                    await asyncio.sleep(.02)
                assert trace.accepts(destination) and redirect in trace.chain
                await page.evaluate("history.pushState({},'', '/jobs/123/apply')")
                await asyncio.sleep(.05)
                assert trace.accepts(destination+'/apply')
            finally:
                if trace:trace.close()
                if pending:await asyncio.gather(*pending)
                await page._session.call('Fetch.disable');remove()
    asyncio.run(check())
