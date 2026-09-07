"""Fenced runtime budgets and tab ownership records; no browser/process operations."""
from datetime import datetime
import json
import re
from urllib.parse import urlsplit,urlunsplit
from .managed_shared import ProtocolError,uid
from .managed_redaction import safe_text
from .managed_identity import canonical_url,job_key,RELATED


class RuntimeServices:
    def _field_context(self,db,a):
        rows=db.execute('SELECT event_type,payload_json FROM managed_events WHERE attempt_id=? AND stale=0 ORDER BY julianday(observed_at) DESC,rowid DESC',(a['id'],))
        legacy=None
        for row in rows:
            payload=json.loads(row['payload_json'])
            if row['event_type'] in ('navigation_verified','field_verified'):return {}
            if row['event_type']=='field_context':
                return {k:payload[k] for k in ('page','field','category')} if payload.get('field') else {}
            # Completion describes action-start attribution, never current scope.
            # Keep legacy manual event support only when no semantic marker exists.
            if legacy is None and row['event_type']=='tool_finished' and payload.get('field'):
                legacy={k:payload.get(k,'') for k in ('page','field','category')}
        return legacy or {}

    def _strategy_check(self,db,a,tool_name):
        cfg=json.loads(a['settings_json'])
        events=db.execute('SELECT * FROM managed_events WHERE attempt_id=? AND stale=0 ORDER BY julianday(observed_at) DESC,rowid DESC',(a['id'],)).fetchall()
        payloads=[(row,json.loads(row['payload_json'])) for row in events]
        phase=next((p.get('phase') for row,p in payloads if row['event_type']=='phase_changed' and p.get('phase')),None)
        if cfg.get('allowed_fallback')=='block' and phase in ('residual_fields','native_fallback'):
            raise ProtocolError('fallback_not_allowed')
        extra=db.execute('SELECT COALESCE(SUM(seconds),0) FROM budget_extensions WHERE attempt_id=?',(a['id'],)).fetchone()[0]
        context=self._field_context(db,a)
        if context:
            matched=[row for row,p in payloads if row['event_type']=='tool_finished' and all(p.get(k,'')==v for k,v in context.items())]
            if any(row['duration_seconds'] is None for row in matched):raise ProtocolError('semantic_field_timing_unknown')
            spent=sum(row['duration_seconds'] for row in matched)
            if spent>cfg.get('field_seconds',60)+extra:raise ProtocolError('semantic_field_budget_exceeded')
        return context

    def _budget_check(self,db,a):
        cfg=json.loads(a['settings_json']);now=datetime.fromisoformat(self.now())
        extra=db.execute('SELECT COALESCE(SUM(seconds),0) FROM budget_extensions WHERE attempt_id=?',(a['id'],)).fetchone()[0]
        if (now-datetime.fromisoformat(a['started_at'])).total_seconds()>cfg.get('attempt_seconds',300)+extra:raise ProtocolError('attempt_budget_exceeded')
        if (now-datetime.fromisoformat(a['progress_at'])).total_seconds()>cfg.get('no_progress_seconds',45)+extra:raise ProtocolError('no_progress_budget_exceeded')

    def extend_budget(self,attempt_id,*,worker_id,fence,seconds,reason):
        if type(seconds) not in (int,float) or not 0<seconds<=120 or not isinstance(reason,str) or not reason.strip():raise ProtocolError('invalid_budget_extension')
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence)
            if self._get(db,'runs',a['run_id'])['control'] in ('stopped','stop_requested'):raise ProtocolError('run_stopping')
            if db.execute('SELECT COUNT(*) FROM budget_extensions WHERE attempt_id=?',(attempt_id,)).fetchone()[0]>=2:raise ProtocolError('budget_extension_limit')
            eid=uid();db.execute('INSERT INTO budget_extensions VALUES (?,?,?,?,?)',(eid,attempt_id,seconds,safe_text(reason),self.now()))
            return dict(self._get(db,'budget_extensions',eid))

    def bind_target(self,attempt_id,*,worker_id,fence,target_id,url):
        if not isinstance(target_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,250}',target_id):raise ProtocolError('invalid_target_id')
        canonical=canonical_url(url);parsed=urlsplit(canonical);display=urlunsplit(parsed._replace(query='',fragment=''))
        identity=job_key(canonical)
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence);job=self._get(db,'jobs',a['job_id']);expected=urlsplit(canonical_url(job['url']))
            verified=db.execute(RELATED+'SELECT 1 FROM related r JOIN job_identity_keys k ON k.job_id=r.id WHERE k.identity_key=?',(job['id'],identity)).fetchone()
            # An account alias proves credential scope, NOT requisition/tab ownership.
            # Alternate URLs need a verified job identity; only the conventional
            # same-origin /apply child preserves the posting identity implicitly.
            apply_child=(bool(expected.path) and parsed.scheme==expected.scheme and parsed.netloc==expected.netloc
                and parsed.path==expected.path+'/apply' and parsed.query==expected.query)
            if not verified and not apply_child:raise ProtocolError('target_job_mismatch')
            old=db.execute('SELECT * FROM owned_targets WHERE profile=? AND target_id=? AND state!=?',(a['browser_profile'],target_id,'closed')).fetchone()
            if old:
                if old['attempt_id']!=attempt_id or old['identity_key']!=identity:raise ProtocolError('target_owned_elsewhere')
                return dict(old)
            prior=db.execute('SELECT * FROM owned_targets WHERE attempt_id=? AND target_id=?',(attempt_id,target_id)).fetchone()
            if prior:raise ProtocolError('closed_target_cannot_rebind')
            rid=uid();db.execute('INSERT INTO owned_targets(id,attempt_id,profile,target_id,url,state,evidence,created_at,updated_at,identity_key) VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,attempt_id,a['browser_profile'],target_id,display,'open','Explicit worker target binding',self.now(),self.now(),identity))
            return dict(self._get(db,'owned_targets',rid))

    def target_state(self,attempt_id,*,worker_id,fence,target_id,state,evidence):
        if state not in ('open','preserved','closed') or not isinstance(evidence,str) or not evidence.strip():raise ProtocolError('invalid_target_state')
        with self.tx() as db:
            self._owner(db,attempt_id,worker_id,fence)
            target=db.execute('SELECT * FROM owned_targets WHERE attempt_id=? AND target_id=?',(attempt_id,target_id)).fetchone()
            if target is None:raise ProtocolError('target_not_owned')
            if target['state']=='closed' and state!='closed':raise ProtocolError('closed_target_immutable')
            if state==target['state']:return dict(target)
            evidence=safe_text(evidence)
            db.execute('UPDATE owned_targets SET state=?,evidence=?,updated_at=? WHERE id=?',(state,evidence,self.now(),target['id']))
            db.execute('INSERT INTO target_history VALUES (?,?,?,?,?)',(uid(),target['id'],state,evidence,self.now()))
            return dict(self._get(db,'owned_targets',target['id']))
