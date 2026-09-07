"""Advisory lessons and versioned helper references; no code execution or fact mutation."""
import hashlib
import json
from pathlib import Path
import re
from .managed_shared import ProtocolError,uid,dumps
from .managed_redaction import reject_secrets,safe_text

ROOT=Path(__file__).resolve().parents[1]
HASH=re.compile(r'^[0-9a-fA-F]{64}$')

def scope_checked(scope):
    if not isinstance(scope,dict) or set(scope)-{'platform','namespace'} or any(not isinstance(v,str) or not v or len(v)>250 for v in scope.values()):raise ProtocolError('invalid_learning_scope')
    reject_secrets(scope)
    return scope

def matches(scope,platform,namespace):
    return (not scope.get('platform') or scope['platform']==platform) and (not scope.get('namespace') or scope['namespace']==namespace)

def public_record(row):
    result=dict(row)
    for key in list(result):
        if key.endswith('_json'):result[key[:-5]]=json.loads(result.pop(key))
    return result


class LearningServices:
    def observe_owned_lesson(self,*,attempt_id,worker_id,fence,condition,action,scope,expected_result,kind='procedure'):
        if kind!='procedure':raise ProtocolError('operator_fact_review_required')
        with self.tx() as db:self._owner(db,attempt_id,worker_id,fence,completed=True)
        return self.lesson_observe(condition=condition,action=action,scope=scope,expected_result=expected_result,attempt_ids=[attempt_id],kind=kind)

    def _lesson(self,db,lesson_id):
        row=public_record(self._get(db,'lessons',lesson_id))
        history=[dict(r) for r in db.execute('SELECT * FROM lesson_history WHERE lesson_id=? ORDER BY id',(lesson_id,))]
        for h in history:
            if h['success'] is not None:h['success']=bool(h['success'])
        return dict(row,history=history,advisory_only=True)

    def lesson_observe(self,*,condition,action,scope,expected_result,attempt_ids,kind='procedure'):
        scope_checked(scope);reject_secrets([condition,action,expected_result])
        if kind not in ('procedure','candidate_fact','company_observation') or not all(isinstance(x,str) and x.strip() for x in (condition,action,expected_result)):raise ProtocolError('invalid_lesson')
        if not isinstance(attempt_ids,list) or len(attempt_ids)>30 or any(type(x) is not int for x in attempt_ids):raise ProtocolError('invalid_supporting_attempts')
        with self.tx() as db:
            for aid in attempt_ids:self._get(db,'application_attempts',aid)
            key=uid();db.execute('INSERT INTO lessons VALUES (?,?,?,?,?,?,?,?,?)',(key,kind,safe_text(condition),safe_text(action),dumps(scope),safe_text(expected_result),dumps(attempt_ids),'candidate',self.now()))
            return self._lesson(db,key)

    def lesson_set_status(self,lesson_id,status,*,reason):
        if status not in ('active','demoted','retired') or not isinstance(reason,str) or not reason.strip():raise ProtocolError('invalid_lesson_transition')
        with self.tx() as db:
            lesson=self._get(db,'lessons',lesson_id)
            if status=='active' and (lesson['kind']!='procedure' or not json.loads(lesson['attempt_ids_json'])):raise ProtocolError('procedural_verification_required')
            db.execute('UPDATE lessons SET status=? WHERE id=?',(status,lesson_id))
            db.execute('INSERT INTO lesson_history(lesson_id,status,reason,created_at) VALUES (?,?,?,?)',(lesson_id,status,safe_text(reason),self.now()))
            return self._lesson(db,lesson_id)

    def lesson_record_outcome(self,lesson_id,attempt_id,success,reason):
        if type(success) is not bool or not isinstance(reason,str) or not reason:raise ProtocolError('invalid_lesson_outcome')
        with self.tx() as db:
            lesson=self._get(db,'lessons',lesson_id);self._get(db,'application_attempts',attempt_id)
            if lesson['kind']!='procedure':raise ProtocolError('not_procedural_learning')
            db.execute('INSERT INTO lesson_history(lesson_id,attempt_id,success,reason,created_at) VALUES (?,?,?,?,?)',(lesson_id,attempt_id,int(success),safe_text(reason),self.now()))
            return self._lesson(db,lesson_id)

    def lessons_for_context(self,platform,namespace,limit=3):
        if type(limit) is not int or limit<1:raise ProtocolError('invalid_limit')
        with self.tx() as db:
            rows=db.execute("SELECT * FROM lessons WHERE status='active' AND kind='procedure' ORDER BY created_at DESC,id").fetchall()
            selected=[r for r in rows if matches(json.loads(r['scope_json']),platform,namespace)][:min(limit,5)]
            return [self._lesson(db,r['id']) for r in selected]

    def _helper_path(self,path,sha256):
        if not isinstance(path,str) or not isinstance(sha256,str) or not HASH.fullmatch(sha256):raise ProtocolError('invalid_helper_reference')
        p=Path(path);p=(ROOT/p).resolve() if not p.is_absolute() else p.resolve()
        if not (p.is_relative_to(ROOT) or p.is_relative_to(self.db_path.parent)) or p.suffix not in ('.py','.js','.md','.json'):raise ProtocolError('helper_path_not_allowed')
        if not p.is_file():raise ProtocolError('helper_missing')
        if p.stat().st_size>1_000_000:raise ProtocolError('helper_too_large')
        if hashlib.sha256(p.read_bytes()).hexdigest().lower()!=sha256.lower():raise ProtocolError('helper_hash_mismatch')
        return p

    def helper_register(self,*,helper_id,version,capability,path,sha256,scope,preconditions,limitations,tests):
        scope_checked(scope);reject_secrets([helper_id,version,capability,scope,preconditions,limitations,tests])
        if not all(isinstance(v,str) and v for v in (helper_id,version,capability)) or capability in ('policy_override','change_credentials','change_submit_permission','edit_candidate_facts'):raise ProtocolError('invalid_helper_capability')
        if not all(isinstance(v,list) and len(v)<=30 for v in (preconditions,limitations,tests)):raise ProtocolError('invalid_helper_metadata')
        resolved=self._helper_path(path,sha256)
        values=(helper_id,version,capability,str(resolved),sha256,dumps(scope),dumps(preconditions),dumps(limitations),dumps(tests))
        with self.tx() as db:
            old=db.execute('SELECT * FROM helper_versions WHERE helper_id=? AND version=?',(helper_id,version)).fetchone()
            if old:
                fields=('helper_id','version','capability','path','sha256','scope_json','preconditions_json','limitations_json','tests_json')
                if tuple(old[k] for k in fields)!=values:raise ProtocolError('helper_version_immutable')
                return public_record(old)
            db.execute('INSERT INTO helper_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',values+('candidate','',self.now()))
            return public_record(db.execute('SELECT * FROM helper_versions WHERE helper_id=? AND version=?',(helper_id,version)).fetchone())

    def helper_activate(self,helper_id,version,*,verification_evidence):
        if not isinstance(verification_evidence,str) or not verification_evidence.strip():raise ProtocolError('helper_verification_required')
        with self.tx() as db:
            if db.execute("SELECT 1 FROM browser_leases WHERE state!='released'").fetchone():raise ProtocolError('activation_requires_quiescence')
            row=db.execute('SELECT * FROM helper_versions WHERE helper_id=? AND version=?',(helper_id,version)).fetchone()
            if row is None:raise ProtocolError('helper_not_found')
            self._helper_path(row['path'],row['sha256'])
            db.execute("UPDATE helper_versions SET status='retired' WHERE helper_id=? AND status='active'",(helper_id,))
            db.execute("UPDATE helper_versions SET status='active',evidence=? WHERE helper_id=? AND version=?",(safe_text(verification_evidence),helper_id,version))
            db.execute('INSERT INTO helper_history VALUES (?,?,?,?,?,?)',(uid(),helper_id,version,'active',safe_text(verification_evidence),self.now()))
            return public_record(db.execute('SELECT * FROM helper_versions WHERE helper_id=? AND version=?',(helper_id,version)).fetchone())

    def helpers_for_context(self,platform,namespace,capability=None):
        with self.tx() as db:rows=[dict(r) for r in db.execute("SELECT * FROM helper_versions WHERE status='active' ORDER BY helper_id,version")]
        result=[]
        for row in rows:
            if (capability and row['capability']!=capability) or not matches(json.loads(row['scope_json']),platform,namespace):continue
            try:self._helper_path(row['path'],row['sha256'])
            except ProtocolError:continue
            result.append(public_record(row))
        return result[:10]
