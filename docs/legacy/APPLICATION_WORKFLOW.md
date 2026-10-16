# Simplify-First Application Workflow

> Historical tracker workflow. The root database/profile and legacy entry points
> below describe an earlier implementation. For the current managed runtime, use
> the [documentation index](../README.md), [architecture](../ARCHITECTURE.md),
> [user guide](../USER_GUIDE.md) and [canonical application skill](../../skills/productivity/job-apply/SKILL.md).
> The explicitly selected managed database is authoritative; do not infer it from
> the root `job_applier.db` mentioned below. Historical stop/retry instructions do
> not override the current [retry policy](../jobbot-v1/RETRY_POLICY.md).

This repository is the single package for application data, portal automation, outcomes, timing, and improvement tracking. `job_applier.db` is the system of record. `timing_log.jsonl` is retained only as historical timing data.

## Components used

| Component | Role in the current workflow |
|---|---|
| `profile.json` | Authoritative identity, resume path, work authorization, application answers, and fast-submit policy |
| Simplify browser extension | Primary broad form fill and preferred multi-page Continue action |
| `job_applier/cdp_client.py` | Browser/tab, trusted input, file upload, and targeted residual-field control |
| `job_applier/platform_handlers/greenhouse.py` | Greenhouse-specific residual filling and submission |
| `job_applier/platform_handlers/workday.py` | Workday-specific residual filling when Simplify does not finish a page |
| `job_applier/platform_handlers/registry.py` | ATS detection and deterministic-handler dispatch |
| `job_applier/database.py` | SQLite models for jobs, attempts, phases, hiccups, steps, retries, and screenshots |
| `job_applier/application_tracker.py` | Unified job/attempt/phase/hiccup lifecycle and reports |
| `run_applier.py` | Single CLI entry point for automation and tracking |
| `artifacts/job-<seq>/` | Per-job traces, logs, screenshots, and evidence |

The generic browser-use/LLM agent remains a fallback. It is not the primary path for a Simplify-supported application. `run_applier.py apply` now reuses the canonical job row and automatically creates/finishes an attempt instead of adding a duplicate job.

### Runtime tiers

- **Primary:** `profile.json`, Simplify, `application_tracker.py`, `job_applier.db`, `cdp_client.py`, portal handlers, and per-job artifacts.
- **Fallback:** `agent.py`/browser-use LLM, `runner.py`, dashboard/API, step extraction, screenshots, and GIF generation. These run when using `run_applier.py apply` or the web dashboard, but are not required for a browser-driven Simplify application.
- **Legacy/diagnostic:** `track_time.py`, `timing_log.jsonl`, deprecated JSON `queue.py`, `scratch/`, and one-off `t_wd_*`/probe scripts. Do not use these as the main workflow.

## Fast application loop

1. Preflight official-live status, location, seniority, sponsorship, fit, and excluded companies.
2. Start an attempt in SQLite. The returned account strategy is based on the exact portal host and prior company applications.
3. If the strategy is `sign_in` or `sign_in_first`, use the configured profile email/password and do not attempt account creation. Use `create_account_or_sign_in` only when no prior portal history exists.
4. Open the application in the persistent Simplify-enabled Brave profile.
5. Run Simplify Autofill on every supported page.
6. Fix Need Review, required errors, and critical profile fields while filling.
7. Prefer Simplify Continue Application over the portal button.
8. Use deterministic/CDP logic only for residual fields.
9. Record every material delay as a categorized hiccup with symptom, resolution, time lost, and reusable fix.
10. Click Submit immediately when enabled; do not perform a full final-page audit or backtrack without a concrete portal error.
11. Verify authoritative submission evidence, finish the attempt, update job status, and close the tab.

## Company account reuse

```bash
# Check before opening account creation
.venv/Scripts/python.exe run_applier.py account-check \
  --company "<company>" --platform "<portal>" --url "<official-url>"

# Record only after account creation or sign-in is confirmed
.venv/Scripts/python.exe run_applier.py account-set \
  --company "<company>" --platform "<portal>" --url "<official-url>" \
  --email "<profile-email>" --status confirmed

# Review prior roles and confirmed portal accounts by company
.venv/Scripts/python.exe run_applier.py companies --applied-only
```

Account decisions are keyed by portal host, not company name alone. Passwords are never stored in SQLite; they remain in protected `profile.json`. Greenhouse returns `not_required`. A confirmed portal account returns `sign_in`. A prior successful Workday/iCIMS application without an explicit account row returns `sign_in_first`.

## Unified tracking CLI

```bash
# Start; returns job_id, seq_id, and attempt_id
.venv/Scripts/python.exe run_applier.py track-start "<official-url>" \
  --company "<company>" --title "<title>" --platform "<portal>" \
  --workflow "simplify"

# Attribute elapsed time to the next phase
.venv/Scripts/python.exe run_applier.py track-phase <attempt-id> simplify \
  --note "Autofill started"

# Record a hiccup while it is fresh
.venv/Scripts/python.exe run_applier.py track-hiccup <attempt-id> dropdown_commit \
  --description "Displayed value but required error remained" \
  --field "Government official" \
  --resolution "Clicked the real option" \
  --reusable-fix "Verify displayed value, aria-invalid, and error text" \
  --seconds-lost 30

# Finish and update the linked job in the same database
.venv/Scripts/python.exe run_applier.py track-end <attempt-id> applied \
  --evidence "Live confirmation page" --note "Submitted"

# Operational reports
.venv/Scripts/python.exe run_applier.py history --status applied
.venv/Scripts/python.exe run_applier.py hiccups
.venv/Scripts/python.exe run_applier.py hiccups --platform workday
```

## Timing phases

Use a phase transition whenever the work changes materially:

- `preflight`
- `login`
- `simplify`
- `handler`
- `residual_fields`
- `user_wait`
- `debugging`
- `verification`
- `cleanup`

The completed attempt returns total duration, whether it met five minutes, phase breakdown, slowest phase, all hiccups and resolutions, and deduplicated improvement candidates.

## Hiccup categories

Use stable semantic categories so recurrence can be aggregated by portal:

- `login`
- `account_creation`
- `dropdown_commit`
- `required_field`
- `resume_parse`
- `file_upload`
- `extension_refresh`
- `iframe`
- `verification_code`
- `captcha`
- `navigation`
- `submission_confirmation`
- `portal_outage`
- `other`

Do not create a new wording variant when an existing category fits.

## Improvement review

After a batch:

1. Run `hiccups` for all portals and for each portal used.
2. Rank categories by cumulative seconds lost, then occurrence count.
3. Convert a repeated resolved hiccup into a handler or skill update.
4. Keep one reusable fix per semantic problem.
5. Leave one-off site quirks in the database rather than adding global complexity.

A code or skill change is justified when the hiccup recurs, consumes material time, or blocks submission. The goal is fewer residual fields and less debugging—not a larger automation framework.
