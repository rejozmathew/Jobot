"""Check tracked publication files without reading ignored private artifacts.

This is a repository hygiene check, not an application-execution restriction or
a replacement for a full secret scanner and historical audit.
"""
from pathlib import Path, PurePosixPath
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def private_path(name):
    path = PurePosixPath(name)
    base = path.name.lower()
    return (
        path.parts[0] in {'artifacts', 'scratch', 'node_modules'}
        or base in {'profile.json', 'profile_no_login.json', 'candidate.json', 'cookies.json',
                    'browser_cookies.json', 'job_queue.json', 'queue_dryrun.json', 'timing_log.jsonl', '.env', 'resume.pdf'}
        or (base.startswith('profile.json.') and base != 'profile.json.template')
        or base.endswith(('.db', '.db-wal', '.db-shm', '.pem', '.key'))
        or (len(path.parts) == 1 and (base.startswith('t_wd_') or base.startswith('_wd_')))
    )


def main():
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    findings = []
    for name in filter(None, names):
        path = ROOT/name
        if not path.is_file():
            continue
        if private_path(name):
            findings.append(f'{name}: private/runtime file must not be tracked')
        if name.startswith('tests/'):
            continue  # Deliberate synthetic credentials; audited separately.
        text = path.read_text(encoding='utf-8', errors='replace')
        if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}|\bsk-(?:proj-|ant-api\d+-)?[A-Za-z0-9_-]{24,}', text):
            findings.append(f'{name}: potential credential material (value withheld)')
    template = json.loads((ROOT/'profile.json.template').read_text(encoding='utf-8'))
    example = json.loads((ROOT/'profile.example.json').read_text(encoding='utf-8'))
    if template != example:
        findings.append('profile.example.json: compatibility copy differs from profile.json.template')
    print('\n'.join(findings) if findings else 'Public tree hygiene passed; ignored private files were not read.')
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
