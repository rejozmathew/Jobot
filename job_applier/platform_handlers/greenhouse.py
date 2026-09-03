"""Greenhouse / Greenhouse.io job application handler (generic, one-command).

Works on ANY Greenhouse-hosted application:
  * boards.greenhouse.io / job-boards.greenhouse.io / *.greenhouse.io postings
  * embedded forms on company career sites (iframe -> embed/job_app)

Everything is driven over a raw CDP session (job_applier.cdp_client.CDPBrowser)
attached to the user's real Chromium/Brave window. No LLM, no browser-use.

Proven on two live forms (2026-08-20): Brex (submitted) and Ethos Life
(submitted). The interaction recipe below is the one that actually worked:

  react-select (Greenhouse uses react-select for every dropdown AND for
  country/location remote-search):
      focus -> ArrowDown (open) -> type filter text -> Enter (commit)
      verify via the COMMITTED value (.select__single-value), NOT el.value

Known Greenhouse quirks handled here:
  * standard contact fields use plain ids (first_name, last_name, email,
    phone, country, candidate-location), not question_* ids
  * "country" is a phone-dialer remote search ("United States +1");
    "candidate-location" is a place remote search ("Wheeling, IL, United
    States") — both commit with the type-filter-Enter recipe
  * conditional follow-up text fields sometimes stay REQUIRED even after the
    parent question is answered (Brex "Capital One -> EID", Ethos "government
    official -> agency/role") — healed with "N/A" on validation error
  * "Preferred First Name" is a distinct required field on some boards
  * reCAPTCHA is invisible/score-based — not a hard blocker

Config: profile.json -> "greenhouse" block
  skip_submit : bool (safety; default True)
  dry_run     : bool (fill + verify, never click Submit)
  questions   : [{label_contains, value, kind?}, ...]  # kind: select|text|checkbox
  dropdowns   : legacy list, merged
  custom_answers: legacy list, merged
  preferred_name: text for "Preferred First Name"
  screening   : {label_contains: answer} for yes/no screening questions
  identity (top-level profile): first/last name, email, phone, location,
                                country, linkedin, website — auto-applied
  resume (top-level profile): {"path": "..."} — auto-uploaded

CLI:  run_applier.py apply <url> --platform greenhouse [--dry-run]
Env:  BROWSER_USE_CDP_URL (default http://127.0.0.1:9222)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Optional

from .base import (
    BasePlatformHandler,
    HandlerOutcome,
    HandlerResult,
    TraceHook,
)


# ---------------------------------------------------------------------------
# JS helpers
# ---------------------------------------------------------------------------

# Extract the Greenhouse embed iframe src from a company career page.
IFRAME_JS = r"""
(function(){
  const frames = Array.from(document.querySelectorAll('iframe'));
  for (const f of frames) {
    const s = f.src || '';
    if (/greenhouse\.io\/embed/.test(s)) return s;
  }
  return '';
})()
"""

# Find the Apply link on a Greenhouse JOB POSTING page (e.g.
# job-boards.greenhouse.io/<co>/jobs/<id>). Returns the embed URL
# (greenhouse.io/embed/job_app?token=...) or '' if not on a posting page.
APPLY_LINK_JS = r"""
(function(){
  const as = Array.from(document.querySelectorAll('a'));
  for (const a of as) {
    const t = (a.textContent || '').trim();
    if (/apply|how to apply|start application/i.test(t) && /greenhouse\.io\/embed\/job_app|job_app/i.test(a.href || '')) {
      return a.href;
    }
  }
  for (const a of as) { if (/greenhouse\.io\/embed\/job_app/i.test(a.href || '')) return a.href; }
  return '';
})()
"""

# Universal element lookup: id OR name (boards vary — Brex/Ethos use id,
# Figma uses name). Returns the element or null.
EL_JS = (
    "(function(k){var e=document.getElementById(k);"
    "if(!e){e=document.querySelector('[name=\"'+k+'\"]');}"
    "return e;})("
)

# Full inventory of fillable fields, id-OR-name agnostic.
# Returns [{id, label, kind, value, required}]. "id" is the key (id or name).
MAP_FIELDS_JS = r"""
(function(){
  const kindOf = (el) => {
    const cls = (el.className || '').toString();
    if (el.type === 'file') return 'file';
    if (el.type === 'checkbox') return 'checkbox';
    if (el.type === 'radio') return 'radio';
    if (cls.indexOf('select__input') !== -1 || el.getAttribute('aria-haspopup') === 'true' || el.tagName === 'SELECT') return 'select';
    return 'text';
  };
  const keyOf = (el) => (el.id || el.name || el.getAttribute('aria-label') || '');
  const labelOf = (el) => {
    const k = keyOf(el);
    if (k) {
      let lab = document.querySelector('label[for="' + CSS.escape(k) + '"]');
      if (lab) return (lab.textContent || '').trim();
      lab = document.querySelector('label[id="' + CSS.escape(k) + '-label"]');
      if (lab) return (lab.textContent || '').trim();
    }
    const wrap = el.closest('.form__field, [class*=field], label');
    if (wrap) { const l = wrap.querySelector('label'); if (l) return (l.textContent || '').trim(); }
    return (el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim();
  };
  const out = [];
  const seen = new Set();
  const all = Array.from(document.querySelectorAll('input,select,textarea'));
  for (const c of all) {
    if (c.type === 'hidden') continue;
    const k = keyOf(c);
    if (!k || seen.has(k)) continue;
    const kind = kindOf(c);
    if (!/^\d+$|question_\d+|^first_name$|^last_name$|^preferred_name$|^email$|^phone$|^country$|^candidate-location$|^location$|^website$|^linkedin$|^resume$|name|email|phone|location|country|website|linkedin/i.test(k)) continue;
    seen.add(k);
    out.push({
      id: k,
      label: labelOf(c),
      kind: kind,
      value: (c.value !== undefined && c.value !== null) ? String(c.value) : '',
      required: !!(c.required || c.getAttribute('aria-required') === 'true')
    });
  }
  return out;
})()
"""

# ---- id-OR-name element access (boards vary: Brex/Ethos use id, Figma uses name) ----
# Reused inside (args)=>{...} arrow fns; arg is {"id": fid} (dict is forwarded).
EL_EXPR = (
    "document.getElementById(args.id) || "
    "document.querySelector('[name=\"' + args.id + '\"]')"
)
EL_EXISTS_JS = "(args) => !!((" + EL_EXPR + "))"
EL_FOCUS_JS  = "(args) => { (" + EL_EXPR + ").focus(); }"
EL_SETVAL_JS = "(args) => { var e = " + EL_EXPR + "; if (e) { e.value = args.val; } return !!(e); }"
EL_GETVAL_JS = "(args) => { var e = " + EL_EXPR + "; return e ? (e.value || '') : null; }"

# Committed value of a field (react-select .select__single-value or raw value).
# id-OR-name agnostic. Call: page.evaluate(COMMITTED_JS, {"id": fid})
COMMITTED_JS = (
    "(args) => {"
    "var e = " + EL_EXPR + ";"
    "if (!e) return null;"
    "var c = e.closest('.select__control');"
    "if (c) { var s = c.querySelector('.select__single-value'); if (s) return (s.textContent||'').trim(); }"
    "return e.value || '';"
    "}"
)

# First visible option text of any open listbox (menus render in a portal).
FIRST_OPTION_JS = r"""
(function(){
  const m = document.querySelector('[role=listbox]');
  if (!m) return null;
  const o = m.querySelector('[role=option]');
  return o ? (o.textContent || '').trim() : null;
})()
"""

# All visible option texts of any open listbox.
OPTIONS_JS = r"""
(function(){
  const m = document.querySelector('[role=listbox]');
  if (!m) return [];
  return Array.from(m.querySelectorAll('[role=option]')).map(o => (o.textContent||'').trim()).slice(0, 30);
})()
"""

# Read inline validation errors currently shown on the form.
ERRORS_JS = r"""
(function(){
  return Array.prototype.slice.call(document.querySelectorAll('[class*=error], .form__error, .text-danger, [role=alert]'))
      .map(e => (e.innerText||'').trim()).filter(Boolean).slice(0, 12);
})()
"""

# Find + click the Submit application button.
SUBMIT_JS = r"""
(function(){
  const b = Array.prototype.slice.call(document.querySelectorAll('button, input[type=submit]'))
      .find(x => /submit application/i.test((x.textContent||x.value||'').trim()));
  if (!b) return false;
  b.scrollIntoView({block:'center'});
  b.click();
  return true;
})()
"""

# Confirmation detection (URL + title + body).
CONFIRM_JS = r"""
(function(){
  const body = (document.body ? document.body.innerText : '') + ' ' + (document.title || '');
  const url = location.href || '';
  const conf = /confirmation/i.test(url) ||
      /thank you for applying|application has been received|we'?ve (received|got) your (application|resume)|your application (has been )?(was )?submitted/i.test(body);
  return {conf: conf, url: url.slice(0,180), title: (document.title||'').slice(0,120)};
})()
"""

# Check whether a file chip (uploaded attachment) is present.
FILE_CHIP_JS = r"""
(function(){
  const c = document.querySelector('[class*=file__file-name], [class*=dropzone], [class*=upload]');
  return c ? (c.textContent||'').trim().slice(0,80) : '';
})()
"""

# Clear a select's committed value (best effort: open + Backspace x2).
CLEAR_SELECT_JS = (
    "(function(){var e=document.getElementById(\"%s\");"
    "if(!e)return false;e.focus();return true;})()"
)


# Standard-field id -> profile keys (applied first, highest priority).
STD_FIELD_MAP = {
    "first_name": [("identity", "first_name")],
    "last_name": [("identity", "last_name")],
    "preferred_name": [("greenhouse", "preferred_name"), ("identity", "preferred_name"), ("identity", "first_name")],
    "email": [("identity", "email")],
    "phone": [("identity", "phone")],
    "country": [("identity", "address.country"), ("greenhouse", "country")],
    "candidate-location": [("identity", "location"), ("identity", "address.city")],
    "website": [("links", "website")],
    "linkedin": [("links", "linkedin")],
}


class GreenhouseHandler(BasePlatformHandler):
    """Deterministic Greenhouse application handler (CDP-based, generic)."""

    platform_name = "greenhouse"

    # ---- base contract ----
    @classmethod
    def can_handle(cls, url: str) -> bool:
        u = (url or "").lower()
        return "greenhouse.io" in u

    # ---- lifecycle ----
    def __init__(
        self,
        *,
        browser_session: Any,           # unused for greenhouse (raw CDP)
        profile: dict[str, Any] | None,
        job_url: str,
        trace_hook: Optional[TraceHook] = None,
        cdp_url: Optional[str] = None,
    ):
        super().__init__(
            browser_session=browser_session,
            profile=profile or {},
            job_url=str(job_url or ""),
            trace_hook=trace_hook,
        )
        self.browser: Any = None
        self._cdp_url = cdp_url
        self.steps: list[str] = []
        self.total_steps = 0

    async def _ensure_browser(self):
        if self.browser is not None and getattr(self.browser, "_page", None) is not None:
            return self.browser
        url = (
            self._cdp_url
            or os.environ.get("BROWSER_USE_CDP_URL", "").strip()
            or "http://127.0.0.1:9222"
        )
        from ..cdp_client import CDPBrowser
        self.browser = await CDPBrowser.connect(url)
        return self.browser

    # ---- main entry point ----
    async def run(self) -> HandlerOutcome:
        self._record("run:start", {"job_url": self.job_url})
        browser = await self._ensure_browser()
        page = await browser.get_current_page()

        # 1) Get to the FORM. Three possible starting states:
        #    a) already on the form (embed/job_app, or a page with fields — e.g.
        #       boards.greenhouse.io/<co>/jobs/<id> renders the form inline)
        #    b) on a Greenhouse JOB POSTING page -> Apply link -> embed
        #    c) on a company career page -> pull the Greenhouse embed iframe src
        cur = await self._eval(page, "location.href", None) or ""
        form_ready = False
        try:
            form_ready = len(await self._eval(page, MAP_FIELDS_JS, None) or []) >= 3
        except Exception:
            form_ready = False
        if not form_ready and "/embed/job_app" not in cur.lower():
            # (b) posting page with an Apply link
            apply_url = await self._eval(page, APPLY_LINK_JS, None) or ""
            if apply_url:
                await page.goto(apply_url)
                await asyncio.sleep(6)
                self._record("nav:apply", {"embed": apply_url[:100]})
            elif "greenhouse.io" not in cur.lower():
                # (c) company career page -> embed iframe
                src = await self._eval(page, IFRAME_JS, None) or ""
                if src:
                    await page.goto(src)
                    await asyncio.sleep(6)
                    self._record("nav:iframe", {"embed": src[:100]})
                elif self.job_url:
                    await page.goto(self.job_url)
                    await asyncio.sleep(6)
                    self._record("nav:joburl", {"url": self.job_url[:100]})
            elif self.job_url and self.job_url not in cur:
                # (a') already greenhouse.io but wrong page -> go to the job URL
                await page.goto(self.job_url)
                await asyncio.sleep(6)
                self._record("nav:joburl", {"url": self.job_url[:100]})
        self._record("nav", {"url": (cur or self.job_url)[:120]})

        # 2) Wait for the form to appear.
        inv = []
        for _ in range(20):
            await asyncio.sleep(1)
            try:
                inv = await self._eval(page, MAP_FIELDS_JS, None) or []
            except Exception:
                inv = []
            if len(inv) >= 3:
                break
        if len(inv) < 3:
            return self._outcome(
                HandlerResult.FAILED, "FAILED",
                "Greenhouse form did not render (no fields found). "
                "Open the job URL in the Brave CDP window and retry.",
            )
        self._record("form:ready", {"fields": len(inv)})

        # 3) Fill standard fields by id (identity block).
        select_fields: list[tuple[str, str]] = []
        for fid, sources in STD_FIELD_MAP.items():
            f = next((x for x in inv if x["id"] == fid), None)
            if not f:
                continue
            val = self._lookup(sources)
            if not val:
                continue
            if f["kind"] == "select":
                ok = await self._fill_select(page, fid, val)
                if ok:
                    select_fields.append((fid, val))
            else:
                ok = await self._fill_text(page, fid, val)
            self._record("std", {"id": fid, "value": val, "ok": ok})

        # 4) Apply profile rules to the remaining question_* fields.
        rules = self._rules()
        used: set[str] = set()
        for rule in rules:
            lc = (rule.get("label_contains") or "").lower()
            val = rule.get("value")
            if not lc or val in (None, ""):
                continue
            # specificity: prefer the LONGEST label containing the phrase
            cands = [
                f for f in inv
                if f["id"] not in used and lc in (f.get("label") or "").lower()
            ]
            if not cands:
                self._record("rule:skip", {"label_contains": lc, "reason": "no match"})
                continue
            best = max(cands, key=lambda f: len(f.get("label") or ""))
            used.add(best["id"])
            if best["kind"] == "select":
                ok = await self._fill_select(page, best["id"], val)
                if ok:
                    select_fields.append((best["id"], val))
            elif best["kind"] == "checkbox":
                ok = await self._fill_checkbox(page, best["id"], val)
            else:
                ok = await self._fill_text(page, best["id"], val)
            self._record("rule", {"label": best["label"][:60], "value": val, "ok": ok})

        # 5) Upload resume.
        resume = self._resume_path()
        if resume and os.path.exists(resume):
            try:
                els = await page.query_selector_all("input[type=file]")
                if els:
                    await els[0].set_input_files(resume)
                    await asyncio.sleep(2.5)
                    self._record("upload", {"file": os.path.basename(resume), "ok": True})
                else:
                    self._record("upload", {"ok": False, "reason": "no file input"})
            except Exception as e:
                self._record("upload", {"ok": False, "error": str(e)[:160]})
        else:
            self._record("upload", {"ok": False, "reason": "no resume path"})

        # 6) Pre-submit verification.
        empty = await self._empty_required(page, inv)
        self._record("pre_submit", {"empty_required": empty})

        # 6b) job-boards.greenhouse.io re-renders the form after fill and can
        #     RESET react-select values (Country, visa, etc.) even though text
        #     fields survive. Re-verify every select-kind field we filled and
        #     re-fill any that got cleared — immediately before submit — so the
        #     values are committed in the final DOM state.
        if select_fields:
            await self._reverify_selects(page, inv, select_fields)
            empty = await self._empty_required(page, inv)
            self._record("pre_submit_re", {"empty_required": empty})

        # 7) dry_run / skip_submit: stop before Submit.
        if self._flag("dry_run") or self._flag("skip_submit", default=True):
            await self._screenshot(page, "greenhouse_dryrun")
            return self._outcome(
                HandlerResult.PROGRESSED, "PENDING_REVIEW",
                f"Dry-run complete. {len(inv)} fields found; "
                f"empty-required: {empty if empty else 'none'}. "
                "Review in the browser; run without --dry-run to submit.",
            )

        # 8) Submit + verify, with one healing retry.
        return await self._submit_with_heal(page, inv)

    # ---- fill primitives (the PROVEN recipe, id-OR-name agnostic) ----
    async def _fill_text(self, page, fid: str, value: str) -> bool:
        browser = await self._ensure_browser()
        if not await page.evaluate(EL_EXISTS_JS, {"id": fid}):
            return False
        # already correct? (idempotent)
        cur = await page.evaluate(EL_GETVAL_JS, {"id": fid})
        if cur == value:
            return True
        await page.evaluate(EL_FOCUS_JS, {"id": fid})
        await asyncio.sleep(0.12)
        await page.evaluate(EL_SETVAL_JS, {"id": fid, "val": ""})
        await asyncio.sleep(0.05)
        await browser.type_text(value)
        await asyncio.sleep(0.15)
        await browser.press_key("Tab", 9)
        await asyncio.sleep(0.25)
        cur = await page.evaluate(EL_GETVAL_JS, {"id": fid})
        return cur == value

    async def _committed(self, page, fid: str) -> str:
        v = await page.evaluate(COMMITTED_JS, {"id": fid})
        return (v or "").strip()

    async def _fill_select(self, page, fid: str, value: str) -> bool:
        """focus -> ArrowDown(open) -> type(filter) -> Enter(commit) -> verify.
        Two attempts; then report. Verified against the COMMITTED value."""
        browser = await self._ensure_browser()
        if not await page.evaluate(EL_EXISTS_JS, {"id": fid}):
            return False
        cur = await self._committed(page, fid)
        if cur and value.lower() in cur.lower():
            return True

        for attempt in range(2):
            await page.evaluate(EL_FOCUS_JS, {"id": fid})
            await asyncio.sleep(0.4)
            await browser.press_key("ArrowDown", 40)
            await asyncio.sleep(1.8)
            await browser.type_text(value[:14])
            # Remote-search dialers (Greenhouse country) need the list to settle
            # before Enter commits; generous wait fixes flaky selects.
            await asyncio.sleep(2.6)
            await browser.press_key("Enter", 13)
            await asyncio.sleep(1.2)
            v = await self._committed(page, fid)
            if v:
                self._record("select:ok", {"id": fid, "committed": v[:40], "attempt": attempt + 1})
                return True
            # Enter didn't commit (non-remote react-select, e.g. Gusto Location):
            # the option is usually still visible in the open menu — click it.
            clicked = await self._eval(page, """(args) => {
                const el = document.querySelector('[id="' + args.id + '"]');
                if (!el) return false;
                const root = el.closest('[class*="css-"]') || el.parentElement;
                const scope = (root && root.querySelector('[role="listbox"], .virtual-list, ul')) || document;
                const opts = Array.from(scope.querySelectorAll('[role="option"], li, [class*="option"]'));
                const want = args.val.toLowerCase();
                const hit = opts.find(o => (o.textContent||'').toLowerCase().includes(want))
                          || opts.find(o => (o.textContent||'').toLowerCase().includes(want.slice(0,6)));
                if (hit) { hit.scrollIntoView({block:'center'}); hit.click(); return true; }
                return false; }""", {"id": fid, "val": value})
            await asyncio.sleep(1.0)
            v = await self._committed(page, fid)
            if v:
                self._record("select:ok_click", {"id": fid, "committed": v[:40], "attempt": attempt + 1})
                return True
            await browser.press_key("Escape", 27)
            await asyncio.sleep(0.3)
        self._record("select:failed", {"id": fid, "value": value,
                                        "options": await self._eval(page, OPTIONS_JS, None)})
        return False

    async def _reverify_selects(self, page: CDPPage, all_fields: list[dict],
                                select_fields: list[tuple[str, str]]) -> None:
        """job-boards.greenhouse.io re-renders the form after fill and can reset
        react-select values (Country, visa, etc.) even though text inputs survive.
        Re-check each select-kind field right before submit and re-fill any that
        went empty so the values are committed in the final DOM state."""
        fbyid = {f["id"]: f for f in all_fields}
        for fid, val in select_fields:
            f = fbyid.get(fid)
            if not f or f["kind"] != "select":
                continue
            if (await self._committed(page, fid)) == val:
                continue
            self._record("select:reset_detected", {"id": fid, "label": f["label"][:60]})
            ok = await self._fill_select(page, fid, val)
            if not ok:
                self._record("select:refill_failed", {"id": fid, "label": f["label"][:60]})
        self._record("select_reverified", {"fields": [fid for fid, _ in select_fields]})

    async def _fill_checkbox(self, page, fid: str, value: str) -> bool:
        want = str(value).lower() in ("yes", "true", "1", "on")
        r = await page.evaluate(
            "(args) => { var el = " + EL_EXPR + "; if (!el) return false; "
            "if (el.checked !== args.want) { el.scrollIntoView({block:'center'}); el.click(); } "
            "return el.checked === args.want; }",
            {"id": fid, "want": want},
        )
        return bool(r)

    # ---- submit ----
    async def _empty_required(self, page, inv: list[dict]) -> list[str]:
        out = []
        for f in inv:
            if f.get("kind") in ("file",):
                continue
            if f.get("kind") == "select":
                v = await self._committed(page, f["id"])
            else:
                v = await page.evaluate(EL_GETVAL_JS, {"id": f["id"]})
            if not v and f.get("label"):
                out.append(f["label"][:60])
        return out

    async def _submit_with_heal(self, page, inv: list[dict]) -> HandlerOutcome:
        browser = await self._ensure_browser()
        for attempt in range(2):
            clicked = await self._eval(page, SUBMIT_JS, None)
            self._record("submit:clicked", {"attempt": attempt + 1, "clicked": bool(clicked)})
            confirmed = False
            errs: list[str] = []
            for _ in range(8):
                await asyncio.sleep(2.5)
                try:
                    v = await self._eval(page, CONFIRM_JS, None) or {}
                    errs = await self._eval(page, ERRORS_JS, None) or []
                except Exception:
                    # page is navigating — treat as in-progress
                    continue
                if v.get("conf"):
                    confirmed = True
                    break
                if errs:
                    break
            if confirmed:
                await self._screenshot(page, "greenhouse_confirmed")
                return self._outcome(
                    HandlerResult.SUBMITTED, "SUBMITTED",
                    "Application submitted — confirmation page verified.",
                )
            if not errs:
                await self._screenshot(page, "greenhouse_submit_unknown")
                return self._outcome(
                    HandlerResult.FAILED, "FAILED",
                    "Submit clicked; neither confirmation nor errors detected. "
                    "Check the browser window.",
                )
            # Healing pass: fill every required-empty field with N/A, retry.
            self._record("submit:errors", {"errs": errs[:6], "attempt": attempt + 1})
            healed = await self._heal_empty(page, inv, errs)
            self._record("heal", {"healed": healed})
            if attempt == 1 or not healed:
                await self._screenshot(page, "greenhouse_failed")
                return self._outcome(
                    HandlerResult.FAILED, "FAILED",
                    "Submit rejected. Errors: " + "; ".join(errs[:6]) +
                    " (healed " + str(healed) + " field(s), still failing — review the form)",
                )
        return self._outcome(HandlerResult.FAILED, "FAILED", "exhausted")

    async def _heal_empty(self, page, inv: list[dict], errs: list[str]) -> int:
        """Fill required-but-empty CONDITIONAL text fields with 'N/A' (Greenhouse
        quirk: follow-up fields stay required after a No, e.g. Brex 'EID').

        CRITICAL: never touch a standard identity select (country,
        candidate-location, ...) or a field that already holds a committed value.
        Earlier this clobbered correct Country/Location values with 'N/A' and
        guaranteed a failed submit (Gusto)."""
        healed = 0
        std_ids = set(STD_FIELD_MAP.keys())
        for f in inv:
            if not f.get("label"):
                continue
            if f.get("kind") in ("file", "checkbox", "radio"):
                continue
            # Standard identity fields are never N/A candidates — they have a real
            # profile value. Re-filling them is the re-render race, not a heal.
            if f["id"] in std_ids:
                continue
            if f.get("kind") == "select":
                v = await self._committed(page, f["id"])
            else:
                v = await page.evaluate(EL_GETVAL_JS, {"id": f["id"]})
            if v:
                continue
            label_l = (f["label"] or "").lower()
            # only heal fields plausibly tied to the visible errors or known
            # conditional patterns, to avoid clobbering legitimate blanks
            tied = any(
                w in " ".join(errs).lower()
                for w in re.findall(r"[a-z]{4,}", label_l)
            ) or any(k in label_l for k in ("eid", "employer id", "agency", "role", "name of"))
            if not tied:
                continue
            ok = await self._fill_text(page, f["id"], "N/A")
            if ok:
                healed += 1
                self._record("heal:filled", {"label": f["label"][:60]})
        return healed

    # ---- config helpers ----
    def _rules(self) -> list[dict[str, Any]]:
        prof = self.profile or {}
        gh = prof.get("greenhouse", {}) if isinstance(prof.get("greenhouse"), dict) else {}
        out: list[dict[str, Any]] = []

        # explicit questions list (primary)
        for q in gh.get("questions", []) or []:
            if isinstance(q, dict) and q.get("label_contains") and q.get("value"):
                out.append(q)
        # legacy dropdowns
        for d in gh.get("dropdowns", []) or []:
            if isinstance(d, dict) and d.get("label_contains") and d.get("option"):
                out.append({"label_contains": d["label_contains"], "value": d["option"], "kind": "select"})
        # legacy custom_answers
        for ca in gh.get("custom_answers", []) or []:
            if isinstance(ca, dict) and ca.get("label_contains") and ca.get("answer"):
                out.append({"label_contains": ca["label_contains"], "value": ca["answer"]})
        # generic yes/no screening defaults (sponsorship, gov official, etc.)
        for lc, ans in (gh.get("screening", {}) or {}).items():
            out.append({"label_contains": lc, "value": ans})
        # top-level convenience keys
        for key, lc in (("how_heard", "how did you hear"), ("country", "country are you based")):
            v = gh.get(key)
            if v:
                out.append({"label_contains": lc, "value": v})
        # dedupe by label_contains (first wins)
        seen: set[str] = set()
        dedup = []
        for r in out:
            k = (r.get("label_contains") or "").lower()
            if k in seen:
                continue
            seen.add(k)
            dedup.append(r)
        return dedup

    def _lookup(self, sources: list[tuple[str, str]]) -> str:
        prof = self.profile or {}
        for top, sub in sources:
            node = prof.get(top)
            if isinstance(node, list):
                # links: pick by host
                if sub == "linkedin":
                    for lk in node:
                        if "linkedin" in str(lk).lower():
                            return str(lk)
                elif sub == "website":
                    for lk in node:
                        s = str(lk).lower()
                        if "linkedin" not in s and "github" not in s and s.startswith("http"):
                            return str(lk)
                continue
            if isinstance(node, dict):
                cur: Any = node
                for part in sub.split("."):
                    if not isinstance(cur, dict) or part not in cur:
                        cur = None
                        break
                    cur = cur[part]
                if isinstance(cur, (str, int)) and str(cur).strip():
                    return str(cur).strip()
            elif isinstance(node, (str, int)) and sub in ("", top):
                return str(node).strip()
        return ""

    def _resume_path(self) -> str:
        resume = (self.profile or {}).get("resume", {})
        p = resume.get("path", "") if isinstance(resume, dict) else str(resume or "")
        if not p:
            return ""
        p = os.path.expanduser(p)
        if not os.path.isabs(p):
            base = os.path.dirname(os.path.abspath(__file__))
            p = os.path.normpath(os.path.join(base, "..", "..", p))
        return p

    def _flag(self, key: str, default: bool = False) -> bool:
        envk = f"JOB_APPLIER_GH_{key.upper()}"
        envv = os.environ.get(envk, "").strip().lower()
        if envv:
            return envv not in ("0", "false", "no", "off")
        gh = self.profile.get("greenhouse", {}) if isinstance(self.profile.get("greenhouse"), dict) else {}
        return bool(gh.get(key, default))

    async def _eval(self, page, js: str, arg: Any = None) -> Any:
        try:
            return await page.evaluate(js, arg=arg)
        except Exception as e:
            self._record("eval:error", {"error": str(e)[:160]})
            return None

    async def _screenshot(self, page, name: str) -> None:
        try:
            shot = os.path.join(os.getcwd(), "artifacts", name + ".png")
            os.makedirs(os.path.dirname(shot), exist_ok=True)
            browser = await self._ensure_browser()
            await browser.screenshot(shot)
            self._record("screenshot", {"path": shot})
        except Exception as e:
            self._record("screenshot:error", {"error": str(e)[:120]})

    # ---- misc ----
    async def recover(self, context: dict[str, Any]) -> HandlerOutcome:
        return await self.run()

    def _record(self, event: str, data: dict[str, Any]) -> None:
        self.steps.append(f"{event}: {json.dumps(data, default=str)[:140]}")
        self.total_steps += 1
        self.trace(event, **{k: str(v)[:200] for k, v in data.items()})

    def _outcome(self, result: HandlerResult, state: str, message: str) -> HandlerOutcome:
        return HandlerOutcome(result=result, state=state, message=message,
                              steps=list(self.steps),
                              handoff_context=message)
