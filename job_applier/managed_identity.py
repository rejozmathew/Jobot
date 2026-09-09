"""Verified job identity aliases without deleting or rewriting historical jobs."""
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import hashlib
import re
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


def query_requisition(url):
    """A consistent explicit Greenhouse query id, not a guessed path number."""
    values=[value for key,value in parse_qsl(urlsplit(url).query,keep_blank_values=True) if key=='gh_jid']
    if not values:return None
    if len(set(values))!=1 or not re.fullmatch(r'[0-9]{1,20}',values[0]):return None
    tail=urlsplit(url).path.rstrip('/').rsplit('/',1)[-1]
    if tail.isdigit() and tail!=values[0]:return None
    return values[0]


def greenhouse_query_identity(url):
    """Narrow employer posting/form aliases; unknown query keys remain meaningful."""
    try:
        p=urlsplit(canonical_url(url));requisition=query_requisition(url)
        if not requisition:return None
        parts=p.path.strip('/').split('/')
        if parts[-1] in ('apply','confirmation'):parts=parts[:-1]
        if not (parts in (['jobs'],['form']) or
                len(parts)>1 and parts[0]=='jobs' and parts[-1]==requisition):return None
        opaque=tuple((k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k!='gh_jid')
        return p.scheme,p.netloc,requisition,opaque
    except (ValueError,ProtocolError):return None


def same_job_url(left, right):
    """Compare URLs without changing persisted identity hashes or opaque queries."""
    try:
        a, b = urlsplit(canonical_url(left)), urlsplit(canonical_url(right))
    except (ValueError, ProtocolError):
        return False
    wd_left,wd_right=workday_identity(left),workday_identity(right)
    if wd_left or wd_right:return bool(wd_left and wd_right and wd_left==wd_right)
    gh_left,gh_right=greenhouse_query_identity(left),greenhouse_query_identity(right)
    if gh_left and gh_right:return gh_left==gh_right
    if any(k=='gh_jid' for p in (a,b) for k,v in parse_qsl(p.query,keep_blank_values=True)):
        if not query_requisition(left) or not query_requisition(right):return False
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


_LOCALE_RE = re.compile(r"^[a-zA-Z]{2}(?:-[a-zA-Z0-9]{2,4})?$")


def _workday_url(url):
    """Parse the portal and requisition, never the display title or location."""
    from urllib.parse import unquote
    try:
        p = urlsplit(canonical_url(url))
        if p.scheme != 'https' or not (p.hostname or '').endswith('.myworkdayjobs.com'):
            return None
        if any(x in p.path.lower() for x in ('%2f', '%2e', '%5c')) or '..' in p.path or '/.' in p.path:
            return None
        parts = [unquote(x).casefold() for x in p.path.strip('/').split('/') if x]
        if parts and _LOCALE_RE.fullmatch(parts[0]) and parts[1:2] not in (['job'],['details'],['login']):parts = parts[1:]
        return p, parts
    except (ValueError, ProtocolError):return None


def workday_identity(url):
    parsed = _workday_url(url)
    if not parsed:return None
    p, parts = parsed
    if parts[1:] == ['login']:
        query = parse_qsl(p.query, keep_blank_values=True)
        if len(query) != 1 or query[0][0].casefold() != 'redirect':return None
        redirect = query[0][1]
        if not redirect.startswith('/') or redirect.startswith('//') or '\\' in redirect:return None
        destination = urlsplit(redirect)
        if destination.query or destination.fragment:return None
        route = urlunsplit((p.scheme, p.netloc, destination.path, '', ''))
        parsed_destination = _workday_url(route)
        if not parsed_destination or parsed_destination[1][1:2] not in (['job'], ['details']):return None
        return workday_identity(route)
    index = 3 if parts[1:2] == ['job'] else 2 if parts[1:2] == ['details'] else None
    if index is None or len(parts) <= index or '_' not in parts[index]:return None
    slug = parts[index]
    # Preserve requisition suffixes such as R100_1; do not mistake its final 1
    # for the entire requisition. Other Workday IDs use the final slug separator.
    markers=list(re.finditer(r'_(?:jr|req|r)[-_]?\d',slug))
    requisition = slug[markers[-1].start()+1:] if markers else slug.rsplit('_', 1)[-1]
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*', requisition):return None
    for key, value in parse_qsl(p.query, keep_blank_values=True):
        if key.casefold() in ('jobid', 'requisitionid', 'reqid') and value.casefold() != requisition:
            return None
    return ('workday', p.netloc, parts[0], requisition)


def job_identity(url):
    """One comparison identity; stored URL hashes and historical rows stay intact."""
    identity = workday_identity(url)
    if identity:return identity
    gh = greenhouse_query_identity(url)
    if gh:return ('requisition_query', gh)
    return (canonical_url(url),)


def job_requisition(job):
    """Confirmation consumes the same complete requisition as job ownership."""
    identity=workday_identity(job['url'])
    return identity[-1] if identity else job.get('requisition_id') or ''


def is_workday_application_scope(job_url, candidate_url):
    expected = workday_identity(job_url)
    parsed = _workday_url(candidate_url)
    if not expected or not parsed:return False
    p, parts = parsed
    if not parts or (p.netloc, parts[0]) != expected[1:3]:return False
    actual = workday_identity(candidate_url)
    if actual:
        # Application steps are site presentation, not an independent permission
        # list. The complete job identity remains the same at every child route.
        return actual == expected
    if parts[1:] != ['login']:return False
    query = parse_qsl(p.query, keep_blank_values=True)
    if not query:return True  # The owned flow already binds this portal and job.
    if len(query) != 1 or query[0][0].casefold() != 'redirect':return False
    redirect = query[0][1]
    if not redirect.startswith('/') or redirect.startswith('//') or '\\' in redirect:return False
    destination = urlsplit(redirect)
    if destination.query or destination.fragment:return False
    return workday_identity(urlunsplit((p.scheme, p.netloc, destination.path, '', ''))) == expected


def application_match(job_url, candidate_url):
    """Separate a conflicting identity from a page the helper cannot recognize."""
    if is_same_application_scope(job_url, candidate_url):return {'status': 'same_job'}
    try:
        expected, actual = urlsplit(job_url), urlsplit(candidate_url)
        different = expected.netloc.casefold() != actual.netloc.casefold()
        wd_expected, wd_actual = workday_identity(job_url), workday_identity(candidate_url)
        if wd_expected and wd_actual:different = wd_expected != wd_actual
        gh_expected, gh_actual = query_requisition(job_url), query_requisition(candidate_url)
        if gh_expected and gh_actual:different = different or gh_expected != gh_actual
        return {'status': 'different_job' if different else 'identity_unresolved'}
    except ValueError:return {'status': 'identity_unresolved'}


def public_url(url):
    """Diagnostics never require authentication query strings or fragments."""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, '', ''))


def is_same_application_scope(job_url: str, candidate_url: str) -> bool:
    try:
        workday_host=urlsplit(str(job_url).strip()).hostname or ''
        if workday_host.casefold().endswith('.myworkdayjobs.com') and workday_identity(job_url):
            return is_workday_application_scope(job_url, candidate_url)
        job_p = urlsplit(canonical_url(job_url))
        cand_p = urlsplit(canonical_url(candidate_url))
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
        if any(k=='gh_jid' for p in (job_p,cand_p) for k,v in parse_qsl(p.query,keep_blank_values=True)):
            if not query_requisition(job_url) or not query_requisition(candidate_url):return False
            expected_gh,actual_gh=greenhouse_query_identity(job_url),greenhouse_query_identity(candidate_url)
            if expected_gh and actual_gh:return expected_gh==actual_gh
        if job_p.query!=cand_p.query:return False
        expected_path = job_p.path.rstrip('/')
        actual_path = cand_p.path.rstrip('/')
        return actual_path in (expected_path, expected_path + '/apply', expected_path + '/confirmation')
    except Exception:
        return False


def is_post_submit_scope(job_url: str, candidate_url: str) -> bool:
    """Read-only confirmation scope after intent, never an application-write grant."""
    if is_same_application_scope(job_url,candidate_url) or is_workday_candidate_home(job_url,candidate_url):
        return True
    try:
        job=urlsplit(canonical_url(job_url));current=urlsplit(canonical_url(candidate_url))
        if job.scheme!=current.scheme or job.netloc!=current.netloc:return False
        # Redirects may drop a query but never introduce a conflicting identity.
        expected=parse_qsl(job.query,keep_blank_values=True)
        actual=parse_qsl(current.query,keep_blank_values=True)
        for key in {k for k,v in actual}:
            if [v for k,v in actual if k==key]!=[v for k,v in expected if k==key]:return False
        if any(s in current.path.lower() for s in ('/login','/signin','/reset','/verify','/oauth','..')):return False
        a=job.path.strip('/').split('/');b=current.path.strip('/').split('/')
        if (job.hostname or '').endswith('.myworkdayjobs.com'):
            if a and _LOCALE_RE.fullmatch(a[0]):a=a[1:]
            if b and _LOCALE_RE.fullmatch(b[0]):b=b[1:]
            if not a or not b or a[0].casefold()!=b[0].casefold():return False
            if [part.casefold() for part in b[1:]]==['jobtasks','completed','application']:return not current.query
            # A different requisition on the same career site is never evidence.
            if 'job' in b:
                i=b.index('job');j=a.index('job') if 'job' in a else -1
                return j>=0 and len(a)>j+2 and len(b)>i+2 and b[i+2].casefold()==a[j+2].casefold()
            return len(b)==1 or all(part.casefold() in ('apply','applymanually','confirmation','success','thankyou','thank-you','submitted','userhome','candidatehome') for part in b[1:])
        # Shared company/Greenhouse/Lever thank-you destinations. Keep the
        # employer path prefix and reject another job's id in that prefix.
        end=b[-1].casefold() if b else ''
        if end not in ('confirmation','success','thank-you','thank_you','thankyou','submitted'):return False
        if a and b and a[0].casefold()!=b[0].casefold():return False
        for marker in ('jobs','job','positions','posting','postings'):
            if marker in a and marker in b:
                i=a.index(marker);j=b.index(marker)
                if len(a)>i+1 and len(b)>j+1 and b[j+1]!=a[i+1]:return False
        return True
    except (ValueError,ProtocolError):return False


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
