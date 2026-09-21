"""Durable human questions and retry requests; independent of a browser or harness."""
import hashlib
import json
import re

from .managed_identity import RELATED, canonical_url
from .managed_redaction import reject_secrets
from .managed_shared import ProtocolError, dumps, uid

PRIVATE = re.compile(r'password|passwd|\botp\b|one.?time.?code|(?:verification|security|authentication).?code|secret|social.?security|\bssn\b|tax.?id|bank.?account|routing.?number|credit.?card', re.I)


def human_input_capabilities(metadata=None):
    declared=(metadata or {}).get('human_input') or {}
    messaging=declared.get('messaging') or {} if isinstance(declared,dict) else {}
    result={'messaging':{'available':False},'fallback':'answer_queue',
            'instruction':'Use approved facts and saved exact answers first. Ask only for missing required information. Park unresolved questions before leaving the application.'}
    if isinstance(messaging,dict) and messaging.get('available') is True:
        values={k:messaging.get(k) for k in ('channel','tool','reply_mode')}
        if all(isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',v) for v in values.values()):
            result['messaging']=dict(available=True,**values)
    return result


def question_data(*,field,question,kind,options=None,required=True,context=None):
    if required is not True:raise ProtocolError('required_question_only')
    if kind not in ('text','select','check','radio'):raise ProtocolError('unsupported_question_kind')
    if not isinstance(field,str) or not 1<=len(field)<=500 or not isinstance(question,str) or not 1<=len(question.strip())<=4000:
        raise ProtocolError('invalid_question')
    if PRIVATE.search(field+' '+question):raise ProtocolError('private_question_prohibited')
    # Native country lists routinely contain more than 200 genuine choices.
    # Preserve the complete offered set for exact answer matching.
    if not isinstance(options or [],list):raise ProtocolError('invalid_question_options')
    clean=[]
    for option in options or []:
        if not isinstance(option,dict) or any(not isinstance(option.get(k),str) or len(option[k])>1000 for k in ('value','label')):
            raise ProtocolError('invalid_question_options')
        if not option['label'].strip():raise ProtocolError('invalid_question_options')
        clean.append({k:option[k] for k in ('value','label')})
    if kind in ('select','radio') and not clean:raise ProtocolError('observed_options_required')
    if len({dumps(c) for c in clean})!=len(clean):raise ProtocolError('ambiguous_question_options')
    context=context or {}
    if not isinstance(context,dict) or set(context)-{'page','section','document'}:
        raise ProtocolError('invalid_question_context')
    if any(not isinstance(v,str) or len(v)>4000 for v in context.values()):raise ProtocolError('invalid_question_context')
    if context.get('document'):context=dict(context,document=canonical_url(context['document']))
    data={'field':field,'question':question.strip(),'kind':kind,'options':clean,'context':context,'required':True}
    reject_secrets(data)
    return data


def question_key(data):
    # Preserve exact wording, values and context. No semantic guess can reuse an
    # answer to a different question or a different set of employer choices.
    return hashlib.sha256(dumps(data).encode()).hexdigest()


class QuestionServices:
    @staticmethod
    def _has_question_schema(db):
        return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='application_questions'").fetchone())

    @staticmethod
    def _question(row):
        value=dict(row)
        for key in ('options','context','answer'):
            value[key]=json.loads(value.pop(key+'_json')) if value.get(key+'_json') is not None else None
        value['required']=True
        return value

    def _questions(self,db,job_id,identity_id):
        if not self._has_question_schema(db):return []
        return [self._question(row) for row in db.execute(RELATED+'''SELECT q.* FROM related r
            JOIN application_questions q ON q.job_id=r.id WHERE q.identity_id=? ORDER BY q.created_at,q.id''',
            (job_id,identity_id))]

    def request_question(self,attempt_id,*,worker_id,fence,field,question,kind,options=None,required=True,context=None):
        data=question_data(field=field,question=question,kind=kind,options=options,required=required,context=context)
        key=question_key(data)
        with self.tx() as db:
            attempt=self._owner(db,attempt_id,worker_id,fence)
            siblings=self._questions(db,attempt['job_id'],attempt['identity_id'])
            for old in siblings:
                if old['field']==field and old['context']==data['context'] and old['question_key']!=key:
                    db.execute("UPDATE application_questions SET state='superseded' WHERE id=?",(old['id'],))
            existing=next((q for q in siblings if q['question_key']==key),None)
            from .managed_events import field_task_context
            semantic=field_task_context(data['question'],page=data['context'].get('page','form'),document=data['context'].get('document',''))
            self._append_event(db,attempt,worker_id=worker_id,fence=fence,event_id=uid(),action_id=None,
                event_type='checkpoint',observed_at=self.now(),duration_seconds=None,payload=dict(semantic,
                    task_state='in_progress' if existing and existing['answer'] is not None else 'awaiting_input',source='answer_queue'))
            if existing:
                db.execute('UPDATE application_questions SET last_attempt_id=?,last_seen_at=?,state=? WHERE id=?',
                    (attempt_id,self.now(),'answered' if existing['answer'] is not None else 'pending',existing['id']))
                return self._question(self._get(db,'application_questions',existing['id']))
            identifier=uid();now=self.now()
            db.execute('''INSERT INTO application_questions(id,job_id,identity_id,first_attempt_id,last_attempt_id,
                question_key,field,question,kind,options_json,context_json,state,revision,created_at,last_seen_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending',0,?,?)''',
                (identifier,attempt['job_id'],attempt['identity_id'],attempt_id,attempt_id,key,field,data['question'],
                 kind,dumps(data['options']),dumps(data['context']),now,now))
            return self._question(self._get(db,'application_questions',identifier))

    def questions_for_attempt(self,attempt_id,worker_id=None):
        with self.tx() as db:
            attempt=self._get(db,'application_attempts',attempt_id)
            if worker_id is not None and attempt['worker_id']!=worker_id:raise ProtocolError('attempt_forbidden')
            return {'questions':self._questions(db,attempt['job_id'],attempt['identity_id'])}

    def park_questions(self,attempt_id,*,worker_id,fence):
        with self.tx() as db:
            attempt=self._owner(db,attempt_id,worker_id,fence)
            pending=[q for q in self._questions(db,attempt['job_id'],attempt['identity_id']) if q['state']=='pending']
            if not pending:raise ProtocolError('no_pending_questions')
        result=self.finish(attempt_id,worker_id=worker_id,fence=fence,outcome='blocked',
            evidence=f'Needs your answer: {len(pending)} required question(s) saved in the answer queue',quiescent=False)
        return {'status':'needs_your_answer','attempt_id':attempt_id,'job_id':result['job_id'],
                'question_ids':[q['id'] for q in pending],'browser_stop_requested':True}

    @staticmethod
    def _answer(question,answer):
        if question['kind']=='check':
            if type(answer) is not bool:raise ProtocolError('boolean_answer_required')
            return answer
        if question['kind'] in ('select','radio') and isinstance(answer,dict):
            matches=[o for o in question['options'] if o==answer]
            if len(matches)!=1:raise ProtocolError('answer_option_unavailable')
            return matches[0]
        if not isinstance(answer,str) or not 1<=len(answer.strip())<=4000:raise ProtocolError('answer_required')
        if question['kind']=='text':return answer.strip()
        options=question['options']
        matches=[o for o in options if o['value']==answer]
        if not matches:matches=[o for o in options if o['label']==answer]
        if len(matches)!=1:raise ProtocolError('answer_option_unavailable')
        return matches[0]

    def answer_questions(self,*,answers,source='user_dashboard',reply_evidence=None):
        """An operator saves a human reply; this method performs no browser work."""
        if source not in ('user_dashboard','user_reply'):raise ProtocolError('human_answer_source_required')
        if source=='user_reply' and (not isinstance(reply_evidence,str) or not reply_evidence.strip()):
            raise ProtocolError('user_reply_evidence_required')
        if not isinstance(answers,list) or not 1<=len(answers)<=100:raise ProtocolError('answers_required')
        if len({a.get('question_id') for a in answers if isinstance(a,dict)})!=len(answers):raise ProtocolError('duplicate_answer')
        with self.tx() as db:
            saved=[]
            for change in answers:
                if not isinstance(change,dict) or set(change)!={'question_id','answer','expected_revision'}:raise ProtocolError('invalid_answer')
                question=self._question(self._get(db,'application_questions',change['question_id']))
                if question['state']=='superseded':raise ProtocolError('question_changed')
                if type(change['expected_revision']) is not int or change['expected_revision']!=question['revision']:
                    raise ProtocolError('answer_revision_conflict')
                value=self._answer(question,change['answer']);reject_secrets({'answer':value,'evidence':reply_evidence or ''})
                revision=question['revision']+1;now=self.now()
                db.execute('''INSERT INTO application_question_answers(question_id,revision,answer_json,source,evidence,created_at)
                    VALUES (?,?,?,?,?,?)''',(question['id'],revision,dumps(value),source,(reply_evidence or '')[:1000],now))
                db.execute("UPDATE application_questions SET state='answered',answer_json=?,answer_source=?,answered_at=?,revision=? WHERE id=?",
                    (dumps(value),source,now,revision,question['id']))
                saved.append(self._question(self._get(db,'application_questions',question['id'])))
            return {'questions':saved}

    def answer_from_user(self,attempt_id,*,worker_id,fence,answers,reply_evidence):
        """Live harness bridge. A reply is data; the next browser call rechecks refs."""
        with self.tx() as db:
            attempt=self._owner(db,attempt_id,worker_id,fence)
            allowed={q['id'] for q in self._questions(db,attempt['job_id'],attempt['identity_id'])}
            if not isinstance(answers,list) or any(not isinstance(a,dict) or a.get('question_id') not in allowed for a in answers):
                raise ProtocolError('question_context_mismatch')
        return self.answer_questions(answers=answers,source='user_reply',reply_evidence=reply_evidence)

    def answer_queue(self,identity_id=None):
        with self.tx() as db:
            if not self._has_question_schema(db):return {'groups':[],'available':False}
            where='WHERE q.identity_id=?' if identity_id else ''
            rows=db.execute('''SELECT DISTINCT q.job_id,q.identity_id,j.url,j.company,j.title,j.status,j.disposition,c.email
                FROM application_questions q JOIN jobs j ON j.id=q.job_id JOIN candidates c ON c.id=q.identity_id
                '''+where+' ORDER BY q.last_seen_at DESC', (identity_id,) if identity_id else ()).fetchall()
            groups=[]
            for row in rows:
                group=dict(row);questions=self._questions(db,row['job_id'],row['identity_id'])
                group.update(questions=questions,pending_count=sum(q['state']=='pending' for q in questions))
                queued=db.execute("SELECT id,state,requested_at FROM answer_retry_requests WHERE job_id=? AND identity_id=? ORDER BY requested_at DESC LIMIT 1",
                    (row['job_id'],row['identity_id'])).fetchone()
                group['retry']=dict(queued) if queued else None
                session=db.execute('SELECT id,ended_at FROM application_sessions WHERE job_id=? AND identity_id=? ORDER BY requested_at DESC LIMIT 1',
                    (row['job_id'],row['identity_id'])).fetchone()
                group['session_id']=session['id'] if session else None
                group['browser_stopped']=not session or bool(session['ended_at'])
                groups.append(group)
            return {'groups':groups,'available':True}

    def queue_answer_retries(self,*,job_ids,identity_id):
        if not isinstance(job_ids,list) or not 1<=len(job_ids)<=100 or len(set(job_ids))!=len(job_ids):
            raise ProtocolError('retry_jobs_required')
        with self.tx() as db:
            self._get(db,'candidates',identity_id)
            requests=[]
            for job_id in job_ids:
                questions=self._questions(db,job_id,identity_id)
                if not questions or any(q['state']=='pending' for q in questions):raise ProtocolError('unanswered_questions')
                self._assert_not_suppressed(db,job_id)
                if db.execute('SELECT 1 FROM job_archives WHERE job_id=?',(job_id,)).fetchone():raise ProtocolError('job_archived')
                old=db.execute("SELECT * FROM answer_retry_requests WHERE job_id=? AND identity_id=? AND state='queued'",(job_id,identity_id)).fetchone()
                if old:requests.append(dict(old));continue
                identifier=uid();now=self.now()
                db.execute("INSERT INTO answer_retry_requests(id,job_id,identity_id,state,requested_at) VALUES (?,?,?,'queued',?)",
                    (identifier,job_id,identity_id,now))
                db.execute("UPDATE jobs SET status='queued',updated_at=? WHERE id=? AND status!='running'",(now,job_id))
                requests.append(dict(self._get(db,'answer_retry_requests',identifier)))
            return {'requests':requests,'instruction':'The next application harness can pick up these requests. Browser startup still verifies ownership, history and the configured profile.'}

    def answer_retries(self,identity_id=None):
        with self.tx() as db:
            if not self._has_question_schema(db):return {'requests':[]}
            query="SELECT r.*,j.url,j.company,j.title FROM answer_retry_requests r JOIN jobs j ON j.id=r.job_id WHERE r.state='queued'"
            rows=db.execute(query+(' AND r.identity_id=?' if identity_id else '')+' ORDER BY r.requested_at,r.id',
                (identity_id,) if identity_id else ()).fetchall()
            requests=[]
            for row in rows:
                if any(q['state']=='pending' for q in self._questions(db,row['job_id'],row['identity_id'])):continue
                try:self._assert_not_suppressed(db,row['job_id'])
                except ProtocolError:continue
                requests.append(dict(row,request_id='answer-retry:'+row['id']))
            return {'requests':requests}
