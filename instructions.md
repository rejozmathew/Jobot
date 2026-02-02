## GOAL
Apply for job: {job_url}
{job_title_line}
{company_line}

## CRITICAL EFFICIENCY RULES
1. **Navigate FIRST** - Go to URL immediately. Do NOT think extensively before navigating.
2. **Batch fill forms** - Identify ALL visible input fields, fill them ALL at once, then proceed.
3. **Minimize LLM calls** - Use heuristics for obvious fields (name, email, phone). Only reason about complex/ambiguous fields.
4. **Keep thinking SHORT** - 1-2 sentences max. No repetition of previous steps.

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

## ACTION SEQUENCE
1. **Navigate** → Go to job URL immediately
2. **Click Apply** → Find "Apply", "Apply Now" button
3. **Handle Login** → If login required:
   - Try credentials first
   - If fails: Create account (don't retry failed login)
   - If 2FA needed: STOP with needs_review
4. **Fill Forms** → For each form page:
   - Identify ALL input fields at once
   - Fill obvious fields (name/email/phone) without extra reasoning
   - For dropdowns: type value, wait 1 second, select first match
   - Click Next/Continue
5. **Upload Resume** → Use file path when prompted
6. **Submit** → Click final Submit button
7. **Verify Success** → Look for "Application Submitted" or "Thank you" message

## DROPDOWN HANDLING (CRITICAL)
For searchable dropdowns (Country, Company, School, City):
1. Click the field
2. Type PARTIAL text (e.g., "United" not "US" for country)
3. WAIT 1 second for suggestions
4. Press ArrowDown then Enter, OR click first suggestion
5. Do NOT just type and Tab away

**Country Code Example**: Type "United" → Wait → Select "United States (+1)"

## STOPPING CONDITIONS
- **SUCCESS**: See "Application Submitted" / "Thank you for applying" message ONLY
- **NEEDS_REVIEW**: CAPTCHA, 2FA, unknown questions, errors
- **FAILED**: Page won't load, unrecoverable errors

## EFFICIENCY REMINDERS
- Do NOT repeat yourself in thinking
- Do NOT describe what you just did - just do next action
- Do NOT screenshot/analyze every single field separately
- Fill multiple fields per step when possible
