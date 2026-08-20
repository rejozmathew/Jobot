"""Deterministic Workday handler with LLM fallback handoff."""

from __future__ import annotations

import asyncio
import os
import re
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import urlparse

from .base import BasePlatformHandler, HandlerOutcome, HandlerResult, env_flag, safe_navigate

WORKDAY_HOST_MARKER = "myworkdayjobs.com"
WORKDAY_EXISTING_DATA_CONFLICT_KEYWORDS = (
    "already exists",
    "previous worker information",
    "previously worked for",
    "address already exists",
    "phone number already exists",
)
WORKDAY_REQUIRED_FIELD_LOOP_KEYWORDS = (
    "previously worked for",
    "how did you hear about us",
    "referral source",
    "phone device type",
    "phone number",
    "postal code",
    "zip code",
    "address line",
    "first name",
    "last name",
)
WORKDAY_REFERRAL_LOOP_KEYWORDS = (
    "how did you hear about us",
    "referral source",
    "linkedinlinkedin",
    "venturefizz",
)
WORKDAY_EXPERIENCE_FIELD_LOOP_KEYWORDS = (
    "required fields remaining: from",
    "from field",
    "to field",
    "role description",
    "type to add skills",
)
_MM_YYYY_RE = re.compile(r"^\d{1,2}/\d{4}$")
AUTH_STATES = {"AUTH", "CREATE_ACCOUNT", "SIGN_IN", "LEGAL_ACCEPT"}
FORM_STATES = {"CONTACT", "EXPERIENCE", "DISCLOSURES", "SELF_ID", "REVIEW_SUBMIT"}
DETECT_WAIT_NOTE = "waited for dynamic Workday controls to render"
WD_OPTION_PLACEHOLDERS = {
    "",
    "select",
    "select one",
    "choose one",
    "please select",
    "-- select --",
    "search",
}
US_STATE_BY_ABBR = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

# Workday tiered selectors: automation IDs first, semantic/generic fallback second.
WD_SEL: dict[str, list[str]] = {
    "apply_button": [
        "[data-automation-id='applyButton']",
        "[data-automation-id='applyManually']",
        "button[data-automation-id*='apply']",
        "a[data-automation-id*='apply']",
        "a[href*='apply']",
        "button[type='submit']",
    ],
    "email": [
        "input[data-automation-id='email']",
        "input[data-automation-id*='email']",
        "input[type='email']",
        "input[name*='email' i]",
        "input[id*='email' i]",
        "input[name*='user' i]",
        "input[id*='user' i]",
    ],
    "password": [
        "input[data-automation-id='password']",
        "input[data-automation-id*='password']",
        "input[type='password']",
        "input[name*='password' i]",
        "input[id*='password' i]",
    ],
    "verify_password": [
        "input[data-automation-id='verifyPassword']",
        "input[data-automation-id*='verify' i]",
        "input[data-automation-id*='confirm' i]",
        "input[name*='verify' i]",
        "input[name*='confirm' i]",
        "input[id*='verify' i]",
        "input[id*='confirm' i]",
    ],
    "consent_checkbox": [
        "input[data-automation-id='createAccountCheckbox']",
        "input[type='checkbox']",
        "[role='checkbox']",
    ],
    "create_submit": [
        "button[data-automation-id*='create']",
        "button[type='submit']",
        "input[type='submit']",
    ],
    "signin_submit": [
        "button[data-automation-id*='signIn']",
        "button[data-automation-id*='login']",
        "button[type='submit']",
        "input[type='submit']",
    ],
    "create_account_link": [
        "a[data-automation-id*='create']",
        "button[data-automation-id*='create']",
    ],
    "sign_in_link": [
        "a[data-automation-id*='signIn']",
        "button[data-automation-id*='signIn']",
        "a[href*='sign-in']",
        "a[href*='login']",
    ],
    "next_button": [
        "button[data-automation-id*='saveAndContinue']",
        "button[data-automation-id*='continue']",
        "button[type='submit']",
        "input[type='submit']",
    ],
    "submit_button": [
        "button[data-automation-id*='submit']",
        "button[type='submit']",
        "input[type='submit']",
    ],
    "first_name": [
        "input[data-automation-id='legalNameSection_firstName']",
        "input[name*='first' i]",
        "input[id*='first' i]",
    ],
    "last_name": [
        "input[data-automation-id='legalNameSection_lastName']",
        "input[name*='last' i]",
        "input[id*='last' i]",
    ],
    "address_line1": [
        "input[data-automation-id='addressSection_addressLine1']",
        "input[name*='address' i]",
        "input[id*='address' i]",
    ],
    "city": [
        "input[data-automation-id='addressSection_city']",
        "input[name*='city' i]",
        "input[id*='city' i]",
    ],
    "postal_code": [
        "input[data-automation-id='addressSection_postalCode']",
        "input[name*='postal' i]",
        "input[name*='zip' i]",
        "input[id*='postal' i]",
        "input[id*='zip' i]",
    ],
    "phone_number": [
        "input[data-automation-id='phone-number']",
        "input[name*='phone' i]",
        "input[id*='phone' i]",
        "input[type='tel']",
    ],
    "state_dropdown": [
        "button[data-automation-id='addressSection_countryRegion']",
        "button[data-automation-id*='region']",
        "button[data-automation-id*='state']",
        "div[data-automation-id*='countryRegion'] button",
        "div[data-automation-id*='state'] button",
        # Workday's contact form uses a stable element id (no data-automation-id):
        "button[id*='countryRegion' i]",
        "button[id*='region' i]",
        "button[id*='state' i]",
        # Workday's state/region field is often a DIV (not button) with a stable id:
        "div[id*='countryRegion' i]",
        "div[id*='region' i]",
        "[role='combobox'][id*='region' i]",
        "[role='combobox'][id*='state' i]",
    ],
    "phone_code_dropdown": [
        "button[id*='countryPhoneCode' i]",
        "input[id*='countryPhoneCode' i]",
        "div[id*='countryPhoneCode' i]",
        "[role='combobox'][id*='countryPhoneCode' i]",
        "button[data-automation-id*='phoneCode']",
        "[data-automation-id*='phoneCode'] button",
    ],
    "phone_type_dropdown": [
        "button[data-automation-id='phone-device-type']",
        "button[data-automation-id*='device']",
        "div[data-automation-id*='phone-device-type'] button",
        "div[data-automation-id*='device-type'] button",
    ],
    "error_message": [
        "div[data-automation-id*='error']",
        "[role='alert']",
        ".error",
        ".validation-error",
        ".field-error",
    ],
}


@dataclass(slots=True)
class WorkdayCredentials:
    email: str
    password: str


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def is_workday_url(url: str) -> bool:
    return WORKDAY_HOST_MARKER in normalize_text(url)


def context_matches(context: str, keywords: Iterable[str]) -> bool:
    normalized = normalize_text(context)
    return any(normalize_text(keyword) in normalized for keyword in keywords)


def month_year_from_value(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = raw.split("-")
    if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
        year = parts[0]
        month = parts[1]
        if month.isdigit():
            month = month.zfill(2)
            if 1 <= int(month) <= 12:
                return f"{month}/{year}"
    if _MM_YYYY_RE.fullmatch(raw):
        month_part, year_part = raw.split("/", 1)
        return f"{month_part.zfill(2)}/{year_part}"
    return ""


class WorkdayHandler(BasePlatformHandler):
    platform_name = "workday"

    def __init__(self, *, browser_session: Any, profile: dict[str, Any] | None, job_url: str, trace_hook=None) -> None:
        super().__init__(browser_session=browser_session, profile=profile, job_url=job_url, trace_hook=trace_hook)
        self.auth_create_attempts = 0
        self.auth_signin_attempts = 0
        self.same_state_repeat = 0
        self.last_state = ""
        self.next_click_per_state: dict[str, int] = {}
        self.total_steps = 0
        self.steps: list[str] = []
        self.creds = self._extract_credentials()
        identity = self.profile.get("identity", {}) if isinstance(self.profile.get("identity"), dict) else {}
        self.identity = identity
        self.address = identity.get("address", {}) if isinstance(identity.get("address"), dict) else {}
        self.standard_answers = (
            self.profile.get("standard_answers", {})
            if isinstance(self.profile.get("standard_answers"), dict)
            else {}
        )
        self.detect_wait_steps = 0
        self.conflict_fix_attempts = 0
        self.referral_fix_attempts = 0
        self.required_loop_fix_attempts = 0
        self.state_autofill_attempts: dict[str, int] = {}
        # Dry-run: fill everything and reach the final review/submit screen,
        # then STOP instead of clicking Submit. No side effects past that point.
        self.dry_run = env_flag("JOB_APPLIER_DRY_RUN", False)

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return is_workday_url(url)

    def _extract_credentials(self) -> WorkdayCredentials:
        profile = self.profile if isinstance(self.profile, dict) else {}
        identity = profile.get("identity", {}) if isinstance(profile.get("identity"), dict) else {}
        accounts = profile.get("accounts", {}) if isinstance(profile.get("accounts"), dict) else {}
        default_account = accounts.get("default", {}) if isinstance(accounts.get("default"), dict) else {}
        email = str(default_account.get("email") or identity.get("email") or "").strip()
        password = str(default_account.get("password") or os.getenv("JOB_APPLIER_FALLBACK_PASSWORD", "ApplyFlow#2026!")).strip()
        return WorkdayCredentials(email=email, password=password)

    def _referral_candidates(self) -> list[str]:
        raw_candidates = self.standard_answers.get("job_source_preference")
        if isinstance(raw_candidates, list):
            values = [str(v).strip() for v in raw_candidates if str(v).strip()]
        else:
            values = []
        primary = str(self.standard_answers.get("job_source") or "").strip()
        generic_first = [
            "Other",
            "Job Board",
            "Online Job Board",
            "Company Website",
            "Recruiter",
        ]
        ordered: list[str] = []
        # Prefer tenant-generic choices first; keep profile-specific values as secondary hints.
        for value in [*generic_first, *values, primary, "LinkedIn"]:
            if not value:
                continue
            normalized = normalize_text(value)
            if normalized and all(normalize_text(existing) != normalized for existing in ordered):
                ordered.append(value)
        return ordered

    def _state_option_candidates(self, raw_state: str) -> list[str]:
        value = str(raw_state or "").strip()
        if not value:
            return []
        normalized = normalize_text(value)
        ordered: list[str] = []

        def add(candidate: str) -> None:
            text = str(candidate or "").strip()
            if not text:
                return
            norm = normalize_text(text)
            if norm and all(normalize_text(existing) != norm for existing in ordered):
                ordered.append(text)

        add(value)
        if len(value) == 2:
            upper = value.upper()
            full = US_STATE_BY_ABBR.get(upper)
            if full:
                add(full)
        else:
            for abbr, full in US_STATE_BY_ABBR.items():
                if normalize_text(full) == normalized:
                    add(abbr)
                    break
        for fallback in ("Illinois", "California", "Texas", "New York"):
            add(fallback)
        return ordered

    def _eeo_options(self, *values: Any) -> list[str]:
        out: list[str] = []
        for value in values:
            if isinstance(value, bool) or value is None:
                continue
            text = str(value or "").strip()
            if not text or text.lower() == "decline":
                continue
            if text not in out:
                out.append(text)
        return out

    def _hispanic_options(self, eeo: dict[str, Any]) -> list[str]:
        hispanic = eeo.get("hispanic_latino")
        if hispanic is False or hispanic is None or str(hispanic).lower() == "decline":
            base = "No"
        else:
            base = str(hispanic)
        return self._eeo_options(
            base,
            "No, I am not Hispanic or Latino",
            "No",
        )

    def _eeo_payload(self) -> dict[str, Any]:
        eeo = (
            self.profile.get("eeo_information", {})
            if isinstance(self.profile.get("eeo_information"), dict)
            else {}
        )
        return {
            "disabilityOptions": self._eeo_options(
                str(eeo.get("disability_status") or ""),
                "No, I do not have a disability",
                "No",
                "I do not want to answer",
            ),
            "disabilityQuestionKeywords": [
                "disability",
                "disabilities",
                "cc-305",
                "section 503",
                "self identify",
                "voluntary disability",
            ],
            "veteranOptions": self._eeo_options(
                str(eeo.get("veteran_status") or ""),
                "Not a veteran",
                "I am not a protected veteran",
                "No, I am not a veteran",
                "No",
            ),
            "veteranQuestionKeywords": [
                "veteran",
                "military service",
                "armed forces",
                "select your status",
            ],
            "raceOptions": self._eeo_options(
                eeo.get("race_ethnicity") or "",
                "Asian or Pacific Islander",
            ),
            "hispanicOptions": self._hispanic_options(eeo),
            "raceQuestionKeywords": ["ethnicity", "race", "hispanic", "latino", "origin"],
        }

    def _required_field_payload(self) -> dict[str, Any]:
        state_value = str(self.address.get("state") or "")
        auth_yes = bool(self.standard_answers.get("authorized_to_work_us", True))
        sponsor_yes = bool(
            self.standard_answers.get(
                "requires_sponsorship",
                self.standard_answers.get("will_require_sponsorship_future", True),
            )
        )
        authorized_options = ["Yes", "True", "Authorized"] if auth_yes else ["No", "False", "Not Authorized"]
        sponsorship_options = (
            ["Yes", "True", "Require Sponsorship", "Will Require Sponsorship"]
            if sponsor_yes
            else ["No", "False", "No Sponsorship", "Will Not Require Sponsorship"]
        )
        return {
            "questionKeywords": ["previously worked for", "worked for", "previously employed by"],
            "noOptions": ["No", "Nope", "Never"],
            "phone": str(self.identity.get("phone") or ""),
            "addressLine1": str(self.address.get("street") or ""),
            "city": str(self.address.get("city") or ""),
            "state": state_value,
            "stateOptions": self._state_option_candidates(state_value),
            "postalCode": str(self.address.get("zip") or ""),
            "country": str(self.address.get("country") or "United States"),
            "firstName": str(self.identity.get("first_name") or ""),
            "lastName": str(self.identity.get("last_name") or ""),
            "fullName": str(self.identity.get("full_name") or ""),
            "email": str(self.identity.get("email") or self.creds.email or ""),
            "referralOptions": self._referral_candidates(),
            "deviceTypeOptions": ["Mobile", "Cell", "Home", "Work", "Personal"],
            "countryPhoneCodeOptions": ["United States of America (+1)", "United States (+1)", "+1", "1"],
            "authorizedToWorkOptions": authorized_options,
            "sponsorshipOptions": sponsorship_options,
            **self._eeo_payload(),
        }

    def _record(self, message: str) -> None:
        self.steps.append(f"{datetime.utcnow().isoformat()} {message}")
        self.trace("workday_step", step=message, total_steps=self.total_steps)

    @staticmethod
    def _as_dict(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except Exception:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    async def _get_page(self) -> Any:
        return await self.browser_session.get_current_page()

    async def _element_state(self, element: Any) -> dict[str, Any]:
        try:
            raw = await element.evaluate(
                """(el) => {
                  const style = window.getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  const visible = !!el && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                  const disabled = !!(el.disabled || el.getAttribute('aria-disabled') === 'true');
                  return JSON.stringify({ visible, disabled });
                }"""
            )
            return self._as_dict(raw)
        except Exception:
            return {}

    async def _element_text(self, element: Any) -> str:
        try:
            text = await element.get_attribute("textContent")
            if text:
                return " ".join(str(text).split())
        except Exception:
            pass
        try:
            raw = await element.evaluate(
                """(el) => (el.textContent || el.innerText || el.value || el.getAttribute('aria-label') || '').trim()"""
            )
            return " ".join(str(raw or "").split())
        except Exception:
            return ""

    async def _element_descriptor(self, element: Any) -> str:
        try:
            raw = await element.evaluate(
                """(el) => {
                  const safe = (v) => (v || '').toString();
                  const label = (el.labels && el.labels[0] && el.labels[0].textContent) || '';
                  const parent = (el.parentElement && el.parentElement.textContent) || '';
                  return [
                    safe(el.getAttribute && el.getAttribute('name')),
                    safe(el.getAttribute && el.getAttribute('id')),
                    safe(el.getAttribute && el.getAttribute('aria-label')),
                    safe(el.getAttribute && el.getAttribute('placeholder')),
                    safe(label),
                    safe(parent).slice(0, 240),
                  ].join(' ');
                }"""
            )
            return " ".join(str(raw or "").split())
        except Exception:
            return ""

    async def _candidate_elements(
        self,
        selectors: list[str],
        *,
        require_interactable: bool = True,
        limit_per_selector: int = 6,
        descriptor_hints: list[str] | None = None,
    ) -> list[tuple[Any, str, int]]:
        page = await self._get_page()
        if page is None:
            return []
        candidates: list[tuple[Any, str, int]] = []
        normalized_hints = [normalize_text(h) for h in (descriptor_hints or []) if str(h or "").strip()]
        for selector in selectors:
            try:
                elements = await page.get_elements_by_css_selector(selector)
            except Exception:
                continue
            for idx, element in enumerate(elements[: max(1, limit_per_selector)]):
                if not require_interactable:
                    if normalized_hints:
                        desc = normalize_text(await self._element_descriptor(element))
                        if desc and not any(hint in desc for hint in normalized_hints):
                            continue
                    candidates.append((element, selector, idx))
                    continue
                meta = await self._element_state(element)
                visible = bool(meta.get("visible", True))
                disabled = bool(meta.get("disabled", False))
                if visible and not disabled:
                    if normalized_hints:
                        desc = normalize_text(await self._element_descriptor(element))
                        if desc and not any(hint in desc for hint in normalized_hints):
                            continue
                    candidates.append((element, selector, idx))
        return candidates

    async def _has_field(self, selectors: list[str], descriptor_hints: list[str] | None = None) -> bool:
        candidates = await self._candidate_elements(
            selectors,
            require_interactable=False,
            limit_per_selector=1,
            descriptor_hints=descriptor_hints,
        )
        return bool(candidates)

    async def el_fill(self, selectors: list[str], value: str) -> tuple[bool, str]:
        value = str(value or "").strip()
        if not value:
            return False, "empty-value"
        candidates = await self._candidate_elements(selectors, require_interactable=True, limit_per_selector=4)
        if not candidates:
            return False, f"not-found:{selectors[0] if selectors else 'n/a'}"
        for element, selector, idx in candidates:
            try:
                await element.fill(value)
                check = ""
                try:
                    check = str(await element.get_attribute("value") or "").strip()
                except Exception:
                    check = ""
                if check and normalize_text(value[:6]) not in normalize_text(check) and normalize_text(check[:6]) not in normalize_text(value):
                    # For React inputs value can still be correct even when attribute read is stale.
                    pass
                return True, f"filled:{selector}[{idx}]"
            except Exception:
                continue
        return False, f"fill-failed:{selectors[0] if selectors else 'n/a'}"

    async def el_click(
        self,
        selectors: list[str],
        *,
        state_key: str,
        text_hints: list[str] | None = None,
    ) -> tuple[bool, str]:
        candidates = await self._candidate_elements(selectors, require_interactable=True, limit_per_selector=8)
        click_budget_checked = False
        for element, selector, idx in candidates:
            try:
                if not click_budget_checked:
                    if not self._guard_clicks(state_key):
                        return False, f"click cap reached for state={state_key}"
                    click_budget_checked = True
                await element.click()
                return True, f"clicked:{selector}[{idx}]"
            except Exception:
                continue
        if text_hints:
            page = await self._get_page()
            if page is not None:
                fallback_selectors = [
                    "button",
                    "[role='button']",
                    "div[role='button']",
                    "input[type='submit']",
                    "input[type='button']",
                ]
                text_candidates = await self._candidate_elements(
                    fallback_selectors, require_interactable=True, limit_per_selector=30
                )
                normalized_hints = [normalize_text(h) for h in text_hints if str(h or "").strip()]
                for element, selector, idx in text_candidates:
                    txt = normalize_text(await self._element_text(element))
                    if not txt or not any(h in txt for h in normalized_hints):
                        continue
                    try:
                        if not click_budget_checked:
                            if not self._guard_clicks(state_key):
                                return False, f"click cap reached for state={state_key}"
                            click_budget_checked = True
                        await element.click()
                        return True, f"clicked:text:{txt[:80]}:{selector}[{idx}]"
                    except Exception:
                        continue
        return False, f"click-failed:{selectors[0] if selectors else 'n/a'}"

    async def el_check(self, selectors: list[str]) -> tuple[bool, str]:
        candidates = await self._candidate_elements(selectors, require_interactable=True, limit_per_selector=8)
        if not candidates:
            return False, f"not-found:{selectors[0] if selectors else 'n/a'}"
        for element, selector, idx in candidates:
            try:
                await element.check()
                return True, f"checked:{selector}[{idx}]"
            except Exception:
                try:
                    await element.click()
                    return True, f"clicked-checkbox:{selector}[{idx}]"
                except Exception:
                    continue
        return False, f"check-failed:{selectors[0] if selectors else 'n/a'}"

    async def el_select_combobox(
        self,
        trigger_selectors: list[str],
        option_texts: list[str],
        *,
        state_key: str,
        field_hints: list[str] | None = None,
    ) -> tuple[bool, str]:
        triggers = await self._candidate_elements(
            trigger_selectors,
            require_interactable=True,
            limit_per_selector=8,
            descriptor_hints=field_hints,
        )
        if not triggers and field_hints:
            return False, f"trigger-not-found:{trigger_selectors[0] if trigger_selectors else 'n/a'}:hints"
        if not triggers:
            return False, f"trigger-not-found:{trigger_selectors[0] if trigger_selectors else 'n/a'}"
        normalized_targets = [normalize_text(v) for v in option_texts if str(v or " ").strip()]
        page = await self._get_page()
        if page is None:
            return False, "no-active-page"
        best_any: tuple[Any, str, int, str] | None = None
        for trigger, selector, idx in triggers:
            before_text = normalize_text(await self._element_text(trigger))
            try:
                await trigger.click()
            except Exception:
                continue
            await asyncio.sleep(0.6)
            option_candidates = await self._candidate_elements(
                [
                    "[role='option']",
                    "li[role='option']",
                    "div[role='option']",
                    "[data-automation-id*='menuItem']",
                ],
                require_interactable=True,
                limit_per_selector=120,
            )
            # Two-pass: collect ALL valid (non-placeholder) options with their text,
            # then resolve against the candidate list IN PRIORITY ORDER (user's state
            # first, fallbacks last).  This prevents the alphabetically-first option
            # (e.g. "California") from beating the real target (e.g. "Illinois") even
            # though both exact-match some candidate and California sorts first in the DOM.
            valid_options: list[tuple[Any, str]] = []
            for option_element, option_selector, option_idx in option_candidates:
                txt = normalize_text(await self._element_text(option_element))
                if not txt:
                    continue
                if txt in WD_OPTION_PLACEHOLDERS:
                    continue
                if len(txt) > 80:
                    continue
                if best_any is None:
                    best_any = (option_element, option_selector, option_idx, txt)
                valid_options.append((option_element, txt))

            def find_option(target: str) -> Any | None:
                # exact first, then substring, in DOM order among valid options.
                for opt, txt in valid_options:
                    if txt == target:
                        return opt
                for opt, txt in valid_options:
                    if target in txt or txt in target:
                        return opt
                return None

            chosen = None
            chosen_txt = ""
            for target in normalized_targets:  # candidate priority order
                hit = find_option(target)
                if hit is not None:
                    chosen = hit
                    chosen_txt = next((t for o, t in valid_options if o is hit), target)
                    break
            if chosen is not None:
                try:
                    await chosen.click()
                    await asyncio.sleep(0.2)
                    after_text = normalize_text(await self._element_text(trigger))
                    if after_text and after_text not in WD_OPTION_PLACEHOLDERS and after_text != before_text:
                        return True, f"selected:{after_text}:{selector}[{idx}]"
                    if after_text and any(target in after_text for target in normalized_targets):
                        return True, f"selected:{after_text}:{selector}[{idx}]"
                    if chosen_txt:
                        return True, f"selected:{chosen_txt}:{selector}[{idx}]"
                except Exception:
                    pass
            # Fallback: any non-placeholder option (user preference: pick valid, continue).
            if best_any is not None:
                option_element, option_selector, option_idx, txt = best_any
                try:
                    await option_element.click()
                    await asyncio.sleep(0.2)
                    after_text = normalize_text(await self._element_text(trigger))
                    if after_text and after_text not in WD_OPTION_PLACEHOLDERS and after_text != before_text:
                        return True, f"selected-any:{after_text}:{option_selector}[{option_idx}]"
                except Exception:
                    pass
        return False, "option-not-found"

    async def _post_auth_error(self) -> str:
        candidates = await self._candidate_elements(WD_SEL["error_message"], require_interactable=False, limit_per_selector=10)
        for element, _, _ in candidates:
            txt = normalize_text(await self._element_text(element))
            if txt:
                return txt[:220]
        return ""

    def _handoff(self, state: str, message: str, snap: dict[str, Any] | None = None) -> str:
        data = snap or {}
        return (
            f"platform=workday;state={state};message={message};url={data.get('url')};"
            f"required_empty={data.get('required_empty')};create_attempts={self.auth_create_attempts};"
            f"signin_attempts={self.auth_signin_attempts};same_state_repeat={self.same_state_repeat};"
            f"deterministic_steps={len(self.steps)}"
        )

    def _outcome(self, result: HandlerResult, state: str, message: str, snap: dict[str, Any] | None = None, blocker: str = "") -> HandlerOutcome:
        return HandlerOutcome(
            result=result,
            state=state,
            message=message,
            steps=list(self.steps),
            blocker_code=blocker,
            handoff_context=self._handoff(state, message, snap),
        )

    async def _snapshot(self) -> dict[str, Any]:
        page = await self.browser_session.get_current_page()
        if page is None:
            return {}
        raw = await page.evaluate(
            """
            () => {
              const n=(s)=>(s||'').toLowerCase().replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const text=(el)=>n(el.textContent||el.value||el.getAttribute('aria-label')||'');
              const body=n((document.body&&document.body.innerText)||'').slice(0,24000);
              const btns=Array.from(document.querySelectorAll('button,a,[role="button"],[role="link"],input[type="submit"],input[type="button"]')).filter(v).map(text).filter(Boolean);
              const fields=Array.from(document.querySelectorAll('input,select,textarea')).filter(v);
              const passwords=fields.filter((el)=>n(el.getAttribute('type')||'')==='password');
              const headings=Array.from(document.querySelectorAll('h1,h2,h3,h4,[data-automation-id],legend,[role="heading"]')).filter(v).slice(0,60).map(text);
              const marker=n([document.title||'',...headings,body.slice(0,2200)].join(' '));
              const hasButton=(arr)=>btns.some((t)=>arr.some((w)=>t.includes(w)));
              const hasVisible=(sel)=>{try{return Array.from(document.querySelectorAll(sel)).some(v);}catch(e){return false;}};
              const requiredEmpty=fields.filter((el)=>{const req=el.required||n(el.getAttribute('aria-required')||'')==='true';if(!req)return false;const type=n(el.getAttribute('type')||'');if(type==='checkbox'||type==='radio'){const aria=n(el.getAttribute('aria-checked')||'');const checked=aria==='true'?true:aria==='false'?false:!!el.checked;return !checked;} if((el.tagName||'').toLowerCase()==='select'){const so=el.selectedOptions&&el.selectedOptions.length?el.selectedOptions[0]:null;const val=n((so&&so.textContent)||el.value||'');return !val||val==='select one'||val==='choose one'||val==='please select';} return !n(el.value||'');}).length;
              return {
                url: location.href||'',
                host: location.hostname||'',
                marker,
                body_text: body,
                headings: headings.slice(0,30),
                required_empty: requiredEmpty,
                has_apply: hasButton(['apply now','apply','start application','begin application']),
                has_entry_panel: hasButton(['apply manually','autofill with resume']),
                has_create: hasButton(['create account','create an account','register','sign up','new user']),
                has_signin: hasButton(['sign in','log in','login']),
                has_continue: hasButton(['save and continue','continue','next','review']),
                has_submit: hasButton(['submit application','submit','finish','complete application']),
                has_email: fields.some((el)=>n([el.getAttribute('type')||'',el.getAttribute('name')||'',el.getAttribute('id')||'',el.getAttribute('aria-label')||'',el.getAttribute('placeholder')||'',(el.labels&&el.labels[0]&&el.labels[0].textContent)||''].join(' ')).includes('email')),
                has_terms: btns.some((t)=>t.includes('read and accept')||t.includes('terms')||t.includes('privacy policy')),
                has_checkbox: Array.from(document.querySelectorAll('input[type="checkbox"],[role="checkbox"],[aria-checked]')).filter(v).length>0,
                password_count: passwords.length,
                captcha: marker.includes('verify you are human')||marker.includes('captcha')||marker.includes('just a moment')||marker.includes('security verification')||!!document.querySelector('iframe[src*="captcha"],iframe[src*="challenge"]'),
                already_applied: marker.includes('already applied')||marker.includes('already submitted an application')||marker.includes('application already received'),
                job_closed: marker.includes('job is no longer available')||marker.includes('job posting is no longer available')||marker.includes('position has been filled')||marker.includes('job requisition closed'),
                invalid_auth: marker.includes('invalid')&&(marker.includes('password')||marker.includes('email')||marker.includes('login')),
                has_automation_contact: hasVisible("div[data-automation-id='contactInformationPage'],div[data-automation-id*='contactInformationPage']"),
                has_automation_experience: hasVisible("div[data-automation-id='myExperiencePage'],div[data-automation-id*='myExperiencePage']"),
                has_automation_disclosures: hasVisible("div[data-automation-id='voluntaryDisclosuresPage'],div[data-automation-id*='voluntaryDisclosuresPage']"),
                has_automation_selfid: hasVisible("div[data-automation-id='selfIdentificationPage'],div[data-automation-id*='selfIdentificationPage']"),
                has_automation_review: hasVisible("div[data-automation-id='reviewMyApplicationPage'],div[data-automation-id*='reviewMyApplicationPage']"),
                has_automation_already_applied: hasVisible("div[data-automation-id='alreadyApplied'],div[data-automation-id*='alreadyApplied']"),
                has_confirmation_container: hasVisible("[data-automation-id='applicationConfirmation'],[data-automation-id*='applicationConfirmation'],[data-automation-id='submittedApplication'],[data-automation-id*='submittedApplication'],[data-automation-id='thankYouMessage'],[data-automation-id*='thankYouMessage']"),
                has_previous_employment_question: marker.includes('previously worked for')||marker.includes('previous worker information')||marker.includes('previously employed'),
                has_work_auth_question: marker.includes('authorized to work')||marker.includes('work authorization')||marker.includes('work in the job'),
                has_sponsorship_question: marker.includes('visa sponsorship')||marker.includes('require sponsorship')||marker.includes('sponsorship to work'),
              };
            }
            """
        )
        return self._as_dict(raw)

    def _state(self, snap: dict[str, Any]) -> str:
        marker = normalize_text(snap.get("marker") or "")
        url_value = normalize_text(snap.get("url") or "")
        required_empty = int(snap.get("required_empty") or 0)
        has_email = bool(snap.get("has_email"))
        password_count = int(snap.get("password_count") or 0)
        has_create = bool(snap.get("has_create"))
        has_signin = bool(snap.get("has_signin"))
        create_marker = any(token in marker for token in ("create account", "create an account", "register", "sign up"))
        signin_marker = any(token in marker for token in ("sign in", "log in", "login"))
        login_url = "/login" in url_value or "/signin" in url_value or "/sign-in" in url_value
        apply_url = "/apply" in url_value
        has_automation_state = any(
            bool(snap.get(key))
            for key in (
                "has_automation_contact",
                "has_automation_experience",
                "has_automation_disclosures",
                "has_automation_selfid",
                "has_automation_review",
            )
        )
        on_apply_flow = (
            apply_url
            or "/apply/" in marker
            or has_automation_state
            or password_count > 0
            or bool(snap.get("has_submit"))
            or login_url
        )
        auth_screen = (
            password_count > 0
            or login_url
            or (
                has_email
                and (
                    create_marker
                    or signin_marker
                    or has_create
                    or has_signin
                )
            )
        )
        if snap.get("has_confirmation_container"):
            return "SUBMITTED"
        if snap.get("has_automation_already_applied"):
            return "ALREADY_APPLIED"
        if bool(snap.get("has_apply")) and not on_apply_flow:
            return "APPLY_ENTRY"
        if any(k in marker for k in ("application submitted", "application received", "thank you for applying")):
            return "SUBMITTED"
        if auth_screen:
            if password_count >= 2 and has_email:
                return "CREATE_ACCOUNT"
            if password_count == 1 and has_email:
                return "SIGN_IN"
            if any(
                token in marker
                for token in (
                    "already have an account",
                    "already exists",
                    "account exists",
                    "existing account",
                    "sign in to continue",
                )
            ) and has_signin:
                return "SIGN_IN"
            if signin_marker and has_email:
                return "SIGN_IN"
            if create_marker and has_email:
                return "CREATE_ACCOUNT"
            if (bool(snap.get("has_terms")) or bool(snap.get("has_checkbox"))) and has_email and (create_marker or signin_marker):
                return "LEGAL_ACCEPT"
            if has_email and has_signin and not has_create:
                return "SIGN_IN"
            if has_email and has_create and not has_signin:
                return "CREATE_ACCOUNT"
            if has_email:
                return "AUTH"
        if snap.get("has_automation_contact"):
            return "CONTACT"
        if snap.get("has_automation_experience"):
            return "EXPERIENCE"
        if snap.get("has_automation_disclosures"):
            return "DISCLOSURES"
        if snap.get("has_automation_selfid"):
            return "SELF_ID"
        if snap.get("has_automation_review"):
            return "REVIEW_SUBMIT"
        if on_apply_flow and "current step 6 of" in marker:
            return "REVIEW_SUBMIT"
        if on_apply_flow and "current step 5 of" in marker:
            return "SELF_ID"
        if on_apply_flow and "current step 4 of" in marker:
            return "DISCLOSURES"
        if on_apply_flow and "current step 3 of" in marker:
            return "DISCLOSURES"
        if on_apply_flow and "current step 2 of" in marker:
            return "EXPERIENCE"
        if on_apply_flow and "current step 1 of" in marker:
            return "CONTACT"
        if on_apply_flow and (
            bool(snap.get("has_previous_employment_question"))
            or bool(snap.get("has_work_auth_question"))
            or bool(snap.get("has_sponsorship_question"))
        ):
            return "DISCLOSURES"
        if on_apply_flow and any(k in marker for k in ("my information", "contact information", "personal information")):
            return "CONTACT"
        if on_apply_flow and any(k in marker for k in ("my experience", "work experience", "experience")):
            return "EXPERIENCE"
        if on_apply_flow and any(k in marker for k in ("application questions", "voluntary disclosures", "disclosures")):
            return "DISCLOSURES"
        if on_apply_flow and any(k in marker for k in ("self identify", "self-identify", "self identification")):
            return "SELF_ID"
        if on_apply_flow and "review" in marker and bool(snap.get("has_submit")):
            return "REVIEW_SUBMIT"
        if on_apply_flow and "review" in marker and "/review" in url_value:
            return "REVIEW_SUBMIT"
        if on_apply_flow and bool(snap.get("has_submit")) and required_empty == 0:
            return "REVIEW_SUBMIT"
        if on_apply_flow and bool(snap.get("has_continue")) and not has_signin and not has_create and not login_url:
            return "CONTACT"
        if bool(snap.get("has_apply")):
            return "APPLY_ENTRY"
        if apply_url or "/apply/" in marker:
            return "DETECT"
        return "DETECT"

    def _blocked(self, snap: dict[str, Any], state: str) -> HandlerOutcome | None:
        if snap.get("captcha"):
            return self._outcome(HandlerResult.BLOCKED, state, "CAPTCHA/human verification detected.", snap, "captcha")
        if state == "ALREADY_APPLIED" or snap.get("already_applied") or snap.get("has_automation_already_applied"):
            return self._outcome(HandlerResult.BLOCKED, state, "This job appears already applied.", snap, "already_applied")
        if snap.get("job_closed"):
            return self._outcome(HandlerResult.BLOCKED, state, "This job appears closed/unavailable.", snap, "job_closed")
        job_host = urlparse(self.job_url).hostname or ""
        cur_host = str(snap.get("host") or "")
        if job_host and cur_host and cur_host != job_host and not cur_host.endswith("." + job_host) and not job_host.endswith("." + cur_host):
            if "myworkdayjobs.com" not in cur_host:
                return self._outcome(HandlerResult.BLOCKED, state, f"External SSO redirect: {cur_host}", snap, "external_sso")
        if snap.get("invalid_auth") and self.auth_signin_attempts >= 2:
            return self._outcome(HandlerResult.BLOCKED, state, "Persistent auth failure after retries.", snap, "auth_failure")
        return None

    def _guard_state(self, state: str) -> bool:
        if state == self.last_state:
            self.same_state_repeat += 1
        else:
            self.last_state = state
            self.same_state_repeat = 1
        limits = {
            "DETECT": 24,
            "APPLY_ENTRY": 8,
            "CREATE_ACCOUNT": 8,
            "SIGN_IN": 8,
            "LEGAL_ACCEPT": 6,
            "CONTACT": 10,
            "EXPERIENCE": 8,
            "DISCLOSURES": 8,
            "SELF_ID": 8,
            "REVIEW_SUBMIT": 6,
        }
        limit = limits.get(state, 6)
        return self.same_state_repeat <= limit

    def _guard_clicks(self, state: str) -> bool:
        count = self.next_click_per_state.get(state, 0)
        limits = {
            "APPLY_ENTRY": 8,
            "CREATE_ACCOUNT": 8,
            "SIGN_IN": 6,
            "LEGAL_ACCEPT": 5,
            "CONTACT": 6,
            "EXPERIENCE": 6,
            "DISCLOSURES": 6,
            "SELF_ID": 6,
            "REVIEW_SUBMIT": 4,
            "DETECT": 5,
        }
        limit = limits.get(state, 4)
        if count >= limit:
            return False
        self.next_click_per_state[state] = count + 1
        return True

    async def run(self) -> HandlerOutcome:
        progress = False
        no_action_after_progress = 0
        while self.total_steps < 80:
            snap = await self._snapshot()
            if not snap:
                return self._outcome(HandlerResult.FAILED, "DETECT", "Workday snapshot unavailable.")
            state = self._state(snap)
            self.trace(
                "workday_state",
                state=state,
                url=str(snap.get("url") or "")[:220],
                required_empty=int(snap.get("required_empty") or 0),
                has_apply=bool(snap.get("has_apply")),
                has_create=bool(snap.get("has_create")),
                has_signin=bool(snap.get("has_signin")),
                has_continue=bool(snap.get("has_continue")),
                has_submit=bool(snap.get("has_submit")),
                has_email=bool(snap.get("has_email")),
                password_count=int(snap.get("password_count") or 0),
            )
            blocked = self._blocked(snap, state)
            if blocked:
                return blocked
            if state == "SUBMITTED":
                return self._outcome(HandlerResult.SUBMITTED, state, "Submission confirmation detected.", snap)
            if not self._guard_state(state):
                if progress:
                    return self._outcome(
                        HandlerResult.PROGRESSED,
                        state,
                        "State cycle guard triggered after deterministic progress; handoff to LLM.",
                        snap,
                    )
                return self._outcome(HandlerResult.BLOCKED, state, "State cycle guard triggered.", snap, "state_cycle")

            acted, note = await self._action(state, snap)
            if acted:
                if note != DETECT_WAIT_NOTE:
                    progress = True
                no_action_after_progress = 0
                self._record(note)
                self.total_steps += 1
                continue
            if progress and no_action_after_progress < 4:
                no_action_after_progress += 1
                self._record(f"post-progress-wait:{state}:{note}")
                self.total_steps += 1
                await asyncio.sleep(1.0)
                continue
            if progress:
                return self._outcome(HandlerResult.PROGRESSED, state, note or "Deterministic handoff to LLM.", snap)
            return self._outcome(HandlerResult.NEEDS_LLM, state, note or "No deterministic action matched.", snap)
        return self._outcome(HandlerResult.BLOCKED, self.last_state or "DETECT", "Deterministic step limit exceeded.", None, "step_limit")

    async def recover(self, loop_context: dict[str, Any]) -> HandlerOutcome:
        snap = await self._snapshot()
        state = self._state(snap)
        blocked = self._blocked(snap, state)
        if blocked:
            return blocked
        url = normalize_text(snap.get("url") or "")
        body = normalize_text(snap.get("body_text") or "")
        if "/careers/userhome" in url or ("search for jobs" in body and "/job/" not in url):
            page = await self.browser_session.get_current_page()
            ok, reason = await safe_navigate(page, self.job_url)
            if ok:
                note = "Recovery navigated back to original job URL."
                self._record(note)
                return self._outcome(HandlerResult.PROGRESSED, state, note, snap)
            return self._outcome(HandlerResult.FAILED, state, f"Recovery navigation failed: {reason}", snap)
        if state in FORM_STATES and self.referral_fix_attempts < 2:
            self.referral_fix_attempts += 1
            fixed, note = await self.js_fix_referral_source()
            if fixed:
                self._record(f"recover:{note}")
                return self._outcome(HandlerResult.PROGRESSED, state, note, snap)
        if state in FORM_STATES and int(snap.get("required_empty") or 0) > 0:
            filled, fill_note = await self.js_autofill_required_fields()
            if filled:
                after = await self._snapshot()
                before_required = int(snap.get("required_empty") or 0)
                after_required = int(after.get("required_empty") or 0)
                if after_required < before_required:
                    note = f"{fill_note};required:{before_required}->{after_required}"
                    self._record(f"recover:{note}")
                    return self._outcome(HandlerResult.PROGRESSED, state, note, after or snap)
                return self._outcome(
                    HandlerResult.NEEDS_LLM,
                    state,
                    f"{fill_note};required unchanged={after_required}",
                    after or snap,
                )
        if context_matches(snap.get("body_text") or "", WORKDAY_EXISTING_DATA_CONFLICT_KEYWORDS):
            if self.conflict_fix_attempts < 4:
                resolved, note = await self.js_resolve_existing_data_conflicts()
                if resolved:
                    self.conflict_fix_attempts += 1
                    self._record(f"recover:{note}")
                    return self._outcome(HandlerResult.PROGRESSED, state, note, snap)
        acted, note = await self._action(state, snap)
        if acted:
            self._record(f"recover:{note}")
            return self._outcome(HandlerResult.PROGRESSED, state, note, snap)
        return self._outcome(HandlerResult.NEEDS_LLM, state, f"{note} context={str(loop_context)[:220]}", snap)

    async def _action(self, state: str, snap: dict[str, Any]) -> tuple[bool, str]:
        if state == "DETECT":
            return await self._action_detect()
        if state == "APPLY_ENTRY":
            return await self._action_apply_entry()
        if state in AUTH_STATES:
            return await self._auth_action(state, snap)
        if state in FORM_STATES:
            url_value = normalize_text(snap.get("url") or "")
            if (
                "/apply/" not in url_value
                and int(snap.get("password_count") or 0) == 0
                and not bool(snap.get("has_continue"))
                and not bool(snap.get("has_submit"))
                and int(snap.get("required_empty") or 0) == 0
            ):
                return False, "form-state-without-apply-context"
            if state == "REVIEW_SUBMIT":
                if self.dry_run:
                    return (
                        False,
                        "dry_run:reached review/submit screen; STOPPED before clicking Submit (no application submitted)",
                    )
                clicked, note = await self.el_click(
                    WD_SEL["submit_button"],
                    state_key=state,
                    text_hints=["submit application", "submit", "finish", "complete application"],
                )
                if clicked:
                    return True, f"review-submit:{note}"
                return await self.js_click_verified(
                    WD_SEL["submit_button"],
                    ["submit application", "submit", "finish", "complete application"],
                    state,
                )
            contact_note_parts: list[str] = []
            form_context = " ".join(
                [
                    str(snap.get("marker") or ""),
                    str(snap.get("body_text") or ""),
                    " ".join(str(x) for x in (snap.get("headings") or []) if str(x).strip()),
                ]
            )
            if state == "CONTACT":
                contact_filled, contact_note = await self._fill_contact_info()
                if contact_filled:
                    contact_note_parts.append(contact_note)
            if self.referral_fix_attempts < 2:
                self.referral_fix_attempts += 1
                fixed, note = await self.js_fix_referral_source()
                if fixed:
                    contact_note_parts.append(note)
            required_before = int(snap.get("required_empty") or 0)
            has_keyword_blocker = context_matches(form_context, WORKDAY_REQUIRED_FIELD_LOOP_KEYWORDS) or context_matches(
                form_context, WORKDAY_EXPERIENCE_FIELD_LOOP_KEYWORDS
            )
            has_question_blocker = bool(
                snap.get("has_previous_employment_question")
                or snap.get("has_work_auth_question")
                or snap.get("has_sponsorship_question")
            )
            state_attempts = self.state_autofill_attempts.get(state, 0)
            proactive_state_fill = state in {"DISCLOSURES", "SELF_ID", "EXPERIENCE"} and state_attempts < 2
            should_autofill = required_before > 0 or has_keyword_blocker or has_question_blocker or proactive_state_fill
            if should_autofill and self.required_loop_fix_attempts < 14:
                self.required_loop_fix_attempts += 1
                self.state_autofill_attempts[state] = state_attempts + 1
                before_required = int(snap.get("required_empty") or 0)
                filled, fill_note = await self.js_autofill_required_fields()
                if filled:
                    after = await self._snapshot()
                    after_required = int(after.get("required_empty") or 0)
                    if after_required < before_required:
                        contact_note_parts.append(f"{fill_note};required:{before_required}->{after_required}")
                    elif after_required == before_required:
                        suffix = f"{fill_note};required unchanged={after_required}"
                        if has_keyword_blocker and before_required == 0:
                            suffix += ";keyword-fix"
                        contact_note_parts.append(suffix)
                elif not contact_note_parts:
                    if required_before > 0:
                        return False, fill_note
                    if has_keyword_blocker or has_question_blocker:
                        contact_note_parts.append(f"keyword-fix:{fill_note}")
            if context_matches(snap.get("body_text") or "", WORKDAY_EXISTING_DATA_CONFLICT_KEYWORDS):
                if self.conflict_fix_attempts < 4:
                    resolved, note = await self.js_resolve_existing_data_conflicts()
                    if resolved:
                        self.conflict_fix_attempts += 1
                        contact_note_parts.append(note)
            if int(snap.get("required_empty") or 0) > 0 and not contact_note_parts:
                return False, f"{snap.get('required_empty')} required fields still empty."
            clicked, note = await self.el_click(
                WD_SEL["next_button"],
                state_key=state,
                text_hints=["save and continue", "continue", "next"],
            )
            if clicked:
                joined = ";".join([*contact_note_parts, note]) if contact_note_parts else note
                return True, joined
            clicked, js_note = await self.js_click_verified(
                WD_SEL["next_button"],
                ["save and continue", "continue", "next"],
                state,
            )
            if clicked:
                joined = ";".join([*contact_note_parts, js_note]) if contact_note_parts else js_note
                return True, joined
            if contact_note_parts:
                return True, ";".join(contact_note_parts)
            return False, js_note
        return False, f"No deterministic action for state={state}."

    async def _apply_href(self) -> str:
        """Resolve the Workday Apply href.

        Workday's Apply control is a JS-intercepted link (data-automation-id
        'adventureButton') whose programmatic click does not navigate. The
        href it points at is the deterministic `{job}/apply` entry URL, and
        navigating there directly is proven to work.
        """
        try:
            page = await self.browser_session.get_current_page()
            href = await page.evaluate(
                "() => { const el = document.querySelector(\"a[href*='/apply'],[data-automation-id='adventureButton']\"); return el ? (el.getAttribute('href') || '') : ''; }"
            )
            if href and str(href).startswith("http"):
                return str(href)
        except Exception:
            pass
        base = (self.job_url or "").split("?")[0].rstrip("/")
        return f"{base}/apply" if base else ""

    async def _action_apply_entry(self) -> tuple[bool, str]:
        clicked, note = await self.el_click(
            WD_SEL["apply_button"],
            state_key="APPLY_ENTRY",
            text_hints=["apply now", "apply manually", "autofill with resume", "start application", "begin application", "apply"],
        )
        if clicked:
            await asyncio.sleep(1.5)
            snap = await self._snapshot()
            if snap and self._state(snap) == "APPLY_ENTRY":
                # Click did not advance: Workday intercepts the Apply click.
                # Navigate directly to the /apply entry URL (deterministic).
                href = await self._apply_href()
                job_base = (self.job_url or "").split("?")[0].rstrip("/")
                if href and href.rstrip("/") != job_base and href not in str(snap.get("url") or ""):
                    page = await self.browser_session.get_current_page()
                    ok, reason = await safe_navigate(page, href)
                    if ok:
                        self._record(f"apply_entry:navigated:{href}")
                        return True, f"apply_entry:navigated:{href}"
                    return False, f"apply_entry:click-noop,navigate-failed:{reason}"
            return True, note
        return await self.js_click_verified(
            WD_SEL["apply_button"],
            ["apply now", "apply manually", "autofill with resume", "start application", "begin application", "apply"],
            "APPLY_ENTRY",
        )

    async def _action_detect(self) -> tuple[bool, str]:
        cookies_dismissed, cookie_note = await self.js_dismiss_cookie_banner()
        if cookies_dismissed:
            return True, cookie_note
        acted, note = await self._action_apply_entry()
        if acted:
            return acted, note
        snap = await self._snapshot()
        auth_possible = (
            bool(snap.get("has_email"))
            or int(snap.get("password_count") or 0) > 0
            or "/login" in normalize_text(snap.get("url") or "")
            or (
                bool(snap.get("has_create"))
                and bool(snap.get("has_signin"))
                and "create account" in normalize_text(snap.get("marker") or "")
            )
        )
        if self.creds.email and self.creds.password and auth_possible:
            acted, note = await self._auth_action("AUTH", snap)
            if acted:
                return acted, note
        if self.detect_wait_steps < 15:
            await asyncio.sleep(1.0)
            self.detect_wait_steps += 1
            return True, DETECT_WAIT_NOTE
        return False, "No deterministic entry action found from DETECT state."

    async def _auth_action(self, state: str, snap: dict[str, Any]) -> tuple[bool, str]:
        if not self.creds.email or not self.creds.password:
            return False, "Missing credentials in profile."
        marker = normalize_text(snap.get("marker") or "")
        has_email = bool(snap.get("has_email"))
        password_count = int(snap.get("password_count") or 0)
        has_create_cta = bool(snap.get("has_create"))
        has_signin_cta = bool(snap.get("has_signin"))
        create_marker = any(token in marker for token in ("create account", "create an account", "register", "sign up"))
        signin_marker = any(token in marker for token in ("sign in", "log in", "login"))
        if state == "CREATE_ACCOUNT":
            is_create = True
        elif state == "SIGN_IN":
            is_create = False
        elif password_count >= 2:
            is_create = True
        elif password_count == 1:
            is_create = False
        elif state == "LEGAL_ACCEPT":
            is_create = create_marker and has_email and not signin_marker
        else:
            is_create = create_marker and has_email and not signin_marker and (has_create_cta or not has_signin_cta)
        if is_create and self.auth_create_attempts >= 4:
            return False, "Create-account retry cap reached."
        if (not is_create) and self.auth_signin_attempts >= 2:
            return False, "Sign-in retry cap reached."
        e_ok, e_note = await self.el_fill(WD_SEL["email"], self.creds.email)
        if not e_ok:
            e_ok, e_note = await self.js_set_input_react(WD_SEL["email"], self.creds.email, ["email", "username", "user"])
        p_ok, p_note = await self.el_fill(WD_SEL["password"], self.creds.password)
        if not p_ok:
            p_ok, p_note = await self.js_set_input_react(WD_SEL["password"], self.creds.password, ["password"])
        v_ok, v_note = (True, "n/a")
        consent_ok, consent_note = (True, "n/a")
        if is_create:
            v_ok, v_note = await self.el_fill(WD_SEL["verify_password"], self.creds.password)
            if not v_ok:
                v_ok, v_note = await self.js_set_input_react(WD_SEL["verify_password"], self.creds.password, ["verify", "confirm"])
            if snap.get("has_checkbox"):
                consent_ok, consent_note = await self.el_check(WD_SEL["consent_checkbox"])
                if not consent_ok:
                    consent_ok, consent_note = await self.js_toggle_consent_checkbox()
            if has_email and not e_ok:
                return False, f"create:email not set ({e_note})"
            if not p_ok:
                return False, f"create:password not set ({p_note})"
            if password_count >= 2 and not v_ok:
                return False, f"create:verify not set ({v_note})"
            if snap.get("has_checkbox") and not consent_ok:
                return False, f"create:consent not toggled ({consent_note})"
            clicked, c_note = await self.el_click(
                WD_SEL["create_submit"],
                state_key="CREATE_ACCOUNT",
                text_hints=["create account", "register", "sign up", "continue"],
            )
            if not clicked:
                clicked, c_note = await self.js_click_verified(
                    WD_SEL["create_submit"],
                    ["create account", "register", "sign up", "continue"],
                    "CREATE_ACCOUNT",
                )
            if not clicked:
                return False, f"create:submit failed ({c_note})"
            self.auth_create_attempts += 1
            await asyncio.sleep(1.6)
            auth_err = await self._post_auth_error()
            if auth_err:
                # If account exists, pivot to sign-in and continue.
                if any(token in auth_err for token in ("already", "exists", "existing account", "taken")):
                    switched, switch_note = await self.el_click(
                        WD_SEL["sign_in_link"],
                        state_key="SIGN_IN",
                        text_hints=["already have an account", "sign in", "log in", "login"],
                    )
                    if not switched:
                        switched, switch_note = await self.js_click_verified(
                            WD_SEL["sign_in_link"],
                            ["already have an account", "sign in", "log in", "login"],
                            "SIGN_IN",
                        )
                    if switched:
                        return True, f"create:account-exists;switched:{switch_note};error:{auth_err[:120]}"
                return True, f"create:{c_note};error:{auth_err[:140]}"
            return True, (
                f"create:{c_note};email={e_ok}:{e_note};pass={p_ok}:{p_note};"
                f"verify={v_ok}:{v_note};consent={consent_ok}:{consent_note}"
            )
        if has_email and not e_ok:
            return False, f"signin:email not set ({e_note})"
        if not p_ok:
            return False, f"signin:password not set ({p_note})"
        clicked, c_note = await self.el_click(
            WD_SEL["signin_submit"],
            state_key="SIGN_IN",
            text_hints=["sign in", "log in", "continue"],
        )
        if not clicked:
            clicked, c_note = await self.js_click_verified(
                WD_SEL["signin_submit"],
                ["sign in", "log in", "continue"],
                "SIGN_IN",
            )
        if not clicked:
            return False, f"signin:submit failed ({c_note})"
        self.auth_signin_attempts += 1
        await asyncio.sleep(1.6)
        auth_err = await self._post_auth_error()
        if auth_err:
            if any(token in auth_err for token in ("incorrect", "invalid", "does not match")):
                return False, f"signin:error:{auth_err[:140]}"
            if any(
                token in auth_err
                for token in (
                    "couldn't find an account",
                    "cannot find an account",
                    "account not found",
                    "no account",
                    "not registered",
                )
            ):
                switched, switch_note = await self.el_click(
                    WD_SEL["create_account_link"],
                    state_key="CREATE_ACCOUNT",
                    text_hints=["create account", "register", "sign up", "new user"],
                )
                if not switched:
                    switched, switch_note = await self.js_click_verified(
                        WD_SEL["create_account_link"],
                        ["create account", "register", "sign up", "new user"],
                        "CREATE_ACCOUNT",
                    )
                if switched:
                    return True, f"signin:no-account;switched:{switch_note};error:{auth_err[:120]}"
            return True, f"signin:{c_note};warn:{auth_err[:120]}"
        return True, f"signin:{c_note};email={e_ok}:{e_note};pass={p_ok}:{p_note}"

    async def _fill_contact_info(self) -> tuple[bool, str]:
        filled: list[str] = []
        field_map = {
            "first_name": str(self.identity.get("first_name") or ""),
            "last_name": str(self.identity.get("last_name") or ""),
            "address_line1": str(self.address.get("street") or ""),
            "city": str(self.address.get("city") or ""),
            "postal_code": str(self.address.get("zip") or ""),
            "phone_number": str(self.identity.get("phone") or ""),
        }
        for key, value in field_map.items():
            if not value or key not in WD_SEL:
                continue
            if not await self._has_field(WD_SEL[key]):
                continue
            ok, note = await self.el_fill(WD_SEL[key], value)
            if ok:
                filled.append(key)
            else:
                fallback_ok, _ = await self.js_set_input_react(WD_SEL[key], value, [key.replace("_", " ")])
                if fallback_ok:
                    filled.append(f"{key}-js")

        state_value = str(self.address.get("state") or "").strip()
        state_hints = ["state", "province", "region"]
        if state_value and await self._has_field(WD_SEL["state_dropdown"], descriptor_hints=state_hints):
            state_candidates = self._state_option_candidates(state_value)
            state_ok, state_note = await self.el_select_combobox(
                WD_SEL["state_dropdown"],
                state_candidates,
                state_key="CONTACT",
                field_hints=state_hints,
            )
            if state_ok:
                filled.append(f"state:{state_note}")
            else:
                js_state_ok, js_state_note = await self.js_select_combobox(WD_SEL["state_dropdown"], state_candidates)
                if js_state_ok:
                    filled.append(f"state-js:{js_state_note}")

        phone_type_options = ["Mobile", "Cell", "Mobile Phone", "Cell Phone", "Home", "Work", "Personal"]
        phone_type_hints = ["phone device type", "device type", "phone type"]
        if await self._has_field(WD_SEL["phone_type_dropdown"], descriptor_hints=phone_type_hints):
            phone_type_ok, phone_type_note = await self.el_select_combobox(
                WD_SEL["phone_type_dropdown"],
                phone_type_options,
                state_key="CONTACT",
                field_hints=phone_type_hints,
            )
            if phone_type_ok:
                filled.append(f"phone_type:{phone_type_note}")
            else:
                js_phone_ok, js_phone_note = await self.js_select_combobox(
                    WD_SEL["phone_type_dropdown"],
                    phone_type_options,
                )
                if js_phone_ok:
                    filled.append(f"phone_type-js:{js_phone_note}")

        # Country phone code combobox: select "+1" from the option list.
        # This is a SEARCH-BOX combobox (id=address--countryPhoneCode); the generic
        # autofill fallback can type into its search input (leaving a stale value like
        # a name).  Target it explicitly and pick the matching option.
        phone_code_options = ["+1", "United States (+1)", "United States of America (+1)", "1"]
        if await self._has_field(WD_SEL["phone_code_dropdown"], descriptor_hints=["phone code", "country phone"]):
            phone_code_ok, phone_code_note = await self.el_select_combobox(
                WD_SEL["phone_code_dropdown"],
                phone_code_options,
                state_key="CONTACT",
                field_hints=["phone code", "country phone"],
            )
            if phone_code_ok:
                filled.append(f"phone_code:{phone_code_note}")
            else:
                js_pc_ok, js_pc_note = await self.js_select_combobox(WD_SEL["phone_code_dropdown"], phone_code_options)
                if js_pc_ok:
                    filled.append(f"phone_code-js:{js_pc_note}")

        if not filled:
            return False, "contact-fill:no-change"
        return True, f"contact-fill:{','.join(filled)}"

    async def run_legacy_create_account(self) -> HandlerOutcome:
        for _ in range(12):
            snap = await self._snapshot()
            state = self._state(snap)
            blocked = self._blocked(snap, state)
            if blocked:
                return blocked
            if state == "SUBMITTED":
                return self._outcome(HandlerResult.SUBMITTED, state, "Submission detected during legacy wrapper.", snap)
            if state not in AUTH_STATES and state != "APPLY_ENTRY":
                return self._outcome(HandlerResult.PROGRESSED, state, "Legacy wrapper reached non-auth state.", snap)
            acted, note = await self._action(state, snap)
            if not acted:
                return self._outcome(HandlerResult.NEEDS_LLM, state, note or "Legacy wrapper could not progress.", snap)
            self._record(f"legacy:{note}")
        return self._outcome(HandlerResult.BLOCKED, self.last_state or "AUTH", "Legacy wrapper step cap reached.", None, "legacy_step_limit")

    async def js_resolve_existing_data_conflicts(self) -> tuple[bool, str]:
        page = await self.browser_session.get_current_page()
        if page is None:
            return False, "no-active-page"
        raw = await page.evaluate(
            """
            () => {
              const n=(s)=>(s||'').toLowerCase().replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const click=(el)=>{if(!el)return false;try{el.scrollIntoView({block:'center',inline:'nearest'});}catch(e){}try{el.focus&&el.focus();}catch(e){}try{el.click();}catch(e){}try{el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,composed:true}));}catch(e){}return true;};
              const descriptor=(el)=>n([
                el.getAttribute&&el.getAttribute('name')||'',
                el.getAttribute&&el.getAttribute('id')||'',
                el.getAttribute&&el.getAttribute('aria-label')||'',
                el.getAttribute&&el.getAttribute('value')||'',
                (el.labels&&el.labels[0]&&el.labels[0].textContent)||'',
                (el.parentElement&&el.parentElement.textContent)||'',
                el.textContent||'',
              ].join(' '));
              const matchesNo=(text)=>{const t=n(text);return t==='no'||t.startsWith('no ')||t.includes(' no ')||t.includes('(no)');};

              let selectedNo=false;
              let changed=0;
              const containers=Array.from(document.querySelectorAll('fieldset,section,div,form'))
                .filter(v)
                .filter((el)=>{const txt=n(el.textContent||'');return txt.includes('previously worked for')||txt.includes('previous worker')||txt.includes('previously employed');})
                .slice(0,40);
              for(const container of containers){
                const nodes=Array.from(container.querySelectorAll('input[type="radio"],[role="radio"],label,span,button,div')).filter(v);
                for(const node of nodes){
                  const text=descriptor(node);
                  if(!matchesNo(text)) continue;
                  if(node.tagName==='INPUT'&&n(node.getAttribute('type'))==='radio'){
                    try{node.checked=true;}catch(e){}
                    try{node.dispatchEvent(new Event('input',{bubbles:true}));}catch(e){}
                    try{node.dispatchEvent(new Event('change',{bubbles:true}));}catch(e){}
                  }
                  click(node);
                  changed += 1;
                  selectedNo = true;
                }
              }

              const conflictErrors=Array.from(document.querySelectorAll('[role="alert"],.error,.field-error,.validation-error,[data-automation-id*="error"]'))
                .filter(v)
                .filter((el)=>n(el.textContent||'').includes('already exists'))
                .slice(0,10);
              for(const err of conflictErrors){
                const region=err.closest('fieldset,section,div,form')||err.parentElement;
                if(!region) continue;
                const controls=Array.from(region.querySelectorAll('button,[role="button"],a,span,div'))
                  .filter(v)
                  .filter((el)=>{const txt=descriptor(el);return txt.includes('edit')||txt.includes('update')||txt.includes('remove')||txt.includes('delete')||txt.includes('clear')||txt==='x';})
                  .slice(0,8);
                for(const control of controls){
                  if(click(control)) changed += 1;
                }
              }

              let clickedContinue=false;
              const ctas=Array.from(document.querySelectorAll('button,[role="button"],input[type="submit"]')).filter(v);
              const cta=ctas.find((el)=>{const txt=descriptor(el);if(!(txt.includes('save and continue')||txt==='continue'||txt.includes('next')))return false;return !(el.disabled||el.getAttribute('aria-disabled')==='true');});
              if(cta) clickedContinue = click(cta);

              return {
                success: !!(selectedNo || changed > 0 || clickedContinue),
                selected_no: !!selectedNo,
                changed_count: changed,
                clicked_continue: !!clickedContinue,
              };
            }
            """
        )
        data = self._as_dict(raw)
        if not data:
            return False, "existing-conflict-invalid-response"
        if not data.get("success"):
            return False, "existing-conflict-no-change"
        selected = bool(data.get("selected_no"))
        changed = int(data.get("changed_count") or 0)
        continued = bool(data.get("clicked_continue"))
        return True, f"existing-conflict:selected_no={selected};changed={changed};continued={continued}"

    async def js_fix_referral_source(self) -> tuple[bool, str]:
        page = await self.browser_session.get_current_page()
        if page is None:
            return False, "no-active-page"
        raw = await page.evaluate(
            """
            (payload) => {
              const n=(s)=>(s||'').toLowerCase().replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const d=(el)=>n([
                el.getAttribute&&el.getAttribute('name')||'',
                el.getAttribute&&el.getAttribute('id')||'',
                el.getAttribute&&el.getAttribute('aria-label')||'',
                el.getAttribute&&el.getAttribute('placeholder')||'',
                (el.labels&&el.labels[0]&&el.labels[0].textContent)||'',
                (el.parentElement&&el.parentElement.textContent)||'',
              ].join(' '));
              const click=(el)=>{if(!el)return false;try{el.scrollIntoView({block:'center',inline:'nearest'});}catch(e){}try{el.focus&&el.focus();}catch(e){}try{el.click();}catch(e){}try{el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,composed:true}));}catch(e){}return true;};
              const dispatch=(el)=>{if(!el)return;try{el.dispatchEvent(new Event('input',{bubbles:true}));}catch(e){}try{el.dispatchEvent(new Event('change',{bubbles:true}));}catch(e){}try{el.dispatchEvent(new Event('blur',{bubbles:true}));}catch(e){}};
              const isPlaceholder=(text)=>{const t=n(text);return !t||t==='select one'||t==='choose one'||t==='please select'||t==='select'||t==='-- select --'||t==='search';};
              const readValue=(el)=>{
                if(!el) return '';
                const tag=n(el.tagName||'');
                if(tag==='select'){
                  const so=el.selectedOptions&&el.selectedOptions.length?el.selectedOptions[0]:null;
                  return n((so&&so.textContent)||el.value||'');
                }
                const own=n(el.value||el.textContent||el.getAttribute&&el.getAttribute('aria-label')||'');
                if(own) return own;
                let sibling=el.previousElementSibling;
                let siblingHops=0;
                while(sibling&&siblingHops<6){
                  const raw=n(sibling.textContent||'');
                  const cleaned=n(raw.replace(/\\bx\\b/g,' '));
                  if(cleaned&&!isPlaceholder(cleaned)&&cleaned!=='search') return cleaned;
                  sibling=sibling.previousElementSibling;
                  siblingHops += 1;
                }
                const container=el.closest('[data-automation-id*="formField"],fieldset,section,div')||el.parentElement;
                if(container){
                  const chip=container.querySelector('[data-automation-id*="selected"],[aria-selected="true"],[data-automation-id*="token"],[data-automation-id*="pill"]');
                  const chipText=n(chip&&chip.textContent||'');
                  if(chipText) return chipText;
                }
                return '';
              };
              const choices=(Array.isArray(payload?.referralOptions)?payload.referralOptions:[]).map((x)=>n(x)).filter(Boolean);
              const keywords=['how did you hear','referral source','referral'];
              const matches=(desc)=>keywords.some((k)=>desc.includes(k));
              const fields=Array.from(document.querySelectorAll('select,input,[role="combobox"],[aria-haspopup="listbox"],[data-automation-id*="promptSearchInput"],[data-automation-id*="comboBox"]')).filter(v);
              const target=fields.find((el)=>matches(d(el)));
              if(!target) return {success:false,reason:'referral-field-not-found'};
              const errorNodes=Array.from(document.querySelectorAll('[role="alert"],.error,.field-error,.validation-error,[data-automation-id*="error"]')).filter(v);
              const hasReferralError=errorNodes.some((el)=>{
                const txt=n(el.textContent||'');
                return txt.includes('how did you hear')||txt.includes('referral');
              });

              const before=readValue(target);
              if(!isPlaceholder(before)){
                return {success:false,reason:'referral-already-populated',before:before,after:before,valid:true,changed:false};
              }
              if(!hasReferralError){
                return {success:false,reason:'referral-not-blocking',before:before,after:before,valid:false,changed:false};
              }

              click(target);
              if((target.tagName||'').toLowerCase()==='select'&&target.options){
                const opts=Array.from(target.options||[]);
                let pick=null;
                for(const c of choices){
                  pick=opts.find((o)=>{const txt=n(o.textContent||'');const val=n(o.value||'');return txt===c||txt.includes(c)||val.includes(c);});
                  if(pick) break;
                }
                if(!pick){
                  pick=opts.find((o)=>{
                    const txt=n(o.textContent||'');
                    const val=n(o.value||'');
                    const candidate=txt||val;
                    return !isPlaceholder(candidate);
                  });
                }
                if(pick){
                  try{target.value=pick.value;}catch(e){}
                  dispatch(target);
                }
              } else {
                const first=choices[0]||'';
                if(first&&'value' in target){
                  try{target.value='';target.value=first;}catch(e){}
                  dispatch(target);
                }
                const options=Array.from(document.querySelectorAll('[role="listbox"] [role="option"],[role="option"],li[role="option"],div[role="option"],[data-automation-id*="menuItem"]')).filter(v);
                let picked=null;
                for(const c of choices){
                  picked=options.find((opt)=>{const txt=n(opt.textContent||'');return txt===c||txt.includes(c);});
                  if(picked) break;
                }
                if(!picked){
                  picked=options.find((opt)=>{
                    const txt=n(opt.textContent||'');
                    return !isPlaceholder(txt);
                  });
                }
                if(picked) click(picked);
              }

              const after=readValue(target);
              const valid=!isPlaceholder(after);
              const changed=valid && after!==before;
              return {
                success: !!changed,
                before: before,
                after: after,
                valid: !!valid,
                changed: !!changed,
                reason: changed ? 'referral-updated' : (valid ? 'referral-valid-unchanged' : 'referral-no-change'),
              };
            }
            """,
            {"referralOptions": self._referral_candidates()},
        )
        data = self._as_dict(raw)
        if not data:
            return False, "referral-fix-invalid-response"
        if not data.get("success"):
            return False, str(data.get("reason") or "referral-fix-no-change")
        return True, f"referral-fix:{data.get('before','')}->{data.get('after','')};valid={bool(data.get('valid'))}"

    async def _fill_self_id_date(self) -> tuple[bool, str]:
        """Fill the CC-305 disability-form date picker (MM/DD/YYYY) with a
        proven CDP commit sequence (focus → select-all → clear → type →
        input/change/blur per segment).  Only acts when the date inputs are
        visible on the current page."""
        import asyncio as _asyncio
        from datetime import datetime as _dt
        now = _dt.now()
        segs = [
            ("dateSectionMonth-input", f"{now.month:02d}"),
            ("dateSectionDay-input",   f"{now.day:02d}"),
            ("dateSectionYear-input",  str(now.year)),
        ]
        # Also try the alternate "dateSignedOn" prefix (seen on some Workday
        # disability forms)
        alt_prefixes = ["dateSignedOn-month-input", "dateSignedOn-day-input", "dateSignedOn-year-input"]

        page = await self.browser_session.get_current_page()
        if page is None:
            return False, "no-active-page"

        # Find which prefix is present
        prefix = "selfIdentifiedDisabilityData--"
        found_prefix = None
        for pfx in ["selfIdentifiedDisabilityData--", ""]:
            for sel, _ in segs:
                try:
                    el = await page.evaluate(
                        f"document.querySelector('#{pfx}{sel}')"
                    )
                    if el is not None:
                        found_prefix = pfx
                        break
                except Exception:
                    pass
            if found_prefix:
                break

        if found_prefix is None:
            return False, "no-self-id-date-inputs-found"

        filled_any = False
        for sel, val in segs:
            full_id = f"#{found_prefix}{sel}"
            try:
                await page.evaluate(
                    f"(() => {{ const el=document.querySelector('{full_id}');"
                    f" if(el){{el.scrollIntoView({{block:'center'}}); el.focus();}}"
                    f" return !!el; }})()"
                )
                await _asyncio.sleep(0.12)
                # select-all + clear
                await page.evaluate(
                    f"(() => {{ const el=document.querySelector('{full_id}');"
                    f" if(!el) return false;"
                    f" el.select();"
                    f" const d=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');"
                    f" d.set.call(el,'');"
                    f" el.dispatchEvent(new Event('input',{{bubbles:true}}));"
                    f" return true; }})()"
                )
                await _asyncio.sleep(0.1)
                # type via CDP
                await self.browser_session.type_text(val)
                await _asyncio.sleep(0.12)
                # commit
                await page.evaluate(
                    f"(() => {{ const el=document.querySelector('{full_id}');"
                    f" if(!el) return false;"
                    f" el.dispatchEvent(new Event('change',{{bubbles:true}}));"
                    f" el.dispatchEvent(new Event('blur',{{bubbles:true}}));"
                    f" el.dispatchEvent(new Event('focusout',{{bubbles:true}}));"
                    f" return true; }})()"
                )
                await _asyncio.sleep(0.15)
                filled_any = True
            except Exception:
                continue

        if not filled_any:
            return False, "date-fill-no-segments-filled"

        # Verify
        vals = {}
        for sel, _ in segs:
            try:
                v = await page.evaluate(
                    f"(document.querySelector('#{found_prefix}{sel}')||{{}}).value"
                )
                vals[sel] = str(v)
            except Exception:
                vals[sel] = "?"
        return True, f"self-id-date-filled:{vals}"

    async def js_autofill_required_fields(self) -> tuple[bool, str]:
        page = await self.browser_session.get_current_page()
        if page is None:
            return False, "no-active-page"
        raw = await page.evaluate(
            """
            (payload) => {
              const n=(s)=>(s||'').toLowerCase().replace(/[\\u2018\\u2019]/g,"'").replace(/[\\u201C\\u201D]/g,'"').replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const d=(el)=>{
                const container=el&&el.closest?el.closest('[data-automation-id*="formField"],[data-automation-id*="question"],fieldset,section,li,div'):null;
                const containerText=n((container&&container.textContent)||'').slice(0,480);
                const parentText=n((el&&el.parentElement&&el.parentElement.textContent)||'').slice(0,280);
                return n([
                  el.getAttribute&&el.getAttribute('name')||'',
                  el.getAttribute&&el.getAttribute('id')||'',
                  el.getAttribute&&el.getAttribute('aria-label')||'',
                  el.getAttribute&&el.getAttribute('placeholder')||'',
                  (el.labels&&el.labels[0]&&el.labels[0].textContent)||'',
                  parentText,
                  containerText,
                ].join(' '));
              };
              const click=(el)=>{if(!el)return false;try{el.scrollIntoView({block:'center',inline:'nearest'});}catch(e){}try{el.focus&&el.focus();}catch(e){}try{el.click();}catch(e){}try{el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,composed:true}));}catch(e){}return true;};
              const dispatch=(el)=>{try{el.dispatchEvent(new Event('input',{bubbles:true}));}catch(e){}try{el.dispatchEvent(new Event('change',{bubbles:true}));}catch(e){}try{el.dispatchEvent(new Event('blur',{bubbles:true}));}catch(e){}};
              const anyKeyword=(text,keywords)=>{const t=n(text);return (keywords||[]).some((k)=>t.includes(n(k)));};
              const isPlaceholder=(text)=>{const t=n(text);return !t||t==='select one'||t==='choose one'||t==='please select'||t==='select'||t==='-- select --';};
              const setInput=(keywords,value,requireEmpty=false)=>{const val=String(value||'').trim();if(!val)return false;const fields=Array.from(document.querySelectorAll('input,textarea,[role="textbox"],[contenteditable="true"]')).filter(v);for(const field of fields.slice(0,220)){const desc=d(field);if(!anyKeyword(desc,keywords))continue;const type=n(field.getAttribute&&field.getAttribute('type'));if(['hidden','checkbox','radio','file','button','submit'].includes(type))continue;const current=n(('value' in field?field.value:field.textContent)||'');if(requireEmpty&&current)continue;click(field);try{if('value' in field){field.value='';field.value=val;}else{field.textContent=val;}}catch(e){}dispatch(field);const after=n(('value' in field?field.value:field.textContent)||'');if(after.includes(n(val).slice(0,6)))return true;}return false;};
              const pickOption=(candidates,allowFallback=false)=>{const options=Array.from(document.querySelectorAll('[role="listbox"] [role="option"],[role="option"],li[role="option"],div[role="option"],[data-automation-id*="menuItem"]')).filter(v);for(const desired of (candidates||[])){const key=n(desired);if(!key)continue;const hit=options.find((opt)=>{const txt=n(opt.textContent||'');return txt===key||txt.startsWith(key+' ')||txt.includes(' '+key+' ');});if(hit){click(hit);return n(hit.textContent||desired);}}if(allowFallback){const first=options.find((opt)=>!isPlaceholder(opt.textContent||''));if(first){click(first);return n(first.textContent||'');}}return '';};
              const setSelectOrCombo=(keywords,values)=>{
                const fields=Array.from(document.querySelectorAll('select,input,[role="combobox"],[aria-haspopup="listbox"],[data-automation-id*="promptSearchInput"],[data-automation-id*="comboBox"]')).filter(v);
                const readFieldValue=(field)=>{
                  const tag=n(field.tagName||'');
                  if(tag==='select'){
                    const so=field.selectedOptions&&field.selectedOptions.length?field.selectedOptions[0]:null;
                    return n((so&&so.textContent)||field.value||'');
                  }
                  const own=n(field.value||field.textContent||field.getAttribute&&field.getAttribute('aria-label')||'');
                  if(own) return own;
                  let sibling=field.previousElementSibling;
                  let siblingHops=0;
                  while(sibling&&siblingHops<6){
                    const raw=n(sibling.textContent||'');
                    const cleaned=n(raw.replace(/\\bx\\b/g,' '));
                    if(cleaned&&!isPlaceholder(cleaned)&&cleaned!=='search') return cleaned;
                    sibling=sibling.previousElementSibling;
                    siblingHops += 1;
                  }
                  const container=field.closest('[data-automation-id*="formField"],fieldset,section,div')||field.parentElement;
                  if(container){
                    const chip=container.querySelector('[data-automation-id*="selected"],[aria-selected="true"],[data-automation-id*="token"],[data-automation-id*="pill"]');
                    const chipText=n(chip&&chip.textContent||'');
                    if(chipText) return chipText;
                  }
                  return '';
                };
                for(const field of fields.slice(0,180)){
                  const desc=d(field);
                  if(!anyKeyword(desc,keywords))continue;
                  const existing=readFieldValue(field);
                  if(!isPlaceholder(existing)) return {changed:false,value:existing,already:true};
                  click(field);
                  if((field.tagName||'').toLowerCase()==='select'&&field.options){
                    const opts=Array.from(field.options||[]);
                    let picked=null;
                    for(const value of (values||[])){
                      const key=n(value);
                      if(!key)continue;
                      picked=opts.find((o)=>{const txt=n(o.textContent||'');const val=n(o.value||'');return txt===key||txt.includes(key)||val.includes(key);});
                      if(picked)break;
                    }
                    if(!picked){
                      picked=opts.find((o)=>!isPlaceholder(o.textContent||'')&&!isPlaceholder(o.value||''));
                    }
                    if(picked){
                      try{field.value=picked.value;}catch(e){}
                      dispatch(field);
                      return {changed:true,value:n(picked.textContent||picked.value||''),already:false};
                    }
                    continue;
                  }
                  const picked=pickOption(values||[],true);
                  if(picked)return {changed:true,value:picked,already:false};
                  const typed=String((values&&values[0])||'').trim();
                  if(typed&&'value' in field){
                    const before=n(field.value||'');
                    if(!before||isPlaceholder(before)){
                      try{field.value=typed;}catch(e){}
                      dispatch(field);
                    }
                    const after=n(field.value||'');
                    if(!isPlaceholder(after)&&after.includes(n(typed).slice(0,5)))return {changed:true,value:after,already:false};
                  }
                }
                return {changed:false,value:'',already:false};
              };
              const setPreviousEmploymentNo=()=>{const questionKeywords=Array.isArray(payload?.questionKeywords)?payload.questionKeywords.map((k)=>n(k)).filter(Boolean):[];const noOptions=Array.isArray(payload?.noOptions)?payload.noOptions.map((k)=>n(k)).filter(Boolean):['no'];const containers=Array.from(document.querySelectorAll('fieldset,section,div,form')).filter(v).filter((el)=>questionKeywords.some((q)=>n(el.textContent||'').includes(q))).slice(0,50);for(const container of containers){const nodes=Array.from(container.querySelectorAll('input[type="radio"],[role="radio"],label,span,button,div')).filter(v).filter((el)=>{const txt=n([el.textContent||'',el.getAttribute&&el.getAttribute('aria-label')||'',el.getAttribute&&el.getAttribute('value')||'',(el.parentElement&&el.parentElement.textContent)||''].join(' '));return noOptions.some((opt)=>txt.includes(opt));});for(const node of nodes.slice(0,16)){if((node.getAttribute&&n(node.getAttribute('type')))==='radio'||node.type==='radio'){try{node.checked=true;}catch(e){}dispatch(node);}click(node);const selected=Array.from(container.querySelectorAll('[role="radio"][aria-checked="true"],input[type="radio"]:checked')).some((sel)=>{const txt=n([sel.textContent||'',sel.getAttribute&&sel.getAttribute('aria-label')||'',sel.getAttribute&&sel.getAttribute('value')||'',(sel.parentElement&&sel.parentElement.textContent)||''].join(' '));return noOptions.some((opt)=>txt.includes(opt));});if(selected)return true;}}return false;};
              const setEeoChoice=(questionKeywords,optionValues)=>{
                const keywords=(questionKeywords||[]).map((k)=>n(k)).filter(Boolean);
                if(!keywords.length) return {changed:false,value:''};
                const options=(optionValues||[]).map((k)=>n(k)).filter(Boolean);
                if(!options.length) return {changed:false,value:''};
                const radioText=(r)=>{
                  let t=n(r.textContent||'');
                  if(!t&&r.labels&&r.labels[0]) t=n(r.labels[0].textContent||'');
                  if(!t&&r.closest){const wrap=r.closest('label');if(wrap)t=n(wrap.textContent||'');}
                  if(!t&&r.getAttribute) t=n(r.getAttribute('aria-label')||'');
                  return t;
                };
                const containers=Array.from(document.querySelectorAll('fieldset,section,div,form')).filter(v).filter((el)=>{const t=n(el.textContent||'');return keywords.some((k)=>t.includes(k));}).slice(0,40);
                const order=(list)=>{if(!list.length)return [];const scored=list.map((item,idx)=>({item,idx,score:options.findIndex((opt)=>item.text.includes(opt))})).sort((a,b)=>{const sa=a.score===-1?99:a.score;const sb=b.score===-1?99:b.score;return sa-sb||a.idx-b.idx;});return scored.map((x)=>x.item);};
                for(const container of containers){
                  const radios=order(Array.from(container.querySelectorAll('input[type="radio"],[role="radio"]')).filter(v).map((r)=>({el:r,text:radioText(r),kind:'radio'})));
                  const checkboxes=order(Array.from(container.querySelectorAll('input[type="checkbox"],[role="checkbox"]')).filter(v).map((c)=>{let t=n(c.textContent||'');if(!t&&c.labels&&c.labels[0])t=n(c.labels[0].textContent||'');if(!t&&c.closest){const w=c.closest('label');if(w)t=n(w.textContent||'');}if(!t&&c.getAttribute)t=n(c.getAttribute('aria-label')||'');return {el:c,text:t,kind:'checkbox'};}));
                  const choices=[...radios,...checkboxes];
                  for(const opt of options){
                    const hit=choices.find((r)=>{const b=n(r.text);return b.length>0&&b.includes(opt);});
                    if(!hit) continue;
                    if(hit.kind==='radio'){try{hit.el.checked=true;}catch(e){}dispatch(hit.el);}
                    click(hit.el);
                    if(hit.kind==='checkbox'){
                      let checked=false;
                      try{checked=!!hit.el.checked;}catch(e){}
                      if(!checked){try{hit.el.checked=true;}catch(e){}dispatch(hit.el);click(hit.el);try{checked=!!hit.el.checked;}catch(e){}}
                      const label=(hit.el.labels&&hit.el.labels[0])||null;
                      if(label)click(label);
                      if(checked) return {changed:true,value:n(hit.text||opt),kind:'checkbox'};
                      continue;
                    }
                    const label=(hit.el.labels&&hit.el.labels[0])||null;
                    click(label||hit.el);
                    const verified=Array.from(container.querySelectorAll('input[type="radio"]:checked,[role="radio"][aria-checked="true"]')).some((sel)=>{const b=n(radioText(sel));return b.length>0&&b.includes(opt);});
                    if(verified) return {changed:true,value:n(hit.text||opt),kind:'radio'};
                  }
                }
                return {changed:false,value:'',kind:''};
              };
              const clickContinue=()=>{const nodes=Array.from(document.querySelectorAll('button,[role="button"],input[type="submit"]')).filter(v);const target=nodes.find((el)=>{const txt=n(el.textContent||el.value||el.getAttribute('aria-label')||'');if(!txt)return false;if(!(txt.includes('save and continue')||txt==='continue'||txt.includes('next')))return false;return !(el.disabled||el.getAttribute('aria-disabled')==='true');});if(!target)return false;click(target);return true;};
              const regionsForErrors=(keywords)=>Array.from(document.querySelectorAll('[role="alert"],.error,.field-error,.validation-error,[data-automation-id*="error"]')).filter(v).filter((el)=>anyKeyword(el.textContent||'',keywords)).map((el)=>el.closest('fieldset,section,div,form')||el.parentElement).filter(Boolean);
              const setSelectOrComboInRegion=(regions,optionValues)=>{
                for(const region of (regions||[]).slice(0,20)){
                  const fields=Array.from(region.querySelectorAll('select,input,[role="combobox"],[aria-haspopup="listbox"],[data-automation-id*="promptSearchInput"],[data-automation-id*="comboBox"]')).filter(v);
                  for(const field of fields.slice(0,14)){
                    click(field);
                    if((field.tagName||'').toLowerCase()==='select'&&field.options){
                      const opts=Array.from(field.options||[]);
                      let picked=null;
                      for(const value of (optionValues||[])){const key=n(value);if(!key)continue;picked=opts.find((o)=>{const txt=n(o.textContent||'');const val=n(o.value||'');return txt===key||txt.includes(key)||val.includes(key);});if(picked)break;}
                      if(!picked)picked=opts.find((o)=>!isPlaceholder(o.textContent||'')&&!isPlaceholder(o.value||''));
                      if(picked){try{field.value=picked.value;}catch(e){}dispatch(field);return {changed:true,value:n(picked.textContent||picked.value||'')};}
                    } else {
                      const picked=pickOption(optionValues||[],true);
                      if(picked) return {changed:true,value:picked};
                      const first=String((optionValues&&optionValues[0])||'').trim();
                      if(first&&'value' in field){
                        const before=n(field.value||'');
                        if(!before||isPlaceholder(before)){
                          try{field.value=first;}catch(e){}
                          dispatch(field);
                        }
                        const after=n(field.value||'');
                        if(!isPlaceholder(after)&&after.includes(n(first).slice(0,5))) return {changed:true,value:after};
                      }
                    }
                  }
                }
                return {changed:false,value:''};
              };
              const setPreviousEmploymentNoInRegions=(regions)=>{
                const noOptions=Array.isArray(payload?.noOptions)?payload.noOptions.map((k)=>n(k)).filter(Boolean):['no'];
                for(const region of (regions||[]).slice(0,20)){
                  const nodes=Array.from(region.querySelectorAll('input[type="radio"],[role="radio"],label,span,button,div')).filter(v).filter((el)=>{const txt=n([el.textContent||'',el.getAttribute&&el.getAttribute('aria-label')||'',el.getAttribute&&el.getAttribute('value')||'',(el.parentElement&&el.parentElement.textContent)||''].join(' '));return noOptions.some((opt)=>txt.includes(opt));});
                  for(const node of nodes.slice(0,16)){
                    if((node.getAttribute&&n(node.getAttribute('type')))==='radio'||node.type==='radio'){try{node.checked=true;}catch(e){}dispatch(node);}
                    click(node);
                    const selected=Array.from(region.querySelectorAll('[role="radio"][aria-checked="true"],input[type="radio"]:checked')).some((sel)=>{const txt=n([sel.textContent||'',sel.getAttribute&&sel.getAttribute('aria-label')||'',sel.getAttribute&&sel.getAttribute('value')||'',(sel.parentElement&&sel.parentElement.textContent)||''].join(' '));return noOptions.some((opt)=>txt.includes(opt));});
                    if(selected) return true;
                  }
                }
                return false;
              };
              const setChoiceInRegions=(regions,optionValues)=>{
                const options=(optionValues||[]).map((item)=>n(item)).filter(Boolean);
                if(!options.length) return false;
                for(const region of (regions||[]).slice(0,20)){
                  const nodes=Array.from(region.querySelectorAll('input[type="radio"],[role="radio"],label,span,button,div')).filter(v);
                  for(const node of nodes.slice(0,80)){
                    const txt=n([node.textContent||'',node.getAttribute&&node.getAttribute('aria-label')||'',node.getAttribute&&node.getAttribute('value')||'',(node.parentElement&&node.parentElement.textContent)||''].join(' '));
                    if(!options.some((opt)=>txt===opt||txt.startsWith(opt+' ')||txt.endsWith(' '+opt)||txt.includes(' '+opt+' ')||txt.includes(opt))) continue;
                    if((node.getAttribute&&n(node.getAttribute('type')))==='radio'||node.type==='radio'){try{node.checked=true;}catch(e){}dispatch(node);}
                    click(node);
                    const selected=Array.from(region.querySelectorAll('[role="radio"][aria-checked="true"],input[type="radio"]:checked')).some((sel)=>{
                      const st=n([sel.textContent||'',sel.getAttribute&&sel.getAttribute('aria-label')||'',sel.getAttribute&&sel.getAttribute('value')||'',(sel.parentElement&&sel.parentElement.textContent)||''].join(' '));
                      return options.some((opt)=>st.includes(opt));
                    });
                    if(selected) return true;
                  }
                }
                return false;
              };

              const referralErrors=regionsForErrors(['how did you hear about us','how did you hear','referral','source']);
              const deviceErrors=regionsForErrors(['phone device type','device type']);
              const phoneCodeErrors=regionsForErrors(['country phone code','phone code']);
              const previousEmploymentErrors=regionsForErrors(['previously worked for','worked for','previously employed']);
              const authorizedErrors=regionsForErrors(['authorized to work','work authorization','work in the job']);
              const sponsorshipErrors=regionsForErrors(['visa sponsorship','require sponsorship','sponsorship to work','require visa']);

              const referralFromError=setSelectOrComboInRegion(referralErrors,payload?.referralOptions||[]);
              const deviceFromError=setSelectOrComboInRegion(deviceErrors,payload?.deviceTypeOptions||[]);
              const phoneCodeFromError=setSelectOrComboInRegion(phoneCodeErrors,payload?.countryPhoneCodeOptions||[]);
              const prevSelectFromError=setSelectOrComboInRegion(previousEmploymentErrors,payload?.noOptions||['No']);
              const prevFromError=prevSelectFromError.changed||setPreviousEmploymentNoInRegions(previousEmploymentErrors);
              const authorizedFromError=setSelectOrComboInRegion(authorizedErrors,payload?.authorizedToWorkOptions||[]);
              const sponsorshipFromError=setSelectOrComboInRegion(sponsorshipErrors,payload?.sponsorshipOptions||[]);
              const referral=referralFromError.changed?referralFromError:setSelectOrCombo(['how did you hear about us','how did you hear','referral','source'],payload?.referralOptions||[]);
              const device=deviceFromError.changed?deviceFromError:setSelectOrCombo(['phone device type','device type'],payload?.deviceTypeOptions||[]);
              const phoneCode=phoneCodeFromError.changed?phoneCodeFromError:setSelectOrCombo(['country phone code','phone code'],payload?.countryPhoneCodeOptions||[]);
              const previousEmploymentGeneric=setSelectOrCombo(['previously worked for','worked for','previously employed'],payload?.noOptions||['No']);
              const authorizedGeneric=setSelectOrCombo(['authorized to work','work authorization','work in the job'],payload?.authorizedToWorkOptions||[]);
              const sponsorshipGeneric=setSelectOrCombo(['visa sponsorship','require sponsorship','sponsorship'],payload?.sponsorshipOptions||[]);
              const authorizedChoice=authorizedFromError.changed?true:(setChoiceInRegions(authorizedErrors,payload?.authorizedToWorkOptions||[])||setChoiceInRegions(regionsForErrors(['authorized to work','work authorization']),payload?.authorizedToWorkOptions||[]));
              const sponsorshipChoice=sponsorshipFromError.changed?true:(setChoiceInRegions(sponsorshipErrors,payload?.sponsorshipOptions||[])||setChoiceInRegions(regionsForErrors(['visa sponsorship','require sponsorship','sponsorship']),payload?.sponsorshipOptions||[]));
              const disabilityResult=setEeoChoice(payload?.disabilityQuestionKeywords||[],payload?.disabilityOptions||[]);
              const veteranResult=setEeoChoice(payload?.veteranQuestionKeywords||[],payload?.veteranOptions||[]);
              const hispanicResult=setEeoChoice(payload?.raceQuestionKeywords||[],payload?.hispanicOptions||[]);
              const raceResult=setEeoChoice(['ethnicity','race'],payload?.raceOptions||[]);
              const authorizedSet=!!(authorizedFromError.changed||authorizedGeneric.changed||authorizedChoice);
              const sponsorshipSet=!!(sponsorshipFromError.changed||sponsorshipGeneric.changed||sponsorshipChoice);
              const firstNameSet=setInput(['first name'],payload?.firstName||'',false);
              const lastNameSet=setInput(['last name'],payload?.lastName||'',false);
              const emailSet=setInput(['email'],payload?.email||'',false);
              const selfIdPage=/disabilit|cc-305|section 503|self identify/i.test(document.body.textContent||'');
              const fullNameSet=selfIdPage?setInput(['name'],payload?.fullName||'',true):false;
              const phoneSet=setInput(['phone number','phone'],payload?.phone||'',false);
              const addressSet=setInput(['address line 1','street address','address'],payload?.addressLine1||'',false);
              const citySet=setInput(['city'],payload?.city||'',false);
              const stateSelect=setSelectOrCombo(['state','province'],payload?.stateOptions||[]);
              const stateSet=setInput(['state','province'],payload?.state||'',false);
              const postalSet=setInput(['postal code','zip code','zip'],payload?.postalCode||'',false);
              const countrySelect=setSelectOrCombo(['country'],[payload?.country||'United States','United States','US','USA']);
              const prevEmploymentSet=prevFromError||previousEmploymentGeneric.changed||setPreviousEmploymentNo();
              const continued=clickContinue();
              const dateSegs=Array.from(document.querySelectorAll('input[id*="dateSectionMonth-input"],input[id*="dateSectionDay-input"],input[id*="dateSectionYear-input"],input[id*="dateSignedOn-month-input"],input[id*="dateSignedOn-day-input"],input[id*="dateSignedOn-year-input"]')).filter(v);
              const selfIdDatePresent=dateSegs.length>0;
              const eeoSet=!!(disabilityResult.changed||veteranResult.changed||hispanicResult.changed||raceResult.changed);
              const success=!!(referral.changed||device.changed||phoneCode.changed||authorizedSet||sponsorshipSet||firstNameSet||lastNameSet||fullNameSet||emailSet||phoneSet||addressSet||citySet||stateSet||stateSelect.changed||postalSet||countrySelect.changed||prevEmploymentSet||eeoSet||continued);
              return {
                success,
                referral_set: !!referral.changed,
                referral_value: referral.value||'',
                device_set: !!device.changed,
                device_value: device.value||'',
                phone_code_set: !!phoneCode.changed,
                phone_code_value: phoneCode.value||'',
                authorized_set: !!authorizedSet,
                sponsorship_set: !!sponsorshipSet,
                first_name_set: !!firstNameSet,
                last_name_set: !!lastNameSet,
                full_name_set: !!fullNameSet,
                email_set: !!emailSet,
                phone_set: !!phoneSet,
                address_set: !!addressSet,
                city_set: !!citySet,
                state_set: !!stateSet,
                state_select_set: !!stateSelect.changed,
                postal_set: !!postalSet,
                country_set: !!countrySelect.changed,
                previous_employment_set: !!prevEmploymentSet,
                eeo_set: !!eeoSet,
                self_id_date_present: !!selfIdDatePresent,
                disability_set: !!disabilityResult.changed,
                disability_value: disabilityResult.value||'',
                veteran_set: !!veteranResult.changed,
                veteran_value: veteranResult.value||'',
                hispanic_set: !!hispanicResult.changed,
                hispanic_value: hispanicResult.value||'',
                race_set: !!raceResult.changed,
                race_value: raceResult.value||'',
                clicked_continue: !!continued,
              };
            }
            """,
            self._required_field_payload(),
        )
        data = self._as_dict(raw)
        if not data:
            return False, "required-field-autofill-invalid-response"
        if not data.get("success"):
            return False, "required-field-autofill-no-change"
        flags: list[str] = []
        for key in (
            "referral_set",
            "device_set",
            "phone_code_set",
            "authorized_set",
            "sponsorship_set",
            "first_name_set",
            "last_name_set",
            "full_name_set",
            "email_set",
            "phone_set",
            "address_set",
            "city_set",
            "state_set",
            "state_select_set",
            "postal_set",
            "country_set",
            "previous_employment_set",
            "eeo_set",
            "disability_set",
            "veteran_set",
            "hispanic_set",
            "race_set",
            "clicked_continue",
        ):
            if data.get(key):
                flags.append(key)
        # CC-305 disability form: fill the date picker with CDP typing
        if data.get("self_id_date_present"):
            date_filled, date_note = await self._fill_self_id_date()
            if date_filled:
                flags.append(date_note)
        return True, f"required-field-autofill:{','.join(flags) if flags else 'updated'}"

    async def js_find_visible(self, selectors: list[str], text_hints: list[str] | None = None) -> dict[str, Any]:
        page = await self.browser_session.get_current_page()
        if page is None:
            return {"found": False, "reason": "no-active-page"}
        raw = await page.evaluate(
            """
            (p) => {
              const sels=Array.isArray(p?.selectors)?p.selectors:[];const hints=Array.isArray(p?.text_hints)?p.text_hints:[];
              const n=(s)=>(s||'').toLowerCase().replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const t=(el)=>n(el.textContent||el.value||el.getAttribute('aria-label')||'');
              for(const s of sels){try{const el=Array.from(document.querySelectorAll(s)).find(v);if(el)return {found:true,selector:s,text:t(el)};}catch(e){}}
              if(hints.length){const hs=hints.map(n).filter(Boolean);const el=Array.from(document.querySelectorAll('button,a,[role=\"button\"],[role=\"link\"],input[type=\"submit\"],input[type=\"button\"],span,div')).find((x)=>v(x)&&hs.some((h)=>t(x).includes(h)));if(el)return {found:true,selector:'[text]',text:t(el)};}
              return {found:false};
            }
            """,
            {"selectors": selectors, "text_hints": text_hints or []},
        )
        parsed = self._as_dict(raw)
        return parsed if parsed else {"found": False, "reason": "invalid-response"}

    async def js_dismiss_cookie_banner(self) -> tuple[bool, str]:
        page = await self.browser_session.get_current_page()
        if page is None:
            return False, "no-active-page"
        raw = await page.evaluate(
            """
            () => {
              const n=(s)=>(s||'').toLowerCase().replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const click=(el)=>{if(!el)return false;try{el.scrollIntoView({block:'center',inline:'nearest'});}catch(e){}try{el.focus&&el.focus();}catch(e){}try{el.click();}catch(e){}try{el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,composed:true}));}catch(e){}return true;};
              const text=(el)=>n(el.textContent||el.value||el.getAttribute&&el.getAttribute('aria-label')||'');
              const knownSelectors=[
                '#onetrust-accept-btn-handler',
                '.onetrust-close-btn-handler',
                '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
                '[data-testid=\"cookie-policy-dialog-accept-button\"]',
                '.cc-btn.cc-allow',
                '#accept-cookie-notification',
                '.js-cookie-consent-agree',
                '[data-cookiefirst-action=\"accept\"]',
              ];
              for(const sel of knownSelectors){
                try{
                  const btn=document.querySelector(sel);
                  if(btn&&v(btn)){click(btn);return {success:true,method:'known-selector',label:sel};}
                }catch(e){}
              }

              const keywords=['accept cookies','accept all cookies','accept all','allow all','allow cookies','i agree','agree'];
              const buttons=Array.from(document.querySelectorAll('button,a,[role=\"button\"],input[type=\"button\"],input[type=\"submit\"]')).filter(v);
              for(const btn of buttons){
                const tx=text(btn);
                if(!tx||tx.length>80) continue;
                if(!keywords.some((k)=>tx.includes(k))) continue;
                let inBanner=false;
                let p=btn;
                for(let i=0;i<8&&p;i++){
                  const marker=n([p.className||'',p.id||'',p.getAttribute&&p.getAttribute('role')||'',p.getAttribute&&p.getAttribute('aria-label')||''].join(' '));
                  if(marker.includes('cookie')||marker.includes('consent')||marker.includes('gdpr')||marker.includes('privacy')||marker.includes('banner')||marker==='dialog'||marker==='alertdialog'){
                    inBanner=true;
                    break;
                  }
                  p=p.parentElement;
                }
                if(inBanner||tx.includes('accept cookies')||tx.includes('accept all')){
                  click(btn);
                  return {success:true,method:'keyword-button',label:tx.slice(0,80)};
                }
              }
              return {success:false,reason:'cookie-banner-not-found'};
            }
            """
        )
        parsed = self._as_dict(raw)
        if parsed and parsed.get("success"):
            label = str(parsed.get("label") or parsed.get("method") or "cookie-banner")
            return True, f"dismissed-cookie-banner:{label}"
        return False, str(parsed.get("reason") if parsed else "cookie-banner-dismiss-failed")

    async def js_click_verified(self, selectors: list[str], text_hints: list[str] | None, state_key: str) -> tuple[bool, str]:
        if not self._guard_clicks(state_key):
            return False, f"click cap reached for state={state_key}"
        page = await self.browser_session.get_current_page()
        if page is None:
            return False, "no-active-page"
        before = await self._snapshot()
        raw = await page.evaluate(
            """
            (p)=>{const sels=Array.isArray(p?.selectors)?p.selectors:[];const hints=Array.isArray(p?.text_hints)?p.text_hints:[];
              const n=(s)=>(s||'').toLowerCase().replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const t=(el)=>n(el.textContent||el.value||el.getAttribute('aria-label')||'');
              const c=(el)=>{if(!el)return false;try{el.scrollIntoView({block:'center',inline:'nearest'});}catch(e){}try{el.focus();}catch(e){}try{el.click();}catch(e){}try{el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,composed:true}));}catch(e){}return true;};
              for(const s of sels){try{for(const el of Array.from(document.querySelectorAll(s))){if(!v(el))continue;if(el.disabled||el.getAttribute('aria-disabled')==='true')continue;const tx=t(el);c(el);return {clicked:true,mode:'selector',text:tx};}}catch(e){}}
              if(hints.length){const hs=hints.map(n).filter(Boolean);for(const el of Array.from(document.querySelectorAll('button,a,[role=\"button\"],[role=\"link\"],input[type=\"submit\"],input[type=\"button\"],span'))){if(!v(el))continue;if(el.disabled||el.getAttribute('aria-disabled')==='true')continue;const tx=t(el);if(!hs.some((h)=>tx.includes(h)))continue;c(el);return {clicked:true,mode:'text',text:tx};}}
              return {clicked:false,reason:'not-found'};}\n
            """,
            {"selectors": selectors, "text_hints": text_hints or []},
        )
        raw_dict = self._as_dict(raw)
        if not raw_dict or not raw_dict.get("clicked"):
            return False, str(raw_dict.get("reason") if raw_dict else "click-failed")
        await asyncio.sleep(1.2)
        after = await self._snapshot()
        moved = str(before.get("url") or "") != str(after.get("url") or "")
        return True, f"{raw_dict.get('mode')}:{str(raw_dict.get('text') or '')[:80]} moved={moved}"

    async def js_set_input_react(self, selectors: list[str], value: str, label_hints: list[str] | None = None) -> tuple[bool, str]:
        page = await self.browser_session.get_current_page()
        if page is None:
            return False, "no-active-page"
        raw = await page.evaluate(
            """
            (p)=>{const sels=Array.isArray(p?.selectors)?p.selectors:[];const hints=Array.isArray(p?.label_hints)?p.label_hints:[];const val=String(p?.value||'');
              const n=(s)=>(s||'').toLowerCase().replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const d=(el)=>n([el.getAttribute('name')||'',el.getAttribute('id')||'',el.getAttribute('aria-label')||'',el.getAttribute('placeholder')||'',(el.labels&&el.labels[0]&&el.labels[0].textContent)||'',(el.parentElement&&el.parentElement.textContent)||''].join(' '));
              const set=(el)=>{try{el.scrollIntoView({block:'center',inline:'nearest'});}catch(e){}try{el.focus();}catch(e){}const tag=(el.tagName||'').toUpperCase();const setter=(tag==='TEXTAREA'?Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value'):Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value'))?.set;try{if(setter){setter.call(el,val);}else if('value' in el){el.value=val;}else{el.textContent=val;}}catch(e){return false;}try{el.dispatchEvent(new Event('input',{bubbles:true}));}catch(e){}try{el.dispatchEvent(new Event('change',{bubbles:true}));}catch(e){}try{el.dispatchEvent(new Event('blur',{bubbles:true}));}catch(e){}const after=n(('value' in el?el.value:el.textContent)||'');return after===n(val)||after.includes(n(val).slice(0,6));};
              const nodes=[];const push=(el)=>{if(!el||!v(el)||nodes.includes(el))return;nodes.push(el);};for(const s of sels){try{Array.from(document.querySelectorAll(s)).forEach(push);}catch(e){}}if(!nodes.length)Array.from(document.querySelectorAll('input,textarea')).forEach(push);
              const hs=hints.map(n).filter(Boolean);const ranked=nodes.map((el)=>{const desc=d(el);let score=0;for(const h of hs){if(desc.includes(h))score+=2;}return {el,desc,score};}).sort((a,b)=>b.score-a.score);
              for(const item of ranked){const type=n(item.el.getAttribute('type')||'');if(['hidden','checkbox','radio','file','submit','button'].includes(type))continue;if(set(item.el))return {success:true,descriptor:item.desc.slice(0,120)};}
              return {success:false,reason:'no-match'};}\n
            """,
            {"selectors": selectors, "label_hints": label_hints or [], "value": value},
        )
        raw_dict = self._as_dict(raw)
        if raw_dict and raw_dict.get("success"):
            return True, str(raw_dict.get("descriptor") or "set")
        return False, str(raw_dict.get("reason") if raw_dict else "set-failed")

    async def js_select_combobox(self, trigger_selectors: list[str], option_texts: list[str]) -> tuple[bool, str]:
        page = await self.browser_session.get_current_page()
        if page is None:
            return False, "no-active-page"
        raw = await page.evaluate(
            """
            (p)=>{const sels=Array.isArray(p?.trigger_selectors)?p.trigger_selectors:[];const opts=Array.isArray(p?.option_texts)?p.option_texts:[];
              const n=(s)=>(s||'').toLowerCase().replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const c=(el)=>{try{el.scrollIntoView({block:'center',inline:'nearest'});}catch(e){}try{el.click();}catch(e){}try{el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,composed:true}));}catch(e){}};
              const isPlaceholder=(text)=>{const t=n(text);return !t||t==='select one'||t==='choose one'||t==='please select'||t==='select'||t==='-- select --'||t==='search';};
              const read=(el)=>n(el.textContent||el.value||el.getAttribute&&el.getAttribute('aria-label')||'');
              let t=null;for(const s of sels){try{const x=Array.from(document.querySelectorAll(s)).find(v);if(x){t=x;break;}}catch(e){}}if(!t)return {success:false,reason:'trigger-not-found'};
              const before=read(t);c(t);
              const all=Array.from(document.querySelectorAll('[role=\"listbox\"] [role=\"option\"],[role=\"option\"],li[role=\"option\"],div[role=\"option\"],[data-automation-id*=\"menuItem\"]')).filter(v).map((el)=>({el,tx:read(el)})).filter((item)=>item.tx&&!isPlaceholder(item.tx)&&item.tx.length<=80);
              const desired=opts.map(n).filter(Boolean);
              for(const o of desired){const hit=all.find((item)=>item.tx===o||item.tx.includes(o)||o.includes(item.tx));if(hit){c(hit.el);const after=read(t);if(after&&!isPlaceholder(after)&&after!==before)return {success:true,value:after};return {success:true,value:hit.tx};}}
              const fallback=all.find((item)=>item.tx.split(' ').length<=8);
              if(fallback){c(fallback.el);const after=read(t);if(after&&!isPlaceholder(after)&&after!==before)return {success:true,value:after};return {success:true,value:fallback.tx,method:'fallback'};}
              return {success:false,reason:'option-not-found'};}\n
            """,
            {"trigger_selectors": trigger_selectors, "option_texts": option_texts},
        )
        raw_dict = self._as_dict(raw)
        if raw_dict and raw_dict.get("success"):
            return True, str(raw_dict.get("value") or "selected")
        return False, str(raw_dict.get("reason") if raw_dict else "select-failed")

    async def js_toggle_consent_checkbox(self) -> tuple[bool, str]:
        page = await self.browser_session.get_current_page()
        if page is None:
            return False, "no-active-page"
        raw = await page.evaluate(
            """
            ()=>{
              const n=(s)=>(s||'').toLowerCase().replace(/\\s+/g,' ').trim();
              const v=(el)=>{if(!el)return false;const st=getComputedStyle(el);if(st.display==='none'||st.visibility==='hidden')return false;const r=el.getBoundingClientRect();return r.width>0&&r.height>0;};
              const checked=(el)=>{if(!el)return false;const aria=n(el.getAttribute&&el.getAttribute('aria-checked')||'');if(aria==='true')return true;if(aria==='false')return false;return !!el.checked;};
              const click=(el)=>{if(!el)return false;try{el.scrollIntoView({block:'center',inline:'nearest'});}catch(e){}try{el.focus&&el.focus();}catch(e){}try{el.click();}catch(e){}try{el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,composed:true}));}catch(e){}return true;};
              const dispatch=(el)=>{if(!el)return;try{el.dispatchEvent(new Event('input',{bubbles:true}));}catch(e){}try{el.dispatchEvent(new Event('change',{bubbles:true}));}catch(e){}try{el.dispatchEvent(new Event('blur',{bubbles:true}));}catch(e){}};
              const keywords=['consent','agree','terms','privacy','read and consent','read and accept'];
              const scoreText=(text)=>{const t=n(text);let score=0;for(const k of keywords){if(t.includes(k))score+=2;}if(t.includes('yes'))score+=1;return score;};
              const describe=(el)=>n([
                el&&el.getAttribute&&el.getAttribute('name')||'',
                el&&el.getAttribute&&el.getAttribute('id')||'',
                el&&el.getAttribute&&el.getAttribute('aria-label')||'',
                (el&&el.labels&&el.labels[0]&&el.labels[0].textContent)||'',
                (el&&el.parentElement&&el.parentElement.textContent)||'',
                (el&&el.textContent)||'',
              ].join(' '));
              const resolveCheckbox=(node)=>{
                if(!node)return null;
                const role=n(node.getAttribute&&node.getAttribute('role')||'');
                const type=n(node.getAttribute&&node.getAttribute('type')||'');
                if(role==='checkbox'||type==='checkbox'||node.hasAttribute&&node.hasAttribute('aria-checked')) return node;
                if(node.tagName&&node.tagName.toLowerCase()==='label'){
                  const inside=node.querySelector('input[type="checkbox"],[role="checkbox"],[aria-checked]');
                  if(inside) return inside;
                  const forId=node.getAttribute('for');
                  if(forId){
                    const linked=document.getElementById(forId);
                    if(linked) return linked;
                  }
                }
                const near=node.closest&&node.closest('label,div,section,fieldset,form');
                if(near){
                  const nested=near.querySelector('input[type="checkbox"],[role="checkbox"],[aria-checked]');
                  if(nested) return nested;
                }
                return null;
              };

              const candidates=[];
              const seen=new Set();
              const push=(target,clickEl,hint,bonus=0)=>{
                if(!target)return;
                const key=(target.getAttribute&&target.getAttribute('id'))||target.outerHTML?.slice(0,120)||String(target);
                if(seen.has(key))return;
                seen.add(key);
                const text=describe(clickEl||target);
                const score=scoreText(text)+bonus;
                candidates.push({target,clickEl:clickEl||target,text,score});
              };

              for(const node of Array.from(document.querySelectorAll('input[type="checkbox"],[role="checkbox"],[aria-checked]'))){
                const target=resolveCheckbox(node) || node;
                push(target,node,'direct',v(node)?2:0);
              }

              const textNodes=Array.from(document.querySelectorAll('label,span,div,p,button,a')).filter(v).slice(0,240);
              for(const node of textNodes){
                const text=describe(node);
                if(!keywords.some((k)=>text.includes(k))) continue;
                const target=resolveCheckbox(node);
                if(target) push(target,node,'text-match',4);
              }

              candidates.sort((a,b)=>b.score-a.score);
              for(const item of candidates){
                if(checked(item.target)) return {success:true,note:'already_checked'};
                click(item.clickEl);
                click(item.target);
                dispatch(item.target);
                const parent=item.target.closest&&item.target.closest('label,div,section,fieldset,form');
                if(parent) click(parent);
                if(checked(item.target)) return {success:true,note:item.text.slice(0,120) || 'consent_checked'};
              }

              return {success:false,reason:'consent-checkbox-not-found-or-not-toggleable',candidate_count:candidates.length};
            }\n
            """
        )
        raw_dict = self._as_dict(raw)
        if raw_dict and raw_dict.get("success"):
            return True, str(raw_dict.get("note") or "consent-toggled")
        return False, str(raw_dict.get("reason") if raw_dict else "consent-toggle-failed")


async def run_workday_legacy_create_account(
    *,
    browser_session: Any,
    profile: dict[str, Any] | None,
    job_url: str,
    trace_hook=None,
) -> HandlerOutcome:
    handler = WorkdayHandler(
        browser_session=browser_session,
        profile=profile,
        job_url=job_url,
        trace_hook=trace_hook,
    )
    return await handler.run_legacy_create_account()
