"""Company/role matching with optional local embeddings and reversible decisions.

Network work runs outside database transactions. Similarity alone never confirms
a duplicate. Failed history is not a suppression reason, and fuzzy matches never
become transitive URL/ownership aliases.
"""
from collections import defaultdict
from datetime import date
from functools import wraps
import hashlib
import json
import logging
import math
import re
import threading
import unicodedata
from urllib.parse import urlsplit

from .managed_identity import ats_posting_identity, form_route_identity, RELATED
from .managed_shared import ProtocolError, dumps

TITLE_THRESHOLD = 0.975
PREFIX_VERSION = 'company-role-clustering-v1'


def digest(value):
    return hashlib.sha256(dumps(value).encode('utf-8')).hexdigest()


def normalize(value):
    value=unicodedata.normalize('NFKC',str(value or '')).casefold().replace('&',' and ')
    return ' '.join(re.sub(r'[^\w\s]',' ',value).split())


def company_key(value):
    words=normalize(value).split()
    while words and words[-1] in ('inc','incorporated','llc','ltd','limited','corp','corporation','plc'):
        words.pop()
    return ' '.join(words)


def title_key(value):
    words=normalize(value).split();out=[]
    aliases={'vp':'vice president','svp':'senior vice president','evp':'executive vice president',
             'sr':'senior','jr':'junior'}
    for word in words:
        if word not in ('of','the'):out.extend(aliases.get(word,word).split())
    return ' '.join(out)


def seniority(title):
    words=set(title.split())
    return tuple(sorted(words & {'senior','junior','associate','assistant','executive','managing','vice','president',
                                  'director','head','manager','lead','principal','chief','intern'}))


def location_key(value):
    text=normalize(value)
    text=re.sub(r'\bunited states(?: of america)?\b|\busa\b','us',text)
    return ' '.join(sorted(text.split()))


def native_identity(url):
    """Corroboration/conflict evidence only; never authorizes browser navigation."""
    try:
        p=urlsplit(url);host=(p.hostname or '').casefold()
        if host=='linkedin.com' or host.endswith('.linkedin.com'):return None
        identity=ats_posting_identity(url)
        if identity:
            if identity[0]=='greenhouse':return ('greenhouse:'+identity[1],identity[2])
            if identity[0]=='workday':return ('workday:'+':'.join(identity[1:3]),identity[3])
            if identity[0]=='icims':return ('icims:'+identity[2],identity[3])
        m=re.match(r'/([^/]+)/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})(?:/|$)',p.path,re.I)
        if host in ('jobs.ashbyhq.com','jobs.lever.co') and m:
            return (host+':'+m[1].casefold(),m[2].casefold())
        m=re.match(r'/view/([^/]+)',p.path)
        if host=='jobs.workable.com' and m:return ('workable',m[1])
        m=re.search(r'/recruiting/jobs/(?:apply|details|success)/(\d+)',p.path,re.I)
        if host.endswith('.paylocity.com') and m:return (host,m[1])
        identity=form_route_identity(url)
        if identity:return (identity[1]+':'+identity[2],identity[3])
    except (ValueError,TypeError,ProtocolError):pass
    return None


def profiles(db):
    routes=defaultdict(list)
    for row in db.execute('SELECT job_id,original_url FROM job_sources'):
        routes[row['job_id']].append(row['original_url'])
    for row in db.execute('SELECT job_id,metadata_json FROM application_sessions'):
        meta=json.loads(row['metadata_json'] or '{}')
        routes[row['job_id']].extend(meta[k] for k in ('application_identity_url','application_route_url') if meta.get(k))
    result={}
    for raw in db.execute('SELECT id,seq_id,company,title,url,metadata_json FROM jobs'):
        row=dict(raw);meta=json.loads(row.pop('metadata_json') or '{}')
        row['company_key']=company_key(row['company']);row['title_key']=title_key(row['title'])
        row['location']=location_key(meta.get('location'));row['posted_at']=''
        try:row['posted_at']=date.fromisoformat(str(meta.get('posted_at',''))[:10]).isoformat()
        except ValueError:pass
        description=normalize(meta.get('description') or meta.get('job_description'))
        row['description_hash']=digest(description) if len(description)>=120 else None
        row['native_ids']=sorted({identity for u in [row['url'],*routes[row['id']]] if (identity:=native_identity(u))})
        row['text']='clustering: Company: '+row['company_key']+'. Role: '+row['title_key']
        row['text_hash']=digest([PREFIX_VERSION,row['text']])
        row['hash']=digest({k:row[k] for k in ('company_key','title_key','location','posted_at','description_hash','native_ids')})
        result[row['id']]=row
    return result


def cosine(a,b):
    if not a or not b or len(a)!=len(b):return None
    denom=math.sqrt(sum(v*v for v in a)*sum(v*v for v in b))
    return max(-1.,min(1.,sum(x*y for x,y in zip(a,b))/denom)) if denom else None


def compare(left,right,*,vectors=None,threshold=TITLE_THRESHOLD):
    if not left['company_key'] or left['company_key']!=right['company_key'] or not left['title_key'] or not right['title_key']:
        return None
    a,b=sorted((left,right),key=lambda p:p['id'])
    exact=a['title_key']==b['title_key']
    score=1. if exact else cosine((vectors or {}).get(a['text_hash']),(vectors or {}).get(b['text_hash']))
    first=set(a['native_ids']);second=set(b['native_ids']);shared=first & second
    scopes={x[0] for x in first}&{x[0] for x in second}
    conflict=any({v for s,v in first if s==scope}.isdisjoint({v for s,v in second if s==scope}) for scope in scopes)
    reasons=[];decision='possible';method='normalized_title' if exact else 'embedding'
    if shared and not conflict:
        decision='confirmed';method='employer_posting';reasons.append('Same observed employer posting ID')
    elif conflict:
        decision='different';reasons.append('Different employer requisition IDs')
    elif seniority(a['title_key'])!=seniority(b['title_key']):
        decision='different';reasons.append('Different seniority or role level')
    elif score is None or score<threshold:
        if score is None or score<0.85:return None
        reasons.append('Related title; insufficient title similarity')
    else:
        reasons.append('Same normalized company and '+('title' if exact else 'high title similarity'))
        same_location=bool(a['location'] and a['location']==b['location'])
        same_date=bool(a['posted_at'] and a['posted_at']==b['posted_at'])
        same_description=bool(a['description_hash'] and a['description_hash']==b['description_hash'])
        if same_location and (same_date or same_description):
            decision='confirmed';reasons.append('Same location and '+('posting date' if same_date else 'description'))
        else:reasons.append('Posting details do not establish the same opening')
    return {'id':digest([a['id'],b['id']]),'left_job_id':a['id'],'right_job_id':b['id'],
            'left_hash':a['hash'],'right_hash':b['hash'],'decision':decision,'method':method,
            'similarity':score,'evidence':reasons,'operator_state':'automatic'}


def cached_vectors(db):
    model=db.execute('SELECT * FROM job_duplicate_model WHERE id=1').fetchone()
    if not model:return {},TITLE_THRESHOLD
    return {r['text_hash']:json.loads(r['vector_json']) for r in db.execute(
        'SELECT text_hash,vector_json FROM job_embedding_cache WHERE model_key=?',(model['model_key'],))},model['threshold']


def matching_records(db, *, job_id=None, snapshot=None, embeddings=None):
    data=snapshot if snapshot is not None else profiles(db)
    vectors,threshold=embeddings if embeddings is not None else cached_vectors(db)
    overrides={r['id']:r['operator_state'] for r in db.execute('SELECT id,operator_state FROM job_duplicate_matches')}
    groups=defaultdict(list)
    for row in data.values():
        if row['company_key']:groups[row['company_key']].append(row)
    result=[]
    for group in groups.values():
        for i,left in enumerate(group):
            for right in group[i+1:]:
                if job_id and job_id not in (left['id'],right['id']):continue
                match=compare(left,right,vectors=vectors,threshold=threshold)
                if match:
                    match['operator_state']=overrides.get(match['id'],'automatic');result.append(match)
    return result


def save_match(db,match,now):
    db.execute('''INSERT INTO job_duplicate_matches
        (id,left_job_id,right_job_id,left_hash,right_hash,decision,method,similarity,evidence_json,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        left_hash=excluded.left_hash,right_hash=excluded.right_hash,decision=excluded.decision,
        method=excluded.method,similarity=excluded.similarity,evidence_json=excluded.evidence_json,updated_at=excluded.updated_at
        WHERE left_hash!=excluded.left_hash OR right_hash!=excluded.right_hash OR decision!=excluded.decision
           OR method!=excluded.method OR similarity IS NOT excluded.similarity OR evidence_json!=excluded.evidence_json''',
        tuple(match[k] for k in ('id','left_job_id','right_job_id','left_hash','right_hash','decision','method','similarity'))+
        (dumps(match['evidence']),now,now))


def matching_suppression(service,db,job_id,*,identity_id=None):
    mode=service._settings_record(db)['values'].get('duplicate_matching_mode','shadow')
    if mode=='off':return None
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='job_duplicate_matches'").fetchone():return None
    # Reconciliation checks many jobs in one transaction. Its posting metadata is
    # stable; cache only for this exact connection/snapshot, never across commits.
    context=getattr(service,'_duplicate_context',None)
    if context is None or context[0] is not db:
        context=(db,profiles(db),cached_vectors(db));service._duplicate_context=context
    if identity_id is None:
        candidates=db.execute("SELECT id FROM candidates WHERE state='active'").fetchall()
        identity_id=candidates[0]['id'] if len(candidates)==1 else None
    canceled=None
    for match in matching_records(db,job_id=job_id,snapshot=context[1],embeddings=context[2]):
        # Eligibility also serves read-only question/dashboard views. Persist
        # decisions in the matcher refresh or an actual refused admission.
        if mode!='enforce' or match['decision']!='confirmed' or match['operator_state']=='dismissed':continue
        other=match['right_job_id'] if match['left_job_id']==job_id else match['left_job_id']
        # Cancellation is an explicit posting-level operator choice. Re-read it
        # rather than copying it to the match, so restoring the original works.
        if db.execute(RELATED+'''SELECT 1 FROM related r JOIN jobs j ON j.id=r.id
                WHERE j.disposition='canceled' LIMIT 1''',(other,)).fetchone():
            canceled=(match,other,'job_canceled')
        if not identity_id:continue
        # Success must belong to this candidate; unknown/failed history is eligible.
        success=db.execute(RELATED+'''SELECT 1 FROM related r JOIN submission_ledger l ON l.job_id=r.id
            JOIN candidates c ON c.person_key=l.person_key WHERE c.id=? LIMIT 1''',(other,identity_id)).fetchone()
        if not success:
            success=db.execute(RELATED+'''SELECT 1 FROM related r JOIN application_attempts a ON a.job_id=r.id
                WHERE a.identity_id=? AND a.completed_at IS NOT NULL AND a.outcome IN ('applied','already_applied') LIMIT 1''',
                (other,identity_id)).fetchone()
        if success:return match,other,'already_applied'
    return canceled


def duplicate_error(job_id,matched_job_id,*,match=None,code='already_applied'):
    error=ProtocolError(code,'Matched posting explicitly canceled by operator' if code=='job_canceled'
                        else 'Recorded submission for the same posting')
    error.duplicate_job_id=job_id;error.duplicate_of=matched_job_id;error.duplicate_match=match
    return error


def record_skip(db,error,identity_id,now,source):
    if error.code not in ('already_applied','job_canceled') or not getattr(error,'duplicate_job_id',None):return
    match=getattr(error,'duplicate_match',None)
    if match:save_match(db,match,now)
    db.execute('''INSERT OR IGNORE INTO job_duplicate_skips
        (job_id,identity_id,matched_job_id,skipped_at,source,evidence_json) VALUES (?,?,?,?,?,?)''',
        (error.duplicate_job_id,identity_id or '',error.duplicate_of,now,source,
         dumps([*(match['evidence'] if match else []),
                'Matched posting explicitly canceled by operator' if error.code=='job_canceled' else 'Existing recorded posting success'])))


def audit_duplicate_admission(method):
    """Record an actual refused admission after its transaction rolls back."""
    @wraps(method)
    def wrapped(self,*args,**kwargs):
        try:return method(self,*args,**kwargs)
        except ProtocolError as exc:
            if exc.code in ('already_applied','job_canceled') and getattr(exc,'duplicate_job_id',None):
                with self.tx() as db:record_skip(db,exc,kwargs.get('identity_id'),self.now(),method.__name__)
            raise
    return wrapped


class DuplicateServices:
    def duplicate_matches(self,job_id=None):
        with self.read() as db:
            data=profiles(db);matches=matching_records(db,job_id=job_id,snapshot=data)
            mode=self._settings_record(db)['values']['duplicate_matching_mode']
        for match in matches:
            for side in ('left','right'):
                job=data[match[side+'_job_id']]
                match[side+'_job']={k:job[k] for k in ('id','seq_id','company','title')}
        return {'mode':mode,'matches':matches}

    def set_duplicate_match_state(self,*,match_id,state):
        if state not in ('automatic','dismissed'):raise ProtocolError('invalid_duplicate_state')
        with self.tx() as db:
            match=next((m for m in matching_records(db) if m['id']==match_id),None)
            if match:save_match(db,match,self.now())
            elif not db.execute('SELECT 1 FROM job_duplicate_matches WHERE id=?',(match_id,)).fetchone():
                raise ProtocolError('duplicate_match_not_found')
            db.execute('UPDATE job_duplicate_matches SET operator_state=?,updated_at=? WHERE id=?',(state,self.now(),match_id))
        return {'id':match_id,'operator_state':state}


class DuplicateMatcher:
    def __init__(self,service,config,*,embed=None):
        self.service=service;self.options=config.get('duplicate_matching') or {}
        self.model=self.options.get('model','');self.stop=threading.Event()
        self.model_key=digest([self.options.get('base_url'),self.model,self.options.get('model_revision','1'),PREFIX_VERSION])
        self.embed=embed or self._embed

    def _embed(self,texts):
        import httpx
        base=self.options.get('base_url','').rstrip('/')
        parsed=urlsplit(base)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('invalid_embedding_endpoint')
        with httpx.Client(timeout=5,trust_env=False,follow_redirects=False) as client:
            response=client.post(base+'/embeddings',json={'model':self.model,'input':texts})
            response.raise_for_status();data=response.json()['data']
        if sorted(item['index'] for item in data)!=list(range(len(texts))):raise ValueError('invalid_embedding_batch')
        return [item['embedding'] for item in sorted(data,key=lambda item:item['index'])]

    def refresh(self,job_id=None):
        if self.service.settings_view()['values']['duplicate_matching_mode']=='off':return {'embedding_status':'disabled','matches':0}
        with self.service.read() as db:data=profiles(db)
        if job_id and job_id in data:
            company=data[job_id]['company_key'];data={k:v for k,v in data.items() if v['company_key']==company}
        status='not_configured';added=0
        if self.model:
            threshold=float(self.options.get('title_threshold',TITLE_THRESHOLD))
            if not math.isfinite(threshold) or not 0.9<=threshold<=1:raise ValueError('invalid_duplicate_threshold')
            with self.service.tx() as db:
                db.execute('''INSERT INTO job_duplicate_model VALUES (1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    model_key=excluded.model_key,model_name=excluded.model_name,threshold=excluded.threshold,updated_at=excluded.updated_at''',
                    (self.model_key,self.model,threshold,self.service.now()))
                cached={r[0] for r in db.execute('SELECT text_hash FROM job_embedding_cache WHERE model_key=?',(self.model_key,))}
            missing={r['text_hash']:r['text'] for r in data.values() if r['company_key'] and r['title_key'] and r['text_hash'] not in cached}
            status='ready'
            try:
                items=list(missing.items())
                for start in range(0,len(items),32):
                    batch=items[start:start+32];vectors=self.embed([text for _,text in batch])
                    if len(vectors)!=len(batch):raise ValueError('invalid_embedding_count')
                    dims={len(v) for v in vectors}
                    if len(dims)!=1 or not 1<=next(iter(dims))<=8192:raise ValueError('invalid_embedding_dimensions')
                    if any(not isinstance(v,list) or any(type(x) not in (int,float) or not math.isfinite(x) for x in v)
                           or not any(v) for v in vectors):raise ValueError('invalid_embedding_values')
                    with self.service.tx() as db:
                        for (key,_),vector in zip(batch,vectors):
                            db.execute('INSERT OR IGNORE INTO job_embedding_cache VALUES (?,?,?,?,?)',
                                (self.model_key,key,len(vector),dumps(vector),self.service.now()));added+=1
            except Exception:
                logging.getLogger(__name__).warning('duplicate_embeddings_unavailable; retaining exact matching and ordinary eligibility')
                status='unavailable'
        # Re-read after model I/O: edited metadata must never inherit stale decisions.
        with self.service.tx() as db:
            matches=matching_records(db,job_id=job_id)
            for match in matches:save_match(db,match,self.service.now())
        return {'embedding_status':status,'embeddings_added':added,'matches':len(matches)}

    def start(self):
        def run():
            while not self.stop.is_set():
                try:self.refresh()
                except Exception:logging.getLogger(__name__).exception('duplicate_match_refresh_failed')
                self.stop.wait(30)
        self.thread=threading.Thread(target=run,name='job-duplicate-matcher',daemon=True);self.thread.start()
