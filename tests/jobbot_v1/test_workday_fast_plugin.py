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
