"""Ethos: read the two compliance selects' exact options (focus-based typing)."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect("http://127.0.0.1:9222")
    page = await b.get_current_page()
    await asyncio.sleep(1)

    async def read_opts(fid):
        await page.evaluate(f'document.getElementById("{fid}").focus()')
        await asyncio.sleep(0.3)
        await b.press_key("ArrowDown", 40)
        await asyncio.sleep(1.3)
        r = await page.evaluate("(function(){var m=document.querySelector('[role=listbox]');if(!m)return null;var o=Array.prototype.slice.call(m.querySelectorAll('[role=option]'));return o.map(function(x){return (x.textContent||'').trim();}).slice(0,10);})()")
        await b.press_key("Escape", 27)
        await asyncio.sleep(0.5)
        return r

    print("sponsorship (72002) opts:", await read_opts("question_36662472002"))
    print("gov official (73002) opts:", await read_opts("question_36662473002"))
    print("AI question (97002) opts:", await read_opts("question_36663097002"))
    await b._session.close()

asyncio.run(main())
