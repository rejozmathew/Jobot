"""Staged native Hermes plugin entry. No active-profile installation side effects."""
from pathlib import Path
import json
import sys


def register(ctx):
    required=('get_config','register_tool','register_hook','on_unload')
    if not all(callable(getattr(ctx,name,None)) for name in required):
        raise TypeError('Unsupported Hermes plugin interface')
    config_path=ctx.get_config('app_config')
    repo=ctx.get_config('app_repo')
    if not config_path:
        # A standalone installation may not yet know the app checkout. Expose
        # truthful unavailable metadata without importing arbitrary CWD packages.
        schema={'name':'jobbot','description':'Managed worker; explicit configuration required.',
                'parameters':{'type':'object','properties':{'operation':{'type':'string'},
                    'parameters':{'type':'object'}},'required':['operation']}}
        handler=lambda args, **kwargs: json.dumps({'error':'integration_not_configured','available':False})
        available=lambda:False
        route=lambda name, **kwargs:None
        close=lambda:None
        hooks=('pre_tool_call','post_tool_call','pre_api_request','post_api_request','api_request_error')
    else:
        if repo is None:raise ValueError('Explicit app_repo is required')
        path=Path(repo)
        if not path.is_absolute() or not (path/'job_applier/hermes_plugin.py').is_file():
            raise ValueError('Explicit app_repo is unavailable')
        sys.path.insert(0,str(path))
        from job_applier import hermes_plugin
        if Path(hermes_plugin.__file__).resolve().parent != (path/'job_applier').resolve():
            raise ValueError('Loaded app code differs from configured repository')
        controller=hermes_plugin.PluginController(config_path)
        schema=hermes_plugin.SCHEMA;hooks=hermes_plugin.HOOKS
        handler=controller.handle;available=controller.available;route=controller.route;close=controller.close
    ctx.on_unload(close)
    registration=ctx.register_tool(name='jobbot',toolset='jobbot',schema=schema,
        handler=handler,check_fn=available,
        description=schema['description'],override=False)
    if registration is None:raise ValueError('JobBot tool registration refused')
    for name in hooks:
        def observer(_name=name, **kwargs):
            return route(_name,**kwargs)
        ctx.register_hook(name,observer)
