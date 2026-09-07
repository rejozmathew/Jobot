# Owned CDP recipes

Use the configured browser endpoint and captured target ID, never a machine-local default. Managed connections use the existing `CDPBrowser.connect(cdp_url, target_id=<owned-id>)`. Missing/closed targets fail explicitly; they must not select a different first or blank tab. Await `browser.get_current_page()`.

Inspect current helper signatures before use:
- `page.evaluate` must return primitives/JSON-safe values, not DOM nodes. Use dictionary arguments. IIFEs execute themselves; bare callables need the installed wrapper's verified argument handling.
- Text insertion acts on the focused element. Focus and clear the intended input before typing.
- Non-character CDP key events omit the text field. Mouse input uses viewport coordinates and the proper pressed/released events.
- Verify React-controlled state after commit; a displayed value alone is insufficient.
- Verify uploaded files by attachment UI, not the privacy-protected file input value.
- Rediscover references after navigation/re-render. Do not transplant old coordinates into a new page.

Only close/restart a demonstrably owned target or process under app control. Unrelated browser windows and profiles are not cleanup targets. Preserve persistent browser data; if browser identity is unavailable, report the blocker. Live CDP execution and the synthetic boundary fixtures have distinct evidence labels.
