"""Operator projections over shared records. Reads never start a worker."""
import json
import hashlib
from datetime import datetime,timezone
from .managed_shared import ProtocolError
from .managed_learning import public_record

TERMINAL={'applied','already_applied','ready_for_review','blocked','failed','interrupted','submission_unknown','skipped'}


def attempt_timing_state(db,row,now):
    a=dict(row);reasons=[]
    if a.get('uncertain_duration') or a['outcome'] in ('interrupted','submission_unknown'):reasons.append('recorded_uncertainty')
    if db.execute('SELECT 1 FROM managed_actions WHERE attempt_id=? AND (ended_at IS NULL OR uncertainty=1)',(a['id'],)).fetchone():reasons.append('unfinished_or_unmeasured_action')
    if not a['completed_at']:
        lease=db.execute('SELECT * FROM browser_leases WHERE profile=?',(a['browser_profile'],)).fetchone()
        live=bool(lease and lease['state']=='active' and lease['worker_id']==a['worker_id'] and lease['generation']==a['fence'])
        if live:
            expires=datetime.fromisoformat(lease['expires_at'])
            if expires.tzinfo is None:expires=expires.replace(tzinfo=timezone.utc)
            live=expires>now
        if not live:reasons.append('ownership_lost_or_expired')
    a['uncertain_duration']=bool(reasons)
    a['timing_uncertainty_reasons']=reasons
    return a


def public_attempt(row,now):
    a=dict(row)
    a.pop('profile_json',None)
    config=json.loads(a.get('settings_json') or '{}')
    start=datetime.fromisoformat(a['started_at'])
    if start.tzinfo is None:start=start.replace(tzinfo=timezone.utc)
    end=datetime.fromisoformat(a['completed_at']) if a.get('completed_at') else now
    if end.tzinfo is None:end=end.replace(tzinfo=timezone.utc)
    a['elapsed_seconds']=max(0,(end-start).total_seconds())
    a['uncertain_duration']=bool(a.get('uncertain_duration')) or end<start
    a['settings_hash']=hashlib.sha256(a['settings_json'].encode()).hexdigest()
    progress=datetime.fromisoformat(a.get('progress_at') or a['started_at'])
    heartbeat=datetime.fromisoformat(a.get('heartbeat_at') or a['started_at'])
    if progress.tzinfo is None:progress=progress.replace(tzinfo=timezone.utc)
    if heartbeat.tzinfo is None:heartbeat=heartbeat.replace(tzinfo=timezone.utc)
    a['progress_age_seconds']=max(0,(now-progress).total_seconds())
    a['heartbeat_age_seconds']=max(0,(now-heartbeat).total_seconds())
    a['stalled']=not a.get('completed_at') and a['progress_age_seconds']>config.get('no_progress_seconds',45)
    a['over_target']=a['elapsed_seconds']>config.get('attempt_seconds',300)
    return a


class ViewServices:
    def view(self,run_id=None,include_archived=False):
        if type(include_archived) is not bool:raise ProtocolError('invalid_archive_filter')
        now=datetime.fromisoformat(self.now())
        with self.tx() as db:
            jobs=[dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY created_at DESC,id')]
            archived={r[0] for r in db.execute('SELECT job_id FROM job_archives')}
            jobs=[dict(j,archived=j['id'] in archived) for j in jobs if include_archived or j['id'] not in archived]
            for job in jobs:
                job['assessment']=self._assessment(db,job['id'])
                job['source_count']=db.execute('SELECT COUNT(*) FROM job_sources WHERE job_id=?',(job['id'],)).fetchone()[0]
            runs=[dict(r) for r in db.execute('SELECT * FROM runs ORDER BY requested_at DESC,id')]
            candidates=[dict(r) for r in db.execute('SELECT id,person_key,email,state,profile_hash FROM candidates ORDER BY id')]
            accounts=[dict(r) for r in db.execute('SELECT * FROM company_portal_accounts ORDER BY id')]
            lessons=[self._lesson(db,r[0]) for r in db.execute('SELECT id FROM lessons ORDER BY created_at DESC,id')]
            helpers=[public_record(r) for r in db.execute('SELECT * FROM helper_versions ORDER BY helper_id,version')]
            assets=[public_record(r) for r in db.execute('SELECT * FROM document_assets ORDER BY created_at DESC,id')]
            selections=[dict(r) for r in db.execute('SELECT * FROM document_selections ORDER BY created_at DESC,id')]
            uploads=[dict(r) for r in db.execute('SELECT * FROM document_uploads ORDER BY created_at DESC,id')]
            assessments=[public_record(r) for r in db.execute('SELECT * FROM match_assessments ORDER BY recorded_at DESC,id')]
            for account in accounts:
                account.pop('credential_ref',None)
            chosen=next((r for r in runs if r['id']==run_id),None) if run_id else (runs[0] if runs else None)
            if run_id and chosen is None:raise ProtocolError('run_not_found')
            current=None
            if chosen:
                rows=[dict(r) for r in db.execute('SELECT * FROM run_jobs WHERE run_id=? ORDER BY position',(chosen['id'],))]
                attempts=[public_attempt(attempt_timing_state(db,r,now),now) for r in db.execute('SELECT * FROM application_attempts WHERE run_id=? ORDER BY id',(chosen['id'],))]
                counts={'selected':len(rows),'current':sum(r['state']=='active' for r in rows),
                    'completed':sum(r['state'] in TERMINAL for r in rows),'remaining':sum(r['state']=='pending' for r in rows),
                    'blocked':sum(r['state'] in ('blocked','submission_unknown','interrupted') for r in rows),
                    'applied':sum(r['state'] in ('applied','already_applied') for r in rows)}
                current=dict(chosen,run_id=chosen['id'],attempts=attempts,jobs=rows,**counts)
                current['targets']=[dict(r) for r in db.execute('SELECT t.* FROM owned_targets t JOIN application_attempts a ON a.id=t.attempt_id WHERE a.run_id=? ORDER BY t.created_at,t.id',(chosen['id'],))]
                for target in current['targets']:
                    target['history']=[dict(r) for r in db.execute('SELECT * FROM target_history WHERE target_record_id=? ORDER BY created_at,id',(target['id'],))]
                current['budget_extensions']=[dict(r) for r in db.execute('SELECT e.* FROM budget_extensions e JOIN application_attempts a ON a.id=e.attempt_id WHERE a.run_id=? ORDER BY e.created_at,e.id',(chosen['id'],))]
                current['unclassified']=counts['selected']-counts['current']-counts['completed']-counts['remaining']
                focus=next((a for a in reversed(attempts) if not a['completed_at']),attempts[-1] if attempts else None)
                current['focused_context']=None
                if focus:
                    job=self._get(db,'jobs',focus['job_id'])
                    events=db.execute('SELECT payload_json FROM managed_events WHERE attempt_id=? ORDER BY observed_at DESC,recorded_at DESC,id DESC',(focus['id'],)).fetchall()
                    payloads=[json.loads(e[0]) for e in events]
                    latest=next((p for p in payloads if any(p.get(k) for k in ('phase','activity','page','url','tool_name'))),{})
                    issue=next((p.get('error_type') or p.get('reason_code') or p.get('category') for p in payloads if p.get('status') in ('failed','error','blocked','aborted')),None)
                    versions=json.loads(focus['versions_json'] or '{}')
                    current['focused_context']={'is_active':not bool(focus['completed_at']),'state':'active' if not focus['completed_at'] else 'last_completed',
                        'attempt_id':focus['id'],'job':{k:job[k] for k in ('id','company','title','url')},
                        'page':latest.get('page') or latest.get('url') or job['url'],'activity':latest.get('activity') or latest.get('phase') or latest.get('tool_name') or focus.get('activity'),
                        'latest_unresolved_issue':issue or (focus.get('confirmation_evidence') or focus.get('evidence') if focus['outcome'] in ('failed','blocked','interrupted','submission_unknown') else None),
                        'worker_metadata':{k:versions.get(k) for k in ('skill_version','provider','model','protocol')},
                        'settings_hash':focus['settings_hash'],'uncertain_duration':focus['uncertain_duration']}
            schema=db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
        return {'health':dict(self.health(),schema_version=schema),'settings':self.settings_view(),
            'jobs':jobs,'runs':runs,'accounts':accounts,'candidates':candidates,'current_run':current,
            'lessons':lessons,'helpers':helpers,'assets':assets,'assessments':assessments,
            'document_selections':selections,'document_uploads':uploads}
