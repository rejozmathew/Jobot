"""Local operator UI session boundary. No token is rendered or stored in browser storage."""
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import time
from fastapi import Request
from fastapi.responses import FileResponse,JSONResponse

STATIC=Path(__file__).parent/'static'
COOKIE='jobbot_operator'


class OperatorSessions:
    def __init__(self):self.sessions={}
    @staticmethod
    def key(value):return hashlib.sha256(value.encode()).hexdigest()
    def issue(self):
        now=time.monotonic();self.sessions={k:v for k,v in self.sessions.items() if v>now}
        if len(self.sessions)>=128:return None
        value=secrets.token_urlsafe(32);self.sessions[self.key(value)]=now+1800;return value
    def valid(self,value):return bool(value) and self.sessions.get(self.key(value),0)>time.monotonic()
    def revoke(self,value):
        if value:self.sessions.pop(self.key(value),None)


def install_ui(app,service,operator_token,sessions):
    @app.get('/')
    def index():return FileResponse(STATIC/'jobbot.html',media_type='text/html',headers={'Cache-Control':'no-store'})

    @app.get('/static/{name}')
    def static(name):
        types={'jobbot.js':'text/javascript','jobbot.css':'text/css'}
        if name not in types:return JSONResponse({'error':'not_found'},status_code=404)
        return FileResponse(STATIC/name,media_type=types[name],headers={'Cache-Control':'no-cache'})


    @app.post('/login')
    async def login(request:Request):
        if request.query_params:return JSONResponse({'error':'invalid_login_request'},status_code=422)
        try:
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>4096:return JSONResponse({'error':'invalid_login_request'},status_code=422)
            data=json.loads(body)
            if not isinstance(data,dict) or set(data)!={'token'} or not isinstance(data['token'],str):raise ValueError()
            if not hmac.compare_digest(data['token'].encode(),operator_token.encode()):raise ValueError()
        except (ValueError,TypeError):return JSONResponse({'error':'unauthorized'},status_code=401)
        sessions.revoke(request.cookies.get(COOKIE))
        value=sessions.issue()
        if value is None:return JSONResponse({'error':'session_limit'},status_code=429)
        response=JSONResponse({'instance_id':service.instance_id},headers={'Cache-Control':'no-store'})
        response.set_cookie(COOKIE,value,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=1800,path='/')
        return response

    @app.get('/session')
    def session(request:Request):
        if request.state.role!='operator':return JSONResponse({'error':'role_forbidden'},status_code=403)
        return JSONResponse({'instance_id':service.instance_id},headers={'Cache-Control':'no-store'})

    @app.post('/logout')
    def logout(request:Request):
        if request.state.role!='operator':return JSONResponse({'error':'role_forbidden'},status_code=403)
        sessions.revoke(request.cookies.get(COOKIE));response=JSONResponse({'ok':True})
        response.delete_cookie(COOKIE,path='/');return response
