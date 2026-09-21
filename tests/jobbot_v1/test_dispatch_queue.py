"""Queue contracts use synthetic records, never live jobs or a real executor."""
import json
import sys
from pathlib import Path

import pytest

from job_applier.managed import ProtocolError
from test_local_sessions import setup


def enqueue(s, asset, jobs, request='request', **kwargs):
    return s.queue_enqueue(job_ids=[j['id'] for j in jobs], identity_id='candidate',
                           resume_asset_id=asset['id'], request_id=request, **kwargs)


def test_queue_deduplicates_intake_and_explicit_requests(tmp_path):
    s, asset, jobs, ws, cfg = setup(tmp_path)
    first = enqueue(s, asset, jobs)
    assert len(first['items']) == 3
    assert enqueue(s, asset, jobs)['items'] == first['items']
    assert enqueue(s, asset, jobs, request='rediscovered')['items'] == first['items']
    assert s.queue_status()['counts']['queued'] == 3
    assert s.queue_status()['enabled'] is False


def test_queue_never_downgrades_success_and_rolls_back_batch(tmp_path):
    s, asset, jobs, ws, cfg = setup(tmp_path)
    with s.tx() as db:
        db.execute("UPDATE jobs SET status='applied' WHERE id=?", (jobs[1]['id'],))
    with pytest.raises(ProtocolError, match='already_applied'):
        enqueue(s, asset, jobs)
    assert s.queue_status()['items'] == []
    assert s.job(jobs[1]['id'])['status'] == 'applied'


def test_queue_claim_is_serial_and_review_mode_is_not_submission_permission(tmp_path):
    s, asset, jobs, ws, cfg = setup(tmp_path)
    enqueue(s, asset, jobs)
    first = s.queue_take()
    assert first['job_id'] == jobs[0]['id']
    assert s.queue_take() is None
    assert s.settings_view()['values']['submission_mode'] == 'review'
    s.queue_complete(first['id'], outcome='blocked', detail='Synthetic image CAPTCHA')
    assert s.queue_take()['job_id'] == jobs[1]['id']
    # Rediscovery does not silently replay a blocked application; explicit retry can.
    assert enqueue(s, asset, [jobs[0]], request='rediscovery')['items'][0]['state'] == 'finished'
    assert enqueue(s, asset, [jobs[0]], request='explicit-retry', retry=True)['items'][0]['state'] == 'queued'


def test_queue_unknown_submission_is_not_a_new_manual_retry_lock(tmp_path):
    s, asset, jobs, ws, cfg = setup(tmp_path)
    enqueue(s, asset, [jobs[0]])
    item = s.queue_take()
    s.queue_complete(item['id'], outcome='submission_unknown', detail='No receipt recorded')
    with s.tx() as db:
        db.execute("UPDATE jobs SET status='submission_unknown' WHERE id=?", (jobs[0]['id'],))
    assert enqueue(s, asset, [jobs[0]], request='new-user-request', retry=True)['items'][0]['state'] == 'queued'


def test_dashboard_keeps_latest_job_request_beyond_recent_history_limit(tmp_path):
    s, asset, jobs, _, _ = setup(tmp_path)
    waiting = enqueue(s, asset, [jobs[0]])['items'][0]
    for index in range(101):
        item = enqueue(s, asset, [jobs[1]], request=f'retry-{index}', retry=True)['items'][0]
        s.queue_complete(item['id'], outcome='interrupted', detail='Synthetic executor stopped')
    status = s.queue_status()
    assert len(status['items']) == 100
    assert waiting['id'] not in {item['id'] for item in status['items']}
    assert status['latest_by_job'][jobs[0]['id']]['state'] == 'queued'
    assert status['latest_by_job'][jobs[1]['id']]['id'] == item['id']


def test_brief_restores_mail_ats_vision_simplify_and_one_job(tmp_path):
    from job_applier.application_brief import application_brief
    s, asset, jobs, ws, cfg = setup(tmp_path)
    cfg.update(config_path=str(tmp_path/'config.json'), identity_id='candidate', resume_asset_id=asset['id'],
               mailbox_provider='himalaya', himalaya_account='applications')
    item = enqueue(s, asset, [jobs[0]])['items'][0]
    brief = application_brief(cfg, s, item)
    for term in ('ONE job', 'Himalaya', 'Simplify', 'screenshot', 'actually inspect', 'Workday', 'Greenhouse', 'iCIMS', 'SMS', 'image CAPTCHA'):
        assert term in brief
    assert jobs[0]['url'] in brief and jobs[1]['url'] not in brief
    assert 'read-only' not in brief.lower()  # executor is allowed to apply
    assert '--request-id' in brief and item['id'] in brief
    assert 'review' in brief and 'Do not change code' in brief


def test_himalaya_handoff_does_not_require_gmail_tokens(tmp_path):
    from job_applier.hermes_gmail import mailbox_handoff
    cfg={'mailbox_provider':'himalaya','himalaya_account':'applications','himalaya_executable':sys.executable}
    handoff=mailbox_handoff(cfg)
    assert handoff['provider']=='himalaya'
    assert handoff['available'] is True and handoff['connection_verified'] is False
    assert 'applications' in handoff['instruction'] and '--help' in handoff['instruction']
    assert 'gmail' not in ' '.join(handoff['wrapper_argv']).lower()


def test_missing_himalaya_binary_is_reported_not_faked():
    from job_applier.hermes_gmail import mailbox_handoff
    h=mailbox_handoff({'mailbox_provider':'himalaya','himalaya_executable':'definitely-missing-himalaya-fixture'})
    assert not h['available'] and h['provider']=='himalaya'


def test_himalaya_context_accepts_null_optional_metadata(monkeypatch):
    from job_applier.hermes_gmail import mailbox_handoff
    seen=[]
    monkeypatch.setattr('shutil.which',lambda executable:seen.append(executable) or '/fixture/himalaya')
    handoff=mailbox_handoff({'mailbox_provider':'himalaya','himalaya_executable':None})
    assert seen==['himalaya'] and handoff['available']


def test_command_uses_fresh_cli_and_prompt_file_not_shell(tmp_path):
    from job_applier.queue_runtime import executor_command
    command=executor_command({}, tmp_path/'one job.md')
    assert command[:3]==['hermes','chat','-q']
    assert str(tmp_path/'one job.md') in command[-1]
    assert '--continue' not in command and '--resume' not in command
    custom=executor_command({'hermes_command':['custom-agent','--task','{prompt_file}']},tmp_path/'task.md')
    assert custom==['custom-agent','--task',str(tmp_path/'task.md')]


def test_queue_api_is_operator_only(tmp_path):
    from fastapi.testclient import TestClient
    from job_applier.managed_api import create_app
    s,asset,jobs,ws,cfg=setup(tmp_path)
    app=create_app(s,operator_token='operator-'+'a'*30,worker_tokens={'worker-'+'b'*30:'executor'})
    client=TestClient(app,base_url='http://127.0.0.1')
    payload=dict(job_ids=[jobs[0]['id']],identity_id='candidate',resume_asset_id=asset['id'],request_id='http')
    headers={'Authorization':'Bearer worker-'+'b'*30,'X-JobBot-Instance':s.instance_id}
    assert client.post('/v1/queue_enqueue',json=payload,headers=headers).status_code==403
    headers['Authorization']='Bearer operator-'+'a'*30
    assert client.post('/v1/queue_enqueue',json=payload,headers=headers).status_code==200


def runtime_fixture(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path)
    cfg.update(config_path=str(tmp_path/'runtime.json'),identity_id='candidate',resume_asset_id=asset['id'],
               workspaces=ws,spool_dir=str(tmp_path/'private-spool'))
    Path(cfg['config_path']).write_text(json.dumps(cfg),encoding='utf-8')
    return s,asset,jobs,ws,cfg


def test_dispatch_exit_zero_without_receipt_is_not_applied_and_context_is_isolated(tmp_path,monkeypatch):
    import os
    from job_applier.queue_runtime import dispatch_one
    s,asset,jobs,ws,cfg=runtime_fixture(tmp_path)
    enqueue(s,asset,jobs)
    captured=[]
    monkeypatch.setenv('HERMES_SESSION_ID','old-discovery-session')
    class Done:
        pid=os.getpid();returncode=0
        def poll(self):return 0
    def launch(command,**kwargs):
        captured.append((command,kwargs))
        assert not kwargs['shell'] and 'HERMES_SESSION_ID' not in kwargs['env']
        derived=json.loads(Path(kwargs['env']['JOBBOT_CONFIG']).read_text())
        assert derived['identity_id']=='candidate' and derived['resume_asset_id']==asset['id']
        return Done()
    assert dispatch_one(cfg,s,launcher=launch)['state']=='finished'
    assert dispatch_one(cfg,s,launcher=launch)['state']=='finished'
    assert captured[0][1]['env']['JOBBOT_CONFIG']!=captured[1][1]['env']['JOBBOT_CONFIG']
    first=Path(captured[0][1]['env']['JOBBOT_CONFIG']).with_name('task.md').read_text()
    assert jobs[0]['url'] in first and jobs[1]['url'] not in first
    assert {q['outcome'] for q in s.queue_status()['items'] if q['state']=='finished'}=={'interrupted'}
    assert s.job(jobs[0]['id'])['status']!='applied'


def test_dispatch_uses_real_recorded_outcome_and_does_not_overlap_live_workspace(tmp_path):
    import os
    from job_applier.queue_runtime import dispatch_one
    from test_local_sessions import reserve,connect,own
    s,asset,jobs,ws,cfg=runtime_fixture(tmp_path)
    enqueue(s,asset,jobs)
    active=connect(s,reserve(s,asset,jobs,index=2))
    def forbidden(*args,**kwargs):pytest.fail('Active workspace must not launch another queued executor')
    assert dispatch_one(cfg,s,launcher=forbidden)['state']=='waiting_for_browser'
    s.finish(**own(s,active),outcome='blocked',evidence='Synthetic fixture complete',quiescent=False)
    s.session_stopped(active['id'],reason='Synthetic process stopped',browser_stopped=True)
    class Done:
        pid=os.getpid();returncode=0
        def poll(self):return 0
    def launch(command,**kwargs):
        derived=Path(kwargs['env']['JOBBOT_CONFIG'])
        item=next(q for q in s.queue_status()['items'] if q['state']=='dispatched')
        session=connect(s,reserve(s,asset,jobs,index=0,request='queue:'+item['id']))
        s.finish(**own(s,session),outcome='ready_for_review',evidence='Synthetic form ready',quiescent=False)
        s.session_stopped(session['id'],reason='Review fixture complete',browser_stopped=True)
        return Done()
    assert dispatch_one(cfg,s,launcher=launch)['state']=='finished'
    finished=next(q for q in s.queue_status()['items'] if q['state']=='finished')
    assert finished['outcome']=='ready_for_review' and finished['session_id']


def test_recovery_never_replays_a_live_executor(tmp_path):
    import os
    from job_applier.queue_runtime import recover_dispatch
    from job_applier.workspace_process import process_identity
    s,asset,jobs,ws,cfg=runtime_fixture(tmp_path)
    enqueue(s,asset,[jobs[0]])
    item=s.queue_take()
    with s.tx() as db:
        db.execute('UPDATE dispatch_queue SET executor_identity_json=? WHERE id=?',(json.dumps(process_identity(os.getpid())),item['id']))
    assert recover_dispatch(s) is False
    assert s.queue_take() is None
    with s.tx() as db:db.execute('UPDATE dispatch_queue SET executor_identity_json=NULL WHERE id=?',(item['id'],))
    assert recover_dispatch(s) is True
    assert s.queue_status()['items'][0]['outcome']=='interrupted'


def test_answer_retry_requests_feed_same_queue_idempotently(tmp_path,monkeypatch):
    from job_applier.queue_runtime import import_answer_retries
    s,asset,jobs,ws,cfg=runtime_fixture(tmp_path)
    monkeypatch.setattr(s,'answer_retries',lambda **kwargs:{'requests':[{'job_id':jobs[0]['id'],'request_id':'answer-retry:fixture'}]})
    import_answer_retries(cfg,s);import_answer_retries(cfg,s)
    assert s.queue_status()['counts']['queued']==1


def test_harvest_cli_local_transport_and_explicit_verdict_enqueue(tmp_path,capsys):
    from test_harvest_handoff import get_intake_results_module
    s,asset,jobs,ws,cfg=runtime_fixture(tmp_path)
    records=[{'url':j['url'],'company':'Fixture','title':'Director','source_type':'harvest',
              'source_id':str(i),'verdict':verdict} for i,(j,verdict) in enumerate(zip(jobs,['Apply','Apply with caveats','Skip']))]
    path=tmp_path/'records.json';path.write_text(json.dumps(records),encoding='utf-8')
    module=get_intake_results_module()
    args=['--config',cfg['config_path'],'--input',str(path),'--enqueue']
    assert module.main(args+['--dry-run'])==0
    assert s.queue_status()['items']==[]
    assert module.main(args)==0
    assert s.queue_status()['counts']['queued']==1
    assert s.queue_status()['items'][0]['job_id']==jobs[0]['id']
    assert module.main(args)==0
    assert s.queue_status()['counts']['queued']==1


def test_harvest_brief_does_not_apply_or_assume_intake_equals_submission(tmp_path):
    from job_applier.harvest_runtime import harvest_brief,run_harvest
    s,asset,jobs,ws,cfg=runtime_fixture(tmp_path)
    text=harvest_brief(cfg,s,tmp_path/'records.json',enqueue=True)
    assert '--enqueue' in text and 'currently open roles' in text
    assert 'Do not open an\napplication session' in text
    assert cfg['config_path'] in text
    class Done:returncode=0
    result=run_harvest(cfg,s,enqueue=True,launcher=lambda *a,**k:Done())
    assert result['executor_exit_code']==0 and not result['record_file_exists']
    assert s.queue_status()['items']==[]


def test_dashboard_launcher_accepts_current_single_token_configuration(tmp_path,monkeypatch):
    from job_applier.queue_runtime import serve
    s,asset,jobs,ws,cfg=runtime_fixture(tmp_path)
    cfg.update(base_url='http://127.0.0.1:60158',operator_token_env='OPERATOR_FIXTURE',
               worker_token_env='WORKER_FIXTURE',worker_id='fixture-worker')
    monkeypatch.setenv('OPERATOR_FIXTURE','operator-fixture-'+'a'*30)
    monkeypatch.setenv('WORKER_FIXTURE','worker-fixture-'+'b'*30)
    calls=[]
    monkeypatch.setattr('uvicorn.run',lambda app,**kwargs:calls.append((app,kwargs)))
    serve(cfg,s)
    assert calls[0][1]['host']=='127.0.0.1' and calls[0][1]['port']==60158
    assert s.queue_status()['selection']=={'identity_id':'candidate','resume_asset_id':asset['id']}


def test_thin_entry_does_not_reintroduce_uncertain_history_veto():
    from job_applier.application_runtime import REPOSITORY
    text=(REPOSITORY/'integrations/hermes_jobbot/skills/job-apply/SKILL.md').read_text()
    assert 'or resubmit an uncertain application' not in text
    assert 'canonical retry policy' in text and 'Recorded successful submission suppresses duplicates' in text
