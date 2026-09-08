"""Externally produced document/assessment metadata; never generates, fetches or uploads files."""
from datetime import datetime
import hashlib
import json
import math
import re
from urllib.parse import urlsplit
from .managed_shared import ProtocolError,uid,dumps
from .managed_redaction import reject_secrets,safe_text
from .managed_learning import public_record

HASH=re.compile(r'^[0-9a-fA-F]{64}$')
KINDS={'resume','cover_letter'}
RECOMMENDATIONS={'Strong apply','Apply','Apply with caveats','Skip'}


def local_asset_path(asset):
    """Resolve and hash-check one explicitly selected local document; never extract it."""
    from pathlib import Path
    from urllib.parse import unquote
    from urllib.request import url2pathname
    url=urlsplit(asset['storage_ref'])
    if url.scheme!='file' or url.netloc or url.query or url.fragment:
        raise ValueError('Selected resume must be a verified local file')
    path=Path(url2pathname(unquote(url.path)))
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=asset['sha256']:
        raise ValueError('Selected resume is missing or changed')
    return path


def checked_hash(value):
    if not isinstance(value,str) or not HASH.fullmatch(value):raise ProtocolError('invalid_hash')
    return value


class DocumentServices:
    def register_asset(self,*,identity_id,kind,version,storage_ref,sha256,provenance):
        checked_hash(sha256);reject_secrets(provenance)
        if kind not in KINDS or not isinstance(version,str) or not version or not isinstance(provenance,dict) or not provenance:raise ProtocolError('invalid_asset_metadata')
        if not isinstance(storage_ref,str) or len(storage_ref)>1000:raise ProtocolError('invalid_storage_reference')
        ref=urlsplit(storage_ref)
        if ref.scheme not in ('storage','asset','vault','file','onedrive') or ref.username or ref.password or ref.query or ref.fragment:raise ProtocolError('private_storage_reference_required')
        values=(identity_id,kind,version,storage_ref,sha256,dumps(provenance))
        with self.tx() as db:
            self._get(db,'candidates',identity_id)
            old=db.execute('SELECT * FROM document_assets WHERE identity_id=? AND kind=? AND version=?',(identity_id,kind,version)).fetchone()
            if old:
                if tuple(old[k] for k in ('identity_id','kind','version','storage_ref','sha256','provenance_json'))!=values:raise ProtocolError('asset_version_immutable')
                return public_record(old)
            aid=uid();db.execute('INSERT INTO document_assets VALUES (?,?,?,?,?,?,?,?,?)',(aid,)+values+('available',self.now()))
            return public_record(self._get(db,'document_assets',aid))

    def select_asset(self,*,asset_id,job_id,attempt_id=None):
        with self.tx() as db:
            asset=self._get(db,'document_assets',asset_id);self._get(db,'jobs',job_id)
            if attempt_id is None:
                active=db.execute('SELECT identity_id FROM application_attempts WHERE job_id=? AND completed_at IS NULL',(job_id,)).fetchall()
                if any(r['identity_id']!=asset['identity_id'] for r in active):raise ProtocolError('asset_identity_mismatch')
            if attempt_id is not None:
                attempt=self._get(db,'application_attempts',attempt_id)
                if attempt['job_id']!=job_id or attempt['identity_id']!=asset['identity_id']:raise ProtocolError('asset_identity_mismatch')
                if attempt['completed_at']:raise ProtocolError('attempt_completed')
            previous=db.execute('SELECT s.* FROM document_selections s JOIN document_assets d ON d.id=s.asset_id WHERE s.job_id=? AND s.attempt_id IS ? AND d.identity_id=? AND d.kind=? ORDER BY s.created_at DESC,s.rowid DESC LIMIT 1',(job_id,attempt_id,asset['identity_id'],asset['kind'])).fetchone()
            if previous and previous['asset_id']==asset_id:return dict(previous)
            sid=uid();db.execute('INSERT INTO document_selections VALUES (?,?,?,?,?,?)',(sid,asset_id,job_id,attempt_id,'selected',self.now()))
            return dict(self._get(db,'document_selections',sid))

    def _documents_status(self,db,job_id,identity_id,attempt_id=None):
        job=self._get(db,'jobs',job_id);self._get(db,'candidates',identity_id)
        if attempt_id is not None:
            attempt=self._get(db,'application_attempts',attempt_id)
            if attempt['job_id']!=job_id or attempt['identity_id']!=identity_id:raise ProtocolError('asset_identity_mismatch')
        required=json.loads(job['metadata_json'] or '{}').get('required_documents',[])
        if not isinstance(required,list) or any(k not in KINDS for k in required):raise ProtocolError('invalid_required_documents')
        rows=db.execute('SELECT a.* FROM document_assets a JOIN document_selections s ON s.asset_id=a.id WHERE s.job_id=? AND a.identity_id=? AND (s.attempt_id IS NULL OR s.attempt_id=?) ORDER BY (s.attempt_id IS NOT NULL) DESC,s.created_at DESC,s.rowid DESC',(job_id,identity_id,attempt_id)).fetchall()
        selected={}
        for row in rows:selected.setdefault(row['kind'],dict(public_record(row),selection_state='selected',availability_source='external_producer'))
        missing=[k for k in required if k not in selected]
        default_resume = db.execute("SELECT * FROM document_assets WHERE identity_id=? AND kind='resume' ORDER BY created_at DESC LIMIT 1",(identity_id,)).fetchone()
        return {'ready':not missing,'missing':missing,'assets':list(selected.values()),
                'default_resume':public_record(default_resume) if default_resume else None}

    def documents_status(self,job_id,identity_id,attempt_id=None):
        with self.tx() as db:return self._documents_status(db,job_id,identity_id,attempt_id)

    def report_upload(self,*,attempt_id,worker_id,fence,asset_id,status,evidence):
        if status not in ('upload_attempted','upload_confirmed') or not isinstance(evidence,str) or not evidence.strip():raise ProtocolError('invalid_upload_event')
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence)
            asset=self._get(db,'document_assets',asset_id)
            if asset['identity_id']!=a['identity_id']:raise ProtocolError('asset_identity_mismatch')
            if not db.execute('SELECT 1 FROM document_selections WHERE asset_id=? AND job_id=? AND (attempt_id IS NULL OR attempt_id=?)',(asset_id,a['job_id'],attempt_id)).fetchone():raise ProtocolError('asset_not_selected')
            old=db.execute('SELECT * FROM document_uploads WHERE asset_id=? AND attempt_id=? ORDER BY rowid DESC LIMIT 1',(asset_id,attempt_id)).fetchone()
            if status=='upload_confirmed' and (not old or old['status'] not in ('upload_attempted','upload_confirmed')):raise ProtocolError('upload_not_attempted')
            if old and old['status']==status:return dict(old,version=asset['version'],sha256=asset['sha256'])
            if old and old['status']=='upload_confirmed':raise ProtocolError('confirmed_upload_immutable')
            rid=uid();db.execute('INSERT INTO document_uploads VALUES (?,?,?,?,?,?)',(rid,asset_id,attempt_id,status,safe_text(evidence),self.now()))
            return dict(self._get(db,'document_uploads',rid),version=asset['version'],sha256=asset['sha256'])

    def register_assessment(self,*,job_id,jd_hash,resume_hash,profile_hash,evaluator,model,rubric,score,scale_min,scale_max,recommendation,reasons,evaluated_at):
        for value in (jd_hash,resume_hash,profile_hash):checked_hash(value)
        reject_secrets([evaluator,model,rubric,reasons])
        if not all(isinstance(v,str) and v.strip() and len(v)<=250 for v in (evaluator,model,rubric)):raise ProtocolError('invalid_assessment_provenance')
        if not all(type(v) in (int,float) and math.isfinite(v) for v in (scale_min,scale_max)) or scale_min>=scale_max:raise ProtocolError('invalid_assessment_scale')
        if score is not None and (type(score) not in (int,float) or not math.isfinite(score) or not scale_min<=score<=scale_max):raise ProtocolError('invalid_assessment_score')
        if recommendation not in RECOMMENDATIONS or not isinstance(reasons,list) or len(reasons)>30 or any(not isinstance(v,str) for v in reasons):raise ProtocolError('invalid_assessment')
        try:
            when=datetime.fromisoformat(evaluated_at.replace('Z','+00:00'))
            if when.tzinfo is None:raise ValueError()
        except (AttributeError,ValueError):raise ProtocolError('invalid_assessment_time')
        values=(job_id,jd_hash,resume_hash,profile_hash,evaluator,model,rubric,score,scale_min,scale_max,recommendation,dumps([safe_text(r) for r in reasons]),evaluated_at)
        rid=hashlib.sha256(dumps(values).encode()).hexdigest()
        with self.tx() as db:
            self._get(db,'jobs',job_id)
            db.execute('INSERT OR IGNORE INTO match_assessments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,)+values+(self.now(),))
            return public_record(self._get(db,'match_assessments',rid))

    @staticmethod
    def _assessment(db,job_id):
        row=db.execute('SELECT * FROM match_assessments WHERE job_id=? ORDER BY julianday(evaluated_at) DESC,rowid DESC LIMIT 1',(job_id,)).fetchone()
        return public_record(row) if row else None
