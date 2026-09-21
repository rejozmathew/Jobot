"""Explicit preview/backup/additive archive. Original histories are never rewritten."""
from contextlib import closing
import hashlib
from .managed_data import open_source, _verify_source, backup
from .managed_shared import ProtocolError, dumps
from .managed_identity import linked_jobs
from .managed_redaction import safe_text


class ArchiveServices:
    def set_job_disposition(self, *, job_ids, disposition, reason=''):
        """Reversible operator cleanup; retain identities, accounts and outcomes."""
        if (not isinstance(job_ids,list) or not job_ids
                or any(not isinstance(j,str) or not j for j in job_ids)
                or disposition not in ('active','canceled') or not isinstance(reason,str)
                or (disposition=='canceled' and not reason.strip())):
            raise ProtocolError('invalid_job_disposition')
        reason=safe_text(reason.strip()) if disposition=='canceled' else None
        with self.tx() as db:
            selected=set()
            for job_id in job_ids:
                self._get(db,'jobs',job_id)
                selected.update(linked_jobs(db,job_id))
            # Recheck the entire selection under the writer lock: an application
            # may have submitted since the dashboard last loaded. Do not change
            # either its final disposition or an earlier cancellation reason.
            skipped=[]
            if disposition=='canceled':
                for job_id in sorted(selected):
                    try:self._assert_not_suppressed(db,job_id)
                    except ProtocolError as exc:
                        if exc.code not in ('already_applied','job_canceled'):raise
                        skipped.append(job_id)
                selected.difference_update(skipped)
            now=self.now();stop_runs=set()
            for job_id in sorted(selected):
                job=self._get(db,'jobs',job_id)
                if job['disposition']!=disposition or job['disposition_reason']!=reason:
                    db.execute('UPDATE jobs SET disposition=?,disposition_reason=?,disposition_at=? WHERE id=?',
                               (disposition,reason,now,job_id))
                if disposition!='canceled':continue
                db.execute("UPDATE dispatch_queue SET state='finished',outcome='canceled',detail=?,ended_at=? WHERE job_id=? AND state='queued'",
                           (reason,now,job_id))
                db.execute("UPDATE answer_retry_requests SET state='canceled' WHERE job_id=? AND state='queued'",(job_id,))
                # The existing stop lifecycle owns active browser shutdown. Never
                # rewrite attempt evidence or claim an in-flight submit was prevented.
                sessions=db.execute('SELECT * FROM application_sessions WHERE job_id=? AND ended_at IS NULL',(job_id,)).fetchall()
                for session in sessions:
                    if session['run_id']:stop_runs.add(session['run_id'])
                    elif session['workspace_id'] is None:
                        db.execute("UPDATE application_sessions SET state='stopped',reason=?,ended_at=? WHERE id=?",
                                   ('Canceled by operator',now,session['id']))
                stop_runs.update(r[0] for r in db.execute("SELECT run_id FROM run_jobs WHERE job_id=? AND state='active'",(job_id,)))
                pending=[r[0] for r in db.execute("SELECT run_id FROM run_jobs WHERE job_id=? AND state='pending'",(job_id,))]
                db.execute("UPDATE run_jobs SET state='skipped' WHERE job_id=? AND state='pending'",(job_id,))
                for run_id in pending:
                    if run_id in stop_runs:continue
                    if not db.execute("SELECT 1 FROM run_jobs WHERE run_id=? AND state IN ('active','pending')",(run_id,)).fetchone():
                        db.execute("UPDATE runs SET state='completed',ended_at=? WHERE id=? AND state!='completed'",(now,run_id))
            requested=[]
            for run_id in sorted(stop_runs):
                run=self._get(db,'runs',run_id)
                if run['state']!='completed' and run['control']!='stopped':
                    self._control(db,run,command='stop');requested.append(run_id)
            return {'jobs':[dict(self._get(db,'jobs',j)) for j in sorted(selected)],
                    'stop_requested_run_ids':requested,'skipped_job_ids':skipped}

    def _archive_preview(self,db,job_ids):
        if not isinstance(job_ids,list) or not job_ids or any(not isinstance(j,str) or not j for j in job_ids) or len(set(job_ids))!=len(job_ids):
            raise ProtocolError('invalid_archive_selection')
        job_ids=sorted(job_ids)
        _verify_source(db,self.instance_id)
        if db.execute('SELECT 1 FROM managed_actions WHERE ended_at IS NULL').fetchone():raise ProtocolError('runtime_not_quiescent')
        counts={'jobs':len(job_ids),'attempts':0,'sources':0}
        for job_id in job_ids:
            job=self._get(db,'jobs',job_id)
            if job['status'] not in ('applied','already_applied','ready_for_review','blocked','failed','skipped'):
                raise ProtocolError('archive_requires_completed_job')
            if db.execute('SELECT 1 FROM job_archives WHERE job_id=?',(job_id,)).fetchone():raise ProtocolError('already_archived')
            if db.execute('SELECT 1 FROM application_attempts WHERE job_id=? AND completed_at IS NULL',(job_id,)).fetchone():raise ProtocolError('runtime_not_quiescent')
            if db.execute("SELECT 1 FROM run_jobs j JOIN runs r ON r.id=j.run_id WHERE j.job_id=? AND j.state IN ('pending','active') AND r.control!='stopped'",(job_id,)).fetchone():raise ProtocolError('archive_job_reserved')
            counts['attempts']+=db.execute('SELECT COUNT(*) FROM application_attempts WHERE job_id=?',(job_id,)).fetchone()[0]
            counts['sources']+=db.execute('SELECT COUNT(*) FROM job_sources WHERE job_id=?',(job_id,)).fetchone()[0]
        # Bind approval to selection, instance, and the full consistent logical snapshot,
        # including WAL contents. Never print/export the hashed source material.
        digest=hashlib.sha256(dumps([self.instance_id,job_ids]).encode())
        for line in db.iterdump():digest.update(line.encode());digest.update(b'\n')
        return {'instance_id':self.instance_id,'job_ids':job_ids,'counts':counts,'preview_hash':digest.hexdigest()}

    def preview_archive(self,job_ids):
        with closing(open_source(self.db_path)) as db:
            db.execute('BEGIN')
            return self._archive_preview(db,job_ids)

    def archive(self,job_ids,preview_hash,backup_path):
        # Reserve the writer lock before revalidation and hold it across online backup.
        # No writes occur before backup, so its separate reader sees this exact snapshot.
        with self.tx() as db:
            preview=self._archive_preview(db,job_ids)
            if not isinstance(preview_hash,str) or preview_hash!=preview['preview_hash']:raise ProtocolError('archive_preview_changed')
            saved=backup(self.db_path,backup_path,instance_id=self.instance_id)
            now=self.now()
            for job_id in preview['job_ids']:
                db.execute('INSERT INTO job_archives VALUES (?,?,?,?,?)',(job_id,now,preview_hash,saved['destination'],saved['sha256']))
            return dict(preview,backup=saved,archived_at=now)
