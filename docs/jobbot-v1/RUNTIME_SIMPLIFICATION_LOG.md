# Runtime simplification implementation log

## iCIMS route identity and visual recovery - 2026-09-09

The supplied ComPsych transcript and screenshots show two misses: Apply was
visible in an embedded document omitted by structured observation, and the same
job's `/login` step was refused as `job_identity_unresolved`. An attempted
page-mode URL was also refused as `target_job_mismatch`. The hostname detector
already returned iCIMS; its scope matcher still compared generic exact paths and
queries. The executor also stopped instead of inspecting the visible page and
later inferred an active hCaptcha obstacle merely from a protection notice.

Added the stable iCIMS employer-host/job-id comparison to existing identity,
scope, history comparison and binding paths. The existing frame router now
recognizes same-job embedded mode URLs and login transitions without a new frame
service or permission exception. Other ATS comparison paths remain intact. The
shared inventory identifies Apply controls; iCIMS startup requests a snapshot
before Autofill and recommends the observed Apply ref when present.

Start/status exposes the detected platform and required reference even while
preparing. Added the iCIMS reference with the observed frame/Email/Next behavior.
The user explicitly requested visual inspection before abandoning any portal.
Canonical instructions and shared screen recovery now say to capture AND read
the image, inspect embedded frames and inner scroll areas, try plausible recovery
and continue. Shared snapshots automatically attach masked image evidence on
missing progress controls, structured/frame inspection failures or unresolved
page identity. Enabled Simplify advancement remains a valid progress control.
No screenshot proof/approval gate was added to finish or form entry. A CAPTCHA
notice alone no longer justifies requesting a human challenge response.

No live application/mailbox was used as a fixture or modified. The configured
history was opened read-only for table names; no records changed. No new tests
or regression runs, following the user's instruction. Requested Antigravity
Flash read-only validation could not complete: restricted authentication failed,
headless tool permission was unavailable, and a supplied-diff/no-tools review
timed out without findings. The primary agent reviewed the source and completed
Python/JavaScript syntax and whitespace checks; this does not establish live
iCIMS end-to-end acceptance. Running application hosts were not restarted.

## Credential and submission error-return review - 2026-09-09

Reviewed all credential helper refusals, submission activation/results and the
other error matches visible in the user's two screenshots. Removed code-group
identity/order gating, guessed code length/format, the twelve-ref cap, unknown
metadata refusal, required email/password pairing and rejection of revealed password
inputs. Resend uses its selected control without a
recognized group and does not fail because the post-click group scan is inconclusive.
A successful inspection with no recognized groups is recorded as a successful
read by both the local host and older Hermes caller.
Code-group completion reports nonempty fields without treating `maxlength` as
a required minimum code length. Actual empty-field continuation remains.

Submission's actual click-error diagnostics and current unfinished-field check
remain; the latter addresses the user's earlier premature-submit complaint.
Candidate/account email matching also remains. Automatic approval review rejected
a broader commit removing those two checks along with code-shape validation,
citing wrong-account/incomplete-application risk; this narrowed change retains
the two checks. Code interpretation remains with the executor as explicitly
requested by the user. The legacy Workday
wrapper now hands recovery to the executor; three external-SSO guesses no longer
instruct immediate failure, and an existing account suggests sign-in/recovery.

Retained actual control/transport/configuration failures and existing ownership,
quiescence and confirmation-evidence boundaries. Reasons are itemized in
[ERROR_RETURN_REVIEW.md](ERROR_RETURN_REVIEW.md). No new execution restriction.
Existing obsolete test expectations were removed/aligned; no tests were added
or run, following the user's instruction. Validation is source review, Python
and embedded JavaScript syntax, and whitespace checks only. No live application,
mailbox or production history was used. Running hosts were not restarted.

## Executor-selected email codes - 2026-09-09

The follow-up Philo transcript exposed `verification_delivery_unconfirmed`.
This was a field-label heuristic refusing `kind != email_code` before any
mailbox lookup, not an employer rejection or a failed email/challenge match.
The repository interpreter also lacked the Google client library used by the
existing Hermes Gmail script, while the executor's ordinary Hermes read worked.

Removed the delivery-label veto and the entire automatic mailbox selection/
verification function. The LLM reads mail with Hermes, chooses the relevant
code closest to the request timestamp, and enters it with ordinary browser
fill or supplies `value` to the grouped code-field helper. No sender, company,
template, request-time or multiple-message rule in JobBot approves that choice.
The helper does not read mail. Browser fill no longer refuses code fields;
existing screenshot masking and exclusion from reusable answers remain.

The missing Google library is declared and installed in the repository environment
for the existing Hermes script wrapper. Canonical instructions and the helper map
reflect executor ownership of email interpretation. Three obsolete mailbox-rule
test functions were removed and existing entry expectations aligned. No new tests
or regression runs. No live application or mailbox was used as a fixture.
The user's new standing instruction is recorded in AGENTS.md: obtain explicit
approval before adding any new application-execution restriction or refusal rule.

## Current-form continuation and removal of posting/account locks - 2026-09-09

The earlier same-attempt uncertainty restrictions below are superseded by
[RETRY_POLICY.md](RETRY_POLICY.md). A click is retained evidence, not permission
to freeze a browser. The shared helper reports current unfinished required fields,
verification and validation feedback as `application_incomplete`, and captures
accepted confirmation before finishing. Explicit submission checks delayed
confirmation and activates the current control at most once. Workday and the
older Hermes worker no longer enter permanent confirmation-only mode. Browser,
credentials, answers, reload/restart and pause/resume no longer require a special
rejection-proof unlock. The legacy worker's internal upload-receipt gate is gone.

Independent configured browsers may handle the same posting/account. The global
job-owner check, reservation exclusion, account-use veto and two same-job unique
indexes are removed. Ordinary new requests no longer stop earlier requests;
explicit retry replaces its named session. Host operations queue instead of
failing after five seconds. Posting status preserves accepted success and active
parallel work. Structured correlation IDs survive redaction unchanged.

Canonical instructions, shared helper/caller map and the historical audit notice
were updated. [GUARDRAIL_RESEARCH_HANDOFF.md](GUARDRAIL_RESEARCH_HANDOFF.md) lists
18 concrete earlier/current removals and provides the requested whole-repository
research assignment. It explicitly identifies remaining areas for independent
review; this change does not claim every restriction is gone.

Verification: Python syntax parsed for 18 changed files; both changed JavaScript
files parsed; diff whitespace and source/caller review completed. No new test
cases or regression runs, per the user's explicit instruction. One obsolete
Workday never-resubmit test was removed and existing contradictory assertions
and fixture expectations were aligned. Historical passing suites do not validate
this commit, and no live application was used as a fixture.

The user separately requested correction of attempt 46. Its retained employer
page showed incomplete code verification with no accepted confirmation; an
appended evidence correction cleared pending state while preserving the click,
open attempt and browser. Migration 17 was applied through `prepare_local` with
its integrity-checked backup. The database retained 18 jobs, 46 attempts and
three submission-ledger entries; the two same-job indexes are absent. The
dashboard was refreshed, its authenticated health returned HTTP 200/schema 17,
and the existing dashboard tab was kept open. The application host/browser was
left running; its existing imports change on its normal next start, not merely
because files changed on disk. No new employer submission was performed here.

## Shared retry policy and recovery documentation - 2026-09-09

The current request policy is [RETRY_POLICY.md](RETRY_POLICY.md). Match the URL
to its durable job and start another attempt whenever a new request arrives
without recorded success. Failed, stopped, interrupted and submission-unknown
outcomes are retained as earlier attempt history. They require no special
unblocker or proof of non-submission. This applies to every ATS and proprietary
form, with or without login.

The shared service, local start/retry, native request identity, legacy history
reader and saved-answer queue now follow that decision. New native user turns
distinguish application requests; repeated calls in the same request reuse its
session. Ordinary browser cleanup uses one stop/pause implementation before a
fresh attempt obtains a target. Heartbeats remain telemetry. Pending dispatch
still prevents automatic Submit replay inside its own active attempt. Earlier
entries defending a cross-attempt uncertainty ban are superseded by this policy.

The preceding six recovery/progress tracks were committed at `184717e`:
platform-appropriate initial filling, shared committed-selection handling,
private segmented verification, fresh employer rejection within an attempt,
job label enrichment, and meaningful stage/task progress. Their design,
callers and validation are in [APPLICATION_RUNTIME.md](APPLICATION_RUNTIME.md),
[GREENHOUSE_RECOVERY_PLAN.md](GREENHOUSE_RECOVERY_PLAN.md) and
[GREENHOUSE_RECOVERY_VALIDATION_2026_09_09.md](GREENHOUSE_RECOVERY_VALIDATION_2026_09_09.md).
These documents also distinguish shared behavior from Workday/Greenhouse form
recognition and retain the earlier deployment and evidence limitations.

For the retry-policy follow-up the user prohibited new tests and further
regression execution. Three obsolete test functions representing four cases
were deleted; obsolete blocking assertions were removed from two broader tests.
No new tests were added. Source/diff inspection is the review basis. The earlier
761 passing cases belong to `184717e` and do not validate this later change.
No production attempt was rewritten or live application used as a fixture.

## Proposed shared form recovery and human answers — 2026-09-08

Employer-hosted Greenhouse validation exposed a gap between shared dropdown
operations and access to an embedded application document. The proposed
correction belongs below ATS-specific execution: reuse existing form operations
with verified frame routing, preserve Workday recognition/authentication, and
carry frame submission through the existing confirmation/uncertainty boundary.
Custom-host ATS recognition and same-requisition redirect/identity handling need
observed evidence; neither an ATS label nor matching hostname alone grants form
access. Individual failure narratives remain in the managed database.

The first delivery also aligns existing approved answer defaults with executor
guidance and expands routine privacy consent to observed acknowledgment menus.
Required native questions must remain distinct from optional Simplify review
items. The second delivery is a durable dashboard question queue, with optional
Hermes Discord questions/replies using the same records. Keeping it separate
allows embedded-form fixes to ship without waiting for a new review interface.

The detailed boundaries, test matrix and data ownership are documented under
[planned embedded forms and unresolved questions](APPLICATION_RUNTIME.md#planned-shared-embedded-forms-and-unresolved-questions).
The associated PR must identify its motivating Greenhouse tests and clearly
separate fixture results from live application outcomes. No runtime, policy,
dashboard or Discord behavior was implemented by this design update. Workday's
additional authentication recovery remains deferred.

## Documentation audit and record ownership — 2026-09-08

This log records architecture, implementation rationale, checkpoint commits,
validation and deferred design work. Per-application diagnoses and recovery
narratives belong in the managed database alongside their attempts. Detailed
case notes from the documentation audit have been moved into retrospective
operator checkpoint events; they are available through existing attempt reports.
Original outcomes, timing, account records and execution events remain intact.
README points to this design history and APPLICATION_RUNTIME describes the data
locations, standard ATS-independent request and headless verification limits.

The code checkpoints relevant to the design review are:

| Checkpoint | Design change and reason | Verification / scope |
|---|---|---|
| `40e12f4` | Shared controls/keyboard, action-aware Simplify waiting, profile salary/privacy policy, pre-submit capture, reconciliation and workspace retirement | Focused checks; shared lifecycle and data policy with ATS-specific recognition. |
| `3a8dacc` | Align discovery with the canonical procedure | Remove obsolete benchmark detours from ordinary execution instructions. |
| `1c93616` | Retain auth dispatch results; distinguish pending creation from proven non-dispatch; recognize Workday's matching auth click layer | Focused authentication and account checks; preserve account/attempt history. |
| `0afbf59` | Remove final resume audit, preserve populated answers, retain portal/company-scoped Q&A and accept the completion route | Focused checks; separately attributed submission evidence. Email follow-up remains deferred. |
| `a952cef` | Validate full login redirects; sign in with retained credentials after pending creation; handle Workday's email chooser | Focused scope and authentication checks; no generalization of Workday controls to other ATS. |
| Documentation review | Clarify design versus operational evidence, headless limits and prioritization | Documentation and historical database annotations only; no authentication or browser-mode change. |

Earlier local-session and native-pointer design is recorded below under
`497689c` / `24f9eb3` era checkpoints. The governing split remains shared lifecycle,
approved profile data, private credentials, evidence and generic form operations;
Workday owns its page recognition, account navigation and native auth controls.
Routine work stays with Simplify; the executor handles demonstrated exceptions.

### Deferred: additional Workday authentication recovery

Do not expand the recovery policy solely to complete one repeatedly debugged
application. Evaluate independent occurrence, time lost, successful recovery and
completion benefit. A small matcher correction and a new retry mechanism should
be evaluated separately. Repeated attempts on one job do not establish incidence
across employers, and a changed presentation alone does not establish its cause.

If revisited, any exception must be scoped to the verified active Workday login
form/dialog and its actual control relationships. Keep final application
submission and other ATS outside that exception. The proposed alternate-target
recovery opportunity remains unimplemented. Operational outcomes and detailed
supporting evidence stay with their database attempts, not this design section.

Documentation links, code fences, referenced checkpoints and the diff were
checked. No browser/application or code tests were run for this documentation
review. Headless capability remains separate from full live acceptance.

## Workday login redirect and pending sign-in — 2026-09-08

The shared observer incorrectly revalidated a queryless display URL even when
the full browser URL carried a valid redirect to the same requisition. Display
redaction and application ownership need separate inputs. This defect predates
the previous speed checkpoint; the detailed application diagnosis is in the
managed database.

Observation now validates the full owned URL before and after the read, retains
queryless output, and requires stable full URLs before declaring quiescence.
Unrelated job redirects remain blocked. Workday recognizes the native email
chooser and handles its return after creation. A saved pending creation, even
from an earlier attempt, can use retained credentials for bounded sign-in;
the registry remains pending until authentication succeeds. Rejected credentials,
verification challenges and repeated uncertain sign-in still return precise
exceptions. The canonical skills describe this flow and distinguish chooser
navigation from credential submission.

Validation: four focused regression cases failed before the fix; all 63 selected
observation, authentication, mapped-recovery, advancement and URL-scope checks
passed afterward (9.53 seconds). No broad suite, new browser fixture or live
application was run. Original application and account history were retained.

## Magellan successful run and review overhead — 2026-09-08

The user repeated the application with Luna Medium. Attempt 27 executed Submit
once, and the user observed Simplify success and received employer confirmation
email. Reported end-to-end time was 541.08 seconds including 6.47 seconds of
startup; the managed attempt duration was 534.70 seconds. Native dropdown
recovery and authentication worked. The remaining confirmation failure was local:
the exact same-portal `jobTasks/completed/application` destination was excluded
from observation scope, so the collector could not read Simplify's installed
"Application Submitted!" message. The route now permits confirmation reads only,
and private evidence retains the last post-submit URL for future diagnosis.

Review-to-submit took about 77 seconds because the runner demanded resume
evidence, followed by an upload-ledger lookup for a Simplify-supplied attachment.
The user explicitly removed that final review requirement: authorized Review
submits without a resume/field audit. In `needs_review`, enabled native Continue
preserves populated source answers such as LinkedIn instead of reopening
Simplify's review menu. Already-selected closed dropdowns return without a click.
The observed PageDown helper gap is also fixed.

Questions and observed answers are retained during filling/advancement in the
existing private spool, with company, portal, ATS, job, attempt/session, timestamp,
source and any recorded answer basis. This reuses shared form controls and does
not infer new profile facts or run an additional final review. The 13 application
questions from attempt 27 were recovered into a readable private history with
retrospective provenance. The outcome was reconciled as `applied` from the user's
report, preserving timing and original diagnostic events. Email confirmation
checks around 30 minutes later, and subsequent rejection/interview/recruiter
status updates, remain documented follow-up work.

Validation: 51 focused scope, advancement, answer-history, authentication and
mapped-recovery checks passed (2.93 seconds), plus Python/JavaScript syntax,
PageUp/PageDown dispatch and canonical skill metadata checks. No broad managed
suite, new browser fixture or live employer execution was run for this change.
The next ordinary application will measure the actual time savings and verify
automatic answer capture against its live controls.

## Magellan authentication dispatch correction — 2026-09-08

Attempt 26 had no prior Magellan account. Its own creation intent became a
pending account before the Create Account submit failed. Recovery then treated
that pending record as an existing-account reason to switch to Sign In. The
first click's exact failure was discarded; a later sign-in click was explicitly
blocked by Workday's labelled `click_filter`, and clicking that observed wrapper
worked. The pending-state guard predates the WEX checkpoint.

The bounded fix preserves structured click results and distinguishes proven
non-dispatch from uncertain dispatch. Only the owning attempt can clear its
pending intent to `creation_not_executed`; recovery can then retry without
inventing an existing account. Created/confirmed accounts choose Sign In, and
uncertain creation remains a reconciliation case. Workday auth recognition can
select its matching same-form click wrapper while retaining normal hit testing.
Account handoffs expose status, timing and attempt provenance. The user will
repeat the same application in a new conversation as the live acceptance check.

Validation: the focused credential, mapped-recovery and account tests passed
(25 tests, 4.02s); Python and JavaScript syntax passed. No broad suite or new
browser fixture was run. The generic skill validator rejects the existing Hermes
frontmatter extensions; those supported repository fields were preserved.
At the user's request, the selected private database was backed up, the
unconfirmed Magellan account and its single request were removed, and the job
was queued for retry. Failed attempt 26 and its diagnostic history were retained.
This operator reset was separate from validation and made no employer-side change.

## WEX execution checkpoint — 2026-09-08

The user authorized a checkpoint in the existing checkout and asked to iterate
with another ordinary Workday application instead of a broad suite or new browser
fixtures. The observed WEX issues informed shared fixes: enabled Simplify skills
input despite cosmetic activity, verified native/ARIA selection and idempotent
checkboxes, page keyboard support, profile-backed salary/privacy answers, and
confirmation capture before the single submit. Workday retains recognition/auth
and routine advancement; other ATS use the same scoped browser exceptions and
submission boundary. The fast runner now delegates final submission to that
shared boundary; two existing runner tests were updated for this delegation.

The selected ignored private profile contains the user's advertised-range maximum,
USD 250,000 fallback (not a floor), routine privacy consent and accepted evidence
sources. Startup projects these preferences into future attempt snapshots. No old
WEX answer, outcome or private attempt history was rewritten. Native and Simplify
confirmation are separately attributed; user confirmation can be reconciled with
its own event without inflating the old application's duration. Confirmation mail
through Hermes Gmail and a profile editor with min/max/fallback choices are recorded
as follow-ups in APPLICATION_RUNTIME.md.

The owned headed browser starts maximized without automatic refresh. Pointer
recovery checks bounded uncovered points and returns viewport/covering metadata.
A workspace uses its own background host and retires it after the completion
response; separate applications retain independent process ownership. Uncertain
submission preserves a read-only inspection opportunity for 120 seconds, then
stops the owned browser and records uncertainty. Existing unrelated terminals
were not closed: the old lingering terminal's launcher was not conclusively owned.

Validation: Python compile and browser-helper JavaScript syntax passed. Selected
existing advancement/Simplify/history checks passed (21, 1.09s); existing owned-CDP,
profile-import and reconciliation checks passed (38, 1.50s). No broad managed suite,
new browser fixture, live employer application or production-record test was run.
Gemini via Anti-Gravity completed a bounded source review; it did not run tests
or edit files. Speculative suggestions were not treated as verified defects.
The next user-run Workday application is the live acceptance check for extension
behavior, actual confirmation UI, dropdown compatibility and process cleanup.

## Credit Acceptance login redirect and native activation — 2026-09-08

Attempt 23 reached Create Account after loading the casing fix. Its structured
`workday_auth.auth_submit` action at 20:57:29 UTC was logged as successful, but
the implementation only invoked JavaScript `element.click()`. That proves an
invocation, not an employer-accepted account action. The user reported that a
manual click worked. The owned target subsequently reached the career site's
`/login?redirect=<encoded exact R13799 application route>`, which the validator
rejected because it banned encoded separators across the entire URL and did not
recognize the login wrapper. This is distinct from the earlier casing defect.

The existing scope validator now checks the login site's identity and the decoded
same-job return path. Missing/duplicate redirects, nested redirects, other jobs
and external destinations remain rejected. Native mapped and selector-based
activation now share CDP pointer input after fresh visibility/coverage checks;
partial dispatch stays uncertain. Local click action status no longer treats a
returned not-executed result as success. Skills distinguish dispatched input from
employer acceptance and describe the email option before native account forms.

The focused redirect check passed. One isolated local Chromium check demonstrated
that JavaScript click did not trigger a trusted-event-only button, native runner
pointer input did, and an overlay prevented dispatch (1.02s final check). This
does not establish why Credit Acceptance ignored its earlier click or prove live
account acceptance. Initial test setup hit sandbox GPU failure and an insecure
blank-page fixture; the final fixture used isolated localhost. No employer form,
account, production record, or running browser was changed during engineering.
The existing resident host must restart to load these source changes.

## Credit Acceptance casing repair — 2026-09-08

The owned R13799 target remained on the already-supported
`/apply/applyManually` route. The stored lowercase job path versus Workday's
mixed-case redirect caused `target_job_mismatch`; this was not an unknown SSO
route. Workday scope comparison now ignores path case. The follow-up covers
candidate-home recognition, history matching, target binding/expected URL checks,
confirmation comparison, existing-job reuse at intake, account namespaces, and
candidate/mail/private-fill email comparisons. Existing identity hashes, secrets,
opaque query values and other ATS path semantics are preserved. Native and
Simplify action-label matching was already case-insensitive. Three directly
relevant synthetic checks passed; no broad suite or live application was run.

Session 22 reused host PID 97880, started at 20:28:53 UTC before the repair,
despite creating a fresh browser target. Current source accepts that exact target
URL. The resident host needs to exit and restart to load the changes; restarting
only the application session can reuse it. No active browser was stopped during
this investigation, and no live sign-in/submission is claimed.

## Focused execution follow-up — 2026-09-08

The user supplied a focused execution brief and explicitly replaced broad test
gates with quick syntax/import and directly relevant checks. Work resumed from
clean HEAD `497689c884212780ffc3b340909d7e91538f32fd`; the prior review checkpoint
below remains historical. No broad suite, test delegation, second workspace or
new framework is part of this repair. No automatic push/merge is planned.

The connected change extends the existing observer/snapshot, private filler,
Workday runner and Simplify boundary. A combined screen inventory includes native
and official extension controls and account/activity context. A single mapped
recovery call can privately fill credentials, apply required native answers,
verify, act and return to the runner. It does not rerun the matcher that missed
the field. Unique semantic refs survive routine rerenders. Native authentication
confirmation updates the existing account state; possibly-executed actions remain
distinct from not-executed outcomes. Simplify sign-in is callable with separate
retained-credential-use evidence and an employer/extension login distinction.
The known labelled-text email variant is recognized. Settled unknown screens
return context promptly instead of consuming a full helper window.

Quick compile/import and JS syntax checks passed. The directly relevant mapping
and credential checks passed (18 checks, 1.86s); the first invocation encountered
only a sandbox temp-directory access error, then the same checks used an isolated
ignored temp path. Coverage includes the demonstrated labelled-text email,
mapped input/button use across a rerender, private credential output, the Simplify
sign-in capability/evidence boundary and account state after mapped recovery.
This is not live proof. Shared edits will be frozen for an ordinary Hermes retry
using the configured application model, the existing Wiley account uncertainty,
approved assets and the same managed DB. The first milestone is real authenticated
form access and official Simplify filling; completion still requires submission.

First focused live run: ordinary Hermes `20260908_145203_d29018`, attempt 15,
session `db66b298-15f0-46e3-bbd3-4f8e79b59ae4`, took 314.72s for the full
invocation. It inspected the official Simplify settings and reported ordinary
autofill enabled, continuous multipage autofill disabled by default. Wiley's
Start Your Application chooser opened. No authentication or autofill occurred.
A mapped native action incorrectly marked the writer active as though it had
started Simplify; later unknown extension UI could not settle that false state.
The new chooser's native actions also were missing from screen-key evidence.
The executor stopped safely after failed guarded recovery, leaving interrupted
history and no submission intent. No engineering writes occurred during the run.
One executor-supplied event time was in the future; use server/tool timestamps
for timing, not that client claim. Model/tool/website timing is not yet a complete
attribution. The reported single accepted mapping is not total page interpretations.

After the run ended, two tiny regressions reproduced those exact issues. The
bounded correction marks only Simplify dispatch as an active extension writer,
and includes new native choices in screen evidence (not values/enabled flags).
Existing action ownership still guards native writes. Only the directly relevant
mapping checks are rerun before another frozen ordinary execution.

## Review checkpoint — paused after Wiley attempt 14

This is an implementation checkpoint for independent review, **not accepted live
application automation**. The user paused further implementation and applications
after attempt 14, then requested that the changes and observations be persisted to
GitHub. The sections below are chronological: earlier statements that approval,
tests or retries were pending describe their time, not the current state.

Review branch: `codex/runtime-simplification`; baseline:
`8343893da3b941c078bf936547fdcd50a49b0b11`. All work uses the original checkout.
Start with [APPLICATION_RUNTIME.md](APPLICATION_RUNTIME.md) for the helper map
and data ownership, then review the diff from that baseline and the findings here.
No Simplify sign-in fix was implemented after the latest live failure; that
proposed patch was paused in favor of reviewing the overall recovery policy.

### What changed

- Local session startup now uses the existing Service/database directly, with
  automatic browser readiness, an owned target and a durable conversation/session
  handle. HTTP tokens, a running dashboard and expiring leases are no longer local
  startup prerequisites. Authenticated HTTP remains a compatibility transport.
- Migration 15 and `managed_sessions.py` add session/workspace lifecycle and
  account coordination to the existing ledger. `workspace_host.py` and
  `workspace_process.py` retain OS ownership across model gaps, serialize scoped
  requests and stop the owned browser before releasing capacity. The host has no
  model. Pause/attach/stop/retry and mixed-version/profile-alias guards are included.
- Existing dashboard cards expose sessions, host versus driver activity, selected
  model evidence and real stage/recovery events. Helper errors return to the
  executor without automatically finishing the session; completed reports remain
  readable after the host stops.
- Workday authentication uses the shared private credential resolver and existing
  account ledger. It retains credential references, records creation pending and
  confirmed states separately, handles observed account consent and returns
  specific exceptions. Scoped screenshots mask credentials and support executor
  inspection. Canonical job-apply 0.4.2 and workday-simplify 0.3.0 describe this flow.
- Reproduced and corrected the Workday details-to-job scope rejection, synchronous
  local browser observation inside an async runner, and credential filling stalled
  by unavailable animation frames. These fixes have synthetic regression coverage.

### What the live runs actually established

All times below are full ordinary-Hermes invocation times, including executor
startup and reporting. They are blocked outcomes, not submission performance.

| Role / attempt | Full invocation | Observed outcome |
|---|---:|---|
| Surescripts REQ3151 / 9 | 132.42s | Posting's no-sponsorship requirement prevented eligibility |
| NVIDIA JR2013287 / 10 | 237.62s | Employer page unavailable; local startup worked with dashboard stopped |
| Wiley R2601190 / 11 | 285.47s | Employer page unavailable |
| Wiley R2601245 / 12 | 246.05s | Same-job redirect incorrectly rejected; implementation defect subsequently fixed |
| Wiley R2601245 / 13 | 394.65s | Account creation unconfirmed and sign-in stalled; async/credential defects subsequently fixed |
| Wiley R2601245 / 14 | 315.01s | Ordinary sign-in page remained; helper/LLM recovery stopped prematurely |

Attempt 14 had explicit user approval for this UK role and submission. The earlier
automatic approval rejection was resolved before launch. Ordinary Hermes
conversation `20260908_130856_40ce8a` used openai-codex/gpt-5.6-luna with low effort;
session `60b636ce-c131-42ca-a982-e55eb7347363` opened the owned browser in 6.83s.
Configured credentials were privately committed. The executor reported native
sign-in and bounded recovery attempts, captured the owned page and read fresh DOM
metadata, then explicitly finished blocked. The session itself lasted 242.93s;
that narrower number must not replace the full 315.01s invocation.

The user and retained screenshot showed an enabled official Simplify **Sign In &
Autofill** control beside a normal employer email/password form. The executor
did not try it. There was no observed employer credential rejection, CAPTCHA,
MFA or email-verification challenge. No application form opened, no employer
resume attachment was verified, no mailbox was used, no account was confirmed,
and no submission intent or submission was recorded. The portal account remains
`recovery_required` with the retained credential reference; it is not evidence of
a confirmed account. Simplify bulk-fill runs were zero.

### Priority questions for the independent reviewer

1. **Helper coverage versus authority to stop.** A missing selector currently can
   become a terminal executor outcome without a real employer blocker. Review
   `workday_auth.advance_auth`, `FastRunner.run`, the recovery payload, canonical
   skills and the executor's finish behavior together. A helper limitation needs
   a usable local recovery path; the runtime must still obey user pause/stop.
2. **Simplify is observed but cannot perform this recovery.**
   `browser_helpers/simplify_observe.js` recognizes `controls.sign_in`, including
   Sign In & Autofill. `SimplifyBoundary.perform` permits only autofill/continue/
   start. `FastRunner.choose` routes authentication to the native account helper
   before considering extension actions. Review this whole boundary and the
   configured Simplify policy before adding another isolated special case.
3. **Ordinary form semantics are too narrowly recognized.**
   `workday_observe.js` finds email by type=email, autocomplete=username or
   name=email. Attempt 14 repeatedly returned `missing_email_ref` while the
   executor could observe the live email field. Auth submit/switch matching also
   depends on exact labels and a unique form/dialog match. Review label and
   accessibility based recognition, scoping, ambiguity and stale-control behavior.
   The precise live DOM variant should be verified from private evidence; do not
   copy a real application or credentials into test fixtures.
4. **Balance routine speed with flexible recovery.** The user's requested direction
   is to consider enabled Simplify from authentication onward, let deterministic
   helpers perform confident routine actions, and hand only the ambiguous step to
   the current LLM. After recovery, resume the fast path. Preserve identity,
   secret handling, single-writer ownership and one-submit guarantees. Avoid both
   repeated helper loops and declaring a helper miss to be an employer rejection.
   This direction is a review/design request, not an implemented policy change.
5. **Independent lifecycle/account review.** Check migration/legacy compatibility,
   host crash and orphan isolation, driver replacement, concurrent account locks,
   creation-pending/confirmed transitions, saved credential-reference resolution,
   and screenshot redaction. Browser/profile concurrency in synthetic tests does
   not establish concurrent authenticated official Simplify use.

### Validation and limitations of this checkpoint

The latest full pass used the same application source that attempt 14 used:
**550 passed, 0 failures, 0 errors, 0 skips**, exit 0, 338.139s process wall time.
Antigravity Gemini Flash Medium ran the suite; JUnit was independently checked.
Real headed synthetic lifecycle/gap/parallel/crash/stop coverage took 210.657s;
real browser account/create/sign-in/reuse/screenshot coverage took 14.468s.
Only review documentation was updated after that pass; no new runtime fix is
being represented as tested. Reproduce from the repository virtualenv with the
real browser environment enabled:

```powershell
$env:JOBBOT_BROWSER_TEST_EXE = 'C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe'
.venv/Scripts/python.exe -m pytest tests/jobbot_v1 -q
```

The exact final command additionally used isolated `--basetemp`,
`-p no:cacheprovider` and `--junitxml` paths under ignored
`artifacts/jobbot-v1-private/runtime-final-20260908-auth-recovery`. Local evidence
for attempt 14 is under `artifacts/jobbot-v1-private/ordinary-hermes-wiley-auth`;
screenshots are in the configured private spool. These files, deployment config,
credentials, profiles, databases and raw transcripts are deliberately not in Git.
Reviewers in another checkout have the sanitized observations and synthetic tests,
not the private live evidence.

Successful live application/submission, mailbox verification, under-ten-minute
completion and two authenticated concurrent Simplify workspaces remain unproved.
Production concurrency remains one: workspace A is provisioned; B still needs
official extension installation/authentication following the earlier Computer Use
URL-verification stop. DFC was excluded on citizenship eligibility; Enzo needs an
original application URL. Further live applications and implementation are paused
pending the user's review direction. This checkpoint should not be described as
completion of the application-automation acceptance criteria.

## Baseline and inspection — 2026-09-08

- Actual checkout: `C:/GitClone/auto-job-applier-jobbot-v1`; HEAD
  `8343893da3b941c078bf936547fdcd50a49b0b11`. No tracked dirty changes at intake.
  Created `codex/runtime-simplification` in the existing checkout. Its Git metadata
  resides under `C:/GitClone/auto-job-applier/.git`; no new checkout was created.
- Read the named sources, canonical application skills, architecture, connection,
  review handoff and Windows runbook. Traced indirect expiry in events, views,
  checkpoints and runtime budgets as well as claim/owner.
- Restored and displayed the existing dashboard at `http://127.0.0.1:60157`,
  instance `windows-supervised-pilot-rejo`, from its selected native config and
  credential-file references. Existing jobs/accounts/outcomes were not changed.
- Installed Antigravity CLI is 1.1.27. Elevated `agy models` confirmed Gemini 3.8
  Flash High/Medium availability using existing authentication. The old :8010
  proxy was stopped; the installed skill documents direct CLI delegation.
  Bounded process-helper implementation delegated to Flash High. No new API key
  or billing route. Codex is the engineering harness; its exact runtime effort
  is not exposed here and is not inferred from another harness's settings.
- Plan/delta added to APPLICATION_RUNTIME in place. Existing lease semantics
  remain compatibility behavior until the local session path is exercised.
- Checks so far: read-only configuration/history/UI inspection, Git status,
  installed CLI help/models, actual dashboard startup/readback. No application
  run or full test suite yet.

## Local services, host and connected helpers

- Added `managed_sessions.py` and additive migration 15 in the existing ledger:
  preparing/capacity reservation, idempotent session handle, account coordination,
  workspace aliases and mixed-version guards. Local sessions create attempts only
  after browser readiness and do not create/renew a browser lease. Existing
  account, document, event, duplicate and submission operations remain shared.
- Added `LocalClient`, local CLI transport, high-level `application_runtime`
  start/status/call/pause/stop/attach/retry, and `workspace_host.py`. A host retains
  the profile lock and Windows-owned browser tree; named-pipe requests are JSON,
  not HTTP/pickle. Driver/model gaps remain visible without revoking permission.
  Browser process termination precedes stop/reuse; unknown submission blocks its
  job while another workspace can run. No model is launched by this host.
- Gemini via authenticated `agy` produced `workspace_process.py` and its six
  synthetic tests (conversation `48f27042-88ef-4f30-a476-f8e97fc69e42`). Engineering
  review removed a test-only detachment override, strengthened stop verification,
  and corrected a test's venv-launcher cleanup. Independent process check:
  `test_workspace_process.py`, exit 0, six passed in 1.04s, JUnit under ignored
  `artifacts/jobbot-v1-private/runtime-process-verified.xml`. This includes real
  child/grandchild death on host kill and shell-exit survival without that override.
- Connected session-scoped Workday, private credentials, selected-asset upload,
  browser primitives and native Hermes convenience operations. Replaced the
  crash-prone fast-runner sentinel with an OS lock. Added existing-dashboard
  session cards and separate host/driver/progress visibility. Canonical skills
  now describe local startup; the HTTP credential reference is compatibility only.
- Affected checks: local-session + legacy ownership/CLI/fast integration, 15 passed
  in 14.00s; local-session + fast plugin + configured credentials, 17 passed in
  3.27s. No full-suite run yet. One expected Starlette deprecation warning.
- Real headed localhost lifecycle test proved two distinct browser workspaces,
  idempotent target reuse, continued writes after a real 65-second model gap, and
  B surviving A's forced host crash. It found a paused attach transition defect
  (`startup_cancelled`); the run control reset is fixed and awaits final integrated
  verification. Initial structured-argument defect was also fixed. Do not label
  that whole lifecycle test passed yet. Evidence: runtime-headed-check-2.xml and
  its synthetic database/logs. No employer was used as a test fixture.
- Only the existing `brave-cdp-simplify` automation profile contains official
  Simplify 3.1.4. A second authenticated workspace is not prepared/accepted yet.
  No live application acceptance or performance claim has been made.
## Canonical documentation, activation and final validation

- Replaced the historical default procedure in APPLICATION_RUNTIME in place, with
  actual URL-to-submit calls, responsibilities, record lifetimes, Windows process
  proof, recovery, credential boundaries and the helper map. Updated AGENTS,
  HERMES_CONNECTION, WINDOWS_RUNBOOK, WORKDAY_NEXT_RUN and thin Hermes discovery.
  Old HTTP evidence remains explicitly historical. No additional application agent
  or network service was introduced. Ordinary Hermes can use the portable CLI.
- Review regressions exposed old-profile alias reservation bypass, definitely
  failed host startup retaining capacity, and pause before readiness lacking an
  attempt. Fixed all three (11 affected checks passed in 4.84s). Unconfirmed host
  launch remains isolated, since a delayed process must not be treated as absent.
- Backed up the real selected DB and native config before migration/activation.
  Set local transport, the already selected candidate/resume, Luna subscription
  settings, and two distinct directories/endpoints. Verified no live process used
  the exact old Simplify profile and CDP 9223 was down. Attempt 8 had no submission
  intent; reconciled it as interrupted through the service, retaining all original
  account/events/history. Did not retry Credit Acceptance or prohibited prior jobs.
- Selected ignored runtime-config pointer now targets the existing native-app.json.
  Doctor ran against that config. local-simplify-a uses the existing authenticated
  automation profile; local-simplify-b is a separate private directory on port 9224.
  Production concurrency remains 1 until B is authenticated and verified.
- Gemini Flash Medium through Antigravity ran the complete supported suite once:
  522 passed, 4 failed, 0 skipped; exit 1, 213.33s. It exercised real headed browser
  lifecycle and found a short busy-lock tail immediately after attach. Fixed by
  allowing bounded lock acquisition before the first request; writes still serialize.
  Other failures were skill frontmatter and superseded accept/next/checkpoint
  assertions. Kept safety semantics; updated those labels to start/pause/stop and
  restored the frontmatter contract. Affected documentation/plugin checks: 43
  passed in 0.18s. No shared edits during application execution.
- Gemini ran the corrected final candidate once: **526 passed, 0 failed/errors/
  skipped**, exit 0, 195.98s process wall time (pytest 195.48s). Conversation
  06d78a96-7b0c-4b62-b168-740eb5b919bd. JUnit independently parsed. Evidence root:
  artifacts/jobbot-v1-private/runtime-final-20260908-revised (results.xml,
  pytest.log, summary.json). No test bypasses or live employer fixtures.
- The real headed lifecycle test passed in 88.42s: actual shell exits while host
  persists; two distinct browser profiles and scoped writes; third capacity wait;
  actual 65-second gap without renewal or fabricated progress; A host crash kills
  its owned browser while B works; A safely reused; pause/attach changes driver and
  target; stop C leaves B usable. Cold synthetic startup 5.01s. This does not prove
  official Simplify concurrency. Six lower-level Windows process tests also passed.
- git diff --check passed; changes remain uncommitted on codex/runtime-simplification.
  No push, deployment, alternate checkout, production reset or Ubuntu change.

## Separate ordinary-Hermes acceptance and provisioning evidence

- Surescripts REQ3151: ordinary Hermes conversation 20260908_112237_ccc626,
  observed usage model openai-codex/gpt-5.6-luna; invocation effort low. Session
  8c40543c-d038-4075-8cba-3641c64f1886, attempt 9. Real headed profile/endpoint/
  target and official Simplify panel ready in 7.10s. Executor read the posting and
  correctly blocked its explicit no-sponsorship requirement against the configured
  future H-1B need. No account, mail, upload or submission. Managed session 50.58s;
  full ordinary-Hermes invocation 132.42s. Do not report session time as the whole
  user request. Initial dashboard stop failed, so this is not the HTTP-stopped
  cold-start proof. It was stopped while this session continued independently.
- NVIDIA JR2013287: user explicitly approved the exact employer after automatic
  approval review rejected a newly selected destination. Fresh ordinary Hermes
  conversation 20260908_112943_5b9c1a; session aaad5dc4-5dc4-4cd3-97f3-c12a52013c6a,
  attempt 10. Launcher asserted dashboard 60157 and browser 9223 were both down,
  with no JobBot token exported. Local start opened the correct headed browser and
  official Simplify, but the employer page said it did not exist. Blocked, no
  submission. Managed session 156.38s, full Hermes invocation 237.62s. Actual
  invocation metadata was recorded; usage reports remain private.
- Second workspace setup launched only its own configured directory and official
  Chrome Web Store page. Computer Use stopped because it could not confidently
  determine the browser URL to enforce policy. No extension install/login was
  performed; its owned browser was stopped and profile lock released. No profile
  or cookies were copied. This is a specific provisioning blocker; two authenticated
  official Simplify sessions and second-workspace live acceptance remain unverified.
- All acceptance prompts, launch/usage/result evidence and private logs remain under
  ignored artifacts/jobbot-v1-private/ordinary-hermes-*; no secrets or mailbox
  contents are in this log. The engineer did not complete employer forms.
- User supplied Wiley, Enzo and DFC as replacement roles. None was initially in
  the selected managed queue. Wiley is Workday and was handed to another fresh
  ordinary Hermes conversation. DFC is USAJOBS and requires U.S. citizenship or
  nationality; excluded through normal intake/eligibility with no application.
  Enzo's original application link is still being verified.

## Wiley acceptance and bounded URL-scope correction

- Wiley R2601190, ordinary Hermes conversation 20260908_113456_5ca5a8, attempt
  11/session 575b4448-4572-4e9b-8949-56ed1308f0a1: unavailable employer page;
  blocked without account/mail/upload/submission. Full invocation 285.47s, managed
  session 216.05s. The earlier listing was not retried.
- User supplied Wiley R2601245. Ordinary Hermes 20260908_114225_1ff56f, attempt
  12/session c7de223e-0996-4eea-a97d-4b830936a41a, reached the live posting with
  verified headed profile/target and official Simplify in 7.80s. Apply redirected
  its details URL to Workday's canonical job URL; the existing scope guard rejected
  the same requisition as target_job_mismatch. Hermes recorded blocked; normal
  isolation then closed the browser. This was an implementation defect, not an
  employer rejection. No account/mail/upload/autofill/submission. Full invocation
  246.05s, managed session 169.26s. Usage confirms openai-codex/gpt-5.6-luna, low
  effort supplied in the invocation. The role is hybrid Oxford/London, UK; user
  clarification about proceeding outside the configured US market is pending.
- After the executor ended, added a synthetic failing regression for details-to-job
  navigation. Corrected managed_identity scope comparison to tolerate the location
  segment introduced by Workday while requiring the same host, career site, exact
  full requisition slug/suffix and allowed application child route. Different jobs,
  sites, suffixes and sensitive/arbitrary routes remain rejected. Updated helper map.
  Affected auth/observation/runtime checks: 23 passed in 4.93s, exit 0. Final Gemini
  validation of this revision is pending; the prior 526-pass result predates this fix.
- Dashboard restarted at the original URL/instance/DB. Authenticated health/view
  confirmed schema 15 and new local session metadata during the live Wiley run;
  restarting the observer did not terminate the application. Private configs,
  managed DB, evidence and logs were verified ignored by Git.
- Final corrected revision: Antigravity Gemini Flash Medium conversation
  f2387182-1183-44d7-b010-38542610d3e2 executed the supported managed suite once,
  with the real-browser environment enabled and isolated temporary directories:
  **527 passed, 0 failures/errors/skips**, exit 0, 175.918s process wall time.
  JUnit independently parsed; real headed lifecycle passed in 89.010s. Exact
  command, summary, JUnit and logs are in ignored
  artifacts/jobbot-v1-private/runtime-final-20260908-url-scope. This additional
  final run was required by the live-discovered URL-scope defect. No employer
  fixtures or test bypasses. Dashboard refreshed again after validation and its
  authenticated view confirmed attempts 9–12 and their original blocked evidence.
- The implementation remains uncommitted on codex/runtime-simplification. Live
  submission, mailbox verification and simultaneous official Simplify in two
  authenticated workspaces are not established. The new Wiley retry is pending
  the user's UK-role preference; Enzo still needs a verified original apply link.

## Executor step tracking and Workday authentication

- User reaffirmed retrying Wiley R2601245 and required visible executor steps.
  Added semantic stage/activity/next-step events to the existing timeline and
  session cards. Helper errors are recorded without automatically ending a
  session; completed reports remain readable without contacting a stopped host.
  Prior Gemini final pass for this group: 530 passed, no failures/errors/skips,
  211.43s process time, conversation ec7c4058-b251-40b6-b29a-07b87b0fa839.
- Ordinary Hermes conversation 20260908_121837_a6a382, attempt 13/session
  7427f20e-1c98-45c1-9188-34cbcd16c5c7, passed the repaired Wiley redirect and
  reached Create Account and Sign In. Credential fields were committed but
  account creation was not confirmed; sign-in timed out. Blocked with no
  submission intent, mailbox verification or application autofill. Full ordinary
  invocation 394.65s. The account outcome remained unknown, not a confirmed account.
- Reproduced two actual integration defects after that executor ended: the local
  fast runner called a synchronous browser observer from its asyncio loop, and
  the private credential filler waited indefinitely for animation frames in an
  occluded browser. Fixed the observer call boundary and bounded the credential
  settle while still verifying committed values. Focused combined checks passed
  45 tests in 24.19s. Added report-after-host-stop coverage and visible recent steps.
- User requested deterministic Workday authentication. The existing shared filler
  now resolves a portal's saved credential reference or its retained configured
  default, and rejects an unavailable saved reference instead of substituting.
  New workday_auth is called by the existing fast runner, uses the existing
  account coordination/ledger and observed Workday controls, and handles account
  creation, the account privacy/terms checkbox, sign-in and disabled-until-filled
  controls. Creation is pending before its click; actual creation and successful
  sign-in have distinct recorded evidence. Unknown outcomes are never replayed.
  Mail/challenges/unfamiliar controls return to the executor; no password capture
  from Simplify or second credential store was introduced. Other ATS retain the
  shared filler and executor-driven navigation. Updated the existing helper map
  and canonical skills to job-apply 0.4.2 / workday-simplify 0.3.0.
- Focused regressions first failed, then passed. A real isolated browser exercised
  credential inputs, consent, Create Account, Sign In and a persisted confirmed
  account using only a synthetic page/database. It caught a dropped telemetry key;
  corrected the event to use the existing status field. The first complete
  browser/auth batch passed 13 tests in 12.60s. A second invocation test now also
  checks that the saved account chooses Sign In without another creation.
  Full final Gemini validation and another ordinary Wiley retry are pending.
- The combined credential/runtime/skill revision passed 107 affected checks in
  40.76s, including the actual browser create/sign-in/reuse flow. Antigravity Gemini
  then ran the full suite: 548 passed, zero failures/errors/skips, exit 0,
  215.58s process time. JUnit independently verified; browser auth/reuse 13.929s.
- While that final pass ran, the user added an explicit requirement for changed
  site detection and visual recovery. After the pass ended, added categorized
  auth handoffs with observed non-secret control metadata, one persisted recovery
  event, and an owned screenshot/snapshot command for the current executor.
  Added session-scoped screenshot capture to the existing browser operation,
  reusing the legacy credential mask through the shared credential module.
  Images stay under the configured private spool; masking restores on capture
  failure. Possible changed/unsupported UI is not asserted as a proven site change.
  No helper failure instructs the agent to close the application. The canonical
  procedure specifies image inspection, fresh selectors, bounded supported
  recovery and a later helper update, never an in-run patch.
- Focused red regressions confirmed missing handoff/capture behavior; the revised
  screenshot/handoff/auth/skill batch passed 70 checks in 18.27s (one unrelated
  long lifecycle test deliberately deselected). Real browser capture produced a
  private PNG from the exact owned target, then create/sign-in/reuse succeeded.
  A final revised Gemini pass is required by this added user scope; ordinary
  Hermes Wiley retry uses this complete frozen revision.
- Final revised candidate: Antigravity Gemini Flash Medium conversation
  c3b826df-b756-4218-a0fb-d95902ff9888 ran the supported full suite with both
  real-browser checks enabled. **550 passed, 0 failures/errors/skips**, exit 0,
  338.139s process wall time. JUnit independently parsed; lifecycle/gap/parallel/
  crash/stop test 210.657s and browser account/screenshot/reuse test 14.468s.
  Exact command, JUnit, full logs and summary are private under
  artifacts/jobbot-v1-private/runtime-final-20260908-auth-recovery.
- Dashboard restarted on the same URL, instance and managed DB. Authenticated
  health/view confirms current source fingerprint
  47ab814091ffe47342d5fdbf303884ec2d1861317e480b1a8bf35e7312ddd31d,
  local transport, no active sessions and attempt 13 retained. Configuration,
  database and test evidence remain ignored. No commit or push was made.
- Automatic approval review rejected launching the next ordinary Wiley retry,
  stating that explicit authorization for this exact UK role/submission was not
  clear. The process did not start, no new attempt was created, and no employer
  data was sent. An explicit Wiley retry/submission approval request is pending.
  Thus the corrected helper has synthetic browser evidence, not a successful
  live Wiley application. Mailbox verification, actual employer submission,
  under-ten-minute completion and two authenticated concurrent Simplify
  workspaces remain unverified. The earlier second-workspace Computer Use setup
  stop (browser URL could not be confidently verified) remains an installation gap.

### 2026-09-08: shared embedded forms and durable human answers

- Implemented the user-approved shared form/answer-queue design after stopping the
  stalled owned application. No employer application was used as an engineering
  fixture, retried or submitted during these changes. Source remains in the
  original checkout for review.
- Existing `browser select`/`fill`/`check` calls now route opaque refs through
  DOM-owned application documents, including cross-origin OOPIFs. The model does
  not choose another dropdown helper. Workday keeps its existing observer/runner.
  The same routing covers Simplify, approved uploads/private credentials, masking,
  answer capture and submission; transformed/ambiguous/unverified frames fail
  closed with diagnostics. Parent overlays, iframe replacement and document
  navigation invalidate unsafe actions.
- Added consistent employer query-requisition aliases to intake and read-only
  duplicate history. Submission captures transient child evidence and scoped
  redirects before one click; wrong-requisition and replacement-frame success
  messages cannot establish an application outcome. Uncertainty never permits
  another submit. Duplicate native-select values and ARIA radio read-back are
  verified against the actual offered choice.
- Migration 16 adds required questions, immutable human answer revisions and
  durable retry requests to the existing managed database. Exact question,
  choices, context, job identity and candidate scope control reuse. Approved
  policy runs first; failed controls and optional fields do not become prompts.
  `park_questions` stops the owned browser before releasing capacity. The
  dashboard offers Save, Save and queue retry, and a batch queue action. Draft
  conflicts reload current answers rather than overwriting a newer revision.
  Saving/queueing never launches a model. An ordinary harness picks up queued
  requests and applies saved answers against fresh controls.
- Messaging is optional harness metadata. Hermes observes actual platform/tool
  availability and requires a user turn newer than both the question and its last
  answer; only a turn ID/hash is retained as reply evidence. A harness without
  messaging uses the same durable dashboard path. Existing suppression across
  email identities, submission reconciliation and stop-before-reuse remain.
- Antigravity Gemini supplied synthetic identity tests and bounded source reviews
  of frame routing and the queue. Findings were checked against source and browser
  regressions: duplicate-value ambiguity and revision conflict recovery were
  corrected; suggested removal of same-requisition aliases/global uncertainty
  suppression or release before host termination was rejected because those are
  intentional ownership/history protections. Existing `finish` already converts
  failed post-intent attempts to submission_unknown.
- Focused integration: 48 passed in 49.22s, followed by seven final radio,
  reply-provenance and canonical-skill checks in 5.74s. Tests use isolated
  localhost Brave documents, synthetic ledgers and the actual dashboard API/UI.
  Screenshot QA confirms the question cards, controls and batch actions fit.
  These fixtures do not establish a successful live embedded ATS application or
  universal custom-widget support.
- The first full pass exposed forgotten writer uncertainty after repeated reads
  and the missing backward-compatible snapshot title. Both were fixed. Older
  fixtures were aligned with the already-implemented scoped sign-in, explicit
  writer versus cosmetic spinner policy, and shared submission collector; the
  Workday HTTP/local integration still exercises the real Service/database.
  The affected 50-check group then passed in 23.26s.
- Final managed suite: **624 passed, zero failures/errors/skips**, exit 0, 254.21s.
  JUnit independently confirms those counts (254.095s suite time). Real isolated
  browser checks were enabled, including headed lifecycle survival, a 65-second
  driver gap, parallel isolation, crash cleanup, pause/attach and Workday auth.
  The exact command/log/JUnit are retained privately as
  `embedded-managed-verified.*`; JavaScript syntax and Git whitespace checks pass.
- The dashboard was offline at deployment and was started at its existing
  `http://127.0.0.1:60157` address with the same selected instance/database.
  Preparation initially encountered a filesystem read-only error in workspace
  metadata; the authorized retry with normal-user filesystem access succeeded.
  Schema 16 is present, a fresh SQLite backup passes integrity_check, and hashes
  of all records in 40 existing tables are unchanged by preparation. Authenticated
  health/view/answer_queue confirm the current source fingerprint
  `b0fd3f65d2c24cf7c5c20728bbcf62e6fbc75ae4d096f25b535eb6a1a905715f`.
  No active applications were present. The queue has no historical backfill;
  future observed missing questions populate it. No commit or push was made.
- Long-running native Hermes instances must reload JobBot or restart to load
  the new native operations; the portable CLI already loads current code on each
  call. No live application retry or Discord message was sent by this engineering
  task. Live ATS acceptance and authenticated extension behavior remain separate
  from the synthetic regression evidence.
