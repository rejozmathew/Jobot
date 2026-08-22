const esc=(s)=>String(s||'').replace(/[.*+?^${}()|[\\]]/g,'\\$&');
console.log(typeof esc);