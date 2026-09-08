"""Explicit candidate answer preferences shared by every ATS and executor."""
import json
import math
import re

POLICY_KEYS={'salary_expectation','routine_privacy_consent','submission_evidence_sources'}


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
