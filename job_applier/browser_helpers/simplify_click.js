(args) => {
  // jobbot:simplify:click — only the freshly observed extension control.
  const scope=window.__jobbotSimplifyScope;
  if(!scope || scope.url!==location.href || (args.page_ref && scope.id!==args.page_ref) || location.origin+location.pathname!==args.url)
    return {status:'stale',reason:'page_changed',clicked:false};
  const found=scope.controls.get(args.ref);
  if(!found || found.kind!==args.operation || !found.element.isConnected)
    return {status:'stale',reason:'control_changed',clicked:false};
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
  el.click();
  return {status:'clicked',clicked:true};
}
