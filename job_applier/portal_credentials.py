"""Small private-file password overrides; public callers receive metadata only."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .managed_shared import ProtocolError
from .workspace_process import FileLock

DEFAULT_REFERENCE = 'credential:profile/accounts/default'
OVERRIDE_PREFIX = 'credential:profile/portal-overrides/'


def scope_key(identity_id, namespace, email):
    return hashlib.sha256(json.dumps([identity_id, namespace, email.casefold()]).encode()).hexdigest()


def read_profile(config):
    selected = (config or {}).get('credential_profile_path')
    if not selected:
        raise ProtocolError('credential_profile_not_configured')
    try:
        path = Path(selected).resolve(strict=True)
        raw = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(raw, dict) or not isinstance(raw.get('accounts', {}), dict):
            raise ValueError()
        overrides = raw.get('portal_password_overrides', {})
        if not isinstance(overrides, dict) or any(not isinstance(v, dict) for v in overrides.values()):
            raise ValueError()
        return path, raw
    except (OSError, ValueError, TypeError):
        raise ProtocolError('credential_profile_unavailable') from None


def update_password(config, account, password):
    """None removes the override. Keep a non-secret fallback for retained references."""
    path, _ = read_profile(config)
    key = scope_key(account['identity_id'], account['namespace'], account['email'])
    try:
        with FileLock(str(path) + '.password-overrides.lock'):
            _, raw = read_profile(config)
            overrides = raw.setdefault('portal_password_overrides', {})
            previous = overrides.get(key, {})
            reference = account.get('credential_ref') or DEFAULT_REFERENCE
            if reference.startswith(OVERRIDE_PREFIX):
                reference = previous.get('fallback_reference', DEFAULT_REFERENCE)
            entry = {'identity_id': account['identity_id'], 'namespace': account['namespace'],
                     'email': account['email'], 'fallback_reference': reference}
            if password is not None:
                entry['password'] = password
            overrides[key] = entry
            # Replace atomically: concurrent readers see the complete old or new profile.
            # mkstemp creates a private file on POSIX; Windows inherits the private directory ACL.
            fd, temporary = tempfile.mkstemp(prefix='.portal-password-', dir=path.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as output:
                    json.dump(raw, output, ensure_ascii=False, indent=2)
                    output.write('\n')
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    except OSError:
        raise ProtocolError('credential_profile_write_failed') from None
    return {'account_id': account['id'], 'password_source': 'override' if password is not None else
            ('default' if reference == DEFAULT_REFERENCE else 'saved'), 'password_editable': True}


def password_metadata(config, accounts):
    """Project only source labels; no password or private path enters a dashboard view."""
    try:
        _, raw = read_profile(config)
        overrides = raw.get('portal_password_overrides', {})
    except ProtocolError:
        for account in accounts:
            account.update(password_source='unavailable', password_editable=False)
        return
    for account in accounts:
        if not account.get('identity_id') or not account.get('namespace') or not account.get('email'):
            account.update(password_source='unavailable', password_editable=False)
            continue
        entry = overrides.get(scope_key(account['identity_id'], account['namespace'], account['email']), {})
        reference = account.get('credential_ref') or DEFAULT_REFERENCE
        if reference.startswith(OVERRIDE_PREFIX):
            reference = entry.get('fallback_reference', DEFAULT_REFERENCE)
        account.update(password_source='override' if entry.get('password') else
                       ('default' if reference == DEFAULT_REFERENCE else 'saved'), password_editable=True)


def resolve_override(raw, package, reference, email):
    """Resolve from current scoped state, including updates during a retained session."""
    account = package.get('account') or {}
    namespace = account.get('namespace') or package.get('namespace')
    identity_id = package['attempt'].get('identity_id')
    if namespace and identity_id:
        key = scope_key(identity_id, namespace, email)
        entry = raw.get('portal_password_overrides', {}).get(key)
        if entry:
            if entry.get('password'):
                return {'email': entry['email'], 'password': entry['password'],
                        'credential_ref': OVERRIDE_PREFIX + key}, reference
            if reference == OVERRIDE_PREFIX + key:
                reference = entry['fallback_reference']
    return None, reference
