"""Bounded worker job packages assembled from shared authoritative records."""
import json
from urllib.parse import urlsplit
from .managed_shared import ProtocolError



def platform_for_url(url):
    host=urlsplit(url).hostname or ''
    for suffix,name in (('greenhouse.io','greenhouse'),('myworkdayjobs.com','workday'),('workday.com','workday'),('icims.com','icims'),('lever.co','lever'),('ashbyhq.com','ashby')):
        if host==suffix or host.endswith('.'+suffix):return name
    return 'unknown'


class ContextServices:
    def application_context(self,attempt_id,worker_id=None,platform=None,namespace=None):
        with self.tx() as db:
            attempt=dict(self._get(db,'application_attempts',attempt_id))
            if worker_id is not None and attempt['worker_id']!=worker_id:raise ProtocolError('attempt_forbidden')
            job=dict(self._get(db,'jobs',attempt['job_id']))
            metadata=json.loads(job['metadata_json'] or '{}')
            selected_platform=platform or metadata.get('platform') or (attempt['platform'] if attempt['platform']!='unknown' else platform_for_url(job['url']))
            selected_namespace=namespace if namespace is not None else metadata.get('account_namespace')
            verified_namespace=self._job_account_namespace(db,job,selected_namespace)
            documents=self._documents_status(db,job['id'],attempt['identity_id'],attempt_id)
            semantic=self._field_context(db,attempt)
            attempt['company']=job['company']
            attempt['platform']=selected_platform
            import hashlib
            attempt['profile_hash']=hashlib.sha256((attempt.get('profile_json') or '').encode()).hexdigest()
        account=self.account_strategy(namespace=verified_namespace,identity_id=attempt['identity_id']) if verified_namespace else None
        from .application_answers import approved_policy
        answer_policy=approved_policy(json.loads(attempt['profile_json']).get('application_answer_policy'))
        return {'attempt':attempt,'job':job,'documents':documents,'answer_policy':answer_policy,
            'helpers':self.helpers_for_context(selected_platform,verified_namespace),
            'lessons':self.lessons_for_context(selected_platform,verified_namespace),
            'account':account,'platform':selected_platform,'namespace':verified_namespace,
            'field_budget':{'status':'measured_context' if semantic else 'coarse_only','context':semantic},
            'blocker':'required_document_missing' if not documents['ready'] else None,
            'instruction':'Use this claimed snapshot. Lessons are advisory and never override facts, policy or permissions.',
            'profile_hash':attempt['profile_hash']}
