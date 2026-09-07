"""Small Hermes hook adapter over the agent-neutral API; never imports Hermes core.

Raw hook content/results are never persisted; only execution-mode flags are inspected. The
outbox contains only fixed operation envelopes and immutable action attribution.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading

from .managed_shared import ProtocolError, dumps
from .hermes_model_events import ModelObservers

IDENTIFIER = re.compile(r'^[A-Za-z0-9_.:/-]{1,250}$')


class HermesAdapter(ModelObservers):
    def __init__(self, client, *, worker_id, session_id, browser_profile,
                 skill_version, provider, model, spool_path, reasoning_effort=None):
        for value in (worker_id, session_id, browser_profile, skill_version, provider, model):
            if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
                raise ProtocolError('invalid_adapter_identity')
        if reasoning_effort is not None and (not isinstance(reasoning_effort, str) or reasoning_effort not in ('low', 'medium', 'high', 'xhigh')):
            raise ProtocolError('invalid_adapter_identity')
        self.client = client
        self.worker_id, self.session_id = worker_id, session_id
        self.browser_profile = browser_profile
        self.capabilities = dict(protocol=1, telemetry=True,
            browser_profile=browser_profile, skill_version=skill_version,
            provider=provider, model=model)
        if reasoning_effort is not None:
            self.capabilities['reasoning_effort'] = reasoning_effort
        self.spool_path = Path(spool_path)
        if not self.spool_path.is_absolute():
            raise ProtocolError('absolute_outbox_path_required')
        self.lock = threading.RLock()
        existed = self.spool_path.exists()
        if existed:
            try:
                db = sqlite3.connect(self.spool_path.as_uri()+'?mode=ro', uri=True)
                try:
                    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if names != {'adapter_meta', 'adapter_calls', 'adapter_outbox'}:
                        raise ProtocolError('outbox_target_collision')
                finally:
                    db.close()
            except sqlite3.DatabaseError as exc:
                raise ProtocolError('outbox_target_collision') from exc
        else:
            self.spool_path.parent.mkdir(parents=True, exist_ok=True)
            with self.spool_path.open('xb'):
                pass
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS adapter_meta (key TEXT PRIMARY KEY,value_json TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS adapter_calls (key TEXT PRIMARY KEY,context_json TEXT NOT NULL,completion_json TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS adapter_outbox (id TEXT PRIMARY KEY,operation TEXT NOT NULL,payload_json TEXT NOT NULL)')
            owner = dict(instance_id=client.instance_id, worker_id=worker_id, session_id=session_id)
            old = self._get(db, 'owner')
            if old and old != owner:
                raise ProtocolError('outbox_owner_mismatch')
            self._put(db, 'owner', owner)
        self.last_error = None

    @contextmanager
    def _db(self):
        with self.lock:
            db = sqlite3.connect(self.spool_path, timeout=5, isolation_level=None)
            db.row_factory = sqlite3.Row
            try:
                db.execute('BEGIN IMMEDIATE')
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    @staticmethod
    def _get(db, key):
        row = db.execute('SELECT value_json FROM adapter_meta WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _put(db, key, value):
        db.execute('INSERT INTO adapter_meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json', (key, dumps(value)))

    def _state(self):
        with self._db() as db:
            return self._get(db, 'state') or {}

    def accept(self, run_id):
        state = self._state()
        if state.get('attempt') and state.get('run_id') != run_id:
            raise ProtocolError('active_attempt_requires_reconciliation')
        if self.flush():
            raise ProtocolError('telemetry_delivery_pending')
        run = self.client.call('accept_run', run_id=run_id, worker_id=self.worker_id,
            session_id=self.session_id, capabilities=self.capabilities)
        with self._db() as db:
            state = self._get(db, 'state') or {}
            if state.get('run_id') != run_id:
                self._put(db, 'state', {'run_id': run_id, 'attempt': None})
        return run

    def claim(self):
        if self.flush():
            raise ProtocolError('telemetry_delivery_pending')
        state = self._state()
        if not state.get('run_id'):
            raise ProtocolError('run_not_accepted')
        result = self.client.call('claim', run_id=state['run_id'], worker_id=self.worker_id)
        if result and result['session_id'] != self.session_id:
            raise ProtocolError('wrong_session')
        context = None if result is None else dict(attempt_id=result['id'],
            worker_id=self.worker_id, fence=result['fence'])
        with self._db() as db:
            self._put(db, 'state', {'run_id': state['run_id'], 'attempt': context})
        return result

    @staticmethod
    def _block(code):
        return {'action': 'block', 'message': 'JobBot: '+code}

    def _call_key(self, tool_call_id, kwargs):
        # Runtime IDs remain intact; this derived key disambiguates request scopes.
        return dumps([self.session_id, tool_call_id, kwargs.get('api_request_id'), kwargs.get('turn_id')])

    def pre_tool_call(self, tool_name, args, task_id='', session_id='', tool_call_id='', **kwargs):
        try:
            if session_id != self.session_id:
                return self._block('wrong_session')
            if tool_name == 'jobbot':
                return None
            state = self._state()
            if not state.get('attempt'):
                return None
            if not tool_call_id or not isinstance(tool_call_id, str) or len(tool_call_id) > 250:
                return self._block('missing_or_invalid_tool_call_id')
            if not isinstance(tool_name, str) or not IDENTIFIER.fullmatch(tool_name):
                return self._block('invalid_tool_name')
            context = dict(state['attempt'])
            key = self._call_key(tool_call_id, kwargs)
            action_id = tool_call_id+':'+hashlib.sha256(key.encode()).hexdigest()
            # Persist correlation BEFORE authorizing execution. Lost acknowledgements
            # reuse the same action ID rather than creating an untracked side effect.
            captured = dict(context, action_id=action_id, tool_name=tool_name)
            with self._db() as db:
                old = db.execute('SELECT * FROM adapter_calls WHERE key=?', (key,)).fetchone()
                previous = json.loads(old['context_json']) if old else None
                if previous: previous.pop('denial', None)
                if old and (previous != captured or old['completion_json']):
                    return self._block('tool_call_id_reused')
                db.execute('INSERT OR IGNORE INTO adapter_calls(key,context_json) VALUES (?,?)',
                    (key, dumps(dict(captured,denial='preflight_not_authorized'))))
            # Preserve blocked-call attribution before fallible network operations.
            if tool_name == 'terminal' and isinstance(args,dict) and args.get('background',False) not in (False,None):
                return self._block('managed_background_execution_unsupported')
            if self.flush():return self._block('telemetry_delivery_pending')
            with self._db() as db:
                if self._get(db,'fault'):return self._block('telemetry_reconciliation_required')
            self.client.call('heartbeat', **context)
            with self._db() as db:
                db.execute('UPDATE adapter_calls SET context_json=? WHERE key=?',(dumps(captured),key))
            try:
                self.client.call('action_start', **captured)
            except ProtocolError as exc:
                if exc.code not in ('api_unavailable', 'internal_error'):
                    with self._db() as db:
                        db.execute('UPDATE adapter_calls SET context_json=? WHERE key=?',
                            (dumps(dict(captured, denial=exc.code)), key))
                raise
            with self._db() as db:
                db.execute('UPDATE adapter_calls SET context_json=? WHERE key=?', (dumps(captured), key))
            return None
        except Exception as exc:
            self.last_error = exc.code if isinstance(exc, ProtocolError) else 'adapter_unavailable'
            # Raising here is unsafe: installed Hermes isolates plugin exceptions.
            return self._block(self.last_error)

    def post_tool_call(self, tool_name, args, result, task_id='', session_id='',
                       tool_call_id='', duration_ms=None, status='success', **kwargs):
        if tool_name == 'jobbot' or session_id != self.session_id:
            return
        try:
            key = self._call_key(tool_call_id, kwargs)
            with self._db() as db:
                call = db.execute('SELECT * FROM adapter_calls WHERE key=?', (key,)).fetchone()
                if call is None:
                    # An unbound session's unrelated tools do not belong to a run.
                    if (self._get(db, 'state') or {}).get('attempt'):
                        self._put(db, 'fault', 'uncorrelated_tool_completion')
                    return
                captured = json.loads(call['context_json'])
                denial = captured.pop('denial', None)
                if captured.pop('tool_name') != tool_name:
                    self._put(db, 'fault', 'tool_identity_changed')
                    return
                if call['completion_json']:
                    return
                if type(duration_ms) not in (int, float) or not math.isfinite(duration_ms) or duration_ms < 0:
                    self._put(db, 'fault', 'invalid_tool_duration')
                    return
                observed = datetime.now(timezone.utc).isoformat()
                outcome = 'success' if status == 'success' else ('aborted' if status in ('aborted', 'blocked', 'cancelled') else 'failed')
                payload = dict(captured, status=outcome,
                    duration_seconds=duration_ms/1000, observed_at=observed)
                operation = 'action_end'
                if denial:
                    operation = 'event'
                    payload = dict(captured, event_id='action-end:'+captured['action_id'],
                        event_type='tool_finished', observed_at=observed,
                        duration_seconds=duration_ms/1000,
                        payload={'tool_name':tool_name,'status':'aborted','reason_code':denial})
                encoded = dumps(payload)
                if len(encoded) > 8192:
                    self._put(db, 'fault', 'telemetry_envelope_too_large')
                    return
                db.execute('UPDATE adapter_calls SET completion_json=? WHERE key=?', (encoded, key))
                db.execute('INSERT OR IGNORE INTO adapter_outbox VALUES (?,?,?)', (captured['action_id'], operation, encoded))
            self.flush()
        except Exception as exc:
            self.last_error = exc.code if isinstance(exc, ProtocolError) else 'adapter_unavailable'
            try:
                with self._db() as db:
                    self._put(db, 'fault', self.last_error)
            except Exception:
                pass  # No raw exception, args, result, headers or reasoning is logged.

    def flush(self):
        with self.lock:
            try:
                with self._db() as db:
                    pending = [dict(r) for r in db.execute('SELECT * FROM adapter_outbox ORDER BY rowid LIMIT 100')]
                for row in pending:
                    if row['operation'] not in ('action_end','event'):
                        self.last_error = 'invalid_outbox_operation'
                        break
                    try:
                        self.client.call(row['operation'], **json.loads(row['payload_json']))
                    except ProtocolError as exc:
                        self.last_error = exc.code
                        break
                    with self._db() as db:
                        db.execute('DELETE FROM adapter_outbox WHERE id=?', (row['id'],))
                with self._db() as db:
                    return db.execute('SELECT count(*) FROM adapter_outbox').fetchone()[0]
            except Exception:
                self.last_error = 'outbox_unavailable'
                return 1  # Fail closed, never claim that uninspected delivery drained.
