# Greenhouse recovery and application progress plan

Status: implemented and validated September 9, 2026; final managed suite: 761 passed, no failures or skips.
The six tracks below were authorized for implementation after the original saved
plan and checkpoint regression. The original evidence and design are retained
here for traceability. Implemented contracts and helper ownership are documented
in [Application runtime](APPLICATION_RUNTIME.md#shared-recovery-and-progress-contracts).
This work uses synthetic fixtures only; it does not change attempt 45, retry a
live application, access live mail or backfill production records.
[Implementation validation](GREENHOUSE_RECOVERY_VALIDATION_2026_09_09.md) records the checks and fixes.

Follow-up policy: [Shared application requests and retry](RETRY_POLICY.md)
supersedes this plan's cross-attempt uncertainty restrictions. Any new requested
attempt is allowed unless success is recorded; fresh rejection proof remains
useful for correcting and continuing within the same attempt. The 761-test result
belongs to checkpoint `184717e`, before that follow-up. No new tests or regression
runs were authorized for the retry-policy change.


## Intended result

An executor given a Greenhouse job URL should start Simplify promptly, preserve
answers it already filled, complete actual residual questions, obtain supported
email verification through the configured mailbox, and recover from an explicit
form rejection without confusing it with a lost submission response.

The portal should identify the company and role and show useful progress at two
levels: broad application stages and meaningful tasks within each stage. Regular
users see activities such as **Review and fill “How did you hear about us?”** or
**Fill veteran status**. Helper names, control-selection attempts, technical
failures and verification mechanics belong in collapsed **Debug details**.

This is a shared-runtime improvement with Greenhouse-specific recognition where
needed. Keep the existing browser interface and executor; do not introduce a
second dropdown engine, separate outcome database or Greenhouse agent.

## Evidence from attempt 45

Read-only evidence: the selected managed database, retained executor tool calls
and results, private answer-history metadata, and retained browser screenshots
for Philo's Head of Data application. Private files, candidate answers, mailbox
contents and verification codes are not copied into this plan or Git.

| Observation | Finding and implication |
| --- | --- |
| Session requested at 16:50:58.934 UTC; connected at 16:51:06.654 | Managed startup took about 7.7 seconds. The logs do not establish a browser-load failure. |
| First Autofill click at 16:52:03.293 | About 56.6 seconds elapsed after connection. Before the click, the executor invoked Workday-only `fast_forward` on Greenhouse and passed an unsupported `method` argument to `browser_observe`. Both failed. The successful observation exposed enabled Autofill, which the next action clicked. |
| Veteran status used shared `browser select` | The result was `committed:false` with empty value and label. This was a verification-path failure, not simply forgetting the shared select interface. The current code reaches this result after selecting the matched option and reading it back. |
| Subsequent native inventory still reported the field absent | Retained visual evidence shows a displayed selection while the inventory reports an empty input. The generic selected-value reader does not handle a separate selected label in this kind of combobox. Exact DOM structure remains to be reproduced synthetically. |
| Disability used click, fill and Enter, then ArrowDown and Enter | No shared `select` call was made for this field. The final submission screenshot shows a different option from the executor's stated intended choice. Keyboard activation succeeded, but the intended answer was not verified. This is a correctness issue, not only delay. |
| Executor requested human handling of the security code | The page described an emailed eight-character verification code. The canonical skill already documented configured Gmail. Before the user reminder, the executor instead tried the human-question route, which correctly rejected a private verification question. |
| User reminder arrived roughly 48 minutes later | Gmail recovery followed the reminder. The executor first used the wrong CLI argument layout, then the configured wrapper. There was also a mistyped field ref while entering individual characters. |
| Employer displayed “Invalid security code” after Submit | The retained submission screenshot confirms a form rejection message. Age-related expiry is plausible, but the logs do not establish a provider TTL or prove expiry as the cause. |
| Reconciliation changed the outcome to blocked, then failed; retry stayed prohibited | `submission_pending` consults the latest submission-click dispatch event, which remains `possibly_executed`. It does not consume the reconciliation outcome. Thus changing the outcome label cannot resolve the retry guard. |
| No successful phase or field-context events; 57 tool-finished events | The attempt has recovery/error events and tool records but lacks meaningful task attribution. Every managed action has empty semantic context. One attempted progress event omitted required event ID and time and failed. |

The result remains a failed, unconfirmed application with explicit rejection
evidence. This planning task does not reconcile it again or authorize a new live
attempt. Absence of a confirmation page alone must never prove non-acceptance.

## Why company and title are missing

The recent URL-only start path calls `Service.intake` without company or title.
The inserted `jobs` row therefore has null labels. Re-intake of an existing job
does not fill those missing labels either. `renderSessions` reads this row and
renders “Company unknown”; the queue and attempt report read the same data.

The application already discovers useful metadata: private answer-history
metadata for attempt 45 contains Philo / Head of Data, and attempt 44 contains a
company and Head of Data Governance. `capture_answers` adds these values to a
copy of the application package and saves the private history; it never updates
the authoritative job record. `browser_observe` also returns the stored company.

Git history places URL-only intake in `497689c` and private-history enrichment
in `0afbf59`, both before the latest `68a7865` checkpoint. The inspected code
supports an incomplete metadata-persistence path; it does not show the latest
credential changes erasing previously populated company names.

## Authorized design and implemented scope

### 1. Route initial filling from observed platform and controls

- Return a compact, actionable next operation from session readiness/status:
  Workday uses its existing runner; Greenhouse and other shared forms use the
  existing Simplify observe/click boundary. Include the correct parameter shape.
- Read the ATS reference during browser preparation, then act on an enabled
  Autofill control as soon as the owned page is ready. Avoid skill searches,
  unrelated runner calls and repeated context reads on the critical path.
- Derive guidance from the actual observation. A settled page with enabled
  Autofill should say to fill; generic loading/recovery guidance should not be
  the only instruction returned for that state.
- Preserve ownership, document identity and writer settlement. Use the existing
  reload/restart recovery for an evidenced unusable page. Attempt 45 does not
  justify a new automatic reload rule or a longer startup timeout.
- Record startup readiness and first Autofill dispatch independently so the
  portal can distinguish browser preparation from executor delay.

Likely files: `application_runtime.py`, `managed_runtime.py`, `workspace_host.py`,
`simplify_boundary.py`, canonical job-apply and its Greenhouse reference. Extend
the current contracts; no new Greenhouse fast runner is proposed.

### 2. Make shared dropdown read-back describe committed selection

- Retain `browser select` as the single executor-facing interface. Extend the
  shared field reader for widget-contained selected labels/chips separate from
  the search input. Associate the label with the specific control and document.
- Inventory, `inspect`, already-answered detection, answer capture and
  `verify_select` must agree on the selected value. An empty search input does
  not mean an empty answer; typed filter text and a highlighted menu item do not
  by themselves establish a committed answer.
- Preserve a committed answer even when the menu is open. The executor should
  skip already answered residuals unless an explicit correction is intended.
  Do not treat Simplify's review count or a missing HTML `required` attribute as
  the full list of employer-required fields.
- Keep native SELECT and associated ARIA menu selection, including embedded
  forms. Continue excluding unrelated menus such as the phone country picker.
- After pointer or keyboard activation, reacquire the control if rerendered,
  wait for a bounded stable read-back, and compare the exact intended option.
  A successful key press, enabled Submit or nonempty field is insufficient.
- For a failed verification, return distinct execution and answer results:
  whether activation occurred, whether the intended answer is committed, and
  why verification failed. Supply scoped current options and existing selection
  to the executor so it can recover without blindly reopening or toggling.
- Document that disability and veteran questions use the same shared interface
  and approved facts. Do not add a fixed answer or choose an option by index.

Likely files: `browser_helpers/form_controls.js`, `browser_controls.py`,
`browser_frames.py` only if routing needs adjustment, `application_answers.py`,
canonical job-apply and its Greenhouse reference. Preserve Workday's existing
selected-chip and source-prompt behavior.

### 3. Handle supported email verification promptly and privately

- Recognize an emailed security code separately from a visual CAPTCHA or
  unsupported MFA. Expose mailbox availability and the exact configured wrapper
  invocation in the scoped recovery handoff; never ask the user to remind the
  executor that its already configured mailbox exists.
- Reuse `hermes_gmail.py` and the selected configuration. Correlate the message
  with the portal/employer, intended recipient, purpose and current challenge
  request time. Do not accept an unrelated or merely newest message.
- Track challenge/request/message timing without logging code content. After
  a long interruption, follow the observed resend/new-challenge control and use
  its fresh correlated message. Do not invent a universal expiration duration.
- Finish outstanding form corrections before consuming a fresh code, then
  fill and submit promptly under existing submission authorization. A private
  code should not be parked in the ordinary human-answer queue.
- Add a narrowly scoped verification mode at the existing private-credential
  boundary for one input or an observed segmented group. Resolve a transient
  secret privately, validate all refs/group/length before mutation, fill in one
  bounded operation, and return only per-group commitment/error evidence.
  This mode must remain separate from reusable password/account storage.
- Cover every segment in code detection and redaction, including fields whose
  own label is empty or only “Security code.” Exclude values from standard
  fill arguments, progress events, exception strings and answer history.
- Keep genuine unavailable CAPTCHA/MFA as an executor handoff with its specific
  evidence. Mail retrieval does not bypass a challenge or expand account access.

Likely files: `hermes_gmail.py`, `managed_credentials.py`, existing runtime/host
dispatch, `browser_helpers/form_controls.js`, `managed_redaction.py`,
`application_answers.py`, canonical job-apply and its Greenhouse reference.
Define the opaque verification-value contract before implementing it.

### 4. Represent explicit employer rejection separately from click dispatch

The table describes the semantics. The implemented ledger projection uses
`none`, `not_executed`, `pending`, `rejected` and `accepted`; the browser returns
`submission_rejected` when a captured rejection resolves its dispatch.

| Dispatch/result evidence | Submission interpretation | Next action |
| --- | --- | --- |
| Click proven not executed | No dispatch | Recover the control and retry through the existing boundary. |
| Click occurred; current employer form explicitly rejects that submission | Employer rejected the attempt | Persist rejection tied to that dispatch, correct the field/challenge, and permit a new authorized submission intent. |
| Click may have occurred; response lost or no conclusive result | Submission unknown | Preserve pending state; inspect/reconcile before any resubmission. |
| Accepted employer or configured confirmation source | Submitted | Finish once and suppress duplicates. |

- Extend the existing capture in `submission.py` to retain structured employer
  validation evidence as well as confirmation. For Greenhouse, inspect the
  current challenge rejection in the assigned form after the relevant click.
- Tie rejection to attempt, action/intent, document/frame and observation time.
  An old error, error from another widget, generic failed helper, missing
  confirmation or an arbitrary `failed` outcome must not unlock retry.
- Preserve dispatch truth: do not relabel an executed click `not_executed`.
  Record an explicit rejection resolution, including source and evidence.
- Make `submission_pending`, reconciliation, local retry, duplicate suppression
  and the host write guard consume the same resolved submission state. Retain
  historical intent/dispatch/reconciliation events.
- Allow correction in the same owned session when explicit rejection is
  established. If the session was stopped, permit a fresh managed attempt only
  after the corresponding rejection is resolved in the ledger.
- Keep contradictory success evidence and unresolved transport loss protected.
  A claimed `failed` label without adequate submission evidence is insufficient.

Likely files: `submission.py`, `managed_shared.py`, `managed.py`,
`managed_context.py`, `application_runtime.py`, `workspace_host.py`, existing
retry/history consumers and additive migration only if the contract requires it.
Document the common state contract in `APPLICATION_RUNTIME.md`.

### 5. Persist verified company and role in the authoritative job record

- Reuse metadata already observed during normal page readiness/filling. Prefer
  verified posting metadata; accept an unambiguous Simplify job card associated
  with the owned requisition and retain its provenance. Do not guess the employer
  from a tenant slug or confuse a legal entity with a parent brand.
- Add an idempotent metadata-enrichment operation on the existing service. Fill
  missing labels without replacing explicit/nonempty labels, changing job
  identity, creating another job or rewriting application outcomes.
- Route normal shared and Workday observations through this operation. Private
  answer-history output is an audit artifact, not the dashboard's primary store.
- Enrich after startup without delaying browser launch. Refresh session, queue,
  focused-job and attempt-report views from the same stored labels.
- Provide a separate previewable backfill for missing historical labels using
  retained evidence matched to the exact job. Report conflicts, skip ambiguous
  records and retain the source. Do not automatically mutate production history
  as part of tests, a migration or this planning task.
- While discovery is pending, show the posting hostname/link and “Identifying
  company and role.” After an unsuccessful lookup, expose an honest unavailable
  label with the posting link rather than a raw job UUID as the main heading.

Likely files: `managed.py`, `application_runtime.py`, `managed_runtime.py`,
`application_answers.py`, `browser_helpers/form_controls.js`, `workday_fast.py`,
`managed_views.py`, `managed_reports.py`, `static/jobbot.js`.

### 6. Show application progress; keep implementation details in debug

The user's clarified requirement is the presentation contract:

| Level | Default view | Example |
| --- | --- | --- |
| Broad stage | Visible | Fill application; Complete remaining questions; Verify email; Submit application |
| Meaningful task and state | Visible under its stage | Review and fill “How did you hear about us?”; Fill veteran status; Retrieve verification email; Email code rejected, requesting a fresh code |
| Technical action and evidence | Collapsed Debug details | Shared dropdown handler; associated menu; pointer selection; committed-value verification; recovery reason; duration |

- Express tasks as what the application needs and what the executor is doing.
  “Fill veteran status” is ordinary progress, not automatically “Your action
  required.” Reserve user-action language for an actual unresolved request.
- Show task state such as in progress, completed, recovering, awaiting your input
  or unsuccessful. Mark completion only from evidence appropriate to the task;
  a dispatched select/Submit click is not answer/application success.
- Use existing semantic context and events with stable stage/task IDs, parent
  relationships, action linkage, observed start/end and structured result.
  Enrich existing producers rather than adding a second progress log.
- At browser/helper boundaries, derive the field question from the current
  scoped control and attach task context automatically. Retain handler, method,
  fallback, execution result and verification result for debug. Capture the
  executor's intended task through the existing event interface when it must
  supply meaning the helper cannot infer.
- Supply a valid progress-event convenience contract so missing `event_id` or
  `observed_at` does not discard ordinary progress. Keep source, event identity
  and timestamp validation for externally supplied observations.
- Project stages/tasks before applying the compact-session limit. Current
  `session_status` fetches only 12 raw events from a narrow type list; adding
  field events after that cutoff would still lose meaningful context.
- Collapse repeated observations and unchanged retries beneath the relevant
  task. Preserve raw chronology in debug. Expand active/unresolved tasks by
  default; keep completed stages compact and preserve expansion on refresh.
- Use semantic outcomes to resolve earlier technical errors in the display.
  Do not let a past recovered exception remain the session's apparent blocker.
- Preserve elapsed wall time. Distinguish browser startup, action time and an
  evidenced wait for user input; do not label every uninstrumented gap as model
  thinking or active helper work. Do not double-count overlapping actions.
- Older attempts may show partial stage attribution with “Details not recorded.”
  Do not invent historical tasks, handler choices, timings or successful results.
- Use question labels, never candidate answers, verification values, credentials
  or mailbox bodies, in both normal progress and debug telemetry.

Likely files: `managed_events.py`, `managed_sessions.py`, `managed_reports.py`,
`managed_runtime.py`, `application_runtime.py`, `workday_fast.py`,
`workday_auth.py`, `browser_helpers/workday_source.js`, `static/jobbot.js`, `static/jobbot.html`
and its stylesheet, plus canonical progress-reporting guidance.

## Implementation order and validation

1. Add focused failing synthetic regressions for dropdown read-back and exact
   post-keyboard commitment; implement shared selection changes first.
2. Correct initial platform routing and automatic metadata enrichment. Keep
   metadata backfill separately previewable and scoped.
3. Implement private email-verification handling and the common explicit-rejection
   state contract together before enabling a retry after code rejection.
4. Implement the stage/task projection and normal/debug views, reusing the
   semantic events emitted by the above changes and existing Workday producers.
5. Update the canonical skills, runtime contracts and helper map for every changed
   caller. Preserve legacy callers until their use is established; a new path is
   not evidence that an older helper is unused.

Acceptance coverage:

| Area | Focused acceptance cases |
| --- | --- |
| Startup | Greenhouse ready with enabled Autofill uses shared filling; no Workday-only invocation; delayed readiness, settled review and active writer retain correct routing. |
| Selection | Separate selected label with empty input; open selected widget; typed search text without selection; multiple/ported menus; duplicate labels; rerender after click; delayed commit; wrong keyboard-selected option; native SELECT; embedded forms; existing Workday chips/source selection. |
| Email verification | Configured wrapper resolves without a user reminder; recipient/purpose/challenge matching; stale and unrelated message rejection; new challenge after interruption; eight segments validated as one group; stale/mistyped refs cause no partial fill; all code values excluded from output/history/logs. |
| Submission | Fresh explicit rejection resolves only its dispatch; correction allows one new intent; failed reconciliation label alone does not; stale/cross-frame error, lost click response and no confirmation remain pending; success still prevents duplicate application. |
| Metadata | URL-only job obtains labels; existing labels preserved; wrong-job/ambiguous observations skipped; repeated enrichment is idempotent; all portal views agree; historical backfill previews conflicts without changing outcomes. |
| Progress | Meaningful stage/task names visible; handler names only in collapsed debug; field result accurately completed/recovering; no repeated poll spam; task grouping precedes truncation; recovered errors close; waits and overlap retain honest timing; legacy records show missing attribution honestly. |

Use repository synthetic fixtures, including minimal combobox DOM, fake mailbox
responses and a local form that explicitly rejects a code. Do not use a live
employer application, copied personal form values or production database edits
as fixtures. Existing test homes include `test_application_runtime.py`,
`test_embedded_forms.py`, `test_events.py`, `test_timing_reports.py`,
`test_operator_ui.py`, `test_configured_credentials.py`, `test_local_sessions.py`
and the Workday dropdown/confirmation coverage in `tests/jobbot_v1`.

Earlier current-code regression is recorded in the checkpoint report. This
implementation demonstrated focused synthetic failures, added the bounded
changes and relevant checks, and uses one final managed suite through the repository
virtualenv: `.venv/Scripts/python.exe -m pytest tests/jobbot_v1 -q`. Follow the
repository's configured validation delegation and independently inspect its
results. Any later live acceptance uses a separately authorized real application
and records its actual result; synthetic success is not live ATS acceptance.

## Decisions and limits retained

- Work in the user's original checkout. The checkpoint is local; no push is
  requested. This follow-up implements the authorized recovery and progress changes.
- Simplify remains the bulk filler, and the executor handles exceptions with
  approved facts. No resume reconstruction or new helper edits during a run.
- Dropdown correctness, metadata persistence and clear progress are shared
  responsibilities; provider-specific markup/challenge recognition stays scoped.
- This plan does not assert the original verification code expired, silently
  repair attempt 45, restart its browser, access new mail or retry submission.
- The private verification-value API and rejection evidence schema are documented
  in APPLICATION_RUNTIME.md and validated with synthetic fixtures; they do not
  establish live ATS acceptance.
