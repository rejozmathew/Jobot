"""Portal/account metadata and bounded mail correlation. No credential or mail access."""
import hashlib
import json
import re
from datetime import datetime, timedelta
from .managed_shared import ProtocolError, dumps, uid
from .managed_redaction import safe_text


def valid_namespace(value):
    # Namespace is host plus optional tenant path, not an arbitrary URL or company name.
    if not isinstance(value,str) or len(value)>255 or not re.fullmatch(r'[a-z0-9.-]+(?:/[A-Za-z0-9._-]+)*',value) or '..' in value:
        raise ProtocolError('invalid_namespace')
    return value


def stamp(value):
    try:
        dt=datetime.fromisoformat(value)
        if dt.tzinfo is None:raise ValueError()
        return dt
    except (TypeError,ValueError):raise ProtocolError('invalid_timestamp')


class AccountServices:
    def account_update(self, *, namespace, identity_id, state, credential_ref, request_id, evidence=''):
        valid_namespace(namespace)
        if state not in ('creation_pending','confirmed','reconciliation_required','disabled'):raise ProtocolError('invalid_account_state')
        if not request_id or not re.fullmatch(r'(?:vault|keyring|credential):[A-Za-z0-9._/-]+',credential_ref or ''):raise ProtocolError('credential_reference_required')
        evidence=safe_text(evidence)
        if state=='confirmed' and not evidence:raise ProtocolError('evidence_required')
        key=hashlib.sha256(dumps([namespace,identity_id,state,credential_ref,evidence]).encode()).hexdigest()
        with self.tx() as db:
            candidate=self._get(db,'candidates',identity_id)
            prior=db.execute('SELECT * FROM account_requests WHERE id=?',(request_id,)).fetchone()
            if prior:
                if prior['request_hash']!=key:raise ProtocolError('idempotency_conflict')
                return json.loads(prior['response_json'])
            old=db.execute('SELECT * FROM company_portal_accounts WHERE namespace=? AND identity_id=?',(namespace,identity_id)).fetchone()
            if old:
                if state=='creation_pending':raise ProtocolError('reconciliation_required')
                db.execute('UPDATE company_portal_accounts SET status=?,credential_ref=?,notes=?,updated_at=? WHERE id=?',(state,credential_ref,evidence,self.now(),old['id']))
                account_id=old['id']
            else:
                # Never silently attach an unclassified legacy account to a new identity.
                legacy=db.execute('SELECT 1 FROM company_portal_accounts WHERE portal_key=? AND email=?',(namespace,candidate['email'])).fetchone()
                if legacy:raise ProtocolError('legacy_account_reconciliation_required')
                cursor=db.execute('INSERT INTO company_portal_accounts(company_key,company_name,platform,portal_key,email,status,notes,created_at,updated_at,identity_id,namespace,credential_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (namespace,namespace,'unknown',namespace,candidate['email'],state,evidence,self.now(),self.now(),identity_id,namespace,credential_ref))
                account_id=cursor.lastrowid
            row=dict(self._get(db,'company_portal_accounts',account_id))
            response={k:row[k] for k in ('id','namespace','identity_id','credential_ref')}
            response['state']=row['status']
            db.execute('INSERT INTO account_requests VALUES (?,?,?,?,?)',(request_id,account_id,key,dumps(response),self.now()))
            return response

    def account_strategy(self, *, namespace, identity_id):
        valid_namespace(namespace)
        with self.tx() as db:
            candidate=self._get(db,'candidates',identity_id)
            if candidate['state']!='active':return {'action':'operator_required','reason':'identity_inactive'}
            row=db.execute('SELECT * FROM company_portal_accounts WHERE namespace=? AND identity_id=?',(namespace,identity_id)).fetchone()
            if not row:return {'action':'unknown','namespace':namespace,'identity_id':identity_id}
            action={'confirmed':'sign_in','creation_pending':'reconcile','reconciliation_required':'reconcile','disabled':'operator_required'}.get(row['status'],'operator_required')
            return {'action':action,'namespace':namespace,'identity_id':identity_id,'account_id':row['id'],'credential_ref':row['credential_ref']}

    def mail_request(self, *, identity_id, namespace, purpose, requested_at, expected_sender):
        valid_namespace(namespace)
        if purpose not in ('email_verification','application_confirmation','password_reset'):raise ProtocolError('invalid_mail_purpose')
        if not isinstance(expected_sender,str) or '@' not in expected_sender:raise ProtocolError('expected_sender_required')
        start=stamp(requested_at)
        with self.tx() as db:
            self._get(db,'candidates',identity_id)
            request_id=uid()
            db.execute('INSERT INTO mail_requests VALUES (?,?,?,?,?,?,?)',
                (request_id,identity_id,namespace,purpose,start.isoformat(),(start+timedelta(minutes=10)).isoformat(),expected_sender))
            return dict(self._get(db,'mail_requests',request_id))

    def match_mail(self, request_id, *, messages):
        with self.tx() as db:
            request=self._get(db,'mail_requests',request_id)
            candidate=self._get(db,'candidates',request['identity_id'])
            matches=set()
            for message in messages:
                if any(message.get(k)!=expected for k,expected in {
                    'recipient':candidate['email'],'sender':request['expected_sender'],
                    'namespace':request['namespace'],'purpose':request['purpose']}.items()):continue
                try:received=stamp(message.get('received_at'))
                except ProtocolError:continue
                if stamp(request['requested_at'])<=received<=stamp(request['expires_at']) and message.get('id'):
                    matches.add(message['id'])
            if len(matches)>1:raise ProtocolError('ambiguous_mail')
            # Bodies/codes are ignored even if a caller mistakenly includes them.
            return {'message_id':next(iter(matches))} if matches else None
