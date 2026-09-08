// Workday-specific metadata only; no experience/education fields or secret values.
(args) => {
  const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[hidden]');};
  const native=e=>!e.closest('.simplify-jobs-shadow-root,[id*="simplify"],[class*="simplify"]');
  const all=s=>[...document.querySelectorAll(s)].filter(e=>visible(e)&&native(e));
  const text=e=>(e.innerText||e.textContent||'').trim();
  const steps={'my information':'my_information','my experience':'my_experience','application questions':'application_questions','voluntary disclosures':'voluntary_disclosures','self identify':'self_identify','review':'review'};
  const markers=all('[aria-current="step"],h1,h2,h3');
  const step=markers.map(e=>steps[text(e).toLowerCase()]).find(Boolean)||'unknown';
  const scope={url:location.href,step,controls:new Map()}; window.__jobbotWorkdayScope=scope;
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
  const email=all('input[type="email"],input[autocomplete="username"],input[name="email"]');
  const selector=e=>e&&e.id?'[id='+JSON.stringify(e.id)+']':null;
  const auth_refs={email_ref:email.length===1?selector(email[0]):null,password_ref:pw.length>=1?selector(pw[0]):null,confirmation_ref:pw.length===2?selector(pw[1]):null};
  const escaped=(args.requisition||'').replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const req=escaped?new RegExp('(?:^|[^A-Za-z0-9])'+escaped+'(?:$|[^A-Za-z0-9])','i'):null;
  const rows=all('tr,[role="row"],[data-automation-id="applicationCard"]');
  const rowText=e=>[...e.querySelectorAll('td,[role="cell"]')].map(text).join(' ')||text(e);
  const submitted=!!req&&rows.some(e=>req.test(rowText(e))&&/application (?:has been |was )?(?:successfully )?(?:submitted|received)/i.test(rowText(e)));
  const attachments=all('[data-automation-id*="file"],[data-automation-id*="File"],[role="alert"],a');
  const resume_attached=!!args.resume_name&&attachments.some(e=>text(e).includes(args.resume_name)&&(/uploaded/i.test(text(e))||e.tagName==='A'||/file/i.test(e.getAttribute('data-automation-id')||'')));
  const email_inputs=all('input[type="email"]');
  const identity_mismatch=!!args.expected_email&&email_inputs.some(e=>e.value&&e.value.toLowerCase()!==args.expected_email.toLowerCase());
  return {step,native:controls,blocking_errors:[...new Set(errors)],auth:pw.length>0,auth_refs,submitted,resume_attached,identity_mismatch};
}
