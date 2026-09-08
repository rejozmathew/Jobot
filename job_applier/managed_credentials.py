"""Fill private credentials into controls selected from Hermes's current page."""
import asyncio
import json
from pathlib import Path

from .cdp_client import CDPBrowser
from .managed_identity import is_same_application_scope


FILL_SELECTED = r"""async (args) => {
 const result={email_filled:false,passwords_filled_count:0,
   confirmation_present:!!args.confirmation_ref,values_committed:false,
   account_mode:args.confirmation_ref?'create-account':'sign-in',error:null};
 const selected=[];
 for(const [role,ref] of [['email',args.email_ref],['password',args.password_ref],
                         ['confirmation',args.confirmation_ref]]) {
   if(role==='confirmation'&&!ref)continue;
   if(!ref)return {...result,error:'missing_'+role+'_ref'};
   let matches;
   try {matches=document.querySelectorAll(ref);}catch{return {...result,error:'invalid_'+role+'_ref'};}
   if(matches.length!==1)return {...result,error:'ambiguous_or_stale_'+role+'_ref',match_count:matches.length};
   const e=matches[0],r=e.getBoundingClientRect();
   if(e.tagName!=='INPUT'||!e.isConnected||!r.width||!r.height||getComputedStyle(e).visibility==='hidden'||e.disabled||e.readOnly)
     return {...result,error:'unavailable_'+role+'_control'};
   if((role!=='email'&&e.type!=='password')||(role==='email'&&!['email','text'].includes(e.type)))
     return {...result,error:'incorrect_'+role+'_control_type'};
   if(selected.some(x=>x.e===e))return {...result,error:'duplicate_control_ref'};
   selected.push({role,e,value:role==='email'?args.email:args.password});
 }
 const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
 for(const {e,value} of selected){
   e.focus();setter.call(e,value);
   e.dispatchEvent(new Event('input',{bubbles:true}));
   e.dispatchEvent(new Event('change',{bubbles:true}));e.blur();
 }
 await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
 for(const {role,e,value} of selected){
   const ok=e.isConnected&&e.value===value;
   if(role==='email')result.email_filled=ok;
   else if(ok)result.passwords_filled_count++;
 }
 result.values_committed=selected.every(({e,value})=>e.isConnected&&e.value===value);
 if(!result.values_committed)result.error='values_not_committed';
 return result;
}"""


async def fill_credentials(config, package, params):
    """Selectors are observed control references, never inferred by this helper."""
    allowed = {'target_id', 'email_ref', 'password_ref', 'confirmation_ref'}
    if set(params) - allowed:
        return {'error': 'invalid_credential_parameters'}
    raw = json.loads(Path(config['credential_profile_path']).read_text(encoding='utf-8'))
    account = raw.get('accounts', {}).get('default', {})
    if not account.get('email') or not account.get('password'):
        return {'error': 'configured_credentials_unavailable'}
    profile = package['attempt']['profile_json']
    if isinstance(profile, str):
        profile = json.loads(profile)
    if profile.get('identity', {}).get('email', '').casefold() != account['email'].casefold():
        return {'error': 'candidate_credential_identity_mismatch'}
    browser = await CDPBrowser.connect(config.get('cdp_url', 'http://127.0.0.1:9222'),
                                       target_id=params['target_id'], expected_mode='headed')
    try:
        page = await browser.get_current_page()
        url = await page.evaluate('location.href')
        if not is_same_application_scope(package['job']['url'], url):
            return {'error': 'credential_target_scope_mismatch'}
        return await page.evaluate(FILL_SELECTED, dict(params, email=account['email'], password=account['password']))
    finally:
        await browser.close()


def handle_credentials(config, package, params):
    try:
        return asyncio.run(fill_credentials(config, package, params))
    except Exception as exc:
        # Browser/transport exceptions can contain the evaluation arguments.
        return {'error': 'credential_transport_failed', 'error_type': type(exc).__name__,
                'values_committed': False}
