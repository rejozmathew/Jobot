"""Step Extraction - Parse browser-use history into human-readable steps."""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime


def extract_action_summary(action: Any) -> str:
    """
    Extract a short, human-readable summary from a browser-use action.
    
    Returns a string like:
    - "Clicked 'Apply Now' button"
    - "Typed 'john@email.com' in Email field"
    - "Navigated to example.com/apply"
    - "Scrolled down"
    - "Selected 'United States' from dropdown"
    """
    if action is None:
        return "No action"
    
    # Handle action as dict or object
    if hasattr(action, 'model_dump'):
        action_data = action.model_dump(exclude_none=True)
    elif isinstance(action, dict):
        action_data = action
    else:
        return f"Action: {str(action)[:50]}"
    
    # Extract action type and details
    summary_parts = []
    
    # browser-use uses action names like: click, input, navigate, scroll, etc.
    # The action data format is: {'action_name': {params...}}
    
    # Handle 'click' action
    if 'click' in action_data:
        click = action_data['click']
        index = click.get('index', '?')
        summary_parts.append(f"Clicked element #{index}")
    
    # Handle 'input' action (text input)
    elif 'input' in action_data:
        inp = action_data['input']
        index = inp.get('index', '?')
        text = inp.get('text', '')
        display_text = mask_sensitive(text)
        summary_parts.append(f"Typed '{display_text}' in element #{index}")
    
    # Handle 'navigate' action
    elif 'navigate' in action_data:
        nav = action_data['navigate']
        url = nav.get('url', '')
        short_url = shorten_url(url)
        summary_parts.append(f"Navigated to {short_url}")
    
    # Handle 'scroll' action
    elif 'scroll' in action_data:
        scroll = action_data['scroll']
        direction = scroll.get('direction', 'down')
        summary_parts.append(f"Scrolled {direction}")
    
    # Handle 'select_dropdown' action
    elif 'select_dropdown' in action_data:
        sel = action_data['select_dropdown']
        text = sel.get('text', '')
        index = sel.get('index', '?')
        summary_parts.append(f"Selected '{text[:30]}' from dropdown #{index}")

    # Handle custom 'fill_dropdown' action
    elif 'fill_dropdown' in action_data:
        sel = action_data['fill_dropdown']
        text = sel.get('value', '')
        index = sel.get('index', '?')
        summary_parts.append(f"Filled dynamic dropdown #{index} with '{text[:30]}'")

    # Handle custom 'check_checkbox' action
    elif 'check_checkbox' in action_data:
        chk = action_data['check_checkbox']
        index = chk.get('index', '?')
        checked = chk.get('checked', True)
        summary_parts.append(f"Set checkbox #{index} to {checked}")

    # Handle 'upload_file' action
    elif 'upload_file' in action_data:
        upload = action_data['upload_file']
        path = upload.get('path', '')
        filename = path.split('/')[-1].split('\\')[-1] if path else 'file'
        summary_parts.append(f"Uploaded '{filename}'")

    # Handle custom 'upload_resume' action
    elif 'upload_resume' in action_data:
        upload = action_data['upload_resume']
        path = upload.get('path', '')
        filename = path.split('/')[-1].split('\\')[-1] if path else 'resume'
        summary_parts.append(f"Uploaded resume '{filename}'")

    # Handle scan/diagnostic actions
    elif 'scan_form_fields' in action_data:
        summary_parts.append("Scanned form fields")

    elif 'check_page_state' in action_data:
        summary_parts.append("Checked page diagnostics")

    elif 'smart_fill' in action_data:
        summary_parts.append("Ran smart field fill")
    
    # Handle 'wait' action
    elif 'wait' in action_data:
        wait = action_data['wait']
        seconds = wait.get('seconds', 0)
        summary_parts.append(f"Waited {seconds}s")
    
    # Handle 'go_back' action
    elif 'go_back' in action_data:
        summary_parts.append("Navigated back")
    
    # Handle 'refresh' action
    elif 'refresh' in action_data:
        summary_parts.append("Refreshed page")
    
    # Handle 'done' action
    elif 'done' in action_data:
        done = action_data['done']
        text = done.get('text', '')[:50] if isinstance(done, dict) else str(done)[:50]
        summary_parts.append(f"Completed: {text}")
    
    # Handle 'extract_content' action
    elif 'extract_content' in action_data:
        summary_parts.append("Extracted page content")
    
    # Handle 'hover' action
    elif 'hover' in action_data:
        hover = action_data['hover']
        index = hover.get('index', '?')
        summary_parts.append(f"Hovered over element #{index}")
    
    # Legacy format support (click_element, input_text, go_to_url, select_option)
    elif 'click_element' in action_data:
        click = action_data['click_element']
        index = click.get('index', '?')
        summary_parts.append(f"Clicked element #{index}")
    
    elif 'input_text' in action_data:
        inp = action_data['input_text']
        index = inp.get('index', '?')
        text = inp.get('text', '')
        display_text = mask_sensitive(text)
        summary_parts.append(f"Typed '{display_text}' in element #{index}")
    
    elif 'go_to_url' in action_data:
        url = action_data['go_to_url'].get('url', '')
        short_url = shorten_url(url)
        summary_parts.append(f"Navigated to {short_url}")
    
    elif 'select_option' in action_data:
        sel = action_data['select_option']
        option = sel.get('option', sel.get('text', ''))
        index = sel.get('index', '?')
        summary_parts.append(f"Selected '{option[:30]}' from dropdown #{index}")
    
    else:
        # Fallback: just list the keys present
        keys = [k for k in action_data.keys() if not k.startswith('_')]
        if keys:
            summary_parts.append(f"{keys[0].replace('_', ' ').title()}")
        else:
            summary_parts.append("Unknown action")
    
    return "; ".join(summary_parts) if summary_parts else "No action details"


def mask_sensitive(text: str) -> str:
    """Mask potentially sensitive values."""
    if not text:
        return ""
    
    # Short texts are likely field values, show them
    if len(text) <= 30:
        # Check for password-like patterns
        lower = text.lower()
        if any(x in lower for x in ['password', 'secret', 'key', 'token']):
            return "***"
        return text
    
    # Truncate long texts
    return text[:25] + "..."


def shorten_url(url: str) -> str:
    """Shorten URL for display."""
    if not url:
        return ""
    
    # Remove protocol
    url = url.replace('https://', '').replace('http://', '')
    
    # Truncate if too long
    if len(url) > 50:
        return url[:47] + "..."
    return url


def extract_steps_from_history(history: Any) -> List[Dict[str, Any]]:
    """
    Extract human-readable steps from browser-use AgentHistory.
    
    Returns a list of dicts with:
    - step_number: int
    - action_type: str (click, input, navigate, etc.)
    - description: str (human-readable summary)
    - url: str (current page URL if available)
    - error: str (error message if any)
    - timestamp: datetime
    """
    steps = []
    
    if not history or not hasattr(history, 'history'):
        return steps
    
    for i, item in enumerate(history.history, 1):
        step = {
            "step_number": i,
            "action_type": "unknown",
            "description": "",
            "element_selector": None,
            "input_value": None,
            "url": None,
            "error": None,
            "timestamp": datetime.utcnow(),
        }
        
        # Extract action from model_output
        model_output = getattr(item, 'model_output', None)
        if model_output:
            # browser-use stores actions in model_output.action as a list
            actions = getattr(model_output, 'action', None)
            if actions and len(actions) > 0:
                # Process each action in the step
                descriptions = []
                action_types = []
                for action in actions:
                    desc = extract_action_summary(action)
                    if desc and desc != "No action":
                        descriptions.append(desc)
                    atype = infer_action_type(action)
                    if atype != "unknown":
                        action_types.append(atype)
                    
                    # Try to extract selector and input value
                    if hasattr(action, 'model_dump'):
                        action_data = action.model_dump(exclude_none=True)
                        for key in ['click', 'input', 'select_dropdown', 'click_element', 'input_text', 'select_option']:
                            if key in action_data:
                                sub = action_data[key]
                                if 'index' in sub:
                                    step["element_selector"] = f"index:{sub['index']}"
                                if 'text' in sub:
                                    step["input_value"] = mask_sensitive(sub['text'])
                                break
                
                step["description"] = "; ".join(descriptions) if descriptions else "Unknown action"
                step["action_type"] = action_types[0] if action_types else "unknown"
        
        # Extract URL from state if available
        state = getattr(item, 'state', None)
        if state:
            step["url"] = getattr(state, 'url', None)
        
        # Extract error if present
        results = getattr(item, 'result', None)
        if results:
            for result in results:
                error = getattr(result, 'error', None)
                if error:
                    step["error"] = str(error)[:200]
                    break
        
        # Only add steps that have meaningful content
        if step["description"] or step["error"]:
            steps.append(step)
    
    return steps


def infer_action_type(action: Any) -> str:
    """Infer action type from action object."""
    if action is None:
        return "unknown"
    
    if hasattr(action, 'model_dump'):
        action_data = action.model_dump(exclude_none=True)
    elif isinstance(action, dict):
        action_data = action
    else:
        return "unknown"
    
    # Map action keys to types (browser-use format)
    type_map = {
        # New format
        'click': 'click',
        'input': 'input', 
        'navigate': 'navigate',
        'scroll': 'scroll',
        'select_dropdown': 'select',
        'fill_dropdown': 'select',
        'check_checkbox': 'click',
        'upload_file': 'upload',
        'upload_resume': 'upload',
        'scan_form_fields': 'extract',
        'check_page_state': 'extract',
        'smart_fill': 'input',
        'extract_content': 'extract',
        'wait': 'wait',
        'done': 'done',
        'go_back': 'navigate',
        'refresh': 'navigate',
        'hover': 'hover',
        # Legacy format
        'click_element': 'click',
        'input_text': 'input',
        'go_to_url': 'navigate',
        'select_option': 'select',
    }
    
    for key, action_type in type_map.items():
        if key in action_data:
            return action_type
    
    return "unknown"


def summarize_steps(steps: List[Dict[str, Any]]) -> str:
    """
    Create a brief summary of all steps for logging.
    
    Example: "15 steps: navigate → click (3) → input (8) → click (2) → done"
    """
    if not steps:
        return "0 steps"
    
    type_sequence = []
    current_type = None
    current_count = 0
    
    for step in steps:
        action_type = step.get("action_type", "unknown")
        if action_type == current_type:
            current_count += 1
        else:
            if current_type:
                if current_count > 1:
                    type_sequence.append(f"{current_type} ({current_count})")
                else:
                    type_sequence.append(current_type)
            current_type = action_type
            current_count = 1
    
    # Add last group
    if current_type:
        if current_count > 1:
            type_sequence.append(f"{current_type} ({current_count})")
        else:
            type_sequence.append(current_type)
    
    return f"{len(steps)} steps: " + " → ".join(type_sequence)
