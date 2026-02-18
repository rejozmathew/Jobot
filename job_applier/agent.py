"""Job Application Agent - Core automation logic using browser-use."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

from browser_use import Agent, Browser, BrowserProfile, ChatOpenAI

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
        
        try:
            trace_file = (job_artifacts / "trace.jsonl").open("a", encoding="utf-8")
            from .element_handlers import create_job_applier_controller
            
            # Create extended controller with custom actions for dropdowns and uploads
            controller = create_job_applier_controller(profile)
            
            # ============================================================
            # Define Incremental Step Callback
            # ============================================================
            from .step_tracker import extract_action_summary, infer_action_type
            
            last_step_id = None
            last_step_number = None
            action_fingerprints: list[tuple[str, str, str]] = []
            stagnation_reason: Optional[str] = None

            def normalize_text(value: str) -> str:
                return " ".join(str(value or "").lower().split())

            def append_trace(payload: Dict[str, Any]) -> None:
                if not trace_file:
                    return
                try:
                    trace_file.write(json.dumps(payload, default=str) + "\n")
                    trace_file.flush()
                except Exception as trace_exc:
                    print(f"Warning: Failed to write trace: {trace_exc}")
            
            async def on_step(state, output, step_num):
                nonlocal last_step_id, last_step_number, stagnation_reason
                
                # Update previous running step if exists
                if agent.state.last_result and last_step_number is not None:
                    try:
                        last_res = agent.state.last_result[-1]
                        res_status = "failed" if (last_res.error) else "success"
                        if last_step_id and self.db_queue:
                            self.db_queue.update_step(
                                step_id=last_step_id, 
                                result=res_status, 
                                error_message=last_res.error
                            )
                        append_trace({
                            "step": last_step_number,
                            "ts": datetime.utcnow().isoformat(),
                            "update": True,
                            "result": res_status,
                            "error": last_res.error,
                        })
                    except Exception as e:
                        print(f"Warning: Failed to update step {last_step_id}: {e}")

                try:
                    descriptions = []
                    action_types = []
                    for action in output.action:
                        desc = extract_action_summary(action)
                        descriptions.append(desc)
                        action_types.append(infer_action_type(action))
                    
                    description = "; ".join(descriptions)
                    action_type = action_types[0] if action_types else "unknown"
                    page_url = state.url or ""
                    
                    # Safe extraction of diagnostics
                    out_dict = output.model_dump() if hasattr(output, 'model_dump') else {}
                    memory_text = out_dict.get('memory') or ""

                    fingerprint = (action_type, normalize_text(description), page_url)
                    action_fingerprints.append(fingerprint)
                    agent._action_fingerprints = action_fingerprints
                    loop_count = sum(1 for item in action_fingerprints[-7:] if item == fingerprint)

                    if loop_count >= 3:
                        loop_warning = (
                            "WARNING: You are stuck in a loop. Same action on same element repeated 3+ times. "
                            "Try a different action (fill_dropdown/check_checkbox), or call check_page_state."
                        )
                        if loop_warning not in memory_text:
                            memory_text = f"{memory_text}\n{loop_warning}".strip()
                            if hasattr(output, 'memory'):
                                output.memory = memory_text

                    if loop_count >= 5 and not stagnation_reason:
                        stagnation_reason = (
                            f"Stagnation: action '{action_type}' on '{description}' repeated {loop_count} times "
                            "without page change."
                        )
                        agent._loop_stop_reason = stagnation_reason
                        if agent.stop_event:
                            agent.stop_event.set()
                        agent.state.stopped = True

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
                    })
                    if stagnation_reason and loop_count >= 5:
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
                            next_goal=out_dict.get('next_goal'),
                            evaluation=out_dict.get('evaluation_previous_goal'),
                        )
                        last_step_id = new_step.id
                    last_step_number = step_num
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
                initial_actions=initial_actions,  # Navigate before LLM starts
                register_new_step_callback=on_step,  # Bind callback
                max_failures=5,
                generate_gif=str(job_artifacts / "recording.gif"),
                llm_timeout=300,  # 5 minutes for local models
                use_vision=True,  # Enable vision for qwen3-vl
                vision_detail_level='low',  # Reduce token usage
                llm_screenshot_size=(800, 600),  # Smaller screenshots = fewer tokens
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
                             last_error = last_result_item.error
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
            errors = history.errors()
            
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
