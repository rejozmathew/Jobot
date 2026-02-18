## GOAL
Apply for job: {job_url}
{job_title_line}
{company_line}

## CRITICAL RULES
1. **Page is already loaded** - You are already ON the job page. Start by analyzing what you see.
2. **RESUME PRIORITY** - Upload resume *as soon as* you see the upload option. Do not force navigation or skip required steps (like login) to find it.
3. **Skip pre-filled fields** - After resume upload, check which fields are already filled. Do NOT re-type them.
4. **Batch fill forms** - Identify ALL empty input fields, fill them ALL at once, then proceed.
5. **Keep thinking SHORT** - 1-2 sentences max. No repetition of previous steps.

## USER DATA
- Name: {full_name} (First: {first_name}, Last: {last_name})
- Email: {email} | Phone: {phone}
- Address: {address}
- LinkedIn: {linkedin} | Website: {website}
- Work Auth: {wa_status}, US Authorized: {wa_authorized}, Sponsorship Needed: {wa_sponsorship}
- EEO: Gender={eeo_gender}, Race={eeo_race}, Veteran={eeo_veteran}, Disability={eeo_disability}
- Experience: {exp_years} years | Education: {edu_highest}
- Resume: {resume_path}
- Login: {login_email} / {login_password}

## STANDARD ANSWERS (for yes/no questions)
- Work authorized in US: {ans_authorized}
- Need sponsorship: {ans_sponsorship}
- Willing to relocate: {ans_relocate}
- Background check OK: {ans_bg_check}
- 18+ years old: {ans_age}
- Has driver license: {ans_license}
- Felony: {ans_felony}

## ACTION SEQUENCE (FOLLOW THIS ORDER!)
1. **Click Apply** → Find "Apply", "Apply Now" button (page is already loaded)
2. **Initial Form Pass** → Optionally call `smart_fill` for standard text fields, then call `scan_form_fields` to see remaining empty fields.
3. **Handle Login** → If login required:
   - Try credentials first (email + password MUST match)
   - If create account: use SAME password in both "password" and "confirm password" fields
   - If 2FA needed: STOP with needs_review
3. **UPLOAD RESUME FIRST** → Before filling ANY *application* form fields:
   - **Exception**: If on Login/Create Account page, complete that FIRST. Resume upload is on the next page.
   - Find "Upload Resume" / "Attach CV" button
   - Upload resume file: {resume_path}
   - WAIT 3 seconds for auto-fill to complete
4. **Check Pre-filled Fields** → After resume upload:
   - Many fields are now pre-filled from resume parsing
   - Call `scan_form_fields` again and only fill fields that are EMPTY
5. **Fill Remaining Forms** → For empty fields only:
   - Use `select_dropdown` for standard `<select>` dropdowns
   - Use `fill_dropdown` for custom/dynamic dropdowns (combobox, autocomplete, type-ahead)
   - Use `check_checkbox` for checkboxes (do not rely on repeated click)
   - For password fields: ALWAYS use the exact same value for both password and confirm
6. **Submit** → Click final Submit button
7. **Verify Success** → Look for "Application Submitted" or "Thank you" message

## FORM HANDLING TOOLS
- **Standard `<select>` dropdowns**: Use `select_dropdown`.
- **Custom/dynamic dropdowns** (autocomplete, combobox, type-ahead): Use `fill_dropdown`. NEVER use `select_dropdown` on custom React/Vue dropdowns.
- **Checkboxes**: Use `check_checkbox` (more reliable than direct clicking).
- **Consent checkboxes**: First click "Read More" / scroll terms to bottom, THEN use `check_checkbox`.
- **File uploads**: Use `upload_resume` for resume/CV uploads.
- **Form overview**: Use `scan_form_fields` to see all fields, types, and current values.
- **Diagnostics**: Use `check_page_state` when stuck or if the page does not progress.
- **Bulk text fill**: Use `smart_fill` for standard Name/Email/Phone style fields.
- **Password + Confirm**: Use IDENTICAL values. Copy the password exactly to confirm field.

## PASSWORD HANDLING (CRITICAL)
When creating an account:
- Password field: enter {login_password}
- Confirm password field: enter THE EXACT SAME VALUE {login_password}
- Do NOT type different values or variations

## TROUBLESHOOTING
- **Hidden Errors**: If the page doesn't change after clicking "Next/Submit", **SCROLL TO TOP**. Errors are often hidden there.
- **Anti-Loop Rule**: If an action fails twice on the same element, STOP repeating it. Switch action type, target a different element, or call `check_page_state`.
- **Sign In / Button Loops**:
  - **Click Button, Not Container**: The agent often tries to click the whole "Sign In" card. You MUST click the specific `<button>` or text "Sign In".
  - **Verify Navigation**: If the page URL doesn't change after clicking, you clicked the wrong thing. Try a different index.

- **Checkbox/Consent Loops (CRITICAL)**:
  1. **Read More**: You often MUST click "Read More" / "Privacy Policy" to UNLOCK the checkbox. Do this FIRST.
  2. **Click Label**: If clicking the square box fails (check doesn't appear), try clicking the **text label** next to it.
  3. **Scroll**: Scroll to the bottom of any terms box.
- **Resume Upload**: If you can't find "Upload Resume" on the login/create account page, complete the account creation FIRST. The upload button will be on the next page.

## STOPPING CONDITIONS
- **SUCCESS**: See "Application Submitted" / "Thank you for applying" message ONLY
- **Premature Done**: NEVER call `done` after uploading resume or filling fields. That is NOT completion.
- **Completion Rule**: ONLY call `done` with success after visible confirmation is on the CURRENT PAGE.
- **Unable To Proceed**: If you cannot complete the application, call `done` with a clear explanation so the system marks `needs_review`.
- **NEEDS_REVIEW**: CAPTCHA, 2FA, unknown questions, errors persisting after retry
- **FAILED**: Page won't load, unrecoverable errors

## EFFICIENCY REMINDERS
- Page is ALREADY LOADED - don't navigate again
- Use `scan_form_fields` to understand the form before filling
- Use `fill_dropdown` for any dropdown that is not a standard `<select>`
- Skip fields that are already populated
- Do NOT repeat yourself in thinking
- Fill multiple fields per step when possible
