"""Explicit single-job dispatch requests. Intake alone never starts execution."""
import json
from datetime import datetime
from .managed_shared import ProtocolError, dumps, uid
from .managed_redaction import safe_text


class QueueServices:
    def queue_enqueue(self, *, job_ids, identity_id, resume_asset_id, request_id, retry=False):
        if (not isinstance(job_ids, list) or not job_ids or len(job_ids)>100
                or any(not isinstance(j, str) for j in job_ids)
                or not isinstance(request_id, str) or not request_id or type(retry) is not bool):
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
                self._assert_not_suppressed(db,job_id)
                old=db.execute('SELECT * FROM dispatch_queue WHERE request_id=? AND job_id=?',(request_id,job_id)).fetchone()
                if old and (old['identity_id']!=identity_id or old['resume_asset_id']!=resume_asset_id):
                    raise ProtocolError('idempotency_conflict')
                if not old:
                    old=db.execute("SELECT * FROM dispatch_queue WHERE job_id=? AND identity_id=? AND (?=0 OR state!='finished') ORDER BY created_at DESC,id DESC LIMIT 1",
                                   (job_id,identity_id,int(retry))).fetchone()
                if old:
                    items.append(dict(old));continue
                if job['eligibility']=='held':
                    db.execute("UPDATE jobs SET eligibility='ready' WHERE id=?",(job_id,))
                self._eligible(db,job_id,self._settings_record(db)['values'])
                item_id=uid()
                db.execute("INSERT INTO dispatch_queue(id,request_id,job_id,identity_id,resume_asset_id,state,created_at) VALUES (?,?,?,?,?,'queued',?)",
                           (item_id,request_id,job_id,identity_id,resume_asset_id,self.now()))
                items.append(dict(self._get(db,'dispatch_queue',item_id)))
        return {'items':items}

    def queue_status(self):
        with self.tx() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dispatch_queue'").fetchone():
                return {'installed':False,'enabled':False,'worker_online':False,'counts':{},'items':[]}
            control=dict(db.execute('SELECT * FROM dispatch_control WHERE id=1').fetchone())
            counts={r['state']:r['count'] for r in db.execute('SELECT state,COUNT(*) AS count FROM dispatch_queue GROUP BY state')}
            items=[dict(r) for r in db.execute('SELECT q.*,j.company,j.title,j.url FROM dispatch_queue q JOIN jobs j ON j.id=q.job_id ORDER BY q.created_at DESC,q.id DESC LIMIT 100')]
        from .workspace_process import process_matches
        identity=json.loads(control.pop('worker_identity_json') or '{}')
        heartbeat=control.get('heartbeat_at')
        age=(datetime.fromisoformat(self.now())-datetime.fromisoformat(heartbeat)).total_seconds() if heartbeat else None
        return {**control,'installed':True,'enabled':bool(control['enabled']),
                'worker_online':bool(identity and process_matches(identity) and age is not None and age<30),
                'counts':counts,'items':items,'selection':getattr(self,'dispatch_selection',None)}

    def queue_control(self, *, command):
        if command not in ('run_next','pause','resume'):raise ProtocolError('invalid_queue_control')
        with self.tx() as db:
            if command=='run_next':db.execute('UPDATE dispatch_control SET wake_requested=1 WHERE id=1')
            else:db.execute('UPDATE dispatch_control SET enabled=? WHERE id=1',(int(command=='resume'),))
        return self.queue_status()

    def queue_take(self):
        """Only the dispatcher calls this, under its OS lock; no model in Service."""
        with self.tx() as db:
            if db.execute("SELECT 1 FROM dispatch_queue WHERE state='dispatched'").fetchone():return None
            for row in db.execute("SELECT * FROM dispatch_queue WHERE state='queued' ORDER BY created_at,rowid").fetchall():
                try:self._eligible(db,row['job_id'],self._settings_record(db)['values'])
                except ProtocolError as exc:
                    db.execute("UPDATE dispatch_queue SET state='finished',outcome=?,detail=?,ended_at=? WHERE id=?",
                               ('already_applied' if exc.code=='already_applied' else 'skipped',exc.code,self.now(),row['id']))
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
