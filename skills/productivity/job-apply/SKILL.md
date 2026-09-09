---
name: job-apply
description: Execute local JobBot applications with Simplify.
version: 0.5.1
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

Slow page loading or missing Simplify returns `startup_recovery` on the same
owned session. Inspect that tab and recover setup; elapsed readiness polling is
not an employer rejection. Identity checks compare browser ownership, configured
candidate and the actual job. Workday location/title changes and new application
steps do not change that job. `identity_unresolved` permits owned snapshots,
screenshots and navigation back to the assigned job; it does not close the session.

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
   Workday creation/sign-in always use these native controls and the retained
   credential filler. Resume Simplify once the application form opens. Its
   account autofill can substitute a generated password; a credential reference
   does not establish what Simplify will type.
   Record `creation_pending` before the create action, `created_unverified` on
   employer-confirmed creation, and `confirmed` after verified sign-in. Persist
   the non-secret `credential_ref` returned by the filler; never invent one.
   Account creation must survive a later application failure. A pending record
   is dispatch intent, not proof of an existing account. Only a proven
   `not_executed` creation click from the owning attempt can become
   `creation_not_executed` and permit bounded creation recovery. A lost or
   possibly dispatched response still requires reconciliation. For Workday,
   continue with one bounded sign-in using the retained credential, including
   the email chooser; a pending record from an earlier attempt supports this
   check. Keep it pending until authenticated application UI confirms success.
   Account scope is
   candidate plus verified portal namespace, not the individual job URL.
   `record_account_event` takes `namespace`, `state`, `credential_ref`,
   `request_id` and non-secret `evidence`. Use `account_lock` with `release:true`
   after a completed/rejected authentication step. Never repeatedly create an
   account whose outcome is unknown. Different employers have independent locks.
   For Workday recognition misses, prefer the combined `screen` inventory and
   one `fast_forward` call with a `recovery` mapping, as described in the Workday
   skill. It fills the selected private controls, acts and observes in one owned
   connection; do not rerun the failed matcher or take a model turn per field.
3. Let official Simplify do bulk filling. Observe until it settles; never compete
   with active writers. For unknown state, reobserve or use an enabled, observed
   Simplify Stop/Cancel autofill control through `browser` with
   `{"method":"simplify","action":"stop"}` (and its ref if needed). This only
   cancels the extension operation; the application stays open. The helper must
   observe settlement before native work resumes. On Workday read
   [workday-simplify](../workday-simplify/SKILL.md) and use `fast_forward`.
   A cosmetic panel spinner can coexist with an enabled Simplify input prompt.
   Use the observed enabled action (including `autofill_skills`, any count), then
   wait again. A real unended write, disabled action or explicit ongoing fill
   still blocks. Permission for extension input does not authorize native edits.
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
   `snapshot` now combines native and official Simplify controls, their observed
   refs, account strategy and current activity/errors. For an observed button,
   `browser click` also accepts `source`, `ref`, and `page_signature` from that
   inventory. No custom DOM-discovery code is needed. On other ATSs, Simplify employer sign-in
   uses `browser simplify` with `action:sign_in` and non-secret
   `credential_evidence` establishing retained credential use. An enabled button
   alone is not that evidence, and Simplify's own login is a separate operation.
   Shared `select` accepts an observed `ref` or `selector` and an exact `label`
   or `value`; it supports native selects and associated ARIA menus, and verifies
   selection. `check` accepts boolean `value` and never toggles an already correct
   box. `fill` and `press` also accept refs; keys include Tab, Shift+Tab, Space,
   Escape, Enter, PageUp, PageDown and Control+A. Unassociated or ambiguous options return evidence.
   Use this SAME API for Workday, other ATSs, native selects and custom dropdowns,
   including embedded application frames. Pass the opaque observed ref unchanged;
   the runtime resolves its document and rechecks ownership. Do not choose a
   separate iframe handler, switch targets or construct a frame selector. A stale
   ref requires a fresh snapshot. Uploads, private credentials, Simplify actions
   and submission use the same document routing. If multiple Simplify documents
   offer an action, pass that action's observed ref to `browser simplify`.
   Keep a populated "How did you hear about us?" answer such as LinkedIn even
   when Simplify marks it for review. Prefer enabled native Continue to opening
   a filled field's review menu; repair only an actual employer validation error.
   Shared form writes and advancement retain observed application questions and
   answers in the private spool's `answers/attempt-<id>.json`; changed answers
   remain in history. `answer_history_path` and timeline checkpoints locate it.
   For a manual answer, optional `answer_basis` identifies the actual approved
   profile fact or user instruction. Missing provenance is recorded as such.
   Answer factual questions from approved facts; do not choose yes/no merely
   because it sounds favorable. This history is an audit, not new profile facts.
   `apply_policy` uses the attempt's approved `application_answer_policy` for
   salary expectations and routine privacy consent. Use the applicable advertised
   range maximum when configured; use the configured absolute amount only when
   no applicable range is available. An explicit observed range can be supplied
   as `salary_range:{min,max,currency}`. Do not use the candidate's desired range
   as the job's range. Routine privacy consent excludes marketing and job alerts.
6. Use the configured approved resume through Simplify during filling. Handle an
   actual required-upload error with `browser upload` and the selected asset.
   Report only uploads performed through that helper; do not manufacture an
   upload event for an attachment Simplify supplied. At Review, proceed directly
   to the enabled Submit control: no attachment search, scrolling audit, re-upload,
   or requirement for resume evidence in the internal ledger. Missing attachment
   evidence alone does not block submission. No in-run PDF extraction, resume
   hunts, or reconstruction of career/education fields on any ATS.
7. Continue every page. In configured submit mode use `browser submit` with the
   observed native `ref` or `selector`, or `source:simplify` for its final action.
   The shared helper arms confirmation capture, records intent and clicks once.
   The Workday runner uses the same helper automatically. It retains native and
   Simplify confirmation messages, source, time and a private screenshot before
   finishing. Accepted sources come from the profile; employer is the default.
   Simplify evidence remains labelled Simplify, never employer evidence. Do not
   add a human review checkpoint or repeat submission after `applied`. An accepted
   Simplify "Application Submitted!" message is sufficient; do not then seek a
   second employer confirmation or wait for email. Review is a submit step, not
   a request to audit the completed application.
8. Use `finish` with the truthful outcome, evidence and observed quiescence.
   The host isolates its browser before making the workspace available again.
   A missing post-click confirmation is `submission_unknown`; never click again.

After an uncertain click, use owned screenshot, snapshot and confirmation
observation. The session stays open until completion, Stop, or an explicitly
configured maximum runtime. A proven `not_executed` Submit returns recovery,
not submission uncertainty: refresh the control and continue in the same attempt.
An intent with a missing dispatch result remains uncertain. `stop` closes
immediately. `reconcile` accepts `outcome`,
`evidence`, and `source` (`employer`, `simplify`, or `user_reported`); cite the
actual user's confirmation when using user_reported. It stops a still-owned
session before correction and preserves the original attempt duration. Portable:
`application_runtime reconcile <session-id> --outcome applied --source user_reported --evidence "<actual confirmation>"`.
Reconciliation never submits or creates a retry. Cross-job URLs are not proof.

Headed sessions start maximized. Obscured clicks return viewport/covering metadata
and use only an uncovered point on the actual control. Inspect and use an observed
panel collapse control if needed; never force through an overlay or automatically
refresh an application. Completed workspaces retire their owned background host;
parallel sessions retain their independent hosts and browser processes.

`finish` parameters are `{"outcome":"blocked","evidence":"<observed reason>",
"quiescent":true}` (or another supported truthful outcome). Do not add invented
fields. `context` and `report` remain readable after the browser host has stopped.

## Missing required answers

Use approved profile facts, policy and exact saved human answers first. When an
actual required question still lacks an answer, call `browser` with
`{"method":"request_answers","refs":["<observed required field ref>"]}`.
This applies configured routine policy and exact saved answers before queuing
anything for the user. It captures the remaining full question, offered
choices and job/candidate context. Optional or already answered fields are skipped.
A known answer that a control refuses to accept is a technical blocker, not a
reason to ask the user to supply the fact again.
Most answers should come from Simplify, approved facts, defaults or saved answers.
Human input is reserved for genuinely missing required information or an
unresolved verification challenge. Optional history/telemetry failures are
diagnostics; they do not justify repeating a completed write or stopping work.

Check context `human_input.messaging.available`. If the harness actually provides
messaging, use its advertised capability for a brief question under the user's
messaging authorization; do not assume Discord exists or invent a recipient.
Record only an actual reply. Native Hermes `answer` accepts
`answers:[{question_id,answer,expected_revision}]` and attaches current user-turn
provenance. Portable `call <session-id> answer` additionally requires
`reply_evidence`; live `answer_from_user` uses the same fields. Choice answers may
be the exact `{value,label}` object, which distinguishes duplicate HTML values.
Never use the original application request or a prior answer as a new reply.

If no quick reply is available, call `park_questions` with empty parameters.
It saves the blocker and requests browser stop; the host releases the workspace
only after its process tree stops. This is not pause, which retains a slot.
The dashboard's **Needs your answer** view supports Save answers, Save and queue
retry, and Queue all answered applications. Saving is data only. Queued retries
are picked up by an ordinary harness, not a model launched by the runtime.

For an authorized answer batch, native `answer_retries` or portable
`application_runtime answer_retries` lists ready jobs and request IDs. Start each
with its `job_id` and returned `request_id` (CLI `--job-id` and `--request-id`).
On the fresh attempt, use `browser apply_answers` with current observed refs to
apply exact saved answers, then continue the ordinary ATS procedure. No old
browser ref is reusable across attempts. Changed questions/choices need a new
answer. Applied jobs and uncertain submissions cannot enter this retry path.

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
no uncertain submission. For all ATS types, a new session on a previously
attempted job clears the assigned employer origin's cookies and site storage
before opening it. This also applies to a new request/conversation and queued
answer retries. Simplify's separate login and extension state remain; the
runtime does not create a completely empty profile or clear unrelated identity
providers. Readiness records the cleared origin. A paused-attempt attach retains
browser storage. Account, credential and submission history always survive.
Changing conversations alone is not a separate browser-isolation mechanism.
Heartbeats report activity and never extend local
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
