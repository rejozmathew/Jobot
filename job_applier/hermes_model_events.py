"""Metadata-only observers for the installed Hermes API-request hook contract."""
from datetime import datetime, timezone
import hashlib
import json
import math
from .managed_shared import dumps


class ModelObservers:
    def _model_fault(self, code):
        with self._db() as db:
            self._put(db, 'fault', code)

    def pre_api_request(self, *, session_id='', api_request_id='', model=None, provider=None, **kwargs):
        if session_id != self.session_id:
            return
        try:
            state = self._state()
            if not state.get('attempt'):
                return
            if not isinstance(api_request_id, str) or not api_request_id or len(api_request_id) > 250:
                self._model_fault('missing_api_request_id')
                return
            if model != self.capabilities['model'] or provider != self.capabilities['provider']:
                self._model_fault('runtime_model_mismatch')
            key = 'api:'+self._call_key(api_request_id, kwargs)
            captured = dict(state['attempt'], model=self.capabilities['model'],
                provider=self.capabilities['provider'])
            with self._db() as db:
                old = db.execute('SELECT * FROM adapter_calls WHERE key=?',(key,)).fetchone()
                if old and json.loads(old['context_json']) != captured:
                    self._put(db,'fault','api_request_id_reused')
                    return
                db.execute('INSERT OR IGNORE INTO adapter_calls(key,context_json) VALUES (?,?)',(key,dumps(captured)))
            self.client.call('heartbeat', **state['attempt'])
        except Exception:
            self._model_fault('api_observer_unavailable')

    def post_api_request(self, *, session_id='', api_request_id='', model=None, provider=None,
                         response_model=None, api_duration=None, usage=None, **kwargs):
        self._finish_api(session_id=session_id,api_request_id=api_request_id,
            model=model,provider=provider,response_model=response_model,
            duration=api_duration,usage=usage,failed=False,kwargs=kwargs)

    def api_request_error(self, *, session_id='', api_request_id='', api_duration=None, **kwargs):
        self._finish_api(session_id=session_id,api_request_id=api_request_id,
            model=None,provider=None,response_model=None,duration=api_duration,
            usage=None,failed=True,kwargs=kwargs)

    def _finish_api(self, *, session_id, api_request_id, model, provider, response_model, duration, usage, failed, kwargs):
        if session_id != self.session_id:
            return
        try:
            key = 'api:'+self._call_key(api_request_id, kwargs)
            with self._db() as db:
                call=db.execute('SELECT * FROM adapter_calls WHERE key=?',(key,)).fetchone()
                if not call:
                    if (self._get(db,'state') or {}).get('attempt'):
                        self._put(db,'fault','uncorrelated_api_completion')
                    return
                if call['completion_json']:
                    return
                captured=json.loads(call['context_json'])
                requested_model=captured.pop('model'); requested_provider=captured.pop('provider')
                observed_model=requested_model if failed and model is None else model
                observed_provider=requested_provider if failed and provider is None else provider
                mismatch=(observed_model!=requested_model or observed_provider!=requested_provider or
                    (response_model is not None and response_model!=requested_model))
                if mismatch:self._put(db,'fault','runtime_model_mismatch')
                payload={'status':'failed' if failed or mismatch else 'success'}
                for name,value in (('provider',observed_provider),('model',observed_model),('response_model',response_model)):
                    if isinstance(value,str) and 0<len(value)<=250:
                        from .managed_redaction import safe_text
                        payload[name]=safe_text(value)
                if isinstance(usage,dict):
                    for canonical, alternatives in (('input_tokens',('input_tokens','prompt_tokens')),('output_tokens',('output_tokens','completion_tokens'))):
                        value=next((usage[k] for k in alternatives if k in usage),None)
                        if type(value) is int and value>=0:payload[canonical]=value
                if mismatch:payload['reason_code']='runtime_model_mismatch'
                if failed:payload['reason_code']='api_request_failed'
                measured=duration if type(duration) in (int,float) and math.isfinite(duration) and duration>=0 else None
                event_id='model:'+api_request_id+':'+hashlib.sha256(key.encode()).hexdigest()
                envelope=dict(captured,event_id=event_id,event_type='model_finished',
                    action_id=None,observed_at=datetime.now(timezone.utc).isoformat(),
                    duration_seconds=measured,payload=payload)
                encoded=dumps(envelope)
                db.execute('UPDATE adapter_calls SET completion_json=? WHERE key=?',(encoded,key))
                db.execute('INSERT OR IGNORE INTO adapter_outbox VALUES (?,?,?)',(event_id,'event',encoded))
            self.flush()
        except Exception:
            self._model_fault('api_observer_unavailable')
