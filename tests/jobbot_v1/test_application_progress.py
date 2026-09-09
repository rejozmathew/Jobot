"""Semantic progress projection and actual dashboard rendering, with synthetic events."""
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import subprocess

import pytest

from job_applier import managed_reports
from job_applier.managed import ProtocolError
from test_local_sessions import setup,reserve,connect,own
from test_workday_dom import JSDOM,ROOT


def row(index,kind='checkpoint',**payload):
    return {'id':str(index),'event_type':kind,'observed_at':f'2026-09-09T12:00:{index:02d}+00:00',
            'recorded_at':f'2026-09-09T12:00:{index:02d}+00:00','payload':payload,'stale':0}


def test_field_task_groups_retries_and_closes_recovered_errors():
    events=[row(1,'field_context',stage_id='remaining_questions',task_id='veteran',field='veteran',field_label='Veteran status',
                activity='Fill veteran status',task_state='in_progress'),
            row(2,'tool_finished',stage_id='remaining_questions',task_id='veteran',status='failed',tool_name='workday_dropdown_helper'),
            row(3,'field_verified',stage_id='remaining_questions',task_id='veteran',field='veteran',field_label='Veteran status',
                task_state='completed',evidence='Exact intended option committed')]
    projected=managed_reports.application_progress(events,now='2026-09-09T12:00:10+00:00')
    stage=projected['stages'][0];task=stage['tasks'][0]
    assert stage['title']=='Complete remaining questions'
    assert len(stage['tasks'])==1 and task['title']=='Fill veteran status' and task['state']=='completed'
    assert task['debug'][0]['resolved'] is True
    assert 'workday_dropdown_helper' not in task['title']


def test_stage_projection_precedes_compact_event_limit(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path);session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    s.progress(**owner,stage='remaining_questions',task_id='source',activity='Review and fill “How did you hear about us?”')
    for i in range(40):
        s.event(**owner,event_id=f'poll-{i}',event_type='tool_finished',observed_at=s.now(),payload={'tool_name':'browser_observe','status':'success'})
    status=s.session_status(session['id'])
    assert status['progress']['stages'][0]['tasks'][0]['id']=='source'
    assert s.attempt_report(owner['attempt_id'])['progress']['stages'][0]['tasks'][0]['id']=='source'


def test_progress_convenience_supplies_identity_time_but_external_event_stays_strict(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path);session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    result=s.progress(**owner,stage='email_verification',task_id='retrieve',activity='Retrieve verification email')
    assert result['id'] and datetime.fromisoformat(result['observed_at']).tzinfo
    with pytest.raises(ProtocolError,match='invalid_timestamp'):
        s.event(**owner,event_id='invalid-external',event_type='checkpoint',observed_at='not a time',payload={})
    with pytest.raises(ProtocolError,match='progress_completion_evidence_required'):
        s.progress(**owner,stage='email_verification',task_id='retrieve',activity='Retrieve verification email',state='completed')


def test_waits_and_overlapping_actions_have_separate_honest_durations():
    events=[row(0,stage_id='remaining_questions',task_id='question',activity='Fill a required answer',task_state='in_progress'),
            row(2,stage_id='remaining_questions',task_id='question',task_state='awaiting_input'),
            row(8,stage_id='remaining_questions',task_id='question',task_state='in_progress'),
            row(10,'field_verified',stage_id='remaining_questions',task_id='question',task_state='completed',evidence='Committed')]
    actions=[{'id':'a','started_at':events[0]['observed_at'],'ended_at':events[1]['observed_at'],
              'semantic_context_json':json.dumps({'task_id':'question'})},
             {'id':'b','started_at':'2026-09-09T12:00:01+00:00','ended_at':'2026-09-09T12:00:03+00:00',
              'semantic_context_json':json.dumps({'task_id':'question'})}]
    task=managed_reports.application_progress(events,actions=actions,now=events[-1]['observed_at'])['stages'][0]['tasks'][0]
    assert task['elapsed_seconds']==10 and task['wait_seconds']==6 and task['action_seconds']==3


def test_unattributed_legacy_tools_are_debug_without_fabricated_tasks():
    progress=managed_reports.application_progress([row(1,'tool_finished',tool_name='workday_dropdown_helper',status='success')],
                                                 now='2026-09-09T12:00:02+00:00')
    assert progress['stages']==[] and progress['details_recorded'] is False
    assert len(progress['debug'])==1


def test_arbitrary_completion_label_does_not_invent_verified_success():
    events=[row(1,stage_id='remaining_questions',task_id='field',activity='Fill veteran status',task_state='recovering'),
            row(2,stage_id='remaining_questions',task_id='field',task_state='completed')]
    task=managed_reports.application_progress(events)['stages'][0]['tasks'][0]
    assert task['state']=='recovering'


def test_runtime_field_context_links_actions_and_contains_question_not_answer(tmp_path):
    from job_applier.managed_events import field_task_context
    s,asset,jobs,ws,cfg=setup(tmp_path);session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    context=field_task_context('Veteran status',document=jobs[0]['url'])
    s.event(**owner,event_id='context',event_type='field_context',observed_at=s.now(),payload=context)
    action=s.action_start(**owner,action_id='selection',tool_name='local_browser.select')
    assert json.loads(action['semantic_context_json'])['task_id']==context['task_id']
    s.action_end(**owner,action_id='selection',status='success')
    s.event(**owner,event_id='verified',event_type='field_verified',observed_at=s.now(),
        payload=dict(context,task_state='completed',evidence='Intended answer verified'))
    task=s.session_status(session['id'])['progress']['stages'][0]['tasks'][0]
    assert task['state']=='completed' and task['title']=='Fill veteran status'
    assert task['action_ids']==['selection'] and task['action_seconds'] is not None
    assert s.view()['current_run'] is None or 'progress' in s.view()['current_run']['focused_context']


def test_ready_to_autofill_timing_uses_first_verified_dispatch_not_polling(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path);session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    connected=datetime.fromisoformat(session['connected_at'])
    for index,seconds in enumerate((3,7)):
        s.event(**owner,event_id=f'fill-{index}',event_type='checkpoint',observed_at=(connected+timedelta(seconds=seconds)).isoformat(),
            payload={'operation':'autofill_dispatch','status':'executed'})
    status=s.session_status(session['id'])
    assert status['ready_to_autofill_seconds']==3


def test_private_progress_recovery_completes_without_transient_values(tmp_path):
    from job_applier.managed_credentials import credential_progress
    s,asset,jobs,ws,cfg=setup(tmp_path);session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    def call(op,**params):return getattr(s,op)(**params)
    params={'mode':'verification','action':'fill'}
    credential_progress(call,owner,params)
    credential_progress(call,owner,params,result={'values_committed':False,'error':'ABCD2345'})
    credential_progress(call,owner,params,result={'values_committed':True,'value':'ABCD2345'})
    progress=s.session_status(session['id'])['progress']
    assert progress['stages'][0]['tasks'][0]['state']=='completed'
    assert 'ABCD2345' not in json.dumps(progress)


def test_actual_required_question_records_wait_for_input_without_answer(tmp_path):
    s,asset,jobs,ws,cfg=setup(tmp_path);session=connect(s,reserve(s,asset,jobs));owner=own(s,session)
    s.request_question(**owner,field='reason',question='Why this role?',kind='text')
    task=s.session_status(session['id'])['progress']['stages'][0]['tasks'][0]
    assert task['state']=='awaiting_input' and task['title']=='Review and fill “Why this role?”'


def test_dashboard_keeps_semantic_tasks_visible_and_helper_names_in_collapsed_debug():
    if not JSDOM.exists():pytest.skip('optional jsdom fixture dependency not installed')
    html=(ROOT/'job_applier/static/jobbot.html').read_text(encoding='utf-8')
    script=(ROOT/'job_applier/static/jobbot.js').read_text(encoding='utf-8')
    payload={'local_runtime':{'workspaces':[{}],'sessions':[{
        'id':'session-fixture','job_id':'job-fixture','identity_id':'candidate','state':'connected','metadata':{},
        'progress':{'details_recorded':True,'debug':[{'payload':{'tool_name':'workday_dropdown_helper','status':'failed'}}],
            'stages':[{'id':'remaining_questions','title':'Complete remaining questions','state':'in_progress',
              'tasks':[{'id':'source','title':'Review and fill “How did you hear about us?”','state':'in_progress','debug':[]}]}]}}]},
        'jobs':[{'id':'job-fixture','url':'https://example.test/jobs/director','company':None,'title':None}],
        'candidates':[]}
    harness=r'''
const fs=require('fs'),{JSDOM}=require(process.argv[1]),d=JSON.parse(fs.readFileSync(0,'utf8'));
const w=new JSDOM(d.html,{url:'http://localhost/',runScripts:'outside-only'}).window;
w.setInterval=()=>0;w.fetch=()=>new Promise(()=>{});w.eval(d.script+'\nwindow.renderTest=renderSessions;');
w.renderTest(d.payload);
const root=w.document.getElementById('local-sessions');
const shown=e=>{for(let p=e.parentElement;p&&root.contains(p);p=p.parentElement)if(p.tagName==='DETAILS'&&!p.open)return false;return !e.closest('details.debug-details');};
const normal=[...root.querySelectorAll('*')].filter(shown).map(e=>e.childNodes.length===1&&e.firstChild.nodeType===3?e.textContent:'').join(' ');
const debug=[...root.querySelectorAll('details.debug-details')];
const stage=root.querySelector('[data-progress-key="session-fixture:stage:remaining_questions"]');
stage.querySelector('summary').click();w.renderTest(d.payload);
console.log(JSON.stringify({normal,debug:debug.map(e=>({open:e.open,text:e.textContent})),
 collapsed:!root.querySelector('[data-progress-key="session-fixture:stage:remaining_questions"]').open}));w.close();
'''
    result=subprocess.run(['node','-e',harness,str(JSDOM)],input=json.dumps({'html':html,'script':script,'payload':payload}),
        text=True,encoding='utf-8',capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr
    rendered=json.loads(result.stdout)
    assert 'How did you hear about us?' in rendered['normal']
    assert 'workday_dropdown_helper' not in rendered['normal'] and 'job-fixture' not in rendered['normal']
    assert 'Identifying company and role' in rendered['normal']
    assert all(not d['open'] for d in rendered['debug']) and any('workday_dropdown_helper' in d['text'] for d in rendered['debug'])
    assert rendered['collapsed']
