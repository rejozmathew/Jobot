(args) => {
  // jobbot:simplify:click — only the freshly observed extension control.
  const scope=window.__jobbotSimplifyScope;
  if(!scope || scope.url!==location.href || (args.page_ref && scope.id!==args.page_ref) || location.origin+location.pathname!==args.url)
    return {status:'stale',reason:'page_changed',clicked:false};
  if(scope.workday&&args.page_signature&&scope.page_signature!==args.page_signature)
    return {status:'stale',reason:'page_changed',clicked:false};
  const found=scope.controls.get(args.ref);
  if(!found || found.kind!==args.operation || !found.element.isConnected)
    return {status:'stale',reason:'control_changed',clicked:false};
  if(scope.workday&&found.kind!=='stop'&&found.kind!=='other'&&
      (scope.nativeAuthenticationRequired?.()||['sign_in','create_account','create_account_autofill'].includes(found.kind)))
    return {status:'native_authentication_required',reason:'workday_native_authentication_required',clicked:false};
  // Click path root validation: control must be rooted in an active Simplify host
  const el=found.element;
  const rootNode=typeof el.getRootNode==='function'?el.getRootNode():found.root;
  const host=rootNode && (rootNode.host || (rootNode.classList?.contains('simplify-jobs-shadow-root') ? rootNode : null));
  if(host) {
    const isSimplify=(typeof host.matches==='function'&&host.matches('.simplify-jobs-shadow-root'))||(host.classList&&host.classList.contains('simplify-jobs-shadow-root'));
    if(!host.isConnected || !isSimplify) return {status:'stale',reason:'control_changed',clicked:false};
  }
  const rect=el.getBoundingClientRect();
  if(el.disabled || el.getAttribute('aria-disabled')==='true' || !rect.width || !rect.height)
    return {status:'disabled',reason:'control_disabled',clicked:false};
  if(scope.workday&&found.kind==='autofill'){
    scope.autofillAttempts=scope.autofillAttempts||new Set();
    if(scope.autofillAttempts.has(scope.autofillPageKey)&&!args.retry)
      return {status:'already_attempted',reason:'autofill_already_attempted_on_page',clicked:false};
    // Receipt precedes dispatch; field changes and new CDP connections do not
    // turn a completed (or uncertain) fill into a new first fill on this page.
    scope.autofillAttempts.add(scope.autofillPageKey);
  }
  const receipt=scope.greenhouse&&found.kind==='autofill'?scope.greenhouseReceipt:null;
  if(!scope.workday&&!scope.greenhouse&&found.kind==='autofill'){
    scope.writer.autofillSteps=scope.writer.autofillSteps||new Set();
    scope.writer.autofillSteps.add(scope.autofillPageKey);
  }
  if(receipt){
    receipt.state='dispatching';receipt.started_at=Date.now();receipt.saw_activity=false;
  }
  if(scope.writer&&!scope.workday&&!scope.greenhouse&&['autofill','autofill_skills','sign_in','create_account_autofill'].includes(found.kind)){
    scope.writer.operation=found.kind;
    scope.writer.participant=true;scope.writer.pending=true;scope.writer.terminal=false;scope.writer.saw_active=false;scope.writer.dispatch_fingerprint=scope.last_fingerprint;
  }
  try{el.click();}catch(error){
    if(receipt)receipt.state='uncertain';
    return {status:'uncertain',reason:'autofill_dispatch_uncertain'};
  }
  if(receipt){
    receipt.dispatch_count++;receipt.automatic_count++;
    receipt.state='dispatched';
  }
  return {status:'clicked',clicked:true};
}
