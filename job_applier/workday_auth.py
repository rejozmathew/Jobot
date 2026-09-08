"""Bounded Workday account navigation using shared private credentials and ledger."""
import asyncio
import uuid

from .managed_credentials import fill_page_credentials


def result(reason=None,status='authentication_required'):
    return {'status':status,'reason':reason}


def recovery_handoff(reason,observed):
    """A changed site is a possibility, not an inferred fact or a close command."""
    if reason=='workday_verification_required':kind='verification_required'
    elif reason=='workday_credentials_rejected':kind='credentials_rejected'
    elif reason=='account_requires_operator':kind='account_status_requires_operator'
    elif reason and ('credential' in reason or 'coordination' in reason or 'namespace' in reason):kind='credential_or_runtime_configuration'
    elif reason and ('unconfirmed' in reason or 'already_attempted' in reason):kind='account_action_unconfirmed'
    else:kind='unsupported_or_changed_auth_ui'
    return {'kind':kind,'reason':reason,'helper':'workday_auth',
        'observed':{'auth_mode':observed.get('auth_ui',{}).get('mode','unknown'),
                    'native_controls':sorted(observed.get('native',{}))},
        'next_operation':{'operation':'browser','parameters':{'method':'screenshot'}},
        'instruction':'Keep this session open. Inspect the owned screenshot with the current executor image/vision capability and use browser snapshot for fresh selectors. Use supported native controls or settled Simplify for a bounded recovery. Do not repeat an uncertain account action, invent credentials, bypass verification, or edit helpers during this application. Record what differed and the recovery result; resume fast_forward after authentication.'}


def record(r,state,reference,evidence):
    r.owned('record_account_event',namespace=r.package['namespace'],state=state,
        credential_ref=reference,request_id=str(uuid.uuid4()),evidence=evidence)
    r.event('account_verified' if state=='confirmed' else 'phase_changed',{
        'phase':'authentication','activity':evidence,'status':state,'source':'Workday helper'})


async def confirm_authenticated(r,observed):
    state=r.state.get('authentication',{})
    if (state.get('submitted') and not state.get('complete') and not observed.get('auth') and
            observed.get('step') in ('my_information','my_experience','application_questions','voluntary_disclosures','self_identify','review')):
        record(r,'confirmed',state['credential_ref'],'Workday accepted the configured credential and opened the application form')
        state['complete']=True;r.persist()
        r.account_lock(release=True)


async def advance_auth(r,observed):
    """Perform at most one observed account action; callers wait and observe again.

    Counters persist before clicks. Creation pending survives failed applications;
    no password, field value, OTP or mail content enters state or event payloads.
    """
    ui=observed.get('auth_ui',{})
    state=r.state.setdefault('authentication',{})
    if ui.get('account_created') and state.get('submitted')=='create_account' and not state.get('creation_confirmed'):
        record(r,'created_unverified',state['credential_ref'],'Workday confirmed account creation; sign-in or email verification remains')
        state['creation_confirmed']=True;r.persist()
    for flag,reason in (('challenge','workday_verification_required'),('credential_rejected','workday_credentials_rejected'),
                        ('unknown_required_consent','workday_consent_needs_inspection')):
        if ui.get(flag):return result(reason)
    if not r.account_lock:return result('workday_account_coordination_unavailable')
    if not r.config.get('credential_profile_path'):return result('configured_credentials_unavailable')
    gate=await asyncio.to_thread(r.owned,'browser_observe',target_id=r.target,cdp_url=r.config.get('cdp_url'))
    if not gate.get('quiescent'):return result(status='waiting')
    fresh=await r.observe()
    if not fresh.get('auth') or fresh.get('auth_ui')!=ui:return result(status='waiting')
    observed=fresh
    r.account_lock()
    package=r.call('application_context',attempt_id=r.owner['attempt_id'],worker_id=r.owner['worker_id'])
    if not package.get('namespace'):return result('account_namespace_unverified')
    r.package=package
    account=package.get('account') or {}
    if account.get('action')=='operator_required':return result('account_requires_operator')
    tried=state.setdefault('tried',[])
    mode=ui.get('mode')
    if state.get('submitted')==mode:
        if ui.get('account_exists') and mode=='create_account':pass
        elif r.clock()-state.get('submitted_at',r.clock())<5:return result(status='waiting')
        else:return result('workday_'+mode+'_unconfirmed')
    if mode not in ('create_account','sign_in'):return result('workday_auth_controls_unrecognized')
    existing=account.get('action') in ('sign_in','reconcile','verify') or ui.get('account_exists')
    action='auth_submit'
    if mode=='create_account' and existing and not (state.get('submitted')=='create_account' and not ui.get('account_exists')):
        action='auth_switch_sign_in'
    elif mode=='sign_in' and account.get('action')=='unknown' and not state.get('submitted'):
        action='auth_switch_create_account'
    elif mode=='create_account' and observed.get('native',{}).get('auth_consent'):
        action='auth_consent'
    key=mode+':'+action
    if key in tried:return result('workday_auth_action_already_attempted')
    control=observed.get('native',{}).get(action,{})
    if not control.get('ref') or (action!='auth_submit' and not control.get('enabled')):
        return result('workday_'+action+'_unavailable')
    aid=str(uuid.uuid4());started=r.clock();success=False
    r.owned('action_start',action_id=aid,tool_name='workday_auth.'+action)
    try:
        if action=='auth_submit':
            filled=await fill_page_credentials(r.config,package,r.page,observed.get('auth_refs',{}))
            if not filled.get('values_committed'):return result(filled.get('error','credential_values_unconfirmed'))
            observed=await r.observe()
            if observed.get('auth_ui',{}).get('mode')!=mode:return result('workday_auth_page_changed_during_fill')
            if not observed.get('native',{}).get(action,{}).get('enabled'):
                return result('workday_auth_submit_disabled_after_fill')
            state['credential_ref']=filled['credential_ref']
            if mode=='create_account':
                record(r,'creation_pending',filled['credential_ref'],'Creating the Workday account with the retained configured credential; employer confirmation pending')
            state['submitted']=mode;state['submitted_at']=r.clock()
        tried.append(key);r.persist()
        r.event('phase_changed',{'phase':'authentication','activity':{
            'auth_submit':'Submitting Workday '+mode.replace('_',' '),
            'auth_consent':'Accepting the required Workday account privacy/terms checkbox',
            'auth_switch_sign_in':'Opening Sign In for the existing or uncertain account',
            'auth_switch_create_account':'Opening Create Account for this unrecorded portal'}[action],
            'next_step':'Verify the employer response before another account action','source':'Workday helper'})
        success=await r.click('native_'+action,observed)
        return result(status='progress') if success else result('workday_auth_click_unconfirmed')
    finally:
        r.owned('action_end',action_id=aid,status='success' if success else 'failed',duration_seconds=r.clock()-started)
