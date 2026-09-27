"""Same-conversation recovery, using synthetic native and application state."""
import json
from job_applier import hermes_desktop as desktop


def test_idle_unfinished_turn_continues_same_conversation(tmp_path,monkeypatch):
    states=iter(['idle','idle','working','idle']);checks=iter([{'session_id':'owned','attempt_id':7},{'session_id':'owned','attempt_id':7},None]);calls=[]
    monkeypatch.setattr(desktop,'continuation_context',lambda *a:next(checks),raising=False)
    class RPC:
        def call(self,method,params):
            calls.append((method,params))
            if method=='session.create':return {'session_id':'live','stored_session_id':'stored'}
            if method=='session.active_list':return {'sessions':[{'id':'live','status':next(states)}]}
            if method=='session.activate':return {'running':False,'inflight':{'status':'error','error':'Decoder failed'}}
            if method=='session.events.since':return {'events':[],'latest_seq':4,'epoch':'one'}
            return {'status':'streaming'}
    path=tmp_path/'receipt.json'
    result=desktop.run_session(RPC(),'original task',{'hermes_desktop':{}},path,sleep=lambda _:None)
    assert [m for m,p in calls].count('session.create')==1
    submits=[p for m,p in calls if m=='prompt.submit'];assert len(submits)==2
    assert {p['session_id'] for p in submits}=={'live'}
    assert 'owned' in submits[-1]['text'] and 'same' in submits[-1]['text']
    assert result['last_executor_failure']['kind']=='model_decode_error'


def test_rpc_retains_terminal_failure_without_private_error_text():
    class Socket:
        def send(self,value):self.rid=json.loads(value)['id']
        def recv(self,timeout=None):return '\n'.join([
            json.dumps({'method':'event','params':{'session_id':'owned','type':'message.complete','seq':5,
                'payload':{'status':'error','error':'Decoder failed password=do-not-log'}}}),
            json.dumps({'id':self.rid,'result':{}})])
    rpc=desktop.RPC(Socket());rpc.call('session.activate',{})
    assert rpc.terminal_events['owned']['kind']=='model_decode_error'
    assert 'do-not-log' not in json.dumps(rpc.terminal_events)


def test_cleanup_retains_native_failure_cause(tmp_path):
    from test_dispatch_queue import runtime_fixture,enqueue
    from job_applier.queue_runtime import settle
    s,asset,jobs,_,cfg=runtime_fixture(tmp_path);item=enqueue(s,asset,[jobs[0]])['items'][0]
    s.queue_take();s.desktop_dispatch_spool=cfg['spool_dir']
    from pathlib import Path
    root=Path(cfg['spool_dir'])/'dispatch'/item['id'];root.mkdir(parents=True)
    (root/'desktop-session.json').write_text(json.dumps({'last_executor_failure':{'kind':'model_decode_error','status':'error'}}))
    assert settle(s,item)
    assert 'model_decode_error' in s.queue_status()['latest_by_job'][jobs[0]['id']]['detail']


def test_uncertain_continuation_requires_its_exact_user_marker():
    marker='[JobBot continuation fixture]';calls=[]
    class RPC:
        def call(self,method,params):
            calls.append(method)
            return {'messages':[{'role':'assistant','text':marker},{'role':'user','text':'unrelated'}]}
    rpc=RPC();receipt={'session_id':'live','continuation_marker':marker}
    assert desktop.continuation_accepted(rpc,receipt,{'inflight':{'user':marker+' resume'}})
    assert calls==[]
    assert not desktop.continuation_accepted(rpc,receipt,{'inflight':{'user':'another turn'}})
    assert calls==['session.history']


def test_continuation_does_not_follow_foreign_attach(tmp_path):
    from test_dispatch_queue import runtime_fixture,enqueue
    from test_local_sessions import reserve,connect
    from pathlib import Path
    s,asset,jobs,_,cfg=runtime_fixture(tmp_path)
    item=enqueue(s,asset,[jobs[0]])['items'][0];s.queue_take()
    session=connect(s,reserve(s,asset,jobs,driver='stored',request='queue:'+item['id']))
    root=Path(cfg['spool_dir'])/'dispatch'/item['id'];root.mkdir(parents=True)
    receipt={'dispatch_id':item['id'],'session_id':'live','stored_session_id':'stored'}
    (root/'desktop-session.json').write_text(json.dumps(receipt))
    assert desktop.continuation_context(cfg,receipt)['session_id']==session['id']
    with s.tx() as db:db.execute('UPDATE application_sessions SET driver_id=? WHERE id=?',('another-owner',session['id']))
    assert desktop.continuation_context(cfg,receipt) is None
    from job_applier.queue_runtime import settle
    s.desktop_dispatch_spool=cfg['spool_dir']
    assert settle(s,item) is False
    with s.tx() as db:assert db.execute('SELECT control FROM runs WHERE id=?',(session['run_id'],)).fetchone()[0]=='running'


def test_continuation_deadline_checked_after_last_native_rpc(tmp_path,monkeypatch):
    from job_applier import application_deadline
    expired=[False];submits=[]
    class Deadline:
        def __init__(self,budget):pass
        def expired(self):return expired[0]
    monkeypatch.setattr(application_deadline,'Deadline',Deadline)
    monkeypatch.setattr(desktop,'continuation_context',lambda *a:{'session_id':'owned'})
    active_calls=[0]
    class RPC:
        def call(self,method,params):
            if method=='session.create':return {'session_id':'live','stored_session_id':'stored'}
            if method=='prompt.submit':submits.append(params);return {}
            if method=='session.active_list':
                active_calls[0]+=1
                if active_calls[0]>=2:expired[0]=True
                return {'sessions':[{'id':'live','status':'idle'}]}
            return {}
    result=desktop.run_session(RPC(),'initial',{'hermes_desktop':{}},tmp_path/'receipt.json',sleep=lambda _:None)
    assert len(submits)==1 and result['stop_reason']=='application_time_limit'


def test_explicit_rejected_followup_does_not_become_uncertain_send(tmp_path,monkeypatch):
    import pytest
    monkeypatch.setattr(desktop,'continuation_context',lambda *a:{'session_id':'owned'})
    count=[0]
    class RPC:
        def call(self,method,params):
            if method=='session.create':return {'session_id':'live','stored_session_id':'stored'}
            if method=='session.active_list':return {'sessions':[{'id':'live','status':'idle'}]}
            if method=='prompt.submit':
                count[0]+=1
                if count[0]>1:raise desktop.RPCRejected('Explicit native rejection')
            return {}
    path=tmp_path/'receipt.json'
    with pytest.raises(desktop.RPCRejected):desktop.run_session(RPC(),'original',{'hermes_desktop':{}},path,sleep=lambda _:None)
    assert json.loads(path.read_text())['state']=='submitted'


def test_initial_prompt_rejection_retains_original_task_on_reconnect(tmp_path):
    import pytest
    prompts=[]
    class RPC:
        def call(self,method,params):
            if method=='session.create':return {'session_id':'live','stored_session_id':'stored'}
            if method=='session.active_list':return {'sessions':[{'id':'live','status':'idle'}]}
            if method=='prompt.submit':
                prompts.append(params['text'])
                if len(prompts)==1:raise desktop.RPCRejected('Explicit rejection')
            return {}
    path=tmp_path/'receipt.json';rpc=RPC();cfg={'hermes_desktop':{}}
    with pytest.raises(desktop.RPCRejected):desktop.run_session(rpc,'Original approved application details',cfg,path,sleep=lambda _:None)
    assert json.loads(path.read_text())['state']=='created'
    desktop.run_session(rpc,'Original approved application details',cfg,path,sleep=lambda _:None)
    assert len(prompts)==2 and all('Original approved application details' in p for p in prompts)


def test_historical_recovered_error_does_not_replace_later_stop(tmp_path):
    from test_dispatch_queue import runtime_fixture,enqueue
    from job_applier.queue_runtime import settle
    from pathlib import Path
    s,asset,jobs,_,cfg=runtime_fixture(tmp_path);item=enqueue(s,asset,[jobs[0]])['items'][0];s.queue_take()
    s.desktop_dispatch_spool=cfg['spool_dir'];root=Path(cfg['spool_dir'])/'dispatch'/item['id'];root.mkdir(parents=True)
    (root/'desktop-session.json').write_text(json.dumps({'last_executor_failure':{'kind':'model_decode_error','status':'error'},
        'last_terminal':{'status':'interrupted','kind':'executor_interrupted'},'stop_reason':'application_stop_requested'}))
    settle(s,item)
    assert 'model_decode_error' not in s.queue_status()['latest_by_job'][jobs[0]['id']]['detail']
