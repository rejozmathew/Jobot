---
name: job-apply
description: Execute local JobBot applications with Simplify.
version: 0.4.2
author: Rejo Z Mathew (rejozmathew), Hermes Agent
human_first: true
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [jobs, local-session, simplify]
    related_skills: [job-posting-harvest]
---

# Job Apply

This repository owns the procedure. Hermes discovery is a thin entry; another
shell-capable harness uses the same local interface. The application executor
uses its configured application model and existing mailbox capabilities. This
skill does not launch a model. Engineering and application execution are separate.

These shared rules apply to all ATS platforms. Respect app-owned controls and
selected profile facts. Use bounded recovery for demonstrated blockers and actual
page evidence. Prefer Simplify for bulk filling, without a redundant full final
audit. Native lifecycle labels are `jobbot start`, `jobbot pause`, `jobbot stop`
and `jobbot finish`; the portable commands below invoke the same services.

## Start in the current conversation

Use native `jobbot(operation="start", parameters={"url":"<eligible-job-url>"})`
when available. Otherwise run from this repository using its virtualenv Python:

```text
.venv/Scripts/python.exe -m job_applier.application_runtime start "<eligible-job-url>"
```

The selected private config resolves through `JOBBOT_CONFIG` or the repository's
ignored `artifacts/jobbot-v1-private/runtime-config.json` pointer. An explicit
`--config <absolute-json>` overrides the pointer. No API token export, dashboard,
claim, lease renewal, port selection or target binding is needed. The service
checks configured identity/resume, eligibility and duplicate history, records
preparing, launches the assigned headed browser and returns a session handle.
Doctor is a separate read-only diagnostic; start performs its own live readiness.

`HERMES_SESSION_ID` identifies this conversation. If the shell does not expose
it, pass `--driver-id <this-conversation-id>` on local commands, consistently for
this conversation. Another conversation uses its own ID. Never adopt an existing
active driver's ID. A repeated start returns the same session/attempt/tab.
`capacity_wait` means the configured pool is occupied or unavailable; inspect
its occupants/reason. It does not authorize another unmanaged browser.

The returned `session_id`, job/context, approved assets, account namespace,
workspace and timing are authoritative. Native subsequent operations resolve
that session automatically. The portable equivalent is:

```text
.venv/Scripts/python.exe -m job_applier.application_runtime call <session-id> <operation> --parameters <JSON-or-@private-file>
.venv/Scripts/python.exe -m job_applier.application_runtime status <session-id>
```

Portable operation names include `context`, `report`, `browser_observe`,
`fast_forward`, `credentials`, `browser`, `event`, `record_account_event`,
`report_upload`, `submission_intent`, `finish`, `request_mail_for_attempt`,
`match_mail_for_attempt`, and `account_lock`. No attempt/fence/target/CDP fields
belong in their parameters. Native `milestone` maps to `event`, `observe` to
`observe_owned_lesson`, `mail_request`/`mail_match` to the matching mail operations.
Native `context`, `report`, and `browser_observe` accept empty parameters.

## Execute

1. Verify the actual role remains eligible and the selected identity, account
   email, contact email, resume and mailbox are the approved ones. Exclusions,
   unknown required facts and same-job submission uncertainty remain binding.
2. Read the returned account strategy; use confirmed accounts. Inspect auth
   controls using `browser` with `{"method":"snapshot"}`. Pass only observed
   unique selectors `email_ref`, `password_ref`, optional `confirmation_ref` to
   `credentials`. It privately resolves the site's saved credential reference or
   the retained configured default for a new site, fills it, and
   coordinates this candidate/portal account. Click the observed native action
   through `browser`. For Workday, the fast runner handles the normal account
   sequence automatically; use manual recovery only for its specific exception.
   Record `creation_pending` before the create action, `created_unverified` on
   employer-confirmed creation, and `confirmed` after verified sign-in. Persist
   the non-secret `credential_ref` returned by the filler; never invent one.
   Account creation must survive a later application failure.
   `record_account_event` takes `namespace`, `state`, `credential_ref`,
   `request_id` and non-secret `evidence`. Use `account_lock` with `release:true`
   after a completed/rejected authentication step. Never repeatedly create an
   account whose outcome is unknown. Different employers have independent locks.
3. Let official Simplify do bulk filling. Observe until it settles; never compete
   with active/unknown writers. On Workday read
   [workday-simplify](../workday-simplify/SKILL.md) and use `fast_forward`.
4. Prefer enabled Continue after settling over nonblocking review warnings.
   Handle only actual required blockers and material identity/document errors.
   Use approved facts; never fabricate screening answers or reconstruct history.
5. For exceptions, `browser` methods are `snapshot`, `screenshot`, `click` (observed `selector`),
   `fill` (`selector`, approved `value`), `press` (`key`), `navigate` (`url` in the
   owned application), `evaluate` (`script`, optional structured `argument`),
   `upload` (`selector`, selected `asset_id`), and `simplify` (`action`). These
   use the assigned target. Never use global desktop focus, a process-global CDP
   variable, arbitrary other tabs, or a generic browser tool's default profile.
   `screenshot` returns an absolute private `image_path` for this session's target
   with credential controls masked. Inspect it with the current harness's image
   capability; in ordinary Hermes, use `vision_analyze(image_url=<image_path>,
   question=<specific question>)`. It uses the existing configured capability,
   not a new worker. Pair the image with `snapshot` for fresh control selectors.
6. Verify the approved resume attachment using actual employer controls. Retain
   a correct verified attachment; do not reupload it unnecessarily. If needed,
   `browser upload` hash-checks only the selected asset and records the attempt.
   After observing successful attachment use `report_upload` with `asset_id`,
   `status:"upload_confirmed"`, and evidence. No in-run PDF extraction, resume
   hunts, or reconstruction of career/education fields on any ATS.
7. Continue every page. In configured submit mode, record `submission_intent`
   with exact employer-page evidence, submit once, and verify the employer's
   exact requisition confirmation once. Do not add a human review checkpoint.
   The Workday runner does these steps when supported; do not repeat them after
   it returns applied. Simplify's success panel alone is not employer evidence.
8. Use `finish` with the truthful outcome, evidence and observed quiescence.
   The host isolates its browser before making the workspace available again.
   A missing post-click confirmation is `submission_unknown`; never click again.

`finish` parameters are `{"outcome":"blocked","evidence":"<observed reason>",
"quiescent":true}` (or another supported truthful outcome). Do not add invented
fields. `context` and `report` remain readable after the browser host has stopped.

## Mail and private identity

The selected config supplies `gmail_script` and `mailbox_token_path`. Use the
existing mailbox capability from the same conversation:

```text
.venv/Scripts/python.exe -m job_applier.hermes_gmail --script <configured-script> --token-file <configured-token-file> gmail search <narrow-query> --max 5
```

The same prefix supports `gmail get <message-id>`. Correlate portal, actual account
recipient, purpose and request time. Use codes/links privately; never log mailbox
bodies, passwords, OTPs or reset tokens. Do not use another personal mailbox.
Routine account creation, relevant verification and approved uploads/submission
follow standing configured authorization. Respect actual provider permissions.
A genuinely unavailable CAPTCHA/MFA or unknown required fact blocks that job,
without blocking unrelated work. Do not bypass challenges. Password recovery
requires the applicable configured/user authorization. Do not use an unretained
provider-generated password; use the configured reusable employer credential.

## Stop, attach and retry

```text
.venv/Scripts/python.exe -m job_applier.application_runtime pause <session-id>
.venv/Scripts/python.exe -m job_applier.application_runtime stop <session-id>
.venv/Scripts/python.exe -m job_applier.application_runtime attach <session-id>
.venv/Scripts/python.exe -m job_applier.application_runtime retry <session-id>
```

Pause/stop acknowledgement means the host stopped its owned browser activity.
Pending control is not acknowledgement. Attach by another driver requires that
pause to finish, then starts a fresh owned target; it does not inherit the old
page ID. Retry creates a new attempt only after scoped stop/reconciliation and
no uncertain submission. Heartbeats report activity and never extend local
permission. A normal reasoning gap is allowed; stalled/disconnected activity is
visible. No progress is inferred from a live host or recent heartbeat.

## Evidence and change discipline

Record a concise update when starting each application stage and when its outcome
changes: opening the role, account sign-in/creation, Simplify filling, required
residuals, resume verification, submitting, and employer confirmation. Use the
existing `event` operation with `event_type:"phase_changed"` and payload `phase`,
`activity` (what you are doing), `next_step`, `source:"Hermes executor"`, and
observed `model`/`provider` when known. Record verified outcomes with the matching
verification event. These updates appear on the session card and attempt timeline;
the engineering conversation's progress messages are not a substitute.

A helper exception is not an employer rejection. Record `event_type:"recovery"`
with its observed `error_type`, concise `evidence`, and the safe `next_step`.
Use the existing scoped browser/credential tools for a supported exception path
when possible; keep Simplify as the bulk filler. Do not finish merely because one
helper failed. If bounded recovery cannot proceed, record what failed, what was
tried, what is needed, and whether any submission occurred before finishing.
Do not log raw prompts, private reasoning, field values or credential/mail content.

`authentication_required.recovery` distinguishes unsupported/possibly changed
controls, rejected credentials, verification, configuration and uncertain account
actions. Follow its scoped screenshot/snapshot handoff. A possible page change is
not proof the employer changed its site. Keep the session open while the current
executor inspects and performs a bounded supported recovery, then return to the
fast runner/Simplify. If image capability is unavailable, report that limitation
and use the fresh DOM snapshot where sufficient. Never claim visual inspection
without seeing the image. Record the observed mismatch and recovery for a later
helper update; do not edit the helper during the application or repeat a pending
creation/submission to discover whether it worked.

Use `event`/native `milestone` for real activities, with `event_id`, `event_type`,
UTC `observed_at`, and a concise non-secret payload. Navigation/field/account
verification records actual progress. For residual timing use `field_context`
with semantic `page`, `field`, `category` identifiers, never values. Follow
observed controls and quiescence guards. A benchmark executor must not edit shared
Python, JavaScript or skills, spawn an alternative application worker, or generate
adapters. Record bounded observations for engineering after the run.

Report exact employer evidence, session/attempt IDs, honest request-to-end wall
time, actual model/effort when observed, and specific blockers. Missing evidence
stays unknown. Fixture tests do not prove live ATS support or a ten-minute result.
The authoritative helper/lifecycle map is
[APPLICATION_RUNTIME.md](../../../docs/jobbot-v1/APPLICATION_RUNTIME.md).
Older accept/claim/fence/HTTP instructions are compatibility history, not this
conversation's startup procedure. Do not invoke `run_applier.py apply`.
