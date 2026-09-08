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
        'instruction':'Keep this session open. Use the returned combined screen inventory to map the whole logical screen once, then pass recovery to fast_forward. Its mapped private fill/action is authoritative and does not rerun the failed matcher. Inspect an owned screenshot only for remaining ambiguity. Use native sign-in with retained credentials, or Simplify employer sign-in only when its credential use is established. A helper recognition miss is not an employer blocker. Do not repeat an uncertain account action or edit helpers during this application.'}


async def recover_screen(r,mapping):
    """Execute one current-screen mapping in the existing owned runner connection."""
    from .workday_fast import screen_inventory,WORKDAY_CLICK
    from .simplify_boundary import SimplifyBoundary
    def stopped(reason,execution='not_executed'):
        return {'status':'inspection_required','reason':reason,'execution':execution}
    if not isinstance(mapping,dict) or set(mapping)-{'screen_key','credentials','fields','action','account_mode','credential_evidence'}:
        return stopped('invalid_screen_mapping')
    gate=await asyncio.to_thread(r.owned,'browser_observe',target_id=r.target,cdp_url=r.config.get('cdp_url'))
    observed=await r.observe();screen=screen_inventory(observed,r.package)
    if not gate.get('quiescent'):return stopped('writer_activity_unconfirmed_observe_only')
    if mapping.get('screen_key')!=screen['screen_key']:return stopped('new_screen_evidence_requires_mapping')
    key=screen['screen_key'];steps=r.state.setdefault('recovery_steps',{})
    if key in steps:return stopped('screen_action_already_attempted',steps[key])
    if r.state.get('submit_intent') or observed.get('confirmation_surface'):
        return stopped('submission_observation_only')
    action=mapping.get('action') or {};source=action.get('source');ref=action.get('ref')
    candidates=screen['native'] if source=='native' else screen['simplify']['controls'] if source=='simplify' else []
    matches=[c for c in candidates if c.get('ref')==ref]
    if len(matches)!=1:return stopped('mapped_action_unavailable')
    control=matches[0]
    if 'submit' in (control.get('text','')+' '+control.get('label','')+' '+control.get('operation','')).lower():
        return stopped('use_existing_final_submission_boundary')
    if observed.get('identity_mismatch'):return stopped('candidate_email_mismatch')
    ui=observed.get('auth_ui') or {}
    if ui.get('challenge'):return stopped('workday_verification_required')
    fields=mapping.get('fields') or [];credentials=mapping.get('credentials');mode=mapping.get('account_mode')
    if not isinstance(fields,list) or len(fields)>30 or any(not isinstance(f,dict) or set(f)!={'ref','value'} for f in fields):
        return stopped('invalid_mapped_fields')
    if credentials is not None and (not isinstance(credentials,dict) or set(credentials)-{'email_ref','password_ref','confirmation_ref'}):
        return stopped('invalid_mapped_credentials')
    if credentials is not None and mode not in ('sign_in','create_account'):return stopped('mapped_account_mode_required')
    if mode and not credentials:return stopped('mapped_private_credentials_required')
    if credentials and ui.get('credential_rejected'):return stopped('workday_credentials_rejected')
    if source=='simplify':
        if r.settings.get('autofill','simplify')!='simplify':return stopped('simplify_disabled_by_configuration')
        if control.get('operation') not in ('autofill','continue','start','sign_in'):return stopped('use_observed_browser_control')
        if control.get('operation')=='sign_in' and (not credentials or not mapping.get('credential_evidence') or screen['simplify']['login_kind']!='employer'):
            return stopped('retained_credential_use_unverified')
    if observed.get('auth'):
        if not r.account_lock:return stopped('workday_account_coordination_unavailable')
        r.account_lock()
        r.package=r.call('application_context',attempt_id=r.owner['attempt_id'],worker_id=r.owner['worker_id'])
        account=r.package.get('account') or {}
        if account.get('action')=='operator_required':return stopped('account_requires_operator')
        if mode=='create_account' and account.get('action') in ('sign_in','reconcile','verify'):
            return stopped('reconcile_existing_account_before_creation')
    if fields:
        validation=await r.page.evaluate_function(WORKDAY_CLICK,{'step':observed['step'],'page_signature':observed['page_signature'],
            'ref':ref if source=='native' else None,'fields':fields,'validate_only':True})
        if not validation.get('validated'):return stopped(validation.get('reason','mapped_fields_unavailable'))
    aid=str(uuid.uuid4());started=r.clock();success=False;execution='not_executed'
    r.owned('action_start',action_id=aid,tool_name='workday_recovery.screen')
    r.state['page_decisions']=r.state.get('page_decisions',0)+1
    r.event('recovery',{'phase':observed.get('step','unknown'),'activity':'Executing one mapped screen decision',
        'next_step':'Private fill, verify, act and observe; resume routine Simplify','source':'Hermes executor'})
    previous_auth=dict(r.state.get('authentication',{}))
    try:
        if credentials is not None:
            filled=await fill_page_credentials(r.config,r.package,r.page,credentials)
            if not filled.get('values_committed'):return stopped(filled.get('error','mapped_credentials_unconfirmed'),'fields_may_have_changed')
            execution='fields_written'
        if fields:
            filled_fields=await r.page.evaluate_function(WORKDAY_CLICK,{'step':observed['step'],'page_signature':observed['page_signature'],
                'fields':fields,'fill_only':True})
            if not filled_fields.get('values_committed'):return stopped(filled_fields.get('reason','mapped_values_unconfirmed'),'fields_may_have_changed')
            execution='fields_written'
        fresh=await r.observe()
        if fresh.get('page_signature')!=observed.get('page_signature') or fresh.get('status')=='active':
            return result(status='progress')
        if mode and mode==ui.get('mode'):
            state=r.state.setdefault('authentication',{})
            state.update(credential_ref=filled['credential_ref'],submitted=mode,submitted_at=r.clock())
            state.pop('complete',None)
            if mode=='create_account':record(r,'creation_pending',filled['credential_ref'],'Mapped account creation with retained credentials; employer confirmation pending')
        # Persist uncertainty BEFORE the browser call; a lost response is not replayed.
        steps[key]='possibly_executed';r.persist();execution='possibly_executed'
        if source=='simplify':
            r.owned('writer_state',state='active')
            response=await SimplifyBoundary(r.page,budget_seconds=30,fast=True).perform(control['operation'],credential_evidence=mapping.get('credential_evidence'))
            execution=response.get('execution','possibly_executed')
            success=execution=='clicked'
        else:
            fresh.setdefault('native',{})['mapped']={'ref':ref,'enabled':True}
            success=await r.click('native_mapped',fresh)
            execution='clicked' if success else getattr(r,'last_click_execution','possibly_executed')
        steps[key]=execution
        if execution=='not_executed':
            del steps[key];r.state['authentication']=previous_auth
        r.persist()
        return result(status='progress') if success else stopped('mapped_action_'+execution,execution)
    except Exception as exc:
        return stopped('mapped_step_'+type(exc).__name__,execution)
    finally:
        r.owned('action_end',action_id=aid,status='success' if success else 'failed',duration_seconds=r.clock()-started)
        r.persist()


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
