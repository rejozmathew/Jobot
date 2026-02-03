"""
Element Handlers - Job Application-specific extensions for browser-use.

This module extends the browser-use Tools class.

Note: We previously had custom dropdown and upload handlers, but browser-use
already provides robust built-in actions:
- `select_dropdown`: For <select> element options
- `upload_file`: For file input handling with button detection
- `input`: For text input with autocomplete detection

The built-in actions are well-tested and handle edge cases properly.
We simply expose a factory function that creates the base Tools.
"""
# Note: Do NOT use "from __future__ import annotations" here
# as it breaks browser-use's registry type validation

import logging
from browser_use.tools.service import Tools

logger = logging.getLogger(__name__)


class JobApplierTools(Tools):
    """
    Extended Tools class for job application automation.
    
    Currently uses all built-in browser-use actions which include:
    - click: Click on interactive elements
    - input: Type text into input fields  
    - upload_file: Upload files with smart file input detection
    - select_dropdown: Select options from <select> elements
    - scroll: Scroll page or elements
    - wait: Wait for specified time
    - navigate: Navigate to URLs
    - go_back: Navigate back
    - refresh: Refresh the page
    - done: Complete the task
    
    Future extensions can add job-specific actions here.
    """
    
    def __init__(
        self,
        exclude_actions: list[str] | None = None,
        output_model = None,
        display_files_in_done_text: bool = True,
    ):
        super().__init__(
            exclude_actions=exclude_actions,
            output_model=output_model,
            display_files_in_done_text=display_files_in_done_text,
        )
        logger.info("JobApplierTools initialized with browser-use built-in actions")


def create_job_applier_controller() -> JobApplierTools:
    """
    Factory function to create the JobApplierTools controller.
    
    Returns:
        JobApplierTools instance with all browser-use actions available
    """
    return JobApplierTools()
