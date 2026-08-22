"""Fill the Work Experience entry (most recent role: Discover Sr Director)."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def fill_field(page, sel, value):
    """React-safe fill via IIFE with inlined values (proven pattern)."""
    js = """
    (() => {
      const sel = %s, value = %s;
      const e = document.querySelector('#' + CSS.escape(sel));
      if (!e) return JSON.stringify({sel, err:'no-el'});
      e.focus();
      const proto = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      setter.call(e, value);
      e.dispatchEvent(new Event('input', {bubbles:true}));
      e.dispatchEvent(new Event('change', {bubbles:true}));
      e.dispatchEvent(new Event('blur', {bubbles:true}));
      return JSON.stringify({sel, ok: e.value === value});
    })()
    """ % (json.dumps(sel), json.dumps(value))
    r = await page.evaluate(js)
    return json.loads(r) if isinstance(r, str) else r

async def main():
    cdp = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await cdp.get_current_page()

    prefix = await page.evaluate(
        "(() => { const el = document.querySelector('[id*=workExperience]'); return el ? el.id.split('--')[0] : null; })()"
    )
    print("prefix:", prefix)
    if not prefix:
        print("no work experience form — may have collapsed")
        await cdp.close(); return

    desc = ("Partnered with BU and marketing analytics teams to build customer acquisition, servicing, "
            "and retention analytics across personal loans, home loans, and deposits. Integrated MarTech, CRM, "
            "digital, and core banking data into the enterprise platform, enabling AI-driven personalization and "
            "decisioning that delivered ~$100M in measurable business impact. Developed the Enterprise Identity "
            "Knowledge Graph (Neo4j) and Customer 360 platform. Drove enterprise data platform transformation to "
            "a modern cloud-native analytics environment (AWS, Snowflake). Directed data workstreams for the $9B "
            "student-loan portfolio migration. Oversaw a global, full-stack data organization of ~75 professionals.")

    fills = [
        (f"{prefix}--jobTitle", "Sr. Director, Data, Analytics & AI"),
        (f"{prefix}--companyName", "Discover Financial Services"),
        (f"{prefix}--location", "Chicago, IL"),
        (f"{prefix}--startDate-dateSectionMonth-input", "6"),
        (f"{prefix}--startDate-dateSectionYear-input", "2022"),
        (f"{prefix}--endDate-dateSectionMonth-input", "5"),
        (f"{prefix}--endDate-dateSectionYear-input", "2026"),
        (f"{prefix}--roleDescription", desc),
    ]
    for sel, val in fills:
        r = await fill_field(page, sel, val)
        print(f"  {r}")

    await asyncio.sleep(0.8)
    # Verify
    v = json.loads(await page.evaluate("""
    (() => {
      const g = (id)=>{ const e=document.querySelector('#'+CSS.escape(id)); return e? e.value.slice(0,50):null; };
      const p = document.querySelector('[id*=workExperience]').id.split('--')[0];
      return JSON.stringify({
        title:g(p+'--jobTitle'), company:g(p+'--companyName'), loc:g(p+'--location'),
        sm:g(p+'--startDate-dateSectionMonth-input'), sy:g(p+'--startDate-dateSectionYear-input'),
        em:g(p+'--endDate-dateSectionMonth-input'), ey:g(p+'--endDate-dateSectionYear-input'),
        desc:g(p+'--roleDescription')
      });
    })()
    """))
    print("\nVERIFIED:", json.dumps(v, indent=2))
    await cdp.close()

asyncio.run(main())
