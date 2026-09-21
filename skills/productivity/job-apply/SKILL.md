---
name: job-apply
description: Execute local JobBot applications with Simplify.
version: 0.5.21
author: Rejo Z Mathew (rejozmathew), Hermes Agent
human_first: true
license: MIT
platforms: [linux, windows]
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

## Per-job reminders

Use a fresh conversation for each dispatched job, with its exact selected config,
identity, resume and request ID. Fetch the prepared session's context rather than
depending on another job's conversation. The mailbox handoff can describe the
existing Himalaya account or Gmail wrapper: check and use that actual integration
before declaring email unavailable. Use the configured `email_route` when present: `application_email`
is the form recipient and `verification_mailbox` is the inbox to read through
the existing connection. For forwarded Greenhouse codes those addresses
intentionally differ; personal mailbox access is not required. Search the jobs
inbox for the forwarded message, correlate the original recipient, employer and
request time, and continue verification. The address difference alone is not
an unavailable capability. Preserve the approved form address after Simplify
and reload/refill, before Submit or requesting a code. Email OTPs, verification
links and email-vs-phone choices are not CAPTCHA. Prefer an offered accessible email route; SMS-only
requires a real SMS channel or human input. An actual image CAPTCHA may be recorded
as blocked, but a protection logo alone is not a challenge. Do not expose codes or
mail bodies in progress/history. Use enabled Simplify for bulk fill. When stuck,
capture **and inspect** the owned screenshot using the harness's image/vision tool.

Linux examples use `.venv/bin/python`; Windows examples use
`.venv/Scripts/python.exe`. The configured paths and actual interpreter override
historical Windows path examples. See `docs/jobbot-v1/QUEUE_AND_VM_RUNBOOK.md` for
queue operation and VM environment setup, not as a prerequisite to every job.

After reading this canonical skill, start the configured browser immediately.
Read the required ATS skill while the host prepares the browser; finish that
reading before form actions. Do not put repository exploration, a separate
doctor run, repeated configuration/history inspection or a planning turn before
start. The runtime already performs its own prerequisite checks. Reuse skills
already loaded in this conversation rather than reading them again.

Do not stop at the first recoverable obstacle. Persist within the operator-selected
application deadline: choose a different supported action, execute it, verify its
effect, and resume the ATS runner when progress is made. An empty option list calls
for opening and inspecting the actual menu; use an observed option and verify the
committed selection, not typed search text or a highlight. Repeated mailbox checks
do not replace refresh-and-refill recovery when the documented missing-code trigger
is reached. Before recording blocked, state the unresolved obstacle, actions actually
tried, and current evidence explaining why remaining plausible recovery cannot
proceed. A helper error alone establishes neither employer rejection nor missing
credentials. Do not fill time with unchanged retries or inspections.
The executor owns progress toward the authorized application outcome. Helpers
accelerate routine work; their matchers, retry counts and call budgets do not
define the limits of executor reasoning. On every ATS, `blocked`,
`inspection_required`, an unsupported control or a failed click is a handoff:
read the evidence and offered options, inspect the current DOM/screenshot,
choose another supported interaction, verify its effect and continue in the
same session. Use the LLM to resolve unfamiliar controls and choices; do not
just repeat an unchanged failing helper or convert its result into `finish`.
When a helper offers alternatives, choose among them using approved facts and
the user's permissions, then return that choice to the helper or scoped browser.
If a control you expect is missing, take an owned-page screenshot immediately
and actually inspect it with the harness image tool. Look inside embedded frames,
overlays and inner scroll containers. Compare the image with the structured
inventory; a reader miss is not evidence that the visible control is absent.
Snapshots that miss progress controls may already include `image_path` and
`visual_recovery`; read that image before choosing the next action. Refresh refs
after navigation and use the observed controls in the same session. Before
ending for any unresolved obstacle, inspect a fresh screenshot and attempt the
remaining plausible recovery. If capture fails, recover the browser or use the
available DOM evidence; do not turn the screenshot failure into another blocker.
Do not return a terminal answer after merely announcing the next action. Perform
it, inspect the result, and continue. A CAPTCHA logo or protection notice alone
does not establish an active challenge or justify asking the user to solve one.
Spend additional time on a plausible recovery and record its timing so later
engineering can improve the slow path. Ask the user only for information or
verification actually requiring them. Real ownership, writer settlement,
eligibility and truthful submission evidence still apply. A helper's
inability alone is never evidence that the application cannot proceed.
User corrections are instructions to adjust and continue the authorized task.
An apology or discovery of an executor mistake is not a stop request. Stop only
when the user requests stopping, the saved application deadline expires, or a real application outcome requires it.

Settings controls the overall application time limit: 30 minutes by default,
an adjustable duration, or Off. The runtime returns the frozen deadline in the
session context and enforces it outside the model, including during model calls
and user-input waits. Reloads, reconnects and replacement sessions in one dispatch
do not reset it. Expiry stops the owned executor and releases its browser before
the queue moves on; it does not erase submission evidence or forbid a later retry.

These shared rules apply to all ATS platforms. Respect app-owned controls and
selected profile facts. Use bounded recovery for demonstrated blockers and actual
page evidence. Prefer Simplify for bulk filling, without a redundant full final
audit. Native lifecycle labels are `jobbot start`, `jobbot pause`, `jobbot stop`
and `jobbot finish`; the portable commands below invoke the same services.

## Start in the current conversation

Use native `jobbot(operation="start", parameters={"url":"<eligible-job-url>","wait_seconds":0})`
when available. Otherwise run from this repository using its virtualenv Python:

```text
.venv/Scripts/python.exe -m job_applier.application_runtime start "<eligible-job-url>" --wait-seconds 0
```

The selected private config resolves through `JOBBOT_CONFIG` or the repository's
ignored `artifacts/jobbot-v1-private/runtime-config.json` pointer. An explicit
`--config <absolute-json>` overrides the pointer. No API token export, dashboard,
claim, lease renewal, port selection or target binding is needed. The service
checks configured identity/resume, eligibility and duplicate history, records
preparing, launches the assigned headed browser and returns a session handle.
Doctor is a separate read-only diagnostic; start performs its own live readiness.
Start returns the durable session while browser preparation continues. Read the
ATS skill now, then check `status`; when connected, retrieve `context` once if
start did not already return it. While preparing, continue waiting on this
session. Never open another browser because readiness is still running.

Start/status returns the detected `platform` and an `ats_reference` path when
available, including while the browser prepares. Read that reference before form
actions: iCIMS uses `references/icims.md`, Greenhouse uses `references/greenhouse.md`,
LinkedIn uses `references/linkedin.md`, and Workday uses the canonical `workday-simplify` skill. Portal detection is a
starting hint; follow the actual page and controls at each step.

Read `next_operation` from readiness/status and fresh browser observations.
Workday routes to `fast_forward` with `{"seconds":60}`. Greenhouse routes to
`greenhouse_advance` with `{"seconds":60}`: Simplify settlement, one eligible
second pass, approved residual batches, grouped semantic questions and shared
submission. See `references/greenhouse.md` for the grouped answer plan and
refresh continuation. Other shared forms use `browser` with
`{"method":"simplify","action":"autofill"}` when Autofill is enabled. Act promptly after readiness. Do not call
the Workday runner on Greenhouse. `browser_observe` accepts empty parameters;
`method` belongs to `browser`. After execution begins, status requests a fresh
observation instead of reusing the original document's Autofill control.

For iCIMS use `icims_advance` with `{"seconds":60}` in this owned session. It
settles the writer, audits current required/invalid work, privately fills missing
credentials, batches approved residual answers and advances the observed stage.
A slice or unfamiliar control returns a handoff; continue the same application.
Return unfamiliar questions together using `answers:[{ref,question_key,answer,basis}]`.
Use approved facts; never infer No for prior employment or relatives.

Use `browser` with `{"method":"audit"}` for compact post-autofill evidence.
The same `audit` is included in snapshots and shared post-autofill handoffs.
Act on `required_missing`, `invalid_blockers` (including invalid optional values)
and private `credential_tasks`. Ignore `optional_ignored`; Simplify review rows
are advisory and do not require repeated Autofill. Unknown presence or incomplete
coverage needs targeted inspection, not fabricated emptiness. Filled values and
secrets are not repeated in the compact audit. Audit is read-only; current writer
and ownership checks still govern writes. Do not reload an otherwise usable form
because a review counter is nonzero. Use the existing ATS runner to advance.

For routine residuals on any portal, a browser snapshot includes
`remaining_required`, validation, `required_evidence`, approved contact facts in
`answer_context.identity`, and exact supported operation shapes. Use one browser
call with `{"method":"repair","fields":[{"method":"fill","ref":"<current ref>","value":"<approved answer>"}]}`;
fields may also use `select` (exact value/label) or `check` (boolean). It verifies
each field and returns a fresh screen. Use approved facts and existing consent
policy; requiredness alone does not supply an answer or permission to consent.
For a file control use `{"method":"upload","ref":"<current file ref>","asset_id":"<selected asset id>"}`.
These ordinary controls should not require source searches or per-employer scripts.
An unresolved route still exposes the owned page's inventory and visual recovery;
follow its current identity evidence instead of inferring identity from a redacted URL.

For confirmed LinkedIn Easy Apply, use `linkedin_easy_apply` with `{"seconds":60}`
in the current owned session. It batches routine fields, approved answers and the
selected résumé, then advances through the dialog under current submission
settings. Resolve returned unfamiliar questions from approved facts with the
current executor and resume the helper. Keep external Apply on its observed
employer URL and existing ATS handler. A missing external URL is not Easy Apply
evidence. Simplify may assist when present and settled; the native LinkedIn helper
also works without it. See [LinkedIn](references/linkedin.md).

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
iCIMS `/jobs/<id>/.../job`, `/login` and embedded page-mode routes retain the
same employer/job identity. Use their current frame refs for Email, Next and
subsequent form controls; an ordinary login transition is not loss of ownership.

The returned `session_id`, job/context, approved assets, account namespace,
workspace and timing are authoritative. Native subsequent operations resolve
that session automatically. The portable equivalent is:

```text
.venv/Scripts/python.exe -m job_applier.application_runtime call <session-id> <operation> --parameters <JSON-or-@private-file>
.venv/Scripts/python.exe -m job_applier.application_runtime status <session-id>
```

Portable operation names include `context`, `report`, `browser_observe`,
`fast_forward`, `icims_advance`, `linkedin_easy_apply`, `credentials`, `browser`, `restart`, `event`, `progress`, `record_account_event`,
`report_upload`, `submission_intent`, `finish`, `request_mail_for_attempt`,
`match_mail_for_attempt`, and `account_lock`. No attempt/fence/target/CDP fields
belong in their parameters. Native `milestone` maps to `event`, `observe` to
`observe_owned_lesson`, `mail_request`/`mail_match` to the matching mail operations.
Native `context`, `report`, and `browser_observe` accept empty parameters.

## Execute

### Approved earliest start date

The user's standing default for earliest anticipated start date / availability
to start a new job is **14 calendar days from today**, when no more specific
approved value exists in the selected profile, saved answers or lessons.
Calculate it from the current date in the user's configured timezone when
answering the form, including month/year rollover; do not reuse a date calculated
for an earlier application. For a field requesting **MM/DD/YYYY**, enter the
calculated date in that format. For separate month/day/year controls, enter the
same date's components. This is an approved answer, so a missing explicit date in
the profile does not require asking the user. This availability default concerns
starting the prospective job; employment-history and education dates still come
from their approved facts.

1. Verify the actual role remains eligible and the selected identity, account
   email, contact email, resume and mailbox are the approved ones. Exclusions,
   unknown required facts remain binding. A previous unfinished attempt does not
   block this newly requested attempt; only recorded successful submission does.
   At a posting or application-method chooser, prefer an observed enabled
   Apply Manually, then Apply Now/Apply for this Job/Start Application/Apply.
   Follow the direct application link before an optional Chat to Apply or
   chatbot route. This includes an employer-branded landing page linking to
   Workday. Do not select chat while a direct application route is available.
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
4. Prefer enabled Simplify Continue Application after settling over nonblocking
   review warnings, source repair or optional field inspection. A populated
   dropdown stays populated even if Simplify says needs_review. Advance first;
   repair it only for an actual employer validation error or incorrect known fact.
   On Workday, if Simplify Continue is unavailable or failed to advance, use the
   page's available Autofill once before manual repair, then try Continue again.
   Return every new page to the normal Simplify flow after handling an exception;
   a manual questionnaire does not make later pages manual, including Self Identify.
   Handle only actual required blockers and material identity/document errors.
   Use approved facts; never fabricate screening answers or reconstruct history.
5. For exceptions, `browser` methods are `snapshot`, `screenshot`, `click` (observed `selector`),
   `fill` (`selector`, approved `value`), `press` (`key`), `reload`, `navigate` (`url` in the
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
   Separate selected labels/chips count as committed answers even with an empty
   search input or open menu. Typed filter text and highlighted options do not.
   Preserve an existing correct selection. For a keyboard correction pass the
   intended `label` (and `value` if known) with `press`; inspect `committed` after
   read-back. `pressed:true` or `execution:executed` alone proves no answer.
   A mismatch returns the actual selection and scoped options for recovery.
   Veteran and disability fields use this same API and approved facts.
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
6. Use the configured approved resume through Simplify during filling. On an
   actual missing/rejected-resume error, immediately capture **and inspect** the
   owned screenshot. A displayed filename or Simplify Completed checkmark can
   coexist with an employer upload rejection. After writer settlement, use the
   Resume/CV widget's observed Remove/Cancel/X control to clear that attachment,
   reveal its Attach/file input, and use `browser upload` with the selected asset
   and a fresh ref/selector scoped to **Resume/CV**. If no attachment is present,
   use its observed Attach/file input directly. A lone file input may belong to
   Cover Letter while Resume/CV's input is absent until removal; inspect its
   field association rather than using a broad `input[type=file]` selector.
   Verify the resulting attachment and current employer feedback, then continue
   submission. Some widgets clear the raw file input after ingesting the upload;
   an empty `files` list alone is not a reason to upload again. Resolve the
   visible resume error through the widget instead of repeating Submit or
   rediscovering why the filename and validation disagree. If the widget stays
   stuck, use the broken-page recovery below. Keep validation
   messages intact so the next observation reflects the actual employer state.
   Report only uploads performed through that helper; do not manufacture an
   upload event for an attachment Simplify supplied. At Review with no employer
   upload error, proceed directly to the enabled Submit control: no attachment
   search, scrolling audit, re-upload,
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
   In an `existing` browser workspace it closes only this application's tab and
   its popups, preserving the user's browser, dashboard, mail and other tabs.
   Record the actual blocker and finish the attempt before reporting it in chat;
   a chat response alone does not release the application tab. Helper misses
   still require the recovery described above, rather than premature finish.
   A missing post-click confirmation is `submission_unknown`, an observation
   rather than a restriction on continuing the application.

After an uncertain click, inspect the current screenshot, fields, verification
and confirmation. Complete unfinished work using the existing form and private
mailbox operations, then submit the current form when appropriate. `browser
submit` without a target observes confirmation only. A targeted submit or another
Workday advance can follow the current page; each call activates Submit at most
once. A previous click does not disable edits, answers, credentials, reload,
restart, pause or resume. The session stays open until completion, Stop, or an explicitly
configured maximum runtime. A proven `not_executed` Submit returns recovery,
not submission uncertainty: refresh the control and continue in the same attempt.
An intent with a missing dispatch result remains uncertain. `stop` closes
immediately. `reconcile` accepts `outcome`,
`evidence`, and `source` (`employer`, `simplify`, or `user_reported`); cite the
actual user's confirmation when using user_reported. It stops a still-owned
session before correction and preserves the original attempt duration. Portable:
`application_runtime reconcile <session-id> --outcome applied --source user_reported --evidence "<actual confirmation>"`.
Reconciliation never submits or creates a retry. Cross-job URLs are not proof.

`application_incomplete` includes observed remaining fields, verification or
validation feedback. Continue that work in this session. It is not a final
outcome and needs no special rejection proof or operator unblock. The helper
uses the existing field inventory, skips optional fields and does not require
an internal resume-upload receipt. Historical clicks remain recorded. Only
accepted confirmation establishes success; never invent confirmation or label
an old click as not executed merely to justify continuing.

Managed headed sessions start maximized; existing-browser sessions retain the
user's window. Obscured clicks return viewport/covering metadata
and use only an uncovered point on the actual control. Inspect and use an observed
panel collapse control if needed; never force through an overlay. Completed workspaces retire their owned background host;
parallel sessions retain their independent hosts and browser processes.

For a broken page, recover it instead of finishing blocked.
This applies to Workday, iCIMS, Greenhouse and proprietary portals alike. A
missing Simplify panel is also a recovery case: inspect the current page and
whether it is still loading, then refresh if the extension did not initialize.
Check again after reload; use session `restart` if still unusable.
In an existing-browser workspace `restart` replaces only the application tab
within the same attempt; it never restarts the user's browser. Diagnose
an extension login/setup issue when the UI shows one. Use approved native
controls where supported after fresh writer observation, without reconstructing
career/education history. Neither missing Simplify nor a helper timeout is by
itself grounds to finish blocked; choose the next recovery from actual evidence.
After a reload, let the application and extension initialize and inspect the
fresh result. `recovery.status:recovered` means resume normal application work.
`loading` means wait and reobserve this page, not another refresh or restart.
Once the old error disappears and the page has usable controls or progresses,
that recovery is finished. Another reload/restart needs a new, currently observed
failure; never keep recovering from an error that existed before the refresh.
Use `browser` with `{"method":"reload"}` when the employer requests a refresh
or the current page evidence supports it. This deliberately cancels the old
document; an unknown Simplify writer and a missing Stop/Cancel button do not
prohibit this recovery. The runtime verifies document replacement, then new
observations govern form writes. Inspect and restore unsaved fields as needed.
If refresh fails or the browser remains unusable, call `restart` with empty
parameters. The host stops its owned browser and reopens the assigned job with
the same profile, session and attempt. Read status until connected, inspect the
page, recover sign-in/form progress and continue. A helper's automatic recovery
limit hands the decision back to the executor; it does not forbid another
evidence-based recovery. Inspect actual submission evidence as part of choosing
the next operation; historical click uncertainty never locks the browser. New
user application requests follow the shared retry policy.

The missing-email refresh-and-refill trigger applies **only to Greenhouse**,
only when its requested email verification code is absent from the configured
mailbox. For this Greenhouse recovery,
compare the approved address with the actual form/verification recipient, check
the configured mailbox including spam/junk and delayed delivery, and use an
observed resend when available. If no matching code arrives within about **1–2
minutes of the employer's code request**, refresh the owned application tab with
`browser reload` and continue in the same attempt. Track elapsed time from that
request across polls and conversation compaction; repeated mailbox reads or a
resend do not restart this recovery window. This is a prompt to change recovery,
not an application time limit or a reason to finish blocked.
For Greenhouse, use `greenhouse_advance` with
`{"seconds":60,"recovery":"missing_verification_email"}`. This calls the shared
owned reload and immediately resumes Simplify, approved residuals and submission.
Continue from its current result; if the call slice ends, resume ordinary
`greenhouse_advance` without repeating the recovery parameter. A reload replaces
the old verification screen: its screenshot and blocker no longer describe the
current page. Finish the new fill/submit cycle and inspect the employer response.
That is an ordinary page recovery; an earlier Submit click or email prompt does
not prohibit it. A mail-request ledger entry records a request and does not send
or resend employer mail. Follow actual page controls for delivery.

After refresh, let the new page and Simplify initialize. If autofill starts
automatically, observe it until settled; otherwise use its enabled Autofill.
Repair the remaining required fields from approved facts (including conditional
questions), handle a renewed upload error as above, and continue to Submit in
configured submit mode. Refresh may discard unsaved answers or invalidate the
old code: use fresh refs and any new verification request. If the same obstacle
recurs, inspect the new evidence and choose the next plausible recovery rather
than refreshing on a timer. This does not predict or bypass a security challenge;
handle any verification the refreshed page actually presents. Once accepted
confirmation is observed, record it and finish.

`finish` parameters are `{"outcome":"blocked","evidence":"<observed reason>",
"quiescent":true}` (or another supported truthful outcome). Do not add invented
fields. `context` and `report` remain readable after the browser host has stopped.

## Missing required answers

This decision sequence applies to every ATS and proprietary application form.
Read the complete question and offered choices, use the selected profile's
standard answers/defaults and other approved facts, and consult saved answers.
The shared screen's `answer_context` exposes those standard answers and core
preferences; the remaining approved profile is in the application context.
Decide answers for the page together where practical, actually enter them with
the available form tools, and verify that they commit. If a known answer fails
to commit, refresh the control, inspect its options, follow child menus or use
another supported interaction and continue. A review count, Select One label
or failed helper is unfinished work, not evidence that the user must answer.
Only information still genuinely unknown after this process belongs in the
human-input workflow. A final blocker is the last resort for an evidenced
obstacle remaining after executor recovery. These judgments belong to the
executor; no universal yes/no answer is manufactured by the helper.

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
answer. Recorded successful submissions are excluded from this retry path;
unfinished attempts, including submission-unknown history, remain retryable.

## Mail and private identity

Read the verification email using the configured mailbox handoff (Himalaya or
the existing Hermes Gmail integration). The LLM
identifies the relevant message and extracts the code. With multiple relevant
messages, choose the one closest to the observed request timestamp. If the email
has not arrived on Greenhouse, check delayed delivery within the approximately
1–2 minute window from the employer's request, then use the Greenhouse-only
refresh-and-refill recovery above. On other ATSs, follow their actual verification
controls; absent mail alone does not trigger a reload. Continue this same application. A helper miss does not
mean the user must retrieve or enter the code, and does not end the application.

Enter the selected code with ordinary `browser fill` on the observed input refs,
or use the convenience operation `credentials` with `mode:"verification"`,
`action:"fill"`, ordered observed `refs`, and `value` set to the code. The
`challenge_ref` is optional metadata. Group detection, guessed length and code
format do not approve entry. `action:"inspect"` suggests current groups; `action:"resend"`
uses an observed resend control when needed. The fill helper enters the supplied
code and reports whether the fields accepted the write. It does not read the mailbox,
classify the delivery channel or decide whether a message is allowed. The
challenge ref describes an observed group; it is not an entry permission or email correlation token.

Use the normal submit operation after entering the code. The employer's response
determines whether it is accepted or expired. If rejected, inspect the latest
email or request another code and continue. Keep codes out of progress messages,
reusable answer history and user-facing summaries; do not create a human-answer
queue item for email the executor can read. Code fields remain excluded from
answer history and masked in private screenshots, without prohibiting entry.

The selected config supplies `gmail_script` and `mailbox_token_path`. Use the
existing mailbox capability from the same conversation:

```text
.venv/Scripts/python.exe -m job_applier.hermes_gmail --script <configured-script> --token-file <configured-token-file> gmail search <narrow-query> --max 5
```

The same prefix supports `gmail get <message-id>`. This invokes the existing
Hermes Gmail script with the selected mailbox credential. The LLM reads the
message and decides which code fits the current application; no JobBot mailbox
verifier runs during field entry. Use codes/links privately; never log mailbox
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
page ID. Retry starts a fresh attempt from the beginning and closes the older
application workspace: the owned browser in managed mode, or only application
tabs in existing-browser mode. It requires no submission reconciliation
or proof that the previous attempt was not submitted. This is the same policy
for every ATS and proprietary URL. The runtime matches the URL to the existing
job, classifies `application_kind` as `first_attempt` or `reattempt`, retains
previous attempts, and suppresses ordinary duplicates only for recorded success.
Native start calls use the observed user turn as request identity when available.
Repeated calls in that request reuse its session. Portable callers may supply
`--request-id` for a distinct request; `retry` explicitly requests a fresh attempt.
Without a request ID, start reuses this driver's active session and creates a new
one once it ends. A new conversation starts its own attempt. Distinct requests
can use distinct configured browser workspaces for the same posting or account;
an ordinary new request does not stop another request. Existing-browser sessions
retain cookies and site storage because other user tabs share that profile;
only application-owned tabs are replaced. In managed mode, for all ATS types, a new session on a previously
attempted job clears the assigned employer origin's cookies and site storage
before opening it. This also applies to a new request/conversation and queued
answer retries. Simplify's separate login and extension state remain; the
runtime does not create a completely empty profile or clear unrelated identity
providers. Readiness records the cleared origin. A paused-attempt attach retains
browser storage. Account, credential and submission history always survive.
Changing conversations alone is not a separate browser-isolation mechanism.
The authoritative decision table and caller responsibilities are in
[RETRY_POLICY.md](../../../docs/jobbot-v1/RETRY_POLICY.md).
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

Prefer the `progress` convenience operation for executor activities:
`{"stage":"remaining_questions","task_id":"source","activity":"Review and fill How did you hear about us?","state":"in_progress"}`.
It supplies valid event identity and UTC time. Stages are `opening`,
`authentication`, `fill_application`, `remaining_questions`, `email_verification`
and `submission`. Task states are `in_progress`, `completed`, `recovering`,
`awaiting_input` and `unsuccessful`; `completed` requires actual `evidence`.
Reuse the task ID through recovery. Describe what the application needs, using
question labels without answers. Reserve `awaiting_input` for an actual missing
human answer. Shared field, private verification, Workday and submission helpers
record their semantic activities automatically. Supply intent they cannot infer.
The portal groups tasks before limiting recent history, keeps completed stages
compact, preserves expansion on refresh and places technical chronology in
collapsed Debug details. Old attempts may honestly show Details not recorded.

A helper exception is not an employer rejection. Record `event_type:"recovery"`
with its observed `error_type`, concise `evidence`, and the safe `next_step`.
Use the existing scoped browser/credential tools for a supported exception path
when possible; keep Simplify as the bulk filler. Do not finish merely because one
helper failed or its bounded call ended. Continue executor-led recovery using
the current screen, alternative controls and actual offered choices. A failed
matcher is a technical limitation, not missing candidate information. If an
actual obstacle remains after these alternatives, record its evidence, what was
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
helper update; do not edit the helper during the application. Inspect an uncertain
account-creation action before choosing account recovery. Application submission
follows the shared current-form continuation policy above.

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

### Explicit stop and manual completion

When the user says stop or reports that they finished this application, issue
the existing structured `stop` immediately. Do not take another application
screenshot, audit, or recovery action. After stop acknowledgement, use the
existing reconcile operation with `source:"user_reported"` for their completion
report. Preserve the stop time and report source; do not claim employer
confirmation or invent an executor Submit timestamp.
