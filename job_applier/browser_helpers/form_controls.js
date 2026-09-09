// Generic form inventory and value operations for the existing owned CDP target.
(args) => {
 const visible=e=>!!e&&e.isConnected&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
 const native=e=>!e.closest('.simplify-jobs-shadow-root,[id*="simplify"]');
 const text=e=>(e?.innerText||e?.textContent||'').replace(/\s+/g,' ').trim();
 const label=e=>e.getAttribute('aria-label')||[...(e.labels||[])].map(text).join(' ')||
  (e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)).filter(Boolean).map(text).join(' ')||
  e.getAttribute('placeholder')||text(e.closest('label'))||'';
 const nodes=()=>[...document.querySelectorAll('input:not([type="hidden"]),textarea,select,button,a,[role="button"],[role="checkbox"],[role="radio"],[role="combobox"]')].filter(e=>visible(e)&&native(e));
 const enabled=e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true';
 const checked=e=>['checkbox','radio'].includes(e.getAttribute('role'))?e.getAttribute('aria-checked')==='true':!!e.checked;
 const descriptor=e=>({tag:e.tagName,type:e.type||'',role:e.getAttribute('role')||'',name:e.name||'',
  label:label(e).slice(0,300),text:/^(BUTTON|A)$/.test(e.tagName)||e.getAttribute('role')==='button'?text(e).slice(0,200):'',
  automation_id:e.getAttribute('data-automation-id')||''});
 const key=e=>JSON.stringify(descriptor(e));
 let scope=window.__jobbotFormScope;
 if(!scope||scope.url!==location.href)scope={url:location.href,keys:new Map(),inventory:new Map(),controls:new Map(),bindings:new Map()};
 scope.page_signature=args.page_signature||scope.page_signature||location.origin+location.pathname;
 scope.step='form';
 window.__jobbotFormScope=scope;
 const remember=e=>{
  const k=key(e),matches=nodes().filter(n=>key(n)===k);
  let ref=matches.length===1?scope.keys.get(k):null;
  if(!ref)ref='form:'+crypto.randomUUID();
  if(matches.length===1)scope.keys.set(k,ref);
  scope.inventory.set(ref,e);scope.bindings.set(ref,k);return ref;
 };
 const required=e=>!!e.required||e.getAttribute('aria-required')==='true'||/\*\s*$/.test(label(e));
 const selectedValue=e=>{
  const workday=window.__jobbotWorkdayScope;
  if(workday?.url===location.href&&workday.selectedValue)return workday.selectedValue(e);
  if(e.tagName==='SELECT'){
   const value=e.selectedOptions[0]?.text||'';
   return e.value&&!/^(?:select(?: one)?|please select|choose(?: an? option)?)[.\s…]*$/i.test(value)?value:'';
  }
  if(e.getAttribute('role')==='combobox'||e.getAttribute('aria-haspopup')){
   const value=e.getAttribute('aria-valuetext')||(!['INPUT','TEXTAREA'].includes(e.tagName)?text(e):'');
   if(e.getAttribute('aria-expanded')!=='true'&&!/^(?:select(?: one)?|please select|choose(?: an? option)?)[.\s…]*$/i.test(value))return value;
  }
  return '';
 };
 const describe=e=>({...descriptor(e),ref:remember(e),enabled:enabled(e),required:required(e),
  present:!!selectedValue(e)||!!e.value,...(selectedValue(e)?{selected_value:selectedValue(e)}:{}),checked:['checkbox','radio'].includes(e.type)||e.getAttribute('role')==='checkbox'?checked(e):undefined,
  ...(e.tagName==='SELECT'?{options:[...e.options].map(o=>({value:o.value,label:o.text,disabled:o.disabled||o.parentElement.disabled}))}:{}),
  expanded:e.getAttribute('aria-expanded'),haspopup:e.getAttribute('aria-haspopup')});
 if(args.method==='observe'){
  const inventory=nodes().map(describe),controls={};
  const labels={'save and continue':'continue','continue':'continue','next':'continue','next step':'continue',
    'submit':'submit','submit application':'submit','send application':'submit'};
  for(const item of inventory){
   const kind=labels[item.text.toLowerCase()];if(!kind)continue;
   controls[kind]=controls[kind]?{enabled:false,ref:null}:{ref:item.ref,enabled:item.enabled};
  }
  const errors=[...document.querySelectorAll('[aria-invalid="true"],[role="alert"]')].filter(e=>visible(e)&&native(e))
   .filter(e=>e.getAttribute('aria-invalid')==='true'||/required|invalid|must (?:select|enter)/i.test(text(e)))
   .map(e=>(label(e)||text(e)).slice(0,180)).slice(0,8);
  return {step:'form',native:controls,inventory,blocking_errors:errors,auth:nodes().some(e=>e.type==='password'),
    page_signature:scope.page_signature};
 }
 if(args.method==='answers'){
  const currentPage=window.__jobbotWorkdayScope?.step||args.page;
  const questionnaire=['application_questions','voluntary_disclosures','self_identify'].includes(currentPage);
  const answers=[];
  for(const e of nodes()){
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
   let question=(group?.querySelector('legend')&&text(group.querySelector('legend')))||
    group?.getAttribute('aria-label')||text(fieldLabel)||ids.map(text).join(' ')||[...(e.labels||[])].map(text).join(' ')||label(e);
   const identity=question+' '+(e.name||'')+' '+(e.autocomplete||'');
   if(/password|passwd|\botp\b|token|secret|social.?security|\bssn\b|tax.?id|bank.?account|routing.?number|credit.?card|e.?mail|phone|postal|street.?address/i.test(identity))continue;
   if(!questionnaire&&!/\?|\b(?:salary|sponsorship|work authorization|consent|privacy|veteran|disability)\b/i.test(question))continue;
   let answer;
   if(type==='checkbox'||role==='checkbox')answer=checked(e)?'Yes':'No';
   else if(type==='radio'||role==='radio')answer=label(e)||e.value||text(e);
   else if(e.tagName==='SELECT')answer=e.selectedOptions[0]?.text||'';
   else answer=/^(INPUT|TEXTAREA)$/.test(e.tagName)?e.value:text(e);
   answer=(answer||'').trim();
   if(!answer||/^(?:select(?: one)?|please select|choose(?: an? option)?)[.\s…]*$/i.test(answer))continue;
   question=question.replace(/\s+Required\s*$/i,'').replace(/\s*\*$/,'').trim();
   if(!['checkbox','radio'].includes(type)&&!['checkbox','radio'].includes(role)&&question.endsWith(' '+answer))
    question=question.slice(0,-answer.length).trim();
   if(question&&question!==answer&&!/^(?:select one|yes|no)$/i.test(question))
    answers.push({field:e.name||e.id||question,question,answer,page:currentPage||'form'});
  }
  const cards=new Map();
  for(const host of document.querySelectorAll('.simplify-jobs-shadow-root')){
   for(const e of (host.shadowRoot||host).querySelectorAll('button,[role="button"]')){
    if(!visible(e))continue;
    const lines=(e.innerText||e.textContent||'').split(/\r?\n/).map(t=>t.trim()).filter(Boolean);
    if(lines.length>=2&&/\s[·•]\s*Updated on\b/i.test(lines[1])){
     const company=lines[1].split(/\s[·•]\s*Updated on\b/i)[0].trim();
     cards.set(lines[0]+'|'+company,{job_title:lines[0],company,source:'simplify_job_card'});
    }
   }
  }
  return {answers,context:cards.size===1?[...cards.values()][0]:{}};
 }
 let owner=args.ref?.startsWith('form:')?scope:window.__jobbotWorkdayScope;
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
 if(el.type==='password'||/otp|one.?time|verification.?code/i.test((el.name||'')+' '+(el.autocomplete||'')+' '+label(el)))
  return {committed:false,reason:'use_private_credentials_helper',execution:'not_executed'};
 const value=()=>el.tagName==='SELECT'?{value:el.value,label:el.selectedOptions[0]?.text||''}:
  {value:selectedValue(el)||(/^(INPUT|TEXTAREA)$/.test(el.tagName)?el.value:text(el)),label:selectedValue(el)||(/^(INPUT|TEXTAREA)$/.test(el.tagName)?el.value:text(el))};
 if(args.method==='question'){
  const role=el.getAttribute('role'),group=el.closest('fieldset,[role="radiogroup"],[role="group"]');
  const question=(owner===window.__jobbotWorkdayScope&&owner.questionText?.(el))||
   text(group?.querySelector('legend'))||group?.getAttribute('aria-label')||label(el);
  let kind=el.tagName==='SELECT'||role==='combobox'||['listbox','menu','true'].includes(el.getAttribute('aria-haspopup'))?'select':
   el.type==='checkbox'||role==='checkbox'?'check':el.type==='radio'||role==='radio'?'radio':'text';
  if(kind==='text'&&!['INPUT','TEXTAREA'].includes(el.tagName))return {reason:'question_control_unrecognized'};
  let options=[];
  if(el.tagName==='SELECT')options=[...el.options].filter(o=>!o.disabled&&!o.parentElement.disabled&&o.value!==''&&
    !/^(?:select(?: one)?|please select|choose(?: an? option)?)[.\s…]*$/i.test(o.text.trim())).map(o=>({value:o.value,label:o.text.trim()}));
  const radios=kind==='radio'?[...(group||document).querySelectorAll('input[type="radio"],[role="radio"]')]
    .filter(e=>visible(e)&&enabled(e)&&(!el.name||e.name===el.name)):[];
  if(kind==='radio')options=radios.map(e=>({value:e.value||label(e),label:label(e),ref:remember(e)}));
  const actual=value().value.trim();
  const answered=kind==='check'?checked(el):kind==='radio'?radios.some(e=>e.checked||e.getAttribute('aria-checked')==='true'):
   !!actual&&!/^(?:select(?: one)?|please select|choose(?: an? option)?)[.\s…]*$/i.test(actual);
  return {field:el.name||el.id||question,question,kind,options,
   required:required(el)||owner===window.__jobbotWorkdayScope&&/\*\s*$/.test(question),answered,
   context:{page:window.__jobbotWorkdayScope?.step||'form',section:text(group?.querySelector('legend'))||
    text(el.closest('section')?.querySelector('h1,h2,h3')),document:location.href}};
 }
 if(args.method==='inspect'){
  scope.beforeMenus=[...document.querySelectorAll('[role="listbox"],[role="menu"]')].filter(visible);
  return {...describe(el),...value(),checked:checked(el),submission_control:
   /^(?:submit|submit application|send application)$/i.test(text(el)||el.value||label(el))&&
   !el.closest('form')?.querySelector('input[type="password"]')};
 }
 if(args.method==='focus'){el.focus();return {committed:document.activeElement===el};}
 if(args.method==='check'){
  if(!(['checkbox','radio'].includes(el.type)||['checkbox','radio'].includes(el.getAttribute('role')))||typeof args.value!=='boolean')
   return {committed:false,reason:'checkbox_value_required'};
  return {committed:checked(el)===args.value,needs_click:checked(el)!==args.value,checked:checked(el)};
 }
 if(args.method==='fill'){
  if(!['INPUT','TEXTAREA'].includes(el.tagName)||['checkbox','radio','file'].includes(el.type)||el.readOnly||typeof args.value!=='string')
   return {committed:false,reason:'text_input_required'};
  const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
  el.focus();Object.getOwnPropertyDescriptor(proto,'value').set.call(el,args.value);
  el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.blur();
  return {committed:el.isConnected&&el.value===args.value};
 }
 if(args.method==='select_native'){
  if(el.tagName!=='SELECT')return {committed:false,reason:'native_select_required'};
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
  if(!menus.length)menus=[...document.querySelectorAll('[role="listbox"],[role="menu"]')]
   .filter(e=>visible(e)&&!(scope.beforeMenus||[]).includes(e));
  if(!menus.length&&el.getAttribute('aria-expanded')==='true'&&
     nodes().filter(e=>e.getAttribute('aria-expanded')==='true').length===1)
   menus=[...document.querySelectorAll('[role="listbox"],[role="menu"]')].filter(visible);
  if(menus.length!==1)return {reason:'menu_association_unconfirmed',options:[]};
  const menu=menus[0];
  const options=[...menu.querySelectorAll('[role="option"],[role="menuitem"],option,[data-automation-id="promptOption"]')]
   .filter(visible).map(e=>({ref:remember(e),label:text(e),value:e.getAttribute('data-value')||e.value||text(e),enabled:enabled(e)}));
  scope.lastOptions=options;
  return {options};
 }
 if(args.method==='verify_select'){
  const actual=value();
  const matches=el.tagName==='SELECT'?actual.value===args.value&&actual.label===args.label:
   actual.value===args.value||actual.label===args.value||actual.label===args.label;
  return {committed:matches,...actual};
 }
 return {committed:false,reason:'unsupported_form_operation'};
}
