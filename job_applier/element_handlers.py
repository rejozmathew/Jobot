
"""
Element handlers for job application automation.

This module extends browser-use Tools with deterministic, verifiable actions
for dropdowns, checkboxes, file uploads, and form diagnostics.
"""
# Note: Do NOT use "from __future__ import annotations" here
# as it breaks browser-use registry type validation.

import asyncio
import json
import os
import re
from typing import Any, Optional

from browser_use.agent.views import ActionResult
from browser_use.browser import BrowserSession
from browser_use.filesystem.file_system import FileSystem
from browser_use.tools.service import Tools
from browser_use.tools.views import DoneAction

COUNTRY_PHONE_CODES: dict[str, list[str]] = {
    "US": ["+1", "1", "United States", "United States (+1)", "+1 (United States)", "US (+1)", "USA"],
    "CA": ["+1", "1", "Canada", "Canada (+1)"],
    "UK": ["+44", "44", "United Kingdom", "Great Britain", "UK", "United Kingdom (+44)"],
    "IN": ["+91", "91", "India", "India (+91)"],
    "AU": ["+61", "61", "Australia", "Australia (+61)"],
    "DE": ["+49", "49", "Germany", "Deutschland", "Germany (+49)"],
    "FR": ["+33", "33", "France", "France (+33)"],
    "ES": ["+34", "34", "Spain", "Espana", "Spain (+34)"],
    "IT": ["+39", "39", "Italy", "Italia", "Italy (+39)"],
    "NL": ["+31", "31", "Netherlands", "Nederland", "Netherlands (+31)"],
    "SE": ["+46", "46", "Sweden", "Sweden (+46)"],
    "NO": ["+47", "47", "Norway", "Norway (+47)"],
    "DK": ["+45", "45", "Denmark", "Denmark (+45)"],
    "CH": ["+41", "41", "Switzerland", "Swiss", "Switzerland (+41)"],
    "IE": ["+353", "353", "Ireland", "Ireland (+353)"],
    "NZ": ["+64", "64", "New Zealand", "New Zealand (+64)"],
    "SG": ["+65", "65", "Singapore", "Singapore (+65)"],
    "JP": ["+81", "81", "Japan", "Japan (+81)"],
    "KR": ["+82", "82", "South Korea", "Korea", "South Korea (+82)"],
    "BR": ["+55", "55", "Brazil", "Brasil", "Brazil (+55)"],
}

CONFIRMATION_PHRASES = (
    "application submitted",
    "thank you for applying",
    "successfully submitted",
    "application received",
    "application confirmed",
)


def _normalize_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[\(\)\[\],]", " ", text)
    text = re.sub(r"[^a-z0-9+ ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _truncate(value: str, limit: int = 120) -> str:
    text = str(value or "")
    return text if len(text) <= limit else f"{text[:limit - 3]}..."


class JobApplierTools(Tools):
    """Extended tools for job application automation."""

    def __init__(
        self,
        profile_data: Optional[dict[str, Any]] = None,
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
        self._register_custom_actions()

    def _register_custom_actions(self) -> None:
        @self.registry.action(
            "Fill standard and dynamic dropdowns reliably. Use this for combobox/autocomplete dropdowns."
        )
        async def fill_dropdown(index: int, value: str, browser_session: BrowserSession):
            return await self._fill_dropdown(index=index, value=value, browser_session=browser_session)

        @self.registry.action("Check or uncheck checkbox controls reliably, including custom role=checkbox elements.")
        async def check_checkbox(index: int, checked: bool = True, browser_session: BrowserSession = None):
            if browser_session is None:
                return ActionResult(error="check_checkbox requires browser_session")
            return await self._check_checkbox(index=index, checked=checked, browser_session=browser_session)

        @self.registry.action("Upload resume/CV file with fallback lookup and verification.")
        async def upload_resume(
            index: int,
            path: str,
            wait_seconds: int = 3,
            browser_session: BrowserSession = None,
            available_file_paths: list[str] | None = None,
        ):
            if browser_session is None:
                return ActionResult(error="upload_resume requires browser_session")
            return await self._upload_resume(
                index=index,
                path=path,
                wait_seconds=wait_seconds,
                browser_session=browser_session,
                available_file_paths=available_file_paths or [],
            )

        @self.registry.action("Scan all form fields and report current values, empty required fields, and checkbox states.")
        async def scan_form_fields(browser_session: BrowserSession):
            return await self._scan_form_fields(browser_session=browser_session)

        @self.registry.action("Check page diagnostics: visible errors, required-empty count, submit visibility, URL, and title.")
        async def check_page_state(browser_session: BrowserSession):
            return await self._check_page_state(browser_session=browser_session)

        @self.registry.action("Heuristically fill standard text/textarea fields from profile data.")
        async def smart_fill(browser_session: BrowserSession):
            return await self._smart_fill(browser_session=browser_session)

        if self.get_output_model() is None:
            @self.registry.action("Complete task.", param_model=DoneAction)
            async def done(params: DoneAction, browser_session: BrowserSession, file_system: FileSystem):
                return await self._guarded_done(params=params, browser_session=browser_session, file_system=file_system)

    async def _fill_dropdown(self, index: int, value: str, browser_session: BrowserSession) -> ActionResult:
        node = await browser_session.get_element_by_index(index)
        if node is None:
            msg = self._verification_message(
                "fill_dropdown",
                f"element #{index} not found in current DOM snapshot",
                verified=False,
            )
            return ActionResult(extracted_content=msg, metadata={"verified": False, "index": index})

        aliases = self._dropdown_aliases(value)
        label = self._node_label(node)

        try:
            if node.node_name.lower() == "select":
                result = await self.select_dropdown(index=index, text=value, browser_session=browser_session)
                state = await self._read_control_state(browser_session, node)
                final_value = str(state.get("selected_text") or state.get("value") or "")
                verified = self._matches_any_alias(final_value, aliases)
                detail = f"selected '{_truncate(value)}' in {label}; final value='{_truncate(final_value)}'"
                if result.error:
                    detail = f"{detail}; tool_error='{_truncate(result.error)}'"
                msg = self._verification_message("fill_dropdown", detail, verified)
                return ActionResult(
                    extracted_content=msg,
                    metadata={
                        "verified": verified,
                        "index": index,
                        "final_value": final_value,
                        "mode": "native_select",
                    },
                )

            page = await browser_session.get_current_page()
            if page is None:
                msg = self._verification_message("fill_dropdown", "no active page available", verified=False)
                return ActionResult(extracted_content=msg, metadata={"verified": False, "index": index})

            element = await page.get_element(node.backend_node_id)
            # fill() in browser-use types character-by-character via CDP keyDown/char/keyUp events
            # This triggers React/Vue onChange per keystroke (unlike Playwright's fill which sets value directly)
            await element.fill(value, clear=True)
            await asyncio.sleep(0.3)

            # Actively poll for dropdown options to appear (up to 2s)
            # Critical for slow-loading React dropdowns — replaces a fixed 350ms sleep
            for _poll in range(8):  # 8 x 250ms = 2s max
                has_options = await page.evaluate("""
                    () => {
                        const selectors = '[role="option"], [role="listbox"] li, .dropdown-item';
                        for (const sel of selectors.split(', ')) {
                            const els = document.querySelectorAll(sel);
                            for (const el of els) {
                                const style = window.getComputedStyle(el);
                                if (style.display !== 'none' && style.visibility !== 'hidden') return true;
                            }
                        }
                        return false;
                    }
                """)
                if has_options == "true" or has_options is True:
                    break
                await asyncio.sleep(0.25)

            selection = await self._pick_dropdown_option(page=page, desired=value, aliases=aliases)
            await asyncio.sleep(0.2)

            state = await self._read_control_state(browser_session, node)
            final_value = str(state.get("value") or state.get("selected_text") or state.get("text") or "")
            clicked_text = str(selection.get("clicked") or "")
            options = selection.get("options") or []

            verified = self._matches_any_alias(final_value, aliases) or self._matches_any_alias(clicked_text, aliases)
            option_preview = ", ".join([_truncate(str(opt), 40) for opt in options[:6]])

            detail_parts = [
                f"typed '{_truncate(value)}' in {label}",
                f"clicked='{_truncate(clicked_text)}'" if clicked_text else "no option clicked",
                f"final value='{_truncate(final_value)}'",
            ]
            if option_preview:
                detail_parts.append(f"options=[{option_preview}]")

            msg = self._verification_message("fill_dropdown", "; ".join(detail_parts), verified)
            return ActionResult(
                extracted_content=msg,
                metadata={
                    "verified": verified,
                    "index": index,
                    "final_value": final_value,
                    "clicked": clicked_text,
                    "options": options[:12],
                    "mode": "custom_dropdown",
                },
            )

        except Exception as exc:
            msg = self._verification_message(
                "fill_dropdown",
                f"exception while filling {label}: {_truncate(str(exc), 220)}",
                verified=False,
            )
            return ActionResult(error=msg, metadata={"verified": False, "index": index})

    async def _check_checkbox(self, index: int, checked: bool, browser_session: BrowserSession) -> ActionResult:
        node = await browser_session.get_element_by_index(index)
        if node is None:
            msg = self._verification_message(
                "check_checkbox",
                f"element #{index} not found in current DOM snapshot",
                verified=False,
            )
            return ActionResult(extracted_content=msg, metadata={"verified": False, "index": index})

        label = self._node_label(node)
        page = await browser_session.get_current_page()
        if page is None:
            msg = self._verification_message("check_checkbox", "no active page available", verified=False)
            return ActionResult(extracted_content=msg, metadata={"verified": False, "index": index})

        try:
            element = await page.get_element(node.backend_node_id)
            attrs = node.attributes or {}
            tag = node.node_name.lower()
            input_type = (attrs.get("type") or "").lower()
            role = (attrs.get("role") or "").lower()

            if tag == "input" and input_type == "checkbox":
                await element.evaluate(
                    """
                    (desired) => {
                        this.checked = !!desired;
                        this.dispatchEvent(new Event('input', { bubbles: true }));
                        this.dispatchEvent(new Event('change', { bubbles: true }));
                        this.dispatchEvent(new Event('click', { bubbles: true }));
                        return { checked: this.checked, aria_checked: this.getAttribute('aria-checked') || '' };
                    }
                    """,
                    checked,
                )
            else:
                for _ in range(2):
                    current = await self._read_checkbox_value(element)
                    if current == checked:
                        break
                    try:
                        await element.click()
                    except Exception:
                        pass
                    await asyncio.sleep(0.2)

                current = await self._read_checkbox_value(element)
                if current != checked:
                    await element.evaluate(
                        """
                        (desired) => {
                            const getLabel = () => {
                                if (this.id) {
                                    const escaped = (window.CSS && CSS.escape) ? CSS.escape(this.id) : this.id;
                                    const byFor = document.querySelector(`label[for="${escaped}"]`);
                                    if (byFor) return byFor;
                                }
                                if (this.closest('label')) return this.closest('label');
                                if (this.parentElement) {
                                    const withinParent = this.parentElement.querySelector('label');
                                    if (withinParent) return withinParent;
                                }
                                return null;
                            };
                            const label = getLabel();
                            if (!label) {
                                return { clicked_label: false };
                            }
                            label.scrollIntoView({ block: 'center', inline: 'nearest' });
                            label.click();
                            return { clicked_label: true };
                        }
                        """,
                        checked,
                    )
                    await asyncio.sleep(0.2)

            resolved = await self._read_checkbox_value(element)
            verified = resolved == checked
            mode = "native_checkbox" if (tag == "input" and input_type == "checkbox") else (role or "custom_checkbox")
            detail = f"target={label}; requested={checked}; actual={resolved}; mode={mode}"
            msg = self._verification_message("check_checkbox", detail, verified)
            return ActionResult(
                extracted_content=msg,
                metadata={"verified": verified, "index": index, "actual": resolved, "requested": checked},
            )

        except Exception as exc:
            msg = self._verification_message(
                "check_checkbox",
                f"exception while setting {label}: {_truncate(str(exc), 220)}",
                verified=False,
            )
            return ActionResult(error=msg, metadata={"verified": False, "index": index})
    async def _upload_resume(
        self,
        index: int,
        path: str,
        wait_seconds: int,
        browser_session: BrowserSession,
        available_file_paths: list[str],
    ) -> ActionResult:
        target_path = os.path.expanduser(path or "")
        before_filled = await self._count_prefilled_fields(browser_session)
        attempts: list[str] = []

        upload_ok = False
        used_index = index

        try:
            primary = await self.upload_file(
                index=index,
                path=target_path,
                browser_session=browser_session,
                available_file_paths=available_file_paths,
            )
            if primary.error:
                attempts.append(f"index {index}: {_truncate(primary.error, 100)}")
            else:
                upload_ok = True
                attempts.append(f"index {index}: success")

            if not upload_ok:
                selector_map = await browser_session.get_selector_map()
                fallback_indexes = [i for i, candidate in selector_map.items() if browser_session.is_file_input(candidate)]
                for candidate_index in fallback_indexes:
                    if candidate_index == index:
                        continue
                    retry_result = await self.upload_file(
                        index=candidate_index,
                        path=target_path,
                        browser_session=browser_session,
                        available_file_paths=available_file_paths,
                    )
                    if retry_result.error:
                        attempts.append(f"index {candidate_index}: {_truncate(retry_result.error, 100)}")
                        continue
                    attempts.append(f"index {candidate_index}: success")
                    upload_ok = True
                    used_index = candidate_index
                    break

            if wait_seconds > 0:
                await asyncio.sleep(min(max(wait_seconds, 0), 10))

            after_filled = await self._count_prefilled_fields(browser_session)
            file_count = await self._count_selected_files(browser_session)
            autofill_delta = after_filled - before_filled

            verified = upload_ok and (file_count > 0 or autofill_delta > 0)
            detail_parts = [
                f"path='{_truncate(target_path, 100)}'",
                f"used_index={used_index}",
                f"selected_files={file_count}",
                f"autofill_delta={autofill_delta}",
            ]
            if attempts:
                detail_parts.append(f"attempts=[{'; '.join(attempts[:6])}]")

            msg = self._verification_message("upload_resume", "; ".join(detail_parts), verified)
            return ActionResult(
                extracted_content=msg,
                metadata={
                    "verified": verified,
                    "used_index": used_index,
                    "selected_files": file_count,
                    "autofill_delta": autofill_delta,
                    "attempts": attempts[:10],
                },
            )

        except Exception as exc:
            msg = self._verification_message(
                "upload_resume",
                f"exception while uploading resume: {_truncate(str(exc), 220)}",
                verified=False,
            )
            return ActionResult(error=msg, metadata={"verified": False, "index": index})

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
    async def _check_page_state(self, browser_session: BrowserSession) -> ActionResult:
        diagnostics = await self._collect_page_diagnostics(browser_session=browser_session, include_body_text=False)
        if diagnostics is None:
            return ActionResult(error="check_page_state: no active page")

        url = diagnostics.get("url") or ""
        title = diagnostics.get("title") or ""
        errors = diagnostics.get("errors") or []
        required_empty = int(diagnostics.get("required_empty") or 0)
        submit_visible = bool(diagnostics.get("submit_visible"))

        lines = [
            f"URL: {url}",
            f"Title: {title}",
            f"Visible errors: {len(errors)}",
            f"Required empty fields: {required_empty}",
            f"Submit visible: {submit_visible}",
        ]

        for idx, message in enumerate(errors[:8], start=1):
            lines.append(f"Error {idx}: {_truncate(str(message), 180)}")

        return ActionResult(extracted_content="\n".join(lines))

    async def _smart_fill(self, browser_session: BrowserSession) -> ActionResult:
        if not self.profile_data:
            return ActionResult(extracted_content="smart_fill: no profile data available [UNVERIFIED]", metadata={"verified": False})

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
            msg = f"smart_fill: filled {', '.join(sorted(set(filled_keys)))} [VERIFIED]"
            return ActionResult(extracted_content=msg, metadata={"verified": True, "filled": filled_keys})

        return ActionResult(
            extracted_content="smart_fill: no matching empty fields were filled [UNVERIFIED]",
            metadata={"verified": False, "filled": []},
        )

    async def _guarded_done(self, params: DoneAction, browser_session: BrowserSession, file_system: FileSystem) -> ActionResult:
        if params.success:
            diagnostics = await self._collect_page_diagnostics(browser_session=browser_session, include_body_text=True)
            body_text = str((diagnostics or {}).get("body_text") or "").lower()
            has_confirmation = any(phrase in body_text for phrase in CONFIRMATION_PHRASES)
            if not has_confirmation:
                return ActionResult(
                    error=(
                        "No submission confirmation found on page. Continue filling and submit the application "
                        "before calling done."
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

                return {
                    url: window.location.href,
                    title: document.title || '',
                    errors: errors.slice(0, 20),
                    required_empty: requiredEmpty,
                    submit_visible: submitVisible,
                    body_text: includeBodyText ? ((document.body && document.body.innerText) || '') : '',
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
            "body_text": "",
        }

    async def _count_prefilled_fields(self, browser_session: BrowserSession) -> int:
        page = await browser_session.get_current_page()
        if page is None:
            return 0

        raw = await page.evaluate(
            """
            () => {
                let count = 0;
                const fields = document.querySelectorAll('input, textarea, select');
                for (const field of fields) {
                    const tag = (field.tagName || '').toLowerCase();
                    const type = (field.getAttribute('type') || '').toLowerCase();
                    if (tag === 'input' && ['hidden', 'submit', 'button', 'file', 'checkbox', 'radio', 'password'].includes(type)) {
                        continue;
                    }
                    let value = '';
                    if (tag === 'select') {
                        const selected = field.selectedOptions && field.selectedOptions.length > 0 ? field.selectedOptions[0] : null;
                        value = (selected && selected.textContent) ? selected.textContent : (field.value || '');
                    } else {
                        value = field.value || '';
                    }
                    if (String(value || '').trim()) count += 1;
                }
                return count;
            }
            """
        )

        try:
            return int(str(raw).strip() or 0)
        except Exception:
            return 0

    async def _count_selected_files(self, browser_session: BrowserSession) -> int:
        page = await browser_session.get_current_page()
        if page is None:
            return 0

        raw = await page.evaluate(
            """
            () => {
                const fileInputs = document.querySelectorAll('input[type="file"]');
                let selected = 0;
                for (const input of fileInputs) {
                    if (input.files && input.files.length > 0) selected += input.files.length;
                }
                return selected;
            }
            """
        )

        try:
            return int(str(raw).strip() or 0)
        except Exception:
            return 0

    async def _read_control_state(self, browser_session: BrowserSession, node) -> dict[str, Any]:
        page = await browser_session.get_current_page()
        if page is None:
            return {}

        element = await page.get_element(node.backend_node_id)
        raw = await element.evaluate(
            """
            () => {
                const selected = this.selectedOptions && this.selectedOptions.length > 0 ? this.selectedOptions[0] : null;
                const text = this.innerText || this.textContent || '';
                return {
                    value: this.value || '',
                    text: text.trim(),
                    selected_text: selected ? (selected.textContent || '').trim() : '',
                };
            }
            """
        )
        parsed = self._parse_json(raw)
        return parsed if isinstance(parsed, dict) else {"value": str(parsed or "")}

    async def _read_checkbox_value(self, element) -> bool:
        raw = await element.evaluate(
            """
            () => {
                const aria = (this.getAttribute('aria-checked') || '').toLowerCase();
                const checked = this.checked === true;
                return { aria_checked: aria, checked };
            }
            """
        )
        parsed = self._parse_json(raw)
        if isinstance(parsed, dict):
            aria = str(parsed.get("aria_checked") or "").lower()
            if aria == "true":
                return True
            if aria == "false":
                return False
            return bool(parsed.get("checked"))
        return False

    async def _pick_dropdown_option(self, page, desired: str, aliases: list[str]) -> dict[str, Any]:
        raw = await page.evaluate(
            """
            (desired, aliases) => {
                const norm = (value) => String(value || '')
                    .toLowerCase()
                    .replace(/[()\\[\\],]/g, ' ')
                    .replace(/[^a-z0-9+ ]+/g, ' ')
                    .replace(/\\s+/g, ' ')
                    .trim();

                const visible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    if (!style) return false;
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };

                const selectors = [
                    '[role="option"]',
                    '[role="listbox"] li',
                    '.dropdown-item',
                    '[class*="option"]',
                    'li[aria-selected]',
                ];

                const candidates = new Set([norm(desired)]);
                for (const alias of aliases || []) candidates.add(norm(alias));

                const options = [];
                const seen = new Set();
                for (const selector of selectors) {
                    for (const el of document.querySelectorAll(selector)) {
                        if (!visible(el)) continue;
                        const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                        if (!text) continue;
                        const key = `${selector}::${text}`;
                        if (seen.has(key)) continue;
                        seen.add(key);
                        options.push({ text, normalized: norm(text), el });
                    }
                }

                const score = (normalized) => {
                    if (!normalized) return -1;
                    if (candidates.has(normalized)) return 500;

                    let best = -1;
                    for (const alias of candidates) {
                        if (!alias) continue;
                        if (normalized.includes(alias)) best = Math.max(best, 350);
                        if (alias.includes(normalized)) best = Math.max(best, 320);

                        const aliasDigits = alias.replace(/\\D/g, '');
                        const normDigits = normalized.replace(/\\D/g, '');
                        if (aliasDigits && normDigits && aliasDigits === normDigits) best = Math.max(best, 380);

                        const aliasTokens = alias.split(' ').filter(Boolean);
                        const normTokens = normalized.split(' ').filter(Boolean);
                        const overlap = aliasTokens.filter((token) => normTokens.includes(token)).length;
                        if (overlap > 0) {
                            best = Math.max(best, Math.min(280, overlap * 80));
                        }
                    }
                    return best;
                };

                let bestOption = null;
                let bestScore = -1;
                for (const option of options) {
                    const optionScore = score(option.normalized);
                    if (optionScore > bestScore) {
                        bestScore = optionScore;
                        bestOption = option;
                    }
                }

                let clicked = '';
                if (bestOption && bestScore >= 0) {
                    bestOption.el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
                    bestOption.el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    bestOption.el.click();
                    bestOption.el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    clicked = bestOption.text;
                }

                return {
                    clicked,
                    score: bestScore,
                    options: options.map((item) => item.text).slice(0, 30),
                };
            }
            """,
            desired,
            aliases,
        )

        parsed = self._parse_json(raw)
        if isinstance(parsed, dict):
            return parsed
        return {"clicked": "", "score": -1, "options": []}

    def _dropdown_aliases(self, value: str) -> list[str]:
        aliases: set[str] = {str(value or "").strip()}
        normalized_value = _normalize_text(value)
        value_digits = re.sub(r"\D", "", str(value or ""))

        for country_code, country_aliases in COUNTRY_PHONE_CODES.items():
            normalized_aliases = {_normalize_text(alias): alias for alias in country_aliases}
            alias_digits = {re.sub(r"\D", "", alias) for alias in country_aliases}

            if normalized_value in normalized_aliases:
                aliases.update(country_aliases)
                aliases.add(country_code)
                continue

            if normalized_value == country_code.lower():
                aliases.update(country_aliases)
                aliases.add(country_code)
                continue

            if value_digits and value_digits in alias_digits:
                aliases.update(country_aliases)
                aliases.add(country_code)

        aliases = {item for item in aliases if item and str(item).strip()}
        return sorted(aliases)

    def _matches_any_alias(self, candidate: str, aliases: list[str]) -> bool:
        normalized_candidate = _normalize_text(candidate)
        if not normalized_candidate:
            return False

        candidate_digits = re.sub(r"\D", "", candidate or "")
        for alias in aliases:
            normalized_alias = _normalize_text(alias)
            if not normalized_alias:
                continue
            if normalized_candidate == normalized_alias:
                return True
            if normalized_alias in normalized_candidate or normalized_candidate in normalized_alias:
                return True

            alias_digits = re.sub(r"\D", "", alias or "")
            if alias_digits and candidate_digits and alias_digits == candidate_digits:
                return True

        return False

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

    @staticmethod
    def _node_label(node: Any) -> str:
        attrs = node.attributes or {}
        for key in ("aria-label", "placeholder", "name", "id", "title"):
            if attrs.get(key):
                return f"{node.node_name.lower()}[{key}='{attrs.get(key)}']"

        ax_node = getattr(node, "ax_node", None)
        if ax_node and getattr(ax_node, "name", None):
            return f"{node.node_name.lower()}['{ax_node.name}']"

        return f"{node.node_name.lower()}#{node.backend_node_id}"

    @staticmethod
    def _verification_message(action_name: str, details: str, verified: bool) -> str:
        marker = "[VERIFIED]" if verified else "[UNVERIFIED]"
        return f"{action_name}: {details} {marker}"


def create_job_applier_controller(profile_data: Optional[dict[str, Any]] = None) -> JobApplierTools:
    """Factory function to create the JobApplierTools controller."""
    return JobApplierTools(profile_data=profile_data)
