"""Private credentials for the original browser-use executor.

The managed runtime has its own credential references. This module only replaces
the legacy executor's former shared account-creation default.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import string
from urllib.parse import urlsplit


def account_password(profile: dict, job_url: str, profile_path: Path | None = None) -> str:
    accounts = profile.get('accounts') or {}
    default = accounts.get('default') or {}
    login = profile.get('login') or {}
    configured = str(default.get('password') or login.get('password') or '').strip()
    if configured:
        return configured
    configured = os.environ.get('JOB_APPLIER_FALLBACK_PASSWORD', '').strip()
    if configured:
        return configured
    email = str(default.get('email') or login.get('email') or (profile.get('identity') or {}).get('email') or '').strip().casefold()
    host = (urlsplit(job_url).hostname or '').casefold()
    key = hashlib.sha256((host + '\n' + email).encode()).hexdigest()
    profile_path = Path(profile_path or profile.get('_legacy_credential_profile_path') or 'profile.json')
    path = profile_path.with_name(profile_path.name + '.credentials.db')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create privately before SQLite opens it; never truncate an existing store.
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(fd)
    if os.name != 'nt':
        path.chmod(0o600)
    db = sqlite3.connect(path, timeout=30)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS passwords (account_key TEXT PRIMARY KEY, password TEXT NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT password FROM passwords WHERE account_key=?', (key,)).fetchone()
        if row:
            return row[0]
        groups = (string.ascii_uppercase, string.ascii_lowercase, string.digits, '!@#%_-')
        chars = [secrets.choice(group) for group in groups]
        chars.extend(secrets.choice(''.join(groups)) for _ in range(24))
        secrets.SystemRandom().shuffle(chars)
        password = ''.join(chars)
        db.execute('INSERT INTO passwords VALUES (?, ?)', (key, password))
        db.commit()
        return password
    finally:
        db.close()
