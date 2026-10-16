"""Job Application Agent - Core automation logic using browser-use."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from dotenv import load_dotenv

load_dotenv()

from browser_use import Agent, Browser, BrowserProfile, ChatOpenAI
from .browser_use_overrides import apply_browser_use_overrides
from .legacy_credentials import account_password
from .platform_handlers import (
    HandlerResult,
    WORKDAY_EXISTING_DATA_CONFLICT_KEYWORDS,
    WORKDAY_EXPERIENCE_FIELD_LOOP_KEYWORDS,
    WORKDAY_REQUIRED_FIELD_LOOP_KEYWORDS,
    create_platform_handler,
    context_matches as workday_context_matches,
    detect_platform,
    env_flag,
    is_workday_url,
    month_year_from_value,
    safe_navigate,
)

# Ensure local browser-use overrides are active for this project runtime.
apply_browser_use_overrides()

# ---------------------------------------------------------------------------
# Reusable JS to auto-dismiss cookie/consent banners (OneTrust, Cookiebot, etc.)
# ---------------------------------------------------------------------------
COOKIE_DISMISS_JS = """() => {
    const normalize = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
    const isVisible = (el) => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };

    // Strategy 1: Known consent framework selectors
    const knownSelectors = [
        '#onetrust-accept-btn-handler',
        '.onetrust-close-btn-handler',
        '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
        '[data-testid="cookie-policy-dialog-accept-button"]',
        '.cc-btn.cc-allow',
        '#accept-cookie-notification',
        '.js-cookie-consent-agree',
        '[data-cookiefirst-action="accept"]',
    ];
    for (const sel of knownSelectors) {
        try {
            const btn = document.querySelector(sel);
            if (btn && isVisible(btn)) {
                btn.click();
                return { dismissed: true, method: 'known_selector', selector: sel };
            }
        } catch (e) {}
    }

    // Strategy 2: Buttons inside cookie/consent containers
    const candidates = document.querySelectorAll(
        'button, a, [role="button"], input[type="button"], input[type="submit"]'
    );
    const acceptPatterns = [
        'accept all', 'accept cookies', 'allow all', 'allow cookies',
        'agree', 'i agree', 'got it', 'accept and continue', 'i accept',
    ];
    for (const btn of candidates) {
        if (!isVisible(btn)) continue;
        const text = normalize(btn.textContent || btn.value || btn.getAttribute('aria-label') || '');
        if (text.length > 50) continue;
        let inBanner = false;
        let parent = btn;
        for (let i = 0; i < 8 && parent; i++) {
            const cls = (parent.className || '').toLowerCase();
            const id = (parent.id || '').toLowerCase();
            const role = (parent.getAttribute('role') || '').toLowerCase();
            if (/cookie|consent|gdpr|privacy|banner|notice/.test(cls + ' ' + id) ||
                role === 'dialog' || role === 'alertdialog') {
                inBanner = true; break;
            }
            parent = parent.parentElement;
        }
        if (inBanner && acceptPatterns.some(p => text.includes(p))) {
            btn.click();
            return { dismissed: true, method: 'banner_text', text: text.substring(0, 40) };
        }
    }

    // Strategy 3: Strict text match (no container requirement)
    for (const btn of candidates) {
        if (!isVisible(btn)) continue;
        const text = normalize(btn.textContent || btn.value || '');
        if (['accept all', 'accept all cookies', 'accept cookies', 'allow all cookies'].includes(text)) {
            btn.click();
            return { dismissed: true, method: 'strict_text', text: text };
        }
    }
    return { dismissed: false };
}"""


def _coerce_eval_dict(raw: Any) -> dict[str, Any]:
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


async def verify_submission(page: Any) -> dict[str, Any]:
    """Verify submission via DOM signals to avoid false applied statuses."""
    if page is None:
        return {"confirmed": False, "reason": "no-active-page"}
    try:
        raw = await page.evaluate(
            """() => {
                const normalize = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
                const url = normalize(location.href || '');
                const body = normalize((document.body && document.body.innerText) || '').slice(0, 12000);

                const urlConfirmed = [
                    '/confirmation', '/submitted', '/thank-you', '/thankyou',
                    '/success', '/complete', '/received'
                ].some((p) => url.includes(p));

                const textPatterns = [
                    'application submitted',
                    'application received',
                    'thank you for applying',
                    'successfully submitted',
                    'we have received your application',
                    'application has been submitted'
                ];
                const matchedText = textPatterns.find((p) => body.includes(p)) || '';

                const workdayContainer = !!document.querySelector(
                    '[data-automation-id="applicationConfirmation"],' +
                    '[data-automation-id*="applicationConfirmation"],' +
                    '[data-automation-id="thankYouMessage"],' +
                    '[data-automation-id*="thankYouMessage"],' +
                    '[data-automation-id="submittedApplication"],' +
                    '[data-automation-id*="submittedApplication"]'
                );

                const genericSuccessContainer = !!document.querySelector(
                    '[data-testid*="thank" i],' +
                    '[class*="thank-you" i],' +
                    '[id*="thank-you" i],' +
                    '[data-qa*="confirmation" i],' +
                    '[data-qa*="submitted" i]'
                );

                const hasErrors = !!document.querySelector(
                    'div[data-automation-id*="error"]:not([style*="display: none"]),' +
                    '[role="alert"]:not([style*="display: none"]),' +
                    '.error:where(:not([style*="display: none"])),' +
                    '.validation-error:where(:not([style*="display: none"]))'
                );

                const confirmed = (urlConfirmed || !!matchedText || workdayContainer || genericSuccessContainer) && !hasErrors;
                const method = urlConfirmed
                    ? 'url'
                    : matchedText
                        ? 'text'
                        : workdayContainer
                            ? 'workday_container'
                            : genericSuccessContainer
                                ? 'generic_container'
                                : 'none';
                return {
                    confirmed,
                    method,
                    final_url: location.href || '',
                    confirmation_text: matchedText,
                    workday_container: workdayContainer,
                    generic_container: genericSuccessContainer,
                    has_errors: hasErrors,
                };
            }"""
        )
        data = _coerce_eval_dict(raw)
        if not data:
            return {"confirmed": False, "reason": "invalid-eval-response"}
        data["confirmed"] = bool(data.get("confirmed"))
        return data
    except Exception as exc:
        return {"confirmed": False, "reason": f"verify_submission_failed:{exc}"}

class AutoFillingAgent(Agent):
    """
    Agent with pause/stop support and context-level stagnation warnings.
    """
    # Slot for pause/stop events, db_queue, job_id
    pause_event: Optional[asyncio.Event] = None
    stop_event: Optional[asyncio.Event] = None
    db_queue: Any = None
    job_id: str = ""
    _loop_stop_reason: Optional[str] = None
    _last_context_url: Optional[str] = None
    _url_unchanged_count: int = 0
    
    async def _prepare_context(self, step_info=None):
        # Stop check
        if self.stop_event and self.stop_event.is_set():
             self.state.stopped = True
             reason = self._loop_stop_reason or "Agent execution stopped by user"
             raise InterruptedError(reason)

        # Human-in-the-loop Pause
        if self.pause_event and not self.pause_event.is_set():
             print("â¸ï¸  Agent PAUSED. Waiting for user to Resume...")
             await self.pause_event.wait()
             print("â–¶ï¸  Agent RESUMED - Capturing fresh state.")
             if self.db_queue and self.job_id:
                 try:
                     self.db_queue.add_step(
                         job_id=self.job_id,
                         step_number=getattr(self, 'last_step_num', 0) + 1,
                         action_type="human_intervention",
                         element_description="Human resumed execution",
                         result="success",
                         step_memory="Human paused and resumed execution. State may have changed."
                     )
                 except: pass

        # Handle Stale Element Errors (Loop Prevention)
        last_history = getattr(self.history, "history", [])
        if last_history and last_history[-1].result:
            last_res = last_history[-1].result[-1]
            if last_res.error and "Element with index" in str(last_res.error) and "does not exist" in str(last_res.error):
                warning_msg = (
                    "SYSTEM ALERT: Previous action failed because the element index is invalid (stale). "
                    "The page has changed. DO NOT retry the same index. You MUST call check_page_state or scan_form_fields to refresh."
                )
                if self.state.last_model_output:
                    memory = self.state.last_model_output.memory or ""
                    if warning_msg not in memory:
                        self.state.last_model_output.memory = f"{memory}\n{warning_msg}".strip()

        current_url = ""
        try:
             current_url = await self.browser_session.get_current_page_url()
        except Exception:
             current_url = ""

        if current_url and current_url == self._last_context_url:
             self._url_unchanged_count += 1
        else:
             self._last_context_url = current_url
             self._url_unchanged_count = 1 if current_url else 0

        if self._url_unchanged_count >= 4 and self.state.last_model_output:
             warning = (
                 f"WARNING: Page has not changed for {self._url_unchanged_count} steps. "
                 "Your actions may not be having effect. Call check_page_state to diagnose."
             )
             memory = self.state.last_model_output.memory or ""
             if warning not in memory:
                 self.state.last_model_output.memory = f"{memory}\n{warning}".strip()

        # CAPTCHA detection: if page title suggests bot-check, stop early
        try:
            page = await self.browser_session.get_current_page()
            if page:
                title = await page.evaluate("() => document.title || ''")
                title_lower = str(title or "").lower()
                captcha_signals = ["just a moment", "security check", "verify you are human", "attention required"]
                if any(signal in title_lower for signal in captcha_signals) and self._url_unchanged_count >= 3:
                    self._loop_stop_reason = "CAPTCHA/bot-check detected. This site requires human verification."
                    self.state.stopped = True
                    raise InterruptedError(self._loop_stop_reason)
        except InterruptedError:
            raise
        except Exception:
            pass

        return await super()._prepare_context(step_info)


def build_application_task(
    profile: Dict[str, Any],
    job_url: str,
    job_title: Optional[str] = None,
    job_company: Optional[str] = None,
    resolved_resume_path: Optional[str] = None,
    credential_profile_path: Optional[Path] = None,
) -> str:
    """Build a comprehensive task prompt for job application."""
    
    identity = profile.get("identity", {})
    work_auth = profile.get("work_authorization", {})
    eeo = profile.get("eeo_information", {})
    standard_answers = profile.get("standard_answers", {})
    experience = profile.get("experience", [])
    education = profile.get("education", [])
    resume = profile.get("resume", {})
    accounts = profile.get("accounts", {})
    default_account = accounts.get("default", {}) if isinstance(accounts.get("default"), dict) else {}
    login_email = default_account.get("email", identity.get("email", ""))
    login_password = str(default_account.get("password", "") or "")
    login_password_display = login_password if login_password.strip() else "[NOT_PROVIDED]"
    profile_email = str(identity.get("email", "") or "").strip()
    fallback_account_password = account_password(profile, job_url, credential_profile_path or Path("profile.json"))

    # CRITICAL INSTRUCTIONS INJECTION
    critical_rules = """
CRITICAL RULES - READ THESE FIRST:
1. **COOKIE BANNERS**: Check for cookie banners/popups IMMEDIATELY. You MUST dismiss them before doing anything else.
   - If you see "Accept Cookies", "Agree", or "Close", click it FIRST.
   - If a banner blocks the "Apply" button, you WILL FAIL if you don't close it.
2. **LOGIN LOOPS**:
   - If you try to Create Account and it says "Account already exists" or "Email taken", SUSPEND CREATION immediately.
   - Switch to "Sign In" / "Log In" with the provided credentials.
   - DO NOT keep trying to create an account if it exists.
3. **STALE ELEMENTS**:
   - If an action fails with "Element with index X does not exist", DO NOT RETRY the same index.
   - Call `check_page_state` or `scan_form_fields` to refresh your view of the page.
   - The page has likely changed, and the old index is invalid.
4. **FILE UPLOADS**:
   - Use `upload_file` action directly. DO NOT click "Choose File" buttons.

"""
    if profile_email:
        critical_rules += f"""
5. **EMAIL LOCK**:
   - Always use this exact email when filling forms: {profile_email}
   - Never change the email domain or spelling.
"""
    if not login_password.strip():
        critical_rules += f"""
6. **NO SAVED LOGIN PASSWORD**:
   - The profile has no login password saved.
   - Do NOT attempt Sign In; use Create Account/Register flow unless account-exists is explicitly shown.
   - If account creation needs a password, use fallback `{fallback_account_password}` for both password fields.
"""
    
    # Build experience summary
    exp_summary = ""
    if experience:
        current = next((e for e in experience if e.get("current")), None)
        if current:
            exp_summary = f"Current role: {current.get('title')} at {current.get('company')} ({current.get('dates')})"
    
    # Build education summary
    edu_summary = ""
    if education:
        highest = education[0]  # Assuming sorted by recency
        edu_summary = f"Education: {highest.get('degree')} from {highest.get('institution')} ({highest.get('year')})"
    
    
    # Format the address string
    addr = identity.get('address', {})
    address_str = f"{addr.get('street', '')}, {addr.get('city', '')}, {addr.get('state', '')} {addr.get('zip', '')}"
    
    # Load instructions template
    try:
        template_path = Path("instructions.md")
        if not template_path.exists():
            # Try looking in the package root if running from elsewhere
            template_path = Path(__file__).parent.parent / "instructions.md"
        
        template = template_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error loading instructions.md: {e}. Please ensure the file exists."

    return template.format(
        critical_rules=critical_rules,
        job_url=job_url,
        job_title_line=f"Job Title: {job_title}" if job_title else "",
        company_line=f"Company: {job_company}" if job_company else "",
        
        # Identity
        full_name=identity.get('full_name', ''),
        first_name=identity.get('first_name', ''),
        last_name=identity.get('last_name', ''),
        email=identity.get('email', ''),
        phone=identity.get('phone', ''),
        address=address_str,
        linkedin=identity.get('linkedin', ''),
        website=identity.get('website', ''),
        
        # Work Auth
        wa_country=work_auth.get('country', 'United States'),
        wa_status=work_auth.get('status', ''),
        wa_authorized=work_auth.get('legally_authorized_us', True),
        wa_sponsorship=work_auth.get('needs_sponsorship', False),
        
        # EEO
        eeo_gender=eeo.get('gender', 'decline'),
        eeo_race=eeo.get('race_ethnicity', 'decline'),
        eeo_hispanic=eeo.get('hispanic_latino', 'decline'),
        eeo_veteran=eeo.get('veteran_status', 'decline'),
        eeo_disability=eeo.get('disability_status', 'decline'),
        
        # Standard Answers
        ans_authorized=standard_answers.get('authorized_to_work_us', True),
        ans_sponsorship=standard_answers.get('requires_sponsorship', True),
        ans_relocate=standard_answers.get('willing_to_relocate', True),
        ans_bg_check=standard_answers.get('background_check_consent', True),
        ans_age=standard_answers.get('age_18_or_older', True),
        ans_license=standard_answers.get('has_drivers_license', True),
        ans_felony=standard_answers.get('felony_conviction', False),
        ans_prev_applied=standard_answers.get('previously_applied', False),
        ans_prev_employed=standard_answers.get('previously_employed', False),
        
        # Experience & Education
        exp_summary=exp_summary,
        exp_years=profile.get('years_experience', ''),
        edu_summary=edu_summary,
        edu_highest=standard_answers.get('highest_education', ''),
        
        # Resume
        resume_path=resolved_resume_path or resume.get('path', ''),
        
        # Login
        login_email=login_email,
        login_password=login_password_display,
    )


class JobApplyAgent:
    """Agent for automating job applications using browser-use."""
    
    def __init__(
        self,
        profile_path: str = "./profile.json",
        artifacts_dir: str = "./artifacts",
        max_steps: int = 30,
        max_history_items: int = 7,
        llm_timeout: int = 180,
        step_timeout: int = 90,
        headless: bool = False,
        db_queue = None,  # Optional: JobQueueDB for step tracking
    ):
        self.profile_path = Path(profile_path)
        self.artifacts_dir = Path(artifacts_dir)
        self.max_steps = max_steps
        self.max_history_items = max_history_items
        self.llm_timeout = max(30, int(llm_timeout))
        self.step_timeout = max(15, int(step_timeout))
        self.headless = headless
        self.db_queue = db_queue
        self._profile: Optional[Dict[str, Any]] = None
        # Human-in-the-loop controls
        self.pause_event = asyncio.Event()
        self.pause_event.set() # Default to running

    def pause(self):
        """Pause the agent execution."""
        self.pause_event.clear()
        
    def resume(self):
        """Resume the agent execution."""
        self.pause_event.set()
    
    def load_profile(self) -> Dict[str, Any]:
        """Load user profile from JSON file."""
        if self._profile is None:
            if not self.profile_path.exists():
                raise FileNotFoundError(f"Profile not found: {self.profile_path}")
            self._profile = json.loads(self.profile_path.read_text(encoding="utf-8"))
        return self._profile
    
    def get_resume_path(self) -> Optional[str]:
        """Get the resume file path from profile."""
        profile = self.load_profile()
        resume_path = profile.get("resume", {}).get("path", "")
        if resume_path:
            # Resolve relative paths
            path = Path(resume_path)
            if not path.is_absolute():
                path = self.profile_path.parent / resume_path
            if path.exists():
                return str(path.resolve())
        return None

    @staticmethod
    def _artifact_folder_name(job_id: str, job_seq_id: Optional[int] = None) -> str:
        """Build deterministic artifact folder name."""
        if job_seq_id is not None:
            return f"job-{int(job_seq_id):05d}"
        return job_id
    
    async def apply(
        self,
        job_url: str,
        job_id: str,
        job_seq_id: Optional[int] = None,
        job_title: Optional[str] = None,
        job_company: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the job application process.
        
        Returns:
            Dict with keys:
            - status: "applied" | "needs_review" | "failed"
            - message: Human-readable result description
            - error: Error message if failed
            - intervention_reason: Why human intervention is needed (if applicable)
            - screenshot_path: Path to final screenshot
        """
        # Imports moved to top
        
        profile = {**self.load_profile(), '_legacy_credential_profile_path': str(self.profile_path.resolve())}
        resume_path = self.get_resume_path()
        
        # Create job-specific artifacts directory (numbered by seq_id when available)
        artifact_folder = self._artifact_folder_name(job_id=job_id, job_seq_id=job_seq_id)
        job_artifacts = self.artifacts_dir / artifact_folder
        job_artifacts.mkdir(parents=True, exist_ok=True)
        (job_artifacts / "job_meta.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "job_seq_id": job_seq_id,
                    "job_url": job_url,
                    "artifact_folder": artifact_folder,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        
        # Build the task prompt
        task = build_application_task(
            profile,
            job_url,
            job_title=job_title,
            job_company=job_company,
            resolved_resume_path=resume_path,
            credential_profile_path=self.profile_path,
        )
        
        # Save task for debugging
        (job_artifacts / "task_prompt.txt").write_text(task, encoding="utf-8")
        
        # Configure LLM
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            base_url=os.getenv("OPENAI_API_BASE"),
            api_key=os.getenv("OPENAI_API_KEY", "local"),
        )
        
        # Configure browser
        browser_profile = BrowserProfile(
            headless=self.headless,
            disable_security=True,  # Allow cross-origin iframes
        )
        # Optional: attach to an existing CDP browser (e.g. user's Brave)
        # instead of launching a fresh headless Chromium.
        cdp_url = os.getenv("BROWSER_USE_CDP_URL", "").strip()
        if cdp_url:
            browser_profile.cdp_url = cdp_url
            browser_profile.headless = False
        browser = Browser(browser_profile=browser_profile)
        
        # Prepare file paths for upload
        available_files = []
        if resume_path:
            available_files.append(resume_path)
        
        trace_file = None
        bu_logger = logging.getLogger("browser_use")
        bu_handler = None
        bu_previous_level = bu_logger.level
        
        try:
            trace_file = (job_artifacts / "trace.jsonl").open("a", encoding="utf-8")
            bu_handler = logging.FileHandler(str(job_artifacts / "browser_use.log"), encoding="utf-8")
            bu_handler.setLevel(logging.DEBUG)
            bu_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
            bu_logger.addHandler(bu_handler)
            if bu_logger.level > logging.DEBUG:
                bu_logger.setLevel(logging.DEBUG)
            from .element_handlers import create_job_applier_controller
            
            # Create extended controller with custom actions for dropdowns and uploads
            controller = create_job_applier_controller(profile, job_url=job_url)
            
            # ============================================================
            # Define Incremental Step Callback
            # ============================================================
            from .step_tracker import extract_action_summary, infer_action_type
            
            last_step_id = None
            last_step_number = None
            last_step_url = ""
            last_raw_action_key = ""
            action_fingerprints: list[str] = []
            last_action_fingerprint = ""
            repeat_streak = 0
            last_intent_fingerprint = ""
            intent_repeat_streak = 0
            recent_urls: list[str] = []
            previous_tab_ids: set[str] = set()
            url_tool_error_counts: dict[str, int] = {}
            recent_login_signals: list[str] = []
            login_fail_phrases = [
                "invalid email",
                "invalid password",
                "couldn't find an account",
                "login failed",
                "incorrect password",
                "authentication failed",
            ]
            stagnation_reason: Optional[str] = None
            checkbox_click_hint_issued = False
            checkbox_progress_hint_step: Optional[int] = None
            upload_progress_hint_issued = False
            consecutive_json_errors = 0
            workday_create_attempts = 0
            recovery_attempt_counts: dict[str, int] = {}
            platform_handlers_enabled = env_flag("JOB_APPLIER_PLATFORM_HANDLERS", True)
            workday_deterministic_enabled = env_flag("JOB_APPLIER_WORKDAY_DETERMINISTIC", True)
            # Dry-run: deterministic handler stops before Submit AND the LLM
            # fallback loop is disabled (it could otherwise click Submit).
            dry_run = env_flag("JOB_APPLIER_DRY_RUN", False)
            workday_fallback_llm_enabled = (not dry_run) and env_flag("JOB_APPLIER_WORKDAY_FALLBACK_LLM", True)
            use_vision = env_flag("JOB_APPLIER_USE_VISION", False)
            vision_detail_level = os.getenv("JOB_APPLIER_VISION_DETAIL", "low")
            detected_platform = detect_platform(job_url) if platform_handlers_enabled else "generic"
            active_platform_handler = None
            platform_handoff_context = ""
            platform_handler_steps: list[str] = []
            legacy_workday_recovery_enabled = not (
                platform_handlers_enabled and detected_platform in ("workday", "greenhouse")
            )
            identity_profile = profile.get("identity", {}) if isinstance(profile, dict) else {}
            if not isinstance(identity_profile, dict):
                identity_profile = {}
            address_profile = identity_profile.get("address", {})
            if not isinstance(address_profile, dict):
                address_profile = {}
            standard_answers_profile = profile.get("standard_answers", {}) if isinstance(profile, dict) else {}
            if not isinstance(standard_answers_profile, dict):
                standard_answers_profile = {}
            job_source_preferences_raw = standard_answers_profile.get("job_source_preference", [])
            if isinstance(job_source_preferences_raw, str):
                job_source_preferences = [job_source_preferences_raw]
            elif isinstance(job_source_preferences_raw, (list, tuple, set)):
                job_source_preferences = list(job_source_preferences_raw)
            else:
                job_source_preferences = []
            # Build generic referral candidates from profile data (no employer-specific literals).
            referral_candidates: list[str] = []
            seen_referral_values: set[str] = set()
            generic_referral_fallbacks = [
                "Other",
                "Job Board",
                "Online Job Board",
                "Company Website",
                "Recruiter",
            ]
            for candidate in [
                *generic_referral_fallbacks,
                standard_answers_profile.get("job_source", ""),
                *job_source_preferences,
                "LinkedIn",
            ]:
                value = str(candidate or "").strip()
                if not value:
                    continue
                lowered = value.lower()
                if lowered in seen_referral_values:
                    continue
                seen_referral_values.add(lowered)
                referral_candidates.append(value)
            accounts_profile = profile.get("accounts", {}) if isinstance(profile, dict) else {}
            if not isinstance(accounts_profile, dict):
                accounts_profile = {}
            default_account_profile = accounts_profile.get("default", {})
            if not isinstance(default_account_profile, dict):
                default_account_profile = {}
            has_saved_login_password = bool(str(default_account_profile.get("password", "") or "").strip())
            account_password_value = account_password(profile, job_url, self.profile_path)
            experience_profile = profile.get("experience", []) if isinstance(profile, dict) else []
            if not isinstance(experience_profile, list):
                experience_profile = []
            primary_experience = next(
                (
                    item for item in experience_profile
                    if isinstance(item, dict) and item.get("current")
                ),
                None,
            )
            if primary_experience is None:
                primary_experience = next(
                    (item for item in experience_profile if isinstance(item, dict)),
                    {},
                )
            if not isinstance(primary_experience, dict):
                primary_experience = {}

            experience_from_hint = month_year_from_value(primary_experience.get("start_date", ""))
            experience_to_hint = month_year_from_value(primary_experience.get("end_date", ""))
            if not experience_from_hint:
                experience_from_hint = "01/2023"
            if not experience_to_hint:
                experience_to_hint = datetime.utcnow().strftime("%m/%Y")
            highlights_raw = primary_experience.get("highlights", [])
            if isinstance(highlights_raw, str):
                highlights = [highlights_raw]
            elif isinstance(highlights_raw, (list, tuple, set)):
                highlights = [str(item).strip() for item in highlights_raw if str(item).strip()]
            else:
                highlights = []
            role_description_hint = (
                " ".join(highlights[:2]).strip()
                or str(profile.get("summary", "") or "").strip()
                or "Led cross-functional data and analytics initiatives."
            )
            if len(role_description_hint) > 360:
                role_description_hint = role_description_hint[:357].rstrip() + "..."
            skills_raw = profile.get("skills", []) if isinstance(profile, dict) else []
            if isinstance(skills_raw, str):
                skill_values = [skills_raw.strip()]
            elif isinstance(skills_raw, (list, tuple, set)):
                skill_values = [str(item).strip() for item in skills_raw if str(item).strip()]
            else:
                skill_values = []
            experience_skills_hint = ", ".join(skill_values[:5])
            if len(experience_skills_hint) > 180:
                experience_skills_hint = experience_skills_hint[:177].rstrip() + "..."

            def normalize_text(value: str) -> str:
                return " ".join(str(value or "").lower().split())

            def normalize_url(url: str) -> str:
                clean = str(url or "").strip()
                if not clean:
                    return ""
                try:
                    parsed = urlparse(clean)
                    if parsed.scheme and parsed.netloc:
                        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path}"
                except Exception:
                    pass
                return clean

            def canonicalize_error_text(error_value: Any) -> str:
                text = str(error_value or "")
                if not text:
                    return ""
                if "Invalid JSON" in text:
                    return "LLM output truncated (JSON parse failure). Keep responses shorter."
                text = " ".join(text.split())
                if len(text) > 320:
                    return text[:317] + "..."
                return text

            def build_action_fingerprint(raw_action_key: str, action_payload: dict[str, Any], page_url: str) -> str:
                parts = [normalize_text(raw_action_key or "unknown"), normalize_url(page_url)]
                if isinstance(action_payload, dict):
                    for key in sorted(action_payload.keys()):
                        if str(key).startswith("_"):
                            continue
                        value = action_payload.get(key)
                        if key == "path":
                            value = os.path.basename(str(value or ""))
                        elif isinstance(value, (dict, list)):
                            value = json.dumps(value, sort_keys=True, default=str)
                        parts.append(f"{key}={value}")
                return "|".join(parts)

            def normalize_desc_for_intent(description_value: str) -> str:
                text = str(description_value or "")
                if not text:
                    return ""
                # Strip volatile element numbers (e.g., "Clicked element #1234").
                text = re.sub(r"#\d+", "#", text)
                return normalize_text(text)

            def build_intent_fingerprint(action_type_value: str, page_url: str, next_goal_value: str, description_value: str) -> str:
                goal = normalize_text(next_goal_value or "")
                desc = normalize_desc_for_intent(description_value or "")
                anchor = goal or desc
                if len(anchor) > 220:
                    anchor = anchor[:220]
                return "|".join(
                    [
                        normalize_text(action_type_value or "unknown"),
                        normalize_url(page_url),
                        anchor,
                    ]
                )

            def register_recovery_attempt(marker: str, max_attempts: int = 3) -> tuple[bool, int]:
                count = recovery_attempt_counts.get(marker, 0)
                if count >= max_attempts:
                    return False, count
                count += 1
                recovery_attempt_counts[marker] = count
                return True, count

            def upsert_memory_line(memory_text: str, prefix: str, message: str, max_chars: int = 220) -> str:
                compact = " ".join(str(message or "").split())
                if len(compact) > max_chars:
                    compact = compact[: max_chars - 3] + "..."
                kept_lines = [
                    line for line in str(memory_text or "").splitlines()
                    if not line.strip().startswith(prefix)
                ]
                kept_lines.append(f"{prefix} {compact}".strip())
                return "\n".join(line for line in kept_lines if line.strip())

            def is_url_likely_corrupted(raw_url: str) -> bool:
                value = str(raw_url or "").lower()
                if not value:
                    return False
                # Guard against LLM-emitted JSON tail artifacts appended to query strings.
                suspicious_markers = ("%7d%7d%5d", "%7d%5d", "}}]", "%5d%7d")
                return any(marker in value for marker in suspicious_markers)

            def has_off_task_signals(*texts: str) -> bool:
                combined = normalize_text(" ".join(str(t or "") for t in texts))
                if not combined:
                    return False
                signals = (
                    "laptop comparison",
                    "target websites",
                    "pricing data",
                    "amazon",
                    "ebay",
                    "walmart",
                    "best buy",
                    "shopping cart",
                    "coupon",
                )
                hits = sum(1 for signal in signals if signal in combined)
                return hits >= 2

            async def collect_page_diagnostics() -> str:
                try:
                    page = await agent.browser_session.get_current_page()
                    if page is None:
                        return "no active page detected"
                    diag = await page.evaluate(
                        """
                        () => {
                            const isVisible = (el) => {
                                if (!el) return false;
                                const s = window.getComputedStyle(el);
                                if (!s) return false;
                                if (s.display === 'none' || s.visibility === 'hidden') return false;
                                const r = el.getBoundingClientRect();
                                return r.width > 0 && r.height > 0;
                            };

                            const out = [];
                            const push = (text) => {
                                const clean = String(text || '').replace(/\\s+/g, ' ').trim();
                                if (!clean) return;
                                if (!out.includes(clean)) out.push(clean.slice(0, 120));
                            };

                            const errorSelectors = [
                                '[class*="error"]',
                                '[class*="invalid"]',
                                '[role="alert"]',
                                '[aria-invalid="true"]',
                                '.validation-error',
                                '.field-error',
                                '.form-error'
                            ];
                            for (const selector of errorSelectors) {
                                for (const el of Array.from(document.querySelectorAll(selector)).slice(0, 30)) {
                                    if (!isVisible(el)) continue;
                                    const text = el.textContent || '';
                                    if (text.trim().length > 2) push(`error: ${text}`);
                                    if (out.length >= 4) break;
                                }
                                if (out.length >= 4) break;
                            }

                            const ctaWords = ['submit', 'next', 'continue', 'apply', 'create account', 'autofill'];
                            for (const btn of Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"]')).slice(0, 80)) {
                                if (!isVisible(btn)) continue;
                                const text = (btn.textContent || btn.value || '').toLowerCase();
                                if (!ctaWords.some(word => text.includes(word))) continue;
                                const disabled = !!btn.disabled || btn.getAttribute('aria-disabled') === 'true';
                                if (disabled) {
                                    push(`disabled cta: ${text.slice(0, 40)}`);
                                    break;
                                }
                            }

                            for (const overlay of Array.from(document.querySelectorAll('[role="dialog"], [class*="modal"], [class*="overlay"]')).slice(0, 40)) {
                                if (!isVisible(overlay)) continue;
                                const r = overlay.getBoundingClientRect();
                                if (r.width >= 120 && r.height >= 120) {
                                    push('overlay/dialog visible');
                                    break;
                                }
                            }

                            let requiredEmpty = 0;
                            for (const field of Array.from(document.querySelectorAll('input, select, textarea')).slice(0, 400)) {
                                if (!isVisible(field)) continue;
                                if (!(field.required || field.getAttribute('aria-required') === 'true')) continue;
                                const type = (field.getAttribute('type') || '').toLowerCase();
                                if (type === 'checkbox' || type === 'radio') {
                                    if (!field.checked) requiredEmpty += 1;
                                } else if (!String(field.value || '').trim()) {
                                    requiredEmpty += 1;
                                }
                            }
                            if (requiredEmpty > 0) push(`empty required fields: ${requiredEmpty}`);

                            return out.slice(0, 4);
                        }
                        """
                    )
                    if isinstance(diag, list) and diag:
                        return "; ".join(str(item) for item in diag[:4])
                    return "no visible errors/disabled ctas/overlays; try different action or element"
                except Exception:
                    return "diagnostics unavailable; try scan_form_fields or check_page_state"

            async def attempt_targeted_recovery(page_url: str, combined_context: str) -> tuple[bool, str, str]:
                nonlocal stagnation_reason
                nonlocal platform_handoff_context
                ctx = normalize_text(combined_context)
                raw_url_value = str(page_url or "")
                url_value = normalize_url(page_url)

                if active_platform_handler is not None:
                    marker = "platform_handler_recover"
                    allowed, attempt_no = register_recovery_attempt(marker, max_attempts=8)
                    if allowed:
                        outcome = await active_platform_handler.recover(
                            {
                                "url": page_url,
                                "context": combined_context,
                                "detected_platform": detected_platform,
                                "step": len(action_fingerprints) + 1,
                            }
                        )
                        if outcome.handoff_context:
                            platform_handoff_context = outcome.handoff_context
                        if outcome.steps:
                            platform_handler_steps.extend(outcome.steps)
                        if outcome.result in {HandlerResult.PROGRESSED, HandlerResult.SUBMITTED}:
                            return True, f"Platform recovery #{attempt_no}: {outcome.message}", marker
                        if outcome.result == HandlerResult.BLOCKED:
                            return False, f"Platform helper needs executor recovery ({outcome.blocker_code or 'blocked'}): {outcome.message}. Inspect a fresh screenshot and remaining controls/options.", marker
                        if outcome.result == HandlerResult.FAILED:
                            return False, f"Platform recovery #{attempt_no} failed: {outcome.message}", marker

                # Generic: if URL gets polluted with model-output artifacts, hard reset to the target URL.
                if is_url_likely_corrupted(raw_url_value):
                    marker = "url_noise_reset_to_target"
                    allowed, attempt_no = register_recovery_attempt(marker, max_attempts=3)
                    if allowed:
                        page = await agent.browser_session.get_current_page()
                        if page is not None:
                            ok, nav_reason = await safe_navigate(page, job_url)
                            if ok:
                                return True, f"URL recovery #{attempt_no}: reset navigation to original job URL.", marker
                            return False, f"URL recovery #{attempt_no} failed to reset URL: {nav_reason}", marker

                # Generic login loops: pivot away from blind Sign In retries.
                if any(
                    key in ctx
                    for key in (
                        "sign in",
                        "log in",
                        "login",
                        "password",
                        "couldn't find an account",
                        "invalid password",
                    )
                ):
                    marker = "login_loop_pivot"
                    allowed, attempt_no = register_recovery_attempt(marker, max_attempts=4)
                    if allowed:
                        page = await agent.browser_session.get_current_page()
                        if page is None:
                            return False, "No active page for login loop recovery.", marker
                        raw = await page.evaluate(
                            """
                            () => {
                                const normalize = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
                                const isVisible = (el) => {
                                    if (!el) return false;
                                    const st = window.getComputedStyle(el);
                                    if (!st) return false;
                                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                                    const r = el.getBoundingClientRect();
                                    return r.width > 0 && r.height > 0;
                                };
                                const clickNode = (el) => {
                                    if (!el) return false;
                                    try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                                    try { el.click(); } catch (e) {}
                                    try { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })); } catch (e) {}
                                    return true;
                                };
                                const textOf = (el) => normalize(
                                    (el && (el.textContent || el.value || (el.getAttribute && el.getAttribute('aria-label')) || '')) || ''
                                );

                                const bodyText = normalize((document.body && document.body.innerText) || '');
                                const captchaSignals = ['captcha', 'verify you are human', 'security check', 'just a moment'];
                                if (captchaSignals.some((signal) => bodyText.includes(signal))) {
                                    return { success: true, action: 'captcha_detected', reason: 'captcha_or_bot_check' };
                                }

                                const createAccountNodes = Array.from(
                                    document.querySelectorAll('a, button, [role=\"button\"], [role=\"link\"], span')
                                )
                                    .filter(isVisible)
                                    .map((el) => ({ el, text: textOf(el) }))
                                    .filter((item) => item.text && (
                                        item.text.includes('create account') ||
                                        item.text.includes('create an account') ||
                                        item.text.includes('register') ||
                                        item.text.includes('sign up') ||
                                        item.text.includes('new user') ||
                                        item.text.includes(\"don't have an account\")
                                    ));
                                if (createAccountNodes.length) {
                                    const picked = createAccountNodes[0];
                                    clickNode(picked.el);
                                    return { success: true, action: 'create_account_path', text: picked.text.slice(0, 80) };
                                }

                                const signInNodes = Array.from(
                                    document.querySelectorAll('button, [role=\"button\"], input[type=\"submit\"]')
                                )
                                    .filter(isVisible)
                                    .map((el) => ({ el, text: textOf(el) }))
                                    .filter((item) => item.text && (
                                        item.text === 'sign in' ||
                                        item.text.includes('log in') ||
                                        item.text.includes('sign in')
                                    ))
                                    .filter((item) => !(item.el.disabled || item.el.getAttribute('aria-disabled') === 'true'));
                                if (signInNodes.length) {
                                    const picked = signInNodes[0];
                                    clickNode(picked.el);
                                    try {
                                        const form = picked.el.closest('form');
                                        if (form) {
                                            form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
                                        }
                                    } catch (e) {}
                                    return { success: true, action: 'resubmit_login', text: picked.text.slice(0, 80) };
                                }

                                return { success: false, reason: 'no_alternate_login_path' };
                            }
                            """
                        )
                        parsed_raw = raw
                        if isinstance(parsed_raw, str):
                            try:
                                parsed_raw = json.loads(parsed_raw)
                            except Exception:
                                parsed_raw = raw
                        if isinstance(parsed_raw, dict) and parsed_raw.get("success"):
                            action = str(parsed_raw.get("action") or "")
                            if action == "captcha_detected":
                                return True, f"Login recovery #{attempt_no}: CAPTCHA/bot-check detected; stop blind retries and request manual review.", marker
                            if action == "create_account_path":
                                return True, f"Login recovery #{attempt_no}: pivoted to create-account path.", marker
                            return True, f"Login recovery #{attempt_no}: retried login with form-submit fallback.", marker
                        return False, f"Login recovery #{attempt_no} attempted but not verified: {parsed_raw}", marker

                # Workday: if redirected to userHome while trying to apply, return to the job/apply context.
                if legacy_workday_recovery_enabled and is_workday_url(url_value) and "/careers/userhome" in url_value:
                    marker = "workday_userhome_return_to_job"
                    allowed, attempt_no = register_recovery_attempt(marker, max_attempts=6)
                    if allowed:
                        try:
                            pages = list(getattr(agent.browser_session.browser_context, "pages", []) or [])
                            for candidate_page in reversed(pages):
                                candidate_url = normalize_url(getattr(candidate_page, "url", ""))
                                if not is_workday_url(candidate_url):
                                    continue
                                if "/careers/job/" in candidate_url or "/apply/" in candidate_url:
                                    await candidate_page.bring_to_front()
                                    return True, f"Workday recovery #{attempt_no}: switched focus back to job/apply tab.", marker
                        except Exception:
                            pass
                        page = await agent.browser_session.get_current_page()
                        if page is not None:
                            ok, nav_reason = await safe_navigate(page, job_url)
                            if ok:
                                return True, f"Workday recovery #{attempt_no}: navigated back to target job URL.", marker
                            return False, f"Workday recovery #{attempt_no} failed to navigate back to job URL: {nav_reason}", marker

                # Workday: sometimes auth/redirect lands on generic career-search page; jump back to target job/apply URL.
                if (
                    legacy_workday_recovery_enabled
                    and
                    is_workday_url(url_value)
                    and "/job/" not in url_value
                    and "/apply/" not in url_value
                    and any(signal in ctx for signal in ("search for jobs", "careers at", "job listing"))
                ):
                    marker = "workday_search_return_to_job"
                    allowed, attempt_no = register_recovery_attempt(marker, max_attempts=6)
                    if allowed:
                        target_url = job_url
                        try:
                            parsed = urlparse(raw_url_value or page_url or "")
                            redirect_qs = parse_qs(parsed.query or "")
                            redirect_value = str((redirect_qs.get("redirect") or [""])[0] or "").strip()
                            if redirect_value:
                                redirect_value = unquote(redirect_value)
                                if redirect_value.startswith("http://") or redirect_value.startswith("https://"):
                                    target_url = redirect_value
                                elif parsed.scheme and parsed.netloc and redirect_value.startswith("/"):
                                    target_url = f"{parsed.scheme}://{parsed.netloc}{redirect_value}"
                        except Exception:
                            target_url = job_url

                        page = await agent.browser_session.get_current_page()
                        if page is not None:
                            ok, nav_reason = await safe_navigate(page, target_url)
                            if ok:
                                return True, f"Workday recovery #{attempt_no}: navigated from search page back to target URL.", marker
                            return False, f"Workday recovery #{attempt_no} failed to leave search page: {nav_reason}", marker

                # Generic consent-checkbox loops: avoid endless re-toggling on account/forms pages.
                if any(
                    key in ctx
                    for key in (
                        "toggle checkbox",
                        "checkbox",
                        "consent",
                        "terms",
                        "privacy policy",
                        "please check the box",
                        "must be checked",
                        "read and accept",
                    )
                ) and "/careers/userhome" not in url_value:
                    marker = "consent_checkbox_submit"
                    allowed, attempt_no = register_recovery_attempt(marker, max_attempts=4)
                    if allowed:
                        page = await agent.browser_session.get_current_page()
                        if page is None:
                            return False, "No active page for consent checkbox recovery.", marker
                        raw = await page.evaluate(
                            """
                            () => {
                            const normalize = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
                            const isVisible = (el) => {
                                if (!el) return false;
                                const st = window.getComputedStyle(el);
                                if (!st) return false;
                                if (st.display === 'none' || st.visibility === 'hidden') return false;
                                const r = el.getBoundingClientRect();
                                return r.width > 0 && r.height > 0;
                            };
                            const clickNode = (el) => {
                                if (!el) return false;
                                try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                                try { el.click(); } catch (e) {}
                                try { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })); } catch (e) {}
                                return true;
                            };
                            const getChecked = (el) => {
                                if (!el) return null;
                                const aria = normalize(el.getAttribute && el.getAttribute('aria-checked'));
                                if (aria === 'true') return true;
                                if (aria === 'false') return false;
                                if ('checked' in el) return !!el.checked;
                                return null;
                            };
                            const descriptor = (el) => normalize([
                                el.getAttribute && (el.getAttribute('name') || ''),
                                el.getAttribute && (el.getAttribute('id') || ''),
                                el.getAttribute && (el.getAttribute('aria-label') || ''),
                                (el.labels && el.labels[0] && el.labels[0].textContent) || '',
                                (el.parentElement && el.parentElement.textContent) || '',
                            ].join(' '));
                            const consentScore = (el) => {
                                const text = descriptor(el);
                                let score = 0;
                                if (text.includes('consent')) score += 3;
                                if (text.includes('term')) score += 3;
                                if (text.includes('privacy')) score += 2;
                                if (text.includes('agree')) score += 2;
                                if (text.includes('read')) score += 1;
                                if (el.required || el.getAttribute('aria-required') === 'true') score += 2;
                                return score;
                            };

                            const checkboxes = Array.from(
                                document.querySelectorAll('input[type=\"checkbox\"], [role=\"checkbox\"], [aria-checked]')
                            )
                                .filter(isVisible)
                                .map((el) => ({ el, score: consentScore(el) }))
                                .sort((a, b) => b.score - a.score)
                                .slice(0, 8);

                            let changed = 0;
                            for (const item of checkboxes) {
                                const el = item.el;
                                const before = getChecked(el);
                                if (before === true) continue;
                                if (el.tagName === 'INPUT' && (el.getAttribute('type') || '').toLowerCase() === 'checkbox') {
                                    try { el.checked = true; } catch (e) {}
                                }
                                if (el.getAttribute && el.getAttribute('aria-checked') !== null) {
                                    try { el.setAttribute('aria-checked', 'true'); } catch (e) {}
                                }
                                try { el.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                                try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                                clickNode(el);
                                const after = getChecked(el);
                                if (after === true) changed += 1;
                            }

                            let clickedCta = false;
                            let ctaText = '';
                            const ctaCandidates = Array.from(
                                document.querySelectorAll('button, [role=\"button\"], input[type=\"submit\"], input[type=\"button\"]')
                            )
                                .filter(isVisible)
                                .map((el) => ({ el, text: normalize(el.textContent || el.value || el.getAttribute('aria-label') || '') }))
                                .filter((item) => item.text && (item.text.includes('create account') || item.text.includes('continue') || item.text.includes('submit') || item.text.includes('next') || item.text.includes('apply')))
                                .filter((item) => !(item.el.disabled || item.el.getAttribute('aria-disabled') === 'true'));
                            if (ctaCandidates.length) {
                                const best = ctaCandidates[0];
                                ctaText = best.text.slice(0, 80);
                                clickedCta = clickNode(best.el);
                            }

                            return {
                                success: !!(changed > 0 || clickedCta),
                                changed_count: changed,
                                clicked_cta: !!clickedCta,
                                cta_text: ctaText,
                            };
                            }
                            """
                        )
                        parsed_raw = raw
                        if isinstance(parsed_raw, str):
                            try:
                                parsed_raw = json.loads(parsed_raw)
                            except Exception:
                                parsed_raw = raw
                        if isinstance(parsed_raw, dict) and parsed_raw.get("success"):
                            return True, f"Consent recovery #{attempt_no}: forced checkbox state and attempted CTA.", marker
                        return False, f"Consent recovery #{attempt_no} attempted but not verified: {parsed_raw}", marker

                # Generic invalid-email loops: force profile email into visible email fields.
                if any(
                    key in ctx
                    for key in (
                        "invalid email",
                        "valid email",
                        "email is invalid",
                        "please enter a valid email",
                    )
                ):
                    target_email = str(identity_profile.get("email", "") or "").strip()
                    if target_email:
                        marker = "email_field_profile_lock"
                        allowed, attempt_no = register_recovery_attempt(marker, max_attempts=4)
                        if not allowed:
                            return False, f"Email recovery already attempted {attempt_no} times in this run.", marker
                        page = await agent.browser_session.get_current_page()
                        if page is None:
                            return False, "No active page for email recovery.", marker
                        raw = await page.evaluate(
                            """
                            (payload) => {
                                const normalize = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
                                const isVisible = (el) => {
                                    if (!el) return false;
                                    const st = window.getComputedStyle(el);
                                    if (!st) return false;
                                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                                    const r = el.getBoundingClientRect();
                                    return r.width > 0 && r.height > 0;
                                };
                                const clickNode = (el) => {
                                    if (!el) return false;
                                    try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                                    try { el.click(); } catch (e) {}
                                    return true;
                                };
                                const descriptor = (el) => normalize([
                                    el.getAttribute && (el.getAttribute('type') || ''),
                                    el.getAttribute && (el.getAttribute('name') || ''),
                                    el.getAttribute && (el.getAttribute('id') || ''),
                                    el.getAttribute && (el.getAttribute('aria-label') || ''),
                                    el.getAttribute && (el.getAttribute('placeholder') || ''),
                                    (el.labels && el.labels[0] && el.labels[0].textContent) || '',
                                    (el.parentElement && el.parentElement.textContent) || '',
                                ].join(' '));
                                const value = String(payload?.email || '').trim();
                                if (!value) return { success: false, reason: 'missing_profile_email' };

                                const fields = Array.from(document.querySelectorAll('input[type=\"email\"], input'))
                                    .filter(isVisible)
                                    .filter((el) => {
                                        const d = descriptor(el);
                                        return d.includes('email');
                                    })
                                    .slice(0, 10);
                                let setCount = 0;
                                for (const field of fields) {
                                    try { field.focus(); } catch (e) {}
                                    clickNode(field);
                                    try { field.value = ''; } catch (e) {}
                                    try { field.value = value; } catch (e) {}
                                    try { field.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                                    try { field.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                                    try { field.dispatchEvent(new Event('blur', { bubbles: true })); } catch (e) {}
                                    const current = String(field.value || '').trim().toLowerCase();
                                    if (current === value.toLowerCase()) setCount += 1;
                                }

                                let clickedCta = false;
                                let ctaText = '';
                                const ctaCandidates = Array.from(
                                    document.querySelectorAll('button, [role=\"button\"], input[type=\"submit\"], input[type=\"button\"]')
                                )
                                    .filter(isVisible)
                                    .map((el) => ({ el, text: normalize(el.textContent || el.value || el.getAttribute('aria-label') || '') }))
                                    .filter((item) => item.text && (item.text.includes('create account') || item.text.includes('sign in') || item.text.includes('continue') || item.text.includes('submit') || item.text.includes('next')))
                                    .filter((item) => !(item.el.disabled || item.el.getAttribute('aria-disabled') === 'true'));
                                if (ctaCandidates.length) {
                                    const best = ctaCandidates[0];
                                    ctaText = best.text.slice(0, 80);
                                    clickedCta = clickNode(best.el);
                                }

                                return {
                                    success: !!(setCount > 0),
                                    fields_set: setCount,
                                    clicked_cta: !!clickedCta,
                                    cta_text: ctaText,
                                };
                            }
                            """,
                            {"email": target_email},
                        )
                        parsed_raw = raw
                        if isinstance(parsed_raw, str):
                            try:
                                parsed_raw = json.loads(parsed_raw)
                            except Exception:
                                parsed_raw = raw
                        if isinstance(parsed_raw, dict) and parsed_raw.get("success"):
                            return True, f"Email recovery #{attempt_no}: restored profile email in visible fields.", marker
                        return False, f"Email recovery #{attempt_no} attempted but not verified: {parsed_raw}", marker

                # Generic password mismatch loops: force password/confirm fields to one canonical value.
                if any(
                    key in ctx
                    for key in (
                        "passwords do not match",
                        "password mismatch",
                        "verify new password",
                        "confirm password",
                    )
                ):
                    marker = "password_fields_realign"
                    allowed, attempt_no = register_recovery_attempt(marker, max_attempts=5)
                    if allowed:
                        page = await agent.browser_session.get_current_page()
                        if page is None:
                            return False, "No active page for password recovery.", marker
                        raw = await page.evaluate(
                            """
                            (payload) => {
                                const normalize = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
                                const isVisible = (el) => {
                                    if (!el) return false;
                                    const st = window.getComputedStyle(el);
                                    if (!st) return false;
                                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                                    const r = el.getBoundingClientRect();
                                    return r.width > 0 && r.height > 0;
                                };
                                const descriptor = (el) => normalize([
                                    el.getAttribute && (el.getAttribute('type') || ''),
                                    el.getAttribute && (el.getAttribute('name') || ''),
                                    el.getAttribute && (el.getAttribute('id') || ''),
                                    el.getAttribute && (el.getAttribute('aria-label') || ''),
                                    el.getAttribute && (el.getAttribute('placeholder') || ''),
                                    (el.labels && el.labels[0] && el.labels[0].textContent) || '',
                                    (el.parentElement && el.parentElement.textContent) || '',
                                ].join(' '));
                                const clickNode = (el) => {
                                    if (!el) return false;
                                    try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                                    try { el.click(); } catch (e) {}
                                    return true;
                                };

                                const value = String(payload?.password || '').trim();
                                if (!value) return { success: false, reason: 'missing_password_value' };

                                const fields = Array.from(document.querySelectorAll('input[type=\"password\"], input'))
                                    .filter(isVisible)
                                    .filter((el) => descriptor(el).includes('password'))
                                    .slice(0, 8);
                                if (!fields.length) return { success: false, reason: 'no_password_fields' };

                                // Fill confirm/verify fields first, then primary password fields.
                                fields.sort((a, b) => {
                                    const da = descriptor(a);
                                    const db = descriptor(b);
                                    const aConfirm = (da.includes('verify') || da.includes('confirm')) ? 1 : 0;
                                    const bConfirm = (db.includes('verify') || db.includes('confirm')) ? 1 : 0;
                                    return bConfirm - aConfirm;
                                });

                                let setCount = 0;
                                const observed = [];
                                for (const field of fields) {
                                    try { field.focus(); } catch (e) {}
                                    clickNode(field);
                                    try { field.value = ''; } catch (e) {}
                                    try { field.value = value; } catch (e) {}
                                    try { field.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                                    try { field.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                                    try { field.dispatchEvent(new Event('blur', { bubbles: true })); } catch (e) {}
                                    const current = String(field.value || '');
                                    observed.push(current);
                                    if (current === value) setCount += 1;
                                }

                                let clickedCta = false;
                                let ctaText = '';
                                const ctaCandidates = Array.from(
                                    document.querySelectorAll('button, [role=\"button\"], input[type=\"submit\"], input[type=\"button\"]')
                                )
                                    .filter(isVisible)
                                    .map((el) => ({ el, text: normalize(el.textContent || el.value || el.getAttribute('aria-label') || '') }))
                                    .filter((item) => item.text && (item.text.includes('create account') || item.text.includes('continue') || item.text.includes('submit') || item.text.includes('next')))
                                    .filter((item) => !(item.el.disabled || item.el.getAttribute('aria-disabled') === 'true'));
                                if (ctaCandidates.length) {
                                    const best = ctaCandidates[0];
                                    ctaText = best.text.slice(0, 80);
                                    clickedCta = clickNode(best.el);
                                }

                                const matchingPairs = observed.filter((v) => v === value).length;
                                return {
                                    success: !!(setCount >= 2 || matchingPairs >= 2),
                                    fields_set: setCount,
                                    clicked_cta: !!clickedCta,
                                    cta_text: ctaText,
                                };
                            }
                            """,
                            {"password": account_password_value},
                        )
                        parsed_raw = raw
                        if isinstance(parsed_raw, str):
                            try:
                                parsed_raw = json.loads(parsed_raw)
                            except Exception:
                                parsed_raw = raw
                        if isinstance(parsed_raw, dict) and parsed_raw.get("success"):
                            return True, f"Password recovery #{attempt_no}: realigned password and confirm fields.", marker
                        return False, f"Password recovery #{attempt_no} attempted but not verified: {parsed_raw}", marker

                # Workday: handle "already exists" conflicts by forcing "No" for previous-worker and continuing.
                if (
                    legacy_workday_recovery_enabled
                    and
                    is_workday_url(url_value)
                    and workday_context_matches(ctx, WORKDAY_EXISTING_DATA_CONFLICT_KEYWORDS)
                ):
                    marker = "workday_existing_data_conflict"
                    allowed, attempt_no = register_recovery_attempt(marker, max_attempts=4)
                    if allowed:
                        page = await agent.browser_session.get_current_page()
                        if page is None:
                            return False, "No active page for Workday conflict recovery.", marker
                        raw = await page.evaluate(
                            """
                            () => {
                                const normalize = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
                                const isVisible = (el) => {
                                    if (!el) return false;
                                    const st = window.getComputedStyle(el);
                                    if (!st) return false;
                                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                                    const r = el.getBoundingClientRect();
                                    return r.width > 0 && r.height > 0;
                                };
                                const clickNode = (el) => {
                                    if (!el) return false;
                                    try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                                    try { el.click(); } catch (e) {}
                                    try { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })); } catch (e) {}
                                    return true;
                                };
                                const descriptor = (el) => normalize([
                                    el.getAttribute && (el.getAttribute('name') || ''),
                                    el.getAttribute && (el.getAttribute('id') || ''),
                                    el.getAttribute && (el.getAttribute('aria-label') || ''),
                                    el.getAttribute && (el.getAttribute('value') || ''),
                                    (el.labels && el.labels[0] && el.labels[0].textContent) || '',
                                    (el.parentElement && el.parentElement.textContent) || '',
                                    el.textContent || '',
                                ].join(' '));
                                const noMatch = (el) => {
                                    const t = descriptor(el);
                                    return t === 'no' || t.startsWith('no ') || t.includes(' no ') || t.includes('(no)');
                                };

                                let changed = 0;
                                let selectedNo = false;

                                const containers = Array.from(document.querySelectorAll('fieldset, section, div, form'))
                                    .filter(isVisible)
                                    .filter((el) => {
                                        const text = normalize(el.textContent || '');
                                        return text.includes('previously worked for') || text.includes('previous worker');
                                    })
                                    .slice(0, 30);
                                for (const container of containers) {
                                    const candidates = Array.from(
                                        container.querySelectorAll('input[type=\"radio\"], [role=\"radio\"], label, span, button, div')
                                    ).filter(isVisible);
                                    for (const node of candidates) {
                                        if (!noMatch(node)) continue;
                                        if (node.tagName === 'INPUT' && (node.getAttribute('type') || '').toLowerCase() === 'radio') {
                                            try { node.checked = true; } catch (e) {}
                                            try { node.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                                            try { node.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                                        }
                                        clickNode(node);
                                        changed += 1;
                                        selectedNo = true;
                                    }
                                }

                                // If errors are visible, click only conflict-local edit/remove controls.
                                const conflictErrors = Array.from(
                                    document.querySelectorAll('[role=\"alert\"], .error, .field-error, .validation-error, [data-automation-id*=\"error\"]')
                                )
                                    .filter(isVisible)
                                    .filter((el) => {
                                        const text = normalize(el.textContent || '');
                                        return text.includes('already exists');
                                    })
                                    .slice(0, 8);
                                for (const errorNode of conflictErrors) {
                                    const region = errorNode.closest('fieldset, section, div, form') || errorNode.parentElement;
                                    if (!region) continue;
                                    const controls = Array.from(region.querySelectorAll('button, [role=\"button\"], a, span'))
                                        .filter(isVisible)
                                        .filter((el) => {
                                            const text = descriptor(el);
                                            return (
                                                text.includes('edit') ||
                                                text.includes('remove') ||
                                                text.includes('delete') ||
                                                text.includes('clear') ||
                                                text === 'x'
                                            );
                                        })
                                        .slice(0, 4);
                                    for (const control of controls) {
                                        clickNode(control);
                                        changed += 1;
                                    }
                                }

                                let clickedContinue = false;
                                const cta = Array.from(document.querySelectorAll('button, [role=\"button\"], input[type=\"submit\"]'))
                                    .filter(isVisible)
                                    .find((el) => {
                                        const txt = descriptor(el);
                                        if (!(txt.includes('save and continue') || txt === 'continue' || txt.includes('next'))) return false;
                                        return !(el.disabled || el.getAttribute('aria-disabled') === 'true');
                                    });
                                if (cta) clickedContinue = clickNode(cta);

                                return {
                                    success: !!(changed > 0 || clickedContinue),
                                    selected_no: !!selectedNo,
                                    changed_count: changed,
                                    clicked_continue: !!clickedContinue,
                                };
                            }
                            """
                        )
                        parsed_raw = raw
                        if isinstance(parsed_raw, str):
                            try:
                                parsed_raw = json.loads(parsed_raw)
                            except Exception:
                                parsed_raw = raw
                        if isinstance(parsed_raw, dict) and parsed_raw.get("success"):
                            return True, f"Workday conflict recovery #{attempt_no}: attempted to clear conflict state and continue.", marker
                        return False, f"Workday conflict recovery #{attempt_no} attempted but not verified: {parsed_raw}", marker

                # Workday: break loops on experience date/description fields by forcing blur/change + continue.
                if (
                    legacy_workday_recovery_enabled
                    and
                    is_workday_url(url_value)
                    and workday_context_matches(ctx, WORKDAY_EXPERIENCE_FIELD_LOOP_KEYWORDS)
                ):
                    marker = "workday_experience_fields"
                    allowed, attempt_no = register_recovery_attempt(marker, max_attempts=5)
                    if not allowed:
                        return False, f"Workday experience recovery already attempted {attempt_no} times in this run.", marker
                    page = await agent.browser_session.get_current_page()
                    if page is None:
                        return False, "No active page for Workday experience recovery.", marker
                    raw = await page.evaluate(
                        """
                        (payload) => {
                            const normalize = (s) => (s || '')
                                .toLowerCase()
                                .replace(/[\\u2018\\u2019]/g, "'")
                                .replace(/[\\u201C\\u201D]/g, '"')
                                .replace(/\\s+/g, ' ')
                                .trim();
                            const isVisible = (el) => {
                                if (!el) return false;
                                const st = window.getComputedStyle(el);
                                if (!st) return false;
                                if (st.display === 'none' || st.visibility === 'hidden') return false;
                                const r = el.getBoundingClientRect();
                                return r.width > 0 && r.height > 0;
                            };
                            const clickNode = (el) => {
                                if (!el) return false;
                                try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                                try { el.click(); } catch (e) {}
                                try { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })); } catch (e) {}
                                return true;
                            };
                            const descriptor = (el) => normalize([
                                el.getAttribute && (el.getAttribute('name') || ''),
                                el.getAttribute && (el.getAttribute('id') || ''),
                                el.getAttribute && (el.getAttribute('aria-label') || ''),
                                el.getAttribute && (el.getAttribute('placeholder') || ''),
                                (el.labels && el.labels[0] && el.labels[0].textContent) || '',
                                (el.parentElement && el.parentElement.textContent) || '',
                                (el.closest && el.closest('label') && el.closest('label').textContent) || '',
                            ].join(' '));
                            const toMonthInputValue = (text) => {
                                const raw = String(text || '').trim();
                                const match = raw.match(/^(\\d{1,2})\\/(\\d{4})$/);
                                if (!match) return '';
                                const month = match[1].padStart(2, '0');
                                const year = match[2];
                                return `${year}-${month}`;
                            };
                            const dispatchFieldEvents = (field) => {
                                try { field.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                                try { field.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                                try { field.dispatchEvent(new Event('blur', { bubbles: true })); } catch (e) {}
                            };
                            const setField = (keywords, value, options = {}) => {
                                const textValue = String(value || '').trim();
                                if (!textValue) return false;
                                const keywordList = (keywords || []).map((k) => normalize(k)).filter(Boolean);
                                if (!keywordList.length) return false;
                                const requireEmpty = !!options.requireEmpty;
                                const pressEnter = !!options.pressEnter;
                                const fields = Array.from(
                                    document.querySelectorAll('input, textarea, [role=\"textbox\"], [contenteditable=\"true\"]')
                                ).filter(isVisible);
                                for (const field of fields.slice(0, 180)) {
                                    const desc = descriptor(field);
                                    if (!keywordList.some((keyword) => desc.includes(keyword))) continue;
                                    const current = normalize(('value' in field ? field.value : field.textContent) || '');
                                    if (requireEmpty && current) continue;
                                    clickNode(field);
                                    try { field.focus(); } catch (e) {}
                                    const inputType = normalize(field.getAttribute && field.getAttribute('type'));
                                    if ('value' in field) {
                                        try { field.value = ''; } catch (e) {}
                                        if (inputType === 'month') {
                                            const monthValue = toMonthInputValue(textValue);
                                            try { field.value = monthValue || textValue; } catch (e) {}
                                        } else {
                                            try { field.value = textValue; } catch (e) {}
                                        }
                                    } else {
                                        try { field.textContent = textValue; } catch (e) {}
                                    }
                                    dispatchFieldEvents(field);
                                    if (pressEnter) {
                                        try { field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); } catch (e) {}
                                        try { field.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true })); } catch (e) {}
                                    }
                                    const after = normalize(('value' in field ? field.value : field.textContent) || '');
                                    const probe = normalize(textValue).slice(0, 12);
                                    if (!probe || after.includes(probe)) return true;
                                }
                                return false;
                            };

                            const fromSet = setField(
                                ['from', 'start date', 'employment date from'],
                                payload?.fromDate || '',
                                { requireEmpty: false }
                            );
                            const toSet = setField(
                                ['to', 'end date', 'employment date to'],
                                payload?.toDate || '',
                                { requireEmpty: false }
                            );
                            const roleSet = setField(
                                ['role description', 'description', 'responsibilities', 'summary of duties'],
                                payload?.roleDescription || '',
                                { requireEmpty: true }
                            );
                            const skillsSet = setField(
                                ['type to add skills', 'skills', 'add skills'],
                                payload?.skills || '',
                                { requireEmpty: true, pressEnter: true }
                            );

                            let clickedContinue = false;
                            const ctaCandidates = Array.from(
                                document.querySelectorAll('button, [role=\"button\"], input[type=\"submit\"]')
                            )
                                .filter(isVisible)
                                .filter((el) => {
                                    const txt = normalize(el.textContent || el.value || el.getAttribute('aria-label') || '');
                                    if (!txt) return false;
                                    if (!(txt.includes('save and continue') || txt === 'continue' || txt.includes('next'))) return false;
                                    return !(el.disabled || el.getAttribute('aria-disabled') === 'true');
                                });
                            if (ctaCandidates.length) {
                                clickedContinue = clickNode(ctaCandidates[0]);
                            }

                            return {
                                success: !!(fromSet || toSet || roleSet || skillsSet || clickedContinue),
                                from_set: !!fromSet,
                                to_set: !!toSet,
                                role_set: !!roleSet,
                                skills_set: !!skillsSet,
                                clicked_continue: !!clickedContinue,
                            };
                        }
                        """,
                        {
                            "fromDate": experience_from_hint,
                            "toDate": experience_to_hint,
                            "roleDescription": role_description_hint,
                            "skills": experience_skills_hint,
                        },
                    )
                    parsed_raw = raw
                    if isinstance(parsed_raw, str):
                        try:
                            parsed_raw = json.loads(parsed_raw)
                        except Exception:
                            parsed_raw = raw
                    if isinstance(parsed_raw, dict) and parsed_raw.get("success"):
                        return True, f"Workday experience recovery #{attempt_no}: forced date/description field commit and continue flow.", marker
                    return False, f"Workday experience recovery #{attempt_no} attempted but not verified: {parsed_raw}", marker

                # Workday: recurrent loops on required fields (referral, previous employment, phone/device fields)
                if (
                    legacy_workday_recovery_enabled
                    and
                    is_workday_url(url_value)
                    and workday_context_matches(ctx, WORKDAY_REQUIRED_FIELD_LOOP_KEYWORDS)
                ):
                    needs_referral = any(
                        key in ctx for key in ("how did you hear about us", "referral source", "referral")
                    )
                    needs_prev = "previously worked for" in ctx
                    needs_phone = any(key in ctx for key in ("phone device type", "phone number"))
                    needs_postal = any(key in ctx for key in ("postal code", "zip code"))
                    needs_address = "address line" in ctx
                    needs_name = any(key in ctx for key in ("first name", "last name"))
                    recovery_tags: list[str] = []
                    if needs_referral:
                        recovery_tags.append("referral")
                    if needs_prev:
                        recovery_tags.append("employment")
                    if needs_phone:
                        recovery_tags.append("phone")
                    if needs_postal:
                        recovery_tags.append("postal")
                    if needs_address:
                        recovery_tags.append("address")
                    if needs_name:
                        recovery_tags.append("name")
                    marker_suffix = "_".join(sorted(recovery_tags)) if recovery_tags else "general"
                    marker = f"workday_required_fields_{marker_suffix}"
                    max_attempts = 8

                    allowed, attempt_no = register_recovery_attempt(marker, max_attempts=max_attempts)
                    if not allowed:
                        return False, f"Workday recovery already attempted {attempt_no} times in this run.", marker
                    page = await agent.browser_session.get_current_page()
                    if page is None:
                        return False, "No active page for Workday recovery.", marker
                    raw = await page.evaluate(
                        """
                        (payload) => {
                            const normalize = (s) => (s || '')
                                .toLowerCase()
                                .replace(/[\\u2018\\u2019]/g, "'")
                                .replace(/[\\u201C\\u201D]/g, '"')
                                .replace(/\\s+/g, ' ')
                                .trim();
                            const isVisible = (el) => {
                                if (!el) return false;
                                const st = window.getComputedStyle(el);
                                if (!st) return false;
                                if (st.display === 'none' || st.visibility === 'hidden') return false;
                                const r = el.getBoundingClientRect();
                                return r.width > 0 && r.height > 0;
                            };
                            const clickNode = (el) => {
                                if (!el) return false;
                                try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                                try { el.click(); } catch (e) {}
                                try { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })); } catch (e) {}
                                return true;
                            };
                            const descriptor = (el) => normalize([
                                el.getAttribute && (el.getAttribute('name') || ''),
                                el.getAttribute && (el.getAttribute('id') || ''),
                                el.getAttribute && (el.getAttribute('aria-label') || ''),
                                el.getAttribute && (el.getAttribute('placeholder') || ''),
                                (el.labels && el.labels[0] && el.labels[0].textContent) || '',
                                (el.parentElement && el.parentElement.textContent) || '',
                            ].join(' '));

                            const anyKeyword = (text, keywords) => {
                                const t = normalize(text);
                                return (keywords || []).some((k) => t.includes(normalize(k)));
                            };

                            const isPlaceholderChoice = (text) => {
                                const t = normalize(text || '');
                                return (
                                    !t ||
                                    t === 'select one' ||
                                    t === 'choose one' ||
                                    t === 'please select' ||
                                    t === 'select' ||
                                    t === '-- select --'
                                );
                            };

                            const clickBestVisibleOption = (candidates, allowFirstFallback = false) => {
                                const options = Array.from(
                                    document.querySelectorAll(
                                        '[role=\"listbox\"] [role=\"option\"], [role=\"option\"], li[role=\"option\"], div[role=\"option\"], [data-automation-id*=\"menuItem\"]'
                                    )
                                ).filter(isVisible);
                                for (const desired of candidates || []) {
                                    const d = normalize(desired);
                                    if (!d) continue;
                                    const match = options.find((opt) => {
                                        const txt = normalize(opt.textContent || '');
                                        return txt === d || txt.startsWith(d + ' ') || txt.includes(' ' + d + ' ');
                                    });
                                    if (match) {
                                        clickNode(match);
                                        return normalize(match.textContent || desired);
                                    }
                                }
                                if (allowFirstFallback) {
                                    const fallback = options.find((opt) => {
                                        const txt = normalize(opt.textContent || '');
                                        return !isPlaceholderChoice(txt);
                                    });
                                    if (fallback) {
                                        clickNode(fallback);
                                        return normalize(fallback.textContent || '');
                                    }
                                }
                                return '';
                            };

                            const setSelectOrCombobox = (keywords, options) => {
                                let selectedText = '';
                                let changed = false;
                                const readFieldValue = (field) => {
                                    const tag = normalize(field.tagName || '');
                                    if (tag === 'select') {
                                        const so = field.selectedOptions && field.selectedOptions.length ? field.selectedOptions[0] : null;
                                        return normalize((so && so.textContent) || field.value || '');
                                    }
                                    const own = normalize(field.value || field.textContent || (field.getAttribute && field.getAttribute('aria-label')) || '');
                                    if (own && !isPlaceholderChoice(own)) return own;
                                    let sibling = field.previousElementSibling;
                                    let siblingHops = 0;
                                    while (sibling && siblingHops < 6) {
                                        const raw = normalize(sibling.textContent || '');
                                        const cleaned = normalize(raw.replace(/\\bx\\b/g, ' '));
                                        if (cleaned && !isPlaceholderChoice(cleaned) && cleaned !== 'search') return cleaned;
                                        sibling = sibling.previousElementSibling;
                                        siblingHops += 1;
                                    }
                                    const container = field.closest('[data-automation-id*=\"formField\"], fieldset, section, div') || field.parentElement;
                                    if (container) {
                                        const chip = container.querySelector('[data-automation-id*=\"selected\"], [aria-selected=\"true\"], [data-automation-id*=\"token\"], [data-automation-id*=\"pill\"]');
                                        const chipText = normalize((chip && chip.textContent) || '');
                                        if (chipText && !isPlaceholderChoice(chipText)) return chipText;
                                    }
                                    return '';
                                };
                                const fields = Array.from(
                                    document.querySelectorAll(
                                        'select, input, [role=\"combobox\"], [aria-haspopup=\"listbox\"], [data-automation-id*=\"promptSearchInput\"], [data-automation-id*=\"comboBox\"]'
                                    )
                                ).filter(isVisible);
                                for (const field of fields) {
                                    const desc = descriptor(field);
                                    if (!anyKeyword(desc, keywords)) continue;
                                    const existing = readFieldValue(field);
                                    if (!isPlaceholderChoice(existing)) {
                                        selectedText = existing;
                                        break;
                                    }
                                    try { field.focus && field.focus(); } catch (e) {}
                                    clickNode(field);

                                    if ((field.tagName || '').toLowerCase() === 'select' && field.options) {
                                        const opts = Array.from(field.options || []);
                                        let picked = null;
                                        for (const desired of options || []) {
                                            const d = normalize(desired);
                                            picked = opts.find((o) => {
                                                const txt = normalize(o.textContent || '');
                                                const val = normalize(o.value || '');
                                                return txt === d || txt.includes(d) || val.includes(d);
                                            });
                                            if (picked) break;
                                        }
                                        if (!picked) {
                                            picked = opts.find((o) => {
                                                const txt = normalize(o.textContent || '');
                                                const val = normalize(o.value || '');
                                                if (isPlaceholderChoice(txt) || isPlaceholderChoice(val)) return false;
                                                return true;
                                            });
                                        }
                                        if (picked) {
                                            field.value = picked.value;
                                            field.dispatchEvent(new Event('input', { bubbles: true }));
                                            field.dispatchEvent(new Event('change', { bubbles: true }));
                                            selectedText = normalize(picked.textContent || picked.value || '');
                                            changed = true;
                                            break;
                                        }
                                    } else {
                                        const picked = clickBestVisibleOption(options || [], true);
                                        if (picked) {
                                            selectedText = picked;
                                            changed = true;
                                            break;
                                        }
                                        const firstChoice = String((options && options[0]) || '');
                                        if ('value' in field && firstChoice) {
                                            const before = normalize(field.value || '');
                                            if (!before || isPlaceholderChoice(before)) {
                                                try { field.value = firstChoice; } catch (e) {}
                                                try { field.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                                                try { field.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                                            }
                                            const after = normalize(field.value || '');
                                            if (after && !isPlaceholderChoice(after)) {
                                                selectedText = after;
                                                changed = after !== before;
                                                break;
                                            }
                                        }
                                        try {
                                            field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
                                            field.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }));
                                        } catch (e) {}
                                        const committed = readFieldValue(field);
                                        if (committed && !isPlaceholderChoice(committed)) {
                                            selectedText = committed;
                                            break;
                                        }
                                    }
                                }
                                return { changed, selectedText };
                            };

                            const setPhoneNumber = (phoneValue) => {
                                const digits = String(phoneValue || '').replace(/\\D+/g, '');
                                if (!digits) return false;
                                const fields = Array.from(document.querySelectorAll('input[type=\"tel\"], input'))
                                    .filter(isVisible)
                                    .filter((el) => {
                                        const desc = descriptor(el);
                                        return desc.includes('phone') && !desc.includes('device type');
                                    });
                                for (const field of fields.slice(0, 8)) {
                                    try { field.focus(); } catch (e) {}
                                    clickNode(field);
                                    try { field.value = ''; } catch (e) {}
                                    try { field.value = String(phoneValue || ''); } catch (e) {}
                                    try { field.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                                    try { field.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                                    const currentDigits = String(field.value || '').replace(/\\D+/g, '');
                                    if (currentDigits.length >= 7) return true;
                                }
                                return false;
                            };

                            const setPostalCode = (postalCode) => {
                                const value = String(postalCode || '').trim();
                                if (!value) return false;
                                const fields = Array.from(document.querySelectorAll('input')).filter(isVisible);
                                for (const field of fields.slice(0, 120)) {
                                    const desc = descriptor(field);
                                    if (!(desc.includes('postal code') || desc.includes('zip code'))) continue;
                                    try { field.focus(); } catch (e) {}
                                    clickNode(field);
                                    try { field.value = ''; } catch (e) {}
                                    try { field.value = value; } catch (e) {}
                                    try { field.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                                    try { field.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                                    try { field.dispatchEvent(new Event('blur', { bubbles: true })); } catch (e) {}
                                    const current = String(field.value || '').trim();
                                    if (current) return true;
                                }
                                return false;
                            };

                            const setAddressLine = (addressLine1) => {
                                const value = String(addressLine1 || '').trim();
                                if (!value) return false;
                                const fields = Array.from(document.querySelectorAll('input, textarea')).filter(isVisible);
                                for (const field of fields.slice(0, 120)) {
                                    const desc = descriptor(field);
                                    if (!(desc.includes('address line 1') || desc.includes('street address') || desc.includes('address'))) {
                                        continue;
                                    }
                                    try { field.focus(); } catch (e) {}
                                    clickNode(field);
                                    try { field.value = ''; } catch (e) {}
                                    try { field.value = value; } catch (e) {}
                                    try { field.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                                    try { field.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                                    const current = String(field.value || '').trim();
                                    if (current) return true;
                                }
                                return false;
                            };

                            const setNameCasing = (firstName, lastName) => {
                                const first = String(firstName || '').trim();
                                const last = String(lastName || '').trim();
                                let changed = false;
                                const fields = Array.from(document.querySelectorAll('input')).filter(isVisible);
                                for (const field of fields.slice(0, 120)) {
                                    const desc = descriptor(field);
                                    if (first && desc.includes('first name')) {
                                        try { field.focus(); } catch (e) {}
                                        try { field.value = first; } catch (e) {}
                                        try { field.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                                        try { field.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                                        changed = true;
                                    }
                                    if (last && desc.includes('last name')) {
                                        try { field.focus(); } catch (e) {}
                                        try { field.value = last; } catch (e) {}
                                        try { field.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                                        try { field.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                                        changed = true;
                                    }
                                }
                                return changed;
                            };

                            const setPreviousEmploymentNo = () => {
                                const questionKeywords = Array.isArray(payload?.questionKeywords)
                                    ? payload.questionKeywords.map((k) => normalize(k)).filter(Boolean)
                                    : [normalize(payload?.question || '')].filter(Boolean);
                                const noCandidates = Array.isArray(payload?.noOptions)
                                    ? payload.noOptions.map((v) => normalize(v)).filter(Boolean)
                                    : [normalize(payload?.option || 'no')].filter(Boolean);
                                const containerText = (el) => normalize((el && el.textContent) || '');
                                const radioText = (el) => normalize([
                                    el.textContent || '',
                                    el.getAttribute && (el.getAttribute('aria-label') || ''),
                                    el.getAttribute && (el.getAttribute('value') || ''),
                                    (el.parentElement && el.parentElement.textContent) || '',
                                ].join(' '));
                                const matchesAny = (text, candidates) => {
                                    const t = normalize(text);
                                    return (candidates || []).some((candidate) => candidate && t.includes(candidate));
                                };
                                const containers = Array.from(document.querySelectorAll('fieldset, section, div, form'))
                                    .filter((el) => matchesAny(containerText(el), questionKeywords))
                                    .slice(0, 40);
                                const selectedIn = (container) => {
                                    for (const roleRadio of Array.from(container.querySelectorAll('[role=\"radio\"][aria-checked=\"true\"]'))) {
                                        if (matchesAny(radioText(roleRadio), noCandidates)) return true;
                                    }
                                    for (const nativeRadio of Array.from(container.querySelectorAll('input[type=\"radio\"]:checked'))) {
                                        if (matchesAny(radioText(nativeRadio), noCandidates)) return true;
                                    }
                                    return false;
                                };
                                for (const container of containers) {
                                    const radios = Array.from(container.querySelectorAll('input[type=\"radio\"], [role=\"radio\"], label, span, button, div'))
                                        .filter(isVisible)
                                        .filter((el) => matchesAny(radioText(el), noCandidates));
                                    for (const node of radios.slice(0, 12)) {
                                        if (node.type === 'radio') {
                                            try { node.checked = true; } catch (e) {}
                                            try { node.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}
                                            try { node.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                                        }
                                        clickNode(node);
                                        if (selectedIn(container)) return true;
                                    }
                                }
                                return false;
                            };

                            const clickSaveAndContinue = () => {
                                const buttons = Array.from(document.querySelectorAll('button, [role=\"button\"], input[type=\"submit\"]'))
                                    .filter(isVisible);
                                const target = buttons.find((btn) => {
                                    const txt = normalize(btn.textContent || btn.value || '');
                                    if (!txt) return false;
                                    if (!(txt.includes('save and continue') || txt === 'continue')) return false;
                                    return !(btn.disabled || btn.getAttribute('aria-disabled') === 'true');
                                });
                                if (!target) return false;
                                clickNode(target);
                                return true;
                            };

                            const referralOptions = (payload?.referralOptions || []).map((v) => String(v || ''));
                            const referral = setSelectOrCombobox(
                                ['how did you hear about us', 'how did you hear', 'referral', 'source'],
                                referralOptions
                            );
                            const device = setSelectOrCombobox(
                                ['phone device type', 'device type'],
                                (payload?.deviceTypeOptions || []).map((v) => String(v || ''))
                            );
                            const phoneSet = setPhoneNumber(payload?.phone || '');
                            const postalSet = setPostalCode(payload?.postalCode || '');
                            const addressSet = setAddressLine(payload?.addressLine1 || '');
                            const nameSet = setNameCasing(payload?.firstName || '', payload?.lastName || '');
                            const prevSet = setPreviousEmploymentNo();
                            const continued = clickSaveAndContinue();
                            const success = !!(
                                referral.changed ||
                                referral.selectedText ||
                                device.changed ||
                                device.selectedText ||
                                phoneSet ||
                                postalSet ||
                                addressSet ||
                                prevSet ||
                                nameSet
                            );

                            return {
                                success,
                                referral_set: !!(referral.changed || referral.selectedText),
                                referral_value: referral.selectedText || '',
                                device_set: !!(device.changed || device.selectedText),
                                device_value: device.selectedText || '',
                                phone_set: !!phoneSet,
                                postal_set: !!postalSet,
                                address_set: !!addressSet,
                                name_set: !!nameSet,
                                previous_employment_set: !!prevSet,
                                clicked_continue: !!continued,
                            };
                        }
                        """,
                        {
                            "questionKeywords": ["previously worked for", "worked for", "previously employed by"],
                            "noOptions": ["No", "Nope", "Never"],
                            "phone": identity_profile.get("phone", ""),
                            "addressLine1": address_profile.get("street", ""),
                            "postalCode": address_profile.get("zip", ""),
                            "firstName": identity_profile.get("first_name", ""),
                            "lastName": identity_profile.get("last_name", ""),
                            "referralOptions": referral_candidates,
                            "deviceTypeOptions": ["Mobile", "Cell", "Home", "Work", "Personal"],
                        },
                    )
                    parsed_raw = raw
                    if isinstance(parsed_raw, str):
                        try:
                            parsed_raw = json.loads(parsed_raw)
                        except Exception:
                            parsed_raw = raw
                    if isinstance(parsed_raw, dict) and parsed_raw.get("success"):
                        return True, f"Workday recovery #{attempt_no}: attempted required field autofill and continue flow.", marker
                    return False, f"Workday recovery #{attempt_no} attempted but not verified: {parsed_raw}", marker

                # Greenhouse: recurrent loop on Country dropdown not selecting
                if "greenhouse.io" in url_value and "country" in ctx and ("dropdown" in ctx or "united states" in ctx):
                    marker = "greenhouse_country_united_states"
                    allowed, attempt_no = register_recovery_attempt(marker, max_attempts=3)
                    if not allowed:
                        return False, f"Greenhouse country recovery already attempted {attempt_no} times in this run.", marker
                    page = await agent.browser_session.get_current_page()
                    if page is None:
                        return False, "No active page for Greenhouse recovery.", marker
                    raw = await page.evaluate(
                        """
                        () => {
                            const normalize = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
                            const isVisible = (el) => {
                                if (!el) return false;
                                const st = window.getComputedStyle(el);
                                if (!st) return false;
                                if (st.display === 'none' || st.visibility === 'hidden') return false;
                                const r = el.getBoundingClientRect();
                                return r.width > 0 && r.height > 0;
                            };
                            const usMatch = (text) => {
                                const t = normalize(text);
                                return t.includes('united states') || t === 'usa' || t === 'us';
                            };
                            const descriptor = (el) => normalize([
                                el.getAttribute('name') || '',
                                el.getAttribute('id') || '',
                                el.getAttribute('aria-label') || '',
                                el.getAttribute('placeholder') || '',
                                (el.labels && el.labels[0] && el.labels[0].textContent) || '',
                                (el.parentElement && el.parentElement.textContent) || ''
                            ].join(' '));

                            // 1) Standard select path
                            const selects = Array.from(document.querySelectorAll('select')).filter(isVisible);
                            for (const sel of selects) {
                                if (!descriptor(sel).includes('country')) continue;
                                const options = Array.from(sel.options || []);
                                const opt = options.find((o) => usMatch(o.textContent || '') || usMatch(o.value || ''));
                                if (!opt) continue;
                                sel.value = opt.value;
                                sel.dispatchEvent(new Event('input', { bubbles: true }));
                                sel.dispatchEvent(new Event('change', { bubbles: true }));
                                if (normalize(sel.value) === normalize(opt.value)) {
                                    return { success: true, marker: 'select', value: opt.value };
                                }
                            }

                            // 2) Text/combobox input path
                            const inputs = Array.from(document.querySelectorAll('input, [role=\"combobox\"]'))
                                .filter(isVisible)
                                .filter((el) => descriptor(el).includes('country'));
                            for (const field of inputs) {
                                try { field.focus(); } catch (e) {}
                                try { field.click(); } catch (e) {}
                                if ('value' in field) {
                                    try { field.value = ''; } catch (e) {}
                                    try { field.value = 'United States'; } catch (e) {}
                                }
                                field.dispatchEvent(new Event('input', { bubbles: true }));
                                field.dispatchEvent(new Event('change', { bubbles: true }));
                                try {
                                    field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
                                    field.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }));
                                } catch (e) {}
                                const text = normalize((field.value || field.textContent || ''));
                                if (text.includes('united states') || text === 'us' || text === 'usa') {
                                    return { success: true, marker: 'combobox_input', value: text };
                                }
                            }

                            return { success: false, marker: 'no_match' };
                        }
                        """
                    )
                    parsed_raw = raw
                    if isinstance(parsed_raw, str):
                        try:
                            parsed_raw = json.loads(parsed_raw)
                        except Exception:
                            parsed_raw = raw
                    if isinstance(parsed_raw, dict) and parsed_raw.get("success"):
                        return True, f"Greenhouse country recovery #{attempt_no}: set field to 'United States'.", marker
                    return False, f"Greenhouse country recovery #{attempt_no} attempted but not verified: {parsed_raw}", marker

                return False, "No targeted recovery matched current loop context.", ""

            def get_recovery_hint(action_type: str, description: str, goal: str) -> str:
                combined = normalize_text(f"{description} {goal}")
                is_click = action_type == "click"

                if "toggle checkbox" in combined:
                    return "STUCK: Checkbox action is repeating. Stop toggling and click Create Account/Submit/Continue, then scan_form_fields."

                if is_click and any(
                    signal in combined
                    for signal in (
                        "checkbox",
                        "consent",
                        "agree",
                        "terms of use",
                        "acknowledge",
                        "i understand",
                        "privacy policy",
                        "read and accept",
                    )
                ):
                    return "STUCK: Use toggle_checkbox. Open 'Read and accept' first if required."

                if is_click and any(
                    signal in combined
                    for signal in (
                        "autofill",
                        "resume",
                        "browse",
                        "from device",
                        "choose file",
                        "upload",
                        "attach",
                        "cv",
                        "file",
                    )
                ):
                    return "STUCK: Click Autofill once, then upload_file immediately. Else use Apply Manually."

                if is_click and any(
                    signal in combined
                    for signal in (
                        "submit",
                        "next",
                        "continue",
                        "create account",
                        "apply",
                        "button",
                        "finish",
                    )
                ):
                    return "STUCK: Run scan_form_fields, check top errors, and check for a new tab."

                if action_type in ("scroll", "unknown") and any(
                    signal in combined for signal in ("element index", "not available", "not found", "stale")
                ):
                    return "STUCK: Scroll without element index, then re-read the page."

                return "RECOVERY HINT: Try a completely different approach and call check_page_state."

            checkbox_click_signals = (
                "checkbox",
                "consent",
                "agree",
                "terms of use",
                "acknowledge",
                "i understand",
                "privacy policy",
                "read and accept",
            )

            def append_trace(payload: Dict[str, Any]) -> None:
                if not trace_file:
                    return
                try:
                    trace_file.write(json.dumps(payload, default=str) + "\n")
                    trace_file.flush()
                except Exception as trace_exc:
                    print(f"Warning: Failed to write trace: {trace_exc}")
            
            async def on_step(state, output, step_num):
                nonlocal last_step_id, last_step_number, last_step_url, stagnation_reason
                nonlocal checkbox_click_hint_issued, previous_tab_ids, last_raw_action_key
                nonlocal checkbox_progress_hint_step, upload_progress_hint_issued
                nonlocal last_action_fingerprint, repeat_streak, consecutive_json_errors
                nonlocal last_intent_fingerprint, intent_repeat_streak
                nonlocal workday_create_attempts
                previous_step_success = False
                last_res = None

                # Update previous running step if exists
                if agent.state.last_result and last_step_number is not None:
                    try:
                        last_res = agent.state.last_result[-1]
                        canonical_error = canonicalize_error_text(last_res.error)
                        previous_step_success = not bool(last_res.error)
                        res_status = "failed" if (last_res.error) else "success"
                        if previous_step_success:
                            consecutive_json_errors = 0
                        elif "JSON parse failure" in canonical_error:
                            consecutive_json_errors += 1
                        else:
                            consecutive_json_errors = 0
                        if last_step_id and self.db_queue:
                            self.db_queue.update_step(
                                step_id=last_step_id, 
                                result=res_status, 
                                error_message=canonical_error or None,
                            )
                        if last_res.error:
                            if last_step_url:
                                url_tool_error_counts[last_step_url] = url_tool_error_counts.get(last_step_url, 0) + 1
                            recent_login_signals.append(normalize_text(canonical_error))
                            recent_login_signals[:] = recent_login_signals[-8:]
                        append_trace({
                            "step": last_step_number,
                            "ts": datetime.utcnow().isoformat(),
                            "update": True,
                            "result": res_status,
                            "error": canonical_error or None,
                        })
                    except Exception as e:
                        print(f"Warning: Failed to update step {last_step_id}: {e}")

                try:
                    descriptions = []
                    action_types = []
                    action_keys = []
                    action_params = []
                    for action in output.action:
                        desc = extract_action_summary(action)
                        descriptions.append(desc)
                        action_types.append(infer_action_type(action))
                        if hasattr(action, "model_dump"):
                            action_payload = action.model_dump(exclude_none=True)
                        elif isinstance(action, dict):
                            action_payload = action
                        else:
                            action_payload = {}
                        if isinstance(action_payload, dict):
                            key = next((str(k) for k in action_payload.keys() if not str(k).startswith("_")), "")
                            if key:
                                action_keys.append(key)
                                payload = action_payload.get(key)
                                action_params.append(payload if isinstance(payload, dict) else {})
                    
                    description = "; ".join(descriptions)
                    action_type = action_types[0] if action_types else "unknown"
                    raw_action_key = action_keys[0] if action_keys else ""
                    primary_action_params = action_params[0] if action_params else {}
                    page_url = state.url or ""
                    normalized_page_url = normalize_url(page_url)
                    
                    # Auto-dismiss cookie banners after navigation to new URL
                    if normalized_page_url and normalized_page_url != last_step_url:
                        try:
                            _page = await agent.browser_session.get_current_page()
                            if _page:
                                _cookie_raw = await _page.evaluate(COOKIE_DISMISS_JS)
                                _cookie = _coerce_eval_dict(_cookie_raw)
                                if _cookie.get("dismissed"):
                                    append_trace({"step": step_num, "ts": datetime.utcnow().isoformat(),
                                                  "event": "auto_cookie_dismiss", "result": _cookie})
                        except Exception:
                            pass

                    # Safe extraction of diagnostics
                    out_dict = output.model_dump() if hasattr(output, 'model_dump') else {}
                    memory_text = out_dict.get('memory') or ""
                    thinking_text = out_dict.get("thinking") or ""
                    next_goal = str(out_dict.get("next_goal") or "")
                    if has_off_task_signals(memory_text, thinking_text, next_goal):
                        task_lock_note = (
                            "Only work on this single job application. Ignore unrelated websites, "
                            "price research, and non-application tasks."
                        )
                        memory_text = upsert_memory_line(memory_text, "TASK LOCK:", task_lock_note)
                        if hasattr(output, "memory"):
                            output.memory = memory_text
                        forced_goal = (
                            "Continue this job application only: identify visible blocking fields/errors, "
                            "complete one required step, then proceed."
                        )
                        next_goal = forced_goal
                        if hasattr(output, "next_goal"):
                            output.next_goal = forced_goal
                    combined_context = normalize_text(f"{description} {next_goal}")
                    if (
                        not has_saved_login_password
                        and any(signal in combined_context for signal in ("sign in", "log in", "password", "email"))
                    ):
                        no_password_hint = (
                            "NO SAVED LOGIN PASSWORD: Do not attempt Sign In. Use Create Account/Register flow."
                        )
                        next_memory = upsert_memory_line(memory_text, "NO PASSWORD:", no_password_hint)
                        if next_memory != memory_text:
                            memory_text = next_memory
                            if hasattr(output, "memory"):
                                output.memory = memory_text
                    if consecutive_json_errors >= 2:
                        next_memory = upsert_memory_line(
                            memory_text,
                            "JSON LIMIT:",
                            "Responses were truncated. Keep thinking to one short sentence and actions minimal.",
                        )
                        if next_memory != memory_text:
                            memory_text = next_memory
                            if hasattr(output, "memory"):
                                output.memory = memory_text
                    if thinking_text and not isinstance(thinking_text, str):
                        thinking_text = json.dumps(thinking_text, default=str)

                    # --- Fix 3B: workday_create_account retry cap ---
                    if raw_action_key == "workday_create_account":
                        workday_create_attempts += 1
                        if workday_create_attempts >= 2 and not previous_step_success:
                            wd_hint = (
                                "workday_create_account FAILED 2+ times. STOP using it. "
                                "Manually: find email field, type email, find password fields, type password, "
                                "find consent checkbox, toggle_checkbox, click Create Account button."
                            )
                            next_memory = upsert_memory_line(memory_text, "WORKDAY MANUAL:", wd_hint)
                            if next_memory != memory_text:
                                memory_text = next_memory
                                if hasattr(output, "memory"):
                                    output.memory = memory_text

                    # --- Fix 3C: Account-exists signal detection ---
                    if not previous_step_success and last_res is not None:
                        err_lower = str(getattr(last_res, 'error', '') or '').lower()
                        if any(p in err_lower for p in [
                            "account already exists", "already registered", "email already",
                            "already have an account", "existing account",
                        ]):
                            sign_in_hint = (
                                "ACCOUNT EXISTS: Switch to Sign In with same credentials. "
                                "Do NOT retry Create Account."
                            )
                            next_memory = upsert_memory_line(memory_text, "ACCOUNT EXISTS:", sign_in_hint)
                            if next_memory != memory_text:
                                memory_text = next_memory
                                if hasattr(output, "memory"):
                                    output.memory = memory_text

                    current_tab_ids: set[str] = set()
                    raw_tabs = getattr(state, "tabs", None) or []
                    for tab in raw_tabs:
                        if isinstance(tab, dict):
                            tab_id = str(tab.get("tab_id") or tab.get("target_id") or "")
                        else:
                            tab_id = str(getattr(tab, "tab_id", "") or getattr(tab, "target_id", ""))
                        if tab_id:
                            current_tab_ids.add(tab_id[-4:])
                    new_tab_ids = (current_tab_ids - previous_tab_ids) if previous_tab_ids else set()

                    if last_raw_action_key == "toggle_checkbox" and previous_step_success:
                        progression_hint = (
                            "CHECKBOX TOGGLED. Click Create Account/Submit/Next now. "
                            "Do not click terms/read links again unless unchecked."
                        )
                        if progression_hint not in memory_text:
                            memory_text = f"{memory_text}\n{progression_hint}".strip()
                            if hasattr(output, "memory"):
                                output.memory = memory_text
                        checkbox_progress_hint_step = step_num

                    if (
                        checkbox_progress_hint_step is not None
                        and step_num - checkbox_progress_hint_step <= 2
                        and action_type == "click"
                        and any(signal in combined_context for signal in ("read and accept", "terms", "privacy policy"))
                    ):
                        suppress_terms_hint = (
                            "STOP: Terms already handled. Proceed with Create Account/Submit/Next."
                        )
                        if suppress_terms_hint not in memory_text:
                            memory_text = f"{memory_text}\n{suppress_terms_hint}".strip()
                            if hasattr(output, "memory"):
                                output.memory = memory_text

                    if (
                        last_raw_action_key == "upload_file"
                        and previous_step_success
                        and normalized_page_url == last_step_url
                        and not upload_progress_hint_issued
                    ):
                        upload_hint = (
                            "FILE UPLOADED. Do NOT upload again. Next: scan_form_fields, fill empty fields, then submit."
                        )
                        if upload_hint not in memory_text:
                            memory_text = f"{memory_text}\n{upload_hint}".strip()
                            if hasattr(output, "memory"):
                                output.memory = memory_text
                        upload_progress_hint_issued = True

                    last_action_click_like = last_raw_action_key in {
                        "click",
                        "click_element",
                        "click_by_index",
                        "click_element_by_index",
                    }
                    if (
                        last_action_click_like
                        and previous_step_success
                        and new_tab_ids
                        and normalized_page_url == last_step_url
                    ):
                        newest_tab = sorted(new_tab_ids)[-1]
                        tab_hint = (
                            f"NEW TAB DETECTED ({', '.join(sorted(new_tab_ids))}). "
                            f"Use switch(tab_id=\"{newest_tab}\") now."
                        )
                        if tab_hint not in memory_text:
                            memory_text = f"{memory_text}\n{tab_hint}".strip()
                            if hasattr(output, "memory"):
                                output.memory = memory_text

                        # Fix 4: Auto-switch to new tab for apply/submit clicks
                        apply_keywords = ['apply', 'submit', 'continue', 'next', 'start', 'begin']
                        last_desc_lower = normalize_text(description or "")
                        is_apply_click = any(kw in last_desc_lower for kw in apply_keywords)
                        if is_apply_click:
                            try:
                                pages = agent.browser_session.browser_context.pages
                                if len(pages) > 1:
                                    await pages[-1].bring_to_front()
                                    repeat_streak = 0
                                    last_action_fingerprint = ""
                                    append_trace({"step": step_num, "ts": datetime.utcnow().isoformat(),
                                                  "event": "auto_tab_switch", "new_url": pages[-1].url})
                            except Exception:
                                pass

                    current_fingerprint = build_action_fingerprint(
                        raw_action_key=raw_action_key,
                        action_payload=primary_action_params,
                        page_url=normalized_page_url,
                    )
                    current_intent_fingerprint = build_intent_fingerprint(
                        action_type_value=action_type,
                        page_url=normalized_page_url,
                        next_goal_value=next_goal,
                        description_value=description,
                    )
                    action_fingerprints.append(current_fingerprint)
                    agent._action_fingerprints = action_fingerprints
                    if current_fingerprint == last_action_fingerprint:
                        repeat_streak += 1
                    else:
                        repeat_streak = 1
                        last_action_fingerprint = current_fingerprint
                    if current_intent_fingerprint == last_intent_fingerprint:
                        intent_repeat_streak += 1
                    else:
                        intent_repeat_streak = 1
                        last_intent_fingerprint = current_intent_fingerprint
                    loop_count = repeat_streak
                    effective_loop_count = max(repeat_streak, intent_repeat_streak)
                    recent_urls.append(normalized_page_url)
                    recent_urls[:] = recent_urls[-20:]
                    same_url_run_len = 0
                    if normalized_page_url:
                        for seen_url in reversed(recent_urls):
                            if seen_url == normalized_page_url:
                                same_url_run_len += 1
                            else:
                                break
                    url_error_count = (
                        url_tool_error_counts.get(normalized_page_url, 0) if normalized_page_url else 0
                    )

                    evaluation_text = str(out_dict.get("evaluation_previous_goal") or "")
                    if evaluation_text:
                        recent_login_signals.append(normalize_text(evaluation_text))
                    if description:
                        recent_login_signals.append(normalize_text(description))
                    recent_login_signals[:] = recent_login_signals[-8:]
                    login_failures = sum(
                        1 for signal in recent_login_signals[-4:]
                        if any(phrase in signal for phrase in login_fail_phrases)
                    )

                    if action_type == "click" and not checkbox_click_hint_issued:
                        if any(signal in combined_context for signal in checkbox_click_signals):
                            checkbox_hint = (
                                "NOTE: You used 'click' on a checkbox/consent element. "
                                "If it didn't toggle, use toggle_checkbox('label text') next. "
                                "For Terms of Use, click the 'Read and accept' link FIRST, then toggle_checkbox."
                            )
                            if checkbox_hint not in memory_text:
                                memory_text = f"{memory_text}\n{checkbox_hint}".strip()
                                if hasattr(output, "memory"):
                                    output.memory = memory_text
                            checkbox_click_hint_issued = True

                    if loop_count >= 2:
                        diag_summary = await collect_page_diagnostics()
                        next_memory = upsert_memory_line(
                            memory_text,
                            "PAGE STATE:",
                            diag_summary,
                            max_chars=200,
                        )
                        if next_memory != memory_text:
                            memory_text = next_memory
                            if hasattr(output, "memory"):
                                output.memory = memory_text

                    if login_failures >= 2:
                        force_msg = (
                            "CRITICAL: Login failed multiple times. DO NOT try the same credentials again. "
                            "Find a Create Account path, or call done(success=false) if unavailable."
                        )
                        if force_msg not in memory_text:
                            memory_text = f"{memory_text}\n{force_msg}".strip()
                            if hasattr(output, "memory"):
                                output.memory = memory_text

                    if (
                        effective_loop_count >= 3
                        and any(signal in combined_context for signal in ("sign in", "log in", "login"))
                    ):
                        login_loop_hint = (
                            "LOGIN LOOP: Stop clicking Sign In repeatedly. Try Create Account/Register/New User. "
                            "If no alternate path is available, call done(success=false) with authentication block reason."
                        )
                        next_memory = upsert_memory_line(memory_text, "LOGIN LOOP:", login_loop_hint)
                        if next_memory != memory_text:
                            memory_text = next_memory
                            if hasattr(output, "memory"):
                                output.memory = memory_text

                    if effective_loop_count == 3:
                        hint = get_recovery_hint(action_type, description, next_goal)
                        if hint and hint not in memory_text:
                            memory_text = f"{memory_text}\n{hint}".strip()
                            if hasattr(output, "memory"):
                                output.memory = memory_text

                    if effective_loop_count >= 3 and action_type in {"click", "input", "extract"}:
                        recovery_applied = False
                        recovery_note = ""
                        recovery_marker = ""
                        recovery_applied, recovery_note, recovery_marker = await attempt_targeted_recovery(
                            page_url=page_url,
                            combined_context=f"{combined_context} {memory_text}",
                        )
                        if recovery_applied:
                            repeat_streak = 0
                            last_action_fingerprint = ""
                            intent_repeat_streak = 0
                            last_intent_fingerprint = ""
                            next_memory = upsert_memory_line(
                                memory_text,
                                "AUTO-RECOVERY:",
                                f"{recovery_note} Continue with next required fields. Call scan_form_fields now.",
                            )
                            if next_memory != memory_text:
                                memory_text = next_memory
                                if hasattr(output, "memory"):
                                    output.memory = memory_text
                            append_trace({
                                "step": step_num,
                                "ts": datetime.utcnow().isoformat(),
                                "event": "auto_recovery",
                                "recovery_marker": recovery_marker,
                                "note": recovery_note,
                            })
                        elif recovery_marker:
                            if recovery_marker=='platform_handler_recover':
                                memory_text=upsert_memory_line(memory_text,'HELPER-RECOVERY:',recovery_note)
                                if hasattr(output,'memory'):output.memory=memory_text
                            append_trace({
                                "step": step_num,
                                "ts": datetime.utcnow().isoformat(),
                                "event": "auto_recovery_attempt",
                                "recovery_marker": recovery_marker,
                                "note": recovery_note,
                            })

                    if effective_loop_count == 5 and not stagnation_reason:
                        try:
                            page = await agent.browser_session.get_current_page()
                            if page:
                                await page.evaluate("window.scrollBy(0, 50)")
                                await asyncio.sleep(0.5)
                                await page.evaluate("window.scrollBy(0, -50)")
                        except Exception:
                            pass
                        next_memory = upsert_memory_line(
                            memory_text,
                            "RECOVERY:",
                            "Performed micro-scroll to refresh indices. Re-read page and choose a different action.",
                        )
                        if next_memory != memory_text:
                            memory_text = next_memory
                            if hasattr(output, "memory"):
                                output.memory = memory_text

                    if effective_loop_count == 7 and not stagnation_reason:
                        next_memory = upsert_memory_line(
                            memory_text,
                            "CRITICAL LOOP:",
                            "Action repeated 7 times. Change strategy now or call done(success=false) if blocked.",
                        )
                        if next_memory != memory_text:
                            memory_text = next_memory
                            if hasattr(output, "memory"):
                                output.memory = memory_text

                    triggered_stagnation = False
                    if effective_loop_count >= 10 and not stagnation_reason:
                        mode = "semantic intent" if intent_repeat_streak > repeat_streak else "action fingerprint"
                        stagnation_reason = (
                            f"Stagnation: {mode} for action '{action_type}' on '{description}' repeated "
                            f"{effective_loop_count} times without page change."
                        )
                        agent._loop_stop_reason = stagnation_reason
                        if agent.stop_event:
                            agent.stop_event.set()
                        agent.state.stopped = True
                        triggered_stagnation = True

                    if (
                        same_url_run_len >= 12
                        and url_error_count >= 3
                        and not stagnation_reason
                    ):
                        stagnation_reason = (
                            f"Stagnation: URL unchanged for {same_url_run_len} steps on '{normalized_page_url}' "
                            f"with {url_error_count} tool errors. Failing to avoid login/action loops."
                        )
                        agent._loop_stop_reason = stagnation_reason
                        if agent.stop_event:
                            agent.stop_event.set()
                        agent.state.stopped = True
                        triggered_stagnation = True

                    append_trace({
                        "step": step_num,
                        "ts": datetime.utcnow().isoformat(),
                        "url": page_url,
                        "action_type": action_type,
                        "element_desc": description,
                        "llm_output": out_dict,
                        "result": "running",
                        "error": None,
                        "loop_count": loop_count,
                        "intent_loop_count": intent_repeat_streak,
                        "effective_loop_count": effective_loop_count,
                        "repeat_streak": loop_count,
                        "same_url_run_len": same_url_run_len,
                        "url_error_count": url_error_count,
                        "login_failure_signals": login_failures,
                        "raw_action": raw_action_key,
                        "action_fingerprint": current_fingerprint,
                        "new_tabs": sorted(new_tab_ids),
                    })
                    if triggered_stagnation:
                        append_trace({
                            "step": step_num,
                            "ts": datetime.utcnow().isoformat(),
                            "event": "stagnation_stop",
                            "reason": stagnation_reason,
                        })

                    if self.db_queue:
                        new_step = self.db_queue.add_step(
                            job_id=job_id,
                            step_number=step_num,
                            action_type=action_type,
                            element_description=description,
                            element_selector=None,
                            input_value=None,
                            result="running",
                            page_url=page_url,
                            step_memory=memory_text,
                            llm_thinking=(thinking_text[:500] if thinking_text else None),
                            next_goal=out_dict.get('next_goal'),
                            evaluation=out_dict.get('evaluation_previous_goal'),
                        )
                        last_step_id = new_step.id
                    last_step_number = step_num
                    last_step_url = normalized_page_url
                    last_raw_action_key = raw_action_key
                    previous_tab_ids = current_tab_ids
                    # Update shared step count for AutoFillingAgent
                    if hasattr(agent, 'last_step_num'):
                         agent.last_step_num = step_num
                except Exception as e:
                    print(f"Warning: Failed to log step {step_num}: {e}")            # ============================================================
            # Deterministic platform preflight (before LLM loop)
            # ============================================================
            print(f"🌐 Agent target URL: {job_url}")
            # For Greenhouse we drive the browser via our own raw-CDP session
            # (see registry._cdp_session), so we must NOT call browser.start()
            # (browser-use watchdogs hang processing all attached tabs) and we
            # skip the browser-use safe_navigate (the handler navigates itself).
            is_greenhouse = (detected_platform == "greenhouse")
            if not is_greenhouse:
                try:
                    await browser.start()
                except Exception:
                    pass

            if platform_handlers_enabled:
                active_platform_handler = create_platform_handler(
                    url=job_url,
                    browser_session=browser,
                    profile=profile,
                    trace_hook=append_trace,
                )
                append_trace(
                    {
                        "step": 0,
                        "ts": datetime.utcnow().isoformat(),
                        "event": "platform_handler_detected",
                        "platform": detected_platform,
                        "enabled": bool(active_platform_handler),
                    }
                )

            if (
                active_platform_handler is not None
                and detected_platform in ("workday", "greenhouse")
                and workday_deterministic_enabled
            ):
                if is_greenhouse:
                    # Greenhouse handler navigates itself (raw CDP). No browser-use
                    # safe_navigate — it would use the wrong session and hang.
                    append_trace(
                        {
                            "step": 0,
                            "ts": datetime.utcnow().isoformat(),
                            "event": "platform_safe_navigate",
                            "platform": detected_platform,
                            "success": True,
                            "reason": "handler-managed-cdp-navigation",
                        }
                    )
                else:
                    nav_ok, nav_reason = await safe_navigate(browser, job_url)
                    append_trace(
                        {
                            "step": 0,
                            "ts": datetime.utcnow().isoformat(),
                            "event": "platform_safe_navigate",
                            "platform": detected_platform,
                            "success": nav_ok,
                            "reason": nav_reason,
                        }
                    )
                    if not nav_ok:
                        return {
                            "status": "failed",
                            "message": f"Platform preflight navigation failed: {nav_reason}",
                            "error": f"Navigation failed: {nav_reason}",
                            "intervention_reason": None,
                            "screenshot_path": None,
                        }

                platform_outcome = await active_platform_handler.run()
                if platform_outcome.handoff_context:
                    platform_handoff_context = platform_outcome.handoff_context
                if platform_outcome.steps:
                    platform_handler_steps.extend(platform_outcome.steps)

                append_trace(
                    {
                        "step": 0,
                        "ts": datetime.utcnow().isoformat(),
                        "event": "platform_handler_outcome",
                        "platform": detected_platform,
                        "result": platform_outcome.result.value,
                        "state": platform_outcome.state,
                        "message": platform_outcome.message,
                        "blocker_code": platform_outcome.blocker_code,
                    }
                )

                platform_screen = job_artifacts / "platform_handler.png"
                platform_screen_path = None
                try:
                    snap_page = await browser.get_current_page()
                    if snap_page:
                        await snap_page.screenshot(path=str(platform_screen))
                        platform_screen_path = str(platform_screen)
                except Exception:
                    platform_screen_path = None

                if platform_outcome.result == HandlerResult.SUBMITTED:
                    evidence = {"confirmed": False, "reason": "missing-evidence"}
                    try:
                        snap_page = await browser.get_current_page()
                        evidence = await verify_submission(snap_page)
                    except Exception as evidence_exc:
                        evidence = {"confirmed": False, "reason": f"platform-evidence-error:{evidence_exc}"}
                    append_trace(
                        {
                            "step": 0,
                            "ts": datetime.utcnow().isoformat(),
                            "event": "platform_submission_evidence",
                            "platform": detected_platform,
                            "evidence": evidence,
                        }
                    )
                    if not evidence.get("confirmed"):
                        reason = "Deterministic handler reached submit state but confirmation was not verified."
                        return {
                            "status": "needs_review",
                            "message": f"{platform_outcome.message or reason} (unverified)",
                            "error": "",
                            "intervention_reason": reason,
                            "screenshot_path": platform_screen_path,
                        }
                    return {
                        "status": "applied",
                        "message": platform_outcome.message or "Deterministic Workday handler submitted the application.",
                        "error": "",
                        "intervention_reason": None,
                        "screenshot_path": platform_screen_path,
                    }
                if platform_outcome.result in {HandlerResult.BLOCKED,HandlerResult.FAILED}:
                    platform_handoff_context += (
                        '\nHelper handoff: '+platform_outcome.message+
                        '\nContinue this application from its current page. Inspect a fresh screenshot, frames, overlays and remaining controls; '
                        'try supported field-by-field recovery before concluding an unresolved obstacle. A helper limit is not an application outcome.'
                    )
                if (
                    platform_outcome.result in {HandlerResult.PROGRESSED, HandlerResult.NEEDS_LLM,HandlerResult.BLOCKED,HandlerResult.FAILED}
                    and not workday_fallback_llm_enabled
                ):
                    if dry_run and "dry_run" in str(platform_outcome.message or ""):
                        return {
                            "status": "dry_run",
                            "message": "DRY RUN: reached the review/submit screen; STOPPED before clicking Submit. No application was submitted.",
                            "error": "",
                            "intervention_reason": None,
                            "screenshot_path": platform_screen_path,
                        }
                    return {
                        "status": "needs_review",
                        "message": platform_outcome.message or "LLM fallback disabled after deterministic preflight.",
                        "error": "",
                        "intervention_reason": "platform_handoff_required",
                        "screenshot_path": platform_screen_path,
                    }

            # Retry Logic: Summary & Clear
            failure_context = ""
            if self.db_queue:
                 try:
                     steps = self.db_queue.get_steps(job_id)
                     if steps:
                         last = steps[-1]
                         failure_context = f"\n\nðŸ›‘ PREVIOUS ATTEMPT FAILED: The last run failed at step {last['step_number']} ({last['action_type']}). Error: {last.get('error_message') or 'Unknown'}. Logic: {last.get('evaluation') or 'N/A'}. Please correct this strategy."
                         print(f"ðŸ”„ Retry detected. Clearing {len(steps)} steps and injecting failure context.")
                         # Clear steps now that we have the summary
                         self.db_queue.clear_steps(job_id)
                         # Add Step 0 to log the context
                         self.db_queue.add_step(
                             job_id=job_id,
                             step_number=0,
                             action_type="retry_context",
                             element_description=f"RETRYING. Context: {failure_context}",
                             result="success",
                             step_memory="Previous attempt failure analysis injected."
                         )
                 except Exception as e:
                     print(f"Warning: Failed to process retry logic: {e}")

            task = build_application_task(profile, job_url, job_title, job_company, credential_profile_path=self.profile_path) + failure_context
            if platform_handoff_context:
                task += (
                    "\n\nPLATFORM HANDOFF CONTEXT:\n"
                    f"{platform_handoff_context}\n"
                    "Continue from CURRENT visible state. Do not restart auth unless this page explicitly requires it."
                )

            if (
                active_platform_handler is not None
                and detected_platform in ("workday", "greenhouse")
                and workday_deterministic_enabled
            ):
                initial_actions = [{'wait': {'seconds': 1}}]
            else:
                initial_actions = [
                    {'navigate': {'url': job_url, 'new_tab': False}},
                    {'wait': {'seconds': 3}},
                ]
            
            agent = AutoFillingAgent(
                task=task,
                llm=llm,
                browser=browser,
                controller=controller,  # Inject custom element handlers
                available_file_paths=available_files,
                file_system_path=str(job_artifacts),  # FileSystem for upload_file and done
                initial_actions=initial_actions,  # Navigate before LLM starts
                register_new_step_callback=on_step,  # Bind callback
                max_failures=5,
                generate_gif=str(job_artifacts / "recording.gif"),
                llm_timeout=self.llm_timeout,
                step_timeout=self.step_timeout,
                use_vision=use_vision,
                vision_detail_level=vision_detail_level,
                llm_screenshot_size=(800, 600),  # Keep current resolution for visual accuracy
                max_history_items=self.max_history_items,  # Limit history to prevent context overflow
            )
            
            # Inject pause event and logging context
            agent.pause_event = self.pause_event
            agent.stop_event = asyncio.Event()
            agent.db_queue = self.db_queue
            agent.job_id = job_id
            # Track step number for AutoFillingAgent to usage
            agent.last_step_num = 0
            agent._action_fingerprints = action_fingerprints
            agent._loop_stop_reason = None

            # --- Pre-LLM cookie banner dismissal ---
            try:
                page = await browser.get_current_page()
                if page:
                    await asyncio.sleep(2.0)  # Wait for cookie banner to render
                    cookie_raw = await page.evaluate(COOKIE_DISMISS_JS)
                    cookie_result = _coerce_eval_dict(cookie_raw)
                    if cookie_result.get("dismissed"):
                        print(f"  ðŸª Auto-dismissed cookie banner: {cookie_result}")
                        append_trace({"step": 0, "ts": datetime.utcnow().isoformat(),
                                      "event": "auto_cookie_dismiss", "result": cookie_result})
                        await asyncio.sleep(1.0)  # Wait for banner animation
            except Exception as e:
                print(f"  Cookie dismissal skipped: {e}")

            history = await agent.run(max_steps=self.max_steps)
            stagnation_reason = stagnation_reason or getattr(agent, "_loop_stop_reason", None)
            
            # Update final step status after run completes
            if last_step_id and self.db_queue:
                try:
                    last_status = "success"
                    last_error = None
                    if history.history and history.history[-1].result:
                         # Check if the very last action had an error
                         last_result_item = history.history[-1].result[-1]
                         if last_result_item.error:
                             last_status = "failed"
                             last_error = canonicalize_error_text(last_result_item.error)
                    if stagnation_reason:
                        last_status = "failed"
                        last_error = stagnation_reason
                    
                    self.db_queue.update_step(last_step_id, result=last_status, error_message=last_error)
                    append_trace({
                        "step": last_step_number,
                        "ts": datetime.utcnow().isoformat(),
                        "update": True,
                        "result": last_status,
                        "error": last_error,
                    })
                except Exception as e:
                    print(f"Warning: Failed to update final step: {e}")
            
            # Capture final validation screenshot
            final_screenshot_path = job_artifacts / "final_screenshot.png"
            try:
                page = await browser.get_current_page()
                await page.screenshot(path=str(final_screenshot_path))
            except Exception as e:
                # If page is closed or specific error, trying to rely on the last history item might be hard
                # But usually browser is still open here
                final_screenshot_path = None

            submission_evidence: dict[str, Any] = {"confirmed": False, "reason": "not-evaluated"}
            try:
                evidence_page = await browser.get_current_page()
                submission_evidence = await verify_submission(evidence_page)
            except Exception as evidence_exc:
                submission_evidence = {"confirmed": False, "reason": f"evidence-eval-error:{evidence_exc}"}
            append_trace(
                {
                    "step": last_step_number,
                    "ts": datetime.utcnow().isoformat(),
                    "event": "submission_evidence",
                    "evidence": submission_evidence,
                }
            )
            
            # Analyze result
            final_result = history.final_result()
            raw_errors = history.errors()
            errors = [canonicalize_error_text(e) for e in raw_errors] if raw_errors else []
            
            # Extract and save steps to database
            steps_summary = ""
            if self.db_queue:
                try:
                    from .step_tracker import extract_steps_from_history, summarize_steps
                    steps = extract_steps_from_history(history)
                    steps_summary = summarize_steps(steps)
                    
                    # Steps already saved incrementally
                    pass
                except Exception as e:
                    # Step tracking should not fail the job
                    print(f"Warning: Step tracking failed: {e}")
            
            # Use final screenshot if available, else recording
            display_screenshot = str(final_screenshot_path) if final_screenshot_path and final_screenshot_path.exists() else str(job_artifacts / "recording.gif")
            
            # Save result
            result_data = {
                "final_result": final_result,
                "errors": [str(e) for e in errors] if errors else [],
                "steps": len(history.history),
                "steps_summary": steps_summary,
                "stagnation_reason": stagnation_reason,
                "platform": detected_platform,
                "platform_handoff_context": platform_handoff_context,
                "platform_steps": platform_handler_steps,
                "submission_evidence": submission_evidence,
                "screenshot": display_screenshot
            }
            (job_artifacts / "result.json").write_text(
                json.dumps(result_data, indent=2), encoding="utf-8"
            )

            if stagnation_reason:
                append_trace({
                    "step": last_step_number,
                    "ts": datetime.utcnow().isoformat(),
                    "event": "final_stagnation",
                    "reason": stagnation_reason,
                })
                return {
                    "status": "needs_review",
                    "message": stagnation_reason,
                    "error": "",
                    "intervention_reason": stagnation_reason,
                    "screenshot_path": display_screenshot,
                }
            
            # Determine status based on result
            if final_result:
                result_lower = final_result.lower()
                
                # Check for failure indicators FIRST (takes precedence)
                failure_phrases = ["cannot complete", "max_steps", "failed to", "not complete", "unable to"]
                is_failure = any(phrase in result_lower for phrase in failure_phrases)
                
                if is_failure:
                    return {
                        "status": "failed",
                        "message": final_result,
                        "error": "Agent could not complete task",
                        "intervention_reason": None,
                        "screenshot_path": display_screenshot,
                    }
                
                # Check for clear success indicators
                success_phrases = ["application submitted", "thank you for applying", "successfully submitted", 
                                   "application received", "application confirmed"]
                if any(phrase in result_lower for phrase in success_phrases):
                    if not submission_evidence.get("confirmed"):
                        return {
                            "status": "needs_review",
                            "message": f"{final_result} (submission not DOM-verified)",
                            "error": "",
                            "intervention_reason": "Submission text reported but confirmation evidence was not detected",
                            "screenshot_path": display_screenshot,
                        }
                    return {
                        "status": "applied",
                        "message": final_result,
                        "error": "",
                        "intervention_reason": None,
                        "screenshot_path": display_screenshot,
                    }
                if any(word in result_lower for word in ["captcha", "verify", "intervention", "review", "stuck", "help"]):
                    return {
                        "status": "needs_review",
                        "message": final_result,
                        "error": "",
                        "intervention_reason": final_result,
                        "screenshot_path": display_screenshot,
                    }

            if submission_evidence.get("confirmed"):
                return {
                    "status": "applied",
                    "message": "Submission confirmed via DOM evidence.",
                    "error": "",
                    "intervention_reason": None,
                    "screenshot_path": display_screenshot,
                }
            
            # Check for errors
            if errors:
                # Filter out "None" strings
                real_errors = [e for e in errors if e and str(e).lower() != "none"]
                if real_errors:
                    return {
                        "status": "failed",
                        "message": str(real_errors[-1]),
                        "error": str(real_errors[-1]),
                        "intervention_reason": None,
                        "screenshot_path": str(job_artifacts / "recording.gif"),
                    }
            
            # Default to needs_review if unclear
            return {
                "status": "needs_review",
                "message": final_result or "Application process incomplete",
                "error": "",
                "intervention_reason": "Application did not reach clear completion state",
                "screenshot_path": str(job_artifacts / "recording.gif"),
            }
            
        except Exception as e:
            if trace_file:
                try:
                    trace_file.write(
                        json.dumps({
                            "ts": datetime.utcnow().isoformat(),
                            "event": "agent_exception",
                            "error": str(e),
                        }) + "\n"
                    )
                    trace_file.flush()
                except Exception:
                    pass
            return {
                "status": "failed",
                "message": f"Agent error: {str(e)}",
                "error": str(e),
                "intervention_reason": None,
                "screenshot_path": None,
            }
        finally:
            if trace_file:
                try:
                    trace_file.close()
                except Exception:
                    pass
            if bu_handler:
                try:
                    bu_logger.removeHandler(bu_handler)
                    bu_handler.close()
                except Exception:
                    pass
            try:
                bu_logger.setLevel(bu_previous_level)
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass
    
    def apply_sync(
        self,
        job_url: str,
        job_id: str,
        job_seq_id: Optional[int] = None,
        job_title: Optional[str] = None,
        job_company: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronous wrapper for apply()."""
        return asyncio.run(self.apply(job_url, job_id, job_seq_id, job_title, job_company))

