"""Job Application Agent - Core automation logic using browser-use."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

from browser_use import Agent, Browser, BrowserProfile, ChatOpenAI
from .browser_use_overrides import apply_browser_use_overrides

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
             print("⏸️  Agent PAUSED. Waiting for user to Resume...")
             await self.pause_event.wait()
             print("▶️  Agent RESUMED - Capturing fresh state.")
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


def build_application_task(profile: Dict[str, Any], job_url: str, job_title: Optional[str] = None, job_company: Optional[str] = None) -> str:
    """Build a comprehensive task prompt for job application."""
    
    identity = profile.get("identity", {})
    work_auth = profile.get("work_authorization", {})
    eeo = profile.get("eeo_information", {})
    standard_answers = profile.get("standard_answers", {})
    experience = profile.get("experience", [])
    education = profile.get("education", [])
    resume = profile.get("resume", {})
    accounts = profile.get("accounts", {})

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
        resume_path=resume.get('path', ''),
        
        # Login
        login_email=accounts.get('default', {}).get('email', identity.get('email', '')),
        login_password=accounts.get('default', {}).get('password', ''),
    )


class JobApplyAgent:
    """Agent for automating job applications using browser-use."""
    
    def __init__(
        self,
        profile_path: str = "./profile.json",
        artifacts_dir: str = "./artifacts",
        max_steps: int = 30,
        max_history_items: int = 7,
        headless: bool = False,
        db_queue = None,  # Optional: JobQueueDB for step tracking
    ):
        self.profile_path = Path(profile_path)
        self.artifacts_dir = Path(artifacts_dir)
        self.max_steps = max_steps
        self.max_history_items = max_history_items
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
        
        profile = self.load_profile()
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
        task = build_application_task(profile, job_url, job_title, job_company)
        
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

            def get_recovery_hint(action_type: str, description: str, goal: str) -> str:
                combined = normalize_text(f"{description} {goal}")
                is_click = action_type == "click"

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
                                _cookie = await _page.evaluate(COOKIE_DISMISS_JS)
                                if _cookie and _cookie.get("dismissed"):
                                    append_trace({"step": step_num, "ts": datetime.utcnow().isoformat(),
                                                  "event": "auto_cookie_dismiss", "result": _cookie})
                        except Exception:
                            pass

                    # Safe extraction of diagnostics
                    out_dict = output.model_dump() if hasattr(output, 'model_dump') else {}
                    memory_text = out_dict.get('memory') or ""
                    thinking_text = out_dict.get("thinking") or ""
                    next_goal = str(out_dict.get("next_goal") or "")
                    combined_context = normalize_text(f"{description} {next_goal}")
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
                    action_fingerprints.append(current_fingerprint)
                    agent._action_fingerprints = action_fingerprints
                    if current_fingerprint == last_action_fingerprint:
                        repeat_streak += 1
                    else:
                        repeat_streak = 1
                        last_action_fingerprint = current_fingerprint
                    loop_count = repeat_streak
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

                    if loop_count == 3:
                        hint = get_recovery_hint(action_type, description, next_goal)
                        if hint and hint not in memory_text:
                            memory_text = f"{memory_text}\n{hint}".strip()
                            if hasattr(output, "memory"):
                                output.memory = memory_text

                    if loop_count == 5 and not stagnation_reason:
                        try:
                            page = await agent.browser_session.get_current_page()
                            if page:
                                await page.evaluate("window.scrollBy(0, 50)")
                                await page.wait_for_timeout(500)
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

                    if loop_count == 7 and not stagnation_reason:
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
                    if loop_count >= 10 and not stagnation_reason:
                        stagnation_reason = (
                            f"Stagnation: action '{action_type}' on '{description}' repeated {loop_count} times "
                            "without page change."
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
                    print(f"Warning: Failed to log step {step_num}: {e}")

            # ============================================================
            # Use initial_actions for programmatic navigation BEFORE LLM
            # This executes immediately without LLM reasoning
            # ============================================================
            initial_actions = [
                {'navigate': {'url': job_url, 'new_tab': False}},
                {'wait': {'seconds': 3}},  # Wait for dynamic content to load
            ]
            
            print(f"🌐 Agent will navigate to: {job_url}")
            
            # Retry Logic: Summary & Clear
            failure_context = ""
            if self.db_queue:
                 try:
                     steps = self.db_queue.get_steps(job_id)
                     if steps:
                         last = steps[-1]
                         failure_context = f"\n\n🛑 PREVIOUS ATTEMPT FAILED: The last run failed at step {last['step_number']} ({last['action_type']}). Error: {last.get('error_message') or 'Unknown'}. Logic: {last.get('evaluation') or 'N/A'}. Please correct this strategy."
                         print(f"🔄 Retry detected. Clearing {len(steps)} steps and injecting failure context.")
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

            task = build_application_task(profile, job_url, job_title, job_company) + failure_context
            
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
                llm_timeout=300,  # 5 minutes for local models
                use_vision=True,  # Enable vision for qwen3-vl
                vision_detail_level='low',  # Reduce token usage
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
                    await page.wait_for_timeout(2000)  # Wait for cookie banner to render
                    cookie_result = await page.evaluate(COOKIE_DISMISS_JS)
                    if cookie_result and cookie_result.get("dismissed"):
                        print(f"  🍪 Auto-dismissed cookie banner: {cookie_result}")
                        append_trace({"step": 0, "ts": datetime.utcnow().isoformat(),
                                      "event": "auto_cookie_dismiss", "result": cookie_result})
                        await page.wait_for_timeout(1000)  # Wait for banner animation
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
                    return {
                        "status": "applied",
                        "message": final_result,
                        "error": "",
                        "intervention_reason": None,
                        "screenshot_path": display_screenshot,
                    }
                elif any(word in result_lower for word in ["captcha", "verify", "intervention", "review", "stuck", "help"]):
                    return {
                        "status": "needs_review",
                        "message": final_result,
                        "error": "",
                        "intervention_reason": final_result,
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
