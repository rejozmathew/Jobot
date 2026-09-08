// Transient confirmation collector, installed before the one submit action.
(args) => {
 const name=args.name;
 if(args.operation==='stop'){window[name]?.observer?.disconnect();return true;}
 if(args.operation==='read')return window[name]?.records||[];
 if(args.operation==='start'){if(window[name])window[name].active=true;return true;}
 const visible=e=>!!e&&e.isConnected&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
 const clean=e=>(e.innerText||e.textContent||'').replace(/\s+/g,' ').trim();
 const success=/\b(?:your\s+)?application\s+(?:(?:has been|was|is)\s+)?(?:successfully\s+)?(?:submitted|received)\b|\bthank you for (?:applying|your application)\b|\byou(?:'ve| have) successfully applied\b/i;
 const baseline=new Set(args.baseline||[]),seen=new Set();
 const state={records:[],active:!!args.active,observer:null};window[name]=state;
 const scan=()=>{
  const roots=[{root:document,source:'employer'}];
  for(const host of document.querySelectorAll('.simplify-jobs-shadow-root'))roots.push({root:host.shadowRoot||host,source:'simplify'});
  const found=[];
  for(const {root,source} of roots){
   for(const el of root.querySelectorAll('h1,h2,h3,p,[role="alert"],[role="status"],[aria-live],div,span')){
    if(!visible(el)||el.matches('button,a,[role="button"]')||el.closest('button,a,[role="button"]'))continue;
    if(source==='employer'&&el.closest('.simplify-jobs-shadow-root'))continue;
    const text=clean(el);if(text.length>700||!success.test(text))continue;
    const row=el.closest('tr,[role="row"],[data-automation-id="applicationCard"]');
    if(row&&args.requisition&&!clean(row).includes(args.requisition))continue;
    if(source==='employer'&&/\/(?:candidatehome|userhome)(?:\/|$)/i.test(location.pathname)&&!row&&
       !el.closest('[role="alert"],[role="status"],[role="dialog"],[aria-live]'))continue;
    // Prefer the smallest message, not an ancestor containing all form text.
    if([...el.children].some(c=>visible(c)&&success.test(clean(c))))continue;
    const key=source+':'+text;found.push(key);
    if(!state.active||baseline.has(key)||seen.has(key))continue;
    seen.add(key);
    const item={source,text,url:location.href,observed_at:new Date().toISOString()};
    state.records.push(item);
    if(typeof window[args.binding]==='function')window[args.binding](JSON.stringify(item));
   }
  }
  return found;
 };
 const existing=scan();
 if(!args.active)existing.forEach(k=>baseline.add(k));
 state.observer=new MutationObserver(scan);
 const observe=()=>{
  if(document.documentElement)state.observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['class','style','hidden','aria-hidden']});
  for(const host of document.querySelectorAll('.simplify-jobs-shadow-root'))if(host.shadowRoot)state.observer.observe(host.shadowRoot,{subtree:true,childList:true,characterData:true,attributes:true});
  scan();
 };
 if(document.documentElement)observe();else document.addEventListener('DOMContentLoaded',observe,{once:true});
 // Extensions can mount their shadow root after the document observer starts.
 const timer=setInterval(()=>{if(window[name]!==state){clearInterval(timer);return;}observe();},250);
 state.observerStop=()=>{state.observer.disconnect();clearInterval(timer);};
 return {baseline:existing};
}
