"""Verified job identity aliases without deleting or rewriting historical jobs."""
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import hashlib
from .managed_shared import ProtocolError, dumps


def canonical_url(url):
    p = urlsplit(str(url).strip())
    if p.scheme not in ('https','http') or not p.hostname or p.username or p.password:
        raise ProtocolError('invalid_job_url')
    if any(s in p.path.lower() for s in ('reset-password','password-reset','verify-email','oauth/','signin/callback')):
        raise ProtocolError('sensitive_url')
    query = parse_qsl(p.query, keep_blank_values=True)
    if any(k.lower() in ('access_token','refresh_token','otp','password','reset_token','authorization_code') for k,v in query):
        raise ProtocolError('sensitive_url')
    tracking={'gh_src','utm_source','utm_medium','utm_campaign','utm_term','utm_content','rx_campaign','rx_source','rx_medium','rx_ts'}
    # token, rx_job, and unknown query keys can identify a requisition.
    query=sorted((k,v) for k,v in query if k.lower() not in tracking)
    host=p.netloc.lower()
    if host=='boards.greenhouse.io': host='job-boards.greenhouse.io'
    return urlunsplit((p.scheme.lower(),host,p.path.rstrip('/'),urlencode(query),''))


def job_key(url, namespace=None, requisition_id=None):
    data=[namespace,str(requisition_id)] if namespace and requisition_id else [canonical_url(url)]
    return hashlib.sha256(dumps(data).encode()).hexdigest()


RELATED = """WITH RECURSIVE related(id) AS (
    SELECT ? UNION
    SELECT other.job_id FROM related r
    JOIN job_identity_keys own ON own.job_id=r.id
    JOIN job_identity_keys other ON other.identity_key=own.identity_key
) """


def linked_jobs(db, job_id):
    return [r[0] for r in db.execute(RELATED+'SELECT id FROM related',(job_id,))]
