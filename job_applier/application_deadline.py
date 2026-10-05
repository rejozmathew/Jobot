"""Operator-selected application wall-clock budget, independent of model turns."""
from datetime import datetime, timedelta, timezone
import json
import logging
import sqlite3
import time

REASON = 'application_time_limit: Application time limit reached'


def freeze(config, settings, started_at):
    """A dispatch/replacement keeps its original budget, including an explicit Off."""
    result = dict(config)
    if 'application_deadline' not in result:
        minutes = settings.get('application_time_limit_minutes', 30)
        seconds = minutes * 60 if minutes else None
        result['application_deadline'] = {
            'started_at': started_at, 'limit_seconds': seconds,
            'expires_at': (datetime.fromisoformat(started_at) + timedelta(seconds=seconds)).isoformat() if seconds else None}
    result['maximum_runtime_seconds'] = result['application_deadline']['limit_seconds']
    return result


class Deadline:
    def __init__(self, budget, *, now=None, monotonic=time.monotonic):
        self.budget = budget or {}
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.end = datetime.fromisoformat(self.budget['expires_at']) if self.budget.get('expires_at') else None
        self.monotonic_end = monotonic() + max(0, (self.end-self.now()).total_seconds()) if self.end else None

    def expired(self):
        return bool(self.end and (self.now() >= self.end or self.monotonic() >= self.monotonic_end))

    def remaining(self):
        if not self.end:return None
        return max(0, min((self.end-self.now()).total_seconds(), self.monotonic_end-self.monotonic()))


def request_stop(service, sessions):
    """Record why, then use the existing control/cleanup lifecycle. Keep evidence."""
    with service.tx() as db:
        for session in sessions:
            current = service._get(db, 'application_sessions', session['id'])
            if current['ended_at']:continue
            metadata = json.loads(current['metadata_json'])
            metadata.setdefault('deadline_expired_at', service.now())
            db.execute('UPDATE application_sessions SET reason=?,metadata_json=? WHERE id=?',
                       (REASON, json.dumps(metadata), current['id']))
            if current['run_id']:
                run = service._get(db, 'runs', current['run_id'])
                if run['state'] != 'completed':service._control(db, run, command='stop')


def stop_process(identity):
    """Terminate only the verified executor process tree, never a model server."""
    from .workspace_process import process_matches
    import os
    import signal
    import subprocess
    if not identity or not process_matches(identity):return True
    try:
        pid=identity['pid']
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(pid),'/T','/F'],stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            # dispatch_one starts a new session. Never signal an inherited group
            # containing the dispatcher or a shared service.
            if os.getpgid(pid)!=pid:return False
            if process_matches(identity):os.killpg(pid,signal.SIGKILL)
        return not process_matches(identity)
    except ProcessLookupError:return True
    except (OSError,subprocess.TimeoutExpired):return False


def dispatch_expired(service, item, *, clock=None):
    """Re-enterable after supervisor crashes; no fresh budget on reconnection."""
    from pathlib import Path
    from .queue_runtime import find_sessions
    root = getattr(service, 'desktop_dispatch_spool', None)
    if not root:return False
    folder = Path(root)/'dispatch'/item['id']
    path = folder/'runtime.json'
    if not path.exists():return False
    config = json.loads(path.read_text())
    if not (clock or Deadline(config.get('application_deadline'))).expired():return False
    try:
        sessions = find_sessions(service, item)
        request_stop(service, sessions)
    except sqlite3.OperationalError as exc:
        from .managed_migrations import database_busy
        if not database_busy(exc):raise
        # The saved deadline still cancels the executor. A later supervision
        # pass records the stop and completes ordinary owned-browser cleanup.
        logging.getLogger(__name__).warning('sqlite_contention operation=dispatch_deadline; cancelling owned executor')
    # Record independently of a functioning model or browser. The queue's normal
    # settlement preserves successful submission and uncertainty from attempts.
    from .queue_runtime import private_write
    marker = folder/'deadline.json'
    if not marker.exists():private_write(marker, json.dumps({'reason': REASON, 'expired_at': service.now()}))
    if isinstance(config.get('hermes_desktop'), dict):
        from .hermes_desktop import cancel_dispatch
        cancelled = cancel_dispatch(config, folder/'desktop-session.json')
        if not cancelled:return True
    stop_process(json.loads(item.get('executor_identity_json') or '{}'))
    return True
