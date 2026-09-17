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
function submitted(job){return ['applied','already_applied'].includes(job.status);}
function unfinished(job){return !submitted(job)&&job.disposition!=='canceled'&&!job.archived;}
function latestDispatch(v,job){return v.dispatch_queue?.latest_by_job?.[job.id]||v.dispatch_queue?.items?.find(q=>q.job_id===job.id);}
function postingMetadata(job){let metadata=job.metadata||{};try{if(job.metadata_json)metadata=JSON.parse(job.metadata_json);}catch{}return metadata;}
function discoverySkipped(job){return job.eligibility==='held'&&String(postingMetadata(job).verdict||'').trim().toLowerCase()==='skip';}
function postingCountry(job){const metadata=postingMetadata(job);const country=metadata.country||(/(?:, |\()United States\)?$/.test(metadata.location||'')?'US':'');if(!country)return 'Unavailable';try{return /^[A-Z]{2}$/.test(country)?new Intl.DisplayNames(['en'],{type:'region'}).of(country):country;}catch{return country;}}
function postingDate(job){const value=postingMetadata(job).posted_at;if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}(?:$|T)/.test(value))return 'Unavailable';const day=value.slice(0,10);const parsed=new Date(day+'T00:00:00Z');return !Number.isNaN(parsed.getTime())&&parsed.toISOString().slice(0,10)===day?day:'Unavailable';}
function queueJobStatus(job,queued,local){
 if(job.disposition==='canceled')return 'Canceled';
 if(submitted(job))return displayStatus(job.status);
 if(queued?.waiting_for_retry)return 'Retry scheduled';
 if(queued?.state==='queued'&&queued.immediate_requested_at)return 'Apply now requested';
 if(queued?.automatic_limit_reached)return 'Needs attention';
 if(queued?.state==='queued')return 'Queued';
 if(queued?.state==='dispatched')return 'In progress';
 if(discoverySkipped(job))return 'Not selected for application';
 const outcome=queued?.outcome==='canceled'?job.status:queued?.outcome||job.status;
 return local&&outcome==='queued'?(job.eligibility==='excluded'?'Excluded':job.intervention_reason?'Needs attention':'Awaiting automatic pickup'):displayStatus(outcome);
}
function visibleJobs(v){
 const filter=$('job-filter').value,query=$('job-search').value.trim().toLocaleLowerCase();
 return v.jobs.filter(job=>{
  if(query&&![job.company,job.title,job.url].filter(Boolean).join(' ').toLocaleLowerCase().includes(query))return false;
  if(filter==='canceled')return job.disposition==='canceled';
  if(filter==='submitted')return submitted(job);
  if(filter==='active')return unfinished(job);
  if(filter==='attention'){
   const queued=latestDispatch(v,job);
   const problems=['blocked','failed','interrupted','submission_unknown','ready_for_review','skipped'];
   return unfinished(job)&&(problems.includes(job.status)||!!job.failure_reason||(queued?.state==='finished'&&problems.includes(queued.outcome)));
  }
  return true;
 });
}
function selection(){
 const selected=(state.view?.jobs||[]).filter(j=>state.selected.has(j.id));
 const cancelable=selected.filter(unfinished),restorable=selected.filter(j=>j.disposition==='canceled');
 $('selection').textContent=state.selected.size?`${state.selected.size} job${state.selected.size===1?'':'s'} selected`:'No jobs selected';
 $('start-application-btn').disabled=!cancelable.length||cancelable.length!==selected.length;
 $('cancel-selected').disabled=!cancelable.length;
 $('restore-selected').disabled=!restorable.length;
 $('clear-selection').disabled=!state.selected.size;
 const visible=state.view?visibleJobs(state.view):[];
 $('select-unfinished').disabled=!visible.some(unfinished);
 $('select-visible').disabled=!visible.some(j=>j.disposition==='canceled');
}
function link(url,label){try{const u=new URL(url);if(!['http:','https:'].includes(u.protocol))return el('span',label);const a=el('a',label);a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';return a;}catch{return el('span',label);}}
function postingLabel(job){
 const known=[job.company,job.title||job.job_title].filter(Boolean);if(known.length)return known.join(' · ');
 let metadata=job.metadata||{};try{if(job.metadata_json||job.job_metadata_json)metadata=JSON.parse(job.metadata_json||job.job_metadata_json);}catch{}
 return metadata.label_discovery?.status==='unavailable'?'Company and role unavailable':'Identifying company and role';
}
function postingHeading(job){const n=el('div',undefined,'posting-heading');n.append(el('strong',postingLabel(job)));
 const url=job.url||job.job_url;if(url){let hostname='View job posting';try{hostname=new URL(url).hostname;}catch{}n.append(link(url,hostname));}return n;}
const progressExpansion=new Map();
function rememberProgress(root){for(const node of root.querySelectorAll('details[data-progress-key]'))progressExpansion.set(node.dataset.progressKey,node.open);}
function progressDetails(key,title,open=false,cls='progress-stage'){
 const n=el('details',undefined,cls);n.dataset.progressKey=key;n.open=progressExpansion.has(key)?progressExpansion.get(key):open;n.append(el('summary',title));return n;
}
function renderProgress(progress,key){
 const root=el('div',undefined,'application-progress');
 const states={in_progress:'In progress',completed:'Completed',recovering:'Recovering',awaiting_input:'Awaiting your input',unsuccessful:'Unsuccessful'};
 if(!progress?.details_recorded)root.append(el('p','Details not recorded.','progress-empty'));
 for(const stage of progress?.stages||[]){
  const section=progressDetails(key+':stage:'+stage.id,stage.title,stage.state!=='completed');
  section.querySelector('summary').append(badge(states[stage.state]||'In progress'));
  for(const task of stage.tasks||[]){
   const row=el('div',undefined,'progress-task');row.append(el('span',task.title),badge(states[task.state]||'In progress'));
   if(typeof task.elapsed_seconds==='number')row.append(el('small',`Elapsed ${duration(task.elapsed_seconds)}${task.wait_seconds?' · Waiting for your input '+duration(task.wait_seconds):''}${typeof task.action_seconds==='number'?' · Recorded actions '+duration(task.action_seconds):''}`));
   section.append(row);
  }
  if(stage.omitted_completed_tasks)section.append(el('small',`${stage.omitted_completed_tasks} earlier completed tasks in the full application history.`));root.append(section);
 }
 const debug=progressDetails(key+':debug','Debug details',false,'debug-details');
 for(const event of progress?.debug||[])debug.append(el('pre',JSON.stringify(event,null,2)));
 root.append(debug);return root;
}
function sourceLabel(value){return ({manual:'Manual',legacy_cli:'Legacy CLI',
 'job_harvester:google_jobs':'Job Harvester / Google Jobs','job_harvester:linkedin':'Job Harvester / LinkedIn',
 linkedin_alert_email:'LinkedIn alert email',employer_search:'Employer search'})[value]||value||'Unknown';}
function producerLabel(value){return ({dashboard:'Dashboard',queue_cli:'Queue CLI',legacy_cli:'Legacy CLI',managed_cli:'Managed CLI',
 application_runtime:'Application runtime',discovery_intake:'Discovery import',queue_worker:'Queue worker',
 hermes_scheduled_discovery:'Hermes scheduled discovery',hermes_manual_discovery:'Hermes manual discovery'})[value]||value||'Not recorded';}
function enqueueLabel(value){return ({discovery:'Discovery handoff',manual_enqueue:'Manual enqueue',api_request:'API request',
 manual_retry:'Manual retry',automatic_intake:'Automatic pickup',automatic_retry:'Automatic retry',
 automatic_restore:'Automatic pickup after restoration',answer_retry:'Retry after answer'})[value]||value||'Not recorded';}
function processDetails(parent,item){
 parent.append(el('small','Process: '+producerLabel(item.producer)));
 if(item.discovery_profile)parent.append(el('small','Profile: '+item.discovery_profile));
 if(item.discovery_run_id)parent.append(el('small','Discovery run: '+item.discovery_run_id));
}
function sourceCell(job,queued){
 const td=el('td'),sources=job.sources||[];
 td.append(el('span',sourceLabel(sources[0]?.source_type)));
 const firstObservation=sources[0]?.observations?.[0];
 td.append(el('small',firstObservation?'Seen by '+producerLabel(firstObservation.producer):'Discovery process: Not recorded'));
 const detail=progressDetails(job.id+':sources',`Origin details · ${sources.length} source${sources.length===1?'':'s'}`);
 for(const source of sources){
  const row=el('div');row.append(el('strong',sourceLabel(source.source_type)),
   el('small',`First recorded ${stamp(source.discovered_at)}`));
  if(source.original_url)row.append(link(source.original_url,'Discovery link'));
  if(!source.observations?.length)row.append(el('small','Discovery process: Not recorded'));
  for(const observation of source.observations||[]){
   const seen=el('div');processDetails(seen,observation);
   seen.append(el('small','Observed '+stamp(observation.recorded_at)));row.append(seen);
  }
  detail.append(row);
 }
 const hasHistory=!!job.queue_origins?.length;
 const entries=hasHistory?job.queue_origins:queued?[queued]:[];
 if(entries.length){
  td.append(el('small',(hasHistory?'First queued: ':'Latest queue entry: ')+enqueueLabel(entries[0].enqueue_origin)));
  detail.append(el('strong','Queue entry history'));
  for(const entry of entries){
   const row=el('div');row.append(el('span',enqueueLabel(entry.enqueue_origin)));
   processDetails(row,entry);row.append(el('small','Queued '+stamp(entry.created_at)));
   if(entry.request_id)row.append(el('small','Request: '+entry.request_id));detail.append(row);
  }
 }else detail.append(el('small','No queue entry recorded'));
 td.append(detail);return td;
}
function sourceReferenceCell(job){
 const td=el('td',undefined,'source-reference');
 if(!job.sources?.length)td.append(el('span','Not recorded'));
 for(const source of job.sources||[]){
  const row=el('div'),reference=source.source_id||'Reference unavailable';
  row.title=sourceLabel(source.source_type);
  row.append(source.original_url?link(source.original_url,reference):el('span',reference));td.append(row);
 }
 return td;
}
function applicationTimeCell(job){
 const td=el('td',undefined,'application-time'),timing=job.application_timing;
 if(!submitted(job)){td.textContent='—';return td;}
 if(!Number.isFinite(timing?.elapsed_seconds)||timing.elapsed_seconds<0){td.textContent='Not recorded';return td;}
 const seconds=Math.round(timing.elapsed_seconds),hours=Math.floor(seconds/3600),minutes=Math.floor(seconds%3600/60);
 td.textContent=(timing.uncertain_duration?'Approx. ':'')+(hours?`${hours}h ${minutes}m ${seconds%60}s`:minutes?`${minutes}m ${seconds%60}s`:`${seconds}s`);
 td.title=`Successful attempt: ${stamp(timing.started_at)} to ${stamp(timing.completed_at)}. Includes waits during this attempt; excludes earlier attempts and queue time.`;
 if(timing.uncertain_duration)td.title+=' Some timing evidence is incomplete.';
 return td;
}
function dispositionCell(job){
 const td=el('td'),last=job.last_disposition;
 if(!last){td.append(el('span','Not recorded'));return td;}
 const label=last.source==='operator'?(last.value==='active'?'Restored':'Canceled'):displayStatus(last.value);
 td.append(el('span',label),el('small',stamp(last.at)),el('small',({operator:'By you',application:'Application outcome',queue:'Queue outcome'})[last.source]||last.source));
 return td;
}
function renderQueue(v){
 renderSessions(v);
 renderAnswers(v);
 renderDispatcher(v);
 const jobs=visibleJobs(v),visibleIds=new Set(jobs.map(j=>j.id));
 for(const id of state.selected)if(!visibleIds.has(id))state.selected.delete(id);
 const key=JSON.stringify([jobs,v.answer_queue,v.dispatch_queue?.items,v.dispatch_queue?.latest_by_job,[...state.selected],$('job-filter').value]);if(key===state.queueKey){selection();return;}state.queueKey=key;
 rememberProgress($('queue-rows'));
 const canceledView=$('job-filter').value==='canceled';
 $('select-visible').hidden=!canceledView;$('select-unfinished').hidden=canceledView;
 $('restore-selected').hidden=!jobs.some(j=>j.disposition==='canceled');
 $('cancel-selected').hidden=canceledView;$('cancel-reason').closest('label').hidden=canceledView;
 $('queue-count').textContent=`${jobs.length} shown · ${v.jobs.length} total`;$('queue-rows').replaceChildren();
 for(const job of jobs){
  const tr=el('tr');
  const check=el('input');check.type='checkbox';check.checked=state.selected.has(job.id);
  check.disabled=submitted(job)&&job.disposition!=='canceled';
  check.setAttribute('aria-label','Select '+postingLabel(job));
  check.onchange=()=>{if(check.checked)state.selected.add(job.id);else state.selected.delete(job.id);selection();};
  const cell=el('td');cell.append(check);tr.append(cell);
  const title=el('td');title.append(postingHeading(job));tr.append(title);
  const queued=latestDispatch(v,job);
  const statusTd=el('td');statusTd.append(badge(queueJobStatus(job,queued,!!v.local_runtime?.workspaces?.length)));
  if(v.local_runtime?.workspaces?.length&&unfinished(job)&&!['queued','dispatched'].includes(queued?.state)){
   statusTd.append(el('small',queued?.automatic_limit_reached?'Six attempts ended without completion. Review the reason; Retry selected starts a new attempt series.':discoverySkipped(job)?'Discovery marked this job Skip. Review its match before explicitly choosing Retry selected.':queued?.state==='finished'?'The worker schedules recovery for interrupted or failed attempts. Review-only results and user stops stay here.':job.intervention_reason||'Active jobs enter the execution queue automatically.'));
  }
  if(queued?.attempt_number)statusTd.append(el('small',`Attempt ${queued.attempt_number} of ${v.dispatch_queue?.automatic_attempt_limit||3}`));
  if(queued?.waiting_for_retry)statusTd.append(el('small',`Retry at ${stamp(queued.next_attempt_at)}. Other ready jobs can run first.`));
  if(v.local_runtime?.workspaces?.length&&unfinished(job)){
   const apply=el('button',queued?.state==='dispatched'?'In progress':'Apply now','primary');
   apply.type='button';apply.dataset.applyNow=job.id;apply.disabled=queued?.state==='dispatched';
   apply.setAttribute('aria-label',apply.textContent+' · '+postingLabel(job));
   apply.onclick=()=>applyNow(job,apply);statusTd.append(apply);
   if(queued?.state==='queued'&&queued.immediate_requested_at)statusTd.append(el('small','Starts when the worker is free, ahead of automatic jobs.'));
  }
  if(job.disposition==='canceled')statusTd.append(el('small',job.disposition_reason||'Canceled by you'),el('small','Last outcome: '+displayStatus(job.status)));
  const unanswered=v.answer_queue?.groups.find(g=>g.job_id===job.id&&g.pending_count);
  if(unanswered&&job.disposition!=='canceled'){const review=el('button',`Answer ${unanswered.pending_count} question${unanswered.pending_count===1?'':'s'}`);review.onclick=()=>tab('answers');statusTd.append(review);}
  if(job.failure_reason||queued?.detail){const details=progressDetails(job.id+':outcome','Outcome details',false,'job-outcome');details.append(el('p','Reason: '+(job.failure_reason||queued.detail)));statusTd.append(details);}
  tr.append(statusTd);
  const assessment=job.assessment;tr.append(el('td',assessment?(assessment.recommendation||'Assessment available'):'Unassessed'));
  tr.append(el('td',postingCountry(job)),el('td',postingDate(job)));
  tr.append(sourceCell(job,queued),sourceReferenceCell(job),el('td',stamp(job.created_at)),dispositionCell(job),applicationTimeCell(job));
  $('queue-rows').append(tr);
 }
 if(!jobs.length){const tr=el('tr'),td=el('td',v.jobs.length?'No jobs match this view.':'No postings in this instance.');td.colSpan=11;tr.append(td);$('queue-rows').append(tr);}
 selection();
}
function renderSessions(v){
 const runtime=v.local_runtime||{sessions:[],workspaces:[]};
 if($('start-application-btn'))$('start-application-btn').textContent=runtime.workspaces.length?'Retry selected':'Start application';
 $('local-sessions-card').hidden=!runtime.workspaces.length&&!runtime.sessions.length;
 const historyScroll=$('session-history')?.scrollTop||0;
 rememberProgress($('local-sessions'));$('local-sessions').replaceChildren();
 const active=runtime.sessions.filter(s=>!s.ended_at);
 const past=runtime.sessions.filter(s=>s.ended_at);
 $('activity-count').textContent=active.length?`${active.length} in progress`:'No application running';
 const history=progressDetails('session-history',`Recent history · ${past.length} application${past.length===1?'':'s'}`,false,'session-history');history.id='session-history';
 if(!active.length)$('local-sessions').append(el('p','Current work will appear here. Open recent history to review earlier applications.','activity-empty'));
 for(const s of [...active,...past]){
  const job=v.jobs.find(j=>j.id===s.job_id)||{};
  const candidate=v.candidates.find(c=>c.id===s.identity_id)||{};
  const metadata=s.metadata||{},n=progressDetails(s.id+':application',postingLabel(job),false,'application-row');
  const summary=n.querySelector('summary');
  summary.append(badge(!s.ended_at&&s.host_alive===false&&s.state==='connected'?'Needs attention':displayStatus(s.state)));
  n.append(postingHeading(job));
  if(metadata.application_kind)n.append(badge(metadata.application_kind==='reattempt'?'Reattempt':'First attempt'));
  if(candidate.email)n.append(el('p',candidate.email));
  const progress=renderProgress(s.progress||{debug:s.steps||[]},s.id),debug=progress.querySelector('.debug-details');n.append(progress);
  debug.append(el('p',`Host ${s.host_alive?'running':'offline'} · Driver ${s.driver_recently_active?'recently active':'idle or disconnected'} · Writer ${s.writer_state}`));
  debug.append(el('p',`Executor: ${metadata.provider||'unknown'} / ${metadata.model||'unknown'} · effort ${metadata.reasoning_effort||'unknown'}`));
  n.append(el('small',`Requested ${stamp(s.requested_at)} · Connected ${stamp(s.connected_at)} · Ended ${stamp(s.ended_at)} · Total ${duration(s.elapsed_seconds)}`));
  n.append(el('small',`Queue ${duration(s.queue_seconds)} · Browser startup ${duration(s.startup_seconds)} · Last verified progress ${stamp(s.last_verified_progress_at)}`));
  if(s.first_autofill_at)n.append(el('small',`First Autofill ${stamp(s.first_autofill_at)} · Ready to Autofill ${duration(s.ready_to_autofill_seconds)}`));
  if(s.reason)debug.append(el('p',s.reason,'job-reason'));
  debug.append(el('small',`Session ${s.id} · Attempt ${s.attempt_id||'not started'} · Config ${metadata.config_path||'unknown'}`,'mono'));
  if(s.run_id&&!s.ended_at){
   for(const command of ['pause','stop']){
    const button=el('button',command==='pause'?'Pause this application':'Stop this application');
    button.disabled=s.state==='paused'&&command==='pause';
    button.onclick=async()=>{try{await api('control',{run_id:s.run_id,command});await refresh();}catch(e){notice(e.message,true);}};
    n.append(button);
   }
  }
  (s.ended_at?history:$('local-sessions')).append(n);
 }
 if(past.length){$('local-sessions').append(history);history.scrollTop=historyScroll;}
}
function displayStatus(value){return ({connected:'In progress',preparing:'In progress',waiting:'In progress',running:'In progress',finishing:'In progress',capacity_wait:'Waiting to start',applied:'Applied',already_applied:'Already applied',ready_for_review:'Ready for review',submission_unknown:'Submission uncertain',blocked:'Needs attention',failed:'Needs attention',interrupted:'Interrupted',paused:'Paused',queued:'Queued',completed:'Completed',stopped:'Stopped',skipped:'Skipped'})[value]||value||'Not started';}
async function applyNow(job,button){
 if(button.disabled)return;
 button.disabled=true;
 try{
  const identity_id=$('candidate').value;
  const asset=(state.view.assets||[]).find(a=>a.id===$('queue-resume').value&&a.identity_id===identity_id&&a.kind==='resume'&&a.status==='available');
  if(!asset)throw Error('Choose a candidate with a registered resume.');
  const submission_mode=$('main-submission-mode').value;
  if(submission_mode!==state.view.settings.values.submission_mode)await api('configure',{changes:{submission_mode,mode:submission_mode==='submit'?'pilot':'development'},expected_version:state.settingsVersion});
  const result=await api('queue_enqueue',{job_ids:[job.id],identity_id,resume_asset_id:asset.id,request_id:crypto.randomUUID(),retry:true,start_now:true,producer:'dashboard',enqueue_origin:'manual_retry'});
  const q=result.queue||{},item=result.items[0];
  const message=item.state==='dispatched'?'This application is already in progress.':
   !q.worker_online?'Request saved, but the queue worker is offline. It will start this job when the service is back online.':
   q.counts?.dispatched?'Request saved. This job will run after the current application and any earlier Apply now requests.':
   'Request saved. The worker will start this job as soon as its browser is free, ahead of automatic jobs.';
  notice(postingLabel(job)+': '+message);
  await refresh();
 }catch(error){notice(error.message,true);}
 finally{button.disabled=false;}
}
function runNextMessage(q){
 if(!q.counts?.queued)return q.counts?.dispatched?'An application is already in progress. No other jobs are waiting.':'No eligible jobs are waiting. Active jobs are picked up automatically; check job reasons below.';
 if(!q.worker_online)return 'Request saved, but the queue worker is offline. Start the JobBot queue service to run queued jobs.';
 if(q.ready_count===0&&q.scheduled_count)return `Retries are scheduled for later. Next retry: ${stamp(q.next_job_at)}.`;
 return q.counts?.dispatched?'Request saved. The next queued job will wait for the current application to finish.':'Request saved. The worker will start the next queued job when its browser is free.';
}
function renderDispatcher(v){
 const q=v.dispatch_queue||{};
 const discovery=v.discovery;
 if($('discovery-status')){
  const last=discovery?.last_run;
  $('discovery-status').textContent=!discovery?.installed?'Discovery status unavailable until the updated discovery service is installed.':
   `Discovery: up to ${discovery.batch_size} jobs every ${discovery.interval_hours} hours · Runner: ${discovery.runner}. `+
   `${last?`Last started ${stamp(last.started_at)} · ${last.state==='completed'?'Executor finished; see discovered jobs':last.state==='incomplete'?'Incomplete: executor ended without saving discovery results':displayStatus(last.state)}. `:'No discovery run recorded yet. '}`+
   `${last?.state==='running'?'Discovery is running. ':`Next due: ${discovery.next_due_at?stamp(discovery.next_due_at):'next scheduler check'}. `}`+
   `${discovery.scheduler_recent?'Scheduler checked recently.':last?.state==='running'?`Last scheduler check: ${stamp(discovery.scheduler_last_checked_at)}.`:'No recent scheduler check; check the discovery service.'} Change frequency and job limit in Settings.`;
 }
 if($('main-resume-filename'))$('main-resume-filename').hidden=!!v.local_runtime?.workspaces?.length;
 const candidate=$('candidate')?.value;
 if($('queue-resume')){
  const assets=(v.assets||[]).filter(a=>a.identity_id===candidate&&a.kind==='resume'&&a.status==='available');
  const options=assets.map(a=>[a.id,(a.provenance?.filename||a.storage_ref.split('/').pop())+' · '+a.version]);
  const selected=$('queue-resume').value||((q.selection?.identity_id===candidate)?q.selection?.resume_asset_id:null);
  choice('queue-resume',options,selected);
 }
 if($('dispatcher-status'))$('dispatcher-status').textContent=!q.installed?'Queue upgrade required: restart with the current queue dashboard launcher.':
  `${q.worker_online?'Worker online':'Worker offline — start the JobBot queue service'} · ${q.ready_count??q.counts?.queued??0} ready · ${q.scheduled_count||0} scheduled retries · ${q.counts?.dispatched||0} in progress · Automatic queue ${q.enabled?'on':'paused'}. Active jobs are picked up automatically, one application at a time.`;
 if($('application-schedule'))$('application-schedule').textContent=
  `${q.counts?.dispatched?'An application is running. The next ready job follows after it finishes. ':''}`+
  `${q.enabled?`Next application check: ${q.next_automatic_at?stamp(q.next_automatic_at):'worker’s next check'}.`:'Automatic applications are paused; Apply now or Run next queued job can start work immediately.'}`+
  `${q.ready_count===0&&q.next_job_at?` Next scheduled retry: ${stamp(q.next_job_at)}.`:''} Up to 6 attempts: 4 in the first 24 hours, then 2 the next day. Targets: 0, 2, 4, 6, 24 and 28 hours; busy or long runs move later. After 6 attempts, review the failure reason.`;
 if($('queue-toggle'))$('queue-toggle').textContent=q.enabled?'Pause automatic queue':'Enable automatic queue';
 // The local queue uses Hermes' configured model and the runtime's actual workspace.
 // Do not imply that legacy model/browser controls can change that configuration.
 for(const id of ['main-model-picker','main-effort-picker','browser-profile','main-browser-mode']){
  const label=$(id)?.closest?.('label');if(label)label.hidden=!!v.local_runtime?.workspaces?.length;
 }
}
function canQueueAnswers(group){return group.disposition!=='canceled'&&!group.pending_count&&!['applied','already_applied'].includes(group.status)&&group.retry?.state!=='queued';}
function answerError(error){return ({unanswered_questions:'Answer every required question before queueing a retry.',answer_revision_conflict:'This answer changed elsewhere. Refresh and review the latest saved answer.',question_changed:'The employer changed this question. Review its current choices.',owned_elsewhere:'Save your answers now; queue a retry after the current application closes.',reconciliation_required:'The previous browser must finish closing before another attempt can start.',already_applied:'This application was already submitted.'})[error.message]||error.message;}
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
 const groups=(v.answer_queue?.groups||[]).filter(g=>g.disposition!=='canceled');
 const pending=groups.reduce((count,g)=>count+g.pending_count,0);
 $('answer-count').textContent=pending?`(${pending})`:'';
 $('queue-answered-batch').disabled=!groups.some(canQueueAnswers);
 const key=JSON.stringify(groups);if(key===state.answerKey)return;state.answerKey=key;
 $('answer-groups').replaceChildren();
 if(!groups.length){$('answer-groups').append(el('p','No application questions are waiting for you.','answer-empty'));return;}
 for(const group of groups){
  const card=el('article',undefined,'answer-application');
  const heading=el('div',undefined,'section-title');
  const title=el('h3');title.append(link(group.url,postingLabel(group)));heading.append(title);
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
  const retry=el('button','Save and queue retry','primary');retry.type='button';retry.disabled=['applied','already_applied'].includes(group.status);retry.onclick=()=>saveAnswerGroup(group,true);actions.append(save,retry);card.append(actions);
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
 rememberProgress($('focused-context'));$('focused-context').replaceChildren();const focused=r.focused_context;
 if(focused){
  $('focused-context').append(el('p',focused.is_active?'Current job':'Last completed job'),postingHeading(focused.job));
  const progress=renderProgress(focused.progress,'focus:'+focused.attempt_id),debug=progress.querySelector('.debug-details');
  debug.append(el('p',`Page: ${focused.page||'Unknown'} · Activity: ${focused.activity||'Unknown'}`),el('pre',JSON.stringify(focused.worker_metadata,null,2)));
  if(focused.latest_unresolved_issue)debug.append(el('p',focused.latest_unresolved_issue));$('focused-context').append(progress);
 }
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
 if(state.settingsVersion===s.version)return;state.settingsVersion=s.version;
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
 const box=$('setting-fields');box.replaceChildren();const discoveryBox=$('discovery-setting-fields');discoveryBox?.replaceChildren();
 const discoveryLabels={discovery_batch_size:'Maximum jobs per discovery run',discovery_interval_hours:'Discover jobs every (hours)'};
 for(const [key,value]of Object.entries(s.values)){const label=el('label',discoveryLabels[key]||key.replaceAll('_',' '));let input;
  if(s.supported?.[key]){input=el('select');for(const x of s.supported[key]){const o=el('option',x);o.value=x;input.append(o);}input.value=value;}
  else {input=el('input');if(typeof value==='boolean'){input.type='checkbox';input.checked=value;}else if(typeof value==='number'){input.type='number';input.value=value;const range=s.budget_ranges?.[key];if(range){input.min=range[0];input.max=range[1];}}else{input.type='text';input.value=Array.isArray(value)?value.join(', '):(value??'');}}
  if(key==='discovery_batch_size'){input.min=1;input.max=100;input.step=1;}
  if(key==='discovery_interval_hours'){input.min=1;input.max=168;input.step='any';}
  input.dataset.setting=key;input.dataset.kind=Array.isArray(value)?'list':(value===null?'nullable':typeof value);label.append(input);(discoveryLabels[key]&&discoveryBox?discoveryBox:box).append(label);
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

async function loadAttempt(id){state.attempt=id;try{const report=await api('attempt_report',{attempt_id:id});const a=report.attempt,t=report.timing;const loc=postingLabel(a);$('attempt-summary').textContent=`Attempt ${id}${loc?' · '+loc:''} · ${a.outcome||'active'} · ${duration(t.wall_seconds)} wall time · ${stamp(a.started_at)} → ${stamp(a.completed_at)}`;rememberProgress($('events'));$('events').replaceChildren(postingHeading(a));const projected=renderProgress(report.progress,'attempt:'+id);const debug=projected.querySelector('.debug-details');$('events').append(projected);
 const reasonText=a.failure_reason||report.failure_reason;
 if(reasonText){
  const p=el('p',undefined,'attempt-failure-prominent');
  const strong=el('strong','Reason: ');
  p.append(strong,document.createTextNode(reasonText));
  $('events').append(p);
 }
 debug.append(el('p',`Observed coverage ${duration(t.observed_union_seconds)}; unattributed ${duration(t.unattributed_seconds)}. Tool ${duration(t.category_seconds.tool)}; model ${duration(t.category_seconds.model)}. ${t.uncertainty?'Some timing is uncertain.':''}`),el('p',t.overlap_note));if(a.profile_hash)debug.append(el('p',`Attempt profile hash: ${a.profile_hash}`,'mono'));
 const table=el('table'),body=el('tbody');for(const phase of report.phases){const r=el('tr');r.append(el('td',phase.phase),el('td',duration(phase.duration_seconds)));body.append(r);}table.append(body);debug.append(table);
 if(report.fields&&Object.keys(report.fields).length){
  const fTable=el('table'),fBody=el('tbody');
  fBody.append(el('tr',undefined,undefined,[el('th','Field'),el('th','Elapsed'),el('th','Actions'),el('th','Status')]));
  for(const [k,f] of Object.entries(report.fields)){
   fBody.append(el('tr',undefined,undefined,[el('td',f.field_key),el('td',f.elapsed_seconds!=null?duration(f.elapsed_seconds):'unknown'),el('td',String(f.action_count)),el('td',f.verified?'verified':'unverified')]));
  }
  fTable.append(fBody);debug.append(el('h4','Field Telemetry'),fTable);
 }
 if(report.simplify&&report.simplify.runs_count){
  const s=report.simplify;
  debug.append(el('p',`Simplify runs: ${s.runs_count} · Total duration: ${duration(s.total_duration_seconds)}${s.fallback_reasons.length?' · Fallback reasons: '+s.fallback_reasons.join(', '):''}`));
 }
 if(report.problems&&report.problems.length){
  const pTable=el('table'),pBody=el('tbody');
  pBody.append(el('tr',undefined,undefined,[el('th','Category'),el('th','Field'),el('th','Fallback Reason'),el('th','Source'),el('th','Status'),el('th','Resolution')]));
  for(const p of report.problems){
   pBody.append(el('tr',undefined,undefined,[el('td',p.category||'-'),el('td',p.field_key||'-'),el('td',p.fallback_reason||'-'),el('td',p.source||'native'),el('td',p.status||'-'),el('td',p.resolution||'-')]));
  }
  pTable.append(pBody);debug.append(el('h4','Problems & Recoveries'),pTable);
 }
 for(const e of report.timeline){const row=el('details',undefined,'event');row.append(el('summary',`${stamp(e.observed_at)} · ${e.payload.activity||e.payload.evidence||e.event_type} · ${duration(e.duration_seconds)}${e.stale?' · late metadata':''}`),el('pre',JSON.stringify(e.payload,null,2)));debug.append(row);}if(!report.timeline.length)debug.append(el('p','No events recorded.'));}catch(e){notice(e.message,true);}}

async function refresh(){if(!state.instance||state.busy)return;state.busy=true;try{const v=await api('view',state.run?{run_id:state.run}:{});state.view=v;$('instance').textContent=`Instance ${v.health.instance_id} · DB ${v.health.db_path}`;$('mode').textContent=v.settings.values.mode+' / '+v.settings.values.submission_mode;$('mode').dataset.state=v.settings.values.mode;
 choice('candidate',v.candidates.filter(c=>c.state==='active').map(c=>[c.id,c.email]),$('candidate').value||v.dispatch_queue?.selection?.identity_id);
 if($('browser-profile')&&!$('browser-profile').value.trim()){
  $('browser-profile').value=v.current_run?.browser_profile||v.runs?.[0]?.browser_profile||'operator-chrome';
 }
 renderQueue(v);renderRun(v);renderAccounts(v);renderResources(v);renderSettings(v.settings);await renderProfile(v);$('health').textContent=JSON.stringify(v.health,null,2);if(state.attempt)await loadAttempt(state.attempt);
 }catch(e){notice(e.message,true);}finally{state.busy=false;}}
function tab(name){document.querySelectorAll('.tab').forEach(n=>n.hidden=n.id!=='tab-'+name);document.querySelectorAll('[data-tab]').forEach(n=>n.classList.toggle('active',n.dataset.tab===name));}
$('reconnect').onclick=()=>location.reload();
$('refresh').onclick=refresh;document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
function filterJobs(){rememberProgress($('queue-rows'));state.queueKey=null;state.selected.clear();if(state.view)renderQueue(state.view);}
$('job-filter').onchange=filterJobs;$('job-search').oninput=filterJobs;
$('select-unfinished').onclick=()=>{state.selected=new Set(visibleJobs(state.view).filter(unfinished).map(j=>j.id));state.queueKey=null;renderQueue(state.view);};
$('select-visible').onclick=()=>{state.selected=new Set(visibleJobs(state.view).filter(j=>j.disposition==='canceled').map(j=>j.id));state.queueKey=null;renderQueue(state.view);};
$('clear-selection').onclick=()=>{state.selected.clear();state.queueKey=null;renderQueue(state.view);};
async function changeDisposition(disposition){
 const job_ids=state.view.jobs.filter(j=>state.selected.has(j.id)&&(disposition==='canceled'?unfinished(j):j.disposition==='canceled')).map(j=>j.id);
 if(!job_ids.length)return;
 try{
  const result=await api('set_job_disposition',{job_ids,disposition,reason:disposition==='canceled'?$('cancel-reason').value:''});
  state.selected.clear();state.queueKey=null;
  notice(disposition==='canceled'?`${result.jobs.length} job(s) canceled. History and portal accounts kept.${result.skipped_job_ids?.length?' Submitted or already canceled jobs were left unchanged.':''}${result.stop_requested_run_ids.length?' Stop requested for current work; browser shutdown is pending.':''}`:`${result.jobs.length} job(s) restored. Select and queue them when ready.`);
  await refresh();
 }catch(error){notice(error.message,true);}
}
$('cancel-selected').onclick=()=>changeDisposition('canceled');$('restore-selected').onclick=()=>changeDisposition('active');
if($('candidate'))$('candidate').onchange=()=>{if($('queue-resume'))$('queue-resume').value='';renderDispatcher(state.view);};
if($('queue-answered-batch'))$('queue-answered-batch').onclick=async()=>{
 try{const candidates=new Map();for(const group of state.view?.answer_queue?.groups||[]){if(!canQueueAnswers(group))continue;const jobs=candidates.get(group.identity_id)||[];jobs.push(group.job_id);candidates.set(group.identity_id,jobs);}
  let count=0;for(const [identity_id,job_ids] of candidates){await api('queue_answer_retries',{identity_id,job_ids});count+=job_ids.length;}
  notice(`${count} answered application${count===1?'':'s'} queued for the next batch.`);await refresh();
 }catch(error){notice(answerError(error),true);}
};
$('intake-form').onsubmit=async e=>{e.preventDefault();try{const job=await api('intake',{url:$('job-url').value,company:$('job-company').value,title:$('job-title').value,source_type:'manual',source_id:crypto.randomUUID(),producer:'dashboard'});
 $('job-search').value='';state.selected.clear();state.queueKey=null;
 if(job.disposition==='canceled'){$('job-filter').value='canceled';notice('This job is already saved as canceled. Restore it here if you want to pursue it again.');}
 else if(submitted(job)){$('job-filter').value='submitted';notice('This job is already saved as submitted.');}
 else{$('job-filter').value='active';state.selected.add(job.id);notice('Job saved and selected. Choose Queue selected to apply.');}
 $('intake-form').reset();await refresh();}catch(err){notice(err.message,true);}};
$('mark-ready').onclick=async()=>{try{if(!state.selected.size)throw Error('Select at least one job.');for(const id of state.selected)await api('eligibility',{job_id:id,decision:'ready',reason:'Explicit operator approval'});notice('Selected eligibility recorded.');await refresh();}catch(e){notice(e.message,true);}};
$('request-run').onclick=async()=>{try{if(!state.selected.size||!$('candidate').value||!$('browser-profile').value.trim())throw Error('Select jobs, candidate and exact browser profile.');const r=await api('request_run',{request_id:crypto.randomUUID(),job_ids:[...state.selected],identity_id:$('candidate').value,browser_profile:$('browser-profile').value.trim()});state.run=r.id;state.attempt=null;notice('Run requested; waiting for worker acceptance.');tab('run');await refresh();}catch(e){notice(e.message,true);}};
if($('start-application-btn')){$('start-application-btn').onclick=async()=>{try{
 if(state.view?.local_runtime?.workspaces?.length){
  if(!state.selected.size)throw Error('Select at least one job.');
  const identity_id=$('candidate').value;
  const asset=(state.view.assets||[]).find(a=>a.id===$('queue-resume').value&&a.identity_id===identity_id&&a.kind==='resume'&&a.status==='available');
  if(!asset)throw Error('Choose a candidate with a registered resume.');
  const submission_mode=$('main-submission-mode').value;
  if(submission_mode!==state.view.settings.values.submission_mode)await api('configure',{changes:{submission_mode,mode:submission_mode==='submit'?'pilot':'development'},expected_version:state.settingsVersion});
  await api('queue_enqueue',{job_ids:[...state.selected],identity_id,resume_asset_id:asset.id,request_id:crypto.randomUUID(),retry:true,producer:'dashboard',enqueue_origin:'manual_retry'});
  state.selected.clear();notice('Retry requested. Applications run one at a time; existing scheduled retries keep their due time.');await refresh();return;
 }
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
if($('queue-run-next'))$('queue-run-next').onclick=async()=>{try{const q=await api('queue_control',{command:'run_next'});notice(runNextMessage(q));await refresh();}catch(e){notice(e.message,true);}};
if($('queue-toggle'))$('queue-toggle').onclick=async()=>{try{await api('queue_control',{command:state.view?.dispatch_queue?.enabled?'pause':'resume'});await refresh();}catch(e){notice(e.message,true);}};
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
