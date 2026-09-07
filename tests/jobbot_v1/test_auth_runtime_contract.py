"""Exercise integration contracts hidden by isolated worker mocks."""
import ast
import asyncio
import inspect
import json
import shutil
import subprocess
from contextlib import nullcontext
from unittest.mock import AsyncMock

import pytest
from job_applier import managed_hermes_worker as worker
from job_applier.managed_events import EVENT_TYPES
from test_product_observation import owned_service, browser_probe, WORKER_ID


def test_worker_events_are_accepted_by_real_service_contract():
    tree = ast.parse(inspect.getsource(worker))
    names = {n.args[0].value for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == 'event' and n.args
             and isinstance(n.args[0], ast.Constant)}
    assert names <= EVENT_TYPES


@pytest.mark.parametrize('status', ['unknown', 'missing'])
def test_repeated_observation_cannot_forget_unsettled_writer(tmp_path, monkeypatch, status):
    s, job, run, a = owned_service(tmp_path)
    browser_probe(monkeypatch, job['url'], status=status, panel=status != 'missing')
    s.writer_state(a['id'], worker_id=WORKER_ID, fence=1, state='active')
    for _ in range(3):
        result = s.browser_observe(a['id'], worker_id=WORKER_ID, fence=1)
        assert result['quiescent'] is False
        assert result['writer_state'] != 'idle'


@pytest.mark.parametrize('check', ['committed', 'screenshot_readonly'])
def test_real_auth_javascript_commits_react_fields_and_masks_without_writes(check):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    code = r'''
const vm=require('vm'), fs=require('fs'), d=JSON.parse(fs.readFileSync(0,'utf8'));
let writes=0;
class Input {
 constructor(type){this.type=type;this._value='';this.tracker='';this.committed='';this.style={};
 Object.defineProperty(this,'value',{get:()=>this._value,set:v=>{writes++;this._value=v;this.tracker=v;}});}
 get value(){return this._value;} set value(v){this._value=v;}
 getBoundingClientRect(){return {width:100,height:20};}
 focus(){} blur(){}
 dispatchEvent(e){if(e.type==='input'&&this._value!==this.tracker){this.committed=this._value;this.tracker=this._value;}}
}
const email=new Input('email'), p1=new Input('password'),p2=new Input('password'), all=[email,p1,p2];
const c={HTMLInputElement:Input,Event:class {constructor(type){this.type=type;}},
 document:{querySelectorAll:s=>s.includes('password')?[p1,p2]:[email],body:{innerText:'Create Account'}},
 getComputedStyle:()=>({visibility:'visible'}),requestAnimationFrame:f=>f(),setTimeout};c.window=c;
vm.createContext(c);
(async()=>{const result=await vm.runInContext(d.auth,c)({email:'synthetic@example.test',password:'synthetic-test-pass'});
const committed=email.committed==='synthetic@example.test'&&[p1,p2].every(p=>p.committed==='synthetic-test-pass');
writes=0;vm.runInContext(d.mask,c);vm.runInContext(d.unmask,c);
console.log(JSON.stringify({committed,screenshot_readonly:writes===0,verified:result.verified}));})();
'''
    result = subprocess.run([node, '-e', code], input=json.dumps({
        'auth': worker.AUTH_FIND_AND_FILL, 'mask': worker.MASK_CREDENTIALS,
        'unmask': worker.UNMASK_CREDENTIALS}), capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)[check] is True


def offline_worker(monkeypatch, items):
    app = worker.ApplicationTool(None, 'synthetic', 'synthetic', {'worker_id': 'w'})
    url = 'https://job-boards.greenhouse.io/example/jobs/123'
    app.context = {'attempt_id': 1}
    app.package = {'job': {'url': url}}
    app._last_inventory = {'url': url, 'items': items}
    clicks = []
    async def evaluate(script, arg=None):
        if script == 'location.href':
            return url
        if script == worker.REF and arg.get('operation') == 'click':
            clicks.append(arg['ref'])
            return {'clicked': True}
        return {'is_anchor': False}
    page = type('Page', (), {'evaluate': staticmethod(evaluate),
        '_session': type('Session', (), {'call': AsyncMock(return_value={'data': 'synthetic'})})()})()
    browser = type('Browser', (), {'get_current_page': AsyncMock(return_value=page), 'close': AsyncMock()})()
    monkeypatch.setattr(app, 'connect', AsyncMock(return_value=browser))
    monkeypatch.setattr(app, 'call', lambda *a, **k: {'control': 'running', 'quiescent': True, 'writer_state': 'idle'})
    monkeypatch.setattr(app, 'action', lambda *a, **k: nullcontext())
    monkeypatch.setattr(app, 'event', lambda *a, **k: None)
    monkeypatch.setattr(app, 'inventory', AsyncMock(return_value={'url': url, 'items': [{'ref': 'fresh-ref', 'source': 'native'}]}))
    return app, clicks


def test_screenshot_delivers_its_fresh_control_refs(monkeypatch):
    app, _ = offline_worker(monkeypatch, [])
    result = asyncio.run(app.operate({'operation': 'screenshot'}))
    context = json.loads(result['content'][0]['text'])
    assert context['form']['items'][0]['ref'] == 'fresh-ref'


def test_cdp_invokes_async_credential_callable_with_arguments():
    from job_applier.cdp_client import CDPPage
    async def call(method, params, **kwargs):
        code = 'Promise.resolve(eval(' + json.dumps(params['expression']) + ')).then(x=>console.log(JSON.stringify({value:typeof x===\"function\"?\"NOT_CALLED\":x})))'
        result = subprocess.run([shutil.which('node'), '-e', code], capture_output=True, text=True, check=True)
        return {'result': json.loads(result.stdout)}
    page = CDPPage.__new__(CDPPage)
    page._session = type('Session', (), {'call': staticmethod(call)})()
    result = asyncio.run(page.evaluate('async (args) => args.value', {'value': 'forwarded'}))
    assert result == 'forwarded'


def test_extension_ref_is_not_invalidated_before_click(monkeypatch):
    from job_applier.simplify_boundary import SimplifyBoundary
    app, clicks = offline_worker(monkeypatch, [{'ref': 'visible-ref', 'source': 'simplify', 'label': 'Fill my details', 'tag': 'BUTTON'}])
    monkeypatch.setattr(SimplifyBoundary, 'observe', AsyncMock(return_value={'status': 'unknown', 'controls': {}}))
    monkeypatch.setattr(SimplifyBoundary, 'perform', AsyncMock(return_value={'status': 'unknown', 'writer_state': 'idle', 'changed': False}))
    asyncio.run(app.operate({'operation': 'autofill', 'ref': 'visible-ref'}))
    assert clicks == ['visible-ref']


def test_generic_click_cannot_delegate_password_creation_to_simplify(monkeypatch):
    app, clicks = offline_worker(monkeypatch, [
        {'ref': 'create-ref', 'source': 'simplify', 'label': 'Create Account & Autofill', 'tag': 'BUTTON'},
        {'ref': 'password-ref', 'source': 'native', 'type': 'password'}])
    result = asyncio.run(app.operate({'operation': 'click', 'ref': 'create-ref'}))
    assert not clicks
    assert result['error'] == 'native_auth_required'
