// Generic form inventory and value operations for the existing owned CDP target.
(args) => {
 const visible=e=>!!e&&e.isConnected&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
 const native=e=>!e.closest('.simplify-jobs-shadow-root,[id*="simplify"]');
 const text=e=>(e?.innerText||e?.textContent||'').replace(/\s+/g,' ').trim();
 const linkedin=location.hostname==='linkedin.com'||location.hostname.endsWith('.linkedin.com');
 const greenhouse=/(^|\.)greenhouse\.io$/.test(location.hostname)||new URL(location.href).searchParams.has('gh_jid')||!!window.__jobbotGreenhouseOwner;
 const liModal=linkedin?[...document.querySelectorAll('.jobs-easy-apply-modal,[data-test-modal-id="easy-apply-modal"],[role="dialog"]')]
  .find(e=>visible(e)&&(e.matches('.jobs-easy-apply-modal,[data-test-modal-id="easy-apply-modal"]')||e.querySelector('[data-test-form-element]'))):null;
 const liGroup=e=>liModal?.contains(e)?e.closest('[data-test-form-element]'):null;
 const liQuestion=e=>text(liGroup(e)?.querySelector('legend,[data-test-form-builder-radio-button-form-component__title],label'));
 const nearbyLabel=e=>{
  for(let p=e.parentElement;p&&p!==document.body;p=p.parentElement){
   if(p.matches('form,fieldset,section,[role="dialog"]'))break;
   const controls=p.querySelectorAll('input:not([type="hidden"]),textarea,select,[role="combobox"],[role="checkbox"]');
   if(controls.length!==1||controls[0]!==e)break;
   const labels=[...p.querySelectorAll('label')].filter(n=>!n.htmlFor||n.htmlFor===e.id);
   if(labels.length===1)return text(labels[0]);
  }
  return '';
 };
 const label=e=>e.getAttribute('aria-label')||[...(e.labels||[])].map(text).join(' ')||
  (e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)).filter(Boolean).map(text).join(' ')||
  text(e.closest('label'))||nearbyLabel(e)||e.getAttribute('placeholder')||'';
 const nodes=()=>[...(liModal||document).querySelectorAll('input:not([type="hidden"]),textarea,select,button,a,[role="button"],[role="checkbox"],[role="radio"],[role="combobox"]')].filter(e=>visible(e)&&native(e));
 const enabled=e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true';
 const checked=e=>['checkbox','radio'].includes(e.getAttribute('role'))?e.getAttribute('aria-checked')==='true':!!e.checked;
 const descriptor=e=>({tag:e.tagName,type:e.type||'',role:e.getAttribute('role')||'',name:e.name||'',
  label:label(e).slice(0,300),text:/^(BUTTON|A)$/.test(e.tagName)||e.getAttribute('role')==='button'?text(e).slice(0,200):'',
  automation_id:e.getAttribute('data-automation-id')||'',...(greenhouse?{id:e.id||'',section:text(e.closest('fieldset,section,[role="group"]')?.querySelector('legend,h1,h2,h3'))}:{}),...(liGroup(e)?{question:liQuestion(e)}:{})});
 const key=e=>JSON.stringify(descriptor(e));
 let scope=window.__jobbotFormScope;
 if(!scope||scope.url!==location.href)scope={url:location.href,keys:new Map(),inventory:new Map(),controls:new Map(),bindings:new Map()};
 scope.page_signature=args.page_signature||scope.page_signature||location.origin+location.pathname;
 scope.step='form';
 window.__jobbotFormScope=scope;
 if(greenhouse&&!scope.structureObserver){
  scope.structureEpoch=0;
  const fieldNode=n=>n.nodeType===1&&(n.matches('input:not([type="hidden"]),select,textarea,[role="combobox"],[role="checkbox"],[role="radio"]')||
   !!n.querySelector('input:not([type="hidden"]),select,textarea,[role="combobox"],[role="checkbox"],[role="radio"]'));
  scope.structureObserver=new MutationObserver(records=>{
   if(records.some(r=>native(r.target)&&!r.target.closest?.('[role="listbox"],[role="option"]')&&
      (r.type==='attributes'||[...r.addedNodes,...r.removedNodes].some(fieldNode))))scope.structureEpoch++;
  });
  scope.structureObserver.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['required','aria-required','name','id']});
 }
 const remember=e=>{
  const k=key(e),matches=nodes().filter(n=>key(n)===k);
  let ref=scope.verificationElementRefs?.get(e)||(matches.length===1?scope.keys.get(k):null);
  if(!ref)ref='form:'+crypto.randomUUID();
  if(matches.length===1)scope.keys.set(k,ref);
  scope.inventory.set(ref,e);scope.bindings.set(ref,k);return ref;
 };
 const codePattern=/\botp\b|one[\s_-]?time|(?:security|verification|authentication)[\s_-]*code/i;
 const privateInputs=new Set(),groups=[];
 scope.verificationKeys=scope.verificationKeys||new WeakMap();
 scope.verificationElementRefs=scope.verificationElementRefs||new WeakMap();
 scope.verificationRequests=scope.verificationRequests||new Map();
 scope.verificationRecords=new Map();
 const inputs=nodes().filter(e=>e.tagName==='INPUT'&&!['password','email','tel','file','checkbox','radio','submit'].includes(e.type));
 const roots=new Set();
 for(const input of inputs){
  let root=null;
  if(codePattern.test([input.name,input.id,input.autocomplete,label(input)].join(' ')))root=input;
  if(input.maxLength===1||root){
   for(let candidate=input.parentElement;candidate&&candidate!==document.body;candidate=candidate.parentElement){
    const content=text(candidate),members=[...candidate.querySelectorAll('input')].filter(e=>inputs.includes(e));
    if(content.length>2000)break;
    if(codePattern.test(content)&&members.length>=1&&members.length<=12&&
       (members.length===1||members.every(e=>e.maxLength===1))){root=candidate;break;}
    if(candidate.matches('form,section'))break;
   }
  }
  if(root)roots.add(root);
 }
 for(const root of roots){
  const members=root.tagName==='INPUT'?[root]:[...root.querySelectorAll('input')].filter(e=>inputs.includes(e));
  if(members.some(e=>privateInputs.has(e)))continue;
  members.forEach(e=>privateInputs.add(e));
  const nearby=text(root.tagName==='INPUT'?root.parentElement:root).slice(0,2000);
  const length=members.length>1?members.length:members[0].maxLength>0?members[0].maxLength:null;
  let challenge_ref=scope.verificationKeys.get(root);
  if(!challenge_ref){challenge_ref='verification:'+crypto.randomUUID();scope.verificationKeys.set(root,challenge_ref);}
  const kind=/(?:e-?mail(?:ed)?|inbox).{0,100}(?:code|sent)|(?:code|sent).{0,100}(?:e-?mail|inbox)/i.test(nearby)?'email_code':'verification_code';
  // Unlabelled segments have identical descriptors. Preserve each exact node's
  // opaque ref while it remains in this group; replacing it requires fresh refs.
  const refs=members.map(e=>{
   let ref=scope.verificationElementRefs.get(e);
   if(!ref){ref='form:'+crypto.randomUUID();scope.verificationElementRefs.set(e,ref);}
   scope.inventory.set(ref,e);return ref;
  }),requested_at=scope.verificationRequests.get(challenge_ref)||null;
  const surface=root.closest('form,[role="dialog"]')||root.parentElement||root;
  const resend=nodes().filter(e=>surface.contains(e)&&/^(?:resend(?: (?:security |verification )?(?:code|email))?|send (?:a |new |another )?(?:code|email)|request (?:a )?new code)$/i.test(text(e)));
  const complete=members.every(e=>!!e.value.trim());
  const group={challenge_ref,kind,length,refs,requested_at,complete,...(resend.length===1?{resend_ref:remember(resend[0])}:{})};groups.push(group);
  scope.verificationRecords.set(challenge_ref,{...group,root,elements:members});
 }
 const privateControl=e=>e.type==='password'||privateInputs.has(e)||/^(INPUT|TEXTAREA)$/.test(e.tagName)&&codePattern.test([e.name,e.id,e.autocomplete,label(e)].join(' '));
 scope.privateControl=privateControl;
 if(args.method==='verification')return {groups};
 const requiredEvidence=e=>[e.required?'required':null,e.getAttribute('aria-required')==='true'?'aria-required':null,
  /\*\s*$/.test(label(e))||/\*\s*$/.test(liQuestion(e))?'label_asterisk':null,
  e.getAttribute('data-val-required')?'required_validator':null].filter(Boolean);
 const required=e=>requiredEvidence(e).length>0;
 const choice=e=>e.tagName==='SELECT'||e.getAttribute('role')==='combobox'||['listbox','menu','true'].includes(e.getAttribute('aria-haspopup'));
 const widget=e=>{
  let found=e;
  for(let p=e.parentElement;p&&p!==document.body;p=p.parentElement){
   if(p.matches('form,fieldset,section,[role="dialog"]'))break;
   const controls=[...p.querySelectorAll('input[role="combobox"],[role="combobox"],select')];
   if(controls.length!==1||controls[0]!==e)break;
   found=p;
  }
  return found;
 };
 const validation=e=>{
  const ids=((e.getAttribute('aria-errormessage')||'')+' '+(e.getAttribute('aria-describedby')||'')).split(/\s+/).filter(Boolean);
  const errors=ids.map(id=>document.getElementById(id)).filter(n=>visible(n)&&text(n)&&
   ((e.getAttribute('aria-errormessage')||'').split(/\s+/).includes(n.id)||n.matches('[role="alert"],.error,.field-error,[class*="error"]')));
  const nativeInvalid=e.willValidate&&e.validity&&!e.validity.valid&&!(choice(e)&&e.validity.valueMissing&&selectedValue(e));
  const rejected=e.getAttribute('aria-invalid')==='true'||!!nativeInvalid||errors.length>0;
  return {rejected,aria_invalid:e.getAttribute('aria-invalid')==='true',associated_error:errors.length>0};
 };
 const meaningful=value=>!!value&&!/^(?:select(?: one| an option)?|please select|choose(?: an? option)?)[.\s…]*$/i.test(value);
 const selectedValue=e=>{
  const workday=window.__jobbotWorkdayScope;
  if(workday?.url===location.href&&workday.selectedValue)return workday.selectedValue(e);
  if(e.tagName==='SELECT'){
   if(e.multiple)return [...e.selectedOptions].filter(o=>o.value&&meaningful(o.text)).map(o=>o.text).join('; ');
   const value=e.selectedOptions[0]?.text||'';
   return e.value&&meaningful(value)?value:'';
  }
  if(choice(e)){
   const value=e.getAttribute('aria-valuetext')||(!['INPUT','TEXTAREA'].includes(e.tagName)?text(e):'');
   if(meaningful(value))return value;
   // LinkedIn leaves a committed typeahead choice in the input. A typed filter
   // alone is insufficient: retain only a dispatched observed option whose menu
   // closed and whose exact input value still matches, on this same DOM node.
   const receipt=linkedin&&scope.linkedinSelections?.get(e);
   if(receipt&&e.isConnected&&e.value===receipt.label&&e.getAttribute('aria-expanded')!=='true'&&
      !receipt.menu?.getClientRects().length)return receipt.label;
   // React-select retains its committed label beside an empty/filter input.
   // Stay in the smallest ancestor containing this one control, never in a
   // portalled menu or an adjacent field. Highlighted options are not answers.
   for(let root=e.parentElement;root&&root!==document.body;root=root.parentElement){
    if(root.matches('form,fieldset,section,[role="dialog"]'))break;
    const controls=[...root.querySelectorAll('input[role="combobox"],[role="combobox"],select')];
    if(controls.length!==1||controls[0]!==e)break;
    const selected=[...root.querySelectorAll('[class*="single-value"],[class*="singleValue"],[class*="multi-value__label"],[class*="multiValueLabel"],[data-selected-value]')]
     .filter(n=>visible(n)&&!n.closest('[role="option"],[role="menuitem"],[role="listbox"]'));
    const values=[...new Set(selected.map(text).filter(meaningful))];
    if(values.length===1)return values[0];
    if(values.length>1)return values.join('; ');
   }
  }
  return '';
 };
 const describe=e=>({...descriptor(e),ref:remember(e),enabled:enabled(e),required:required(e),required_evidence:requiredEvidence(e),private:privateControl(e),validation:validation(e),
  present:choice(e)?!!selectedValue(e):!!e.value,...(selectedValue(e)?{selected_value:selectedValue(e)}:{}),checked:['checkbox','radio'].includes(e.type)||e.getAttribute('role')==='checkbox'?checked(e):undefined,
  ...(e.tagName==='SELECT'?{options:[...e.options].map(o=>({value:o.value,label:o.text,disabled:o.disabled||o.parentElement.disabled}))}:{}),
  expanded:e.getAttribute('aria-expanded'),haspopup:e.getAttribute('aria-haspopup')});
 const metadata=()=>{
  const postings=[];
  const visit=value=>{
   if(Array.isArray(value)){value.forEach(visit);return;}
   if(!value||typeof value!=='object')return;
   if([value['@type']].flat().includes('JobPosting'))postings.push(value);
   if(value['@graph'])visit(value['@graph']);
  };
  for(const script of document.querySelectorAll('script[type="application/ld+json"]')){
   try{visit(JSON.parse(script.textContent));}catch{}
  }
  if(postings.length===1){
   const posting=postings[0],company=posting.hiringOrganization?.name,title=posting.title;
   if(typeof company==='string'&&typeof title==='string'&&company.trim()&&title.trim()){
    let url;try{url=new URL(posting.url||location.href,location.href).href;}catch{return {};}
    return {company:company.trim().slice(0,200),title:title.trim().slice(0,300),url,source:'employer_posting'};
   }
  }
  if(postings.length>1)return {};
  const cards=new Map();
  for(const host of document.querySelectorAll('.simplify-jobs-shadow-root')){
   for(const e of (host.shadowRoot||host).querySelectorAll('button,[role="button"]')){
    if(!visible(e))continue;
    const lines=(e.innerText||e.textContent||'').split(/\r?\n/).map(t=>t.trim()).filter(Boolean);
    if(lines.length>=2&&/\s[·•]\s*Updated on\b/i.test(lines[1])){
     const company=lines[1].split(/\s[·•]\s*Updated on\b/i)[0].trim();
     cards.set(lines[0]+'|'+company,{title:lines[0],company,url:location.href,source:'simplify_job_card'});
    }
   }
  }
  return cards.size===1?[...cards.values()][0]:{};
 };
 if(args.method==='metadata')return metadata();
 if(args.method==='resume_widget'){
  const names=[...document.querySelectorAll('label,legend,h2,h3,h4,[id*="resume"],[class*="file-upload"]')]
   .filter(e=>native(e)&&visible(e)&&/^(?:resume(?:\s*\/\s*cv)?|cv)(?:\s*\*)?$/i.test(text(e)));
  const roots=new Set();
  for(const name of names){
   for(let root=name.parentElement;root&&root!==document.body&&!root.matches('form');root=root.parentElement){
    if(/cover letter/i.test(text(root)))break;
    if(root.querySelector('input[type="file"]')||[...root.querySelectorAll('button,[role="button"]')].some(b=>/remove|delete|^x$|^×$/i.test(label(b)||text(b)))){roots.add(root);break;}
   }
  }
  if(roots.size!==1)return {reason:'resume_widget_unresolved'};
  const root=[...roots][0],inputs=[...root.querySelectorAll('input[type="file"]')].filter(enabled),
   remove=[...root.querySelectorAll('button,[role="button"],a')].filter(e=>visible(e)&&enabled(e)&&/remove|delete|^x$|^×$/i.test(label(e)||text(e)));
  const error=/required|attach|upload.*(?:fail|error)|invalid/i.test(text(root.querySelector('[role="alert"],.error,[class*="error"]')))||
   [...document.querySelectorAll('[role="alert"],.error,[class*="error"]')].some(e=>visible(e)&&/resume|\bcv\b/i.test(text(e))&&/required|missing|invalid|failed/i.test(text(e)));
  return {required_error:!!error,input_ref:inputs.length===1?remember(inputs[0]):null,remove_ref:remove.length===1?remember(remove[0]):null,
   files:inputs.flatMap(e=>[...e.files].map(f=>({name:f.name,size:f.size})))};
 }
 if(args.method==='observe'){
  const inventory=nodes().map(describe),controls={};
  const labels={'save and continue':'continue','continue':'continue','next':'continue','next step':'continue',
    'apply':'apply','apply now':'apply','apply for this job':'apply','apply manually':'apply','start application':'apply',
    'submit':'submit','submit application':'submit','send application':'submit'};
  for(const item of inventory){
   const kind=labels[item.text.toLowerCase()];if(!kind)continue;
   controls[kind]=controls[kind]?{enabled:false,ref:null}:{ref:item.ref,enabled:item.enabled};
  }
  const errors=[...document.querySelectorAll('[aria-invalid="true"],[role="alert"]')].filter(e=>visible(e)&&native(e))
   .filter(e=>e.getAttribute('aria-invalid')==='true'||/required|invalid|must (?:select|enter)/i.test(text(e)))
   .map(e=>(label(e)||text(e)).slice(0,180)).slice(0,8);
  return {step:'form',native:controls,inventory,blocking_errors:errors,auth:nodes().some(e=>e.type==='password'),
    page_signature:scope.page_signature,job_metadata:metadata(),verification:{groups},...(greenhouse?{greenhouse:true}:{}),
    ready_state:document.readyState,structure:JSON.stringify(inventory.filter(i=>['INPUT','SELECT','TEXTAREA'].includes(i.tag)||['combobox','checkbox','radio'].includes(i.role)).map(i=>[i.id,i.name,i.tag,i.type,i.role,i.label,i.required,i.section]))};
 }
 if(args.method==='answers'){
  const currentPage=window.__jobbotWorkdayScope?.step||args.page;
  const questionnaire=['application_questions','voluntary_disclosures','self_identify'].includes(currentPage);
  const answers=[];
  for(const e of nodes()){
   if(privateControl(e))continue;
   const type=e.type||'',role=e.getAttribute('role')||'';
   if(e.closest('form,[role="dialog"]')?.querySelector('input[type="password"]'))continue;
   if(['password','hidden','file','email','tel','submit'].includes(type))continue;
   const input=/^(INPUT|TEXTAREA|SELECT)$/.test(e.tagName);
   const choice=['checkbox','radio','combobox'].includes(role)||['listbox','menu','true'].includes(e.getAttribute('aria-haspopup'));
   if(!input&&!choice)continue;
   if((type==='radio'||role==='radio')&&!e.checked&&e.getAttribute('aria-checked')!=='true')continue;
   const ids=(e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)).filter(Boolean);
   const group=e.closest('fieldset,[role="radiogroup"]');
   const field=e.closest('[data-automation-id^="formField"],[data-automation-id="question"],[role="group"]');
   const fieldLabel=field?.querySelector('label,[data-automation-id="richText"],[data-automation-id="questionLabel"]');
   let question=liQuestion(e)||(group?.querySelector('legend')&&text(group.querySelector('legend')))||
    group?.getAttribute('aria-label')||text(fieldLabel)||ids.map(text).join(' ')||[...(e.labels||[])].map(text).join(' ')||label(e);
   const identity=question+' '+(e.name||'')+' '+(e.autocomplete||'');
   if(/password|passwd|\botp\b|token|secret|social.?security|\bssn\b|tax.?id|bank.?account|routing.?number|credit.?card|e.?mail|phone|postal|street.?address/i.test(identity))continue;
   if(!questionnaire&&!/\?|\b(?:salary|sponsorship|work authorization|consent|privacy|veteran|disability)\b/i.test(question))continue;
   let answer;
   if(type==='checkbox'||role==='checkbox')answer=checked(e)?'Yes':'No';
   else if(type==='radio'||role==='radio')answer=label(e)||e.value||text(e);
   else if(e.tagName==='SELECT'||role==='combobox'||e.getAttribute('aria-haspopup'))answer=selectedValue(e);
   else answer=/^(INPUT|TEXTAREA)$/.test(e.tagName)?e.value:text(e);
   answer=(answer||'').trim();
   if(!answer||/^(?:select(?: one)?|please select|choose(?: an? option)?)[.\s…]*$/i.test(answer))continue;
   question=question.replace(/\s+Required\s*$/i,'').replace(/\s*\*$/,'').trim();
   if(!['checkbox','radio'].includes(type)&&!['checkbox','radio'].includes(role)&&question.endsWith(' '+answer))
    question=question.slice(0,-answer.length).trim();
   if(question&&question!==answer&&!/^(?:select one|yes|no)$/i.test(question))
    answers.push({field:e.name||e.id||question,question,answer,page:currentPage||'form'});
  }
  const context=metadata();
  return {answers,context:{...context,...(context.title?{job_title:context.title}:{})}};
 }
 let owner=args.selector||args.ref?.startsWith('form:')?scope:window.__jobbotWorkdayScope;
 let el;
 if(args.selector){const found=document.querySelectorAll(args.selector);if(found.length===1)el=found[0];}
 else el=owner?.inventory?.get(args.ref)||owner?.controls?.get(args.ref);
 const saved=scope.bindings.get(args.ref);
 if((!el||!el.isConnected)&&saved){
  const matches=nodes().filter(e=>key(e)===saved);
  if(matches.length===1){el=matches[0];owner?.inventory?.set(args.ref,el);}
 }
 if(!visible(el)||!native(el)||!enabled(el))return {committed:false,reason:'control_unavailable',execution:'not_executed'};
 if(args.ref)scope.bindings.set(args.ref,key(el));
 if(el.type==='password')
  return {committed:false,reason:'use_private_credentials_helper',execution:'not_executed'};
 const value=()=>el.tagName==='SELECT'?(el.multiple?{value:[...el.selectedOptions].map(o=>o.value),label:[...el.selectedOptions].map(o=>o.text)}:{value:el.value,label:el.selectedOptions[0]?.text||''}):
  {value:choice(el)?selectedValue(el):(/^(INPUT|TEXTAREA)$/.test(el.tagName)?el.value:text(el)),
   label:choice(el)?selectedValue(el):(/^(INPUT|TEXTAREA)$/.test(el.tagName)?el.value:text(el))};
 if(args.method==='question'){
  const role=el.getAttribute('role'),group=el.closest('fieldset,[role="radiogroup"],[role="group"]');
  const question=liQuestion(el)||(owner===window.__jobbotWorkdayScope&&owner.questionText?.(el))||
   text(group?.querySelector('legend'))||group?.getAttribute('aria-label')||label(el);
  let kind=el.tagName==='SELECT'||role==='combobox'||['listbox','menu','true'].includes(el.getAttribute('aria-haspopup'))?'select':
   el.type==='checkbox'||role==='checkbox'?'check':el.type==='radio'||role==='radio'?'radio':'text';
  if(kind==='text'&&!['INPUT','TEXTAREA'].includes(el.tagName))return {reason:'question_control_unrecognized'};
  let options=[];
  if(el.tagName==='SELECT')options=[...el.options].filter(o=>!o.disabled&&!o.parentElement.disabled&&o.value!==''&&
    meaningful(o.text.trim())).map(o=>({value:o.value,label:o.text.trim()}));
  const radios=kind==='radio'?[...(group||document).querySelectorAll('input[type="radio"],[role="radio"]')]
    .filter(e=>visible(e)&&enabled(e)&&(!el.name||e.name===el.name)):[];
  if(kind==='radio')options=radios.map(e=>({value:e.value||label(e),label:label(e),ref:remember(e)}));
  const read=value().value,actual=Array.isArray(read)?read.join('; '):read.trim();
  const answered=kind==='check'?checked(el):kind==='radio'?radios.some(e=>e.checked||e.getAttribute('aria-checked')==='true'):
   meaningful(actual);
  return {field:el.name||el.id||question,question,kind,options,
   required:required(el)||owner===window.__jobbotWorkdayScope&&/\*\s*$/.test(question),answered,
   context:{page:window.__jobbotWorkdayScope?.step||'form',section:text(group?.querySelector('legend'))||
    text(el.closest('section')?.querySelector('h1,h2,h3')),document:location.href}};
 }
 if(args.method==='inspect'){
  scope.beforeMenus=[...document.querySelectorAll('[role="listbox"],[role="menu"]')].filter(visible);
  return {...describe(el),...value(),checked:checked(el),href:el.href||'',submission_control:
   /^(?:submit|submit application|send application)$/i.test(text(el)||el.value||label(el))&&
   !el.closest('form')?.querySelector('input[type="password"]')};
 }
 if(args.method==='focus'){el.focus();return {committed:document.activeElement===el};}
 if(args.method==='begin_menu_inspection'){
  scope.menuInspection={ref:args.ref,element:el};return {started:true};
 }
 if(args.method==='check'){
  if(!(['checkbox','radio'].includes(el.type)||['checkbox','radio'].includes(el.getAttribute('role')))||typeof args.value!=='boolean')
   return {committed:false,reason:'checkbox_value_required'};
  const validity=validation(el),matches=checked(el)===args.value;
  return {committed:matches&&!validity.rejected,needs_click:!matches,checked:checked(el),value_matches:matches,validation:validity,
   ...(matches&&validity.rejected?{reason:'native_validation_rejected'}:{})};
 }
 if(args.method==='fill'||args.method==='search'){
  if(!['INPUT','TEXTAREA'].includes(el.tagName)||['checkbox','radio','file'].includes(el.type)||el.readOnly||typeof args.value!=='string')
   return {committed:false,reason:'text_input_required'};
  const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
  el.focus();Object.getOwnPropertyDescriptor(proto,'value').set.call(el,args.value);
  el.dispatchEvent(new Event('input',{bubbles:true}));
  if(args.method==='search')return {committed:false,focused:el.isConnected&&document.activeElement===el,search_updated:el.value===args.value};
  el.dispatchEvent(new Event('change',{bubbles:true}));el.blur();
  return {committed:el.isConnected&&el.value===args.value};
 }
 if(args.method==='select_native'){
  if(el.tagName!=='SELECT')return {committed:false,reason:'native_select_required'};
  if(el.multiple&&(Array.isArray(args.label)||Array.isArray(args.value))){
   const labels=Array.isArray(args.label)?args.label:null,values=Array.isArray(args.value)?args.value:null,wanted=labels||values;
   const selected=wanted.map(w=>[...el.options].filter(o=>!o.disabled&&!o.parentElement.disabled&&(labels?o.text.trim()===w:o.value===w)));
   if(selected.some(matches=>matches.length!==1)||new Set(selected.map(matches=>matches[0])).size!==wanted.length)return {committed:false,reason:'ambiguous_or_missing_option'};
   const chosen=new Set(selected.map(matches=>matches[0]));
   for(const option of el.options)option.selected=chosen.has(option);
   el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.blur();
   return {committed:el.isConnected,...value()};
  }
  const options=[...el.options].filter(o=>!o.disabled&&!o.parentElement.disabled&&
   (args.label!==undefined?o.text.trim()===args.label:o.value===args.value||o.text.trim()===args.value));
  if(options.length!==1)return {committed:false,reason:options.length?'ambiguous_option':'option_not_found'};
  Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'selectedIndex').set.call(el,options[0].index);
  el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.blur();
  return {committed:el.isConnected&&el.value===options[0].value,...value()};
 }
 if(args.method==='select_options'){
  const ids=((el.getAttribute('aria-controls')||'')+' '+(el.getAttribute('aria-owns')||'')).trim().split(/\s+/).filter(Boolean);
  let menus=ids.map(id=>document.getElementById(id)).filter(visible);
  if(!menus.length&&el.id)menus=[...document.querySelectorAll('[role="listbox"],[role="menu"]')]
   .filter(e=>visible(e)&&(e.getAttribute('aria-labelledby')||'').split(/\s+/).includes(el.id));
  const phone=e=>!!e.closest('.iti,[class^="iti-"],[class*=" iti-"],[id^="iti-"]');
  if(greenhouse){
   const usable=m=>visible(m)&&(phone(el)||!phone(m)&&!m.querySelector('[id^="iti-"],[class^="iti-"]'));
   menus=menus.filter(usable);
   if(!menus.length)menus=[...widget(el).querySelectorAll('[role="listbox"],[role="menu"]')].filter(usable);
   if(!menus.length){
    const attributes=[el.id,el.getAttribute('aria-activedescendant'),...ids].filter(Boolean);
    // Derive the actual React-select instance from observed input/option IDs.
    const instances=[...new Set(attributes.map(a=>a.match(/^(react-select-.+?)-(?:input|listbox|option-.*)$/)?.[1]).filter(Boolean))];
    if(instances.length===1)menus=[...document.querySelectorAll('[role="listbox"],[role="menu"]')].filter(m=>usable(m)&&
     (m.id===instances[0]+'-listbox'||[...m.querySelectorAll('[role="option"]')].some(o=>o.id.startsWith(instances[0]+'-option-'))));
   }
  }
  if(!greenhouse&&!menus.length)menus=[...document.querySelectorAll('[role="listbox"],[role="menu"]')]
   .filter(e=>visible(e)&&!(scope.beforeMenus||[]).includes(e));
  if(!greenhouse&&!menus.length&&el.getAttribute('aria-expanded')==='true'&&
     nodes().filter(e=>e.getAttribute('aria-expanded')==='true').length===1)
   menus=[...document.querySelectorAll('[role="listbox"],[role="menu"]')].filter(visible);
  if(menus.length!==1)return {reason:'menu_association_unconfirmed',options:[]};
  const menu=menus[0];
  const options=[...menu.querySelectorAll('[role="option"],[role="menuitem"],option,[data-automation-id="promptOption"]')]
   .filter(visible).map(e=>({ref:remember(e),label:text(e),value:e.getAttribute('data-value')||e.value||text(e),enabled:enabled(e)}));
  scope.lastOptions=options;
  scope.menuOwner={element:el,menu};
  if(linkedin)scope.linkedinOptionMenu=menu;
  return {options};
 }
 if(args.method==='selection_dispatched'){
  if(linkedin&&el.tagName==='INPUT'&&choice(el)&&scope.lastOptions?.some(o=>o.ref===args.option_ref&&o.label===args.label)){
   scope.linkedinSelections=scope.linkedinSelections||new WeakMap();
   scope.linkedinSelections.set(el,{label:args.label,menu:scope.linkedinOptionMenu});
  }
  return {recorded:true};
 }
 if(args.method==='verify_select'){
  const actual=value();
  const exact=(actual,wanted)=>Array.isArray(actual)&&Array.isArray(wanted)?actual.length===wanted.length&&actual.every(v=>wanted.includes(v)):actual===wanted;
  const matches=el.tagName==='SELECT'?exact(actual.value,args.value)&&exact(actual.label,args.label):
   args.label!==undefined?actual.label===args.label:actual.value===args.value||actual.label===args.value;
  const validity=validation(el);
  const hidden=choice(el)?[...widget(el).querySelectorAll('input[type="hidden"]')].filter(h=>h.name&&(h.name===el.name||h.name===el.id)):[];
  const submission_matches=!hidden.length||args.value===undefined||hidden.length===1&&hidden[0].value===args.value;
  return {committed:matches&&(Array.isArray(actual.label)?actual.label.length>0&&actual.label.every(meaningful):meaningful(actual.label))&&!validity.rejected&&submission_matches,
   value_matches:matches,validation:validity,submission_matches,...actual,
   ...(matches&&validity.rejected?{reason:'native_validation_rejected'}:matches&&!submission_matches?{reason:'submission_value_mismatch'}:{})};
 }
 if(args.method==='close_menu'){
  // Only focus/close this inspection's own menu in the original document.
  if(scope.menuOwner?.element!==el&&scope.menuInspection?.element!==el)return {closed:false};
  el.focus();el.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}));el.blur();
  scope.menuInspection=null;
  return {closed:!visible(scope.menuOwner?.menu)};
 }
 return {committed:false,reason:'unsupported_form_operation'};
}
