"""Shared candidate answer preferences and private application answer history."""
import json
import math
import re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit

POLICY_KEYS={'salary_expectation','routine_privacy_consent','submission_evidence_sources'}


def save_answer_history(config,package,attempt_id,answers,*,page,source,basis=None):
    """Private question/answer history, separate from redacted operational telemetry."""
    from .managed_redaction import reject_secrets
    if not config.get('spool_dir'):return {}
    folder=Path(config['spool_dir'])/'answers'
    if not folder.is_absolute():raise ValueError('absolute_spool_required')
    path=folder/('attempt-'+str(int(attempt_id))+'.json')
    job=package['job'];attempt=package.get('attempt',{})
    history=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {
        'attempt_id':attempt_id,'session_id':attempt.get('local_session_id'),
        'company':job.get('company'),'job_title':job.get('title'),'job_id':job.get('id'),
        'job_url':job['url'],'platform':package.get('platform'),
        'portal_namespace':package.get('namespace') or urlsplit(job['url']).hostname,'answers':[]}
    if history['attempt_id']!=attempt_id or history['job_url']!=package['job']['url']:
        raise ValueError('answer_history_scope_mismatch')
    metadata_changed=False
    for key,value in {'company':job.get('company'),'job_title':job.get('title'),
                      'company_source':job.get('company_source'),'session_id':attempt.get('local_session_id')}.items():
        if value and not history.get(key):history[key]=value;metadata_changed=True
    added=0
    for answer in answers:
        row={key:answer.get(key,'') for key in ('field','question','answer')}
        if any(not isinstance(v,str) or not v.strip() for v in row.values()):continue
        if re.search(r'password|passwd|\botp\b|token|secret|social.?security|\bssn\b|tax.?id|bank.?account|routing.?number|credit.?card',row['question']+' '+row['field'],re.I):continue
        row.update(page=answer.get('page') or page,source=source,answer_basis=basis or 'not_recorded')
        try:reject_secrets(row)
        except ValueError:continue
        previous=next((r for r in reversed(history['answers']) if r['page']==row['page'] and r['field']==row['field'] and r['question']==row['question']),None)
        if previous and previous['answer']==row['answer']:continue
        row['observed_at']=datetime.now(timezone.utc).isoformat()
        history['answers'].append(row);added+=1
    if added or metadata_changed and path.is_file():
        folder.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(history,indent=2,ensure_ascii=False),encoding='utf-8');temporary.replace(path)
    return {'answer_history_path':str(path),'answers_added':added} if path.is_file() else {}


async def capture_answers(browser_page,config,package,ownership,*,page='form',source='employer_form',basis=None):
    # Called during filling/advancement, never as an extra final-review pass.
    if not config.get('spool_dir'):return {}
    from .browser_controls import FORM
    try:
        captured=await browser_page.evaluate_function(FORM,{'method':'answers','page':page})
        context=captured.get('context',{});job=dict(package['job'])
        if not job.get('company') and context.get('company'):
            job.update(company=context['company'],company_source=context.get('source'))
        if not job.get('title') and context.get('job_title'):job['title']=context['job_title']
        return save_answer_history(config,dict(package,job=job),ownership['attempt_id'],captured['answers'],page=page,source=source,basis=basis)
    except Exception as exc:
        # An audit failure must not disguise an executed form write as retryable.
        return {'answer_history_error':type(exc).__name__}


def approved_policy(value):
    """Import the supported preferences without importing legacy execution rules."""
    if not isinstance(value,dict):return {}
    result={}
    salary=value.get('salary_expectation')
    if isinstance(salary,dict):
        amount=salary.get('fallback_amount')
        if type(amount) in (int,float) and math.isfinite(amount) and amount>0:
            result['salary_expectation']={
                'use_posted_range_max':salary.get('use_posted_range_max') is True,
                'fallback_amount':amount,'currency':str(salary.get('currency','USD')).upper(),
                'period':salary.get('period','year')}
    if type(value.get('routine_privacy_consent')) is bool:
        result['routine_privacy_consent']=value['routine_privacy_consent']
    if isinstance(value.get('submission_evidence_sources'),list):
        result['submission_evidence_sources']=[s for s in value['submission_evidence_sources']
            if s in ('employer','simplify','user_reported')]
    return result


def profile_policy(package):
    profile=package['attempt'].get('profile_json') or {}
    if isinstance(profile,str):profile=json.loads(profile)
    return approved_policy(profile.get('application_answer_policy'))


def salary_answer(policy, text='', posted_range=None):
    """Return an approved expectation, never use a candidate's private range as a job range."""
    salary=policy.get('salary_expectation') or {}
    if not salary:return None
    if re.search(r'\b(?:CAD|AUD|EUR|GBP)\b',text or '',re.I) and salary.get('currency')=='USD':return None
    if salary.get('use_posted_range_max'):
        if isinstance(posted_range,dict):
            if str(posted_range.get('currency',salary['currency'])).upper()!=salary['currency']:return None
            if posted_range.get('period',salary.get('period','year'))!=salary.get('period','year'):return None
            high=posted_range.get('max')
            if type(high) in (int,float) and math.isfinite(high) and high>0:return str(int(high))
        # The official Simplify role panel displays the job's advertised range.
        # Multiple different ranges are ambiguous; the executor can supply the
        # applicable location range explicitly to the same operation.
        number=r'(\d[\d,]*(?:\.\d+)?\s*[kK]?)'
        pattern=r'(?:\$|USD\s*)\s*'+number+r'\s*(?:-|–|—|to)\s*(?:\$|USD\s*)?\s*'+number
        ranges=set()
        if salary.get('currency')=='USD':
            for low,high in re.findall(pattern,text or '',re.I):
                def amount(v):
                    v=v.replace(',','').replace(' ','')
                    return float(v[:-1])*1000 if v.lower().endswith('k') else float(v)
                lo,hi=amount(low),amount(high)
                if 0<lo<=hi:ranges.add((lo,hi))
        if ranges and re.search(r'per hour|hourly|per month|monthly',text or '',re.I):return None
        if len(ranges)==1:return str(int(next(iter(ranges))[1]))
        if len(ranges)>1:return None
    return str(int(salary['fallback_amount']))


async def apply_policy(page, package, observed, *, completed=None, posted_range=None, dry_run=False):
    """Only salary expectations and routine privacy boxes; Simplify still fills the form."""
    from .browser_controls import form_action
    policy=profile_policy(package);completed=completed if completed is not None else []
    results=[]
    for field in observed.get('inventory',[]):
        label=field.get('label') or field.get('text') or ''
        key=(observed.get('page_signature') or observed.get('step',''))+'|'+label
        if key in completed or not field.get('enabled') or not field.get('ref'):continue
        params=None
        if policy.get('routine_privacy_consent') and (field.get('type')=='checkbox' or field.get('role')=='checkbox'):
            if (re.search(r'privacy|personal data|data processing|data protection',label,re.I) and
                not re.search(r'marketing|job alerts|talent community|newsletter',label,re.I)):
                params={'method':'check','ref':field['ref'],'value':True}
        elif (field.get('tag')=='INPUT' and field.get('type') in ('text','number','tel','') and
              re.search(r'salary|compensation|pay expectation',label,re.I) and
              not re.search(r'current|previous|past|history|hourly|per hour|monthly|per month',label,re.I)):
            amount=salary_answer(policy,observed.get('panel_text',''),posted_range)
            if amount is not None:params={'method':'fill','ref':field['ref'],'value':amount}
        if params:
            if dry_run:
                results.append({'field':label,'pending':True});continue
            result=await form_action(page,params)
            results.append({'field':label,'committed':result.get('committed',False),'reason':result.get('reason')})
            if result.get('committed'):completed.append(key)
    return {'changed':any(r.get('committed') for r in results),'fields':results}
