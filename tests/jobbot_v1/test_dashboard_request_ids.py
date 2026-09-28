"""Real dashboard actions work on LAN HTTP without the secure-context UUID API."""
import json

import pytest

from test_dispatch_queue_ui import dashboard_check


@pytest.mark.parametrize('native_uuid', [False, True])
@pytest.mark.parametrize('action', ['intake', 'apply_now', 'queue_selected', 'request_run', 'legacy_start'])
def test_dashboard_actions_send_distinct_ids_without_requiring_https(action, native_uuid):
    dashboard_check('const action=' + json.dumps(action) + '; const nativeUUID=' + json.dumps(native_uuid) + ';' + r'''
let nativeCalls=0;
if(nativeUUID){
  const original=w.crypto.randomUUID;
  assert(typeof original==='function','Native UUID control case is unavailable');
  Object.defineProperty(w.crypto,'randomUUID',{configurable:true,value(){nativeCalls++;return original.call(this);}});
}else Object.defineProperty(w.crypto,'randomUUID',{value:undefined,configurable:true});
assert(typeof w.crypto.getRandomValues==='function','Fixture must retain the HTTP-compatible random source');
v.jobs=[{id:'chosen',company:'Synthetic Company',status:'queued'}];
v.candidates=[{id:'candidate',email:'fixture@example.test',state:'active'}];
v.assets=[{id:'resume',identity_id:'candidate',kind:'resume',status:'available',storage_ref:'fixture.pdf'}];
v.settings={values:{submission_mode:'review'}};
if(action==='legacy_start'||action==='request_run')v.local_runtime.workspaces=[];
doc.getElementById('candidate').append(new w.Option('Fixture','candidate'));
doc.getElementById('candidate').value='candidate';
doc.getElementById('browser-profile').value='fixture-browser';
doc.getElementById('main-submission-mode').value='review';
w.draw(v);w.noRefresh();
const calls=[];
w.fetch=async(path,options)=>{
  calls.push({path,body:JSON.parse(options.body)});
  const response=path==='/v1/intake'?{id:'new',status:'queued'}:
    path==='/v1/queue_enqueue'?{items:[{job_id:'chosen'}],queue:{worker_online:true}}:{id:'fixture-run'};
  return {ok:true,status:200,json:async()=>response};
};
const operation=action==='intake'?'intake':action==='apply_now'||action==='queue_selected'?'queue_enqueue':'request_run';
for(let n=0;n<2;n++){
  if(action==='intake'){
    doc.getElementById('job-url').value='https://example.test/jobs/'+n;
    doc.getElementById('job-company').value='Synthetic Company';
    await doc.getElementById('intake-form').onsubmit({preventDefault(){}});
  }else if(action==='apply_now'){
    await doc.querySelector('button[data-apply-now]').onclick();
  }else{
    const checkbox=doc.querySelector('#queue-rows input[type="checkbox"]');
    checkbox.checked=true;checkbox.onchange();
    await doc.getElementById(action==='request_run'?'request-run':action==='queue_selected'?'queue-selected-jobs':'start-application-btn').onclick();
  }
  const sent=calls.filter(c=>c.path==='/v1/'+operation);
  assert(sent.length===n+1,action+' failed before sending request: '+doc.getElementById('notice').textContent);
  assert(!doc.getElementById('notice').classList.contains('error'),'Success was reported as an error');
}
const sent=calls.filter(c=>c.path==='/v1/'+operation);
const ids=sent.map(c=>c.body[action==='intake'?'source_id':'request_id']);
assert(ids.every(id=>/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)),'Requests lack valid UUID v4 identifiers');
assert(new Set(ids).size===2,'Separate user requests reused the same identifier');
assert(nativeCalls===(nativeUUID?2:0),'Unexpected UUID implementation used');
if(action==='intake'){
  assert(sent.every(c=>c.body.source_type==='manual'&&c.body.producer==='dashboard'),'Intake attribution changed');
  assert(doc.getElementById('job-url').value==='','Saved intake did not reset the form');
  assert(doc.getElementById('notice').textContent.includes('Job saved'),'No saved receipt');
}else{
  assert(sent.every(c=>c.body.job_ids.join()==='chosen'&&c.body.identity_id==='candidate'),'Requested job or candidate changed');
  if(operation==='queue_enqueue')assert(sent.every(c=>c.body.retry===true&&c.body.start_now===true&&c.body.resume_asset_id==='resume'),'Queue semantics changed');
}
''')


def test_http_intake_authentication_retry_preserves_request_identifier():
    dashboard_check(r'''
Object.defineProperty(w.crypto,'randomUUID',{value:undefined,configurable:true});
w.noRefresh();const calls=[];let reopened=0;
w.fetch=async(path,options)=>{
  if(path==='/'){reopened++;return {ok:true,status:200};}
  calls.push({path,body:JSON.parse(options.body)});
  return calls.length===1?{ok:false,status:401}:{ok:true,status:200,json:async()=>({id:'saved',status:'queued'})};
};
doc.getElementById('job-url').value='https://example.test/jobs/synthetic';
await doc.getElementById('intake-form').onsubmit({preventDefault(){}});
assert(calls.length===2&&reopened===1,'Existing authentication retry did not complete');
assert(calls.every(c=>c.path==='/v1/intake'),'Unexpected operation');
assert(calls[0].body.source_id===calls[1].body.source_id,'Authentication retry changed the original request identity');
assert(doc.getElementById('notice').textContent.includes('Job saved'),'No saved receipt after authentication retry');
''')
