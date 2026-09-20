// jobbot:simplify:observe — bounded DOM metadata, never field values.
(async () => {
  const visible = el => { const r=el.getBoundingClientRect(); return r.width>0 && r.height>0 && getComputedStyle(el).visibility!=='hidden'; };
  const publicUrl=location.origin+location.pathname;
  const workday=/^https:\/\/[^/]+\.myworkdayjobs\.com\//i.test(publicUrl);
  const greenhouse=/(^|\.)greenhouse\.io$/.test(location.hostname||'')||/[?&]gh_jid=/.test(location.href)||!!window.__jobbotGreenhouseOwner;
  let receipt=null,documentId=null;
  if(greenhouse){
    const doc=window.__jobbotGreenhouseDocument||(window.__jobbotGreenhouseDocument={id:crypto.randomUUID(),cycles:new Map()});
    documentId=doc.id;
    const key=JSON.stringify([window.__jobbotGreenhouseOwner?.attempt_id||null,window.__jobbotGreenhouseOwner?.target_id||null,doc.id]);
    if(!doc.cycles.has(key))doc.cycles.set(key,{dispatch_count:0,automatic_count:0,state:'none',repairs_started:false});
    receipt=doc.cycles.get(key);doc.current=receipt;doc.key=key;
  }
  let hosts=Array.from(document.querySelectorAll('.simplify-jobs-shadow-root'));
  if(!hosts.length && document.querySelector('.simplify-jobs-shadow-root')) hosts=[document.querySelector('.simplify-jobs-shadow-root')];
  const roots=hosts.map(h=>h && (h.shadowRoot || (h.tagName ? h : null))).filter(Boolean);
  // Survives SPA URL/headings; only replacement of the actual document cancels it.
  const writer=window.__jobbotWriter||(window.__jobbotWriter={document_id:crypto.randomUUID(),participant:false,pending:false,terminal:false});
  let scope=window.__jobbotSimplifyScope;
  if(!scope || scope.url!==location.href) scope=window.__jobbotSimplifyScope={url:location.href,id:crypto.randomUUID(),controls:new Map()};
  scope.controls=new Map();
  scope.writer=writer;
  // Employer credentials belong to the native Workday account routine. Recheck
  // the live form at click time too: it can appear after an extension snapshot.
  scope.workday=workday;
  scope.greenhouse=greenhouse;
  scope.greenhouseReceipt=receipt;
  scope.nativeAuthenticationRequired=()=>workday&&(/\/login\/?$/i.test(location.pathname)||
    [...document.querySelectorAll('input[type="password"],button,a,[role="button"]')].some(e=>
      visible(e)&&!e.closest?.('.simplify-jobs-shadow-root,[hidden]')&&
      (e.type==='password'||e.getAttribute('data-automation-id')==='SignInWithEmailButton'||
       /^sign in with e-?mail$/i.test((e.getAttribute('aria-label')||e.textContent||'').trim()))));
  scope.referenceKeys=scope.referenceKeys||new Map();
  const reference=key=>{if(!scope.referenceKeys.has(key))scope.referenceKeys.set(key,crypto.randomUUID());return scope.referenceKeys.get(key);};
  scope.fieldValues=scope.fieldValues||new Map();
  scope.valueEpoch=scope.valueEpoch||0;
  const CONTROL_KINDS=['autofill','autofill_skills','continue','start','create_account_autofill','create_account','sign_in','submit','stop'];
  const candidates={};
  const controls={};
  const inventory=[];
  const ambiguousOther=new Set();
  for(const k of CONTROL_KINDS){candidates[k]=[];controls[k]={ref:null,enabled:false};}
  for(const root of roots) {
    const btns = (typeof root.querySelectorAll === 'function') ? root.querySelectorAll('button,[role="button"]') : [];
    for(const button of btns) {
      if(!visible(button))continue;
      const label=(button.innerText || button.textContent || button.getAttribute('aria-label') || button.getAttribute('title') || '').trim().toLowerCase();
      let kind=null;
      if(/^(?:autofill this page|run autofill again)$/.test(label)) kind='autofill';
      else if(/^autofill\s+\d+\s+skills?$/.test(label)) kind='autofill_skills';
      else if(/^continue application$/.test(label)) kind='continue';
      else if(/^start application$/.test(label)) kind='start';
      else if(/^create account (&|and) autofill$/.test(label)) kind='create_account_autofill';
      else if(/^create account$/.test(label)) kind='create_account';
      else if(/^sign in( (&|and) autofill)?$/.test(label)) kind='sign_in';
      else if(/^submit application$/.test(label)) kind='submit';
      else if(/^(?:stop|cancel) (?:autofill|account step|filling)$/.test(label)) kind='stop';
      const enabled=!button.disabled && button.getAttribute('aria-disabled')!=='true' && button.getAttribute('aria-busy')!=='true';
      if(!kind){
        const ref=reference('other:'+label);
        if(ambiguousOther.has(ref))continue;
        if(scope.controls.has(ref)){scope.controls.delete(ref);ambiguousOther.add(ref);inventory.filter(c=>c.ref===ref).forEach(c=>c.enabled=false);continue;}
        scope.controls.set(ref,{element:button,kind:'other',root});
        inventory.push({ref,label,operation:'other',enabled});continue;
      }
      candidates[kind].push({button,enabled,root,label});
    }
  }
  for(const kind of CONTROL_KINDS) {
    const actionable = candidates[kind].filter(c=>c.enabled);
    if(actionable.length === 1) {
      const chosen = actionable[0];
      const ref = reference(kind+':'+chosen.label);
      scope.controls.set(ref, {element:chosen.button, kind, root:chosen.root});
      controls[kind] = {ref, enabled:true, label:chosen.label};
      inventory.push({ref,label:chosen.label,operation:kind,enabled:true});
    } else if(actionable.length > 1) {
      // Ambiguous multiple actionable controls: fail-closed, do not guess
      controls[kind] = {ref:null, enabled:false};
    } else if(candidates[kind].length === 1) {
      const chosen = candidates[kind][0];
      const ref = reference(kind+':'+chosen.label);
      scope.controls.set(ref, {element:chosen.button, kind, root:chosen.root});
      controls[kind] = {ref, enabled:false};
      inventory.push({ref,label:chosen.label,operation:kind,enabled:false});
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
  const marker=document.querySelector('[aria-current="step"]') || document.querySelector('[data-automation-id="progressBarActiveStep"]') || document.querySelector('[data-automation-id="activeStep"]');
  const stepHeadings=[...document.querySelectorAll('h1,h2,h3')].filter(visible).filter(el=>
    el.getAttribute('role')!=='alert' && !el.getAttribute('aria-live') &&
    !(typeof el.closest==='function' && el.closest('[role="alert"],[aria-live],.validation-error,.field-error,.toast,.alert'))
  ).map(el=>(el.textContent||'').trim()).filter(t=>t.length>0 && !/^(application|apply|job application)$/i.test(t)).slice(0,5).map(t=>t.slice(0,160));
  // Logical step identity excludes values, presence, required/invalid flags and
  // validation headings, but distinguishes same-URL SPA headings/form structure.
  const hasRecognizedStep = Boolean(marker || stepHeadings.length > 0);
  const page_signature=await digest([publicUrl,marker?(marker.textContent||'').slice(0,160):stepHeadings,
    hasRecognizedStep?[]:fields.map(({key,type})=>({key,type}))]);
  if(workday){
    scope.page_signature=page_signature;
    const step=stepHeadings.find(t=>/^(?:my information|my experience|application questions|voluntary disclosures|self identify|review)$/i.test(t.trim()));
    scope.autofillPageKey=JSON.stringify([publicUrl,step||marker?.textContent?.trim()||stepHeadings[0]||'application']);
    scope.autofillAttempts=scope.autofillAttempts||new Set();
  }
  const fingerprint=await digest([page_signature,headings,fields,scope.valueEpoch]);
  const fixture=document.body && document.body.textContent && document.body.textContent.includes('Synthetic fixture; not official Simplify support');
  let declared=null;
  if(fixture) {
    for(const r of roots) {
      const d=r.querySelector && r.querySelector('[data-status]')?.getAttribute('data-status');
      if(d) { declared=d; break; }
    }
  }
  const getRenderedText = (root) => {
    if(!root) return '';
    if(document.createTreeWalker&&typeof NodeFilter!=='undefined'){
      const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),parts=[];let n;
      while(n=walker.nextNode())if(n.parentElement&&!n.parentElement.closest('style,script,[hidden]')&&visible(n.parentElement))parts.push(n.textContent);
      return parts.join(' ').replace(/\s+/g,' ').trim();
    }
    if(typeof root.querySelectorAll === 'function') {
      const all = root.querySelectorAll('*');
      if(all && all.length > 0) {
        const parts = [];
        for(const el of all) {
          if(visible(el)) {
            const t = (el.innerText !== undefined ? el.innerText : el.textContent) || '';
            if(t) parts.push(t);
          }
        }
        if(parts.length > 0) return parts.join(' ');
      }
    }
    return (root.innerText !== undefined ? root.innerText : root.textContent) || '';
  };
  let status='missing';
  let login_kind=null;
  let reviewCount=null;
  let activity={busy_indicator:false,explicit_writer:false,waiting_for_input:false};
  const rendered=new Map(roots.map(r=>[r,getRenderedText(r)]));
  const review_items=[];
  for(const root of roots){
    const heading=[...root.querySelectorAll('h1,h2,h3,h4,[role="heading"]')].find(e=>/need(?:s)?\s+(?:to\s+)?review/i.test(e.textContent||''));
    const list=heading?.nextElementSibling;
    if(list)for(const row of list.querySelectorAll('li,[role="listitem"]')){
      if(visible(row)){const label=(row.innerText||row.textContent||'').replace(/\s+/g,' ').trim();if(label)review_items.push({label:label.slice(0,300)});}
    }
  }
  if(roots.length > 0) {
    let hasActive=false, hasReview=false, hasComplete=false, hasLogin=false, hasUnsupported=false;
    for(const r of roots) {
      const busy = (typeof r.querySelector==='function') ? r.querySelector('[aria-busy="true"]') : null;
      const text = rendered.get(r);
      if(busy || /autofilling|filling your application|autofill in progress|stop account step|creating (?:your )?account/i.test(text)) hasActive=true;
      if(/filling your application|autofill in progress|stop (?:account step|autofill)|creating (?:your )?account/i.test(text)) activity.explicit_writer=true;
      const mInput = text.match(/(\d+)\s+fields?\s+need(?:s)?\s+(?:your\s+input|review)/i);
      const mReviewParen = text.match(/need(?:s)?\s+(?:to\s+)?review\s*\((\d+)\)/i);
      const mReviews = text.match(/(\d+)\s+reviews?/i);
      if(mInput) {
        reviewCount = parseInt(mInput[1], 10);
      } else if(mReviewParen) {
        reviewCount = parseInt(mReviewParen[1], 10);
      } else if(mReviews) {
        reviewCount = parseInt(mReviews[1], 10);
      }
      if(reviewCount !== null) {
        if(reviewCount > 0) hasReview = true;
        else if(reviewCount === 0) hasComplete = true;
      } else if(/need(?:s)?\s+(?:to\s+)?review/i.test(text)) {
        hasReview = true;
      }
      if(/autofill complete|application autofilled|application submitted/i.test(text)) hasComplete=true;
      if(/sign in to simplify|log in to simplify/i.test(text)) hasLogin=true;
      if(/not supported|autofill unavailable/i.test(text)) hasUnsupported=true;
    }
    const hasAccountControls = Boolean(
      controls.create_account_autofill.enabled || controls.create_account.enabled || controls.sign_in.enabled ||
      candidates.create_account_autofill.length > 0 || candidates.create_account.length > 0 || candidates.sign_in.length > 0
    );
    login_kind=hasLogin?'simplify':inventory.some(c=>/^(?:sign in|create account) (&|and) autofill$/.test(c.label))?'employer':hasAccountControls?'unknown':null;
    // A panel spinner is not the state of an enabled input prompt. Skills can
    // require another click while the surrounding panel continues to animate.
    const inputReady=['autofill','autofill_skills','continue','start','create_account_autofill','sign_in']
      .some(k=>controls[k].enabled);
    activity.busy_indicator=hasActive;
    activity.waiting_for_input=inputReady&&!activity.explicit_writer&&
      (controls.autofill_skills.enabled||!roots.some(r=>/autofilling/i.test(getRenderedText(r))));
    if(hasActive&&!activity.waiting_for_input) status='active';
    else if(hasLogin || hasAccountControls) status='login_required';
    else if(controls.autofill_skills.enabled) status='ready';
    else if(hasReview) status='needs_review';
    else if(hasComplete) status='complete';
    else if(hasUnsupported) status='unsupported';
    else if(controls.continue.enabled || controls.submit.enabled) status='complete';
    else if(controls.autofill.enabled || controls.start.enabled) status='ready';
    else status='unknown';
    if(declared && ['ready','active','complete','needs_review','unsupported','login_required'].includes(declared)) status=declared;
  }
  if(receipt&&status==='active'){
    if(receipt.state==='none'){receipt.external_pass_observed=true;receipt.automatic_count=Math.max(1,receipt.automatic_count);receipt.started_at=Date.now();}
    receipt.state='active';receipt.saw_activity=true;
  }
  if(!workday&&!greenhouse&&status==='active'){writer.participant=true;writer.pending=true;writer.terminal=false;writer.saw_active=true;}
  // Completion evidence cannot override a concurrently observed active writer.
  const terminal=roots.some(r=>/autofill complete|application autofilled|\d+\s+fields?\s+needs?\s+(?:review|your input)/i.test(rendered.get(r)))&&status!=='active';
  if(terminal&&(!writer.pending||writer.saw_active||writer.dispatch_fingerprint&&writer.dispatch_fingerprint!==fingerprint)){writer.terminal=true;writer.pending=false;}
  scope.last_fingerprint=fingerprint;
  return {url:publicUrl,page_ref:scope.id,page_signature,fingerprint,panel:roots.length>0,status,controls,inventory,login_kind,
    writer_document_id:writer.document_id,writer_participant:writer.participant,writer_pending:writer.pending,
    terminal_evidence:terminal,settled_evidence:writer.terminal&&!writer.pending,review_items,
    review_items_unavailable:!review_items.length,
    ...(greenhouse?{greenhouse:true,document_id:documentId,autofill_receipt:{...receipt,pending_age_ms:receipt.started_at?Math.max(0,Date.now()-receipt.started_at):0}}:{}),
    ...(workday?{workday:true,autofill_page_key:scope.autofillPageKey,autofill_attempted:scope.autofillAttempts.has(scope.autofillPageKey)}:{}),
    native_authentication_required:scope.nativeAuthenticationRequired()||workday&&
      ['sign_in','create_account','create_account_autofill'].some(k=>controls[k].enabled),
    panel_text:roots.map(r=>rendered.get(r)).join(' ').replace(/\s+/g,' ').slice(0,2200),
    review_count:reviewCount,writer_safe:status!=='active'&&status!=='unknown',activity,
    source:fixture?'fixture':'observed_dom',field_summary:{visible:fields.length,required:fields.filter(x=>x.required).length,invalid:fields.filter(x=>x.invalid).length}};
})()
