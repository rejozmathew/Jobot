// Only a unique native action returned by workday_observe, on the same step/URL.
(args) => {
 const scope=window.__jobbotWorkdayScope;
 let selectorElement;
 if(args.selector){
  if(args.expected_url!==location.href)return {clicked:false,reason:'stale_page'};
  const matches=document.querySelectorAll(args.selector);
  if(matches.length!==1)return {clicked:false,reason:'ambiguous_or_stale_control'};
  selectorElement=matches[0];
 }else{
  if(!scope||scope.url!==location.href||scope.step!==args.step)return {clicked:false,reason:'stale_page'};
  if(args.page_signature&&scope.page_signature!==args.page_signature)return {clicked:false,reason:'stale_screen',execution:'not_executed'};
 }
 const fields=args.fields||[];
 const selected=[];
 for(const field of fields){
  const e=scope.inventory?.get(field.ref);
  if(!e||!e.isConnected||e.disabled||e.readOnly||!e.getClientRects().length)
    return {clicked:false,reason:'mapped_field_unavailable',execution:'not_executed'};
  if(!['INPUT','TEXTAREA','SELECT'].includes(e.tagName)||e.type==='password'||
    /otp|one.?time|verification.?code/i.test(e.name+' '+e.autocomplete+' '+e.getAttribute('aria-label')))
    return {clicked:false,reason:'mapped_field_requires_private_helper',execution:'not_executed'};
  if(e.tagName==='SELECT'&&![...e.options].some(o=>o.value===field.value&&!o.disabled))
    return {clicked:false,reason:'mapped_option_unavailable',execution:'not_executed'};
  if((['checkbox','radio'].includes(e.type)&&typeof field.value!=='boolean')||
    (!['checkbox','radio'].includes(e.type)&&typeof field.value!=='string'))
    return {clicked:false,reason:'invalid_mapped_value',execution:'not_executed'};
  selected.push({e,value:field.value});
 }
 const el=selectorElement||scope.controls.get(args.ref)||scope.inventory?.get(args.ref);
 if(args.validate_only)return {validated:!args.ref||!!el&&el.isConnected,execution:'not_executed'};
 if(args.fill_only){
  for(const {e,value} of selected){
   if(['checkbox','radio'].includes(e.type)){if(e.checked!==value)e.click();}
   else{
    const proto=e.tagName==='SELECT'?HTMLSelectElement.prototype:e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto,'value').set.call(e,value);
    e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));e.blur();
   }
  }
  return {values_committed:selected.every(({e,value})=>e.isConnected&&(['checkbox','radio'].includes(e.type)?e.checked:e.value)===value),execution:'fields_written'};
 }
 if(!el||!el.isConnected||el.disabled||el.getAttribute('aria-disabled')==='true')return {clicked:false,reason:'stale_control'};
 if(args.prepare_pointer)el.scrollIntoView({block:'center',inline:'center',behavior:'instant'});
 const r=el.getBoundingClientRect();
 if(!r.width||!r.height)return {clicked:false,reason:'hidden_control'};
 if(args.prepare_pointer){
  const left=Math.max(0,r.left),right=Math.min(innerWidth,r.right),top=Math.max(0,r.top),bottom=Math.min(innerHeight,r.bottom);
  if(right<=left||bottom<=top)return {clicked:false,reason:'outside_viewport'};
  const x=(left+right)/2,y=(top+bottom)/2,hit=document.elementFromPoint(x,y);
  if(!hit||!(hit===el||el.contains(hit)))return {clicked:false,reason:'control_obscured'};
  return {pointer_ready:true,x,y};
 }
 el.click();return {clicked:true,execution:'clicked'};
}
