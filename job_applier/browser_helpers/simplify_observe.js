// jobbot:simplify:observe — bounded DOM metadata, never field values.
(async () => {
  const visible = el => { const r=el.getBoundingClientRect(); return r.width>0 && r.height>0 && getComputedStyle(el).visibility!=='hidden'; };
  const publicUrl=location.origin+location.pathname;
  const host=document.querySelector('.simplify-jobs-shadow-root');
  const root=host && host.shadowRoot;
  let scope=window.__jobbotSimplifyScope;
  if(!scope || scope.url!==location.href) scope=window.__jobbotSimplifyScope={url:location.href,id:crypto.randomUUID(),controls:new Map()};
  scope.controls=new Map();
  scope.fieldValues=scope.fieldValues||new Map();
  scope.valueEpoch=scope.valueEpoch||0;
  const controls={autofill:{ref:null,enabled:false},continue:{ref:null,enabled:false}};
  if(root) for(const button of root.querySelectorAll('button,[role="button"]')) {
    if(!visible(button))continue;
    const label=(button.innerText || button.getAttribute('aria-label') || '').trim().toLowerCase();
    const kind=/^autofill this page$/.test(label)?'autofill':/^continue application$/.test(label)?'continue':null;
    if(!kind)continue;
    const ref=crypto.randomUUID();
    const enabled=!button.disabled && button.getAttribute('aria-disabled')!=='true';
    scope.controls.set(ref,{element:button,kind});
    controls[kind]={ref,enabled};
  }
  // No input values, selected labels, file names, passwords or OTPs leave the page.
  const nodes=[...document.querySelectorAll('input,select,textarea')].filter(visible).slice(0,200);
  const nextValues=new Map();
  for(const [index,el] of nodes.entries()) {
    // Values remain only in the page, never in returned metadata or value hashes.
    // Secret/code controls are deliberately excluded from this private comparison.
    const identity=(el.getAttribute('name')||'')+' '+(el.getAttribute('autocomplete')||'');
    if(el.type==='password'||/otp|token|secret|password|security.?code|one.time|(?:^|\s)pin(?:\s|$)/i.test(identity))continue;
    const value=JSON.stringify([el.value,!!el.checked,el.multiple?Array.from(el.selectedOptions||[]).map(x=>x.value):null]);
    const key=JSON.stringify([el.getAttribute('name')||el.getAttribute('data-automation-id')||el.getAttribute('aria-label'),el.type,index]);
    if(scope.fieldValues.has(key)&&scope.fieldValues.get(key)!==value)scope.valueEpoch++;
    nextValues.set(key,value);
  }
  scope.fieldValues=nextValues;
  const fields=nodes.map(el=>({
    key:(el.getAttribute('name')||el.getAttribute('data-automation-id')||el.getAttribute('aria-label')||el.type||el.tagName).slice(0,100),
    type:el.type||el.tagName, required:!!el.required,
    present:el.type==='checkbox'||el.type==='radio'?!!el.checked:!!el.value,
    invalid:el.getAttribute('aria-invalid')==='true'||(el.validity && !el.validity.valid)
  }));
  const headings=[...document.querySelectorAll('h1,h2,h3')].filter(visible).slice(0,5).map(el=>(el.textContent||'').slice(0,120));
  const digest=async value=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value))))).map(x=>x.toString(16).padStart(2,'0')).join('');
  const marker=document.querySelector('[aria-current="step"]');
  const stepHeadings=[...document.querySelectorAll('h1,h2,h3')].filter(visible).filter(el=>
    el.getAttribute('role')!=='alert' && !el.getAttribute('aria-live') &&
    !(typeof el.closest==='function' && el.closest('[role="alert"],[aria-live],.validation-error,.field-error'))
  ).slice(0,5).map(el=>(el.textContent||'').slice(0,160));
  // Logical step identity excludes values, presence, required/invalid flags and
  // validation headings, but distinguishes same-URL SPA headings/form structure.
  const page_signature=await digest([publicUrl,marker?(marker.textContent||'').slice(0,160):stepHeadings,
    marker?[]:fields.map(({key,type})=>({key,type}))]);
  const fingerprint=await digest([page_signature,headings,fields,scope.valueEpoch]);
  const text=root?(root.textContent||''):'';
  const fixture=document.body.textContent.includes('Synthetic fixture; not official Simplify support');
  const declared=fixture && root && root.querySelector('[data-status]')?.getAttribute('data-status');
  let status='missing';
  if(root) {
    if(root.querySelector('[aria-busy="true"]')||/autofilling|filling your application|autofill in progress/i.test(text)) status='active';
    else if(/need(?:s)? review/i.test(text))status='needs_review';
    else if(/autofill complete|application autofilled/i.test(text))status='complete';
    else if(/sign in to simplify|log in to simplify/i.test(text))status='login_required';
    else if(/not supported|autofill unavailable/i.test(text))status='unsupported';
    else if(controls.autofill.enabled)status='ready';
    else status='unknown';
    if(declared && ['ready','active','complete','needs_review','unsupported','login_required'].includes(declared))status=declared;
  }
  return {url:publicUrl,page_ref:scope.id,page_signature,fingerprint,panel:!!root,status,controls,
    source:fixture?'fixture':'observed_dom',field_summary:{visible:fields.length,required:fields.filter(x=>x.required).length,invalid:fields.filter(x=>x.invalid).length}};
})()
