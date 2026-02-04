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

import json
import logging
from typing import Optional, Dict, Any
from browser_use.tools.service import Tools

logger = logging.getLogger(__name__)


class JobApplierTools(Tools):
    """
    Extended Tools class for job application automation.
    Includes smart_fill for heuristic form filling.
    """
    
    def __init__(
        self,
        profile_data: Optional[Dict[str, Any]] = None,
        exclude_actions: list[str] | None = None,
        output_model = None,
        display_files_in_done_text: bool = True,
    ):
        super().__init__(
            exclude_actions=exclude_actions,
            output_model=output_model,
            display_files_in_done_text=display_files_in_done_text,
        )
        self.profile_data = profile_data or {}
        logger.info("JobApplierTools initialized with browser-use built-in actions + smart_fill")

    async def smart_fill(self) -> str:
        """
        Heuristically find and fill common job application fields (Name, Email, Phone, LinkedIn, Address) 
        using the user's profile data. Use this FIRST to fill standard fields instantly.
        """
        if not self.profile_data:
            return "No profile data available."

        # Extract flat data
        identity = self.profile_data.get('identity', {})
        address = identity.get('address', {})
        
        flat_data = {
            'first_name': identity.get('first_name', ''),
            'last_name': identity.get('last_name', ''),
            'email': identity.get('email', ''),
            'phone': identity.get('phone', ''),
            'linkedin': identity.get('linkedin', ''),
            'street': address.get('street', ''),
            'city': address.get('city', ''),
            'zip': address.get('zip', ''),
        }
        
        js_code = f"""
            (function() {{
                const data = {json.dumps(flat_data)};
                const mapping = {{
                    'first_name': ['first_name', 'firstname', 'fname', 'given-name', 'givenname'],
                    'last_name': ['last_name', 'lastname', 'lname', 'family-name', 'familyname'],
                    'email': ['email', 'e-mail', 'mail'],
                    'phone': ['phone', 'mobile', 'cell', 'tel', 'contact'],
                    'linkedin': ['linkedin', 'linked-in', 'website'],
                    'street': ['address', 'street', 'line1'],
                    'city': ['city', 'town'],
                    'zip': ['zip', 'postal', 'code']
                }};
                
                let filled = [];
                
                function setVal(el, val) {{
                     if (!val) return;
                     el.focus();
                     el.value = val;
                     el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                     el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                     el.blur();
                }}
                
                const inputs = document.querySelectorAll('input');
                inputs.forEach(input => {{
                    if (input.value && input.value.trim() !== '') return; 
                    if (input.type === 'hidden' || input.type === 'submit' || input.type === 'checkbox' || input.type === 'radio') return;
                     
                    const name = (input.name || '').toLowerCase();
                    const id = (input.id || '').toLowerCase();
                    const label = (input.labels?.[0]?.innerText || input.getAttribute('aria-label') || '').toLowerCase();
                    const placeholder = (input.placeholder || '').toLowerCase();
                    
                    const text = name + ' ' + id + ' ' + label + ' ' + placeholder;
                    
                    for (const [key, keywords] of Object.entries(mapping)) {{
                        if (keywords.some(kw => text.includes(kw))) {{
                             setVal(input, data[key]);
                             filled.push(key);
                             break;
                        }}
                    }}
                }});
                return [...new Set(filled)].join(', ');
            }})();
        """
        try:
            page = await self.browser_session.get_current_page()
            result = await page.evaluate(js_code)
            return f"Smart filled fields: {{result}}"
        except Exception as e:
            return f"Smart fill failed: {{str(e)}}"


def create_job_applier_controller(profile_data: Optional[Dict[str, Any]] = None) -> JobApplierTools:
    """
    Factory function to create the JobApplierTools controller.
    """
    return JobApplierTools(profile_data=profile_data)
