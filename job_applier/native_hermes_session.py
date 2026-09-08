"""Supported Hermes AIAgent invocation with canonical skill and native tools."""
import hashlib
import json
import os
from pathlib import Path
import uuid

from .hermes_plugin import HOOKS, SCHEMA, PluginController
from .managed_hermes_worker import select_runtime
from .managed_redaction import safe_text


def run_session(config, request):
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from hermes_cli.plugins import PluginContext, PluginManifest, get_plugin_manager
    from run_agent import AIAgent
    from hermes_state import SessionDB

    settings=request.get('settings') or json.loads(request.get('settings_json','{}'))
    provider,model,effort=select_runtime(settings)
    if settings.get('browser_mode','headed')!='headed':
        raise ValueError('This application executor requires the headed Simplify browser')
    runtime=resolve_runtime_provider(requested=provider,target_model=model)
    if runtime['provider']!=provider or not runtime['base_url'].startswith('https://chatgpt.com/backend-api/codex'):
        raise ValueError('Subscription route unavailable')
    repo=Path(__file__).resolve().parents[1]
    skill=repo/'skills/productivity/job-apply/SKILL.md'
    profile_skill=Path(os.environ['HERMES_HOME'])/'skills/productivity/job-apply/SKILL.md'
    if profile_skill.resolve()!=skill.resolve():
        raise ValueError('Hermes profile job-apply must reference the canonical repository skill')
    digest=hashlib.sha256()
    for path in sorted(skill.parent.rglob('*')):
        if path.is_file():
            digest.update(path.relative_to(skill.parent).as_posix().encode())
            digest.update(path.read_bytes())
    helper_digest=hashlib.sha256()
    for name in ('managed_credentials.py','hermes_gmail.py'):
        helper_digest.update((repo/'job_applier'/name).read_bytes())
    helper_version=helper_digest.hexdigest()[:20]
    digest.update(helper_digest.digest())
    version='job-apply-'+digest.hexdigest()[:20]
    sid='jobbot-'+str(uuid.uuid4())
    spool=Path(config['spool_dir'])/sid
    spool.mkdir(parents=True)
    cfg=dict(config,provider=provider,model=model,reasoning_effort=effort,
             skill_version=version,helper_version=helper_version,spool_dir=str(spool))
    cfg_path=spool/'worker.json'
    cfg_path.write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    os.environ['BROWSER_CDP_URL']=cfg.get('cdp_url','http://127.0.0.1:9222')
    controller=PluginController(str(cfg_path))
    ctx=PluginContext(PluginManifest(name='jobbot-runtime',provides_tools=['jobbot'],
                      provides_hooks=list(HOOKS)),get_plugin_manager())
    handles=[]
    agent=None
    receipt=dict(executor='Hermes',run_id=request.get('run_id') or request['id'],
                 session_id=sid,provider=provider,model=model,reasoning_effort=effort,
                 skill_loaded=str(profile_skill),skill_version=version,browser_mode='headed',
                 helper_version=helper_version,attempt_id=None,finished=False)

    def jobbot(args,**kwargs):
        result=controller.handle(args,**kwargs)
        data=json.loads(result)
        op=args.get('operation')
        if op=='next' and isinstance(data,dict) and data.get('id'):
            receipt['attempt_id']=data['id']
            print(json.dumps(dict(receipt,event='application_start',
                                  actual_runtime=controller.runtime.get(sid))),flush=True)
        if op=='finish' and isinstance(data,dict) and data.get('completed_at'):
            receipt.update(outcome=data['outcome'],finished=True)
        print(json.dumps({'operation':'jobbot.'+str(op),'attempt_id':receipt['attempt_id'],
                          'error':data.get('error') if isinstance(data,dict) else None}),flush=True)
        return result

    for name in HOOKS:
        def hook(_name=name,**kwargs):
            if kwargs.get('session_id')!=sid:return None
            if _name=='pre_tool_call' and kwargs.get('tool_name') in (
                    'write_file','file_write','patch','apply_patch','skill_manage','delegate_task'):
                return {'action':'block','message':'Application execution only: Codex owns source and skill changes.'}
            if _name=='post_api_request' and agent is not None:
                kwargs['reasoning_config']=dict(agent.reasoning_config or {})
                kwargs['reasoning_effort']=(agent.reasoning_config or {}).get('effort')
                print(json.dumps({'event':'model_response','model':kwargs.get('response_model'),
                                  'effort':kwargs['reasoning_effort']}),flush=True)
            return controller.route(_name,**kwargs)
        handles.append(ctx.register_hook(name,hook))
    handles.append(ctx.register_tool(name='jobbot',toolset='jobbot',schema=SCHEMA,
                                    handler=jobbot,check_fn=controller.available))
    result={}
    session_db=SessionDB()
    try:
        agent=AIAgent(model=model,provider=provider,base_url=runtime['base_url'],
            api_key=runtime['api_key'],api_mode=runtime.get('api_mode'),
            reasoning_config={'effort':effort},
            enabled_toolsets=['terminal','file','browser','skills','memory','jobbot'],
            ephemeral_system_prompt=f'Canonical job-apply skill loaded from {skill} (version {version}). '
                f'This version governs this application session; use its references at {skill.parent}.\n\n'+skill.read_text(encoding='utf-8'),
            max_iterations=160,quiet_mode=True,skip_background_review=True,
            session_id=sid,session_db=session_db,platform='cli',fallback_model={},
            run_budget_seconds=settings.get('attempt_seconds',1200),pass_session_id=True)
        if agent.model!=model or agent.provider!=provider or (agent.reasoning_config or {}).get('effort')!=effort:
            raise ValueError('Actual Hermes configuration mismatch')
        # Hermes normally defers plugin schemas behind tool_search. Queue pickup
        # needs JobBot immediately; retain every normal tool and expose only this
        # already-registered integration eagerly (including its native handler).
        from model_tools import get_tool_definitions
        if 'jobbot' not in {t['function']['name'] for t in agent.tools}:
            agent.tools.extend(t for t in get_tool_definitions(enabled_toolsets=['jobbot'],
                quiet_mode=True,skip_tool_search_assembly=True) if t['function']['name']=='jobbot')
            agent.valid_tool_names={t['function']['name'] for t in agent.tools}
        names={t['function']['name'] for t in agent.tools}
        required={'jobbot','terminal'}
        browser_available='browser_exec' in names or {'browser_navigate','browser_snapshot','browser_console'}<=names
        if not required<=names or not browser_available:
            raise ValueError('Required Hermes capabilities unavailable: '+','.join(sorted(required-names)))
        print(json.dumps(dict(receipt,event='session_ready',tools=sorted(names))),flush=True)
        agent._ensure_db_session()
        session_db.set_session_title(sid,'JobBot application '+sid[-12:])
        context=dict(run_id=receipt['run_id'],repository=str(repo),python=os.sys.executable,
                     cdp_url=os.environ['BROWSER_CDP_URL'],browser_profile=cfg['browser_profile'],
                     mailbox_token_path=cfg.get('mailbox_token_path'),
                     gmail_script=cfg.get('gmail_script'),worker_config=str(cfg_path))
        result=agent.run_conversation('Execute the authorized JobBot run using the loaded canonical job-apply skill. '
            'You are Windows Hermes, the application executor. Do not edit shared code or skills, invoke legacy '
            'application agents, or delegate execution. The user authorized account creation, ordinary email '
            'verification and final submission without human review. Start with jobbot accept then next. '
            'Use native browser tools and saved read-only helpers to decide the actual steps. '
            'A blocked job must be recorded and the next reserved job attempted. Preserve any failed page. '
            'Return only actual results, including employer evidence; never report a submit click as success.\n'
            'Run context:\n'+json.dumps(context))
    finally:
        # Never close the browser on failure: the exact page is acceptance evidence.
        adapter=controller.adapters.get(sid)
        current=adapter._state().get('attempt') if adapter else None
        if current:
            receipt['finished']=False
            receipt['attempt_id']=current['attempt_id']
            receipt['cleanup_status']='failed_page_preserved_attempt_requires_reconciliation'
        receipt['final']=safe_text(str(result.get('final_response') or result.get('response') or ''),limit=4000)
        (spool/'worker-result.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        print(json.dumps(receipt),flush=True)
        controller.close()
        session_db.close()
        for handle in handles:
            if callable(getattr(handle,'dispose',None)):handle.dispose()
            elif callable(getattr(handle,'unregister',None)):handle.unregister()
    return receipt
