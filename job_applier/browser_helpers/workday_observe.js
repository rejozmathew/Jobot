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
  const question=e=>{
    const field=e.closest('[data-automation-id^="formField"],fieldset,[role="group"],[role="radiogroup"]');
    const label=field?.querySelector('legend,label,[data-automation-id="questionLabel"],[data-automation-id="richText"]');
    return label?text(label):accessible(e);
  };
  scope.questionText=question;
  const placeholder=t=>!t||/^(?:search|select(?: one)?|please select|choose(?: an? option)?)[.\s…]*$/i.test(t.trim());
  const selectedValue=e=>{
    if(e.tagName==='SELECT')return e.value&&!placeholder(text(e.selectedOptions[0]))?text(e.selectedOptions[0]):'';
    const field=e.closest('[data-automation-id^="formField"],fieldset');
    const chips=field?[...field.querySelectorAll('[data-automation-id^="selectedItem"],[data-automation-id^="promptSelectedOption"],[data-automation-id^="promptSelection"]')]:[];
    // Workday uses suffixed selection IDs and can wrap the selected chip and
    // the open popup in one listbox. Menu ancestry does not erase that chip.
    const chip=chips.filter(visible).filter(n=>!n.querySelector('[data-automation-id="promptOptions"],[role="menu"]')).map(text).find(t=>!placeholder(t));
    if(chip)return chip;
    if(!['INPUT','TEXTAREA'].includes(e.tagName)&&(e.getAttribute('role')==='combobox'||e.getAttribute('aria-haspopup'))){
      const value=e.getAttribute('aria-valuetext')||text(e);
      if(e.getAttribute('aria-expanded')!=='true'&&!placeholder(value))return value;
    }
    return '';
  };
  scope.selectedValue=selectedValue;
  const nodes=all('input:not([type="hidden"]),select,textarea,button,a,[role="button"],[role="checkbox"],[role="combobox"]');
  const describe=e=>({tag:e.tagName,type:e.type||'',role:e.getAttribute('role')||'',name:e.name||'',
    label:accessible(e).slice(0,300),question:question(e).slice(0,4000),
    text:/^(BUTTON|A)$/.test(e.tagName)||e.getAttribute('role')==='button'?text(e).slice(0,200):'',
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
      required:!!e.required||e.getAttribute('aria-required')==='true'||/\*\s*$/.test(question(e)),present:!!selectedValue(e)||!!e.value,
      ...(selectedValue(e)?{selected_value:selectedValue(e)}:{}),
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
  // Exact direct-entry actions outrank optional chat flows, including anchors
  // on employer-customized Workday landing pages and application choosers.
  const entryLabels=['apply manually','apply now','apply for this job','apply for job','apply for application','start application','begin application','apply'];
  for(const label of entryLabels){
    const matches=all('button,a,[role="button"]').filter(e=>enabledEntry(e)&&
      (accessible(e)||text(e)).trim().toLowerCase()===label);
    if(!matches.length)continue;
    const e=matches[0];
    // Matching responsive duplicates are safe only when they share a destination.
    const unique=matches.length===1||e.tagName==='A'&&matches.every(n=>n.tagName==='A'&&n.href===e.href);
    controls.apply={enabled:unique,ref:unique?'apply':null,label,href:e.tagName==='A'?e.href:null};
    if(unique)scope.controls.set('apply',e);
    break;
  }
  function enabledEntry(e){return !e.disabled&&e.getAttribute('aria-disabled')!=='true';}
  const errors=all('[aria-invalid="true"],[data-automation-id="errorMessage"],[role="alert"]')
    .filter(e=>!(/successfully uploaded/i.test(text(e))))
    .filter(e=>e.getAttribute('aria-invalid')==='true'||/required|error|invalid|must select|must enter/i.test(text(e)))
    .map(e=>((e.getAttribute('aria-label')||text(e)).slice(0,180))).filter(Boolean).slice(0,8);
  const pw=all('input[type="password"]');
  const email=all('input').filter(e=>e.type==='email'||e.autocomplete.toLowerCase()==='username'||e.name.toLowerCase()==='email'||
    (e.type==='text'&&/^e[- ]?mail(?: address)?\s*\*?$/i.test(accessible(e).trim())));
  const selector=e=>e&&e.id?'[id='+JSON.stringify(e.id)+']':null;
  const auth_refs={email_ref:email.length===1?selector(email[0]):null,password_ref:pw.length>=1?selector(pw[0]):null,confirmation_ref:pw.length===2?selector(pw[1]):null};
  const emailEntry=all('button,a,[role="button"]').filter(e=>
    e.getAttribute('data-automation-id')==='SignInWithEmailButton'||
    /^sign in with (?:e-mail|email)$/i.test((accessible(e)||text(e)).trim()));
  const mode=pw.length===2?'create_account':pw.length===1?'sign_in':emailEntry.length===1?'email_chooser':'unknown';
  const authRoot=pw[0]&&(pw[0].closest('form,[role="dialog"]')||document);
  const authButtons=authRoot?all('button,a,[role="button"]').filter(e=>authRoot.contains(e)):[];
  const authControl=(kind,matches)=>{
    if(matches.length!==1){if(matches.length)controls[kind]={enabled:false,ref:null};return;}
    const e=matches[0];scope.controls.set(kind,e);
    controls[kind]={ref:kind,enabled:!e.disabled&&e.getAttribute('aria-disabled')!=='true'};
  };
  if(mode==='email_chooser')authControl('auth_sign_in_email',emailEntry);
  const label=mode==='create_account'?'create account':'sign in';
  const submitButtons=authButtons.filter(e=>text(e).toLowerCase()===label&&e.tagName==='BUTTON');
  // Workday can place a labelled click_filter over its visible submit button.
  // Select that actual control only when it belongs to the same auth form and
  // covers the matching button's center. Unrelated overlays remain blockers.
  const wrappers=submitButtons.length===1?authButtons.filter(e=>
    e.getAttribute('data-automation-id')==='click_filter'&&e.getAttribute('role')==='button'&&
    (e.getAttribute('aria-label')||'').trim().toLowerCase()===label&&(()=>{
      const b=submitButtons[0].getBoundingClientRect(),w=e.getBoundingClientRect();
      const x=b.left+b.width/2,y=b.top+b.height/2;
      return w.left<=x&&w.right>=x&&w.top<=y&&w.bottom>=y;
    })()):[];
  const fallback=authButtons.filter(e=>text(e).toLowerCase()===label&&(e.tagName==='BUTTON'||e.getAttribute('role')==='button'));
  authControl('auth_submit',wrappers.length===1?wrappers:fallback);
  if(wrappers.length===1)controls.auth_submit.enabled=controls.auth_submit.enabled&&
    !submitButtons[0].disabled&&submitButtons[0].getAttribute('aria-disabled')!=='true';
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
  const pageNotices=all('main,[role="main"],[role="alert"],[data-automation-id="errorPage"],h1,h2,h3,p').map(text).join(' ');
  const refresh_error=/something went wrong/i.test(pageNotices)&&/(?:refresh|reload) (?:the |this |your )?page/i.test(pageNotices);
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
  // References and referrers have their own email addresses. Only a labelled
  // applicant address or the current account form establishes candidate identity.
  const emailMeaning=e=>[accessible(e),e.name,e.getAttribute('data-automation-id')||''].join(' ').trim();
  const otherPerson=e=>/refer(?:ence|ral|rer)|recommender|supervisor|manager|recruiter|emergency|contact person/i.test(emailMeaning(e));
  const candidateEmails=email.filter(e=>!otherPerson(e)&&(authRoot?.contains(e)||
    /applicant|candidate|personal|your e[- ]?mail/i.test(emailMeaning(e))||
    /^e[- ]?mail(?: address)?\s*\*?$/i.test(accessible(e).trim())||/^email(?:address)?$/i.test(e.name)||
    /^(?:email|username)$/i.test(e.autocomplete)));
  const identityEmails=candidateEmails.length?candidateEmails:email.length===1&&!otherPerson(email[0])&&!emailMeaning(email[0])?email:[];
  const identity_mismatch=!!args.expected_email&&identityEmails.some(e=>e.value&&e.value.trim().toLowerCase()!==args.expected_email.trim().toLowerCase());
  return {step,native:controls,inventory,blocking_errors:[...new Set(errors)],refresh_error,document_id:performance.timeOrigin,auth:pw.length>0||mode==='email_chooser'||auth_ui.challenge,auth_refs,auth_ui,submitted,resume_attached,identity_mismatch};
}
