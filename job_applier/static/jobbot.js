'use strict';
const $=id=>document.getElementById(id);
const state={instance:null,view:null,selected:new Set(),run:null,attempt:null,busy:false,queueKey:null,settingsVersion:null,profileCandidate:null,profileDirty:false,answerKey:null,answerDrafts:new Map()};
function el(tag,text,cls,children){const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(cls)n.className=cls;if(Array.isArray(children)){for(const c of children)if(c)n.append(c);}return n;}
function badge(value){const n=el('span',value??'Unknown','badge');n.dataset.state=value??'unknown';return n;}
function notice(message,error=false){$('notice').textContent=message;$('notice').classList.toggle('error',error);}
function stamp(value){if(!value)return '—';const d=new Date(value);if(Number.isNaN(d.getTime()))return 'Unknown';return new Intl.DateTimeFormat(undefined,{dateStyle:'short',timeStyle:'medium',timeZone:state.view?.settings?.values?.timezone||'UTC'}).format(d);}
function duration(n){return typeof n==='number'?`${n.toFixed(1)} s`:'Unknown';}
async function request(path,body,method='POST'){
 const headers={};if(body!==undefined)headers['Content-Type']='application/json';if(state.instance)headers['X-JobBot-Instance']=state.instance;
 const options={method,headers,credentials:'same-origin',body:body===undefined?undefined:JSON.stringify(body)};
 let r=await fetch(path,options);
 if(r.status===401&&path!='/login'){
  const opened=await fetch('/',{credentials:'same-origin',cache:'no-store'});
  if(opened.ok)r=await fetch(path,options);
 }
 const data=r.status===204?{}:await r.json();
 if(!r.ok){if(r.status===401&&path!='/login')showLogin();throw new Error(data.error||`HTTP ${r.status}`);}return data;
}
const api=(operation,payload={})=>request('/v1/'+operation,payload);
const LEGACY_ALLOWED=new Set(['identity','summary','years_experience','target_roles','industries','skills','leadership_scope','work_authorization','work_preferences','dealbreakers','eeo_information','standard_answers','experience','education','certifications','projects','languages','links','resume']);
const LEGACY_EXCLUDED=new Set(['accounts','cover_letter','login','greenhouse','automation_preferences','application_answer_policy']);
const LEGACY_IDENTITY=new Set(['full_name','first_name','middle_name','last_name','preferred_name','email','phone','country code','address','location','linkedin','website','github']);
function sanitizeLegacyClient(data){
 const clean={},skipped=[];
 for(const [k,v] of Object.entries(data||{})){
  if(LEGACY_EXCLUDED.has(k)||!LEGACY_ALLOWED.has(k)){skipped.push(k);continue;}
  if(k==='identity'&&typeof v==='object'&&v!==null){
   clean.identity={};for(const [ik,iv] of Object.entries(v)){if(LEGACY_IDENTITY.has(ik))clean.identity[ik]=iv;else skipped.push('identity.'+ik);}
  }else if(k==='resume'&&typeof v==='object'&&v!==null){
   clean.resume={};if(v.path)clean.resume.path=v.path;if(v.text)skipped.push('resume.text');
   for(const rk of Object.keys(v)){if(rk!=='path'&&rk!=='text')skipped.push('resume.'+rk);}
  }else{clean[k]=v;}
 }
 return {clean,skipped:skipped.sort()};
}
function showLogin(){state.answerDrafts.clear();state.answerKey=null;$('answer-groups')?.replaceChildren();if($('answer-count'))$('answer-count').textContent='';state.instance=null;state.view=null;state.run=null;state.attempt=null;state.queueKey=null;state.settingsVersion=null;state.profileCandidate=null;state.selected.clear();for(const id of ['queue-rows','account-rows','history','attempts','events','health','instance','run-owner','focused-context','target-list','extension-list','lesson-list','helper-list','asset-list','assessment-list','profile-import-skipped'])$(id)?.replaceChildren();for(const f of document.querySelectorAll('form'))f.reset();$('console').hidden=true;$('login-panel').hidden=false;$('refresh').hidden=true;$('mode').textContent='Disconnected';if($('profile-hash'))$('profile-hash').textContent='';if($('profile-id'))$('profile-id').textContent='';if($('profile-person-key'))$('profile-person-key').textContent='';if($('profile-resume'))$('profile-resume').textContent='None';if($('main-resume-filename'))$('main-resume-filename').textContent='None registered';}
function showConsole(){state.profileDirty=false;$('console').hidden=false;$('login-panel').hidden=true;$('refresh').hidden=false;}
function choice(id,items,value){const select=$(id),before=value??select.value;select.replaceChildren();for(const [v,label]of items){const option=el('option',label);option.value=v;select.append(option);}if(items.some(x=>x[0]===before))select.value=before;}
function selection(){$('selection').textContent=`${state.selected.size} job(s) selected`;}
function link(url,label){try{const u=new URL(url);if(!['http:','https:'].includes(u.protocol))return el('span',label);const a=el('a',label);a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';return a;}catch{return el('span',label);}}
function renderQueue(v){
 renderSessions(v);
 renderAnswers(v);
 const key=JSON.stringify([v.jobs,v.answer_queue]);if(key===state.queueKey)return;state.queueKey=key;
 $('queue-count').textContent=`${v.jobs.length} records`;$('queue-rows').replaceChildren();
 for(const job of v.jobs){
  const tr=el('tr');
  const check=el('input');check.type='checkbox';check.checked=state.selected.has(job.id);
  check.setAttribute('aria-label','Select '+(job.title||job.id));
  check.onchange=()=>{if(check.checked)state.selected.add(job.id);else state.selected.delete(job.id);selection();};
  const cell=el('td');cell.append(check);tr.append(cell);
  const title=el('td');title.append(link(job.url,job.title||'Untitled posting'),el('small',job.company||'Unknown company'));tr.append(title);
  const statusTd=el('td');statusTd.append(badge(job.status));
  const unanswered=v.answer_queue?.groups.find(g=>g.job_id===job.id&&g.pending_count);
  if(unanswered){const review=el('button',`Answer ${unanswered.pending_count} question${unanswered.pending_count===1?'':'s'}`);review.onclick=()=>tab('answers');statusTd.append(review);}
  if(job.failure_reason)statusTd.append(el('div',`Reason: ${job.failure_reason}`,'job-reason'));
  tr.append(statusTd);
  const assessment=job.assessment;tr.append(el('td',assessment?(assessment.recommendation||'Assessment available'):'Unassessed'));
  $('queue-rows').append(tr);
 }
 if(!v.jobs.length){const tr=el('tr'),td=el('td','No postings in this instance.');td.colSpan=4;tr.append(td);$('queue-rows').append(tr);}
 selection();
}
function renderSessions(v){
 const runtime=v.local_runtime||{sessions:[],workspaces:[]};
 if($('start-application-btn'))$('start-application-btn').textContent=runtime.workspaces.length?'Start in your conversation':'Start application';
 $('local-sessions-card').hidden=!runtime.workspaces.length;
 $('local-sessions').replaceChildren();
 for(const s of runtime.sessions.slice(0,12)){
  const job=v.jobs.find(j=>j.id===s.job_id)||{};
  const candidate=v.candidates.find(c=>c.id===s.identity_id)||{};
  const metadata=s.metadata||{},n=el('div',undefined,'attempt');
  n.append(el('strong',`${job.company||'Company unknown'} · ${job.title||s.job_id}`),badge(s.state));
  n.append(el('p',`${candidate.email||s.identity_id} · ${s.workspace_id||'Waiting for capacity'} · ${s.workspace?.mode||'Mode pending'}`));
  n.append(el('p',`Host ${s.host_alive?'running':'offline'} · Driver ${s.driver_recently_active?'recently active':'idle or disconnected'} · Writer ${s.writer_state}`));
  n.append(el('p',`Executor: ${metadata.provider||'unknown'} / ${metadata.model||'unknown'} · effort ${metadata.reasoning_effort||'unknown'}`));
  const activity=s.activity?.payload;
  if(activity){
   n.append(el('p',`Latest step: ${activity.activity||activity.phase||activity.evidence||s.activity.event_type}`));
   if(activity.next_step)n.append(el('p',`Next: ${activity.next_step}`));
  }else n.append(el('p','No step update recorded by the executor yet.'));
  if(s.steps?.length){
   const details=el('div'),list=el('ol');details.append(el('strong','Recent application steps'));
   for(const step of s.steps){const p=step.payload||{};list.append(el('li',`${stamp(step.observed_at)} · ${p.source||step.event_type} · ${p.activity||p.evidence||p.phase||step.event_type}${p.error_type?' · '+p.error_type:''}`));}
   details.append(list);n.append(details);
  }
  n.append(el('small',`Requested ${stamp(s.requested_at)} · Connected ${stamp(s.connected_at)} · Ended ${stamp(s.ended_at)} · Total ${duration(s.elapsed_seconds)}`));
  n.append(el('small',`Queue ${duration(s.queue_seconds)} · Browser startup ${duration(s.startup_seconds)} · Last verified progress ${stamp(s.last_verified_progress_at)}`));
  if(s.reason)n.append(el('p',s.reason,'job-reason'));
  n.append(el('small',`Session ${s.id} · Attempt ${s.attempt_id||'not started'} · Config ${metadata.config_path||'unknown'}`,'mono'));
  if(s.run_id&&!s.ended_at){
   for(const command of ['pause','stop']){
    const button=el('button',command==='pause'?'Pause this application':'Stop this application');
    button.disabled=s.state==='paused'&&command==='pause';
    button.onclick=async()=>{try{await api('control',{run_id:s.run_id,command});await refresh();}catch(e){notice(e.message,true);}};
    n.append(button);
   }
  }
  $('local-sessions').append(n);
 }
}
function canQueueAnswers(group){return !group.pending_count&&group.browser_stopped&&['blocked','failed','interrupted','ready_for_review','needs_review','queued'].includes(group.status)&&group.retry?.state!=='queued';}
function answerError(error){return ({unanswered_questions:'Answer every required question before queueing a retry.',answer_revision_conflict:'This answer changed elsewhere. Refresh and review the latest saved answer.',question_changed:'The employer changed this question. Review its current choices.',owned_elsewhere:'Save your answers now; queue a retry after the current application closes.',reconciliation_required:'Submission needs to be verified before this application can retry.',already_applied:'This application was already submitted.'})[error.message]||error.message;}
async function saveAnswerGroup(group,queue){
 const changes=group.questions.filter(q=>state.answerDrafts.has(q.id)).map(q=>{const draft=state.answerDrafts.get(q.id);return {question_id:q.id,answer:draft.value,expected_revision:draft.revision};});
 let saved=false;
 try{
  if(changes.length){await api('answer_questions',{answers:changes});for(const change of changes)state.answerDrafts.delete(change.question_id);saved=true;}
  if(queue)await api('queue_answer_retries',{job_ids:[group.job_id],identity_id:group.identity_id});
  notice(queue?'Answers saved and application queued for the next batch.':saved?'Answers saved.':'No answer changes to save.');
  }catch(error){
   if(error.message==='answer_revision_conflict')for(const change of changes)state.answerDrafts.delete(change.question_id);
   notice((saved?'Answers saved. ':'')+answerError(error),true);
  }
 state.answerKey=null;await refresh();
}
function renderAnswers(v){
 if(!$('answer-groups'))return;
 const groups=v.answer_queue?.groups||[];
 const pending=groups.reduce((count,g)=>count+g.pending_count,0);
 $('answer-count').textContent=pending?`(${pending})`:'';
 $('queue-answered-batch').disabled=!groups.some(canQueueAnswers);
 const key=JSON.stringify(groups);if(key===state.answerKey)return;state.answerKey=key;
 $('answer-groups').replaceChildren();
 if(!groups.length){$('answer-groups').append(el('p','No application questions are waiting for you.','answer-empty'));return;}
 for(const group of groups){
  const card=el('article',undefined,'answer-application');
  const heading=el('div',undefined,'section-title');
  const title=el('h3');title.append(link(group.url,`${group.company||'Company unknown'} · ${group.title||'Application'}`));heading.append(title);
  heading.append(badge(group.pending_count?'Needs your answer':group.retry?.state==='queued'?'Queued for retry':'Answers saved'));card.append(heading);
  card.append(el('p',`${group.email} · ${group.pending_count} required question${group.pending_count===1?'':'s'} remaining`,'answer-meta'));
  for(const question of group.questions.filter(q=>q.state!=='superseded')){
   const label=el('label',undefined,'answer-field');label.append(el('span',question.question));
   const draft=state.answerDrafts.get(question.id);
   const current=draft?draft.value:question.answer;
   let input;
   if(question.kind==='text'){input=el('textarea');input.rows=3;input.maxLength=4000;input.value=current??'';}
   else{
    input=el('select');const empty=el('option','Choose your answer');empty.value='';empty.disabled=true;input.append(empty);
    const choices=question.kind==='check'?[{value:'true',label:'Yes'},{value:'false',label:'No'}]:question.options;
    for(const choice of choices){const option=el('option',choice.label);option.value=question.kind==='check'?choice.value:JSON.stringify([choice.value,choice.label]);input.append(option);}
    input.value=current===null||current===undefined?'':question.kind==='check'?String(current):JSON.stringify([current.value,current.label]);
   }
   input.id='answer-'+question.id;input.setAttribute('aria-label',question.question);input.required=true;
   input.oninput=()=>{let value=question.kind==='check'?input.value==='true':input.value;
    if(question.kind==='select'||question.kind==='radio'){const parts=JSON.parse(input.value);value={value:parts[0],label:parts[1]};}
    state.answerDrafts.set(question.id,{value,revision:state.answerDrafts.get(question.id)?.revision??question.revision});};
   label.append(input);
   if(question.answered_at)label.append(el('small',`Saved ${stamp(question.answered_at)}`));
   card.append(label);
  }
  const actions=el('div',undefined,'answer-actions');const save=el('button','Save answers');save.type='button';save.onclick=()=>saveAnswerGroup(group,false);
  const retry=el('button','Save and queue retry','primary');retry.type='button';retry.disabled=!group.browser_stopped||['applied','already_applied','submission_unknown'].includes(group.status);retry.onclick=()=>saveAnswerGroup(group,true);actions.append(save,retry);card.append(actions);
  if(!group.browser_stopped)card.append(el('small','Save your answers to continue in the active application.'));
  if(group.retry?.state==='queued')card.append(el('small','Ready for pickup by your next application batch.'));
  const superseded=group.questions.filter(q=>q.state==='superseded');
  if(superseded.length){const history=el('details');history.append(el('summary','Earlier versions of these questions'));for(const q of superseded)history.append(el('p',q.question+' — choices changed'));card.append(history);}
  $('answer-groups').append(card);
 }
}
function renderRun(v){
 choice('run-picker',v.runs.map(r=>[r.id,`${stamp(r.requested_at)} · ${r.state}`]),state.run||v.current_run?.run_id);
 const r=v.current_run;$('run-counts').replaceChildren();$('attempts').replaceChildren();
 const done=!!r&&(r.state==='completed'||(r.selected>0&&r.completed===r.selected&&!r.remaining&&!r.current));
 document.querySelectorAll('[data-control]').forEach(b=>b.disabled=!r||done);
 if(!r){$('run-state').textContent='No run selected.';$('run-owner').textContent='';return;}
 const activeAttempt=r.attempts?.find(a=>!a.completed_at);
 const leaseSec=v.settings?.values?.lease_seconds||60;
 const localSession=v.local_runtime?.sessions.find(s=>s.run_id===r.run_id);
 const connected=localSession?(!done&&localSession.host_alive&&localSession.driver_recently_active):(!done&&!!activeAttempt&&activeAttempt.heartbeat_age_seconds!==null&&activeAttempt.heartbeat_age_seconds<=leaseSec&&activeAttempt.writer_state!=='expired');
 $('run-state').replaceChildren(badge(done?'Completed':r.state));
 if(done){
  $('run-state').append(document.createTextNode(' — No active application worker.'));
 } else if(r.control==='stop_requested'){
  const b=badge('Stop request pending');b.dataset.state='stop_requested';
  $('run-state').append(b,document.createTextNode(connected?' — awaiting worker acknowledgement.':' — worker disconnected; no acknowledgement.'));
 } else if(r.control==='pause_requested'){
  const b=badge('Pause request pending');b.dataset.state='pause_requested';
  $('run-state').append(b,document.createTextNode(' — acknowledgement pending.'));
 } else if(connected) {
  $('run-state').append(badge(r.control));
 }
 if(r.state==='awaiting_worker'){
  $('run-state').append(document.createTextNode(' — Waiting for worker acceptance.'));
 } else if(localSession&&!done){
  $('run-state').append(document.createTextNode(` · Host ${localSession.host_alive?'running':'offline'}; driver ${localSession.driver_recently_active?'recently active':'idle or disconnected'}`));
 } else if(activeAttempt && (activeAttempt.heartbeat_age_seconds>leaseSec || activeAttempt.writer_state==='expired')){
  const dis=badge('Worker disconnected / not running');dis.dataset.state='stalled';
  $('run-state').append(document.createTextNode(' · '),dis);
 }
 for(const [key,label]of [['selected','Selected'],['completed','Processed'],['applied','Applied'],['blocked','Blocked / uncertain'],['current','Active'],['remaining','Remaining']]){const n=el('div',undefined,'stat');n.append(el('strong',r[key]),el('span',label));$('run-counts').append(n);}
 let requestedSettings={};try{requestedSettings=JSON.parse(r.settings_json||'{}');}catch{}
 const reqModel=requestedSettings.reasoning_model||r.settings?.reasoning_model||'—';
 const reqEffort=r.requested_reasoning_effort||v.settings?.values?.reasoning_effort||'low';
 const verifiedEffort=r.actual_reasoning_effort||r.observed_reasoning_effort||'—';
 const actualModel=r.focused_context?.worker_metadata?.model;
 const workerInfo=actualModel?`${connected?'Connected worker':'Last worker'}: ${actualModel} · verified effort ${verifiedEffort}`:'Model execution not yet verified';
 $('run-owner').textContent=`Requested: ${reqModel} (${reqEffort}) | ${workerInfo}`;
 if(r.state!=='awaiting_worker'&&$('notice').textContent.startsWith('Application run started;'))notice('');
 $('focused-context').replaceChildren();const focused=r.focused_context;
 if(focused){$('focused-context').append(el('strong',`${focused.is_active?'Current job':'Last completed job'}: ${focused.job.company||'Unknown'} · ${focused.job.title||focused.job.id}`),el('p',`Page: ${focused.page||'Unknown'} · Activity: ${focused.activity||'Unknown'}`),el('p',`Skill ${focused.worker_metadata.skill_version||'Unknown'} · ${focused.worker_metadata.provider||'Unknown'} / ${focused.worker_metadata.model||'Unknown'} · effort ${focused.actual_reasoning_effort||focused.worker_metadata.reasoning_effort||'low'}`,'mono'));if(focused.latest_unresolved_issue)$('focused-context').append(el('p','Issue: '+focused.latest_unresolved_issue));if(focused.uncertain_duration)$('focused-context').append(badge('uncertain timing'));}
 $('target-list').replaceChildren();for(const t of r.targets||[]){const n=el('p');n.append(badge(t.state),document.createTextNode(` · attempt ${t.attempt_id} · ${t.target_id} · `),link(t.url,t.url));$('target-list').append(n);}
 $('extension-list').replaceChildren();for(const e of r.budget_extensions||[])$('extension-list').append(el('p',`Attempt ${e.attempt_id}: +${e.seconds}s · ${e.reason} · ${stamp(e.created_at)}`));
 for(const a of r.attempts){
  const n=el('div',undefined,'attempt');const b=el('button',`Attempt ${a.id}`);b.onclick=()=>loadAttempt(a.id);n.append(b,badge(a.outcome||'active'),document.createTextNode(' '+duration(a.elapsed_seconds)));
  n.append(el('small',`Heartbeat ${duration(a.heartbeat_age_seconds)} ago · verified progress ${duration(a.progress_age_seconds)} ago · writer ${a.writer_state}`));if(a.stalled)n.append(badge('stalled'));if(a.over_target)n.append(el('p','Target exceeded — bounded extension or intervention required.'));
  const evidence=a.confirmation_evidence||a.evidence;
  if(a.failure_reason){
    n.append(el('div',`Reason: ${a.failure_reason}`,'attempt-reason'));
  }
  if(evidence||a.outcome==='applied'||a.outcome==='completed'){
   n.append(el('div',`${a.outcome==='applied'?'Employer confirmation':'Outcome details'}: ${evidence||'No confirmation evidence recorded'}`,'verified-evidence'));
  }
  $('attempts').append(n);
 }
}
function renderAccounts(v){$('account-rows').replaceChildren();for(const a of v.accounts){const tr=el('tr');tr.append(el('td',a.namespace||a.portal_key||a.company_key),el('td',a.identity_id||'Legacy / unresolved'),el('td',a.status||'unknown'),el('td',stamp(a.last_confirmed_at)));$('account-rows').append(tr);}
 $('history').replaceChildren();for(const r of v.runs){const n=el('p');const b=el('button',`${stamp(r.requested_at)} · ${r.state}`);b.onclick=()=>{state.run=r.id;tab('run');refresh();};n.append(b,document.createTextNode(' '+r.id));$('history').append(n);}}
function renderResources(v){
 $('lesson-list').replaceChildren();for(const lesson of v.lessons||[]){const row=el('div',undefined,'event');row.append(el('strong',lesson.condition),el('p',lesson.action),badge(lesson.status),el('p',JSON.stringify(lesson.scope)));for(const status of ['active','demoted','retired']){const b=el('button',status==='active'?'Activate':status==='demoted'?'Demote':'Retire');b.disabled=lesson.kind!=='procedure'||lesson.status===status;b.onclick=async()=>{const reason=prompt('Verification or transition reason:');if(!reason)return;try{await api('lesson_set_status',{lesson_id:lesson.id,status,reason});await refresh();}catch(e){notice(e.message,true);}};row.append(b);}const history=el('details');history.append(el('summary',`${(lesson.history||[]).length} verification/history records`));for(const h of lesson.history||[])history.append(el('p',`${stamp(h.created_at)} · ${h.success===null?h.status:h.success?'verified':'failed'} · ${h.reason}`));row.append(history);$('lesson-list').append(row);}if(!v.lessons?.length)$('lesson-list').append(el('p','No observations recorded.'));
 $('helper-list').replaceChildren();for(const helper of v.helpers||[]){const row=el('div',undefined,'event');row.append(el('strong',helper.helper_id+' · '+helper.version),el('p',helper.capability),badge(helper.status),el('p',helper.path,'mono'));const b=el('button','Activate verified version');b.disabled=helper.status==='active';b.onclick=async()=>{const verification_evidence=prompt('Verification evidence reference:');if(!verification_evidence)return;try{await api('helper_activate',{helper_id:helper.helper_id,version:helper.version,verification_evidence});await refresh();}catch(e){notice(e.message,true);}};row.append(b);$('helper-list').append(row);}if(!v.helpers?.length)$('helper-list').append(el('p','No helper versions registered.'));
 $('asset-list').replaceChildren();for(const asset of v.assets||[]){const row=el('div',undefined,'event');row.append(el('strong',asset.kind+' · '+asset.version),badge(asset.status),el('p',asset.identity_id+' · '+asset.storage_ref,'mono'),el('p',asset.sha256,'mono'));for(const selection of v.document_selections||[])if(selection.asset_id===asset.id)row.append(el('p',`Selected for ${selection.job_id}${selection.attempt_id?' · attempt '+selection.attempt_id:''}`));for(const upload of v.document_uploads||[])if(upload.asset_id===asset.id)row.append(el('p',`${upload.status} · attempt ${upload.attempt_id} · ${stamp(upload.created_at)}`));$('asset-list').append(row);}if(!v.assets?.length)$('asset-list').append(el('p','No document metadata registered.'));
 $('assessment-list').replaceChildren();for(const a of v.assessments||[]){const row=el('div',undefined,'event');row.append(el('strong',a.recommendation),el('p',a.score===null?'Unassessed':`${a.score} on scale ${a.scale_min}–${a.scale_max}; not a probability`),el('p',`${a.evaluator} / ${a.model} · ${stamp(a.evaluated_at)}`),el('p',(a.reasons||[]).join('; ')));$('assessment-list').append(row);}if(!v.assessments?.length)$('assessment-list').append(el('p','No external assessments registered.'));
 choice('asset-identity',[['','Select candidate'],...v.candidates.filter(c=>c.state==='active').map(c=>[c.id,c.email+' · '+c.id])]);choice('select-asset',[['','Select version'],...(v.assets||[]).map(a=>[a.id,a.identity_id+' · '+a.kind+' '+a.version])]);choice('select-asset-job',[['','Select job'],...v.jobs.map(j=>[j.id,j.title||j.id])]);
}
function renderSettings(s){
 $('settings-version').textContent=`Version ${s.version}`;
 const modelPicker=$('main-model-picker');
 if(modelPicker){
  const models=[['gpt-5.6-luna','Luna (gpt-5.6-luna)'],['gpt-5.6-terra','Terra (gpt-5.6-terra)']];
  const curModel=s.values.reasoning_model;
  if(curModel&&!models.some(m=>m[0]===curModel))models.push([curModel,curModel]);
  choice('main-model-picker',models,curModel||'gpt-5.6-luna');
 }
 if($('main-effort-picker'))$('main-effort-picker').value=s.values.reasoning_effort||'low';
 if($('main-submission-mode'))$('main-submission-mode').value=s.values.submission_mode||'review';
 if($('main-browser-mode'))$('main-browser-mode').value=s.values.browser_mode||'headed';
 if(state.settingsVersion===s.version)return;state.settingsVersion=s.version;
 const box=$('setting-fields');box.replaceChildren();
 for(const [key,value]of Object.entries(s.values)){const label=el('label',key.replaceAll('_',' '));let input;
  if(s.supported?.[key]){input=el('select');for(const x of s.supported[key]){const o=el('option',x);o.value=x;input.append(o);}input.value=value;}
  else {input=el('input');if(typeof value==='boolean'){input.type='checkbox';input.checked=value;}else if(typeof value==='number'){input.type='number';input.value=value;const range=s.budget_ranges?.[key];if(range){input.min=range[0];input.max=range[1];}}else{input.type='text';input.value=Array.isArray(value)?value.join(', '):(value??'');}}
  input.dataset.setting=key;input.dataset.kind=Array.isArray(value)?'list':(value===null?'nullable':typeof value);label.append(input);box.append(label);
 }
}
async function renderProfile(v){
 const candidates=v.candidates||[];
 if(!candidates.length){
  if(state.profileDirty)return;
  $('profile-candidate')?.replaceChildren();
  if($('profile-hash'))$('profile-hash').textContent='';
  if($('profile-id'))$('profile-id').textContent='';
  if($('profile-person-key'))$('profile-person-key').textContent='';
  if($('profile-email'))$('profile-email').value='';
  if($('profile-full-name'))$('profile-full-name').value='';
  if($('profile-work-auth'))$('profile-work-auth').value='';
  if($('profile-json'))$('profile-json').value='{}';
  if($('profile-resume'))$('profile-resume').textContent='None';
  if($('main-resume-filename'))$('main-resume-filename').textContent='None registered';
  return;
 }
 const currentId=state.profileCandidate||candidates[0].id;
 state.profileCandidate=currentId;
 choice('profile-candidate',candidates.map(c=>[c.id,`${c.email} (${c.id})`]),currentId);
 try{
  const cand=await api('candidate',{identity_id:currentId});
  if($('profile-id'))$('profile-id').textContent=cand.id;
  if($('profile-person-key'))$('profile-person-key').textContent=cand.person_key;
  if($('profile-hash'))$('profile-hash').textContent=`Hash: ${cand.profile_hash.slice(0,16)}...`;
  const prof=cand.profile||{};
  const idSec=prof.identity||{};
  if(!state.profileDirty){
   $('profile-email').value=cand.email;
   $('profile-full-name').value=idSec.full_name||'';
   const auth=prof.work_authorization??prof.facts?.work_authorization??'';
   $('profile-work-auth').value=typeof auth==='string'?auth:JSON.stringify(auth);
   $('profile-json').value=JSON.stringify(prof,null,2);
  }
  const resume=cand.resume_asset?.provenance?.filename||(cand.resume_asset?.storage_ref?cand.resume_asset.storage_ref.split('/').pop():'None registered');
  if($('profile-resume'))$('profile-resume').textContent=resume;
  if($('main-resume-filename'))$('main-resume-filename').textContent=resume;
 }catch(err){
  notice(err.message,true);
 }
}

async function loadAttempt(id){state.attempt=id;try{const report=await api('attempt_report',{attempt_id:id});const a=report.attempt,t=report.timing;const loc=[a.company,a.platform].filter(Boolean).join(' · ');$('attempt-summary').textContent=`Attempt ${id}${loc?' · '+loc:''} · ${a.outcome||'active'} · ${duration(t.wall_seconds)} wall time · ${stamp(a.started_at)} → ${stamp(a.completed_at)}`;$('events').replaceChildren();
 const reasonText=a.failure_reason||report.failure_reason;
 if(reasonText){
  const p=el('p',undefined,'attempt-failure-prominent');
  const strong=el('strong','Reason: ');
  p.append(strong,document.createTextNode(reasonText));
  $('events').append(p);
 }
 $('events').append(el('p',`Observed coverage ${duration(t.observed_union_seconds)}; unattributed ${duration(t.unattributed_seconds)}. Tool ${duration(t.category_seconds.tool)}; model ${duration(t.category_seconds.model)}. ${t.uncertainty?'Some timing is uncertain.':''}`),el('p',t.overlap_note));if(a.profile_hash)$('events').append(el('p',`Attempt profile hash: ${a.profile_hash}`,'mono'));
 const table=el('table'),body=el('tbody');for(const phase of report.phases){const r=el('tr');r.append(el('td',phase.phase),el('td',duration(phase.duration_seconds)));body.append(r);}table.append(body);$('events').append(table);
 if(report.fields&&Object.keys(report.fields).length){
  const fTable=el('table'),fBody=el('tbody');
  fBody.append(el('tr',undefined,undefined,[el('th','Field'),el('th','Elapsed'),el('th','Actions'),el('th','Status')]));
  for(const [k,f] of Object.entries(report.fields)){
   fBody.append(el('tr',undefined,undefined,[el('td',f.field_key),el('td',f.elapsed_seconds!=null?duration(f.elapsed_seconds):'unknown'),el('td',String(f.action_count)),el('td',f.verified?'verified':'unverified')]));
  }
  fTable.append(fBody);$('events').append(el('h4','Field Telemetry'),fTable);
 }
 if(report.simplify&&report.simplify.runs_count){
  const s=report.simplify;
  $('events').append(el('p',`Simplify runs: ${s.runs_count} · Total duration: ${duration(s.total_duration_seconds)}${s.fallback_reasons.length?' · Fallback reasons: '+s.fallback_reasons.join(', '):''}`));
 }
 if(report.problems&&report.problems.length){
  const pTable=el('table'),pBody=el('tbody');
  pBody.append(el('tr',undefined,undefined,[el('th','Category'),el('th','Field'),el('th','Fallback Reason'),el('th','Source'),el('th','Status'),el('th','Resolution')]));
  for(const p of report.problems){
   pBody.append(el('tr',undefined,undefined,[el('td',p.category||'-'),el('td',p.field_key||'-'),el('td',p.fallback_reason||'-'),el('td',p.source||'native'),el('td',p.status||'-'),el('td',p.resolution||'-')]));
  }
  pTable.append(pBody);$('events').append(el('h4','Problems & Recoveries'),pTable);
 }
 for(const e of report.timeline){const row=el('details',undefined,'event');row.append(el('summary',`${stamp(e.observed_at)} · ${e.payload.activity||e.payload.evidence||e.event_type} · ${duration(e.duration_seconds)}${e.stale?' · late metadata':''}`),el('pre',JSON.stringify(e.payload,null,2)));$('events').append(row);}if(!report.timeline.length)$('events').append(el('p','No events recorded.'));}catch(e){notice(e.message,true);}}

async function refresh(){if(!state.instance||state.busy)return;state.busy=true;try{const v=await api('view',state.run?{run_id:state.run}:{});state.view=v;$('instance').textContent=`Instance ${v.health.instance_id} · DB ${v.health.db_path}`;$('mode').textContent=v.settings.values.mode+' / '+v.settings.values.submission_mode;$('mode').dataset.state=v.settings.values.mode;
 choice('candidate',v.candidates.filter(c=>c.state==='active').map(c=>[c.id,c.email]));
 if($('browser-profile')&&!$('browser-profile').value.trim()){
  $('browser-profile').value=v.current_run?.browser_profile||v.runs?.[0]?.browser_profile||'operator-chrome';
 }
 renderQueue(v);renderRun(v);renderAccounts(v);renderResources(v);renderSettings(v.settings);await renderProfile(v);$('health').textContent=JSON.stringify(v.health,null,2);if(state.attempt)await loadAttempt(state.attempt);
 }catch(e){notice(e.message,true);}finally{state.busy=false;}}
function tab(name){document.querySelectorAll('.tab').forEach(n=>n.hidden=n.id!=='tab-'+name);document.querySelectorAll('[data-tab]').forEach(n=>n.classList.toggle('active',n.dataset.tab===name));}
$('reconnect').onclick=()=>location.reload();
$('refresh').onclick=refresh;document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
if($('queue-answered-batch'))$('queue-answered-batch').onclick=async()=>{
 try{const candidates=new Map();for(const group of state.view?.answer_queue?.groups||[]){if(!canQueueAnswers(group))continue;const jobs=candidates.get(group.identity_id)||[];jobs.push(group.job_id);candidates.set(group.identity_id,jobs);}
  let count=0;for(const [identity_id,job_ids] of candidates){await api('queue_answer_retries',{identity_id,job_ids});count+=job_ids.length;}
  notice(`${count} answered application${count===1?'':'s'} queued for the next batch.`);await refresh();
 }catch(error){notice(answerError(error),true);}
};
$('intake-form').onsubmit=async e=>{e.preventDefault();try{const job=await api('intake',{url:$('job-url').value,company:$('job-company').value,title:$('job-title').value,source_type:'manual',source_id:crypto.randomUUID()});notice(`Recorded ${job.id}; ${job.status}, ${job.eligibility}.`);$('intake-form').reset();await refresh();}catch(err){notice(err.message,true);}};
$('mark-ready').onclick=async()=>{try{if(!state.selected.size)throw Error('Select at least one job.');for(const id of state.selected)await api('eligibility',{job_id:id,decision:'ready',reason:'Explicit operator approval'});notice('Selected eligibility recorded.');await refresh();}catch(e){notice(e.message,true);}};
$('request-run').onclick=async()=>{try{if(!state.selected.size||!$('candidate').value||!$('browser-profile').value.trim())throw Error('Select jobs, candidate and exact browser profile.');const r=await api('request_run',{request_id:crypto.randomUUID(),job_ids:[...state.selected],identity_id:$('candidate').value,browser_profile:$('browser-profile').value.trim()});state.run=r.id;state.attempt=null;notice('Run requested; waiting for worker acceptance.');tab('run');await refresh();}catch(e){notice(e.message,true);}};
if($('start-application-btn')){$('start-application-btn').onclick=async()=>{try{
 if(state.view?.local_runtime?.workspaces?.length){notice('Give your application conversation one eligible job URL. Its session and browser will appear here.');return;}
 if(!state.selected.size)throw Error('Please select at least one job from the queue.');
 const candidateId=$('candidate').value;if(!candidateId)throw Error('Please select a candidate.');
 const browserProfile=($('browser-profile').value||'').trim()||'operator-chrome';
 const chosenModel=$('main-model-picker')?.value||'gpt-5.6-luna';
 const chosenEffort=$('main-effort-picker')?.value||'low';
 const chosenSubMode=$('main-submission-mode')?.value||'review';
 const chosenBrowserMode=$('main-browser-mode')?.value||'headed';
 const opMode=chosenSubMode==='submit'?'pilot':'development';
 await api('configure',{changes:{reasoning_provider:'openai-codex',reasoning_model:chosenModel,reasoning_effort:chosenEffort,submission_mode:chosenSubMode,mode:opMode,browser_mode:chosenBrowserMode},expected_version:state.settingsVersion});
 for(const id of state.selected){await api('eligibility',{job_id:id,decision:'ready',reason:'Operator approved start application'});}
 const r=await api('request_run',{request_id:crypto.randomUUID(),job_ids:[...state.selected],identity_id:candidateId,browser_profile:browserProfile});
 state.run=r.id;state.attempt=null;tab('run');notice('Application run started; waiting for worker acceptance.');await refresh();
}catch(err){notice(err.message,true);}};}
$('run-picker').onchange=()=>{state.run=$('run-picker').value;state.attempt=null;refresh();};
for(const b of document.querySelectorAll('[data-control]'))b.onclick=async()=>{try{const r=state.view?.current_run;if(!r)throw Error('No run selected.');await api('control',{run_id:r.run_id,command:b.dataset.control});notice('Control request recorded; observe acknowledgement.');await refresh();}catch(e){notice(e.message,true);}};
$('copy-handoff').onclick=async()=>{const r=state.view?.current_run;if(!r)return;const text=`Use the canonical job-apply skill to accept JobBot run ${r.run_id} in instance ${state.instance}; pull one job at a time and obey app controls.`;try{await navigator.clipboard.writeText(text);notice('Worker handoff copied.');}catch{notice(text);}};
$('settings-form').onsubmit=async e=>{e.preventDefault();try{const changes={};for(const n of document.querySelectorAll('[data-setting]')){const k=n.dataset.setting,kind=n.dataset.kind;changes[k]=kind==='boolean'?n.checked:kind==='number'?Number(n.value):kind==='list'?n.value.split(',').map(x=>x.trim()).filter(Boolean):kind==='nullable'?(n.value.trim()||null):n.value;}await api('configure',{changes,expected_version:state.settingsVersion});notice('Settings saved for new requests.');await refresh();}catch(err){notice(err.message,true);}};
(async()=>{try{const data=await request('/session',undefined,'GET');state.instance=data.instance_id;showConsole();await refresh();}catch{showLogin();}})();
$('helper-form').onsubmit=async e=>{e.preventDefault();try{const scope={};if($('helper-platform').value)scope.platform=$('helper-platform').value;if($('helper-namespace').value)scope.namespace=$('helper-namespace').value;await api('helper_register',{helper_id:$('helper-id').value,version:$('helper-version').value,capability:$('helper-capability').value,path:$('helper-path').value,sha256:$('helper-hash').value,scope,preconditions:[],limitations:[],tests:$('helper-tests').value.split('\n').filter(Boolean)});notice('Candidate helper version registered, not activated.');$('helper-form').reset();await refresh();}catch(err){notice(err.message,true);}};
$('asset-form').onsubmit=async e=>{e.preventDefault();try{await api('register_asset',{identity_id:$('asset-identity').value,kind:$('asset-kind').value,version:$('asset-version').value,storage_ref:$('asset-ref').value,sha256:$('asset-hash').value,provenance:{source:$('asset-source').value}});notice('External document metadata registered; not selected or uploaded.');$('asset-form').reset();await refresh();}catch(err){notice(err.message,true);}};
$('asset-select-form').onsubmit=async e=>{e.preventDefault();try{await api('select_asset',{asset_id:$('select-asset').value,job_id:$('select-asset-job').value});notice('Document selected for job; upload not yet confirmed.');await refresh();}catch(err){notice(err.message,true);}};
$('profile-form').oninput=()=>{state.profileDirty=true;};
$('profile-candidate').onchange=async()=>{state.profileDirty=false;state.profileCandidate=$('profile-candidate').value;await renderProfile(state.view);};
$('profile-form').onsubmit=async e=>{e.preventDefault();try{
 let prof={};try{prof=JSON.parse($('profile-json').value);}catch{throw Error('Profile JSON must be valid JSON');}
 const email=$('profile-email').value.trim();
 if(!email||!email.includes('@'))throw Error('Valid email required');
 const idSec=prof.identity||{};idSec.email=email;if($('profile-full-name').value.trim())idSec.full_name=$('profile-full-name').value.trim();prof.identity=idSec;
 const auth=$('profile-work-auth').value.trim();
 if(auth)prof.work_authorization=/^[{[]/.test(auth)?JSON.parse(auth):auth;
 const r=await api('import_profile',{data:prof,identity_id:state.profileCandidate});
 state.profileDirty=false;
 state.profileCandidate=r.candidate.id;
 notice(`Profile saved for candidate ${r.candidate.id}.`+(r.skipped.length?' Unsupported fields omitted: '+r.skipped.join(', '):''));
 await refresh();
}catch(err){notice(err.message,true);}};
$('profile-import-file').onchange=async e=>{
 const file=e.target.files?.[0];if(!file)return;
 const reader=new FileReader();
 reader.onload=async()=>{
  try{
   const raw=JSON.parse(reader.result);
   const {clean,skipped}=sanitizeLegacyClient(raw);
   $('profile-import-skipped').replaceChildren();
   if(skipped.length){
    $('profile-import-skipped').append(el('p','Skipped non-factual / excluded fields: '+skipped.join(', ')));
   }
   const res=await api('import_profile',{data:clean,identity_id:state.profileCandidate});
   state.profileDirty=false;
   state.profileCandidate=res.candidate.id;
   notice(`Imported profile for ${res.candidate.email} (${res.candidate.id}); ${skipped.length} excluded fields skipped.`);
   e.target.value='';
   await refresh();
  }catch(err){notice(err.message,true);e.target.value='';}
 };
 reader.readAsText(file);
};
$('profile-resume-form').onsubmit=async e=>{
 e.preventDefault();
 const file=$('profile-resume-file').files?.[0];
 if(!file||!state.profileCandidate){notice('Candidate and resume file required.',true);return;}
 try{
  const buffer=await file.arrayBuffer();
  const url=`/v1/upload_asset?identity_id=${encodeURIComponent(state.profileCandidate)}&filename=${encodeURIComponent(file.name)}&kind=resume`;
  const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-JobBot-Instance':state.instance},credentials:'same-origin',body:buffer});
  const data=await res.json();
  if(!res.ok)throw new Error(data.error||`HTTP ${res.status}`);
  notice(`Registered resume ${data.version} (${file.name}).`);
  $('profile-resume-file').value='';
  await refresh();
 }catch(err){notice(err.message,true);}
};
setInterval(()=>{if(state.instance)refresh();},1500);
