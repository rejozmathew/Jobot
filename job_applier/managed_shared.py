"""Small shared protocol primitives; no runtime initialization."""
import json
import uuid
from functools import wraps


class ProtocolError(ValueError):
    def __init__(self, code, detail=''):
        self.code = code
        super().__init__(code + (': ' + detail if detail else ''))


def legacy_writer(method):
    """Legacy entrypoints cannot bypass managed ownership or overwrite its history."""
    @wraps(method)
    def guarded(self, *args, **kwargs):
        manager = getattr(self, 'db_manager', None) or getattr(self, 'db', None)
        manager.require_legacy()
        return method(self, *args, **kwargs)
    return guarded


def uid():
    return str(uuid.uuid4())


def dumps(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


LEGACY_IDENTITY_FIELDS = frozenset({
    'full_name', 'first_name', 'middle_name', 'last_name', 'preferred_name',
    'email', 'phone', 'country code', 'address', 'location', 'linkedin', 'website', 'github'
})
LEGACY_ALLOWED_SECTIONS = frozenset({
    'identity', 'summary', 'years_experience', 'target_roles', 'industries',
    'skills', 'leadership_scope', 'work_authorization', 'work_preferences',
    'dealbreakers', 'eeo_information', 'standard_answers', 'experience',
    'education', 'certifications', 'projects', 'languages', 'links', 'resume'
})
LEGACY_EXCLUDED_SECTIONS = frozenset({
    'accounts', 'cover_letter', 'login', 'greenhouse',
    'automation_preferences', 'application_answer_policy'
})


def sanitize_legacy_profile(data):
    from .managed_redaction import reject_secrets
    if not isinstance(data, dict):
        raise ProtocolError('invalid_profile_data')
    sanitized = {}
    skipped = []

    for key, value in data.items():
        if key=='application_answer_policy':
            from .application_answers import approved_policy
            policy=approved_policy(value)
            if policy:sanitized[key]=policy
            else:skipped.append(key)
            continue
        if key in LEGACY_EXCLUDED_SECTIONS:
            skipped.append(key)
            continue
        if key not in LEGACY_ALLOWED_SECTIONS:
            skipped.append(key)
            continue

        if key == 'identity':
            if isinstance(value, dict):
                clean_identity = {}
                for ik, iv in value.items():
                    if ik in LEGACY_IDENTITY_FIELDS:
                        clean_identity[ik] = iv
                    else:
                        skipped.append(f"identity.{ik}")
                sanitized['identity'] = clean_identity
            else:
                skipped.append('identity')
        elif key == 'resume':
            if isinstance(value, dict):
                clean_resume = {}
                if 'path' in value:
                    clean_resume['path'] = value['path']
                if 'text' in value:
                    skipped.append('resume.text')
                for rk in value:
                    if rk not in ('path', 'text'):
                        skipped.append(f"resume.{rk}")
                sanitized['resume'] = clean_resume
            else:
                skipped.append('resume')
        else:
            sanitized[key] = value

    reject_secrets(sanitized)
    return sanitized, sorted(skipped)
