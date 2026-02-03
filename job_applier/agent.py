"""Job Application Agent - Core automation logic using browser-use."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()


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
        max_history_items: int = 10,
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
    
    async def apply(
        self,
        job_url: str,
        job_id: str,
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
        from browser_use import Agent, Browser, BrowserProfile, ChatOpenAI
        
        profile = self.load_profile()
        resume_path = self.get_resume_path()
        
        # Create job-specific artifacts directory
        job_artifacts = self.artifacts_dir / job_id
        job_artifacts.mkdir(parents=True, exist_ok=True)
        
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
        
        try:
            from .element_handlers import create_job_applier_controller
            
            # Create extended controller with custom actions for dropdowns and uploads
            controller = create_job_applier_controller()
            
            # ============================================================
            # Use initial_actions for programmatic navigation BEFORE LLM
            # This executes immediately without LLM reasoning
            # ============================================================
            initial_actions = [
                {'navigate': {'url': job_url, 'new_tab': False}},
                {'wait': {'seconds': 3}},  # Wait for dynamic content to load
            ]
            
            print(f"🌐 Agent will navigate to: {job_url}")
            
            agent = Agent(
                task=task,
                llm=llm,
                browser=browser,
                controller=controller,  # Inject custom element handlers
                available_file_paths=available_files,
                initial_actions=initial_actions,  # Navigate before LLM starts
                max_failures=5,
                generate_gif=str(job_artifacts / "recording.gif"),
                llm_timeout=300,  # 5 minutes for local models
                use_vision=True,  # Enable vision for qwen3-vl
                vision_detail_level='low',  # Reduce token usage
                llm_screenshot_size=(800, 600),  # Smaller screenshots = fewer tokens
                max_history_items=self.max_history_items,  # Limit history to prevent context overflow
            )
            
            history = await agent.run(max_steps=self.max_steps)
            
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
            errors = history.errors()
            
            # Extract and save steps to database
            steps_summary = ""
            if self.db_queue:
                try:
                    from .step_tracker import extract_steps_from_history, summarize_steps
                    steps = extract_steps_from_history(history)
                    steps_summary = summarize_steps(steps)
                    
                    # Save each step to database
                    for step in steps:
                        self.db_queue.add_step(
                            job_id=job_id,
                            step_number=step["step_number"],
                            action_type=step["action_type"],
                            element_description=step["description"],
                            element_selector=step.get("element_selector"),
                            input_value=step.get("input_value"),
                            result="failed" if step.get("error") else "success",
                            error_message=step.get("error"),
                            page_url=step.get("url"),
                        )
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
                "screenshot": display_screenshot
            }
            (job_artifacts / "result.json").write_text(
                json.dumps(result_data, indent=2), encoding="utf-8"
            )
            
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
            return {
                "status": "failed",
                "message": f"Agent error: {str(e)}",
                "error": str(e),
                "intervention_reason": None,
                "screenshot_path": None,
            }
        finally:
            try:
                await browser.close()
            except Exception:
                pass
    
    def apply_sync(
        self,
        job_url: str,
        job_id: str,
        job_title: Optional[str] = None,
        job_company: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronous wrapper for apply()."""
        return asyncio.run(self.apply(job_url, job_id, job_title, job_company))
