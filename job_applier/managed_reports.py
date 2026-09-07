"""Timing projections preserve wall time and report overlap instead of inventing speed."""
from datetime import datetime,timedelta,timezone
import json
from .managed_shared import ProtocolError
from .managed_redaction import safe_payload
from .managed_views import public_attempt,attempt_timing_state


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


class ReportServices:
    def attempt_report(self,attempt_id,worker_id=None):
        now=instant(self.now())
        with self.tx() as db:
            a=dict(self._get(db,'application_attempts',attempt_id))
            if worker_id is not None and a['worker_id']!=worker_id:raise ProtocolError('attempt_forbidden')
            a=attempt_timing_state(db,a,now)
            rows=[dict(r) for r in db.execute('SELECT * FROM managed_events WHERE attempt_id=? ORDER BY observed_at,recorded_at,id',(attempt_id,))]
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
        return {'attempt':public_attempt(a,now),'timeline':timeline,'phases':phases,'issues':issues,
            'timing':{'wall_seconds':wall,'observed_union_seconds':covered,'unattributed_seconds':max(0,wall-covered),
                'category_seconds':{k:union_seconds(v) if v else None for k,v in categories.items()},
                'reported_tokens':{k:sum(v) if v else None for k,v in token_values.items()},
                'uncertainty':uncertainty or not bool(spans),'uncertainty_reasons':a['timing_uncertainty_reasons'],
                'overlap_note':'Category times may overlap. Phase slices and category times are alternative views; do not add them.'}}
