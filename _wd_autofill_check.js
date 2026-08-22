
            (payload) => {
              const n=(s)=>(s||'').toLowerCase().replace(/[\\u2018\\u2019]/g,"'").replace(/[\\u201C\\u201D]/g,'"').replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const d=(el)=>{
                const container=el&&el.closest?el.closest('[data-automation-id*="formField"],[data-automation-id*="question"],fieldset,section,li,div'):null;
                const containerText=n((container&&container.textContent)||'').slice(0,480);
                const parentText=n((el&&el.parentElement&&el.parentElement.textContent)||'').slice(0,280);
                return n([
                  el.getAttribute&&el.getAttribute('name')||'',
                  el.getAttribute&&el.getAttribute('id')||'',
                  el.getAttribute&&el.getAttribute('aria-label')||'',
                  el.getAttribute&&el.getAttribute('placeholder')||'',
                  (el.labels&&el.labels[0]&&el.labels[0].textContent)||'',
                  parentText,
                  containerText,
                ].join(' '));
              };
              const click=(el)=>{if(!el)return false;try{el.scrollIntoView({block:'center',inline:'nearest'});}catch(e){}try{el.focus&&el.focus();}catch(e){}try{el.click();}catch(e){}try{el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,composed:true}));}catch(e){}return true;};
              const dispatch=(el)=>{try{el.dispatchEvent(new Event('input',{bubbles:true}));}catch(e){}try{el.dispatchEvent(new Event('change',{bubbles:true}));}catch(e){}try{el.dispatchEvent(new Event('blur',{bubbles:true}));}catch(e){}};
              const anyKeyword=(text,keywords)=>{const t=n(text);return (keywords||[]).some((k)=>t.includes(n(k)));};
              const isPlaceholder=(text)=>{const t=n(text);return !t||t==='select one'||t==='choose one'||t==='please select'||t==='select'||t==='-- select --';};
              const setInput=(keywords,value,requireEmpty=false)=>{const val=String(value||'').trim();if(!val)return false;const fields=Array.from(document.querySelectorAll('input,textarea,[role="textbox"],[contenteditable="true"]')).filter(v);for(const field of fields.slice(0,220)){const desc=d(field);if(!anyKeyword(desc,keywords))continue;const type=n(field.getAttribute&&field.getAttribute('type'));if(['hidden','checkbox','radio','file','button','submit'].includes(type))continue;const current=n(('value' in field?field.value:field.textContent)||'');if(requireEmpty&&current)continue;click(field);try{if('value' in field){field.value='';field.value=val;}else{field.textContent=val;}}catch(e){}dispatch(field);const after=n(('value' in field?field.value:field.textContent)||'');if(after.includes(n(val).slice(0,6)))return true;}return false;};
              const pickOption=(candidates,allowFallback=false)=>{const options=Array.from(document.querySelectorAll('[role="listbox"] [role="option"],[role="option"],li[role="option"],div[role="option"],[data-automation-id*="menuItem"]')).filter(v);for(const desired of (candidates||[])){const key=n(desired);if(!key)continue;const hit=options.find((opt)=>{const txt=n(opt.textContent||'');return txt===key||txt.startsWith(key+' ')||txt.includes(' '+key+' ');});if(hit){click(hit);return n(hit.textContent||desired);}}if(allowFallback){const first=options.find((opt)=>!isPlaceholder(opt.textContent||''));if(first){click(first);return n(first.textContent||'');}}return '';};
              const setSelectOrCombo=(keywords,values)=>{
                const fields=Array.from(document.querySelectorAll('select,input,[role="combobox"],[aria-haspopup="listbox"],[data-automation-id*="promptSearchInput"],[data-automation-id*="comboBox"]')).filter(v);
                const readFieldValue=(field)=>{
                  const tag=n(field.tagName||'');
                  if(tag==='select'){
                    const so=field.selectedOptions&&field.selectedOptions.length?field.selectedOptions[0]:null;
                    return n((so&&so.textContent)||field.value||'');
                  }
                  const own=n(field.value||field.textContent||field.getAttribute&&field.getAttribute('aria-label')||'');
                  if(own) return own;
                  let sibling=field.previousElementSibling;
                  let siblingHops=0;
                  while(sibling&&siblingHops<6){
                    const raw=n(sibling.textContent||'');
                    const cleaned=n(raw.replace(/\\bx\\b/g,' '));
                    if(cleaned&&!isPlaceholder(cleaned)&&cleaned!=='search') return cleaned;
                    sibling=sibling.previousElementSibling;
                    siblingHops += 1;
                  }
                  const container=field.closest('[data-automation-id*="formField"],fieldset,section,div')||field.parentElement;
                  if(container){
                    const chip=container.querySelector('[data-automation-id*="selected"],[aria-selected="true"],[data-automation-id*="token"],[data-automation-id*="pill"]');
                    const chipText=n(chip&&chip.textContent||'');
                    if(chipText) return chipText;
                  }
                  return '';
                };
                for(const field of fields.slice(0,180)){
                  const desc=d(field);
                  if(!anyKeyword(desc,keywords))continue;
                  const existing=readFieldValue(field);
                  if(!isPlaceholder(existing)) return {changed:false,value:existing,already:true};
                  click(field);
                  if((field.tagName||'').toLowerCase()==='select'&&field.options){
                    const opts=Array.from(field.options||[]);
                    let picked=null;
                    for(const value of (values||[])){
                      const key=n(value);
                      if(!key)continue;
                      picked=opts.find((o)=>{const txt=n(o.textContent||'');const val=n(o.value||'');return txt===key||txt.includes(key)||val.includes(key);});
                      if(picked)break;
                    }
                    if(!picked){
                      picked=opts.find((o)=>!isPlaceholder(o.textContent||'')&&!isPlaceholder(o.value||''));
                    }
                    if(picked){
                      try{field.value=picked.value;}catch(e){}
                      dispatch(field);
                      return {changed:true,value:n(picked.textContent||picked.value||''),already:false};
                    }
                    continue;
                  }
                  const picked=pickOption(values||[],true);
                  if(picked)return {changed:true,value:picked,already:false};
                  const typed=String((values&&values[0])||'').trim();
                  if(typed&&'value' in field){
                    const before=n(field.value||'');
                    if(!before||isPlaceholder(before)){
                      try{field.value=typed;}catch(e){}
                      dispatch(field);
                    }
                    const after=n(field.value||'');
                    if(!isPlaceholder(after)&&after.includes(n(typed).slice(0,5)))return {changed:true,value:after,already:false};
                  }
                }
                return {changed:false,value:'',already:false};
              };
              const setPreviousEmploymentNo=()=>{const questionKeywords=Array.isArray(payload?.questionKeywords)?payload.questionKeywords.map((k)=>n(k)).filter(Boolean):[];const noOptions=Array.isArray(payload?.noOptions)?payload.noOptions.map((k)=>n(k)).filter(Boolean):['no'];const containers=Array.from(document.querySelectorAll('fieldset,section,div,form')).filter(v).filter((el)=>questionKeywords.some((q)=>n(el.textContent||'').includes(q))).slice(0,50);for(const container of containers){const nodes=Array.from(container.querySelectorAll('input[type="radio"],[role="radio"],label,span,button,div')).filter(v).filter((el)=>{const txt=n([el.textContent||'',el.getAttribute&&el.getAttribute('aria-label')||'',el.getAttribute&&el.getAttribute('value')||'',(el.parentElement&&el.parentElement.textContent)||''].join(' '));return noOptions.some((opt)=>txt.includes(opt));});for(const node of nodes.slice(0,16)){if((node.getAttribute&&n(node.getAttribute('type')))==='radio'||node.type==='radio'){try{node.checked=true;}catch(e){}dispatch(node);}click(node);const selected=Array.from(container.querySelectorAll('[role="radio"][aria-checked="true"],input[type="radio"]:checked')).some((sel)=>{const txt=n([sel.textContent||'',sel.getAttribute&&sel.getAttribute('aria-label')||'',sel.getAttribute&&sel.getAttribute('value')||'',(sel.parentElement&&sel.parentElement.textContent)||''].join(' '));return noOptions.some((opt)=>txt.includes(opt));});if(selected)return true;}}return false;};
              const setEeoChoice=(questionKeywords,optionValues)=>{
                const keywords=(questionKeywords||[]).map((k)=>n(k)).filter(Boolean);
                if(!keywords.length) return {changed:false,value:''};
                const options=(optionValues||[]).map((k)=>n(k)).filter(Boolean);
                if(!options.length) return {changed:false,value:''};
                const esc=(s)=>String(s||'').replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
                const matchesOpt=(text,opt)=>{const b=n(text);return b.length>0&&new RegExp('(^|[^a-z])'+esc(opt)+'([^a-z]|$)').test(b);};
                const radioText=(r)=>{
                  let t=n(r.textContent||'');
                  if(!t&&r.labels&&r.labels[0]) t=n(r.labels[0].textContent||'');
                  if(!t&&r.closest){const wrap=r.closest('label');if(wrap)t=n(wrap.textContent||'');}
                  if(!t&&r.getAttribute) t=n(r.getAttribute('aria-label')||'');
                  return t;
                };
                const containers=Array.from(document.querySelectorAll('fieldset,section,div,form')).filter(v).filter((el)=>{const t=n(el.textContent||'');return keywords.some((k)=>t.includes(k));}).slice(0,40);
                const order=(list)=>{if(!list.length)return [];const scored=list.map((item,idx)=>({item,idx,score:options.findIndex((opt)=>item.text.includes(opt))})).sort((a,b)=>{const sa=a.score===-1?99:a.score;const sb=b.score===-1?99:b.score;return sa-sb||a.idx-b.idx;});return scored.map((x)=>x.item);};
                for(const container of containers){
                  const radios=order(Array.from(container.querySelectorAll('input[type="radio"],[role="radio"]')).filter(v).map((r)=>({el:r,text:radioText(r),kind:'radio'})));
                  const checkboxes=order(Array.from(container.querySelectorAll('input[type="checkbox"],[role="checkbox"]')).filter(v).map((c)=>{let t=n(c.textContent||'');if(!t&&c.labels&&c.labels[0])t=n(c.labels[0].textContent||'');if(!t&&c.closest){const w=c.closest('label');if(w)t=n(w.textContent||'');}if(!t&&c.getAttribute)t=n(c.getAttribute('aria-label')||'');return {el:c,text:t,kind:'checkbox'};}));
                  const choices=[...radios,...checkboxes];
                  for(const opt of options){
                    const hit=choices.find((r)=>{const b=n(r.text);return b.length>0&&(b.includes(opt)||matchesOpt(r.text,opt));});
                    if(!hit) continue;
                    if(hit.kind==='radio'){try{hit.el.checked=true;}catch(e){}dispatch(hit.el);}
                    click(hit.el);
                    if(hit.kind==='checkbox'){
                      let checked=false;
                      try{checked=!!hit.el.checked;}catch(e){}
                      if(!checked){try{hit.el.checked=true;}catch(e){}dispatch(hit.el);click(hit.el);try{checked=!!hit.el.checked;}catch(e){}}
                      const label=(hit.el.labels&&hit.el.labels[0])||null;
                      if(label)click(label);
                      if(checked) return {changed:true,value:n(hit.text||opt),kind:'checkbox'};
                      continue;
                    }
                    const label=(hit.el.labels&&hit.el.labels[0])||null;
                    click(label||hit.el);
                    const verified=Array.from(container.querySelectorAll('input[type="radio"]:checked,[role="radio"][aria-checked="true"]')).some((sel)=>{const b=n(radioText(sel));return b.length>0&&(b.includes(opt)||matchesOpt(radioText(sel),opt));});
                    if(verified) return {changed:true,value:n(hit.text||opt),kind:'radio'};
                  }
                }
                return {changed:false,value:'',kind:''};
              };
              const clickContinue=()=>{const nodes=Array.from(document.querySelectorAll('button,[role="button"],input[type="submit"]')).filter(v);const target=nodes.find((el)=>{const txt=n(el.textContent||el.value||el.getAttribute('aria-label')||'');if(!txt)return false;if(!(txt.includes('save and continue')||txt==='continue'||txt.includes('next')))return false;return !(el.disabled||el.getAttribute('aria-disabled')==='true');});if(!target)return false;click(target);return true;};
              const regionsForErrors=(keywords)=>Array.from(document.querySelectorAll('[role="alert"],.error,.field-error,.validation-error,[data-automation-id*="error"]')).filter(v).filter((el)=>anyKeyword(el.textContent||'',keywords)).map((el)=>el.closest('fieldset,section,div,form')||el.parentElement).filter(Boolean);
              const setSelectOrComboInRegion=(regions,optionValues)=>{
                for(const region of (regions||[]).slice(0,20)){
                  const fields=Array.from(region.querySelectorAll('select,input,[role="combobox"],[aria-haspopup="listbox"],[data-automation-id*="promptSearchInput"],[data-automation-id*="comboBox"]')).filter(v);
                  for(const field of fields.slice(0,14)){
                    click(field);
                    if((field.tagName||'').toLowerCase()==='select'&&field.options){
                      const opts=Array.from(field.options||[]);
                      let picked=null;
                      for(const value of (optionValues||[])){const key=n(value);if(!key)continue;picked=opts.find((o)=>{const txt=n(o.textContent||'');const val=n(o.value||'');return txt===key||txt.includes(key)||val.includes(key);});if(picked)break;}
                      if(!picked)picked=opts.find((o)=>!isPlaceholder(o.textContent||'')&&!isPlaceholder(o.value||''));
                      if(picked){try{field.value=picked.value;}catch(e){}dispatch(field);return {changed:true,value:n(picked.textContent||picked.value||'')};}
                    } else {
                      const picked=pickOption(optionValues||[],true);
                      if(picked) return {changed:true,value:picked};
                      const first=String((optionValues&&optionValues[0])||'').trim();
                      if(first&&'value' in field){
                        const before=n(field.value||'');
                        if(!before||isPlaceholder(before)){
                          try{field.value=first;}catch(e){}
                          dispatch(field);
                        }
                        const after=n(field.value||'');
                        if(!isPlaceholder(after)&&after.includes(n(first).slice(0,5))) return {changed:true,value:after};
                      }
                    }
                  }
                }
                return {changed:false,value:''};
              };
              const setPreviousEmploymentNoInRegions=(regions)=>{
                const noOptions=Array.isArray(payload?.noOptions)?payload.noOptions.map((k)=>n(k)).filter(Boolean):['no'];
                for(const region of (regions||[]).slice(0,20)){
                  const nodes=Array.from(region.querySelectorAll('input[type="radio"],[role="radio"],label,span,button,div')).filter(v).filter((el)=>{const txt=n([el.textContent||'',el.getAttribute&&el.getAttribute('aria-label')||'',el.getAttribute&&el.getAttribute('value')||'',(el.parentElement&&el.parentElement.textContent)||''].join(' '));return noOptions.some((opt)=>txt.includes(opt));});
                  for(const node of nodes.slice(0,16)){
                    if((node.getAttribute&&n(node.getAttribute('type')))==='radio'||node.type==='radio'){try{node.checked=true;}catch(e){}dispatch(node);}
                    click(node);
                    const selected=Array.from(region.querySelectorAll('[role="radio"][aria-checked="true"],input[type="radio"]:checked')).some((sel)=>{const txt=n([sel.textContent||'',sel.getAttribute&&sel.getAttribute('aria-label')||'',sel.getAttribute&&sel.getAttribute('value')||'',(sel.parentElement&&sel.parentElement.textContent)||''].join(' '));return noOptions.some((opt)=>txt.includes(opt));});
                    if(selected) return true;
                  }
                }
                return false;
              };
              const setChoiceInRegions=(regions,optionValues)=>{
                const options=(optionValues||[]).map((item)=>n(item)).filter(Boolean);
                if(!options.length) return false;
                for(const region of (regions||[]).slice(0,20)){
                  const nodes=Array.from(region.querySelectorAll('input[type="radio"],[role="radio"],label,span,button,div')).filter(v);
                  for(const node of nodes.slice(0,80)){
                    const txt=n([node.textContent||'',node.getAttribute&&node.getAttribute('aria-label')||'',node.getAttribute&&node.getAttribute('value')||'',(node.parentElement&&node.parentElement.textContent)||''].join(' '));
                    if(!options.some((opt)=>txt===opt||txt.startsWith(opt+' ')||txt.endsWith(' '+opt)||txt.includes(' '+opt+' ')||txt.includes(opt))) continue;
                    if((node.getAttribute&&n(node.getAttribute('type')))==='radio'||node.type==='radio'){try{node.checked=true;}catch(e){}dispatch(node);}
                    click(node);
                    const selected=Array.from(region.querySelectorAll('[role="radio"][aria-checked="true"],input[type="radio"]:checked')).some((sel)=>{
                      const st=n([sel.textContent||'',sel.getAttribute&&sel.getAttribute('aria-label')||'',sel.getAttribute&&sel.getAttribute('value')||'',(sel.parentElement&&sel.parentElement.textContent)||''].join(' '));
                      return options.some((opt)=>st.includes(opt));
                    });
                    if(selected) return true;
                  }
                }
                return false;
              };

              const referralErrors=regionsForErrors(['how did you hear about us','how did you hear','referral','source']);
              const deviceErrors=regionsForErrors(['phone device type','device type']);
              const phoneCodeErrors=regionsForErrors(['country phone code','phone code']);
              const previousEmploymentErrors=regionsForErrors(['previously worked for','worked for','previously employed']);
              const authorizedErrors=regionsForErrors(['authorized to work','work authorization','work in the job']);
              const sponsorshipErrors=regionsForErrors(['visa sponsorship','require sponsorship','sponsorship to work','require visa']);

              const referralFromError=setSelectOrComboInRegion(referralErrors,payload?.referralOptions||[]);
              const deviceFromError=setSelectOrComboInRegion(deviceErrors,payload?.deviceTypeOptions||[]);
              const phoneCodeFromError=setSelectOrComboInRegion(phoneCodeErrors,payload?.countryPhoneCodeOptions||[]);
              const prevSelectFromError=setSelectOrComboInRegion(previousEmploymentErrors,payload?.noOptions||['No']);
              const prevFromError=prevSelectFromError.changed||setPreviousEmploymentNoInRegions(previousEmploymentErrors);
              const authorizedFromError=setSelectOrComboInRegion(authorizedErrors,payload?.authorizedToWorkOptions||[]);
              const sponsorshipFromError=setSelectOrComboInRegion(sponsorshipErrors,payload?.sponsorshipOptions||[]);
              const referral=referralFromError.changed?referralFromError:setSelectOrCombo(['how did you hear about us','how did you hear','referral','source'],payload?.referralOptions||[]);
              const device=deviceFromError.changed?deviceFromError:setSelectOrCombo(['phone device type','device type'],payload?.deviceTypeOptions||[]);
              const phoneCode=phoneCodeFromError.changed?phoneCodeFromError:setSelectOrCombo(['country phone code','phone code'],payload?.countryPhoneCodeOptions||[]);
              const previousEmploymentGeneric=setSelectOrCombo(['previously worked for','worked for','previously employed'],payload?.noOptions||['No']);
              const authorizedGeneric=setSelectOrCombo(['authorized to work','work authorization','work in the job'],payload?.authorizedToWorkOptions||[]);
              const sponsorshipGeneric=setSelectOrCombo(['visa sponsorship','require sponsorship','sponsorship'],payload?.sponsorshipOptions||[]);
              const authorizedChoice=authorizedFromError.changed?true:(setChoiceInRegions(authorizedErrors,payload?.authorizedToWorkOptions||[])||setChoiceInRegions(regionsForErrors(['authorized to work','work authorization']),payload?.authorizedToWorkOptions||[]));
              const sponsorshipChoice=sponsorshipFromError.changed?true:(setChoiceInRegions(sponsorshipErrors,payload?.sponsorshipOptions||[])||setChoiceInRegions(regionsForErrors(['visa sponsorship','require sponsorship','sponsorship']),payload?.sponsorshipOptions||[]));
              const disabilityResult=setEeoChoice(payload?.disabilityQuestionKeywords||[],payload?.disabilityOptions||[]);
              const veteranResult=setEeoChoice(payload?.veteranQuestionKeywords||[],payload?.veteranOptions||[]);
              const hispanicResult=setEeoChoice(payload?.raceQuestionKeywords||[],payload?.hispanicOptions||[]);
              const raceResult=setEeoChoice(['ethnicity','race'],payload?.raceOptions||[]);
              const authorizedSet=!!(authorizedFromError.changed||authorizedGeneric.changed||authorizedChoice);
              const sponsorshipSet=!!(sponsorshipFromError.changed||sponsorshipGeneric.changed||sponsorshipChoice);
              const firstNameSet=setInput(['first name'],payload?.firstName||'',false);
              const lastNameSet=setInput(['last name'],payload?.lastName||'',false);
              const emailSet=setInput(['email'],payload?.email||'',false);
              const phoneSet=setInput(['phone number','phone'],payload?.phone||'',false);
              const addressSet=setInput(['address line 1','street address','address'],payload?.addressLine1||'',false);
              const citySet=setInput(['city'],payload?.city||'',false);
              const stateSelect=setSelectOrCombo(['state','province'],payload?.stateOptions||[]);
              const stateSet=setInput(['state','province'],payload?.state||'',false);
              const postalSet=setInput(['postal code','zip code','zip'],payload?.postalCode||'',false);
              const countrySelect=setSelectOrCombo(['country'],[payload?.country||'United States','United States','US','USA']);
              const prevEmploymentSet=prevFromError||previousEmploymentGeneric.changed||setPreviousEmploymentNo();
              const continued=clickContinue();
              const dateSegs=Array.from(document.querySelectorAll('input[id*="dateSectionMonth-input"],input[id*="dateSectionDay-input"],input[id*="dateSectionYear-input"],input[id*="dateSignedOn-month-input"],input[id*="dateSignedOn-day-input"],input[id*="dateSignedOn-year-input"]')).filter(v);
              const selfIdDatePresent=dateSegs.length>0;
              const eeoSet=!!(disabilityResult.changed||veteranResult.changed||hispanicResult.changed||raceResult.changed);
              const success=!!(referral.changed||device.changed||phoneCode.changed||authorizedSet||sponsorshipSet||firstNameSet||lastNameSet||emailSet||phoneSet||addressSet||citySet||stateSet||stateSelect.changed||postalSet||countrySelect.changed||prevEmploymentSet||eeoSet||continued);
              return {
                success,
                referral_set: !!referral.changed,
                referral_value: referral.value||'',
                device_set: !!device.changed,
                device_value: device.value||'',
                phone_code_set: !!phoneCode.changed,
                phone_code_value: phoneCode.value||'',
                authorized_set: !!authorizedSet,
                sponsorship_set: !!sponsorshipSet,
                first_name_set: !!firstNameSet,
                last_name_set: !!lastNameSet,
                email_set: !!emailSet,
                phone_set: !!phoneSet,
                address_set: !!addressSet,
                city_set: !!citySet,
                state_set: !!stateSet,
                state_select_set: !!stateSelect.changed,
                postal_set: !!postalSet,
                country_set: !!countrySelect.changed,
                previous_employment_set: !!prevEmploymentSet,
                eeo_set: !!eeoSet,
                self_id_date_present: !!selfIdDatePresent,
                disability_set: !!disabilityResult.changed,
                disability_value: disabilityResult.value||'',
                veteran_set: !!veteranResult.changed,
                veteran_value: veteranResult.value||'',
                hispanic_set: !!hispanicResult.changed,
                hispanic_value: hispanicResult.value||'',
                race_set: !!raceResult.changed,
                race_value: raceResult.value||'',
                clicked_continue: !!continued,
              };
            }
            """,
            self._required_field_payload(),
        )
        data = self._as_dict(raw)
        if not data:
            return False, "required-field-autofill-invalid-response"
        if not data.get("success"):
            return False, "required-field-autofill-no-change"
        flags: list[str] = []
        for key in (
            "referral_set",
            "device_set",
            "phone_code_set",
            "authorized_set",
            "sponsorship_set",
            "first_name_set",
            "last_name_set",
            "email_set",
            "phone_set",
            "address_set",
            "city_set",
            "state_set",
            "state_select_set",
            "postal_set",
            "country_set",
            "previous_employment_set",
            "clicked_continue",
        ):
            if data.get(key):
                flags.append(key)
        return True, f"required-field-autofill:{','.join(flags) if flags else 'updated'}"

    async def js_find_visible(self, selectors: list[str], text_hints: list[str] | None = None) -> dict[str, Any]:
        page = await self.browser_session.get_current_page()
        if page is None:
            return {"found": False, "reason": "no-active-page"}
        raw = await page.evaluate(
            """
            (p) => {
              const sels=Array.isArray(p?.selectors)?p.selectors:[];const hints=Array.isArray(p?.text_hints)?p.text_hints:[];
              const n=(s)=>(s||'').toLowerCase().replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const t=(el)=>n(el.textContent||el.value||el.getAttribute('aria-label')||'');
              for(const s of sels){try{const el=Array.from(document.querySelectorAll(s)).find(v);if(el)return {found:true,selector:s,text:t(el)};}catch(e){}}
              if(hints.length){const hs=hints.map(n).filter(Boolean);const el=Array.from(document.querySelectorAll('button,a,[role=\"button\"],[role=\"link\"],input[type=\"submit\"],input[type=\"button\"],span,div')).find((x)=>v(x)&&hs.some((h)=>t(x).includes(h)));if(el)return {found:true,selector:'[text]',text:t(el)};}
              return {found:false};
            }
            """,
            {"selectors": selectors, "text_hints": text_hints or []},
        )
        parsed = self._as_dict(raw)
        return parsed if parsed else {"found": False, "reason": "invalid-response"}

    async def js_dismiss_cookie_banner(self) -> tuple[bool, str]:
        page = await self.browser_session.get_current_page()
        if page is None:
            return False, "no-active-page"
        raw = await page.evaluate(
            """
            () => {
              const n=(s)=>(s||'').toLowerCase().replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const click=(el)=>{if(!el)return false;try{el.scrollIntoView({block:'center',inline:'nearest'});}catch(e){}try{el.focus&&el.focus();}catch(e){}try{el.click();}catch(e){}try{el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,composed:true}));}catch(e){}return true;};
              const text=(el)=>n(el.textContent||el.value||el.getAttribute&&el.getAttribute('aria-label')||'');
              const knownSelectors=[
                '#onetrust-accept-btn-handler',
                '.onetrust-close-btn-handler',
                '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
                '[data-testid=\"cookie-policy-dialog-accept-button\"]',
                '.cc-btn.cc-allow',
                '#accept-cookie-notification',
                '.js-cookie-consent-agree',
                '[data-cookiefirst-action=\"accept\"]',
              ];
              for(const sel of knownSelectors){
                try{
                  const btn=document.querySelector(sel);
                  if(btn&&v(btn)){click(btn);return {success:true,method:'known-selector',label:sel};}
                }catch(e){}
              }

              const keywords=['accept cookies','accept all cookies','accept all','allow all','allow cookies','i agree','agree'];
              const buttons=Array.from(document.querySelectorAll('button,a,[role=\"button\"],input[type=\"button\"],input[type=\"submit\"]')).filter(v);
              for(const btn of buttons){
                const tx=text(btn);
                if(!tx||tx.length>80) continue;
                if(!keywords.some((k)=>tx.includes(k))) continue;
                let inBanner=false;
                let p=btn;
                for(let i=0;i<8&&p;i++){
                  const marker=n([p.className||'',p.id||'',p.getAttribute&&p.getAttribute('role')||'',p.getAttribute&&p.getAttribute('aria-label')||''].join(' '));
                  if(marker.includes('cookie')||marker.includes('consent')||marker.includes('gdpr')||marker.includes('privacy')||marker.includes('banner')||marker==='dialog'||marker==='alertdialog'){
                    inBanner=true;
                    break;
                  }
                  p=p.parentElement;
                }
                if(inBanner||tx.includes('accept cookies')||tx.includes('accept all')){
                  click(btn);
                  return {success:true,method:'keyword-button',label:tx.slice(0,80)};
                }
              }
              return {success:false,reason:'cookie-banner-not-found'};
            }
            