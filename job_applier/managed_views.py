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
        from .managed_sessions import local_session
        session=local_session(db,a['id'])
        if session:
            a['local_session_id']=session['id']
            a['session_state']=session['state']
            a['workspace_id']=session['workspace_id']
            if session['state'] not in ('connected','waiting','paused'):reasons.append('session_not_connected')
            a['uncertain_duration']=bool(reasons)
            a['timing_uncertainty_reasons']=reasons
            return a
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
    raw_profile=row.get('profile_json') or a.get('profile_json') or ''
    a['profile_hash']=hashlib.sha256(raw_profile.encode()).hexdigest()
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


def resolve_failure_reason(db, attempt, events=None):
    if not attempt:
        return None
    attempt = dict(attempt)
    outcome = attempt.get('outcome')
    if outcome not in ('failed', 'blocked', 'interrupted', 'submission_unknown'):
        return None
    if not attempt.get('completed_at'):
        return None

    # Submission unknown must override earlier pre-submit failures
    if outcome == 'submission_unknown':
        ev = (attempt.get('evidence') or '').strip()
        return ev if ev else 'Submit clicked; employer confirmation was not recorded. A new application request starts a separate attempt.'

    generic = (
        'worker exited before submission; owned target absence verified',
        'owned target absence verified',
        'worker_exit',
    )
    terminal_reason = (attempt.get('evidence') or '').strip()
    if terminal_reason.lower() in generic:
        terminal_reason = ''
    elif terminal_reason.lower().endswith('; owned target absence verified'):
        terminal_reason = terminal_reason[:-len('; owned target absence verified')].strip()

    ev_rows = events
    if ev_rows is None and db is not None:
        ev_rows = [dict(r) for r in db.execute(
            'SELECT payload_json, event_type, observed_at, recorded_at, id FROM managed_events WHERE attempt_id=? ORDER BY observed_at DESC, recorded_at DESC, id DESC',
            (attempt['id'],)
        ).fetchall()]
    elif ev_rows is not None:
        ev_rows = [dict(r) for r in ev_rows]
        ev_rows.sort(key=lambda r: (r.get('observed_at') or '', r.get('recorded_at') or '', r.get('id') or 0), reverse=True)

    resolved_operations = set()
    if ev_rows:
        for row in ev_rows:
            p = row.get('payload')
            if p is None and 'payload_json' in row:
                raw_json = row['payload_json']
                p = json.loads(raw_json) if isinstance(raw_json, str) else {}
            elif p is None:
                p = {}
            ev_type = row.get('event_type')
            if terminal_reason:
                # A completed attempt describes the remaining obstacle. Earlier
                # helper exceptions describe recovery, not its terminal cause.
                # Explicit later reconciliation can still refine the projection
                # without changing the original attempt or its completion time.
                if ev_type != 'outcome':
                    continue
                try:
                    observed = datetime.fromisoformat(row.get('observed_at') or row.get('recorded_at') or '')
                    completed = datetime.fromisoformat(attempt.get('completed_at') or '')
                    if observed.tzinfo is None: observed = observed.replace(tzinfo=timezone.utc)
                    if completed.tzinfo is None: completed = completed.replace(tzinfo=timezone.utc)
                    if observed < completed: continue
                except (TypeError, ValueError):
                    continue
            status = p.get('status')
            code = p.get('reason_code') or p.get('fallback_reason') or p.get('error_type') or ''
            evidence = (p.get('evidence') or '').strip()
            operation = p.get('operation') or p.get('tool_name')
            if status == 'resolved':
                if operation:
                    resolved_operations.add(operation)
                continue
            if operation and operation in resolved_operations:
                continue

            if ev_type == 'outcome' or status in ('failed', 'blocked', 'interrupted', 'submission_unknown', 'error', 'aborted') or (code and status != 'resolved'):
                if evidence and evidence.lower() not in generic:
                    return evidence

                if code == 'browser_writer_busy':
                    op = p.get('operation') or p.get('tool_name') or 'action'
                    return f"JobBot blocked the {op} operation because its browser state was busy or unverified (browser_writer_busy). No submission was made."

                if code and code.strip():
                    op = p.get('operation') or p.get('tool_name')
                    return f"{code} during {op}" if op else str(code)

    if terminal_reason:
        return terminal_reason

    return 'No specific failure reason was recorded.'


class ViewServices:
    def view(self,run_id=None,include_archived=False):
        if type(include_archived) is not bool:raise ProtocolError('invalid_archive_filter')
        now=datetime.fromisoformat(self.now())
        with self.read() as db:
            jobs=[dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY created_at DESC,id')]
            archived={r[0] for r in db.execute('SELECT job_id FROM job_archives')}
            jobs=[dict(j,archived=j['id'] in archived) for j in jobs if include_archived or j['id'] not in archived]
            from .job_duplicates import matching_records
            duplicates={job['id']:[] for job in jobs}
            labels={job['id']:job for job in jobs}
            for match in matching_records(db):
                if match['decision']=='different':continue
                for job_id,other in ((match['left_job_id'],match['right_job_id']),(match['right_job_id'],match['left_job_id'])):
                    if job_id in duplicates:
                        duplicates[job_id].append({k:match[k] for k in ('id','decision','method','similarity','evidence','operator_state')} |
                            {'other_job_id':other,'other_seq_id':labels.get(other,{}).get('seq_id')})
            for job in jobs:
                job['duplicate_matches']=duplicates[job['id']]
                job['assessment']=self._assessment(db,job['id'])
                job['sources']=self._source_rows(db,job['id'])
                job['source_count']=len(job['sources'])
                job['queue_origins']=[dict(r) for r in db.execute('''SELECT id,request_id,created_at,
                    enqueue_origin,producer,discovery_run_id,discovery_profile FROM dispatch_queue
                    WHERE job_id=? ORDER BY rowid''',(job['id'],))]
                # Metadata refreshes, heartbeats and new retries are not dispositions.
                # Keep the last recorded outcome visible even during a newer attempt.
                disposition=db.execute('''SELECT at,value,source FROM (
                    SELECT disposition_at AS at,disposition AS value,'operator' AS source,3 AS precedence
                    FROM jobs WHERE id=? AND disposition_at IS NOT NULL
                    UNION ALL SELECT completed_at,outcome,'application',2
                    FROM application_attempts WHERE job_id=? AND completed_at IS NOT NULL AND outcome IS NOT NULL
                    UNION ALL SELECT ended_at,outcome,'queue',1
                    FROM dispatch_queue WHERE job_id=? AND ended_at IS NOT NULL AND outcome IS NOT NULL
                    ) ORDER BY julianday(at) DESC,precedence DESC LIMIT 1''', (job['id'],)*3).fetchone()
                job['last_disposition']=dict(disposition) if disposition else None
                latest=db.execute('SELECT * FROM application_attempts WHERE job_id=? ORDER BY started_at DESC, id DESC LIMIT 1',(job['id'],)).fetchone()
                job['failure_reason']=resolve_failure_reason(db,dict(latest)) if latest else None
                # Completion time belongs to the successful attempt, across all runs.
                # An already-applied check does not measure the original application.
                job['application_timing']=None
                if job['status'] in ('applied','already_applied'):
                    successful=db.execute('''SELECT * FROM application_attempts WHERE job_id=?
                        AND outcome='applied' AND completed_at IS NOT NULL
                        AND julianday(completed_at)>=julianday(started_at)
                        ORDER BY julianday(completed_at) DESC,id DESC LIMIT 1''',(job['id'],)).fetchone()
                    if successful:
                        timing=public_attempt(attempt_timing_state(db,successful,now),now)
                        job['application_timing']={k:timing[k] for k in
                            ('started_at','completed_at','elapsed_seconds','uncertain_duration')}
                        job['application_timing']['attempt_id']=timing['id']
            runs=[dict(r) for r in db.execute('SELECT * FROM runs ORDER BY requested_at DESC,id')]
            candidates=[dict(r) for r in db.execute('SELECT id,person_key,email,state,profile_hash FROM candidates ORDER BY id')]
            accounts=[dict(r) for r in db.execute('SELECT * FROM company_portal_accounts ORDER BY id')]
            lessons=[self._lesson(db,r[0]) for r in db.execute('SELECT id FROM lessons ORDER BY created_at DESC,id')]
            helpers=[public_record(r) for r in db.execute('SELECT * FROM helper_versions ORDER BY helper_id,version')]
            assets=[public_record(r) for r in db.execute('SELECT * FROM document_assets ORDER BY created_at DESC,id')]
            selections=[dict(r) for r in db.execute('SELECT * FROM document_selections ORDER BY created_at DESC,id')]
            uploads=[dict(r) for r in db.execute('SELECT * FROM document_uploads ORDER BY created_at DESC,id')]
            assessments=[public_record(r) for r in db.execute('SELECT * FROM match_assessments ORDER BY recorded_at DESC,id')]
            from .portal_credentials import password_metadata
            for account in accounts:
                if account.get('namespace'):
                    account['namespace'] = self._namespace(db, account['namespace'])
            password_metadata(getattr(self, 'executor_config', {}), accounts)
            for account in accounts:
                account.pop('credential_ref',None)
            chosen=next((r for r in runs if r['id']==run_id),None) if run_id else (runs[0] if runs else None)
            if run_id and chosen is None:raise ProtocolError('run_not_found')
            current=None
            if chosen:
                rows=[dict(r) for r in db.execute('SELECT * FROM run_jobs WHERE run_id=? ORDER BY position',(chosen['id'],))]
                attempt_rows=[dict(r) for r in db.execute('SELECT a.*, j.company, j.title as job_title, j.url as job_url FROM application_attempts a JOIN jobs j ON j.id=a.job_id WHERE a.run_id=? ORDER BY a.id',(chosen['id'],))]
                for r in attempt_rows:
                    r['failure_reason']=resolve_failure_reason(db,r)
                attempts=[public_attempt(attempt_timing_state(db,r,now),now) for r in attempt_rows]
                for a in attempts:
                    if a.get('platform')=='unknown' and a.get('job_url'):
                        from .managed_context import platform_for_url
                        p=platform_for_url(a['job_url'])
                        if p!='unknown':a['platform']=p
                counts={'selected':len(rows),'current':sum(r['state']=='active' for r in rows),
                    'completed':sum(r['state'] in TERMINAL for r in rows),'remaining':sum(r['state']=='pending' for r in rows),
                    'blocked':sum(r['state'] in ('blocked','submission_unknown','interrupted') for r in rows),
                    'applied':sum(r['state'] in ('applied','already_applied') for r in rows)}
                current=dict(chosen,run_id=chosen['id'],attempts=attempts,jobs=rows,**counts)
                chosen_settings=json.loads(chosen['settings_json'])
                chosen_caps=json.loads(chosen['capabilities_json'] or '{}')
                current['requested_browser_mode']=chosen_settings.get('browser_mode','headed')
                current['observed_browser_mode']=chosen_caps.get('observed_browser_mode','unknown')
                current['requested_reasoning_effort']=chosen_settings.get('reasoning_effort','low')
                current['actual_reasoning_effort']=chosen_caps.get('reasoning_effort')
                current['observed_reasoning_effort']=chosen_caps.get('reasoning_effort')
                current['targets']=[dict(r) for r in db.execute('SELECT t.* FROM owned_targets t JOIN application_attempts a ON a.id=t.attempt_id WHERE a.run_id=? ORDER BY t.created_at,t.id',(chosen['id'],))]
                for target in current['targets']:
                    target['history']=[dict(r) for r in db.execute('SELECT * FROM target_history WHERE target_record_id=? ORDER BY created_at,id',(target['id'],))]
                current['budget_extensions']=[dict(r) for r in db.execute('SELECT e.* FROM budget_extensions e JOIN application_attempts a ON a.id=e.attempt_id WHERE a.run_id=? ORDER BY e.created_at,e.id',(chosen['id'],))]
                current['unclassified']=counts['selected']-counts['current']-counts['completed']-counts['remaining']
                focus=next((a for a in reversed(attempts) if not a['completed_at']),attempts[-1] if attempts else None)
                current['focused_context']=None
                if focus:
                    job=self._get(db,'jobs',focus['job_id'])
                    events=[dict(e) for e in db.execute('SELECT * FROM managed_events WHERE attempt_id=? ORDER BY observed_at DESC,recorded_at DESC,id DESC',(focus['id'],))]
                    payloads=[json.loads(e['payload_json']) for e in events]
                    latest=next((p for p in payloads if any(p.get(k) for k in ('phase','activity','page','url','tool_name'))),{})
                    issue=next((p.get('error_type') or p.get('reason_code') or p.get('category') for p in payloads if p.get('status') in ('failed','error','blocked','aborted')),None)
                    versions=json.loads(focus['versions_json'] or '{}')
                    from .managed_context import platform_for_url
                    current['focused_context']={'is_active':not bool(focus['completed_at']),'state':'active' if not focus['completed_at'] else 'last_completed',
                        'attempt_id':focus['id'],'job':{k:job[k] for k in ('id','company','title','url','metadata_json')},
                        'platform':focus.get('platform') or platform_for_url(job['url']),
                        'page':latest.get('page') or latest.get('url') or job['url'],'activity':latest.get('activity') or latest.get('phase') or latest.get('tool_name') or focus.get('activity'),
                        'worker_metadata':{k:versions.get(k) for k in ('skill_version','provider','model','protocol','reasoning_effort')},
                        'actual_reasoning_effort':versions.get('reasoning_effort'),
                        'latest_unresolved_issue':focus.get('failure_reason') or issue or (focus.get('evidence') if focus.get('outcome') not in ('applied','already_applied') else None),
                        'settings_hash':focus['settings_hash'],'uncertain_duration':focus['uncertain_duration']}
                    from .managed_reports import application_progress
                    current['focused_context']['progress']=application_progress(events,now=self.now(),ended_at=focus['completed_at'],
                        actions=[dict(a) for a in db.execute('SELECT * FROM managed_actions WHERE attempt_id=?',(focus['id'],))])
            schema=db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
        return {'health':dict(self.health(),schema_version=schema),'settings':self.settings_view(),
            'jobs':jobs,'runs':runs,'accounts':accounts,'candidates':candidates,'current_run':current,
            'lessons':lessons,'helpers':helpers,'assets':assets,'assessments':assessments,
            'document_selections':selections,'document_uploads':uploads,
            'local_runtime':self.sessions_view(),'answer_queue':self.answer_queue(),'dispatch_queue':self.queue_status(),
            'answer_library':self.answer_library(),
            'discovery':self.discovery_status()}
