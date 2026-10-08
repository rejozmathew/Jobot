"""Capacity-aware dispatch, automatic active-job pickup, and durable delayed retries."""
import json
from datetime import datetime, timedelta
from .managed_shared import ProtocolError, dumps, uid
from .managed_redaction import safe_text, provenance_text
from .job_duplicates import audit_duplicate_admission, record_skip

AUTOMATIC_ATTEMPT_HOURS = (0, 2, 4, 6, 24, 28)
AUTOMATIC_ATTEMPTS = len(AUTOMATIC_ATTEMPT_HOURS)
RETRY_OUTCOMES = frozenset({'interrupted', 'failed', 'blocked', 'submission_unknown'})


def attempt_schedule(rows):
    """Retry lineage lives in immutable request IDs; no historical outcomes change."""
    details = {}
    by_id = {row['id']: row for row in rows}
    starts = {}
    for row in rows:  # insertion order: a parent always precedes its retry
        parent_id = row['request_id'].removeprefix('automatic-retry:') if row['request_id'].startswith('automatic-retry:') else None
        parent = by_id.get(parent_id)
        number = details[parent_id]['attempt_number'] + 1 if parent_id in details else 1
        starts[row['id']] = starts.get(parent_id, row.get('started_at') or row['created_at'])
        due = row['created_at']
        if parent and parent['ended_at']:
            spacing = 4 if number >= AUTOMATIC_ATTEMPTS else 2
            offset = AUTOMATIC_ATTEMPT_HOURS[min(number, AUTOMATIC_ATTEMPTS)-1]
            due = max(datetime.fromisoformat(starts[row['id']]) + timedelta(hours=offset),
                      datetime.fromisoformat(parent['ended_at']) + timedelta(hours=spacing)).isoformat()
        if row.get('immediate_requested_at'):
            due = row['immediate_requested_at']
        details[row['id']] = {'attempt_number': number, 'next_attempt_at': due,
            'automatic_limit_reached': row['state'] == 'finished' and row['outcome'] in RETRY_OUTCOMES and number >= AUTOMATIC_ATTEMPTS}
    return details


class QueueServices:
    def _settle_reconciled_queue(self, db, attempt):
        """Same transaction as success; preserve running and historical dispatches."""
        from .managed_identity import RELATED
        return db.execute(RELATED+"UPDATE dispatch_queue SET state='finished',outcome='already_applied',detail=?,ended_at=? WHERE state='queued' AND identity_id=? AND job_id IN (SELECT id FROM related)",
            (attempt['job_id'],'Successful reconciliation of attempt '+str(attempt['id']),self.now(),attempt['identity_id'])).rowcount

    def queue_reconcile(self, *, identity_id, resume_asset_id):
        """Pick up active intake and schedule recovery; the dispatcher executes it."""
        added = []
        with self.tx() as db:
            candidate = self._get(db, 'candidates', identity_id)
            asset = self._get(db, 'document_assets', resume_asset_id)
            if candidate['state'] != 'active': raise ProtocolError('identity_inactive')
            if asset['identity_id'] != identity_id or asset['kind'] != 'resume' or asset['status'] != 'available':
                raise ProtocolError('asset_identity_mismatch')
            rows = [dict(r) for r in db.execute('SELECT * FROM dispatch_queue WHERE identity_id=? ORDER BY rowid', (identity_id,))]
            # Newly linked history can make an already queued alias a duplicate.
            # Settle pending work now, without touching active/historical dispatches.
            for row in rows:
                if row['state']!='queued':continue
                try:self._assert_not_suppressed(db,row['job_id'],identity_id=identity_id)
                except ProtocolError as exc:
                    if exc.code not in ('already_applied','job_canceled'):raise
                    record_skip(db,exc,identity_id,self.now(),'queue_reconcile')
                    row.update(state='finished',outcome='already_applied' if exc.code=='already_applied' else 'canceled')
                    db.execute("UPDATE dispatch_queue SET state='finished',outcome=?,detail=?,ended_at=? WHERE id=? AND state='queued'",
                        (row['outcome'],exc.code,self.now(),row['id']))
            latest = {r['job_id']: r for r in rows}
            schedule = attempt_schedule(rows)
            settings = self._settings_record(db)['values']
            jobs = db.execute("SELECT * FROM jobs WHERE disposition='active' AND status NOT IN ('applied','already_applied') ORDER BY created_at,rowid").fetchall()
            for job in jobs:
                old = latest.get(job['id'])
                restored = old and old['state'] == 'finished' and old['outcome'] == 'canceled'
                if old and not restored and (old['state'] != 'finished' or old['outcome'] not in RETRY_OUTCOMES or schedule[old['id']]['automatic_limit_reached']): continue
                # Preserve existing user-answer and policy holds; don't burn retries on them.
                if db.execute("SELECT 1 FROM application_questions WHERE job_id=? AND identity_id=? AND state='pending'", (job['id'], identity_id)).fetchone(): continue
                if db.execute('SELECT 1 FROM application_sessions WHERE job_id=? AND ended_at IS NULL', (job['id'],)).fetchone(): continue
                if job['eligibility'] == 'excluded': continue
                if job['eligibility'] == 'held' and job['intervention_reason']: continue
                if job['eligibility'] == 'held' and str(json.loads(job['metadata_json'] or '{}').get('verdict', '')).strip().casefold() == 'skip': continue
                db.execute('SAVEPOINT auto_pickup')
                try:
                    # An active intake row no longer needs a second, manual enqueue click.
                    if job['eligibility'] == 'held': db.execute("UPDATE jobs SET eligibility='ready' WHERE id=?", (job['id'],))
                    self._eligible(db, job['id'], settings, identity_id=identity_id)
                    item_id = uid()
                    request = 'automatic-retry:' + old['id'] if old and not restored else 'automatic-intake:' + (old['id'] if restored else job['id'])
                    origin='automatic_retry' if old and not restored else 'automatic_restore' if restored else 'automatic_intake'
                    db.execute("INSERT INTO dispatch_queue(id,request_id,job_id,identity_id,resume_asset_id,state,created_at,enqueue_origin,producer) VALUES (?,?,?,?,?,'queued',?,?,?)",
                        (item_id, request, job['id'], identity_id, resume_asset_id, self.now(),origin,'queue_worker'))
                    added.append(item_id)
                except ProtocolError as exc:
                    db.execute('ROLLBACK TO auto_pickup')
                    if exc.code not in ('already_applied','job_canceled','company_excluded','job_archived','not_ready','market_incompatible'): raise
                    record_skip(db,exc,identity_id,self.now(),'queue_reconcile')
                finally:
                    db.execute('RELEASE auto_pickup')
        return {'added': added}

    @audit_duplicate_admission
    def queue_enqueue(self, *, job_ids, identity_id, resume_asset_id, request_id, retry=False,
                      enqueue_origin=None, producer=None, discovery_run_id=None, discovery_profile=None, start_now=False):
        if (not isinstance(job_ids, list) or not job_ids or len(job_ids)>100
                or any(not isinstance(j, str) for j in job_ids)
                or not isinstance(request_id, str) or not request_id or type(retry) is not bool or type(start_now) is not bool):
            raise ProtocolError('invalid_queue_request')
        items=[]
        with self.tx() as db:
            candidate=self._get(db,'candidates',identity_id)
            asset=self._get(db,'document_assets',resume_asset_id)
            if candidate['state']!='active':raise ProtocolError('identity_inactive')
            if asset['identity_id']!=identity_id or asset['kind']!='resume' or asset['status']!='available':
                raise ProtocolError('asset_identity_mismatch')
            for job_id in dict.fromkeys(job_ids):
                job=self._get(db,'jobs',job_id)
                self._assert_not_suppressed(db,job_id,identity_id=identity_id)
                old=db.execute('SELECT * FROM dispatch_queue WHERE request_id=? AND job_id=?',(request_id,job_id)).fetchone()
                if not old and start_now:
                    old=db.execute('''SELECT q.* FROM dispatch_queue q JOIN dispatch_immediate_requests r ON r.item_id=q.id
                        WHERE r.request_id=? AND r.job_id=?''',(request_id,job_id)).fetchone()
                if old and (old['identity_id']!=identity_id or old['resume_asset_id']!=resume_asset_id):
                    raise ProtocolError('idempotency_conflict')
                if not old:
                    old=db.execute("SELECT * FROM dispatch_queue WHERE job_id=? AND identity_id=? AND (?=0 OR state!='finished') ORDER BY created_at DESC,id DESC LIMIT 1",
                                   (job_id,identity_id,int(retry))).fetchone()
                if old:
                    items.append(dict(old));continue
                if job['eligibility']=='held':
                    db.execute("UPDATE jobs SET eligibility='ready' WHERE id=?",(job_id,))
                self._eligible(db,job_id,self._settings_record(db)['values'],identity_id=identity_id)
                item_id=uid()
                context=tuple(provenance_text(v) for v in (enqueue_origin,producer,discovery_run_id,discovery_profile))
                db.execute("INSERT INTO dispatch_queue(id,request_id,job_id,identity_id,resume_asset_id,state,created_at,enqueue_origin,producer,discovery_run_id,discovery_profile) VALUES (?,?,?,?,?,'queued',?,?,?,?,?)",
                           (item_id,request_id,job_id,identity_id,resume_asset_id,self.now(),*context))
                items.append(dict(self._get(db,'dispatch_queue',item_id)))
            if start_now:
                for item in items:
                    receipt=db.execute('INSERT OR IGNORE INTO dispatch_immediate_requests(request_id,job_id,item_id,requested_at) VALUES (?,?,?,?)',
                               (request_id,item['job_id'],item['id'],self.now()))
                    if item['state']=='queued':
                        if receipt.rowcount:
                            db.execute('UPDATE dispatch_queue SET immediate_requested_at=? WHERE id=?',
                                       (self.now(),item['id']))
                        db.execute('UPDATE dispatch_control SET wake_requested=1 WHERE id=1')
                items=[dict(self._get(db,'dispatch_queue',item['id'])) for item in items]
        return {'items':items, **({'queue':self.queue_status()} if start_now else {})}

    def queue_status(self):
        with self.read() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dispatch_queue'").fetchone():
                return {'installed':False,'enabled':False,'worker_online':False,'counts':{},'items':[]}
            control=dict(db.execute('SELECT * FROM dispatch_control WHERE id=1').fetchone())
            counts={r['state']:r['count'] for r in db.execute('SELECT state,COUNT(*) AS count FROM dispatch_queue GROUP BY state')}
            items=[dict(r) for r in db.execute('SELECT q.*,j.company,j.title,j.url FROM dispatch_queue q JOIN jobs j ON j.id=q.job_id ORDER BY q.created_at DESC,q.id DESC LIMIT 100')]
            # Row labels need the latest request even when it is outside recent history.
            latest={r['job_id']:dict(r) for r in db.execute('''SELECT id,job_id,state,outcome,detail,created_at,request_id,
                enqueue_origin,producer,discovery_run_id,discovery_profile,immediate_requested_at
                FROM dispatch_queue WHERE rowid IN (SELECT MAX(rowid) FROM dispatch_queue GROUP BY job_id)''')}
            schedule=attempt_schedule([dict(r) for r in db.execute('SELECT * FROM dispatch_queue ORDER BY rowid')])
            waiting=[dict(r) for r in db.execute("SELECT * FROM dispatch_queue WHERE state='queued'")]
            concurrency=self._settings_record(db)['values']['application_concurrency']
            active_items=[dict(r) for r in db.execute("SELECT id,job_id,started_at,session_id FROM dispatch_queue WHERE state='dispatched' ORDER BY started_at,rowid")]
        now=datetime.fromisoformat(self.now())
        for item in [*items,*latest.values()]:
            item.update(schedule[item['id']])
            item['waiting_for_retry']=item['state']=='queued' and datetime.fromisoformat(item['next_attempt_at'])>now
        ready=sum(datetime.fromisoformat(schedule[r['id']]['next_attempt_at'])<=now for r in waiting)
        next_job=min((schedule[r['id']]['next_attempt_at'] for r in waiting),default=None)
        from .workspace_process import process_matches
        identity=json.loads(control.pop('worker_identity_json') or '{}')
        heartbeat=control.get('heartbeat_at')
        age=(datetime.fromisoformat(self.now())-datetime.fromisoformat(heartbeat)).total_seconds() if heartbeat else None
        return {**control,'installed':True,'enabled':bool(control['enabled']),
                'automation_paused':bool(control.get('automation_paused',False)),
                'automation_pause_supported':'automation_paused' in control,
                'worker_online':bool(identity and process_matches(identity) and age is not None and age<30),
                'counts':counts,'ready_count':ready,'scheduled_count':len(waiting)-ready,'next_job_at':next_job,
                'immediate_count':sum(bool(r['immediate_requested_at']) for r in waiting),
                'automatic_attempt_limit':AUTOMATIC_ATTEMPTS,
                'concurrency_limit':concurrency,'active_count':len(active_items),'active_items':active_items,
                'items':items,'latest_by_job':latest,'selection':getattr(self,'dispatch_selection',None)}

    def queue_control(self, *, command):
        if command not in ('run_next','pause','resume','pause_all','resume_all'):raise ProtocolError('invalid_queue_control')
        selection=getattr(self,'dispatch_selection',None)
        if command in ('run_next','resume') and selection:self.queue_reconcile(**selection)
        with self.tx() as db:
            if command in ('pause_all','resume_all'):
                db.execute('UPDATE dispatch_control SET automation_paused=? WHERE id=1',(int(command=='pause_all'),))
            elif command=='run_next':db.execute('UPDATE dispatch_control SET wake_requested=1 WHERE id=1')
            else:db.execute('UPDATE dispatch_control SET enabled=? WHERE id=1',(int(command=='resume'),))
        return self.queue_status()

    def queue_take(self, *, concurrency_limit=None):
        """Only the dispatcher calls this, under its OS lock; no model in Service."""
        with self.tx() as db:
            if db.execute('SELECT automation_paused FROM dispatch_control WHERE id=1').fetchone()[0]:return None
            limit=self._settings_record(db)['values']['application_concurrency']
            if concurrency_limit is not None:limit=min(limit,concurrency_limit)
            if db.execute("SELECT COUNT(*) FROM dispatch_queue WHERE state='dispatched'").fetchone()[0]>=limit:return None
            schedule=attempt_schedule([dict(r) for r in db.execute('SELECT * FROM dispatch_queue ORDER BY rowid')])
            for row in db.execute("""SELECT * FROM dispatch_queue WHERE state='queued'
                    ORDER BY immediate_requested_at IS NULL,immediate_requested_at,
                    (SELECT MAX(r.rowid) FROM dispatch_immediate_requests r WHERE r.item_id=dispatch_queue.id),
                    CASE WHEN request_id LIKE 'automatic-retry:%' THEN 1 ELSE 0 END,
                    created_at,rowid""").fetchall():
                if datetime.fromisoformat(schedule[row['id']]['next_attempt_at'])>datetime.fromisoformat(self.now()):continue
                try:self._eligible(db,row['job_id'],self._settings_record(db)['values'],identity_id=row['identity_id'])
                except ProtocolError as exc:
                    record_skip(db,exc,row['identity_id'],self.now(),'queue_take')
                    db.execute("UPDATE dispatch_queue SET state='finished',outcome=?,detail=?,ended_at=? WHERE id=?",
                               ('already_applied' if exc.code=='already_applied' else 'canceled' if exc.code=='job_canceled'
                                else 'skipped',exc.code,self.now(),row['id']))
                    continue
                db.execute("UPDATE dispatch_queue SET state='dispatched',started_at=? WHERE id=?",(self.now(),row['id']))
                return dict(self._get(db,'dispatch_queue',row['id']))
        return None

    def queue_complete(self, item_id, *, outcome, detail='', session_id=None):
        with self.tx() as db:
            item=self._get(db,'dispatch_queue',item_id)
            if item['state']=='finished':return dict(item)
            db.execute("UPDATE dispatch_queue SET state='finished',outcome=?,detail=?,session_id=?,ended_at=? WHERE id=?",
                       (outcome,safe_text(detail),session_id,self.now(),item_id))
            return dict(self._get(db,'dispatch_queue',item_id))

    def queue_heartbeat(self, identity, *, current_item=None, detail='Waiting for queued work'):
        with self.tx() as db:
            db.execute('UPDATE dispatch_control SET worker_identity_json=?,heartbeat_at=?,current_item=?,detail=? WHERE id=1',
                       (dumps(identity),self.now(),current_item,safe_text(detail)))
