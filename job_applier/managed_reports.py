"""Timing projections preserve wall time and report overlap instead of inventing speed."""
from datetime import datetime,timedelta,timezone
import json
import hashlib
import re
from .managed_shared import ProtocolError
from .managed_redaction import safe_payload
from .managed_views import public_attempt,attempt_timing_state,resolve_failure_reason


def instant(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def union_seconds(spans):
    merged=[]
    for start,end in sorted(spans):
        if end<=start:continue
        if not merged or start>merged[-1][1]:merged.append([start,end])
        else:merged[-1][1]=max(merged[-1][1],end)
    return sum((end-start).total_seconds() for start,end in merged)


STAGE_TITLES={'opening':'Open the job posting','authentication':'Sign in to the employer',
    'fill_application':'Fill application','remaining_questions':'Complete remaining questions',
    'email_verification':'Verify email','submission':'Submit application'}
STAGE_ALIASES={'residual_fields':'remaining_questions','native_fallback':'remaining_questions','verification':'email_verification',
    'my_information':'fill_application','my_experience':'fill_application','application_questions':'remaining_questions',
    'voluntary_disclosures':'remaining_questions','self_identify':'remaining_questions','review':'submission','filling':'fill_application'}


def application_progress(events,*,actions=(),now=None,ended_at=None,limit=12):
    """Project semantic tasks before truncating; technical chronology stays in debug."""
    now=instant(now) if isinstance(now,str) else now or datetime.now(timezone.utc)
    until=instant(ended_at) if ended_at else now
    stages={};tasks={};debug=[]
    for raw in sorted(events,key=lambda row:(row.get('observed_at',''),row.get('recorded_at',''))):
        item=dict(raw);payload=safe_payload(item.get('payload') or json.loads(item.get('payload_json','{}')))
        item.pop('payload_json',None);item['payload']=payload
        debug.append(item)
        if item.get('stale'):continue
        try:when=instant(item['observed_at'])
        except (KeyError,TypeError,ValueError):continue
        stage_id=payload.get('stage_id') or STAGE_ALIASES.get(payload.get('phase'),payload.get('phase'))
        field=payload.get('field') or payload.get('field_key')
        if not stage_id and field:stage_id='remaining_questions'
        if stage_id not in STAGE_TITLES:continue
        stage=stages.setdefault(stage_id,{'id':stage_id,'title':STAGE_TITLES[stage_id],'state':'in_progress',
            'started_at':when.isoformat(),'ended_at':None,'tasks':[]})
        task_id=payload.get('task_id') or field
        kind=item.get('event_type');label=payload.get('field_label');activity=payload.get('activity')
        technical=bool(activity and re.search(r'\bhelper\b|workday_fast|\bCDP\b|pointer|quiescen|dispatch|read.?back',activity,re.I))
        if not task_id and kind=='phase_changed' and activity and not technical:
            task_id='activity:'+hashlib.sha256(activity.encode()).hexdigest()[:16]
        if not task_id:
            if payload.get('task_state'):stage['state']=payload['task_state']
            continue
        key=(stage_id,task_id)
        task=tasks.get(key)
        if task is None:
            title=activity if activity and not technical else ('Review and fill “'+label+'”' if label and '?' in label else 'Fill '+label if label else None)
            if not title:continue  # A tool name cannot manufacture a historical task.
            task={'id':task_id,'parent_id':stage_id,'title':title,'state':'in_progress','started_at':when.isoformat(),
                'ended_at':None,'debug':[],'action_ids':[],'_wait_start':None,'_waits':[]}
            tasks[key]=task;stage['tasks'].append(task)
        elif activity and not technical and kind!='tool_finished':task['title']=activity
        if item.get('action_id') and item['action_id'] not in task['action_ids']:task['action_ids'].append(item['action_id'])
        desired=payload.get('task_state') if kind!='tool_finished' else None
        if kind in ('field_verified','account_verified') and payload.get('evidence'):desired='completed'
        if kind=='tool_finished' or kind=='recovery' or payload.get('error_type'):
            task['debug'].append(dict(item,resolved=False))
            if payload.get('status') in ('failed','error','blocked','aborted'):desired='recovering'
        if desired=='completed' and not payload.get('evidence'):desired=None
        if desired not in ('in_progress','completed','recovering','awaiting_input','unsuccessful'):continue
        if task['_wait_start'] and desired!='awaiting_input':
            task['_waits'].append((task['_wait_start'],when));task['_wait_start']=None
        if desired=='awaiting_input' and task['_wait_start'] is None:task['_wait_start']=when
        task['state']=desired;task['ended_at']=when.isoformat() if desired in ('completed','unsuccessful') else None
        if desired=='completed':
            for error in task['debug']:error['resolved']=True
    for task in tasks.values():
        end=instant(task['ended_at']) if task['ended_at'] else until
        start=instant(task['started_at']);task['elapsed_seconds']=max(0,(end-start).total_seconds())
        if task['_wait_start']:task['_waits'].append((task['_wait_start'],end))
        task['wait_seconds']=union_seconds(task.pop('_waits'));task.pop('_wait_start')
        spans=[]
        for raw in actions:
            action=dict(raw);context=json.loads(action.get('semantic_context_json') or '{}')
            if action.get('id') not in task['action_ids'] and context.get('task_id')!=task['id']:continue
            try:
                left=max(start,instant(action['started_at']));right=min(end,instant(action['ended_at']) if action.get('ended_at') else until)
                spans.append((left,right))
            except (KeyError,TypeError,ValueError):pass
        task['action_seconds']=union_seconds(spans) if spans else None
    for stage in stages.values():
        children=stage['tasks']
        if children:
            states={task['state'] for task in children}
            stage['state']=next((s for s in ('awaiting_input','recovering','in_progress','unsuccessful') if s in states),'completed')
            if stage['state']=='completed':stage['ended_at']=max(t['ended_at'] for t in children)
        end=instant(stage['ended_at']) if stage['ended_at'] else until
        stage['elapsed_seconds']=max(0,(end-instant(stage['started_at'])).total_seconds())
        # Keep unresolved work visible regardless of low-level polling volume.
        active=[t for t in children if t['state']!='completed'];completed=[t for t in children if t['state']=='completed']
        stage['tasks']=active+completed[-max(0,limit-len(active)):] if len(active)<limit else active
        stage['omitted_completed_tasks']=len(children)-len(stage['tasks'])
    values=list(stages.values())
    active=next((task for stage in reversed(values) for task in reversed(stage['tasks']) if task['state']!='completed'),None)
    return {'stages':values,'active_task':active,'details_recorded':bool(values),'debug':debug[-100:]}


class ReportServices:
    def attempt_report(self,attempt_id,worker_id=None):
        now=instant(self.now())
        with self.tx() as db:
            row=db.execute('SELECT a.*, j.company, j.title as job_title, j.url as job_url, j.metadata_json as job_metadata_json FROM application_attempts a JOIN jobs j ON j.id=a.job_id WHERE a.id=?',(attempt_id,)).fetchone()
            if row is None:raise ProtocolError('not_found')
            a=dict(row)
            if a.get('platform')=='unknown' and a.get('job_url'):
                from .managed_context import platform_for_url
                p=platform_for_url(a['job_url'])
                if p!='unknown':a['platform']=p
            if worker_id is not None and a['worker_id']!=worker_id:raise ProtocolError('attempt_forbidden')
            a=attempt_timing_state(db,a,now)
            rows=[dict(r) for r in db.execute('SELECT * FROM managed_events WHERE attempt_id=? ORDER BY observed_at,recorded_at,id',(attempt_id,))]
            actions=[dict(r) for r in db.execute('SELECT * FROM managed_actions WHERE attempt_id=?',(attempt_id,))]
            failure_reason = resolve_failure_reason(db, a, events=rows)
            a['failure_reason'] = failure_reason
        start=instant(a['started_at']);end=instant(a['completed_at']) if a['completed_at'] else now
        wall=max(0,(end-start).total_seconds());spans=[];categories={'tool':[],'model':[]};timeline=[];issues=[]
        uncertainty=bool(a.get('uncertain_duration')) or end<start or a['outcome'] in ('interrupted','submission_unknown');phase_points=[(start,'unattributed')]
        token_values={'input_tokens':[],'output_tokens':[]}
        for event in rows:
            payload=safe_payload(json.loads(event.pop('payload_json')))
            event['payload']=payload;observed=instant(event['observed_at']);timeline.append(event)
            if event['event_type'] in ('phase','phase_changed') and payload.get('phase') and start<=observed<=end:
                phase_points.append((observed,payload['phase']))
            kind={'tool_finished':'tool','model_finished':'model'}.get(event['event_type'])
            if kind:
                duration=event['duration_seconds']
                if duration is None:uncertainty=True
                else:
                    raw_start=observed-timedelta(seconds=duration);left=max(start,raw_start);right=min(end,observed)
                    if left!=raw_start or right!=observed:uncertainty=True;event['uncertain']=True
                    if right>=left:spans.append((left,right));categories[kind].append((left,right))
                for key in token_values:
                    if type(payload.get(key)) is int and payload[key]>=0:token_values[key].append(payload[key])
            if payload.get('status') in ('failed','error','aborted','blocked'):
                issues.append({'event_id':event['id'],'status':payload['status'],
                    'category':payload.get('category') or payload.get('error_type') or payload.get('reason_code') or 'unspecified',
                    'tool_name':payload.get('tool_name'),'resolution':payload.get('resolution'),'observed_at':event['observed_at']})
        phase_points.sort(key=lambda x:x[0]);phases=[]
        for i,(when,name) in enumerate(phase_points):
            until=phase_points[i+1][0] if i+1<len(phase_points) else end
            if until>when:phases.append({'phase':name,'started_at':when.isoformat(),'ended_at':until.isoformat(),'duration_seconds':(until-when).total_seconds()})
        covered=union_seconds(spans)
        field_durations={};field_actions={};field_labels={};verified_fields=set();field_issues={}
        simplify_runs=[];simplify_fallbacks=[];problems=[]
        for event in rows:
            payload=event['payload']
            ev_type=event['event_type']

            fld=payload.get('field') or payload.get('field_key')
            lbl=payload.get('field_label')
            if fld and isinstance(fld,str) and lbl and isinstance(lbl,str):
                field_labels[fld]=lbl

            if ev_type=='tool_finished':
                tool_n=payload.get('tool_name','')
                is_field_tool=(tool_n.startswith('form_') or tool_n.startswith('upload_') or tool_n in ('upload_resume','upload_asset'))
                if is_field_tool and fld and isinstance(fld,str):
                    dur=event.get('duration_seconds')
                    if dur is not None:
                        if field_durations.get(fld) is None:field_durations[fld]=dur
                        else:field_durations[fld]+=dur
                    else:
                        if fld not in field_durations:field_durations[fld]=None
                    field_actions.setdefault(fld,[]).append(tool_n)

            if ev_type=='field_context' and payload.get('field'):
                f_ctx=payload['field']
                if f_ctx not in field_durations:field_durations[f_ctx]=None

            if ev_type=='field_verified' and payload.get('field'):
                verified_fields.add(payload['field'])

            if ev_type=='tool_finished' and payload.get('tool_name')=='simplify_autofill':
                dur=event.get('duration_seconds')
                simplify_runs.append({
                    'status':'complete' if payload.get('status')=='success' else payload.get('status','unknown'),
                    'reason':None,'duration_seconds':dur,'residual_fields':[],'field_attribution':'unknown'
                })
            elif (payload.get('source')=='Simplify' or (ev_type=='recovery' and payload.get('source')=='Simplify')):
                fb=payload.get('fallback_reason') or payload.get('reason')
                if fb and fb not in simplify_fallbacks:simplify_fallbacks.append(fb)
                if simplify_runs:
                    cur=simplify_runs[-1]
                    if payload.get('residual_fields') is not None:cur['residual_fields']=payload.get('residual_fields')
                    if fb:cur['reason']=fb
                    if payload.get('status') or payload.get('category'):cur['status']=payload.get('status') or payload.get('category')
                else:
                    dur=event.get('duration_seconds')
                    if dur is None:dur=payload.get('elapsed_seconds')
                    simplify_runs.append({
                        'status':payload.get('status') or payload.get('category') or 'unknown',
                        'reason':fb,'duration_seconds':dur,'residual_fields':payload.get('residual_fields',[]),'field_attribution':'unknown'
                    })

            if ev_type=='recovery' or payload.get('status') in ('failed','error','aborted','blocked'):
                prob_cat=payload.get('category') or payload.get('error_type') or payload.get('reason_code') or payload.get('status') or 'unspecified'
                f_key=payload.get('field_key') or payload.get('field')
                f_lbl=payload.get('field_label') or field_labels.get(f_key)
                src=payload.get('source','native')
                fb_reason=payload.get('fallback_reason') or payload.get('reason')
                res_status=payload.get('status','unresolved')
                problems.append({
                    'event_id':event['id'],'category':prob_cat,'field_key':f_key,'field_label':f_lbl,
                    'source':src,'fallback_reason':fb_reason,'status':res_status,
                    'resolution':payload.get('resolution'),'observed_at':event['observed_at']
                })
                if f_key:field_issues.setdefault(f_key,[]).append(prob_cat)

        for p in problems:
            if p['status']=='unresolved' and p.get('field_key'):
                fk=p['field_key']
                p_time=instant(p['observed_at'])
                resolved_later=False
                res_detail=None
                for ev in rows:
                    if instant(ev['observed_at'])>p_time:
                        p_ev=ev['payload']
                        ev_fld=p_ev.get('field') or p_ev.get('field_key')
                        if ev_fld==fk:
                            if ev['event_type']=='field_verified':
                                resolved_later=True;res_detail='verified_on_retry';break
                            elif ev['event_type']=='recovery' and p_ev.get('status')=='resolved':
                                resolved_later=True;res_detail=p_ev.get('resolution') or 'resolved';break
                if resolved_later:
                    p['status']='resolved'
                    p['resolution']=res_detail

        all_field_keys=set(field_durations.keys())|set(field_actions.keys())|verified_fields|set(field_issues.keys())
        fields={}
        for fk in sorted(all_field_keys):
            fields[fk]={'field_key':fk,'field_label':field_labels.get(fk),'elapsed_seconds':field_durations.get(fk),
                'action_count':len(field_actions.get(fk,[])),'actions':field_actions.get(fk,[]),
                'issue_count':len(field_issues.get(fk,[])),'verified':fk in verified_fields,
                'attribution':'native' if fk in field_actions else 'unknown'}
        valid_simp_durs=[r['duration_seconds'] for r in simplify_runs if r.get('duration_seconds') is not None]
        simplify_total=sum(valid_simp_durs) if valid_simp_durs else None
        simplify_summary={'runs_count':len(simplify_runs),'total_duration_seconds':simplify_total,
            'fallback_reasons':simplify_fallbacks,'runs':simplify_runs}

        return {'attempt':public_attempt(a,now),'failure_reason':failure_reason,'timeline':timeline,'phases':phases,'issues':issues,
            'progress':application_progress(timeline,actions=actions,now=now,ended_at=a['completed_at']),
            'timing':{'wall_seconds':wall,'observed_union_seconds':covered,'unattributed_seconds':max(0,wall-covered),
                'category_seconds':{k:union_seconds(v) if v else None for k,v in categories.items()},
                'reported_tokens':{k:sum(v) if v else None for k,v in token_values.items()},
                'uncertainty':uncertainty or not bool(spans),'uncertainty_reasons':a['timing_uncertainty_reasons'],
                'overlap_note':'Category times may overlap. Phase slices and category times are alternative views; do not add them.'},
            'fields':fields,'simplify':simplify_summary,'problems':problems}
