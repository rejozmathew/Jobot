"""Authenticated, loopback-only agent-neutral JSON protocol. No runner startup."""
import hmac
import json
import sqlite3
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .managed_shared import ProtocolError

READS=frozenset({'job','attempt_status','events','account_strategy'})
OPERATOR=frozenset({'identity','intake','eligibility','request_run','control','reconcile','retry','account_update','mail_request','match_mail'})|READS
WORKER=frozenset({'accept_run','claim','heartbeat','event','action_start','action_end','writer_state','submission_intent','finish','ack_control','ack_run_control','checkpoint','resume_run'})|READS


def create_app(service, *, operator_token, worker_tokens):
    if not isinstance(operator_token,str) or len(operator_token)<24 or not worker_tokens:
        raise ProtocolError('strong_local_credentials_required')
    if operator_token in worker_tokens or any(not isinstance(k,str) or len(k)<24 or not v for k,v in worker_tokens.items()):
        raise ProtocolError('distinct_worker_credentials_required')
    app=FastAPI(title='JobBot v1',docs_url=None,redoc_url=None,openapi_url=None)
    operations={name:getattr(service,name) for name in OPERATOR|WORKER}
    app.state.service=service

    @app.middleware('http')
    async def authorize(request, call_next):
        if request.url.hostname not in ('localhost','127.0.0.1','::1'):
            return JSONResponse({'error':'loopback_host_required'},status_code=403)
        origin=request.headers.get('origin')
        if origin and origin!=str(request.base_url).rstrip('/'):
            return JSONResponse({'error':'untrusted_origin'},status_code=403)
        auth=request.headers.get('authorization','')
        provided=auth[7:] if auth.startswith('Bearer ') else ''
        request.state.role=None;request.state.worker_id=None
        if hmac.compare_digest(provided,operator_token):request.state.role='operator'
        for token,worker in worker_tokens.items():
            if hmac.compare_digest(provided,token):request.state.role='worker';request.state.worker_id=worker
        if request.state.role is None:return JSONResponse({'error':'unauthorized'},status_code=401)
        if request.headers.get('x-jobbot-instance')!=service.instance_id:
            return JSONResponse({'error':'instance_mismatch'},status_code=409)
        return await call_next(request)

    @app.get('/v1/health')
    def health():return service.health()

    @app.post('/v1/{operation}')
    async def operate(operation: str,request: Request):
        if operation not in operations:return JSONResponse({'error':'unknown_operation'},status_code=404)
        permitted=OPERATOR if request.state.role=='operator' else WORKER
        if operation not in permitted:return JSONResponse({'error':'role_forbidden'},status_code=403)
        try:
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>65536:return JSONResponse({'error':'payload_too_large'},status_code=413)
            payload=json.loads(body)
            if not isinstance(payload,dict):raise ValueError()
            # JSON booleans/IDs are strict; string 'false' must never acknowledge a writer.
            bool_fields={'finish':('quiescent',),'ack_control':('quiescent',),
                'ack_run_control':('quiescent',),'reconcile':('browser_quiescent',),
                'submission_intent':('fixture',)}.get(operation,())
            for key in bool_fields:
                if key in payload and type(payload[key]) is not bool:raise ValueError()
            for key in ('attempt_id','fence'):
                if key in payload and (type(payload[key]) is not int or payload[key]<1):raise ValueError()
            if request.state.role=='worker':
                worker_id=request.state.worker_id
                if 'worker_id' in payload and payload['worker_id']!=worker_id:
                    return JSONResponse({'error':'worker_identity_mismatch'},status_code=403)
                if operation not in READS and payload.get('worker_id')!=worker_id:
                    return JSONResponse({'error':'worker_identity_required'},status_code=403)
                if 'attempt_id' in payload and service.attempt(payload['attempt_id'])['worker_id']!=worker_id:
                    return JSONResponse({'error':'attempt_forbidden'},status_code=403)
                if operation in ('job','account_strategy'):
                    with service.tx() as db:
                        if operation=='job':
                            allowed=db.execute('SELECT 1 FROM runs r JOIN run_jobs j ON r.id=j.run_id WHERE r.worker_id=? AND j.job_id=?',(worker_id,payload.get('job_id'))).fetchone()
                        else:
                            allowed=db.execute('SELECT 1 FROM runs WHERE worker_id=? AND identity_id=?',(worker_id,payload.get('identity_id'))).fetchone()
                        if not allowed:return JSONResponse({'error':'context_forbidden'},status_code=403)
            # Only static bound methods above are reachable; no reflection on user strings.
            return JSONResponse(operations[operation](**payload))
        except ProtocolError as exc:
            code=409 if exc.code in ('owned_elsewhere','already_applied','stale_owner','reconciliation_required','idempotency_conflict','conflicting_finish','awaiting_worker') else 422
            return JSONResponse({'error':exc.code},status_code=code)
        except (TypeError,ValueError,KeyError):return JSONResponse({'error':'invalid_payload'},status_code=422)
        except sqlite3.Error:return JSONResponse({'error':'database_operation_failed'},status_code=409)
    return app
