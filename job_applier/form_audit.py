"""Compact, pure projection of the shared DOM inventory. Never a write gate."""
import re
import uuid


def data_control(f):
    return (f.get('tag') in ('INPUT','TEXTAREA','SELECT') and f.get('type') not in
            ('hidden','submit','button','reset','image') or f.get('role') in
            ('textbox','combobox','checkbox','radio','listbox','switch'))


def group_key(f):
    return (f.get('document_id',f.get('document')),f.get('root_id'),f.get('form_id'),f.get('group_id') or f.get('name') or f.get('ref'))


def classify(observed):
    """One definition for audit, legacy residuals and submission continuation."""
    fields=[f for f in observed.get('inventory',[]) if data_control(f)]
    groups={}
    for f in fields:
        if (f.get('role') or f.get('type'))=='radio':groups.setdefault(group_key(f),[]).append(f)
    results=[];seen=set()
    for f in fields:
        if f.get('enabled') is False:continue
        kind=f.get('role') or f.get('type');required=f.get('required') is True
        present=None if f.get('attachment')=='pending' else f.get('present');members=groups.get(group_key(f),[]) if kind=='radio' else []
        if members:
            if group_key(f) in seen:continue
            seen.add(group_key(f));required=any(x.get('required') for x in members)
            present=True if any(x.get('checked') is True for x in members) else False if all(x.get('checked') is False for x in members) else None
        elif kind in ('checkbox','switch'):present=f.get('checked')
        private=f.get('private') or f.get('type')=='password'
        invalid=f.get('validation',{}).get('rejected') is True
        state=('unknown' if f.get('hidden_validation') or f.get('attachment')=='pending' else
               'credential' if private and (present is False or invalid) else
               'invalid' if f.get('attachment')=='rejected' else
               'missing' if required and present is False else
               'invalid' if invalid else 'unknown' if present is None else
               'filled' if present else 'optional')
        results.append((f,state,required,present,members))
    return results


def normalize(text):
    return re.sub(r'[^\w]+',' ',re.sub(r'(?:\*|\(required\)|\brequired)\s*$','',text or '',flags=re.I).casefold()).strip()


def recovery(observed):
    stop=observed.get('controls',{}).get('stop',{})
    if stop.get('enabled') and stop.get('ref'):
        return {'operation':'browser','parameters':{'method':'simplify','action':'stop','ref':stop['ref']},
                'instruction':'Use observed Stop/Cancel if taking over; verify settlement before form writes.'}
    return {'operation':'browser','parameters':{'method':'audit'},
            'instruction':'Inspect the returned audit and owned frame/panel once; use browser screenshot and read it for unresolved coverage/writer evidence. Do not repeat unchanged observations. Reload/restart only for an evidenced unusable page, not optional blanks or a review count.'}


def audit(observed, *, writer=None):
    required=[];invalid=[];unknown=[];credentials={};optional=0;filled=0;attachments=0;public=[]
    for f,state,mandatory,present,members in classify(observed):
        kind=f.get('role') or f.get('type')
        private=bool(f.get('private') or f.get('type')=='password')
        item={k:f[k] for k in ('ref','label','type','role','document_id','form_id','root_id','section','section_id','required_evidence','validation','attachment') if k in f}
        item.update(required=mandatory,presence='unknown' if present is None else 'filled' if present else 'missing',private=private)
        if not private:
            method='upload' if kind=='file' else 'check' if kind in ('checkbox','radio','switch') else 'select' if f.get('tag')=='SELECT' or kind in ('combobox','listbox') or f.get('haspopup') in ('listbox','menu','true') else 'fill'
            item['action']={'method':method,'ref':f.get('ref')}
        if state=='credential':
            # Secret tasks expose presence/roles only, never values, lengths or hashes.
            key=(f.get('document_id',f.get('document')),f.get('form_id'),'password' if f.get('type')=='password' else 'verification')
            task=credentials.setdefault(key,{'kind':'employer_credentials' if key[-1]=='password' else 'verification','fields':[]})
            task['fields'].append(item)
        elif state=='missing':required.append(item)
        elif state=='invalid':invalid.append(item)
        elif state=='unknown':unknown.append(item)
        elif state=='optional':optional+=1
        elif state=='filled' and not private:filled+=1
        if f.get('attachment')=='accepted':attachments+=1
        if not private:public.append((f,item,state))
    for task in credentials.values():
        if task['kind']!='employer_credentials':continue
        primary=[f for f in task['fields'] if not re.search(r'confirm|re.?enter|repeat',f.get('label',''),re.I)]
        confirmation=[f for f in task['fields'] if f not in primary]
        params={}
        if len(primary)==1:params['password_ref']=primary[0]['ref']
        if len(confirmation)==1:params['confirmation_ref']=confirmation[0]['ref']
        task.update(account_mode='create-account' if confirmation else 'sign-in',
                    missing_roles=list(params),next_operation={'operation':'credentials','parameters':params})
    reviews=[];counts=dict(matched_required=0,matched_optional=0,already_filled=0,unmatched=0,ambiguous=0)
    for row in observed.get('review_items',[]):
        row={'label':row} if isinstance(row,str) else row
        candidates=[(f,item,state) for f,item,state in public if
                    (row.get('ref') and row['ref']==f.get('ref') or row.get('id') and row['id']==f.get('id') or
                     normalize(row.get('label')) and normalize(row['label']) in (normalize(f.get('label')),normalize(f.get('question')),normalize(f.get('section')) if f.get('type')=='file' else ''))]
        for key in ('document_id','section','type'):
            if row.get(key):candidates=[c for c in candidates if normalize(c[0].get(key))==normalize(row[key])]
        disposition='unmatched' if not candidates else 'ambiguous' if len(candidates)>1 else 'already_filled' if candidates[0][2]=='filled' else 'matched_required' if candidates[0][1]['required'] else 'matched_optional'
        counts[disposition]+=1
        reviews.append({'label':row.get('label',''),'disposition':disposition,'refs':[i.get('ref') for _,i,_ in candidates]})
    frames=observed.get('application_frames',{})
    diagnostics=(frames.get('diagnostics',[]) if isinstance(frames,dict) else observed.get('frame_diagnostics',[]))+observed.get('coverage_diagnostics',[])
    native=observed.get('native',{});stage=observed.get('stage') or {'name':observed.get('step','unknown'),'evidence':[]}
    advance=native.get('continue') or native.get('apply') or native.get('submit') or {}
    advancement=({'ref':advance['ref'],'label':advance.get('label',''),'kind':'final_submit' if advance is native.get('submit') else 'stage_advance',
                  'final_application_submit':advance is native.get('submit')} if advance.get('enabled') and advance.get('ref') else None)
    writer=writer or {'ui_status':observed.get('status','unknown'),'state':observed.get('writer_state','unverified'),
                       'native_takeover_authorized':False,'terminal_evidence':observed.get('terminal_evidence',False)}
    result={'audit_version':1,'observation_id':observed.get('observation_id') or str(uuid.uuid4()),'document_id':observed.get('document_id'),
        'stage':stage,'coverage':{'status':'incomplete' if diagnostics else 'complete_for_observed_supported_controls',
            'documents_scanned':1+(frames.get('count',0) if isinstance(frames,dict) else len(frames)),
            'unresolved_documents':diagnostics,'truncated':False},'writer':writer,
        'summary':{'observed_data_controls':sum(1 for f in observed.get('inventory',[]) if data_control(f)),
            'filled_nonprivate_controls':filled,'accepted_attachment_widgets':attachments,'required_missing_nonprivate':len(required),
            'missing_credential_controls':sum(len(t['fields']) for t in credentials.values()),'invalid_nonprivate':len(invalid),'optional_blank_count':optional},
        'required_missing':required,'invalid_blockers':invalid,'credential_tasks':list(credentials.values()),'unknown_controls':unknown,
        'optional_ignored':{'count':optional,'reason':'empty_not_required_no_blocking_validation'},
        'simplify_review':{'count':observed.get('review_count'),'source':'observed_panel' if observed.get('review_items') else 'review_items_unavailable',
            'authority':'advisory',**counts,'items':reviews},'advancement':advancement,
        'validation_summary':observed.get('validation_summary',[]),
        'metrics':observed.get('audit_metrics',{}),
        'next_operation':recovery(observed),
        'instruction':'Repair required_missing, invalid_blockers and private credential_tasks only; ignore optional blanks and advisory unmatched review rows. Unknown is not empty. Continue the existing ATS flow after repair; this audit never grants writer permission or proves submission.'}
    if writer.get('native_takeover_authorized'):
        if credentials:result['next_operation']=next(iter(credentials.values())).get('next_operation',recovery(observed))
        elif not required and not invalid and advancement:
            result['next_operation']={'operation':'browser','parameters':{'method':'submit' if advancement['final_application_submit'] else 'click','ref':advancement['ref']}}
    return result
