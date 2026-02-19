"""
Element handlers for job application automation.

This module extends browser-use Tools with lightweight diagnostic actions
and a guarded 'done' action.  Interaction actions (typing, clicking,
uploading) are left to browser-use's built-in handlers which use
coordinate-based CDP calls and handle cross-origin iframes correctly.

Custom actions that called page.get_element(backend_node_id) were removed
because CDP's DOM.resolveNode() fails with "Document needs to be requested
first" on iframe-heavy ATS sites (Workday, iCIMS, Greenhouse).
"""
# Note: Do NOT use "from __future__ import annotations" here
# as it breaks browser-use registry type validation.

import json
import logging
import os
import re
from typing import Any, Optional

from browser_use.agent.views import ActionResult
from browser_use.browser import BrowserSession
from browser_use.filesystem.file_system import FileSystem
from browser_use.tools.service import Tools
from browser_use.tools.views import DoneAction, InputTextAction, UploadFileAction

CONFIRMATION_PHRASES = (
    "application submitted",
    "thank you for applying",
    "successfully submitted",
    "application received",
    "application confirmed",
)

CAPTCHA_PHRASES = (
    "verify you are human",
    "captcha",
    "cloudflare",
    "just a moment",
    "security verification",
    "prove you are not a robot",
    "recaptcha",
    "hcaptcha",
    "challenge-platform",
)

EMAIL_BASIC_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_TRAILING_ARTIFACT_RE = re.compile(r"[}\]\"'`)\s]+$")

logger = logging.getLogger(__name__)


def _truncate(value: str, limit: int = 120) -> str:
    text = str(value or "")
    return text if len(text) <= limit else f"{text[:limit - 3]}..."


class JobApplierTools(Tools):
    """Extended tools for job application automation.

    Only registers actions that do NOT resolve DOM nodes via CDP
    (i.e. read-only JavaScript and the guarded done override).
    All element interactions use browser-use's built-in actions.
    """

    def __init__(
        self,
        profile_data: Optional[dict[str, Any]] = None,
        job_url: str = "",
        exclude_actions: list[str] | None = None,
        output_model=None,
        display_files_in_done_text: bool = True,
    ):
        super().__init__(
            exclude_actions=exclude_actions,
            output_model=output_model,
            display_files_in_done_text=display_files_in_done_text,
        )
        self.profile_data = profile_data or {}
        self.job_url = job_url or ""
        self._register_custom_actions()

    def _register_custom_actions(self) -> None:
        action_map = self.registry.registry.actions
        base_upload_meta = action_map.get("upload_file")
        base_input_meta = action_map.get("input")

        @self.registry.action("Scan all form fields and report current values, empty required fields, and checkbox states.")
        async def scan_form_fields(browser_session: BrowserSession):
            return await self._scan_form_fields(browser_session=browser_session)

        @self.registry.action("Check page diagnostics: visible errors, required-empty count, submit visibility, URL, title, and CAPTCHA detection.")
        async def check_page_state(browser_session: BrowserSession):
            return await self._check_page_state(browser_session=browser_session)

        @self.registry.action(
            "Toggle a checkbox by its label text. Uses JavaScript to find the checkbox near the given label and click it. "
            "Use this instead of click for checkboxes that don't respond to regular clicks (custom React/Workday checkboxes). "
            "Parameter label_text: a few words from the checkbox label (e.g. 'consent to the terms', 'I agree')."
        )
        async def toggle_checkbox(label_text: str, browser_session: BrowserSession):
            return await self._toggle_checkbox(label_text=label_text, browser_session=browser_session)

        @self.registry.action(
            "Complete Workday account setup in one action. Detects external SSO redirects, "
            "distinguishes Sign In vs Create Account pages, fills email/password/verify-password, "
            "handles consent checkbox, and submits. Use on Workday account pages."
        )
        async def workday_create_account(browser_session: BrowserSession):
            return await self._workday_create_account(browser_session=browser_session)

        @self.registry.action("Heuristically fill standard text/textarea fields (name, email, phone, address) from profile data. Only fills empty fields.")
        async def smart_fill(browser_session: BrowserSession):
            return await self._smart_fill(browser_session=browser_session)

        @self.registry.action(
            "Dismiss cookie banner, consent popup, or overlay blocking the page. "
            "Call this if a cookie/GDPR banner is blocking interaction."
        )
        async def dismiss_popup(browser_session: BrowserSession):
            return await self._dismiss_popup(browser_session=browser_session)

        if base_input_meta is not None:
            @self.registry.action("Input text into element by index.", param_model=InputTextAction)
            async def input(
                params: InputTextAction,
                browser_session: BrowserSession,
                has_sensitive_data: bool = False,
                sensitive_data: dict[str, str | dict[str, str]] | None = None,
            ):
                cleaned_text, changed = self._sanitize_email_input_text(params.text)
                effective_params = params
                if changed:
                    effective_params = InputTextAction(index=params.index, text=cleaned_text, clear=params.clear)

                try:
                    result = await base_input_meta.function(
                        params=effective_params,
                        browser_session=browser_session,
                        has_sensitive_data=has_sensitive_data,
                        sensitive_data=sensitive_data,
                    )
                except Exception as exc:
                    return ActionResult(error=f"input failed: {exc}")

                if changed and isinstance(result, ActionResult):
                    note = "Sanitized trailing JSON artifact characters from email before input."
                    if result.extracted_content:
                        result.extracted_content = f"{result.extracted_content}\n{note}"
                    else:
                        result.extracted_content = note
                return result

        if base_upload_meta is not None:
            @self.registry.action("Upload file with fallback CDP file-input discovery.", param_model=UploadFileAction)
            async def upload_file(
                params: UploadFileAction,
                browser_session: BrowserSession,
                available_file_paths: list[str],
                file_system: FileSystem,
            ):
                base_result: Any = None
                base_error = ""
                try:
                    base_result = await base_upload_meta.function(
                        params=params,
                        browser_session=browser_session,
                        available_file_paths=available_file_paths,
                        file_system=file_system,
                    )
                    base_error = str(getattr(base_result, "error", "") or "")
                except Exception as exc:
                    base_error = str(exc or "")

                if base_error and not self._is_no_file_upload_error(base_error):
                    if isinstance(base_result, ActionResult):
                        return base_result
                    return ActionResult(error=base_error)

                if not base_error:
                    if isinstance(base_result, ActionResult):
                        confirmation = await self._wait_for_upload_processing(browser_session, params.path)
                        self._append_upload_followup_hint(base_result, confirmation)
                    return base_result

                fallback_result = await self._upload_file_via_cdp_fallback(
                    file_path=params.path,
                    browser_session=browser_session,
                )
                if fallback_result and not fallback_result.error:
                    confirmation = await self._wait_for_upload_processing(browser_session, params.path)
                    self._append_upload_followup_hint(fallback_result, confirmation)
                return fallback_result

        if self.get_output_model() is None:
            @self.registry.action("Complete task.", param_model=DoneAction)
            async def done(params: DoneAction, browser_session: BrowserSession, file_system: FileSystem):
                return await self._guarded_done(params=params, browser_session=browser_session, file_system=file_system)

    @staticmethod
    def _is_no_file_upload_error(error_text: str) -> bool:
        return "No file upload element found" in str(error_text or "")

    @staticmethod
    def _sanitize_email_input_text(value: str) -> tuple[str, bool]:
        original = str(value or "")
        candidate = original.strip()
        if "@" not in candidate:
            return original, False
        stripped = EMAIL_TRAILING_ARTIFACT_RE.sub("", candidate)
        if stripped == candidate:
            return original, False
        if not EMAIL_BASIC_RE.match(stripped):
            return original, False
        return stripped, True

    @staticmethod
    def _append_upload_followup_hint(result: ActionResult, confirmation_note: str | None = None) -> None:
        follow_up = (
            "Upload processed. Waited 5 seconds. Now call scan_form_fields to verify "
            "what autofill populated."
        )
        if confirmation_note:
            follow_up = f"{confirmation_note}\n{follow_up}"
        if result.extracted_content:
            result.extracted_content = f"{result.extracted_content}\n{follow_up}"
        else:
            result.extracted_content = follow_up
        if result.long_term_memory:
            result.long_term_memory = f"{result.long_term_memory}\n{follow_up}"
        else:
            result.long_term_memory = follow_up

    async def _wait_for_upload_processing(
        self,
        browser_session: BrowserSession,
        file_path: str | None = None,
    ) -> str | None:
        try:
            page = await browser_session.get_current_page()
            if page is not None:
                await page.wait_for_timeout(5000)
                if file_path:
                    filename = os.path.basename(str(file_path))
                    found = await page.evaluate(
                        """
                        (fn) => {
                            const bodyText = (document.body && document.body.innerText) || '';
                            const shortName = String(fn || '').replace(/\\.pdf$/i, '');
                            return bodyText.includes(fn) || (shortName && bodyText.includes(shortName));
                        }
                        """,
                        filename,
                    )
                    if found:
                        return f"CONFIRMED: '{filename}' is visible on page after upload."
                    return f"Upload completed but '{filename}' was not found in visible page text."
        except Exception as exc:
            logger.debug("upload_file post-wait skipped: %s", exc)
        return None

    async def _upload_file_via_cdp_fallback(self, file_path: str, browser_session: BrowserSession) -> ActionResult:
        session_ids: list[str] = []
        try:
            focused = await browser_session.get_or_create_cdp_session(focus=True)
            if focused and focused.session_id:
                session_ids.append(focused.session_id)
        except Exception as exc:
            logger.debug("upload_file fallback: failed to get focused session: %s", exc)

        session_manager = getattr(browser_session, "session_manager", None)
        if session_manager is not None:
            try:
                for cdp_session in session_manager.get_all_sessions().values():
                    sid = getattr(cdp_session, "session_id", None)
                    if sid:
                        session_ids.append(sid)
            except Exception as exc:
                logger.debug("upload_file fallback: failed to list sessions: %s", exc)

        ordered_session_ids: list[str] = []
        seen_sessions: set[str] = set()
        for sid in session_ids:
            if sid and sid not in seen_sessions:
                seen_sessions.add(sid)
                ordered_session_ids.append(sid)

        cdp_client = browser_session.cdp_client
        seen_backend_ids: set[int] = set()

        for session_id in ordered_session_ids:
            try:
                await cdp_client.send.DOM.enable(session_id=session_id)
                doc = await cdp_client.send.DOM.getDocument(
                    params={"depth": -1, "pierce": True},
                    session_id=session_id,
                )
                root = (doc.get("root") or {}).get("nodeId")
                if not root:
                    continue

                query = await cdp_client.send.DOM.querySelectorAll(
                    params={"nodeId": root, "selector": "input[type=\"file\"]"},
                    session_id=session_id,
                )
                node_ids = query.get("nodeIds") or []
                for node_id in node_ids:
                    try:
                        described = await cdp_client.send.DOM.describeNode(
                            params={"nodeId": node_id},
                            session_id=session_id,
                        )
                        backend_node_id = (described.get("node") or {}).get("backendNodeId")
                        if not backend_node_id or backend_node_id in seen_backend_ids:
                            continue
                        seen_backend_ids.add(backend_node_id)

                        await cdp_client.send.DOM.setFileInputFiles(
                            params={"files": [file_path], "backendNodeId": backend_node_id},
                            session_id=session_id,
                        )
                        return ActionResult(
                            extracted_content="Successfully uploaded file via CDP fallback file-input discovery.",
                            long_term_memory=f"Uploaded file via CDP fallback: {file_path}",
                        )
                    except Exception as inner_exc:
                        logger.debug(
                            "upload_file fallback: setFileInputFiles failed (session=%s, node=%s): %s",
                            session_id,
                            node_id,
                            inner_exc,
                        )
            except Exception as exc:
                logger.debug("upload_file fallback: DOM query failed for session %s: %s", session_id, exc)

        return ActionResult(error="No file upload element found (base + fallback failed)")

    # ------------------------------------------------------------------
    # scan_form_fields  (read-only JS)
    # ------------------------------------------------------------------
    async def _scan_form_fields(self, browser_session: BrowserSession) -> ActionResult:
        page = await browser_session.get_current_page()
        if page is None:
            return ActionResult(error="scan_form_fields: no active page")

        raw = await page.evaluate(
            """
            () => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    if (!style) return false;
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };

                const fieldNodes = Array.from(
                    document.querySelectorAll('input, select, textarea, [role="combobox"], [role="checkbox"]')
                );

                const rows = [];
                const seen = new Set();

                for (const el of fieldNodes) {
                    if (!isVisible(el)) continue;
                    const tag = (el.tagName || '').toLowerCase();
                    const typeAttr = (el.getAttribute('type') || '').toLowerCase();
                    if (tag === 'input' && ['hidden', 'submit', 'button', 'image'].includes(typeAttr)) continue;

                    const key = [
                        tag,
                        typeAttr,
                        el.getAttribute('id') || '',
                        el.getAttribute('name') || '',
                        el.getAttribute('placeholder') || '',
                        el.getAttribute('role') || '',
                    ].join('|');
                    if (seen.has(key)) continue;
                    seen.add(key);

                    const role = (el.getAttribute('role') || '').toLowerCase();
                    let fieldType = tag;
                    if (role === 'combobox') fieldType = 'combobox';
                    else if (role === 'checkbox' || typeAttr === 'checkbox') fieldType = 'checkbox';
                    else if (tag === 'input') fieldType = typeAttr || 'text';

                    const label =
                        (el.labels && el.labels[0] && el.labels[0].innerText && el.labels[0].innerText.trim()) ||
                        el.getAttribute('aria-label') ||
                        el.getAttribute('placeholder') ||
                        el.getAttribute('name') ||
                        el.getAttribute('id') ||
                        '(unlabeled field)';

                    let value = '';
                    let checked = null;

                    if (fieldType === 'checkbox') {
                        const aria = (el.getAttribute('aria-checked') || '').toLowerCase();
                        if (aria === 'true') checked = true;
                        else if (aria === 'false') checked = false;
                        else checked = !!el.checked;
                    } else if (tag === 'select') {
                        const selected = el.selectedOptions && el.selectedOptions.length > 0 ? el.selectedOptions[0] : null;
                        value = (selected && selected.textContent) ? selected.textContent.trim() : (el.value || '');
                    } else if (tag === 'textarea' || tag === 'input') {
                        value = el.value || '';
                    } else {
                        value = (el.textContent || '').trim();
                    }

                    const required = !!el.required || el.getAttribute('aria-required') === 'true';
                    const empty = fieldType === 'checkbox' ? checked !== true : !String(value || '').trim();

                    rows.push({
                        type: fieldType,
                        label: String(label || '').replace(/\\s+/g, ' ').trim(),
                        value: String(value || '').replace(/\\s+/g, ' ').trim(),
                        checked,
                        required,
                        empty,
                    });
                }

                const requiredEmpty = rows.filter((row) => row.required && row.empty).length;
                return { fields: rows.slice(0, 220), required_empty: requiredEmpty };
            }
            """
        )

        payload = self._parse_json(raw)
        if not isinstance(payload, dict):
            return ActionResult(error=f"scan_form_fields: unexpected payload '{_truncate(str(payload), 180)}'")

        fields = payload.get("fields") or []
        required_empty = int(payload.get("required_empty") or 0)

        lines = ["Form fields found:"]
        for idx, field in enumerate(fields[:120], start=1):
            if not isinstance(field, dict):
                continue
            field_type = field.get("type") or "unknown"
            label = _truncate(str(field.get("label") or "(unlabeled)"), 80)
            required = bool(field.get("required"))
            empty = bool(field.get("empty"))

            if field_type == "checkbox":
                checked = field.get("checked")
                row = f"{idx}. [{field_type}] \"{label}\" - checked: {checked}"
            else:
                value = _truncate(str(field.get("value") or ""), 80)
                row = f"{idx}. [{field_type}] \"{label}\" - value: \"{value}\""

            if required:
                row += " (required)"
            if empty:
                row += " (EMPTY)"
            lines.append(row)

        lines.append(f"Required empty fields: {required_empty}")
        return ActionResult(extracted_content="\n".join(lines))

    # ------------------------------------------------------------------
    # dismiss_popup  (cookie banners, consent overlays)
    # ------------------------------------------------------------------
    async def _dismiss_popup(self, browser_session: BrowserSession) -> ActionResult:
        """Dismiss cookie banner, consent popup, or overlay using JS."""
        from .agent import COOKIE_DISMISS_JS
        page = await browser_session.get_current_page()
        if page is None:
            return ActionResult(error="dismiss_popup: no active page")
        try:
            result = await page.evaluate(COOKIE_DISMISS_JS)
            if result and result.get("dismissed"):
                return ActionResult(
                    extracted_content=f"Dismissed popup: {result.get('method')} - {result.get('text', result.get('selector', ''))}"
                )
            return ActionResult(extracted_content="No cookie/consent popup found to dismiss.")
        except Exception as e:
            return ActionResult(error=f"dismiss_popup failed: {str(e)[:150]}")

    # ------------------------------------------------------------------
    # toggle_checkbox  (JS-based, no CDP element resolution)
    # ------------------------------------------------------------------
    async def _toggle_checkbox(self, label_text: str, browser_session: BrowserSession) -> ActionResult:
        """Find a checkbox by nearby label text and toggle it using JavaScript.

        This bypasses coordinate-based CDP clicks which fail on custom React/Workday
        checkboxes. Uses page.evaluate() to find and click the checkbox element
        directly in the page context.
        """
        if not label_text or not label_text.strip():
            return ActionResult(error="toggle_checkbox: label_text is required")

        page = await browser_session.get_current_page()
        if page is None:
            return ActionResult(error="toggle_checkbox: no active page")

        raw = await page.evaluate(
            """
            (labelText) => {
                const normalize = (s) => (s || '')
                    .toLowerCase()
                    .replace(/&rsquo;|&lsquo;|[\u2018\u2019]/g, "'")
                    .replace(/&rdquo;|&ldquo;|[\u201C\u201D]/g, '"')
                    .replace(/&amp;/g, '&')
                    .replace(/&nbsp;/g, ' ')
                    .replace(/\\s+/g, ' ')
                    .trim();
                const target = normalize(labelText);
                if (!target) return { success: false, error: 'Empty label text' };
                const targetWords = target.split(/\\s+/).filter(w => w.length > 2);

                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    if (!style) return false;
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };

                const getCheckedState = (el) => {
                    if (!el) return null;
                    const aria = (el.getAttribute('aria-checked') || '').toLowerCase();
                    if (aria === 'true') return true;
                    if (aria === 'false') return false;
                    if (typeof el.checked === 'boolean') return el.checked;
                    return null;
                };

                // Strategy 1: Find all checkbox-like elements and match by nearby text
                const checkboxSelectors = [
                    'input[type="checkbox"]',
                    '[role="checkbox"]',
                    '[aria-checked]',
                ];

                let bestMatch = null;
                let bestScore = 0;

                for (const selector of checkboxSelectors) {
                    const elements = document.querySelectorAll(selector);
                    for (const el of elements) {
                        if (!isVisible(el)) continue;

                        // Collect text from: the element itself, its label, parent, siblings
                        const texts = [];

                        // Own text/aria-label
                        texts.push(el.getAttribute('aria-label') || '');
                        texts.push(el.textContent || '');

                        // Associated <label>
                        if (el.id) {
                            const label = document.querySelector('label[for="' + el.id + '"]');
                            if (label) texts.push(label.textContent || '');
                        }
                        if (el.labels) {
                            for (const lbl of el.labels) texts.push(lbl.textContent || '');
                        }

                        // Parent container text (up to 3 levels)
                        let parent = el.parentElement;
                        for (let i = 0; i < 3 && parent; i++) {
                            texts.push(parent.textContent || '');
                            parent = parent.parentElement;
                        }

                        // Next sibling text
                        if (el.nextElementSibling) {
                            texts.push(el.nextElementSibling.textContent || '');
                        }

                        const combined = normalize(texts.join(' '));
                        // Fuzzy word-overlap matching (60% threshold)
                        const combinedWords = new Set(combined.split(/\\s+/));
                        const matchCount = targetWords.filter(w => combinedWords.has(w)).length;
                        const matchRatio = targetWords.length > 0 ? matchCount / targetWords.length : 0;

                        if (matchRatio >= 0.6) {
                            let score = matchRatio * 10;
                            if (el.tagName === 'INPUT' && el.type === 'checkbox') score += 3;
                            if (el.getAttribute('role') === 'checkbox') score += 2;
                            if (el.getAttribute('aria-checked') !== null) score += 1;
                            if (combined.includes(target)) score += 5;  // Bonus for exact match

                            if (score > bestScore) {
                                bestScore = score;
                                bestMatch = el;
                            }
                        }
                    }
                }

                // Strategy 2: Find by label text and walk to associated checkbox
                if (!bestMatch) {
                    const allLabels = document.querySelectorAll('label, [class*="label"], [class*="Label"]');
                    for (const lbl of allLabels) {
                        if (!isVisible(lbl)) continue;
                        const lblText = normalize(lbl.textContent || '');
                        // Fuzzy word-overlap matching for labels too
                        const lblWords = new Set(lblText.split(/\\s+/));
                        const lblMatchCount = targetWords.filter(w => lblWords.has(w)).length;
                        if (targetWords.length > 0 && lblMatchCount / targetWords.length < 0.6) continue;

                        // Check if label has a 'for' attribute
                        const forAttr = lbl.getAttribute('for');
                        if (forAttr) {
                            const linked = document.getElementById(forAttr);
                            if (linked && (linked.type === 'checkbox' || linked.getAttribute('role') === 'checkbox')) {
                                bestMatch = linked;
                                break;
                            }
                        }

                        // Check for checkbox inside the label
                        const inner = lbl.querySelector('input[type="checkbox"], [role="checkbox"]');
                        if (inner) {
                            bestMatch = inner;
                            break;
                        }

                        // Check siblings
                        const sibling = lbl.previousElementSibling || lbl.nextElementSibling;
                        if (sibling && (sibling.type === 'checkbox' || sibling.getAttribute('role') === 'checkbox')) {
                            bestMatch = sibling;
                            break;
                        }
                    }
                }

                if (!bestMatch) {
                    // Collect all visible checkboxes for diagnostic
                    const allCheckboxes = [];
                    for (const selector of checkboxSelectors) {
                        const elements = document.querySelectorAll(selector);
                        for (const el of elements) {
                            if (!isVisible(el)) continue;
                            const lbl = el.getAttribute('aria-label')
                                || (el.labels && el.labels[0] && el.labels[0].textContent)
                                || (el.parentElement && el.parentElement.textContent || '').substring(0, 80);
                            allCheckboxes.push(normalize(lbl).substring(0, 60));
                        }
                    }
                    return {
                        success: false,
                        error: 'No checkbox found matching "' + target + '"',
                        visible_checkboxes: allCheckboxes.slice(0, 10),
                    };
                }

                // Record state before click
                const stateBefore = getCheckedState(bestMatch);

                // Click the element - use .click() which triggers React/framework handlers
                bestMatch.click();

                // Also dispatch events for frameworks that need them
                bestMatch.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, composed: true }));

                // For native checkboxes, ensure change event fires
                if (bestMatch.tagName === 'INPUT' && bestMatch.type === 'checkbox') {
                    bestMatch.dispatchEvent(new Event('change', { bubbles: true }));
                }

                // Check state after click
                const stateAfter = getCheckedState(bestMatch);

                // If state didn't change, try alternative: toggle via property for native, or click label
                if (stateAfter === stateBefore) {
                    if (bestMatch.tagName === 'INPUT' && bestMatch.type === 'checkbox') {
                        bestMatch.checked = !bestMatch.checked;
                        bestMatch.dispatchEvent(new Event('change', { bubbles: true }));
                        bestMatch.dispatchEvent(new Event('input', { bubbles: true }));
                    } else {
                        // For role=checkbox, try clicking the parent or associated label
                        const clickTargets = [bestMatch.parentElement];
                        if (bestMatch.id) {
                            const lbl = document.querySelector('label[for="' + bestMatch.id + '"]');
                            if (lbl) clickTargets.push(lbl);
                        }
                        for (const ct of clickTargets) {
                            if (ct) ct.click();
                        }
                    }
                }

                // Final state check
                const finalState = getCheckedState(bestMatch);
                const desc = bestMatch.tagName + (bestMatch.id ? '#' + bestMatch.id : '')
                    + (bestMatch.getAttribute('role') ? '[role=' + bestMatch.getAttribute('role') + ']' : '');

                return {
                    success: finalState !== stateBefore,
                    element: desc,
                    state_before: stateBefore,
                    state_after: finalState,
                    verified: finalState !== stateBefore,
                };
            }
            """,
            label_text.strip(),
        )

        payload = self._parse_json(raw)
        if not isinstance(payload, dict):
            return ActionResult(error=f"toggle_checkbox: unexpected result '{_truncate(str(payload), 180)}'")

        success = bool(payload.get("success"))
        element_desc = payload.get("element") or "unknown"
        state_before = payload.get("state_before")
        state_after = payload.get("state_after")
        verified = bool(payload.get("verified"))

        if success and verified:
            msg = f"toggle_checkbox: toggled {element_desc} ({state_before} â†’ {state_after}) [VERIFIED]"
            return ActionResult(extracted_content=msg)

        if not success and "error" in payload:
            error_msg = payload["error"]
            visible = payload.get("visible_checkboxes") or []
            hint = ""
            if visible:
                hint = f" Visible checkboxes on page: {', '.join(visible[:5])}"
            return ActionResult(error=f"toggle_checkbox: {error_msg}{hint} [UNVERIFIED]")

        # Click executed but state didn't change - still report what happened
        msg = (
            f"toggle_checkbox: clicked {element_desc} but state may not have changed "
            f"({state_before} â†’ {state_after}). The checkbox may need 'Read More' clicked first, "
            f"or try clicking the checkbox via its element index instead. [UNVERIFIED]"
        )
        return ActionResult(extracted_content=msg)

    # ------------------------------------------------------------------
    # workday_create_account  (JS-based, handles entire Workday account flow)
    # ------------------------------------------------------------------
    async def _workday_create_account(self, browser_session: BrowserSession) -> ActionResult:
        """Handle Workday Create Account, with Sign In and external SSO detection."""
        identity = self.profile_data.get("identity", {})
        accounts = self.profile_data.get("accounts", {})
        default_account = accounts.get("default", {})
        login = self.profile_data.get("login", {})
        email = default_account.get("email") or login.get("email") or identity.get("email") or ""
        password = default_account.get("password") or login.get("password") or ""

        if not email or not password:
            return ActionResult(error="workday_create_account: no login credentials in profile data")

        page = await browser_session.get_current_page()
        if page is None:
            return ActionResult(error="workday_create_account: no active page")

        async def run_workday_js(skip_detection: bool, allow_terms_click: bool = True) -> dict[str, Any]:
            raw = await page.evaluate(
                """
                (creds) => {
                    const result = {
                        steps: [],
                        errors: [],
                        success: false,
                        needs_retry: false,
                        needs_terms_retry: false,
                        page_type: 'unknown',
                        is_external_sso: false,
                        current_host: window.location.hostname || '',
                        job_host: '',
                    };

                    const normalize = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
                    const isVisible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        if (!style) return false;
                        if (style.display === 'none' || style.visibility === 'hidden') return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };

                    const sameDomain = (a, b) => {
                        if (!a || !b) return true;
                        return a === b || a.endsWith('.' + b) || b.endsWith('.' + a);
                    };

                    if (!creds.skip_detection) {
                        try {
                            if (creds.job_url) {
                                result.job_host = new URL(creds.job_url).hostname || '';
                            }
                        } catch (e) {
                            result.job_host = '';
                        }

                        if (result.current_host && result.job_host && !sameDomain(result.current_host, result.job_host)) {
                            result.is_external_sso = true;
                            result.errors.push(
                                'EXTERNAL SSO REDIRECT: Current host (' + result.current_host + ') differs from job host (' + result.job_host + ').'
                            );
                            return result;
                        }
                    }

                    const allInputs = Array.from(document.querySelectorAll('input'));
                    const visibleInputs = allInputs.filter((el) => isVisible(el));
                    const passwordFields = [];
                    let emailField = null;
                    let passwordField = null;
                    let verifyPasswordField = null;

                    for (const inp of visibleInputs) {
                        const type = (inp.getAttribute('type') || '').toLowerCase();
                        const name = normalize(inp.getAttribute('name') || '');
                        const id = normalize(inp.getAttribute('id') || '');
                        const ariaLabel = normalize(inp.getAttribute('aria-label') || '');
                        const placeholder = normalize(inp.getAttribute('placeholder') || '');
                        const labelText = normalize((inp.labels && inp.labels[0] && inp.labels[0].textContent) || '');
                        const fullDesc = name + ' ' + id + ' ' + ariaLabel + ' ' + placeholder + ' ' + labelText;

                        if (type === 'hidden' || type === 'submit' || type === 'button' || type === 'file') {
                            continue;
                        }

                        if (type === 'email' || /email|e-mail/.test(fullDesc)) {
                            emailField = inp;
                            continue;
                        }

                        if (type === 'password') {
                            passwordFields.push(inp);
                            continue;
                        }

                        if (/email|e-mail/.test(fullDesc) && type === 'text' && !emailField) {
                            emailField = inp;
                        }
                    }

                    const links = Array.from(document.querySelectorAll('a, button, [role="link"], [role="button"], span'));
                    let createAccountLink = null;
                    for (const link of links) {
                        if (!isVisible(link)) continue;
                        const text = normalize(link.textContent || link.getAttribute('aria-label') || '');
                        if (
                            text.includes('create account') ||
                            text.includes('create an account') ||
                            text.includes('new user') ||
                            text.includes('sign up') ||
                            text.includes("don't have an account")
                        ) {
                            createAccountLink = link;
                            break;
                        }
                    }

                    if (passwordFields.length >= 2) {
                        passwordField = passwordFields[0];
                        verifyPasswordField = passwordFields[1];
                        result.page_type = 'create_account';
                    } else if (passwordFields.length === 1) {
                        passwordField = passwordFields[0];
                        result.page_type = 'sign_in';
                    }

                    if (!creds.skip_detection && passwordFields.length <= 1) {
                        if (createAccountLink) {
                            createAccountLink.click();
                            result.needs_retry = true;
                            result.steps.push(
                                'Detected Sign In page. Clicked Create Account link. Call workday_create_account again after page loads.'
                            );
                            return result;
                        }

                        result.errors.push(
                            "FAILED: Sign In page detected. DO NOT call workday_create_account again. Find a Create Account path or call done(success=false)."
                        );
                        return result;
                    }

                    const fillField = (el, value, label) => {
                        if (!el || !isVisible(el)) {
                            result.errors.push('Field not found or not visible: ' + label);
                            return;
                        }
                        el.focus();
                        el.value = '';
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.value = value;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.blur();
                        result.steps.push('Filled ' + label + ': ' + (label.toLowerCase().includes('password') ? '***' : value));
                    };

                    fillField(emailField, creds.email, 'Email');
                    fillField(passwordField, creds.password, 'Password');

                    if (!verifyPasswordField) {
                        result.errors.push(
                            'FAILED: Verify Password field not found. This appears to be Sign In, not Create Account. Do not retry Sign In.'
                        );
                        return result;
                    }
                    fillField(verifyPasswordField, creds.password, 'Verify Password');

                    // Some Workday flows require opening terms before the consent checkbox is interactable.
                    const termsLinks = Array.from(document.querySelectorAll('a, button, [role="link"], span'));
                    let termsLink = null;
                    for (const link of termsLinks) {
                        if (!isVisible(link)) continue;
                        const text = normalize(link.textContent || link.getAttribute('aria-label') || '');
                        if (
                            text.includes('read and accept') ||
                            text.includes('read more') ||
                            text.includes('view terms') ||
                            (text.includes('terms') && link.tagName === 'A')
                        ) {
                            termsLink = link;
                            break;
                        }
                    }
                    if (termsLink && creds.allow_terms_click) {
                        termsLink.click();
                        result.steps.push(
                            'Clicked terms link: ' +
                            normalize(termsLink.textContent || termsLink.getAttribute('aria-label') || '').substring(0, 50)
                        );
                        result.needs_terms_retry = true;
                        return result;
                    }

                    const checkboxSelectors = ['input[type="checkbox"]', '[role="checkbox"]', '[aria-checked]'];
                    let checkbox = null;
                    for (const selector of checkboxSelectors) {
                        const elements = document.querySelectorAll(selector);
                        for (const el of elements) {
                            if (!isVisible(el)) continue;
                            let parent = el.parentElement;
                            let surroundingText = '';
                            for (let i = 0; i < 4 && parent; i++) {
                                surroundingText += ' ' + (parent.textContent || '');
                                parent = parent.parentElement;
                            }
                            const text = normalize(surroundingText);
                            if (
                                text.includes('consent') ||
                                text.includes('agree') ||
                                text.includes('terms') ||
                                text.includes('privacy')
                            ) {
                                checkbox = el;
                                break;
                            }
                        }
                        if (checkbox) break;
                    }

                    if (checkbox) {
                        const aria = (checkbox.getAttribute('aria-checked') || '').toLowerCase();
                        const checked = aria === 'true' || checkbox.checked === true;
                        if (!checked) {
                            checkbox.click();
                            checkbox.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, composed: true }));
                            result.steps.push('Toggled consent checkbox');
                        } else {
                            result.steps.push('Consent checkbox already checked');
                        }
                    } else {
                        result.steps.push('No consent checkbox found');
                    }

                    const submitKeywords = ['create account', 'create an account', 'register', 'sign up', 'continue', 'submit', 'next'];
                    let submitBtn = null;
                    const buttons = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"]'));
                    for (const btn of buttons) {
                        if (!isVisible(btn)) continue;
                        const text = normalize(btn.textContent || btn.value || btn.getAttribute('aria-label') || '');
                        if (submitKeywords.some((keyword) => text.includes(keyword))) {
                            submitBtn = btn;
                            break;
                        }
                    }

                    if (!submitBtn) {
                        result.errors.push('Create Account submit button not found');
                    } else {
                        submitBtn.click();
                        result.steps.push('Clicked: ' + normalize(submitBtn.textContent || submitBtn.getAttribute('aria-label') || 'submit').substring(0, 40));
                    }

                    result.field_count = {
                        email: !!emailField,
                        password: !!passwordField,
                        verify_password: !!verifyPasswordField,
                        consent_checkbox: !!checkbox,
                        submit_button: !!submitBtn,
                    };
                    result.success = result.errors.length === 0;
                    return result;
                }
                """,
                {
                    "email": email,
                    "password": password,
                    "job_url": self.job_url or "",
                    "skip_detection": skip_detection,
                    "allow_terms_click": allow_terms_click,
                },
            )
            payload = self._parse_json(raw)
            return payload if isinstance(payload, dict) else {}

        payload = await run_workday_js(skip_detection=False, allow_terms_click=True)
        if payload.get("is_external_sso"):
            host = payload.get("current_host") or "unknown"
            job_host = payload.get("job_host") or "unknown"
            return ActionResult(
                error=(
                    f"EXTERNAL SSO REDIRECT to {host} (job host: {job_host}). "
                    "This likely requires corporate credentials. Call done(success=false) immediately."
                )
                )

        if payload.get("needs_retry"):
            await page.wait_for_timeout(2500)
            payload = await run_workday_js(skip_detection=True, allow_terms_click=True)
            if payload.get("is_external_sso"):
                host = payload.get("current_host") or "unknown"
                job_host = payload.get("job_host") or "unknown"
                return ActionResult(
                    error=(
                        f"EXTERNAL SSO REDIRECT to {host} (job host: {job_host}). "
                        "This likely requires corporate credentials. Call done(success=false) immediately."
                    )
                )

        if payload.get("needs_terms_retry"):
            await page.wait_for_timeout(2000)
            payload = await run_workday_js(skip_detection=True, allow_terms_click=False)
            if payload.get("is_external_sso"):
                host = payload.get("current_host") or "unknown"
                job_host = payload.get("job_host") or "unknown"
                return ActionResult(
                    error=(
                        f"EXTERNAL SSO REDIRECT to {host} (job host: {job_host}). "
                        "This likely requires corporate credentials. Call done(success=false) immediately."
                    )
                )

        if not isinstance(payload, dict):
            return ActionResult(error=f"workday_create_account: unexpected result '{_truncate(str(payload), 180)}'")

        # --- Fix 3A: Check for "account already exists" after submit ---
        if payload.get("success") or not payload.get("errors"):
            try:
                await page.wait_for_timeout(3000)
                exists_check = await page.evaluate("""() => {
                    const text = (document.body.innerText || '').toLowerCase();
                    const patterns = [
                        'already exists', 'already registered', 'already have an account',
                        'account already', 'email is already', 'email already in use',
                        'existing account', 'sign in instead', 'log in instead',
                    ];
                    for (const p of patterns) {
                        if (text.includes(p)) return { exists: true, pattern: p };
                    }
                    return { exists: false };
                }""")
                if exists_check and exists_check.get("exists"):
                    return ActionResult(error=(
                        f"ACCOUNT ALREADY EXISTS (detected: '{exists_check['pattern']}'). "
                        "DO NOT call workday_create_account again. "
                        "Switch to SIGN IN with the same email/password."
                    ))
            except Exception:
                pass

        steps = payload.get("steps") or []
        errors = payload.get("errors") or []
        success = bool(payload.get("success"))
        field_count = payload.get("field_count") or {}

        summary_parts = [f"workday_create_account: {len(steps)} steps completed"]
        for step_desc in steps:
            summary_parts.append(f"  - {step_desc}")

        if errors:
            for err in errors:
                summary_parts.append(f"  ERROR: {err}")

        found = [k for k, v in field_count.items() if v]
        missing = [k for k, v in field_count.items() if not v]
        if found:
            summary_parts.append(f"  Found: {', '.join(found)}")
        if missing:
            summary_parts.append(f"  Missing: {', '.join(missing)}")

        summary_parts.append("[VERIFIED]" if success else "[UNVERIFIED]")
        msg = "\n".join(summary_parts)

        if errors:
            return ActionResult(error=msg)

        return ActionResult(extracted_content=msg)

    # ------------------------------------------------------------------
    # check_page_state  (read-only JS, includes CAPTCHA detection)
    # ------------------------------------------------------------------
    async def _check_page_state(self, browser_session: BrowserSession) -> ActionResult:
        diagnostics = await self._collect_page_diagnostics(browser_session=browser_session, include_body_text=False)
        if diagnostics is None:
            return ActionResult(error="check_page_state: no active page")

        url = diagnostics.get("url") or ""
        title = diagnostics.get("title") or ""
        errors = diagnostics.get("errors") or []
        required_empty = int(diagnostics.get("required_empty") or 0)
        submit_visible = bool(diagnostics.get("submit_visible"))
        has_captcha = bool(diagnostics.get("has_captcha"))

        lines = [
            f"URL: {url}",
            f"Title: {title}",
            f"Visible errors: {len(errors)}",
            f"Required empty fields: {required_empty}",
            f"Submit visible: {submit_visible}",
        ]

        if has_captcha:
            lines.append("CAPTCHA/bot-check DETECTED on page. Call done with success=false to request human intervention.")

        for idx, message in enumerate(errors[:8], start=1):
            lines.append(f"Error {idx}: {_truncate(str(message), 180)}")

        return ActionResult(extracted_content="\n".join(lines))

    # ------------------------------------------------------------------
    # smart_fill  (JS-based, no CDP element resolution)
    # ------------------------------------------------------------------
    async def _smart_fill(self, browser_session: BrowserSession) -> ActionResult:
        if not self.profile_data:
            return ActionResult(extracted_content="smart_fill: no profile data available", metadata={"verified": False})

        identity = self.profile_data.get("identity", {})
        address = identity.get("address", {})

        flat_data = {
            "first_name": identity.get("first_name", ""),
            "last_name": identity.get("last_name", ""),
            "email": identity.get("email", ""),
            "phone": identity.get("phone", ""),
            "linkedin": identity.get("linkedin", ""),
            "website": identity.get("website", ""),
            "street": address.get("street", ""),
            "city": address.get("city", ""),
            "state": address.get("state", ""),
            "zip": address.get("zip", ""),
            "country": address.get("country", ""),
        }

        page = await browser_session.get_current_page()
        if page is None:
            return ActionResult(error="smart_fill: no active page", metadata={"verified": False})

        raw = await page.evaluate(
            """
            (data) => {
                const mapping = {
                    first_name: ['first_name', 'firstname', 'fname', 'given-name', 'givenname'],
                    last_name: ['last_name', 'lastname', 'lname', 'family-name', 'familyname', 'surname'],
                    email: ['email', 'e-mail', 'mail'],
                    phone: ['phone', 'mobile', 'cell', 'tel', 'contact'],
                    linkedin: ['linkedin', 'linked-in'],
                    website: ['website', 'portfolio', 'url'],
                    street: ['address', 'street', 'line1', 'address1'],
                    city: ['city', 'town'],
                    state: ['state', 'province', 'region'],
                    zip: ['zip', 'postal', 'postcode'],
                    country: ['country', 'nation'],
                };

                const setValue = (el, value) => {
                    if (!value) return false;
                    if (el.value && String(el.value).trim() !== '') return false;
                    el.focus();
                    el.value = value;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.blur();
                    return true;
                };

                const fields = Array.from(document.querySelectorAll('input, textarea'));
                const filledKeys = [];

                for (const field of fields) {
                    const tag = (field.tagName || '').toLowerCase();
                    const type = (field.getAttribute('type') || '').toLowerCase();
                    if (tag === 'input' && ['hidden', 'checkbox', 'radio', 'submit', 'button', 'file', 'password'].includes(type)) {
                        continue;
                    }

                    const descriptor = [
                        field.getAttribute('name') || '',
                        field.getAttribute('id') || '',
                        (field.labels && field.labels[0] && field.labels[0].innerText) || '',
                        field.getAttribute('aria-label') || '',
                        field.getAttribute('placeholder') || '',
                    ].join(' ').toLowerCase();

                    for (const [key, keywords] of Object.entries(mapping)) {
                        if (!keywords.some((word) => descriptor.includes(word))) continue;
                        if (setValue(field, data[key])) {
                            filledKeys.push(key);
                        }
                        break;
                    }
                }

                return Array.from(new Set(filledKeys));
            }
            """,
            flat_data,
        )

        parsed = self._parse_json(raw)
        filled_keys: list[str]
        if isinstance(parsed, list):
            filled_keys = [str(item) for item in parsed if str(item).strip()]
        elif isinstance(parsed, str):
            filled_keys = [item.strip() for item in parsed.split(",") if item.strip()]
        else:
            filled_keys = []

        if filled_keys:
            msg = f"smart_fill: filled {', '.join(sorted(set(filled_keys)))}"
            return ActionResult(extracted_content=msg, metadata={"verified": True, "filled": filled_keys})

        return ActionResult(
            extracted_content="smart_fill: no matching empty fields were filled",
            metadata={"verified": False, "filled": []},
        )

    # ------------------------------------------------------------------
    # guarded done  (reads page text via JS, no CDP element resolution)
    # ------------------------------------------------------------------
    async def _guarded_done(self, params: DoneAction, browser_session: BrowserSession, file_system: FileSystem) -> ActionResult:
        if params.success:
            diagnostics = await self._collect_page_diagnostics(browser_session=browser_session, include_body_text=True)
            body_text = str((diagnostics or {}).get("body_text") or "").lower()
            has_confirmation = any(phrase in body_text for phrase in CONFIRMATION_PHRASES)
            if not has_confirmation:
                return ActionResult(
                    error=(
                        "No submission confirmation found on page. Continue filling and submit the application "
                        "before calling done. If you are stuck, call done with success=false."
                    ),
                    metadata={"verified": False, "confirmation_found": False},
                )

        user_message = params.text
        len_max_memory = 100
        memory = f"Task completed: {params.success} - {params.text[:len_max_memory]}"
        if len(params.text) > len_max_memory:
            memory += f" - {len(params.text) - len_max_memory} more characters"

        attachments: list[str] = []
        if params.files_to_display and file_system:
            if self.display_files_in_done_text:
                file_msg = ""
                for file_name in params.files_to_display:
                    file_content = file_system.display_file(file_name)
                    if file_content:
                        file_msg += f"\n\n{file_name}:\n{file_content}"
                        attachments.append(file_name)
                if file_msg:
                    user_message += "\n\nAttachments:"
                    user_message += file_msg
            else:
                for file_name in params.files_to_display:
                    file_content = file_system.display_file(file_name)
                    if file_content:
                        attachments.append(file_name)

            attachments = [str(file_system.get_dir() / file_name) for file_name in attachments]

        return ActionResult(
            is_done=True,
            success=params.success,
            extracted_content=user_message,
            long_term_memory=memory,
            attachments=attachments,
            metadata={"verified": True},
        )

    # ------------------------------------------------------------------
    # shared page diagnostics helper  (read-only JS)
    # ------------------------------------------------------------------
    async def _collect_page_diagnostics(
        self,
        browser_session: BrowserSession,
        include_body_text: bool,
    ) -> Optional[dict[str, Any]]:
        page = await browser_session.get_current_page()
        if page is None:
            return None

        raw = await page.evaluate(
            """
            (includeBodyText) => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    if (!style) return false;
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };

                const errors = [];
                const errorSelectors = ['.error', '.alert-danger', '[role="alert"]', '.invalid-feedback', '.field-error'];
                for (const selector of errorSelectors) {
                    const nodes = document.querySelectorAll(selector);
                    for (const node of nodes) {
                        if (!isVisible(node)) continue;
                        const text = (node.textContent || '').replace(/\\s+/g, ' ').trim();
                        if (text) errors.push(text);
                    }
                }

                const requiredCandidates = Array.from(
                    document.querySelectorAll('input[required], select[required], textarea[required], [aria-required="true"]')
                );
                let requiredEmpty = 0;
                for (const field of requiredCandidates) {
                    if (!isVisible(field)) continue;
                    const role = (field.getAttribute('role') || '').toLowerCase();
                    const type = (field.getAttribute('type') || '').toLowerCase();
                    const isCheckbox = role === 'checkbox' || type === 'checkbox';
                    if (isCheckbox) {
                        const aria = (field.getAttribute('aria-checked') || '').toLowerCase();
                        const checked = aria === 'true' ? true : aria === 'false' ? false : !!field.checked;
                        if (!checked) requiredEmpty += 1;
                        continue;
                    }

                    let value = '';
                    if ((field.tagName || '').toLowerCase() === 'select') {
                        const selected = field.selectedOptions && field.selectedOptions.length > 0 ? field.selectedOptions[0] : null;
                        value = (selected && selected.textContent) ? selected.textContent : (field.value || '');
                    } else {
                        value = field.value || '';
                    }
                    if (!String(value || '').trim()) requiredEmpty += 1;
                }

                const submitSelectors = [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    'button[data-test*="submit"]',
                    'button[aria-label*="submit" i]',
                    'button',
                ];
                let submitVisible = false;
                for (const selector of submitSelectors) {
                    const nodes = document.querySelectorAll(selector);
                    for (const node of nodes) {
                        if (!isVisible(node)) continue;
                        const text = ((node.innerText || node.value || node.getAttribute('aria-label') || '') + '').toLowerCase();
                        if (selector === 'button' && !/submit|apply|send|finish|complete/.test(text)) continue;
                        submitVisible = true;
                        break;
                    }
                    if (submitVisible) break;
                }

                // Detect CAPTCHA / bot-check
                const bodyText = ((document.body && document.body.innerText) || '').toLowerCase();
                const captchaPhrases = [
                    'verify you are human', 'captcha', 'cloudflare',
                    'security verification', 'prove you are not a robot',
                    'recaptcha', 'hcaptcha',
                ];
                const hasCaptcha = captchaPhrases.some(p => bodyText.includes(p))
                    || !!document.querySelector('iframe[src*="captcha"], iframe[src*="challenge"]');

                return {
                    url: window.location.href,
                    title: document.title || '',
                    errors: errors.slice(0, 20),
                    required_empty: requiredEmpty,
                    submit_visible: submitVisible,
                    has_captcha: hasCaptcha,
                    body_text: includeBodyText ? bodyText : '',
                };
            }
            """,
            include_body_text,
        )

        parsed = self._parse_json(raw)
        if isinstance(parsed, dict):
            return parsed

        return {
            "url": "",
            "title": "",
            "errors": [],
            "required_empty": 0,
            "submit_visible": False,
            "has_captcha": False,
            "body_text": "",
        }

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_json(raw: Any) -> Any:
        if isinstance(raw, (dict, list)):
            return raw
        if raw is None:
            return {}
        if isinstance(raw, str):
            stripped = raw.strip()
            if not stripped:
                return ""
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    return raw
            return raw
        return raw


def create_job_applier_controller(
    profile_data: Optional[dict[str, Any]] = None,
    job_url: str = "",
) -> JobApplierTools:
    """Factory function to create the JobApplierTools controller."""
    return JobApplierTools(profile_data=profile_data, job_url=job_url)
