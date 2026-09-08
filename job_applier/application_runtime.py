"""Ordinary local startup/lifecycle and read-only duplicate history.

No model lives here. The dashboard and external HTTP integration are optional.
"""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import hashlib
import os
import sys
import time
from urllib.parse import urlsplit
from .managed_identity import canonical_url
from .managed_cli import credential_available
from .managed_shared import ProtocolError

REPOSITORY=Path(__file__).resolve().parents[1]
CONFIG_POINTER=REPOSITORY/'artifacts/jobbot-v1-private/runtime-config.json'


def resolve_config(path=None):
    """One explicit pointer, never a DB inferred from the shell working directory."""
    selected=path or os.environ.get('JOBBOT_CONFIG')
    if not selected:
        if not CONFIG_POINTER.is_file():raise ProtocolError('runtime_config_not_selected',str(CONFIG_POINTER))
        selected=json.loads(CONFIG_POINTER.read_text(encoding='utf-8'))['config_path']
    cfg=read_config(selected)
    cfg['config_path']=str(Path(selected).resolve())
    if not cfg.get('instance_id') or not Path(cfg.get('db_path','')).is_absolute():
        raise ProtocolError('explicit_managed_instance_required')
    return cfg


def validate_workspaces(workspaces):
    if not isinstance(workspaces,list) or not 1<=len(workspaces)<=8:raise ProtocolError('configured_workspace_pool_required')
    ids=set();profiles=set();endpoints=set();result=[]
    for raw in workspaces:
        w=dict(raw)
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',w.get('id','')):raise ProtocolError('invalid_workspace_id')
        profile=Path(w.get('user_data_dir',''))
        binary=Path(w.get('browser_executable',''))
        if not profile.is_absolute() or not binary.is_absolute():raise ProtocolError('absolute_workspace_paths_required')
        endpoint=urlsplit(w.get('cdp_url',''))
        if endpoint.scheme!='http' or endpoint.hostname!='127.0.0.1' or not endpoint.port or endpoint.path or endpoint.query or endpoint.fragment or endpoint.username or endpoint.password:
            raise ProtocolError('explicit_loopback_cdp_required')
        if w.get('mode','headed') not in ('headed','headless'):raise ProtocolError('invalid_browser_mode')
        resolved=str(profile.resolve()).casefold()
        if w['id'] in ids or resolved in profiles or w['cdp_url'] in endpoints:raise ProtocolError('workspace_isolation_required')
        if any(resolved.startswith(p+os.sep) or p.startswith(resolved+os.sep) for p in profiles):
            raise ProtocolError('workspace_isolation_required')
        ids.add(w['id']);profiles.add(resolved);endpoints.add(w['cdp_url'])
        w['user_data_dir']=str(profile.resolve());w['browser_executable']=str(binary.resolve())
        w.setdefault('mode','headed');result.append(w)
    return result


def prepare_local(config):
    """Back up the selected managed DB before the additive local-session migration."""
    from .managed_migrations import migrate
    from .managed import Service
    path=Path(config['db_path'])
    with closing(readonly(path)) as db:
        row=db.execute('SELECT id FROM instance').fetchone()
        if not row or row[0]!=config['instance_id']:raise ProtocolError('instance_mismatch')
        version=db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
    if version<15:
        from .workspace_process import FileLock
        with FileLock(str(path)+'.migration.lock'):
            with closing(readonly(path)) as db:
                version=db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
                if version<15:
                    backup=path.with_name(path.name+'.before-local-'+str(time.time_ns())+'.db')
                    with closing(sqlite3.connect(backup)) as destination:db.backup(destination)
                    with closing(readonly(backup)) as check:
                        if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ProtocolError('migration_backup_invalid')
                    migrate(path)
    service=Service(path,instance_id=config['instance_id'])
    service.configure_workspaces(config.get('workspaces'))
    return service


def driver_identity(driver_id=None):
    value=driver_id or os.environ.get('HERMES_SESSION_ID')
    if not value or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',value):
        raise ProtocolError('driver_session_required','Use the conversation session ID; another conversation must use its own ID')
    return value


def start(config, *, url=None, job_id=None, driver_id=None, request_id=None, metadata=None,
          company=None,title=None, wait_seconds=25):
    """Record immediately; return one durable handle even if browser startup is slow."""
    driver=driver_identity(driver_id)
    if bool(url)==bool(job_id):raise ProtocolError('one_url_or_job_id_required')
    service=prepare_local(config)
    if service.settings.get('mode')!='development' and config.get('require_simplify') is False:
        raise ProtocolError('official_simplify_required')
    maximum=config.get('maximum_runtime_seconds')
    if maximum is not None and (type(maximum) not in (int,float) or not 60<=maximum<=86400):
        raise ProtocolError('invalid_maximum_runtime')
    if url:
        if history_matches(config.get('legacy_history_paths',[]),url):raise ProtocolError('legacy_history_suppression')
        job=service.intake(url=url,source_type='manual',company=company,title=title)
        # Standing authorization is explicit configuration, not an inferred API role.
        if job['eligibility']=='held' and config.get('authorize_requested_urls') is True:
            job=service.eligibility(job['id'],'ready',reason='User-requested URL under configured standing application authorization')
    else:job=service.job(job_id)
    if history_matches(config.get('legacy_history_paths',[]),job['url']):raise ProtocolError('legacy_history_suppression')
    identity_id=config.get('identity_id');resume=config.get('resume_asset_id')
    if not identity_id or not resume:raise ProtocolError('configured_candidate_and_resume_required')
    requested=request_id or hashlib.sha256(json.dumps([driver,identity_id,job['id']]).encode()).hexdigest()
    from .managed_versions import code_evidence
    evidence=code_evidence()
    meta={**(metadata or {}),'requested_model':config.get('application_model',config.get('model')),
          'requested_provider':config.get('application_provider',config.get('provider')),
          'requested_effort':config.get('application_effort',config.get('reasoning_effort')),
          'config_path':config['config_path'],'canonical_skill_hash':evidence.get('canonical_skill_hash'),
          'source_revision':evidence.get('code_version'),'source_fingerprint':evidence.get('source_fingerprint'),'resume_asset_id':resume}
    meta['credential_sources']={k:config.get(k) for k in ('credential_profile_path','mailbox_token_path','gmail_script')}
    for configured,observed in (('application_model','model'),('application_provider','provider')):
        if config.get(configured) and meta.get(observed) and config[configured]!=meta[observed]:
            raise ProtocolError('application_runtime_model_mismatch')
    workspaces=validate_workspaces(config['workspaces'])
    limit=config.get('concurrency_limit',len(workspaces))
    if type(limit) is not int or not 1<=limit<=len(workspaces):raise ProtocolError('invalid_concurrency_limit')
    session=service.reserve_session(request_id=requested,job_id=job['id'],identity_id=identity_id,driver_id=driver,
        workspace_ids=[w['id'] for w in workspaces],concurrency_limit=limit,metadata=meta,resume_asset_id=resume)
    if session['state']=='preparing':
        from .workspace_host import ensure_host
        try:ensure_host(config,session['workspace_id'])
        except Exception as exc:
            # Release an unstarted request only after excluding both a retained
            # host lock and its recorded process tree. Live/uncertain ownership stays isolated.
            from .workspace_host import workspace_record,lock_path
            from .workspace_process import FileLock,process_matches
            w=workspace_record(service,session['workspace_id']);workspace=json.loads(w['config_json'])
            with FileLock(str(lock_path(workspace))+'.startup'):
                w=workspace_record(service,session['workspace_id'])
                alive=any(w[k] and process_matches(json.loads(w[k])) for k in ('host_identity_json','browser_identity_json'))
                if not alive and not FileLock.is_locked(lock_path(workspace)) and getattr(exc,'code',None)!='host_start_unconfirmed':
                    detail=error_detail(exc)
                    service.session_stopped(session['id'],reason=detail['code']+': '+detail['detail'],browser_stopped=True)
            return {**handle(service,session['id']), 'startup_error':error_detail(exc)}
        end=time.monotonic()+min(max(wait_seconds,0),45)
        while time.monotonic()<end:
            session=service.session(session['id'])
            if session['state']!='preparing':break
            time.sleep(.2)
    result=handle(service,session['id'])
    if session['state']=='capacity_wait':
        result['capacity_limit']=limit
        result['occupants']=[{'session_id':s['id'],'job_id':s['job_id'],'workspace_id':s['workspace_id'],'state':s['state']}
                             for s in service.sessions_view()['sessions'] if s['workspace_id'] and not s['ended_at']]
    return result


def handle(service, session_id):
    state=service.session_status(session_id)
    result={k:state[k] for k in ('id','job_id','run_id','attempt_id','driver_id','workspace_id','target_id','state','reason',
        'transport','requested_at','connected_at','ended_at','elapsed_seconds','host_alive','driver_recently_active','last_verified_progress_at')}
    result['session_id']=result.pop('id')
    if state['attempt_id']:
        package=service.application_context(state['attempt_id'])
        result['context']=package
    result['workspace']=state['workspace'];result['metadata']=state['metadata']
    return result


def session_call(config, session_id, operation, parameters=None, driver_id=None):
    from .managed import Service
    service=Service(config['db_path'],instance_id=config['instance_id'])
    if operation=='status':return handle(service,session_id)
    if operation in ('context','report'):
        session=service.session(session_id)
        if not session['attempt_id']:raise ProtocolError('attempt_not_started')
        return getattr(service,'application_context' if operation=='context' else 'attempt_report')(session['attempt_id'])
    driver=driver_identity(driver_id)
    session=service.session(session_id)
    if operation=='retry':
        if not session['ended_at']:raise ProtocolError('stop_session_before_retry')
        if session['attempt_id'] and service.attempt(session['attempt_id'])['submit_intent_at']:
            raise ProtocolError('verify_exact_submission_before_retry')
        job=service.job(session['job_id'])
        if job['status'] in ('blocked','failed','interrupted','ready_for_review','needs_review'):service.retry(job['id'])
        return start(config,job_id=job['id'],driver_id=driver,request_id='retry:'+session_id+':'+driver)
    if operation=='attach':
        session=service.attach_session(session_id,driver)
        from .workspace_host import ensure_host
        ensure_host(config,session['workspace_id'])
        return handle(service,session_id)
    if session['driver_id']!=driver:raise ProtocolError('driver_owned_elsewhere')
    if operation in ('pause','stop'):
        if not session['run_id']:
            return service.session_stopped(session_id,reason='Cancelled while waiting for capacity',browser_stopped=True)
        service.control(session['run_id'],command=operation)
        from .workspace_host import ensure_host
        ensure_host(config,session['workspace_id'])
        end=time.monotonic()+15
        while time.monotonic()<end:
            current=service.session(session_id)
            if current['state'] in ('paused','stopped','failed','finished'):return handle(service,session_id)
            time.sleep(.1)
        return {**handle(service,session_id),'control_pending':True}
    from .workspace_host import call_host
    return call_host(config,session,operation,parameters or {},driver)


def error_detail(exc):
    from .managed_redaction import safe_text
    return {'code':exc.code if isinstance(exc,ProtocolError) else type(exc).__name__,
            'detail':safe_text(str(exc))[:1000]}


def browser_action(config,client,ownership,package,target_id,params):
    """Existing CDP primitives, scoped to the session. No global focus or browser engine."""
    import asyncio
    from .cdp_client import CDPBrowser
    from .managed_identity import is_same_application_scope, is_workday_candidate_home
    from .managed_shared import uid
    method=params.get('method')
    if method not in ('snapshot','screenshot','evaluate','click','fill','press','navigate','upload','simplify'):
        raise ProtocolError('unsupported_browser_method')
    reads=method in ('snapshot','screenshot')
    aid=uid();started=time.monotonic();succeeded=False
    if not reads:client.call('browser_observe',**ownership,target_id=target_id,cdp_url=config['cdp_url'])
    client.call('action_start',**ownership,action_id=aid,tool_name='local_browser.'+method,writes_browser=not reads)
    async def execute():
        browser=await CDPBrowser.connect(config['cdp_url'],target_id=target_id,expected_mode=config.get('browser_mode','headed'))
        try:
            page=await browser.get_current_page();url=await page.evaluate('location.href')
            if not is_same_application_scope(package['job']['url'],url) and not (reads and is_workday_candidate_home(package['job']['url'],url)):
                raise ProtocolError('target_job_mismatch')
            if method=='screenshot':
                from .managed_credentials import capture_private_screenshot
                folder=Path(config['spool_dir'])/'screenshots'
                if not folder.is_absolute():raise ProtocolError('absolute_spool_required')
                folder.mkdir(parents=True,exist_ok=True);path=folder/(aid+'.png')
                await capture_private_screenshot(page,path)
                return {'image_path':str(path),'mime_type':'image/png','url':url,'target_id':target_id,
                    'instruction':'Inspect this owned-page image with the current harness image/vision capability; snapshot supplies observed selectors.'}
            if method=='snapshot':
                from .workday_fast import observe_page,screen_inventory
                inventory=screen_inventory(await observe_page(page,package),package)
                inventory['text']=await page.evaluate('document.body.innerText.slice(0,8000)')
                return inventory
            if method=='evaluate':
                return await page.evaluate_function(params['script'],params['argument']) if 'argument' in params else await page.evaluate(params['script'])
            if method=='navigate':
                if not is_same_application_scope(package['job']['url'],params['url']):raise ProtocolError('target_job_mismatch')
                await page.goto(params['url']);return {'navigation_requested':True}
            if method=='press':await page.press_key(params['key']);return {'pressed':True}
            if method=='simplify':
                from .simplify_boundary import SimplifyBoundary
                client.call('writer_state',**ownership,state='active')
                result=await SimplifyBoundary(page,budget_seconds=45).perform(params.get('action','autofill'),credential_evidence=params.get('credential_evidence'))
                client.call('writer_state',**ownership,state='idle' if result.get('native_takeover_authorized') else 'unknown')
                return result
            if method=='click' and params.get('ref'):
                from .workday_fast import observe_page,WORKDAY_CLICK
                from .simplify_boundary import CLICK
                observed=await observe_page(page,package)
                if params.get('page_signature')!=observed.get('page_signature'):return {'execution':'not_executed','reason':'stale_screen'}
                if params.get('source')=='simplify':
                    control=next((c for c in observed.get('simplify_inventory',[]) if c['ref']==params['ref']),None)
                    if not control:return {'execution':'not_executed','reason':'stale_control'}
                    if control['operation']=='sign_in':return {'execution':'not_executed','reason':'use_scoped_simplify_sign_in_with_credential_evidence'}
                    return await page.evaluate_function(CLICK,{'ref':control['ref'],'operation':control['operation'],'url':observed['url'],'page_ref':observed.get('page_ref')})
                return await page.click_observed(WORKDAY_CLICK,{'ref':params['ref'],'step':observed['step'],'page_signature':observed['page_signature']})
            selector=params['selector']
            if not isinstance(selector,str) or not selector:raise ProtocolError('observed_selector_required')
            if method=='click':
                from .workday_fast import WORKDAY_CLICK
                return await page.click_observed(WORKDAY_CLICK,{'selector':selector,'expected_url':url})
            if method=='upload':
                from .managed_documents import local_asset_path
                asset=next((a for a in package['documents']['assets'] if a['id']==params['asset_id']),None)
                if not asset:raise ProtocolError('asset_not_selected')
                path=local_asset_path(asset)
                if await page.evaluate_function('(p)=>document.querySelectorAll(p).length',selector)!=1:raise ProtocolError('ambiguous_or_stale_control')
                client.call('report_upload',**ownership,asset_id=asset['id'],status='upload_attempted',evidence='Approved asset supplied to an observed file control')
                controls=await page.query_selector_all(selector)
                await controls[0].set_input_files(str(path))
                return {'upload_attempted':True,'asset_id':asset['id'],'filename':path.name,'confirmation_required':True}
            return await page.evaluate_function("""p=>{const es=document.querySelectorAll(p.selector);
                if(es.length!==1)throw Error('ambiguous_or_stale_control');const e=es[0];
                if(!e.getClientRects().length||e.disabled)throw Error('control_unavailable');
                if(e.type==='password')throw Error('use_private_credentials_helper');
                e.focus();const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
                Object.getOwnPropertyDescriptor(proto,'value').set.call(e,p.value);
                e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));e.blur();
                return {committed:e.value===p.value};} """,{'selector':selector,'method':method,'value':params.get('value')})
        finally:await browser.close()
    try:
        result=asyncio.run(execute())
        succeeded=bool(result.get('clicked') or result.get('execution')=='clicked') if method=='click' else True
        return result
    finally:
        client.call('action_end',**ownership,action_id=aid,status='success' if succeeded else 'failed',duration_seconds=time.monotonic()-started)


def read_config(path):
    p=Path(path)
    if not p.is_absolute() or not p.is_file():raise ValueError('absolute_existing_config_required')
    data=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(data,dict):raise ValueError('invalid_config')
    return data


def readonly(path):
    p=Path(path)
    if not p.is_absolute() or not p.is_file():raise ValueError('history_unavailable')
    db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def history_key(url):
    canonical=canonical_url(url); p=urlsplit(canonical)
    if (p.hostname or '').endswith('.myworkdayjobs.com'):
        parts=p.path.casefold().strip('/').split('/')
        if parts and re.fullmatch(r'[a-z]{2}(?:-[A-Za-z0-9]{2,4})?',parts[0]):parts=parts[1:]
        if 'job' in parts:
            i=parts.index('job')
            if len(parts)>i+2 and '_' in parts[i+2]:
                return p.netloc.lower(),parts[0],parts[i+2].rsplit('_',1)[-1]
    return (canonical,)


def history_matches(paths,url):
    key=history_key(url); matches=[]
    for path in paths:
        try:
            with closing(readonly(path)) as db:
                rows=db.execute("SELECT id,url,status FROM jobs WHERE status IN ('applied','already_applied','submission_unknown','in_progress','running')")
                for row in rows:
                    if history_key(row['url'])==key:
                        matches.append({'database':str(Path(path).resolve()),'job_id':row['id'],'status':row['status']})
        except sqlite3.Error as exc:raise ValueError('history_unavailable') from exc
    return matches


def inspect_runtime(config_path,url=None):
    cfg=read_config(config_path); p=Path(cfg.get('db_path',''))
    if not p.is_absolute():raise ValueError('absolute_database_required')
    with closing(readonly(p)) as db:
        row=db.execute('SELECT id FROM instance').fetchone()
        if not row or row['id']!=cfg.get('instance_id'):raise ValueError('instance_mismatch')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        active=[]
        if 'runs' in tables:
            active=[dict(r) for r in db.execute("SELECT id,state,control FROM runs WHERE state!='completed'")]
    histories=cfg.get('legacy_history_paths',[])
    if not isinstance(histories,list):raise ValueError('invalid_history_paths')
    if any(Path(x).resolve()==p.resolve() for x in histories):raise ValueError('primary_is_not_legacy')
    for source in histories:
        with closing(readonly(source)):pass
    endpoint=urlsplit(cfg.get('cdp_url',''))
    if not cfg.get('workspaces') and (endpoint.scheme!='http' or endpoint.hostname not in ('127.0.0.1','localhost','::1') or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path):
        raise ValueError('explicit_loopback_cdp_required')
    result={'repository':str(Path(__file__).resolve().parents[1]),'instance_id':row['id'],
            'db_path':str(p.resolve()),'cdp_url':cfg.get('cdp_url'),'browser_profile':cfg.get('browser_profile'),
            'legacy_history_paths':histories,'historical_open_runs':active,
            'credential_reference_configured':bool(cfg.get('credential_profile_path')),
            'worker_token_available':credential_available(cfg.get('worker_token_env',''),cfg),
            'migration_performed':False}
    result['transport']=cfg.get('transport','http')
    result['config_path']=str(Path(config_path).resolve())
    if cfg.get('workspaces'):
        result['workspaces']=validate_workspaces(cfg['workspaces'])
        result['readiness']='Configuration checked; start verifies live browser/profile/target and Simplify'
    if url:result['history_matches']=history_matches([str(p),*histories],url)
    return result


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Local JobBot session interface. No API token or dashboard required.')
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('start','status','call','stop','pause','attach','retry','doctor','sessions'):
        p=sub.add_parser(name);p.add_argument('--config');p.add_argument('--driver-id')
        if name=='start':
            p.add_argument('url',nargs='?');p.add_argument('--job-id');p.add_argument('--request-id')
            p.add_argument('--company');p.add_argument('--title');p.add_argument('--metadata',default='{}')
            p.add_argument('--wait-seconds',type=float,default=25)
        elif name not in ('doctor','sessions'):p.add_argument('session_id')
        if name=='call':p.add_argument('operation');p.add_argument('--parameters',default='{}')
        if name=='doctor':p.add_argument('--url')
    args=parser.parse_args(argv)
    try:
        cfg=resolve_config(args.config)
        def payload(value):return json.loads(Path(value[1:]).read_text(encoding='utf-8') if value.startswith('@') else value)
        if args.command=='start':
            result=start(cfg,url=args.url,job_id=args.job_id,driver_id=args.driver_id,request_id=args.request_id,
                         metadata=payload(args.metadata),company=args.company,title=args.title,wait_seconds=args.wait_seconds)
        elif args.command=='doctor':result=inspect_runtime(cfg['config_path'],args.url)
        elif args.command=='sessions':
            from .managed import Service
            result=Service(cfg['db_path'],instance_id=cfg['instance_id']).sessions_view()
        else:result=session_call(cfg,args.session_id,args.operation if args.command=='call' else args.command,
                                 payload(args.parameters) if args.command=='call' else {},args.driver_id)
        print(json.dumps(result,ensure_ascii=False));return 0
    except Exception as exc:
        print(json.dumps({'status':'error','error':error_detail(exc)},ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
