"""Settle the evaluate() return semantics + id/name question on the live Figma form."""
import asyncio, sys, json
sys.path.insert(0, ".")
from job_applier.cdp_client import CDPBrowser

async def main():
    b = await CDPBrowser.connect(cdp_url="http://127.0.0.1:9222", profile_name="brave-cdp-apply")
    page = await b.get_current_page()
    print("URL:", (await page.evaluate("location.href", None) or "")[:100])

    # Style A: bare arrow function, no arg
    A = "() => { return 42; }"
    # Style B: IIFE, no arg
    B = "(function(){ return 42; })()"
    # Style C: arrow with dict arg
    C = "(args) => { return args.x + 1; }"

    for name, expr, arg in [("A bare-arrow no-arg", A, None),
                            ("B IIFE no-arg", B, None),
                            ("C arrow dict-arg", C, {"x": 41})]:
        try:
            v = await page.evaluate(expr, arg)
            print(f"{name:22} -> {v!r}")
        except Exception as e:
            print(f"{name:22} -> ERR {e!r}")

    # id vs name for first_name
    print("id first_name:", await page.evaluate('!!document.getElementById("first_name")', None))
    print("name first_name:", await page.evaluate('!!document.querySelector(\'[name="first_name"]\')', None))
    # does the dict-arg element lookup work?
    EL = ("(args) => { var k=args.id; var e=document.getElementById(k)||document.querySelector('[name=\"'+k+'\"]'); return e? (e.value||'') : 'NULL'; }")
    print("EL first_name value:", repr(await page.evaluate(EL, {"id":"first_name"})))
    await b.close()

asyncio.run(main())
