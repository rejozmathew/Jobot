"""Explicit preview/backup/additive archive. Original histories are never rewritten."""
from contextlib import closing
import hashlib
from .managed_data import open_source, _verify_source, backup
from .managed_shared import ProtocolError, dumps


class ArchiveServices:
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
