"""Fill My Information text fields + select 'No' previous-worker radio.
React-safe value setting. Same tab -> state persists."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

FIRST="Rejo"; LAST="Mathew"
CITY="Wheeling"; ZIP="60090"; ADDR="395 Oak Creek Dr"
PHONE="7074567356"

JS = r"""
(args) => {
  const setVal = (sel, val) => {
    const el = document.querySelector(sel);
    if(!el) return {ok:false, reason:'missing:'+sel};
    const proto = el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto,'value').set;
    el.focus();
    setter.call(el, val);
    el.dispatchEvent(new Event('input',{bubbles:true}));
    el.dispatchEvent(new Event('change',{bubbles:true}));
    el.blur();
    return {ok:true, sel, val: el.value};
  };
  const results = [];
  results.push(setVal('#name--legalName--firstName', args.first));
  results.push(setVal('#name--legalName--lastName', args.last));
  results.push(setVal('#address--city', args.city));
  results.push(setVal('#address--postalCode', args.zip));
  results.push(setVal('#address--addressLine1', args.addr));
  results.push(setVal('#phoneNumber--phoneNumber', args.phone));
  // Previous worker radio = No (false)
  const noRadio = document.querySelector('input[name="candidateIsPreviousWorker"][value="false"]');
  let radio = {ok:false};
  if(noRadio){
    noRadio.click();
    noRadio.dispatchEvent(new Event('click',{bubbles:true}));
    noRadio.dispatchEvent(new Event('change',{bubbles:true}));
    radio = {ok:true, checked: noRadio.checked};
  }
  return JSON.stringify(results.concat([radio]));
}
"""
async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    r = await page.evaluate(JS, {"first":FIRST,"last":LAST,"city":CITY,"zip":ZIP,"addr":ADDR,"phone":PHONE})
    print(r)
asyncio.run(main())
