"""Portable runtime preflight and read-only duplicate history. Never migrates a DB."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit
from .managed_identity import canonical_url
from .managed_cli import credential_available


def read_config(path):
    p=Path(path)
    if not p.is_absolute() or not p.is_file():raise ValueError('absolute_existing_config_required')
    data=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(data,dict):raise ValueError('invalid_config')
    return data


def readonly(path):
    p=Path(path)
    if not p.is_absolute() or not p.is_file():raise ValueError('history_unavailable')
    db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def history_key(url):
    canonical=canonical_url(url); p=urlsplit(canonical)
    if (p.hostname or '').endswith('.myworkdayjobs.com'):
        parts=p.path.strip('/').split('/')
        if parts and re.fullmatch(r'[a-z]{2}(?:-[A-Za-z0-9]{2,4})?',parts[0]):parts=parts[1:]
        if 'job' in parts:
            i=parts.index('job')
            if len(parts)>i+2 and '_' in parts[i+2]:
                return p.netloc.lower(),parts[0],parts[i+2].rsplit('_',1)[-1]
    return (canonical,)


def history_matches(paths,url):
    key=history_key(url); matches=[]
    for path in paths:
        try:
            with closing(readonly(path)) as db:
                rows=db.execute("SELECT id,url,status FROM jobs WHERE status IN ('applied','already_applied','submission_unknown','in_progress','running')")
                for row in rows:
                    if history_key(row['url'])==key:
                        matches.append({'database':str(Path(path).resolve()),'job_id':row['id'],'status':row['status']})
        except sqlite3.Error as exc:raise ValueError('history_unavailable') from exc
    return matches


def inspect_runtime(config_path,url=None):
    cfg=read_config(config_path); p=Path(cfg.get('db_path',''))
    if not p.is_absolute():raise ValueError('absolute_database_required')
    with closing(readonly(p)) as db:
        row=db.execute('SELECT id FROM instance').fetchone()
        if not row or row['id']!=cfg.get('instance_id'):raise ValueError('instance_mismatch')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        active=[]
        if 'runs' in tables:
            active=[dict(r) for r in db.execute("SELECT id,state,control FROM runs WHERE state!='completed'")]
    histories=cfg.get('legacy_history_paths',[])
    if not isinstance(histories,list):raise ValueError('invalid_history_paths')
    if any(Path(x).resolve()==p.resolve() for x in histories):raise ValueError('primary_is_not_legacy')
    for source in histories:
        with closing(readonly(source)):pass
    endpoint=urlsplit(cfg.get('cdp_url',''))
    if endpoint.scheme!='http' or endpoint.hostname not in ('127.0.0.1','localhost','::1') or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path:
        raise ValueError('explicit_loopback_cdp_required')
    result={'repository':str(Path(__file__).resolve().parents[1]),'instance_id':row['id'],
            'db_path':str(p.resolve()),'cdp_url':cfg['cdp_url'],'browser_profile':cfg.get('browser_profile'),
            'legacy_history_paths':histories,'historical_open_runs':active,
            'credential_reference_configured':bool(cfg.get('credential_profile_path')),
            'worker_token_available':credential_available(cfg.get('worker_token_env',''),cfg),
            'migration_performed':False}
    if url:result['history_matches']=history_matches([str(p),*histories],url)
    return result
