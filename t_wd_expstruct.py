"""Read the My Experience step structure from tab 0 (the real CDP tab)."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

JS_EXP = """
(() => {
  const out = {heading:null, fields:[], buttons:[], text:[]};
  const h = document.querySelector('h1,h2');
  if (h) out.heading = h.textContent.trim().slice(0,60);
  document.querySelectorAll('input, textarea, select').forEach(el => {
    if (el.type==='hidden'||el.type==='radio'||el.type==='checkbox') return;
    let label='';
    if (el.id) { const lab=document.querySelector('label[for="'+el.id+'"]'); if(lab) label=lab.textContent.trim().slice(0,50); }
    label = label || el.getAttribute('aria-label') || '';
    out.fields.push({tag:el.tagName.toLowerCase(), type:el.type||'', id:el.id||'', label:label, value:(el.value||'').slice(0,30)});
  });
  document.querySelectorAll('button').forEach(b => out.buttons.push((b.textContent||'').trim().slice(0,40)));
  // grab visible section labels
  document.querySelectorAll('label, .label, [class*=Label], h3, h4').forEach(e=>{
    const t=(e.textContent||'').trim();
    if(t && t.length<60) out.text.push(t);
  });
  out.text = [...new Set(out.text)].slice(0,40);
  return JSON.stringify(out);
})()
"""

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()
    data = json.loads(await page.evaluate(JS_EXP))
    print("HEADING:", data["heading"])
    print("\nFIELDS:")
    for f in data["fields"]:
        print(f"  [{f['tag']}/{f['type']}] id={f['id']!r} label={f['label']!r} val={f['value']!r}")
    print("\nBUTTONS:", data["buttons"])
    print("\nSECTION LABELS:")
    for t in data["text"]:
        print("  -", t)
    await cdp.close()

asyncio.run(main())
