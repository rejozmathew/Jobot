"""Fast-path policy regressions; synthetic observations, never live applications."""
import importlib.util
import asyncio
import pytest


def module():
    assert importlib.util.find_spec('job_applier.workday_fast') is not None, 'Workday supervisor must exist'
    from job_applier import workday_fast
    return workday_fast


def snapshot(status='needs_review', step='my_experience', **extra):
    return dict(url='https://tenant.wd1.myworkdayjobs.com/en-US/Jobs/job/City/Role_R1/applyManually',
                status=status, step=step, fingerprint='stable', controls={'continue': {'enabled': True}},
                native={}, blocking_errors=[], auth=False, **extra)


def test_continue_before_review_warning():
    m=module()
    assert m.choose(snapshot(review_count=3), {}) == 'continue'


@pytest.mark.parametrize('status', ['active', 'unknown'])
def test_unknown_or_active_writer_never_advanced(status):
    m=module()
    assert m.choose(snapshot(status), {}) == 'wait'


def test_retry_requires_failed_advancement_and_is_bounded():
    m=module(); s=snapshot(); s['controls']={'autofill': {'enabled':True}}
    assert m.choose(s, {'fills':1, 'advance_failed':True})=='retry'
    assert m.choose(s, {'fills':2, 'advance_failed':True})=='blocked'


def test_auth_not_delegated_to_generated_password():
    m=module(); s=snapshot('ready'); s['auth']=True
    s['controls']={'create_account_autofill': {'enabled':True}}
    assert m.choose(s,{})=='authentication_required'


def test_workday_native_continue_fallback_not_optional_field_audit():
    m=module(); s=snapshot(); s['controls']={}; s['native']={'continue':{'enabled':True}}
    assert m.choose(s,{})=='native_continue'


def test_submit_requires_review_and_not_preexisting_intent():
    m=module(); s=snapshot(step='review'); s['controls']={'submit':{'enabled':True}}
    assert m.choose(s,{})=='submit'
    assert m.choose(s,{'submit_intent':True})=='confirm_only'
    s['step']='my_experience'
    assert m.choose(s,{})!='submit'


def test_disabled_continue_with_actual_blocker_does_not_audit_all_fields():
    m=module(); s=snapshot(); s['controls']={}; s['blocking_errors']=['Required checkbox']
    assert m.choose(s,{})=='blocked'


class Harness:
    def __init__(self, observations, control='running', intent=False):
        self.observations=observations; self.index=0; self.calls=[]; self.clicks=[]; self.now=0
        self.control=control
        self.package={'job':{'url':snapshot()['url'].replace('/applyManually',''), 'requisition_id':'R1'},
                      'attempt':{'submit_intent_at':'set' if intent else None, 'settings_json':{'submission_mode':'submit'}},
                      'documents':{'assets':[]}}
    def call(self, operation, **kwargs):
        self.calls.append((operation,kwargs))
        if operation=='heartbeat': return {'control':self.control}
        if operation=='browser_observe': return {'quiescent':True}
        if operation=='finish': return {'completed_at':'verified','outcome':kwargs['outcome']}
        if operation=='attempt_status': return {'completed_at':'verified','outcome':'applied'}
        return {}
    async def sleep(self, seconds): self.now+=seconds
    async def observe(self): return self.observations[min(self.index,len(self.observations)-1)]
    async def click(self, action, observed):
        self.clicks.append(action); self.index+=1; return True
    def runner(self):
        m=module(); assert hasattr(m,'FastRunner'), 'Bounded runner must exist'
        r=m.FastRunner(None,self.call,self.package,{'attempt_id':1,'worker_id':'worker','fence':1},
                       {'cdp_url':'http://127.0.0.1:9223'},'owned-tab',clock=lambda:self.now,sleeper=self.sleep)
        r.observe=self.observe; r.click=self.click
        return r


def test_runner_advances_without_model_tick_and_preserves_submission_intent(monkeypatch):
    a=snapshot(); b=snapshot(step='review',resume_attached=True); b['controls']={'submit':{'enabled':True}}
    c=snapshot(step='unknown',submitted=True); h=Harness([a,b,c]); r=h.runner()
    async def capture(page,call,package,owner,config,target,activate,**kwargs):
        assert page is r.page and target==r.target and not kwargs.get('confirmation_only')
        call('submission_intent')
        r.last_click_execution='clicked'
        assert (await activate())['clicked']
        call('finish',outcome='applied')
        return {'status':'applied'}
    monkeypatch.setattr('job_applier.submission.submit',capture)
    result=asyncio.run(r.run(seconds=20))
    assert result['status']=='applied'
    assert h.clicks==['continue','submit']
    ops=[x[0] for x in h.calls]
    assert ops.index('submission_intent') < ops.index('finish')
    assert 'attempt_status' in ops and ops.index('attempt_status') > ops.index('finish')
    assert 'action_start' in ops and 'action_end' in ops


def test_runner_stop_performs_no_click_and_only_acks_quiescence():
    h=Harness([snapshot()],control='stop_requested')
    result=asyncio.run(h.runner().run(seconds=20))
    assert h.clicks==[]
    assert result['status']=='stop_requested'
    assert any(op=='ack_control' for op,_ in h.calls)


def test_runner_prior_submit_intent_never_resubmits(monkeypatch):
    s=snapshot(step='review'); s['controls']={'submit':{'enabled':True}}
    h=Harness([s],intent=True)
    async def confirm(page,call,package,owner,config,target,activate,**kwargs):
        assert kwargs['confirmation_only'] is True
        return {'status':'submission_unknown'}
    monkeypatch.setattr('job_applier.submission.submit',confirm)
    result=asyncio.run(h.runner().run(seconds=3))
    assert h.clicks==[]
    assert result['status']=='submission_unknown'


def test_runner_waits_for_writer_and_returns_boundedly():
    h=Harness([snapshot('active')])
    result=asyncio.run(h.runner().run(seconds=3))
    assert h.clicks==[]
    assert result['status']=='waiting'


def test_runner_records_meaningful_step_and_decision_without_poll_spam():
    h=Harness([snapshot('active')]);result=asyncio.run(h.runner().run(seconds=3))
    events=[args for op,args in h.calls if op=='event' and args['event_type']=='phase_changed']
    assert len(events)==1
    assert events[0]['payload']['page']=='my_experience'
    assert events[0]['payload']['activity']=='Waiting for Simplify to settle'
    assert result['status']=='waiting' and not h.clicks


def test_runner_missing_resume_blocks_submit_not_reconstructs_pdf():
    s=snapshot(step='review'); s['controls']={'submit':{'enabled':True}}
    h=Harness([s]); result=asyncio.run(h.runner().run(seconds=4))
    assert h.clicks==[]
    assert result['reason']=='approved_resume_not_observed'


def test_runner_accepts_real_simplify_click_protocol():
    class Page:
        async def evaluate_function(self,script,args):return {'status':'clicked'}
    h=Harness([snapshot()]);r=h.runner();r.page=Page()
    s=snapshot();s['controls']['continue']['ref']='observed-ref'
    assert asyncio.run(module().FastRunner.click(r,'continue',s)) is True


def test_candidate_home_controls_never_authorize_writes():
    m=module();s=snapshot(confirmation_surface=True)
    assert m.choose(s,{})=='confirm_only'


def test_pending_advancement_survives_a_bounded_call():
    h=Harness([snapshot()]);r=h.runner()
    asyncio.run(r.run(seconds=1))
    assert h.clicks==['continue']
    assert r.state.get('pending')==['my_experience','continue']
    r2=h.runner();r2.state=r.state;r2.pending=tuple(r.state['pending']);r2.last_action=h.now
    asyncio.run(r2.run(seconds=8))
    assert h.clicks==['continue']


def test_residual_repair_allows_one_more_advancement_without_resetting_retry_budget():
    h=Harness([snapshot()]);r=h.runner()
    r.state['pages']['my_experience']={'advance_failed':True,'failure_fingerprint':'old','fills':2}
    asyncio.run(r.run(seconds=1))
    assert h.clicks==['continue']
    assert r.state['pages']['my_experience']['fills']==2


@pytest.mark.parametrize('extra',[{'blocking_errors':['Required answer']},{'identity_mismatch':True}])
def test_submit_checks_observed_blockers_and_fresh_identity(extra):
    s=snapshot(step='review');s.update(extra);s['controls']={'submit':{'enabled':True}}
    assert module().choose(s,{})=='blocked'


def test_unknown_extension_state_surfaces_native_auth_without_authorizing_writes():
    s=snapshot('unknown');s['auth']=True
    assert module().choose(s,{})=='authentication_required'
    s['status']='active'
    assert module().choose(s,{})=='wait'


def test_fast_navigation_emits_one_verified_step_change():
    a=snapshot();b=snapshot(step='review',resume_attached=True);b['controls']={'submit':{'enabled':True}}
    c=snapshot(step='unknown',submitted=True);h=Harness([a,b,c])
    asyncio.run(h.runner().run(seconds=20))
    events=[kw for op,kw in h.calls if op=='event' and kw['event_type']=='navigation_verified']
    assert len(events)==1 and events[0]['payload']['page']=='review'
