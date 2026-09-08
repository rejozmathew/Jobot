// Workday-specific metadata only; no experience/education fields or secret values.
(args) => {
  const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[hidden]');};
  const native=e=>!e.closest('.simplify-jobs-shadow-root,[id*="simplify"],[class*="simplify"]');
  const all=s=>[...document.querySelectorAll(s)].filter(e=>visible(e)&&native(e));
  const text=e=>(e.innerText||e.textContent||'').trim();
  const steps={'my information':'my_information','my experience':'my_experience','application questions':'application_questions','voluntary disclosures':'voluntary_disclosures','self identify':'self_identify','review':'review'};
  const markers=all('[aria-current="step"],h1,h2,h3');
  const step=markers.map(e=>steps[text(e).toLowerCase()]).find(Boolean)||'unknown';
  const page_signature=args.page_signature||location.origin+location.pathname;
  let scope=window.__jobbotWorkdayScope;
  if(!scope||scope.url!==location.href||scope.page_signature!==page_signature)
    scope={url:location.href,page_signature,keys:new Map(),elementKeys:new WeakMap()};
  Object.assign(scope,{step,controls:new Map(),inventory:new Map()}); window.__jobbotWorkdayScope=scope;
  const accessible=e=>e.getAttribute('aria-label')||[...(e.labels||[])].map(text).join(' ')||
    (e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)).filter(Boolean).map(text).join(' ')||
    e.getAttribute('placeholder')||'';
  const nodes=all('input:not([type="hidden"]),select,textarea,button,a,[role="button"],[role="checkbox"],[role="combobox"]');
  const describe=e=>({tag:e.tagName,type:e.type||'',role:e.getAttribute('role')||'',name:e.name||'',
    label:accessible(e).slice(0,300),text:/^(BUTTON|A)$/.test(e.tagName)||e.getAttribute('role')==='button'?text(e).slice(0,200):'',
    automation_id:e.getAttribute('data-automation-id')||'',
    auth_form:!!e.closest('form,[role="dialog"]')?.querySelector('input[type="password"]')});
  const descriptions=nodes.map(describe),keys=descriptions.map(d=>JSON.stringify(d));
  const inventory=nodes.map((e,i)=>{
    // A unique semantic description survives routine rerenders and changing IDs.
    // Ambiguous descriptions retain an element identity; they are never guessed.
    if(!scope.elementKeys.has(e))scope.elementKeys.set(e,crypto.randomUUID());
    const key=keys.filter(k=>k===keys[i]).length===1?keys[i]:keys[i]+'#'+(e.id&&nodes.filter(n=>n.id===e.id).length===1?e.id:scope.elementKeys.get(e));
    let ref=scope.keys.get(key);if(!ref){ref='wd:'+crypto.randomUUID();scope.keys.set(key,ref);}
    scope.inventory.set(ref,e);
    return {...descriptions[i],ref,id:e.id||'',enabled:!e.disabled&&e.getAttribute('aria-disabled')!=='true',
      required:!!e.required||e.getAttribute('aria-required')==='true',present:!!e.value,
      ...((['checkbox','radio'].includes(e.type)||e.getAttribute('role')==='checkbox')?
        {checked:!!e.checked||e.getAttribute('aria-checked')==='true'}:{}),
      ...(e.tagName==='SELECT'?{options:[...e.options].map(o=>({value:o.value,label:o.text,disabled:o.disabled}))}:{})};
  });
  const controls={};
  const labels={'save and continue':'continue','submit':'submit','sign in':'sign_in','create account':'create_account'};
  for(const e of all('button,[role="button"]')){
    const kind=labels[text(e).toLowerCase()]; if(!kind)continue;
    const enabled=!e.disabled&&e.getAttribute('aria-disabled')!=='true';
    if(controls[kind]){controls[kind]={enabled:false,ref:null};continue;}
    const ref=kind; scope.controls.set(ref,e); controls[kind]={enabled,ref};
  }
  const errors=all('[aria-invalid="true"],[data-automation-id="errorMessage"],[role="alert"]')
    .filter(e=>!(/successfully uploaded/i.test(text(e))))
    .filter(e=>e.getAttribute('aria-invalid')==='true'||/required|error|invalid|must select|must enter/i.test(text(e)))
    .map(e=>((e.getAttribute('aria-label')||text(e)).slice(0,180))).filter(Boolean).slice(0,8);
  const pw=all('input[type="password"]');
  const email=all('input').filter(e=>e.type==='email'||e.autocomplete.toLowerCase()==='username'||e.name.toLowerCase()==='email'||
    (e.type==='text'&&/^e[- ]?mail(?: address)?\s*\*?$/i.test(accessible(e).trim())));
  const selector=e=>e&&e.id?'[id='+JSON.stringify(e.id)+']':null;
  const auth_refs={email_ref:email.length===1?selector(email[0]):null,password_ref:pw.length>=1?selector(pw[0]):null,confirmation_ref:pw.length===2?selector(pw[1]):null};
  const mode=pw.length===2?'create_account':pw.length===1?'sign_in':'unknown';
  const authRoot=pw[0]&&(pw[0].closest('form,[role="dialog"]')||document);
  const authButtons=authRoot?all('button,a,[role="button"]').filter(e=>authRoot.contains(e)):[];
  const authControl=(kind,matches)=>{
    if(matches.length!==1){if(matches.length)controls[kind]={enabled:false,ref:null};return;}
    const e=matches[0];scope.controls.set(kind,e);
    controls[kind]={ref:kind,enabled:!e.disabled&&e.getAttribute('aria-disabled')!=='true'};
  };
  const label=mode==='create_account'?'create account':'sign in';
  authControl('auth_submit',authButtons.filter(e=>text(e).toLowerCase()===label&&(e.tagName==='BUTTON'||e.getAttribute('role')==='button')));
  const accountNavigation=all('button,a,[role="button"]');
  authControl('auth_switch_sign_in',mode==='create_account'?accountNavigation.filter(e=>text(e).toLowerCase()==='sign in'):[]);
  authControl('auth_switch_create_account',mode==='sign_in'?accountNavigation.filter(e=>text(e).toLowerCase()==='create account'):[]);
  const checkboxes=authRoot?all('input[type="checkbox"],[role="checkbox"]').filter(e=>authRoot.contains(e)):[];
  const checkboxLabel=e=>[...(e.labels||[])].map(text).join(' ')||e.getAttribute('aria-label')||
    (e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)).filter(Boolean).map(text).join(' ')||text(e.closest('label')||e.parentElement);
  const consent=e=>{const t=checkboxLabel(e);return !/marketing|job alerts|talent community|send me/i.test(t)&&
    /privacy|terms|conditions|consent|personal data/i.test(t)&&(/agree|accept/i.test(t)||e.required||e.getAttribute('aria-required')==='true');};
  const unchecked=e=>!e.checked&&e.getAttribute('aria-checked')!=='true';
  const pendingConsent=checkboxes.filter(e=>consent(e)&&unchecked(e));
  authControl('auth_consent',pendingConsent);
  const notices=all('[role="alert"],[data-automation-id="errorMessage"],h1,h2,h3,p').map(text).join(' ');
  const auth_ui={mode,unknown_required_consent:pendingConsent.length>1||checkboxes.some(e=>unchecked(e)&&!consent(e)&&(e.required||e.getAttribute('aria-required')==='true')),
    challenge:/verify your (?:email|account)|verification (?:email|code)|check your (?:email|inbox)|multi.factor authentication/i.test(notices),
    account_exists:/(?:account|email).{0,70}already (?:exists|registered|in use)/i.test(notices),
    account_created:/(?:account.{0,50}(?:successfully created|has been created)|account created successfully)/i.test(notices),
    credential_rejected:/(?:invalid|incorrect).{0,35}(?:password|credentials|email)|(?:password|credentials).{0,35}(?:invalid|incorrect)|account.{0,30}locked/i.test(notices)};
  const escaped=(args.requisition||'').replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const req=escaped?new RegExp('(?:^|[^A-Za-z0-9])'+escaped+'(?:$|[^A-Za-z0-9])','i'):null;
  const rows=all('tr,[role="row"],[data-automation-id="applicationCard"]');
  const rowText=e=>[...e.querySelectorAll('td,[role="cell"]')].map(text).join(' ')||text(e);
  const submitted=!!req&&rows.some(e=>req.test(rowText(e))&&/application (?:has been |was )?(?:successfully )?(?:submitted|received)/i.test(rowText(e)));
  const attachments=all('[data-automation-id*="file"],[data-automation-id*="File"],[role="alert"],a');
  const resume_attached=!!args.resume_name&&attachments.some(e=>text(e).includes(args.resume_name)&&(/uploaded/i.test(text(e))||e.tagName==='A'||/file/i.test(e.getAttribute('data-automation-id')||'')));
  const email_inputs=all('input[type="email"]');
  const identity_mismatch=!!args.expected_email&&email_inputs.some(e=>e.value&&e.value.toLowerCase()!==args.expected_email.toLowerCase());
  return {step,native:controls,inventory,blocking_errors:[...new Set(errors)],auth:pw.length>0||auth_ui.challenge,auth_refs,auth_ui,submitted,resume_attached,identity_mismatch};
}
