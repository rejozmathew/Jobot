"""Hermes is a thin transport to the portable runner, not its implementation."""
import json
from types import SimpleNamespace
from job_applier import hermes_plugin
from job_applier import workday_fast


def test_fast_forward_is_available_and_invokes_shared_runner(monkeypatch):
    assert 'fast_forward' in hermes_plugin.OPERATIONS
    controller=hermes_plugin.PluginController('unused')
    owner={'attempt_id':1,'worker_id':'w','fence':2}
    client=object()
    adapter=SimpleNamespace(_state=lambda:{'attempt':owner},flush=lambda:False,client=client,worker_id='w')
    monkeypatch.setattr(controller,'_config',lambda:{'shared':'config'})
    monkeypatch.setattr(controller,'_adapter',lambda sid,cfg:adapter)
    calls=[]
    def shared(cfg,c,ctx,p):
        calls.append((cfg,c,ctx,p));return {'status':'waiting','reason':'bounded_call_elapsed'}
    monkeypatch.setattr(workday_fast,'advance',shared)
    result=json.loads(controller.handle({'operation':'fast_forward','parameters':{'target_id':'tab','seconds':60}},session_id='s'))
    assert result['status']=='waiting'
    assert calls==[({'shared':'config'},client,owner,{'target_id':'tab','seconds':60})]


def test_local_plugin_uses_session_metadata_and_scoped_transport(monkeypatch):
    from job_applier import application_runtime
    controller=hermes_plugin.PluginController('unused')
    monkeypatch.setattr(controller,'_config',lambda:{'transport':'local'})
    controller.runtime['ordinary-thread']={'model':'observed-model','provider':'observed-provider','reasoning_effort':'low'}
    calls=[]
    def start(cfg,**params):
        calls.append(params);return {'session_id':'local-session','state':'connected'}
    monkeypatch.setattr(application_runtime,'start',start)
    result=json.loads(controller.handle({'operation':'start','parameters':{'url':'https://example.test/job'}},session_id='ordinary-thread'))
    assert result['session_id']=='local-session'
    assert calls[0]['driver_id']=='ordinary-thread' and calls[0]['metadata']['model']=='observed-model'
    monkeypatch.setattr(application_runtime,'session_call',lambda cfg,sid,op,params,driver:dict(session_id=sid,operation=op,driver=driver))
    result=json.loads(controller.handle({'operation':'fast_forward'},session_id='ordinary-thread'))
    assert result=={'session_id':'local-session','operation':'fast_forward','driver':'ordinary-thread'}
    assert controller.route('pre_tool_call',session_id='ordinary-thread',tool_name='browser_click')['action']=='block'
    assert controller._thread is None
