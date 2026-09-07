// jobbot:simplify:observe — bounded DOM metadata, never field values.
(async () => {
  const visible = el => { const r=el.getBoundingClientRect(); return r.width>0 && r.height>0 && getComputedStyle(el).visibility!=='hidden'; };
  const publicUrl=location.origin+location.pathname;
  let hosts=Array.from(document.querySelectorAll('.simplify-jobs-shadow-root'));
  if(!hosts.length && document.querySelector('.simplify-jobs-shadow-root')) hosts=[document.querySelector('.simplify-jobs-shadow-root')];
  const roots=hosts.map(h=>h && (h.shadowRoot || (h.tagName ? h : null))).filter(Boolean);
  let scope=window.__jobbotSimplifyScope;
  if(!scope || scope.url!==location.href) scope=window.__jobbotSimplifyScope={url:location.href,id:crypto.randomUUID(),controls:new Map()};
  scope.controls=new Map();
  scope.fieldValues=scope.fieldValues||new Map();
  scope.valueEpoch=scope.valueEpoch||0;
  const candidates={autofill:[],continue:[]};
  for(const root of roots) {
    const btns = (typeof root.querySelectorAll === 'function') ? root.querySelectorAll('button,[role="button"]') : [];
    for(const button of btns) {
      if(!visible(button))continue;
      const label=(button.innerText || button.getAttribute('aria-label') || '').trim().toLowerCase();
      const kind=/^autofill this page$/.test(label)?'autofill':/^continue application$/.test(label)?'continue':null;
      if(!kind)continue;
      const enabled=!button.disabled && button.getAttribute('aria-disabled')!=='true';
      candidates[kind].push({button,enabled,root});
    }
  }
  const controls={autofill:{ref:null,enabled:false},continue:{ref:null,enabled:false}};
  for(const kind of ['autofill','continue']) {
    const actionable = candidates[kind].filter(c=>c.enabled);
    if(actionable.length === 1) {
      const chosen = actionable[0];
      const ref = crypto.randomUUID();
      scope.controls.set(ref, {element:chosen.button, kind, root:chosen.root});
      controls[kind] = {ref, enabled:true};
    } else if(actionable.length > 1) {
      // Ambiguous multiple actionable controls: fail-closed, do not guess
      controls[kind] = {ref:null, enabled:false};
    } else if(candidates[kind].length === 1) {
      const chosen = candidates[kind][0];
      const ref = crypto.randomUUID();
      scope.controls.set(ref, {element:chosen.button, kind, root:chosen.root});
      controls[kind] = {ref, enabled:false};
    } else {
      controls[kind] = {ref:null, enabled:false};
    }
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
  const fixture=document.body && document.body.textContent && document.body.textContent.includes('Synthetic fixture; not official Simplify support');
  let declared=null;
  if(fixture) {
    for(const r of roots) {
      const d=r.querySelector && r.querySelector('[data-status]')?.getAttribute('data-status');
      if(d) { declared=d; break; }
    }
  }
  let status='missing';
  if(roots.length > 0) {
    let hasActive=false, hasReview=false, hasComplete=false, hasLogin=false, hasUnsupported=false;
    for(const r of roots) {
      const busy = (typeof r.querySelector==='function') ? r.querySelector('[aria-busy="true"]') : null;
      const text = r.textContent || '';
      if(busy || /autofilling|filling your application|autofill in progress/i.test(text)) hasActive=true;
      if(/need(?:s)? review/i.test(text)) hasReview=true;
      if(/autofill complete|application autofilled/i.test(text)) hasComplete=true;
      if(/sign in to simplify|log in to simplify/i.test(text)) hasLogin=true;
      if(/not supported|autofill unavailable/i.test(text)) hasUnsupported=true;
    }
    // Fail-closed semantics: active visible writer in any relevant panel beats ready
    if(hasActive) status='active';
    else if(hasReview) status='needs_review';
    else if(hasComplete) status='complete';
    else if(hasLogin) status='login_required';
    else if(hasUnsupported) status='unsupported';
    else if(controls.autofill.enabled) status='ready';
    else status='unknown';
    if(declared && ['ready','active','complete','needs_review','unsupported','login_required'].includes(declared)) status=declared;
  }
  return {url:publicUrl,page_ref:scope.id,page_signature,fingerprint,panel:roots.length>0,status,controls,
    source:fixture?'fixture':'observed_dom',field_summary:{visible:fields.length,required:fields.filter(x=>x.required).length,invalid:fields.filter(x=>x.invalid).length}};
})()
