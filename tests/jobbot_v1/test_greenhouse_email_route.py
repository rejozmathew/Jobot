"""Forwarded verification uses synthetic inboxes and isolated browser forms."""
import asyncio
import json
import sys

import pytest

ROUTES={'greenhouse':{'application_email':'personal@example.test',
                      'verification_mailbox':'jobs@example.test'}}


def test_disabling_or_removing_route_restores_default_behavior():
    from job_applier.email_routing import email_route,routed_profile,routed_email_answer
    from job_applier.hermes_gmail import mailbox_handoff
    cfg={'mailbox_provider':'himalaya','himalaya_executable':sys.executable,'himalaya_account':'jobs'}
    baseline=mailbox_handoff(cfg,platform='greenhouse')
    for routes in ({},{'greenhouse':dict(ROUTES['greenhouse'],enabled=False)}):
        disabled=dict(cfg,email_routes=routes)
        route=email_route(disabled,'greenhouse')
        assert route=={}
        profile={'identity':{'email':'default@example.test'}}
        assert routed_profile(profile,route) is profile
        assert routed_email_answer({'kind':'text','field':'email','question':'Email'},route) is None
        assert mailbox_handoff(disabled,platform='greenhouse')==baseline
        assert mailbox_handoff(disabled)==mailbox_handoff(cfg)


def test_route_does_not_replace_an_employees_referral_email():
    from job_applier.email_routing import email_route,routed_email_answer
    route=email_route({'email_routes':ROUTES},'greenhouse')
    assert routed_email_answer({'kind':'text','field':'referrer_email',
        'question':'Email address of the employee who referred you'},route) is None


def test_mailbox_route_keeps_existing_connection():
    from job_applier.hermes_gmail import mailbox_handoff
    cfg={'mailbox_provider':'himalaya','himalaya_executable':sys.executable,
         'himalaya_account':'jobs','email_routes':ROUTES}
    handoff=mailbox_handoff(cfg,platform='greenhouse')
    assert handoff['email_route']['application_email']=='personal@example.test'
    assert handoff['email_route']['verification_mailbox']=='jobs@example.test'
    assert handoff['email_route']['delivery']=='forwarded'
    assert handoff['account']=='jobs'
    assert 'personal mailbox access is not required' in handoff['instruction']
    assert 'email_route' not in mailbox_handoff(cfg,platform='workday')


@pytest.mark.parametrize('platform',['greenhouse','workday'])
def test_context_routes_without_mutating_candidate_or_attempt(tmp_path,platform):
    from test_local_sessions import setup,connect
    s,asset,jobs,_,_=setup(tmp_path)
    session=connect(s,s.reserve_session(request_id='route',job_id=jobs[0]['id'],identity_id='candidate',
        driver_id='fixture',workspace_ids=['workspace-0'],concurrency_limit=1,resume_asset_id=asset['id'],
        metadata={'credential_sources':{'email_routes':ROUTES}}))
    package=s.application_context(session['attempt_id'],platform=platform)
    expected='personal@example.test' if platform=='greenhouse' else 'candidate@example.test'
    assert json.loads(package['attempt']['profile_json'])['identity']['email']==expected
    assert s.candidate('candidate')['email']=='candidate@example.test'
    assert json.loads(s.attempt(session['attempt_id'])['profile_json'])['identity']['email']=='candidate@example.test'
    if platform=='greenhouse':assert package['email_route']['verification_mailbox']=='jobs@example.test'


def test_brief_explains_forwarding_without_personal_mailbox_credentials(tmp_path):
    from test_local_sessions import setup
    from job_applier.application_brief import application_brief
    s,asset,_,_,cfg=setup(tmp_path)
    job=s.intake(url='https://boards.greenhouse.io/example/jobs/123')
    cfg.update(config_path=str(tmp_path/'runtime.json'),email_routes=ROUTES)
    brief=application_brief(cfg,s,{'id':'fixture','job_id':job['id'],
        'identity_id':'candidate','resume_asset_id':asset['id']})
    assert '"application_email": "personal@example.test"' in brief
    assert 'jobs@example.test' in brief
    assert 'personal mailbox access is not required' in brief


@pytest.mark.parametrize('mode',['top','cross'])
def test_autofill_and_reload_keep_route_over_saved_email(tmp_path,monkeypatch,mode):
    import test_embedded_forms as fixture
    from test_greenhouse_batch import batch_html,batch_profile
    from job_applier.greenhouse_fast import GreenhouseRunner
    from job_applier import greenhouse_fast
    # An earlier saved answer must not undo the approved ATS-specific address.
    monkeypatch.setattr(greenhouse_fast,'saved_answer',lambda q,p:'old@example.test' if q['field']=='email' else None)
    panel='''<div class="simplify-jobs-shadow-root"><button type="button" id="fill">Autofill this page</button><p id="status">Need to review (15)</p></div>
<script>fill.onclick=()=>{email.value='old@example.test';for(let i=0;i<14;i++)document.getElementById('f'+i).value='approved-'+i;document.getElementById('status').textContent='Need to review (0)'}</script>'''
    monkeypatch.setattr(fixture,'FORM_HTML',batch_html(simplify=panel))
    async def run():
        async with fixture.fixture_browser(tmp_path,mode=mode) as (page,package,submissions):
            package['attempt'].update(profile_json=batch_profile(),settings_json={'submission_mode':'review'})
            ledger=fixture.SubmissionLedger()
            cfg={'cdp_url':page.fixture_endpoint,'spool_dir':str(tmp_path/'spool'),'email_routes':ROUTES}
            for reload in (False,True):
                if reload:await page.reload()
                runner=GreenhouseRunner(page,ledger.call,package,{'attempt_id':1,'worker_id':'fixture','fence':1},cfg,page.target_id)
                result=await runner.run(30)
                assert result['status']=='ready_for_review',result
                assert await runner.document.evaluate('email.value')=='personal@example.test'
                assert result['email_route']['verification_mailbox']=='jobs@example.test'
            assert package['attempt']['profile_json']['identity']['email']=='fixture@example.test'
            assert submissions==[]
    asyncio.run(run())


def test_submit_uses_routed_email_and_returns_forwarded_verification(tmp_path,monkeypatch):
    import test_embedded_forms as fixture
    from test_greenhouse_batch import batch_html,batch_profile
    from job_applier.greenhouse_fast import GreenhouseRunner
    html=batch_html().replace("await fetch('/fake-submit'", "window.submittedEmail=email.value;await fetch('/fake-submit'")
    html=html.replace('<p>Thank you for applying</p>',
        '<label for="verification">Security code</label><input id="verification" name="security_code" required autocomplete="one-time-code">')
    monkeypatch.setattr(fixture,'FORM_HTML',html)
    async def run():
        async with fixture.fixture_browser(tmp_path,mode='top') as (page,package,submissions):
            package['attempt'].update(profile_json=batch_profile(),settings_json={'submission_mode':'submit'})
            cfg={'cdp_url':page.fixture_endpoint,'spool_dir':str(tmp_path/'spool'),'email_routes':ROUTES}
            ledger=fixture.SubmissionLedger()
            def runner():return GreenhouseRunner(page,ledger.call,package,{'attempt_id':1,'worker_id':'fixture','fence':1},cfg,page.target_id)
            result=await runner().run(30)
            assert result['status']=='application_incomplete',result
            assert await page.evaluate('window.submittedEmail')=='personal@example.test'
            assert result['mailbox']['email_route']['verification_mailbox']=='jobs@example.test'
            assert 'personal mailbox access is not required' in result['mailbox']['instruction']
            assert not ledger.attempt.get('completed_at')
            again=await runner().run(10)
            assert again['status']=='verification_required'
            assert again['mailbox']['email_route']['delivery']=='forwarded'
            assert submissions==['/fake-submit']
    asyncio.run(run())
