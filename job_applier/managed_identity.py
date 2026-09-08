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


def same_job_url(left, right):
    """Compare URLs without changing persisted identity hashes or opaque queries."""
    try:
        a, b = urlsplit(canonical_url(left)), urlsplit(canonical_url(right))
    except (ValueError, ProtocolError):
        return False
    if (a.hostname or '').endswith('.myworkdayjobs.com'):
        a = a._replace(path=a.path.casefold())
        b = b._replace(path=b.path.casefold())
    return a == b


RELATED = """WITH RECURSIVE related(id) AS (
    SELECT ? UNION
    SELECT other.job_id FROM related r
    JOIN job_identity_keys own ON own.job_id=r.id
    JOIN job_identity_keys other ON other.identity_key=own.identity_key
) """


def linked_jobs(db, job_id):
    return [r[0] for r in db.execute(RELATED+'SELECT id FROM related',(job_id,))]


import re

_ALLOWED_WORKDAY_CHILD_ROUTES = (
    "",
    "/apply",
    "/apply/applyManually",
    "/apply/autofillWithResume",
    "/apply/useMyLastApplication",
    "/apply/success",
    "/confirmation",
)

_LOCALE_RE = re.compile(r"^[a-zA-Z]{2}(?:-[a-zA-Z0-9]{2,4})?$")


def is_workday_application_scope(job_url: str, candidate_url: str) -> bool:
    try:
        raw_cand = str(candidate_url).strip()
        job_p = urlsplit(str(job_url).strip())
        cand_p = urlsplit(raw_cand)
        # Encoded separators in a path are ambiguous. In a login redirect query
        # they are normal URL encoding and must be decoded and validated below.
        if any(seq in cand_p.path.lower() for seq in ('%2f', '%2e', '%5c')):
            return False

        # HTTPS only on exact same host
        if job_p.scheme.lower() != 'https' or cand_p.scheme.lower() != 'https':
            return False
        if job_p.netloc.lower() != cand_p.netloc.lower():
            return False
        if cand_p.username or cand_p.password:
            return False

        # Reject dot path tricks in candidate path
        if '..' in cand_p.path or '/.' in cand_p.path:
            return False

        # Reject sensitive path segments
        if any(s in cand_p.path.lower() for s in ('reset-password', 'password-reset', 'verify-email', 'oauth/', 'signin/callback')):
            return False

        # Reject sensitive query parameters
        cand_query = parse_qsl(cand_p.query, keep_blank_values=True)
        if any(k.lower() in ('access_token', 'refresh_token', 'otp', 'password', 'reset_token', 'authorization_code') for k, v in cand_query):
            return False

        # Parse segments
        job_segs = [s for s in job_p.path.strip('/').split('/') if s]
        cand_segs = [s for s in cand_p.path.strip('/').split('/') if s]
        if any(s in ('.', '..') for s in job_segs + cand_segs):
            return False

        # Strip optional locale segment
        if job_segs and _LOCALE_RE.match(job_segs[0]):
            job_segs = job_segs[1:]
        if cand_segs and _LOCALE_RE.match(cand_segs[0]):
            cand_segs = cand_segs[1:]

        # Workday redirects stored lowercase links to mixed-case job paths.
        # Normalize only this comparison, not stored URLs or other ATS paths.
        workday_host = (job_p.hostname or '').endswith('.myworkdayjobs.com')
        if workday_host:
            job_segs = [s.casefold() for s in job_segs]
            cand_segs = [s.casefold() for s in cand_segs]
            if len(job_segs)>=3 and cand_segs==[job_segs[0],'login']:
                if len(cand_query)!=1 or cand_query[0][0].casefold()!='redirect':return False
                redirect=cand_query[0][1]
                if not redirect.startswith('/') or redirect.startswith('//') or '\\' in redirect:return False
                destination=urlsplit(redirect)
                if destination.query or destination.fragment:return False
                parts=[s.casefold() for s in destination.path.strip('/').split('/') if s]
                if parts and _LOCALE_RE.fullmatch(parts[0]):parts=parts[1:]
                if len(parts)<3 or parts[0]!=job_segs[0] or parts[1] not in ('job','details'):return False
                return is_workday_application_scope(job_url,urlunsplit((job_p.scheme,job_p.netloc,destination.path,'','')))

        # Workday's search detail link omits the location segment that Apply
        # inserts into the canonical job route. Keep the exact career site and
        # full requisition slug (including any suffix), plus the child allowlist.
        if workday_host and (
            job_segs[1:2] == ['details'] or cand_segs[1:2] == ['details']
        ):
            for segments in (job_segs, cand_segs):
                if len(segments) >= 3 and segments[1] == 'details' and '_' in segments[2]:
                    segments[1] = 'job'
                elif len(segments) >= 4 and segments[1] == 'job' and '_' in segments[3]:
                    del segments[2]

        if len(cand_segs) < len(job_segs):
            return False
        if cand_segs[:len(job_segs)] != job_segs:
            return False

        # Check remaining child route
        child_parts = cand_segs[len(job_segs):]
        child_route = "/" + "/".join(child_parts) if child_parts else ""
        allowed_routes = (route.casefold() for route in _ALLOWED_WORKDAY_CHILD_ROUTES) if workday_host else _ALLOWED_WORKDAY_CHILD_ROUTES
        return child_route in allowed_routes
    except Exception:
        return False


def is_same_application_scope(job_url: str, candidate_url: str) -> bool:
    if is_workday_application_scope(job_url, candidate_url):
        return True
    try:
        job_p = urlsplit(str(job_url).strip())
        cand_p = urlsplit(str(candidate_url).strip())
        if job_p.scheme.lower() != cand_p.scheme.lower() or job_p.scheme.lower() not in ('https', 'http'):
            return False
        job_host = job_p.netloc.lower()
        cand_host = cand_p.netloc.lower()
        if job_host == 'boards.greenhouse.io': job_host = 'job-boards.greenhouse.io'
        if cand_host == 'boards.greenhouse.io': cand_host = 'job-boards.greenhouse.io'
        if job_host != cand_host:
            return False
        if any(seq in str(candidate_url).lower() for seq in ('%2f', '%2e', '%5c', '..')):
            return False
        cand_query = parse_qsl(cand_p.query, keep_blank_values=True)
        if any(k.lower() in ('access_token', 'refresh_token', 'otp', 'password', 'reset_token', 'authorization_code') for k, v in cand_query):
            return False
        expected_path = job_p.path.rstrip('/')
        actual_path = cand_p.path.rstrip('/')
        return actual_path in (expected_path, expected_path + '/apply', expected_path + '/confirmation')
    except Exception:
        return False


def is_workday_candidate_home(job_url, candidate_url):
    """Exact tenant career-site confirmation read surface; never authorizes writes."""
    try:
        job=urlsplit(canonical_url(job_url)); candidate=urlsplit(canonical_url(candidate_url))
        if job.scheme!='https' or candidate.scheme!='https' or job.netloc!=candidate.netloc:
            return False
        if not (job.hostname or '').endswith('.myworkdayjobs.com') or candidate.query:
            return False
        parts=job.path.strip('/').split('/')
        other=candidate.path.strip('/').split('/')
        if parts and _LOCALE_RE.fullmatch(parts[0]):parts=parts[1:]
        if other and _LOCALE_RE.fullmatch(other[0]):other=other[1:]
        return bool(parts) and [s.casefold() for s in other]==[parts[0].casefold(),'candidatehome']
    except (ValueError,ProtocolError):
        return False
