"""Portal/account metadata and bounded mail correlation. No credential or mail access."""
import hashlib
import json
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from .managed_shared import ProtocolError, dumps, uid
from .managed_redaction import safe_text
from .managed_identity import job_key


def valid_namespace(value):
    # Namespace is host plus optional tenant path, not an arbitrary URL or company name.
    if not isinstance(value,str) or len(value)>255 or not re.fullmatch(r'[A-Za-z0-9.-]+(?:/[A-Za-z0-9._-]+)*',value) or '..' in value:
        raise ProtocolError('invalid_namespace')
    host,sep,path=value.partition('/')
    host=host.casefold()
    return host+sep+(path.casefold() if host.endswith('.myworkdayjobs.com') else path)


def stamp(value):
    try:
        dt=datetime.fromisoformat(value)
        if dt.tzinfo is None:raise ValueError()
        return dt
    except (TypeError,ValueError):raise ProtocolError('invalid_timestamp')


class AccountServices:
    @staticmethod
    def _namespace(db,value):
        value=valid_namespace(value);seen=set()
        while True:
            if value in seen or len(seen)>20:raise ProtocolError('namespace_alias_cycle')
            seen.add(value)
            rows=[r for r in db.execute('SELECT alias,canonical FROM account_namespace_aliases') if valid_namespace(r['alias'])==value]
            if len({valid_namespace(r['canonical']) for r in rows})>1:raise ProtocolError('namespace_alias_conflict')
            row=rows[0] if rows else None
            if not row:return value
            value=valid_namespace(row['canonical'])

    def namespace_alias(self,*,alias,canonical,verification_evidence):
        alias=valid_namespace(alias);canonical=valid_namespace(canonical)
        if not isinstance(verification_evidence,str) or not verification_evidence.strip():raise ProtocolError('namespace_verification_required')
        with self.tx() as db:
            if self._namespace(db,canonical)==alias:raise ProtocolError('namespace_alias_cycle')
            old=next((r for r in db.execute('SELECT * FROM account_namespace_aliases') if valid_namespace(r['alias'])==alias),None)
            if old:
                if valid_namespace(old['canonical'])!=canonical:raise ProtocolError('namespace_alias_conflict')
                return dict(old)
            db.execute('INSERT INTO account_namespace_aliases VALUES (?,?,?,?)',(alias,canonical,safe_text(verification_evidence),self.now()))
            return dict(db.execute('SELECT * FROM account_namespace_aliases WHERE alias=?',(alias,)).fetchone())

    def _account_for_namespace(self,db,namespace,identity_id):
        rows=[r for r in db.execute('SELECT * FROM company_portal_accounts WHERE identity_id=? AND namespace IS NOT NULL',(identity_id,)) if self._namespace(db,r['namespace'])==namespace]
        if len(rows)>1:raise ProtocolError('account_namespace_reconciliation_required')
        return rows[0] if rows else None

    def _job_account_namespace(self,db,job,requested=None):
        # Only verified job identity or an operator-verified alias confers scope.
        # Free-form account_namespace metadata is a request, never its own proof.
        account_url=dict(job).get('account_url') or job['url']
        expected=urlsplit(account_url).hostname
        if job['namespace'] and job['requisition_id']:
            key=job_key(account_url,job['namespace'],job['requisition_id'])
            if db.execute('SELECT 1 FROM job_identity_keys WHERE job_id=? AND identity_key=?',(job['id'],key)).fetchone():
                expected=valid_namespace(job['namespace'])
        expected=self._namespace(db,expected)
        actual=self._namespace(db,requested) if requested is not None else expected
        return actual if actual==expected else None

    def record_account_event(self,*,attempt_id,worker_id,fence,namespace,state,credential_ref,request_id,evidence):
        valid_namespace(namespace)
        if not isinstance(evidence,str) or not evidence.strip():raise ProtocolError('account_evidence_required')
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence,completed=True)
            from .managed_sessions import application_job
            actual=self._job_account_namespace(db,application_job(db,a,self._get(db,'jobs',a['job_id'])),namespace)
            if actual is None:raise ProtocolError('account_namespace_not_verified_for_job')
            # Ownership check, replay check and mutation share the same writer lock.
            return self._account_update(db,namespace=actual,identity_id=a['identity_id'],state=state,
                credential_ref=credential_ref,request_id=request_id,evidence=evidence,
                attempt_id=attempt_id,allow_mutation=not bool(a['completed_at']))

    def account_update(self, *, namespace, identity_id, state, credential_ref, request_id, evidence=''):
        valid_namespace(namespace)
        with self.tx() as db:
            return self._account_update(db,namespace=self._namespace(db,namespace),identity_id=identity_id,
                state=state,credential_ref=credential_ref,request_id=request_id,evidence=evidence)

    def _account_update(self,db,*,namespace,identity_id,state,credential_ref,request_id,evidence,attempt_id=None,allow_mutation=True):
        if state not in ('creation_pending','creation_not_executed','account_absent','creation_rejected','created_unverified','confirmed','verified','recovery_required','reconciliation_required','locked','disabled'):raise ProtocolError('invalid_account_state')
        if not request_id or not re.fullmatch(r'(?:vault|keyring|credential):[A-Za-z0-9._/-]+',credential_ref or ''):raise ProtocolError('credential_reference_required')
        evidence=safe_text(evidence)
        if state in ('confirmed','verified','account_absent','creation_rejected') and not evidence:raise ProtocolError('evidence_required')
        key=hashlib.sha256(dumps([namespace,identity_id,state,credential_ref,evidence]).encode()).hexdigest()
        candidate=self._get(db,'candidates',identity_id)
        prior=db.execute('SELECT * FROM account_requests WHERE id=?',(request_id,)).fetchone()
        if prior:
            if prior['request_hash']!=key or prior['attempt_id']!=attempt_id:raise ProtocolError('idempotency_conflict')
            return json.loads(prior['response_json'])
        if not allow_mutation:raise ProtocolError('account_observation_requires_reconciliation')
        old=self._account_for_namespace(db,namespace,identity_id)
        if state=='creation_not_executed':
            latest=db.execute('SELECT attempt_id FROM account_requests WHERE account_id=? ORDER BY created_at DESC,id DESC LIMIT 1',(old['id'],)).fetchone() if old else None
            if attempt_id is None or not old or old['status']!='creation_pending' or not latest or latest['attempt_id']!=attempt_id or not evidence:
                raise ProtocolError('matching_creation_attempt_required')
        if old:
            if state=='creation_pending' and old['status'] not in ('creation_not_executed','account_absent','creation_rejected'):raise ProtocolError('reconciliation_required')
            db.execute('UPDATE company_portal_accounts SET status=?,credential_ref=?,notes=?,updated_at=? WHERE id=?',(state,credential_ref,evidence,self.now(),old['id']))
            account_id=old['id']
        else:
            # Never silently attach an unclassified legacy account to a new identity.
            legacy=db.execute('SELECT 1 FROM company_portal_accounts WHERE portal_key=? COLLATE NOCASE AND email=? COLLATE NOCASE',(namespace,candidate['email'])).fetchone()
            if legacy:raise ProtocolError('legacy_account_reconciliation_required')
            cursor=db.execute('INSERT INTO company_portal_accounts(company_key,company_name,platform,portal_key,email,status,notes,created_at,updated_at,identity_id,namespace,credential_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (namespace,namespace,'unknown',namespace,candidate['email'],state,evidence,self.now(),self.now(),identity_id,namespace,credential_ref))
            account_id=cursor.lastrowid
        row=dict(self._get(db,'company_portal_accounts',account_id))
        if state in ('confirmed','verified'):db.execute('UPDATE company_portal_accounts SET last_confirmed_at=? WHERE id=?',(self.now(),account_id))
        response={k:row[k] for k in ('id','namespace','identity_id','credential_ref')}
        response['state']=row['status']
        db.execute('INSERT INTO account_requests(id,account_id,request_hash,response_json,created_at,attempt_id) VALUES (?,?,?,?,?,?)',(request_id,account_id,key,dumps(response),self.now(),attempt_id))
        return response

    def account_strategy(self, *, namespace, identity_id):
        valid_namespace(namespace)
        with self.tx() as db:
            namespace=self._namespace(db,namespace)
            candidate=self._get(db,'candidates',identity_id)
            if candidate['state']!='active':return {'action':'operator_required','reason':'identity_inactive'}
            row=self._account_for_namespace(db,namespace,identity_id)
            if not row:return {'action':'unknown','namespace':namespace,'identity_id':identity_id}
            action={'confirmed':'sign_in','verified':'sign_in','created_unverified':'verify','creation_pending':'reconcile','creation_not_executed':'create_account','account_absent':'create_account','creation_rejected':'create_account','recovery_required':'reconcile','reconciliation_required':'reconcile','locked':'operator_required','disabled':'operator_required'}.get(row['status'],'operator_required')
            latest=db.execute('SELECT attempt_id,created_at FROM account_requests WHERE account_id=? ORDER BY created_at DESC,id DESC LIMIT 1',(row['id'],)).fetchone()
            return {'action':action,'namespace':namespace,'identity_id':identity_id,'account_id':row['id'],'credential_ref':row['credential_ref'],
                    'state':row['status'],'created_at':row['created_at'],'last_attempt_id':latest['attempt_id'] if latest else None,
                    'last_action_at':latest['created_at'] if latest else None,
                    'creation_confirmed':row['status'] in ('created_unverified','confirmed','verified')}

    def mail_request(self, *, identity_id, namespace, purpose, requested_at, expected_sender):
        with self.tx() as db:
            return self._mail_request(db,identity_id=identity_id,namespace=namespace,purpose=purpose,requested_at=requested_at,expected_sender=expected_sender)

    def _mail_request(self,db,*,identity_id,namespace,purpose,requested_at,expected_sender):
        valid_namespace(namespace)
        if purpose not in ('email_verification','application_confirmation','password_reset'):raise ProtocolError('invalid_mail_purpose')
        if not isinstance(expected_sender,str) or '@' not in expected_sender:raise ProtocolError('expected_sender_required')
        start=stamp(requested_at)
        self._get(db,'candidates',identity_id)
        request_id=uid()
        db.execute('INSERT INTO mail_requests VALUES (?,?,?,?,?,?,?)',
            (request_id,identity_id,namespace,purpose,start.isoformat(),(start+timedelta(minutes=10)).isoformat(),expected_sender))
        return dict(self._get(db,'mail_requests',request_id))

    def request_mail_for_attempt(self,*,attempt_id,worker_id,fence,namespace,purpose,requested_at,expected_sender):
        valid_namespace(namespace)
        with self.tx() as db:
            a=self._owner(db,attempt_id,worker_id,fence)
            from .managed_sessions import application_job
            canonical=self._job_account_namespace(db,application_job(db,a,self._get(db,'jobs',a['job_id'])),namespace)
            if canonical is None:raise ProtocolError('mail_namespace_not_verified')
            request=self._mail_request(db,identity_id=a['identity_id'],namespace=canonical,purpose=purpose,requested_at=requested_at,expected_sender=expected_sender)
            db.execute('INSERT INTO attempt_mail_requests VALUES (?,?)',(request['id'],attempt_id))
            return dict(request,attempt_id=attempt_id)

    def match_mail_for_attempt(self,*,attempt_id,worker_id,fence,request_id,messages):
        with self.tx() as db:
            self._owner(db,attempt_id,worker_id,fence,completed=True)
            binding=db.execute('SELECT attempt_id FROM attempt_mail_requests WHERE request_id=?',(request_id,)).fetchone()
            if not binding or binding[0]!=attempt_id:raise ProtocolError('mail_request_not_owned')
        return self.match_mail(request_id,messages=messages)

    def match_mail(self, request_id, *, messages):
        with self.tx() as db:
            request=self._get(db,'mail_requests',request_id)
            candidate=self._get(db,'candidates',request['identity_id'])
            matches=set()
            for message in messages:
                if any(str(message.get(k,'')).casefold()!=expected.casefold() for k,expected in {
                    'recipient':candidate['email'],'sender':request['expected_sender']}.items()):continue
                try:
                    if self._namespace(db,message.get('namespace'))!=self._namespace(db,request['namespace']):continue
                except ProtocolError:continue
                if message.get('purpose')!=request['purpose']:continue
                try:received=stamp(message.get('received_at'))
                except ProtocolError:continue
                if stamp(request['requested_at'])<=received<=stamp(request['expires_at']) and message.get('id'):
                    matches.add(message['id'])
            if len(matches)>1:raise ProtocolError('ambiguous_mail')
            # Bodies/codes are ignored even if a caller mistakenly includes them.
            return {'message_id':next(iter(matches))} if matches else None
