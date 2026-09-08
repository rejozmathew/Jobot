// Only a unique native action returned by workday_observe, on the same step/URL.
(args) => {
 const scope=window.__jobbotWorkdayScope;
 if(!scope||scope.url!==location.href||scope.step!==args.step)return {clicked:false,reason:'stale_page'};
 const el=scope.controls.get(args.ref);
 if(!el||!el.isConnected||el.disabled||el.getAttribute('aria-disabled')==='true')return {clicked:false,reason:'stale_control'};
 const r=el.getBoundingClientRect();
 if(!r.width||!r.height)return {clicked:false,reason:'hidden_control'};
 el.click();return {clicked:true};
}
