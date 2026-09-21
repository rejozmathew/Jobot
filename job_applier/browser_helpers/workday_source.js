// Workday's recruiting-source prompt only. Never search another field's options.
(args) => {
  const visible=e=>!!e&&e.isConnected&&e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0&&
    getComputedStyle(e).visibility!=='hidden'&&!e.closest('[hidden]');
  const text=e=>(e?.innerText||e?.textContent||'').replace(/\s+/g,' ').trim();
  const enabled=e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true';
  const question=/how (?:did|do) you (?:hear|learn|find out) about us/i;
  const native=e=>!e.closest('.simplify-jobs-shadow-root,[id*="simplify"],[class*="simplify"]');
  const fields=[...document.querySelectorAll('[data-automation-id^="formField"],fieldset')]
    .filter(e=>visible(e)&&native(e)&&question.test(text(e.querySelector('label,legend,[data-automation-id="questionLabel"]'))));
  const roots=fields.filter(e=>!fields.some(other=>other!==e&&e.contains(other)));
  if(roots.length!==1)return {found:false,reason:roots.length?'source_field_ambiguous':'source_field_absent'};
  const root=roots[0],controls=[...root.querySelectorAll('input:not([type="hidden"]),select,button,[role="combobox"]')]
    .filter(e=>visible(e)&&enabled(e)&&!['checkbox','radio'].includes(e.type));
  const field=controls.find(e=>e.tagName==='SELECT')||controls.find(e=>e.getAttribute('role')==='combobox')||
    controls.find(e=>e.tagName==='INPUT')||controls.find(e=>e.getAttribute('aria-haspopup'));
  if(!field)return {found:false,reason:'source_control_unrecognized'};
  const placeholder=t=>!t||/^(?:search|select(?: one)?|please select|choose(?: an? option)?)[.\s…]*$/i.test(t);
  const menuSelector='[role="listbox"],[role="menu"],[data-automation-id="promptOptions"]';
  const menus=()=>[...document.querySelectorAll(menuSelector)].filter(e=>visible(e)&&native(e));
  const scope=window.__jobbotWorkdayScope;
  const selected=scope?.selectedValue?.(field)||[...root.querySelectorAll('[data-automation-id^="selectedItem"],[data-automation-id^="promptSelectedOption"],[data-automation-id^="promptSelection"]')]
    .filter(e=>visible(e)&&!e.querySelector('[data-automation-id="promptOptions"],[role="menu"]')).map(text).find(t=>!placeholder(t));
  const fieldValue=field.tagName==='SELECT'?(field.value?text(field.selectedOptions[0]):''):
    field.value||(!['INPUT','TEXTAREA'].includes(field.tagName)?text(field):'');
  // We never type a search query: a closed prompt's value or selected chip is
  // field evidence. A highlighted parent or radio in the open menu is not.
  const filled=!!selected||!placeholder(fieldValue)&&field.getAttribute('aria-expanded')!=='true'&&
    !menus().some(e=>root.contains(e));
  if(!scope||scope.url!==location.href)return {found:true,filled,reason:'source_scope_unavailable'};
  const remember=e=>{const ref='wd:'+crypto.randomUUID();scope.inventory.set(ref,e);return ref;};
  const info={found:true,filled,value:selected||fieldValue,field_key:root.getAttribute('data-automation-id')||field.id||'recruiting_source'};
  if(args.method==='inspect')return info;
  if(filled)return {...info,kind:'done'};
  let state=window.__jobbotWorkdaySource;
  if(args.method==='begin'&&(!state||state.url!==location.href||state.field_key!==info.field_key)){
    state={url:location.href,field_key:info.field_key,before:menus(),opened:false};
    window.__jobbotWorkdaySource=state;
  }
  if(!state||state.url!==location.href||state.field_key!==info.field_key)return {...info,kind:'blocked',reason:'source_scope_changed'};
  if(args.method==='reopen')state.opened=false;
  if(field.tagName==='SELECT')return {...info,kind:'native',ref:remember(field),options:[...field.options]
    .filter(e=>!e.disabled&&!e.parentElement.disabled&&e.value&&!placeholder(text(e)))
    .map(e=>({label:text(e),value:e.value,child:false}))};
  const ids=controls.flatMap(e=>((e.getAttribute('aria-controls')||'')+' '+(e.getAttribute('aria-owns')||'')).split(/\s+/)).filter(Boolean);
  let associated=menus().filter(e=>root.contains(e)||ids.includes(e.id)||
    (e.getAttribute('aria-labelledby')||'').split(/\s+/).some(id=>controls.some(c=>c.id&&c.id===id)));
  if(!associated.length&&state.opened){
    // Only a newly opened, geometrically anchored popup can be used when this
    // tenant omits ARIA ownership. An already open phone/country menu is excluded.
    const r=field.getBoundingClientRect();
    associated=menus().filter(e=>!state.before.includes(e)&&(()=>{
      const m=e.getBoundingClientRect();return m.right>r.left&&m.left<r.right&&
        (Math.abs(m.top-r.bottom)<80||Math.abs(m.bottom-r.top)<80);
    })());
  }
  associated=associated.filter(e=>!associated.some(other=>other!==e&&other.contains(e)));
  if(associated.length>1)return {...info,kind:'blocked',reason:'source_menu_ambiguous'};
  if(!associated.length){
    if(state.opened)return {...info,kind:'waiting'};
    state.opened=true;
    const opener=controls.find(e=>e.getAttribute('aria-haspopup')||e.getAttribute('role')==='combobox')||field;
    return {...info,kind:'open',ref:remember(opener)};
  }
  const menu=associated[0];
  const selector='[role="option"],[role="menuitem"],[data-automation-id="promptOption"],[role="radio"],input[type="radio"]';
  const candidates=[...menu.querySelectorAll(selector+',label')].filter(e=>visible(e)&&enabled(e)&&
    (e.tagName!=='LABEL'||e.querySelector('input[type="radio"],[role="radio"]')||e.control?.type==='radio'));
  const rows=candidates.filter(e=>!candidates.some(other=>other!==e&&other.contains(e)));
  const options=rows.map(row=>{
    const radio=row.matches('input[type="radio"],[role="radio"]')?row:row.querySelector('input[type="radio"],[role="radio"]');
    const arrow=row.querySelector('[data-automation-id*="chevronRight" i],[data-automation-id*="rightArrow" i],[data-automation-id*="icon-chevron-right" i]');
    const child=!radio&&(!!arrow||row.getAttribute('aria-haspopup')==='true'||row.getAttribute('aria-haspopup')==='menu'||
      row.getAttribute('aria-expanded')!==null||!!row.querySelector('[data-automation-id*="chevron" i]'));
    const radioLabel=radio&&([...(radio.labels||[])].find(e=>menu.contains(e))||radio.closest('label')||
      [...row.querySelectorAll('label')].find(e=>radio.id&&e.htmlFor===radio.id));
    const target=child&&visible(arrow)?arrow:visible(radioLabel)?radioLabel:visible(radio)?radio:row;
    const label=text(row)||text(radioLabel)||radio?.getAttribute('aria-label')||'';
    return {ref:remember(target),label,child};
  }).filter(o=>!placeholder(o.label)&&!/^back\b/i.test(o.label));
  // Virtualized rows must be mounted by scrolling this popup, never the page or
  // a global role=option list. Retain the same menu association on the next poll.
  if(args.method==='scroll'){
    const scroll=[menu,...menu.querySelectorAll('*')].find(e=>visible(e)&&e.scrollHeight>e.clientHeight+2&&
      /auto|scroll/.test(getComputedStyle(e).overflowY));
    if(!scroll)return {...info,kind:'blocked',reason:'source_options_exhausted'};
    const before=scroll.scrollTop;scroll.scrollTop=Math.min(before+Math.max(80,scroll.clientHeight*.8),scroll.scrollHeight-scroll.clientHeight);
    return {...info,kind:scroll.scrollTop>before?'scrolled':'blocked',reason:'source_options_exhausted'};
  }
  return {...info,kind:options.length?'options':'waiting',options,signature:JSON.stringify(options.map(o=>[o.label,o.child]))};
}
