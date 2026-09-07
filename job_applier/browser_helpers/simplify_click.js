(args) => {
  // jobbot:simplify:click — only the freshly observed extension control.
  const scope=window.__jobbotSimplifyScope;
  if(!scope || scope.url!==location.href || (args.page_ref && scope.id!==args.page_ref) || location.origin+location.pathname!==args.url)
    return {status:'stale',reason:'page_changed',clicked:false};
  const found=scope.controls.get(args.ref);
  if(!found || found.kind!==args.operation || !found.element.isConnected)
    return {status:'stale',reason:'control_changed',clicked:false};
  const el=found.element, rect=el.getBoundingClientRect();
  if(el.disabled || el.getAttribute('aria-disabled')==='true' || !rect.width || !rect.height)
    return {status:'disabled',reason:'control_disabled',clicked:false};
  el.click();
  return {status:'clicked',clicked:true};
}
