// LinkedIn form selectors/flow adapted from GodsScion/Auto_job_applier_linkedIn
// runAiBot.py at e0b2401a7a7b333eab0b518e80be5285c3ee85c5.
// Copyright (c) 2024-2026 Sai Vignesh Golla, MIT; see third_party/godsscion-linkedin.
(args, form) => {
 const visible=e=>!!e&&e.isConnected&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
 const text=e=>(e?.innerText||e?.textContent||'').replace(/\s+/g,' ').trim();
 const enabled=e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true';
 const result=form({method:'observe'}),scope=window.__jobbotFormScope;
 const ref=e=>{
  const current=result.inventory.find(item=>scope.inventory.get(item.ref)===e);
  if(current)return current.ref;
  for(const [key,node] of scope.inventory)if(node===e)return key;
  const key='form:'+crypto.randomUUID();scope.inventory.set(key,e);return key;
 };
 const control=e=>e?{ref:ref(e),enabled:enabled(e),label:text(e)||e.getAttribute('aria-label')||''}:{};
 const dialogs=[...document.querySelectorAll('.jobs-easy-apply-modal,[data-test-modal-id="easy-apply-modal"],[role="dialog"]')]
  .filter(e=>visible(e)&&(e.matches('.jobs-easy-apply-modal,[data-test-modal-id="easy-apply-modal"]')||e.querySelector('[data-test-form-element]')));
 const modal=dialogs.length===1?dialogs[0]:null;
 const details=document.querySelector('.jobs-search__job-details--container,.jobs-details,.job-view-layout')||document.querySelector('main')||document.body;
 const assigned=e=>{
  const card=e.closest('[data-job-id],[data-occludable-job-id]');
  return !card||(card.getAttribute('data-job-id')||card.getAttribute('data-occludable-job-id'))===args.job_id;
 };
 const applicationButtons=[...details.querySelectorAll('#jobs-apply-button-id,.jobs-apply-button,a[href*="openSDUIApplyFlow=true"]')].filter(e=>visible(e)&&assigned(e));
 const easy=applicationButtons.filter(e=>/\beasy apply\b/i.test(text(e)+' '+(e.getAttribute('aria-label')||''))||/^(?:continue|resume) (?:your )?application$/i.test(text(e))||
  new URL(e.href||location.href,location.href).searchParams.get('openSDUIApplyFlow')==='true');
 const external=applicationButtons.filter(e=>/^apply\b/i.test(text(e)||e.getAttribute('aria-label')||'')&&!easy.includes(e)&&e.href&&(()=>{
  try {let u=new URL(e.href,location.href);
   if((u.hostname==='linkedin.com'||u.hostname.endsWith('.linkedin.com'))&&(/\/redir\//.test(u.pathname)||u.pathname==='/safety/go'))u=new URL(u.searchParams.get('url'));
   return u.protocol==='https:'&&u.hostname!=='linkedin.com'&&!u.hostname.endsWith('.linkedin.com');
  } catch {return false;}
 })());
 const applied=[...details.querySelectorAll('.jobs-s-apply,[data-test-job-applied],.jobs-apply-button--applied,.jobs-details-top-card__apply-error')]
  .find(e=>visible(e)&&/^(?:Applied\b|You (?:have |already )?applied\b|Application (?:was )?sent\b)/i.test(text(e))&&(()=>{
   const card=e.closest('[data-job-id],[data-occludable-job-id]');
   return !card||(card.getAttribute('data-job-id')||card.getAttribute('data-occludable-job-id'))===args.job_id;
  })());
 const kind=modal&&assigned(modal)||easy.length===1?'easy_apply':external.length===1?'external':'unknown';
 const route={kind,modal:!!modal,apply:control(easy.length===1?easy[0]:external.length===1?external[0]:null),
  already_applied:applied?text(applied).slice(0,400):null,questions:[],file_inputs:[],resumes:[]};
 if(modal){
  const buttons=[...modal.querySelectorAll('button,[role="button"]')].filter(visible);
  result.native={};
  const locators={continue:e=>e.getAttribute('aria-label')==='Continue to next step'||/^Next(?: step)?$/i.test(text(e)),
   review:e=>e.getAttribute('aria-label')==='Review your application'||/^Review$/i.test(text(e)),
   submit:e=>e.getAttribute('aria-label')==='Submit application'||/^Submit application$/i.test(text(e))};
  for(const [name,match] of Object.entries(locators)){
   const found=buttons.filter(match);if(found.length===1)result.native[name]=control(found[0]);
  }
  const seen=new Set();
  for(const item of result.inventory){
   const el=scope.inventory.get(item.ref);
   if(!el||!modal.contains(el)||item.private||el.type==='file')continue;
   const q=form({method:'question',ref:item.ref});
   if(q.reason)continue;
   const key=JSON.stringify([q.field,q.question,q.kind,q.options.map(o=>[o.value,o.label])]);
   if(seen.has(key))continue;seen.add(key);
   route.questions.push({...q,ref:item.ref,enabled:item.enabled});
  }
  // LinkedIn hides its native file input behind an Upload resume button.
  route.file_inputs=[...modal.querySelectorAll('input[type="file"]')].filter(enabled).map(e=>({ref:ref(e),name:e.name,accept:e.accept,
   files:[...e.files].map(f=>({name:f.name,size:f.size}))}));
  const cards=[...modal.querySelectorAll('.jobs-document-upload-redesign-card__container,[data-test-document-upload-card],.jobs-document-upload__container')].filter(visible);
  route.resumes=cards.map(e=>({text:text(e).slice(0,500),selected:!!e.querySelector('input:checked,[aria-checked="true"]')||e.getAttribute('aria-checked')==='true'||e.classList.contains('jobs-document-upload-redesign-card__container--selected'),
   control:control(e.querySelector('input[type="radio"],[role="radio"]'))}));
  result.blocking_errors=[...modal.querySelectorAll('[role="alert"],[aria-invalid="true"],.artdeco-inline-feedback--error')].filter(visible)
   .filter(e=>e.getAttribute('aria-invalid')==='true'||e.classList.contains('artdeco-inline-feedback--error')||
    /required|invalid|error|failed|unable|must (?:select|enter|provide)|please (?:enter|select|provide)/i.test(text(e)))
   .map(e=>(text(e)||e.getAttribute('aria-label')||'Invalid field').slice(0,300));
  result.inventory=result.inventory.filter(item=>modal.contains(scope.inventory.get(item.ref)));
 }
 const structure=JSON.stringify([text(modal?.querySelector('h2,h3')),route.questions.map(q=>[q.field,q.question,q.kind,q.options.map(o=>[o.value,o.label])]),
  Object.keys(result.native),route.file_inputs.map(f=>[f.name,f.accept])]);
 if(scope.linkedinStructure!==structure){scope.linkedinStructure=structure;scope.linkedinSignature='linkedin:'+crypto.randomUUID();}
 scope.linkedinAutofillShape={headings:[modal?text(modal.querySelector('h2,h3')):'posting'],
  fields:route.questions.map(q=>JSON.stringify([q.field,q.question,q.kind])).concat(route.file_inputs.map(f=>JSON.stringify([f.name,f.accept])))};
 result.page_signature=scope.page_signature=scope.linkedinSignature;
 route.step=modal?(result.native.submit?'review':'easy_apply'):'posting';
 // Shared pointer/manual recovery uses the generic form scope's step.
 result.step='form';
 result.linkedin=route;
 result.auth=!!document.querySelector('input[type="password"]')||/\/login|\/checkpoint|\/authwall/.test(location.pathname);
 return result;
}
