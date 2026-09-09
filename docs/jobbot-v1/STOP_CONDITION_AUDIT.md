# First-principles assessment of application restrictions

Assessment date: 2026-09-09. **Historical assessment; implementation is recorded below.**

Later decision: [RETRY_POLICY.md](RETRY_POLICY.md) supersedes this assessment's
uncertainty and same-job/account exclusion restrictions, including the original
G05 and G16 recommendations and the blanket single-dispatch rule below. A new application request can start another attempt unless
success is recorded. Submission uncertainty remains evidence for its own attempt;
actual browser cleanup is separate. Current changes and remaining audit scope
are in [GUARDRAIL_RESEARCH_HANDOFF.md](GUARDRAIL_RESEARCH_HANDOFF.md).
The historical findings below are retained
to explain the evolution, not to reintroduce the superseded retry policy.

## Implementation follow-up — 2026-09-09

The assessment and companion catalog below describe the original source snapshot.
The user subsequently authorized implementation after preserving the prior
embedded-form, automatic-answer-policy and human-answer work in checkpoint
`0ded3c9`. The current change follows the six-step simplification sequence in the
existing modules; it adds no worker, service, policy framework or database.

| Audit recommendation | Implemented change |
|---|---|
| Job identity and diagnostics | Shared Workday host/site/full-requisition identity; location/title/locale/step spelling no longer vetoes the job. Owned snapshots/screenshots and return navigation remain available when identity is unresolved or conflicting. Confirmation uses the complete requisition too. |
| Recoverable setup and helper states | Slow loading, delayed navigation response and missing Simplify retain the owned target with setup recovery. Unrecognized controls and unconfirmed ordinary clicks request inspection; a helper slice ending returns waiting. |
| Incidental write vetoes | Local semantic timing is telemetry. Removed the global two-non-dispatch auth cap and one-action-per-screen restriction; mapped decisions retain action-specific uncertainty. Auth Submit is distinguished from final application Submit. |
| Writer/control recovery | Observed Simplify Stop/Cancel can settle the extension without closing the application. Native writes still require observed settlement and no unended writer. Explicit unsupported/idle evidence can settle unknown state. Frame diagnostics are localized to affected controls. Changed form evidence permits another fill. |
| Submission dispatch | Existing intent and ordered dispatch events now produce one shared `submission_pending` state. Proven non-dispatch permits recovery; missing or possibly dispatched results never authorize replay. Removed the unrelated two-minute inspection closure; explicit Stop and configured maximum runtime remain. |
| Automatic answers and optional diagnostics | Approved policy and exact saved human answers run before question creation. Human input remains for missing required facts/verification. Optional answer journaling and progress events cannot abort form recovery or disguise an executed write. |
| Canonical instructions | Updated both skills and the helper/caller map. Ownership, candidate selection, actual employer requirements, configured authorization and duplicate prevention remain. Legacy-only callers retain their compatibility rules. |

Focused synthetic regressions were added before each bounded implementation.
Final validation: **655 tests passed in 298.98 seconds**, including isolated
browser tests, with four dependency deprecation warnings. The managed suite ran
with the repository virtualenv, private temporary artifacts and Brave fixtures.
No employer application, production-record correction or benchmark is part of
this engineering change. Synthetic coverage does not establish live ATS acceptance.

## Decision

The runtime needs a small set of guarantees. It does **not** need a large collection of URL, timing and helper-recognition rules that can strand an otherwise valid application. The present implementation mixes these together. Some restrictions are necessary; several use the wrong evidence, apply to too many operations, or have no usable recovery.

The priority is to **remove redundant restrictions and narrow the remaining checks**, using the existing session, browser, account and submission code. Adding another approval layer or policy framework would make the problem worse.

The necessary guarantees are:

1. **One task controls its assigned browser and attempt.** Another task cannot acquire its target or write its records. Only one actor writes the form at a time.
2. **The application belongs to the requested job and candidate.** Bind the job, approved profile, credentials and selected documents to the attempt. Identify the job by its employer/ATS identity and requisition, not the spelling of a location or title in a URL.
3. **Do not duplicate an application or repeat a possibly completed submission.** Preserve confirmed outcomes and actual dispatch uncertainty. A click that was provably never sent is a different case.
4. **Honor actual user instructions and employer requirements.** Respect stop requests, configured exclusions, submission authorization and genuinely missing required facts. A helper's inability to recognize a page is not an employer requirement.

These guarantees justify rejecting particular unsafe operations. They do not justify automatically closing a correctly owned browser whenever a helper is confused.

## What “scope” currently means

In this code, *application scope* is mostly a predicate that asks whether the current URL belongs to an approved family of URL paths. It is separate from browser ownership.

The real task-isolation chain is already:

```text
conversation/driver -> session -> workspace host -> browser process/profile
                    -> assigned target/tab -> attempt -> job + candidate + assets
```

`SessionServices._local_owner`, host dispatch, exact CDP target selection, process/profile isolation and scoped database operations enforce that chain. They do not need the job's location text. The URL check is an additional attempt to detect navigation to a different job **inside that already-owned tab**.

There is a valid question here: the same tab can navigate from requisition A to B. But the implementation answers it using an unnecessarily strict URL comparison. Workday location, title, locale and route formatting can change without changing the requisition. Conversely, a query can identify a different job while the host and path remain identical.

**Proposed replacement:** one shared job-identity comparison, used consistently by history, target binding, browser actions and submission. For Workday, compare verified employer host/tenant, career site and the complete requisition identifier. For other ATSs, preserve their actual identity fields, including meaningful query IDs. Do not add per-employer location exceptions.

Carry the verified job binding through ordinary login and application navigation within the owned flow. A login page need not repeat the requisition visibly on every screen. Conflicting job evidence should stop job-specific writes; absence of a recognizable URL pattern should trigger inspection. Revalidate the job when entering a different application and before final submission. Verified cross-site authentication/embedding relationships need explicit association, not a blanket same-host or same-ID-anywhere rule.

Return a useful distinction: **same job**, **different job**, or **identity unresolved**. “Target scope changed” should disappear as an executor-facing reason.

This identity check does not prove every manually supplied field value is correct. Attempt-scoped profile/answer/document selection and the executor's approved-fact procedure handle that separate concern. A URL string cannot prevent all content mistakes.

## Test every restriction against the same questions

- What concrete mistake does this prevent?
- Does the evidence establish that mistake, or merely show a helper limitation?
- Is another existing boundary already enforcing it?
- What is the smallest operation that must wait or be rejected?
- Can the same task inspect and recover without being blocked by the same check?
- What recorded failures or synthetic counterexamples support keeping or changing it?

An old test asserting rejection is evidence of the current contract, not evidence that the contract is useful. Tests for restrictions proposed for removal must change with that decision.

## Observed incidence

Read-only snapshot of the selected managed database, taken 2026-09-09 at approximately 05:16 UTC. It contains **33 attempts across 13 job records**, from 2026-09-07 16:06 UTC through 2026-09-09 04:36 UTC. Attempts include repeated development/diagnostic runs and different source revisions; this is not an independent-employer success-rate sample.

| Recorded mechanism | Attempts with evidence | Distinct jobs | Evidence and limits |
|---|---:|---:|---|
| `target_scope_changed` / `target_job_mismatch` | **10** | **5** | 20 automatic recovery events in 9 attempts, plus an earlier attempt whose outcome explicitly identifies the same guard. At least one occurred after Submit and obstructed confirmation inspection. |
| Writer-state gates | **3** | **3** | 10 automatic recovery events matching busy/quiescence/unconfirmed-writer reasons. This does not establish that every refusal was false. |
| Authentication helper recognition/click/unconfirmed-action reasons | **9** | **5** | 14 automatic recovery events matching the stated family. Includes cases with later real credential rejection; not all are unnecessary restrictions. |
| Runtime/API integration errors | **5** | **3** | 9 automatic recovery events containing TypeError, AttributeError, SyntaxError or nested-event-loop failures. These are implementation/caller errors, not safety policies. |
| Attempt/lease/field-budget errors | **0 recorded in the queried recovery events** | **0** | Field-budget restrictions are still present in current source. Absence from this event sample is not proof they never fired. |

Two additional sessions failed **before an attempt existed**: one startup URL rejection and one missing-Simplify-panel rejection. The startup URL failure is additional to the ten attempts above; it must not be hidden by an attempt-only report.

The 33 recorded outcomes are 2 applied, 17 blocked, 10 interrupted, 3 failed and 1 submission unknown. It would be incorrect to attribute all 31 non-applied outcomes to guards. The evidence also includes actual missing employer pages, an explicit sponsorship incompatibility, credential rejection, browser exits and operator stops. Categories overlap; do not add their counts.

The configured legacy history contains 180 job records, including 83 failed and 83 needs-review records. Those aggregates lack an equivalent causal event trail, may overlap the newer work and are **not** included in the incidence counts above.

Detailed attempt/session IDs and original evidence remain in the ignored `artifacts/jobbot-v1-private/stop-audit/audit-evidence.json` and existing managed reports. No outcome, account, application or history record was changed for this audit.

## Highest-priority changes

| Priority | Current restriction | Assessment | Proposed change |
|---|---|---|---|
| P1 | Literal URL scope gates across startup, observation, credentials and submission | Repeated demonstrated false rejection; several implementations disagree about the same identity. | Replace with shared semantic job identity and bound-flow continuation. Remove location/title comparisons. |
| P1 | Scope rejection also blocks screenshot/snapshot and navigation back to the requested job | Recovery dead end; task ownership remains intact. | Keep owned diagnostic metadata and safe recovery navigation available independently of job-form write permission. |
| P1 | Unknown writer state can remain latched until a recognized Simplify state appears | Missing recognition can prevent the action needed to recover recognition. | Keep serialization and observed-active-writer protection; give uncertainty a bounded observation/settlement recovery with explicit evidence. Do not simply set idle after a timer. |
| P1 | Two **not-executed** account clicks exhaust recovery | No duplicate action occurred, yet useful recovery is prohibited. A recorded attempt reached this exact limit after covered-control refusals. | Count repeated unchanged failures for loop control; permit a materially different, observed recovery. Keep uncertain account-creation dispatch separate. |
| P1 | Any visible native email input differing from the candidate triggers `candidate_email_mismatch` | A reference/referrer email could falsely become a candidate mismatch. Source-identified counterexample; no incidence claimed. | Compare the identified applicant/account email field, with approved aliases where configured. Other email questions retain their own meaning. |
| P2 | Local field timing/unknown-duration gates remain, while local budget extension is prohibited | Performance telemetry becomes write permission; unrelated to task isolation. | Remove field elapsed/missing-timing rejection from ordinary local execution. Report repeated lack of progress; retain only explicit user budget policy. |
| P2 | Missing Simplify panel within 12 seconds or unrecognized startup route closes the browser | A temporary readiness/recognition problem becomes a failed session before the executor can inspect it. | Separate process/ownership readiness from application/extension readiness; preserve an owned preparation/recovery state. |
| P2 | Submission intent plus timeout can produce read-only/unknown state even after proven non-dispatch | Intent, actual dispatch and evidence availability are being conflated. | Drive recovery from persisted dispatch status; only possible/executed dispatch invokes no-repeat protection. |
| P2 | 120-second confirmation-inspection deadline closes the browser even while useful inspection may continue | The deadline is a resource policy, not proof that confirmation is impossible. | Preserve evidence first; use explicit resource/parking policy and active inspection state rather than unconditional wall-time closure. |
| P2 | “One mapped action per screen” and any label containing “submit” rejected in mapped recovery | A screen can need another reversible action; an auth button may be called Submit. | Track specific action/outcome, classify final submission by context and control role, and allow recovery after new relevant evidence. |
| P2 | Nonessential telemetry/history-capture failures can abort later work or obscure a dispatched action | Observability should not become permission. | Separate best-effort diagnostics from mandatory ownership/action/submission ledger updates; preserve the original dispatch outcome. |
| P2 | Broad frame diagnostics contribute to a global not-quiescent decision | One unsupported application-frame branch can block unrelated usable controls. Source finding, not live acceptance evidence. | Attribute uncertainty to the affected document/control; refresh or inspect it, retaining exact root ownership. |

P1 here means high practical priority for this product, not a claim that every row is a security defect. The mapped-control, timing, email-field and frame findings include current-source deductions beyond the recorded incidents.

## What actually closes a local browser

The current host **does not automatically close a pre-submit session merely because `fast_forward` raises an exception**. It records a recovery event and returns the error. A helper's `blocked`, `inspection_required`, `authentication_required` or `waiting` result also does not itself finish the attempt. Executors can nevertheless abandon the task when the permitted recovery tools fail, so an action-level refusal can have the same practical effect.

Actual local closure paths in [workspace_host.py](../../job_applier/workspace_host.py) are:

| Trigger | Current effect | First-principles decision |
|---|---|---|
| Any exception during `prepare` | Stop the owned browser and fail/stop the session | Keep for lost ownership/process integrity. Change recoverable site/extension readiness failures to preparation recovery. |
| Explicit pause or stop | Kill the owned process tree; pause retains a workspace reservation | Stop must remain reliable. Pause's loss of the live form should be described plainly; consider a distinct parked/waiting state rather than equating pause with teardown. |
| Finished attempt (`finishing`) | Stop browser before slot reuse | Keep isolation at reuse. Successful confirmation already permits completion without another quiescence audit. |
| Configured `maximum_runtime_seconds` exceeded | Stop browser; currently measured from session request time | Only under explicit runtime policy. Avoid charging queue time as execution time. This setting is absent in the reviewed configuration. |
| 120 seconds after uncertain submission handoff | Stop browser and retain uncertainty | Change as above: no-repeat remains, unconditional loss of the evidence surface does not. |
| Owned browser has exited / previous host died | Classify attempt and clear ownership only after process evidence | Keep accurate reconciliation; a crash cannot establish whether an earlier write dispatched. |
| Host exits with its kill-on-close Job Object | Its owned browser descendants terminate | Necessary to prevent an orphan writer using a later session's profile. Repair startup/process faults rather than bypassing ownership. |

The idle host's 60-second exit occurs when it has no active session. Local `driver_recently_active` at 120 seconds is telemetry, not permission expiry. The legacy 45-second no-progress, 300-second attempt and 60-second lease defaults should not be described as current local-session shutdown rules: local ownership and `_budget_check` bypass those mechanisms. The separate field strategy check does not have that bypass.

## Disposition of every restriction family

The [source catalog](STOP_CONDITION_CATALOG.md) maps each indexed message/site to one of the following families. A family can contain several call sites enforcing the same invariant. Where a family contains validation and execution policy, the distinction below governs the disposition; not every exception should be removed merely to reduce a count.

<a id="g01"></a>
### G01 — Task, session, host and target ownership: keep, simplify the interface

**Protects:** a stale or foreign task writing another task's browser/attempt. `driver_owned_elsewhere`, `stale_owner`, `stale_host`, `target_not_owned` and session authority check real ownership evidence. **Challenge:** requiring the executor to repeatedly supply low-level ownership fields creates opportunities for accidental mismatch. **Decision:** retain host/server enforcement; derive IDs from the session handle, as local dispatch already does. A refused foreign request must not close or annotate the legitimate owner's session. Fresh local driver activity should not be required to renew permission. Sources: [managed_sessions.py](../../job_applier/managed_sessions.py), [managed.py](../../job_applier/managed.py), [workspace_host.py](../../job_applier/workspace_host.py).

<a id="g02"></a>
### G02 — Browser/process/profile isolation: keep at acquisition and reuse

**Protects:** two sessions sharing a profile or endpoint, attaching to an unrelated browser, and reusing a profile with an orphan writer. Exact target IDs, unique profile/endpoint configuration, OS locks and PID-plus-creation-time checks directly serve the user's isolation requirement. **Challenge:** an unavailable process inventory is not proof that another owner exists; repeated detection should not be treated as an employer failure. **Decision:** block acquisition of that workspace until verified, report the concrete process/setup issue, and allow other independent workspaces to proceed. Do not make these checks depend on URL punctuation. Sources: [workspace_host.py](../../job_applier/workspace_host.py), [workspace_process.py](../../job_applier/workspace_process.py), [cdp_client.py](../../job_applier/cdp_client.py).

<a id="g03"></a>
### G03 — URL/application “scope”: replace

**Protects:** navigation to a different job in the same tab, and credentials sent to the wrong portal. **Challenge:** raw route equality is an unreliable proxy. Current Workday job-to-job comparison retains location and the full title slug; history comparison extracts the requisition and already accepts those rewrites. Diagnostics are blocked before useful page inspection. **Decision:** remove location/title identity requirements and redundant route-specific guards; use one consistent identity/flow association. Keep actual different-job/different-portal rejection at write boundaries. Malformed/sensitive URLs still need safe parsing/redaction, but a secret-bearing verification URL is not itself proof of the wrong job. The credential/mail helper needs a scoped route for authorized verification, not a public-log exception. Sources: [managed_identity.py](../../job_applier/managed_identity.py), [application_runtime.py](../../job_applier/application_runtime.py), [workday_fast.py](../../job_applier/workday_fast.py), [managed_credentials.py](../../job_applier/managed_credentials.py).

<a id="g04"></a>
### G04 — Candidate, document and answer binding: keep; remove broad content guesses

**Protects:** using another candidate's profile, credential, file or saved answer. Attempt/job/candidate foreign-key checks are valuable. **Challenge:** Workday's observer treats **any** differing visible native email input as the applicant identity; a reference email is not an applicant identity. Exact question fingerprints can also prevent reuse after harmless wording/formatting changes. **Decision:** bind stored records strictly; inspect the actual applicant/account control semantically. Retain saved-answer provenance and question meaning/options; do not silently reuse answers to changed questions. A binding mismatch blocks the offending value/write, while owned inspection remains available. Sources: [workday_observe.js](../../job_applier/browser_helpers/workday_observe.js), [managed_questions.py](../../job_applier/managed_questions.py), [managed_documents.py](../../job_applier/managed_documents.py).

<a id="g05"></a>
### G05 — Duplicate/history and reconciliation: keep the invariant, narrow stale-state barriers

**Protects:** simultaneous or repeated applications to the same job, including an earlier uncertain submission. **Challenge:** a legacy `running` row can suppress a job even when its process is gone; unavailable historical storage blocks all requested jobs. This is missing evidence, not proof of duplication. Managed aliases and legacy history also do not currently use one identity parser. **Decision:** retain confirmed duplicate suppression and unknown-dispatch reconciliation. Automatically resolve proven pre-submit, stopped attempts from existing ownership/dispatch evidence; expose specific unresolved records instead of generic reconciliation. Provide deliberate legacy-history retirement/migration so an obsolete file does not remain a permanent dependency. Never interpret a missing file as “no previous applications.” Sources: [managed.py](../../job_applier/managed.py), [application_runtime.py](../../job_applier/application_runtime.py), [managed_identity.py](../../job_applier/managed_identity.py).

<a id="g06"></a>
### G06 — Authorization, exclusions and eligibility: keep only actual policy

**Protects:** applying against the user's explicit constraints or submitting in review mode. **Challenge:** default eligibility holds or stale metadata can masquerade as a new approval requirement. **Decision:** resolve the current authorized request against the selected candidate policy once; do not repeatedly ask for submission permission already granted. Retain explicit employer/country exclusions and actual incompatible requirements. An inferred market or a helper label must not override approved facts. Existing `authorize_requested_urls` already handles held URLs under standing configuration; preserve that behavior. Sources: [application_runtime.py](../../job_applier/application_runtime.py), [managed.py](../../job_applier/managed.py), [managed_settings.py](../../job_applier/managed_settings.py).

<a id="g07"></a>
### G07 — Configuration, assets, model and extension readiness: move to the proper boundary

**Protects:** an unknown database/candidate, wrong execution environment, missing assets or unavailable configured capabilities. **Challenge:** readiness is conflated with application success. The host demands a recognized official Simplify panel within 12 seconds and closes the browser on failure. An unfamiliar supported-site page or delayed panel may need an ordinary click/login first. **Decision:** keep database/profile/candidate integrity checks before writes. Distinguish workspace provisioning from per-page extension visibility. Expose an owned startup recovery surface; satisfy the user's Simplify requirement without interpreting every missing panel as bad configuration. Explicit model/provider requirements should be checked before browser allocation; absent model telemetry is not a mismatch. Missing optional answer-policy enrichment should not block pages whose required facts are already approved; a configured contradictory or unreadable source needs specific resolution. Sources: [application_runtime.py](../../job_applier/application_runtime.py), [workspace_host.py](../../job_applier/workspace_host.py), [managed_settings.py](../../job_applier/managed_settings.py).

<a id="g08"></a>
### G08 — Stop, pause, terminal state and attach: keep ownership transitions; improve usability

**Protects:** writes after stop, conflicting outcomes, reusing closed targets and two drivers controlling an attached session. **Challenge:** “pause” currently destroys the live browser and retains its slot, which may surprise an executor expecting to wait for the user. Also, `finish(quiescent=True)` can fail because the executor's assertion disagrees with the ledger. **Decision:** keep explicit stop/attach authority and immutable terminal outcomes. Let the host establish quiescence when ending a local session; do not require a model to assert it. Distinguish waiting, parking, stop and handoff clearly. Preserve readable status/report/evidence after termination. Sources: [managed_sessions.py](../../job_applier/managed_sessions.py), [managed_events.py](../../job_applier/managed_events.py), [managed.py](../../job_applier/managed.py).

<a id="g09"></a>
### G09 — Capacity and temporary coordination: wait, do not fail the job

**Protects:** concurrent writes, profile reuse and simultaneous same-candidate/same-portal account actions. **Challenge:** `account_in_use` and `session_operation_busy` are temporary resource contention, not application failures. An account lock can last until authentication succeeds or the session stops. **Decision:** preserve serialization; return a bounded wait with the specific owner/resource. Release account coordination when the action/verification scope ends, provided no account write remains uncertain. `capacity_wait` already avoids creating an attempt prematurely; retain it and keep unrelated portals independent. Sources: [managed_sessions.py](../../job_applier/managed_sessions.py), [workspace_host.py](../../job_applier/workspace_host.py), [workspace_process.py](../../job_applier/workspace_process.py).

<a id="g10"></a>
### G10 — Active and unknown browser writers: keep active-writer exclusion; redesign uncertainty recovery

**Protects:** native filling while Simplify or another action is changing the form. **Challenge:** `unknown` can be latched from an earlier timeout. `browser_observe` requires recognized extension readiness to clear it after prior activity; a missing panel or unfamiliar state can therefore block the very recovery action needed. Whole-form/frame stability and busy indicators are proxies, not all evidence of a real writer. **Decision:** keep one action at a time and wait while writing is actually observed. Separate known-active, waiting-for-input and unavailable-observation states. Use fresh owned observations plus action completion and, where supported, extension stop/settlement evidence to authorize takeover. Do not clear unknown solely because time elapsed; do not let it become an unbounded, unexplained permanent veto. Diagnostic reads and requested stop remain possible. Sources: [managed_runtime.py](../../job_applier/managed_runtime.py), [managed_events.py](../../job_applier/managed_events.py), [simplify_observe.js](../../job_applier/browser_helpers/simplify_observe.js).

<a id="g11"></a>
### G11 — Performance budgets and fallback-phase bans: remove incidental local write gates

**Protects:** runtime cost and uncontrolled loops, not task ownership. **Challenge:** `_strategy_check` rejects all subsequent writes for a semantic field when any matching duration is missing or total duration exceeds `field_seconds`; it runs for local writes. Local dispatch prohibits `extend_budget`. Reporting `residual_fields` with `allowed_fallback=block` also changes write permission based on a telemetry phase. **Decision:** remove missing-duration and field-time rejection from ordinary local execution. Make cost/progress warnings informational unless the user explicitly requested a hard limit. Preserve an explicit no-fallback policy if selected, but represent it as effective action policy, not a phase-string side effect. Keep bounded tool calls for responsiveness. Do not restore expiring local leases. Sources: [managed_runtime.py](../../job_applier/managed_runtime.py), [managed_events.py](../../job_applier/managed_events.py), [workspace_host.py](../../job_applier/workspace_host.py). Existing strategy tests verify this old restriction; they will need replacement when implementation changes it.

<a id="g12"></a>
### G12 — Helper time slices, fill counts and recognition: recover rather than terminate

**Protects:** repeated autofill overwriting data and endless helper loops. **Challenge:** one initial fill/one retry per Workday step, remembered skills-button labels, five-second advancement settlement and unrecognized-state handoffs are helper heuristics. They do not prove that another observed action would be unsafe. **Decision:** keep a bounded call returning `waiting`; allow subsequent calls. Detect repeated unchanged action/evidence loops, then hand off the specific required control. A changed required field, different enabled action or proven non-dispatch may justify recovery. Do not reset counters to hide uncertainty, but do not let cosmetic same-step/same-label identity permanently prevent a new operation. `blocked` should be reserved for an actual unresolved blocker; a recognition miss should be a recovery result. Normal reasons such as `autofill_ready` and `prefer_extension_continue` in the catalog are not restrictions. Sources: [workday_fast.py](../../job_applier/workday_fast.py), [simplify_boundary.py](../../job_applier/simplify_boundary.py).

<a id="g13"></a>
### G13 — Accounts, credentials and authentication: split creation, sign-in and UI recovery

**Protects:** wrong-portal credentials, duplicate account creation, password loss, account lockout and incorrect verification mail. **Challenge:** one-click/one-screen assumptions and a two-not-executed limit apply too broadly. A sign-in action and account creation have different consequences. Missing refs or an unfamiliar checkbox are not rejected credentials. A five-second unchanged screen does not prove an action never happened. **Decision:** retain private retained-credential resolution, candidate/portal association, real challenge/rejection handling and uncertain creation reconciliation. Allow a new observed control recovery after proven non-dispatch; do not exhaust a global account budget because a pointer was covered. Permit bounded sign-in recovery based on actual employer response/lockout signals. Distinguish employer login from Simplify login and use the authorized mailbox helper for verification. Asking for a fresh fact is unnecessary when only the control is broken. Sources: [workday_auth.py](../../job_applier/workday_auth.py), [managed_accounts.py](../../job_applier/managed_accounts.py), [managed_credentials.py](../../job_applier/managed_credentials.py). The recorded covered-control/two-click incident establishes actual cost; not every authentication error is a false stop.

<a id="g14"></a>
### G14 — DOM references, pointer checks, menus and mapped screens: refresh locally

**Protects:** clicking the wrong or stale element, hidden/disabled controls, ambiguous options and unintended submission. **Challenge:** the current response often delegates routine rediscovery to the model. Pixel movement before press can invalidate an otherwise correct control. A Workday click layer may have a different label than the visible button. A completed mapped action occupies the whole logical screen key, and any label containing `submit` is refused even in authentication context. **Decision:** retain pre-dispatch target/visibility checks; rediscover and revalidate boundedly when no input dispatched. Recognize a verified semantic click target/layer instead of forcing through arbitrary overlays. Track specific actions and postconditions rather than prohibiting all subsequent actions on that screen. Classify final Submit using form/step context; regular sign-in, menu selection and Enter need their normal behavior. Keep unsupported control types actionable as capability gaps. Sources: [workday_click.js](../../job_applier/browser_helpers/workday_click.js), [form_controls.js](../../job_applier/browser_helpers/form_controls.js), [workday_auth.py](../../job_applier/workday_auth.py), [cdp_client.py](../../job_applier/cdp_client.py).

<a id="g15"></a>
### G15 — Embedded frames: retain ownership, localize capability failures

**Protects:** selecting another job's frame or a detached/navigated document. **Challenge:** label heuristics, frame depth 4/count 12/first 24 iframes, unsupported transforms and strict redirect checks are implementation limits. A frame diagnostic currently prevents global observation stability. **Decision:** retain root-target ownership, parent association, document freshness and conflicting requisition rejection. Treat discovery/transform limits as specific recovery/capability results. A transformed or unrecognized frame is not proof of a foreign job. Allow unaffected controls and owned inspection to remain usable; refresh a replaced application frame within the same verified flow. Do not declare all embedding support live-verified from synthetic tests. Sources: [browser_frames.py](../../job_applier/browser_frames.py), [browser_controls.py](../../job_applier/browser_controls.py), [managed_runtime.py](../../job_applier/managed_runtime.py).

<a id="g16"></a>
### G16 — Required answers, defaults and consent: ask only for the actual missing answer

**Protects:** inventing facts or reusing an answer for a different question/candidate. **Challenge:** exact text/options can overreact to harmless display changes; helper warnings and optional questions can look like employer requirements. A dropdown failure can be mislabeled as missing information. **Decision:** use approved facts, explicit defaults and saved human answers first; let actual required/validation evidence identify remaining blockers. Support the observed widget. Preserve meaning and option distinctions, and request a new answer only if meaning or applicable facts are unresolved. Keep response provenance/version checks at the answer-record boundary; do not restart an uncertain submission because answers were saved. Park that job when a response is needed, freeing unrelated workspaces. Sources: [application_answers.py](../../job_applier/application_answers.py), [managed_questions.py](../../job_applier/managed_questions.py), [application_runtime.py](../../job_applier/application_runtime.py).

<a id="g17"></a>
### G17 — Final submission and dispatch uncertainty: keep once-only; distinguish intent from dispatch

**Protects:** duplicate final submission and claiming success without sending/confirming it. **Challenge:** the Workday runner sets `submit_intent` from the ledger and subsequently calls confirmation-only mode. The shared submit path can record `not_executed`, yet still return `submission_unknown`; broad pending-intent checks then suppress unrelated recovery and attach/retry. **Decision:** preserve durable pre-dispatch intent and record actual dispatch state. Proven non-dispatch permits fresh validation and a new authorized attempt at that same action. Possible/executed dispatch permits confirmation/reconciliation only. Do not infer non-dispatch from a timeout, unchanged page or missing success message. Final submission controls should route through the existing boundary; no extra end-of-form audit or approval is justified. Sources: [submission.py](../../job_applier/submission.py), [workday_fast.py](../../job_applier/workday_fast.py), [application_runtime.py](../../job_applier/application_runtime.py), [managed_sessions.py](../../job_applier/managed_sessions.py).

<a id="g18"></a>
### G18 — Confirmation scope, evidence and forced inspection timeout: accept sufficient evidence promptly

**Protects:** mistaking a prior/other-job message for this submission. **Challenge:** restrictive post-submit route checks can erase the ability to observe a legitimate confirmation. A 120-second host deadline cannot distinguish useful inspection from abandonment. **Decision:** retain fresh, application-associated confirmation and the profile's accepted evidence sources. One authorized sufficient source is enough; do not add employer-plus-Simplify-plus-email requirements. Keep the no-repeat state while allowing owned evidence inspection and supported reconciliation. Preserve evidence before parking/releasing a workspace; make resource policy explicit rather than converting every delayed inspection into teardown. Sources: [submission.py](../../job_applier/submission.py), [managed_identity.py](../../job_applier/managed_identity.py), [workspace_host.py](../../job_applier/workspace_host.py). Current shared submission already finishes on accepted evidence without requiring another quiescence claim; keep that improvement.

<a id="g19"></a>
### G19 — Selected documents and upload bookkeeping: bind the file, avoid a second audit

**Protects:** uploading the wrong candidate's file or a changed/unapproved asset. **Challenge:** an upload-observed event can be refused because no prior upload-attempt event was recorded, even when Simplify performed it. Older worker code requires its own upload before Submit. **Decision:** keep selected-asset identity/hash checks at actual upload and document registration; satisfy real required documents. Treat missing upload telemetry as a reporting gap, not proof the attachment is absent. The current managed `_documents_status` checks required **selections**, not a universal upload-confirmation prerequisite; do not reintroduce one. Preserve the user's instruction to submit from Review without a final resume/field audit. Sources: [managed_documents.py](../../job_applier/managed_documents.py), [workday_fast.py](../../job_applier/workday_fast.py), [managed_hermes_worker.py](../../job_applier/managed_hermes_worker.py) for older behavior.

<a id="g20"></a>
### G20 — Telemetry, answer history and event validation: separate diagnostics from authority

**Protects:** truthful history, valid timing and avoiding secret leakage. **Challenge:** optional event/history calls occur inline before/after browser actions; failures can prevent the next action or obscure that the previous action already dispatched. Missing duration becomes a field write ban. **Decision:** keep ownership/action/submission ledger correctness mandatory. Make optional activity, performance, answer-history and screenshot capture best-effort with explicit errors, redaction and no replay. Reject malformed or secret-bearing event payloads without falsely declaring the application blocked. `action_start`/`action_end` are coordination records and cannot simply be disabled with logging. Sources: [managed_events.py](../../job_applier/managed_events.py), [managed_redaction.py](../../job_applier/managed_redaction.py), [application_answers.py](../../job_applier/application_answers.py), [application_runtime.py](../../job_applier/application_runtime.py).

<a id="g21"></a>
### G21 — API shape, types and immutable updates: retain at the request boundary

**Protects:** malformed parameters, unauthorized API roles, unknown operations and conflicting record revisions. **Challenge:** these are ordinary programming contracts, not reasons to abandon an employer form. Much of the alarming raw exception count is here. **Decision:** keep schema/type/size and optimistic-concurrency checks. Give the executor the supported signature and exact rejected field; repair the call without replaying an uncertain browser write. A TypeError caused by `phase` in the wrong argument position is a caller/integration bug, not an employer blocker. Avoid exposing unnecessary low-level parameters in the first place. Sources: [managed_api.py](../../job_applier/managed_api.py), [managed_client.py](../../job_applier/managed_client.py), [hermes_plugin.py](../../job_applier/hermes_plugin.py), [managed_settings.py](../../job_applier/managed_settings.py).

<a id="g22"></a>
### G22 — Migration, archive, helper activation and administrative integrity: keep outside applications

**Protects:** corrupted imports/backups, deleting active work, unverified helper activation and stale administrative previews. **Challenge:** counting these as application shutdown policies misrepresents what runs on the hot path. Some preparation/migration work is invoked by startup and should be attributed as environment setup. **Decision:** retain integrity checks for actual administrative changes; do not use them as repeated form-navigation gates. Shared helper/code changes remain outside a live application benchmark. Nothing in this review proves older callers unused, so removal requires a caller map rather than deleting guards by filename. Sources: [managed_data.py](../../job_applier/managed_data.py), [managed_archive.py](../../job_applier/managed_archive.py), [managed_learning.py](../../job_applier/managed_learning.py), [managed_migrations.py](../../job_applier/managed_migrations.py).

<a id="g23"></a>
### G23 — Transport, process and browser capability failures: recover by dispatch state

**Protects:** blind replay after a lost response and operating without a real browser connection. **Challenge:** a CDP timeout or unsupported OS operation is a capability/transport failure; it is not evidence of a wrong job. Marking every lost read as an uncertain write is overly restrictive. **Decision:** distinguish reads, proven not-sent requests, possibly sent writes and actual process loss. Reconnect/read/refresh where ownership is still proven; reconcile possible writes without replay. Classify startup process failures separately from application outcomes. Windows Job Object assignment must succeed before using a browser that relies on it for isolation. Sources: [workspace_host.py](../../job_applier/workspace_host.py), [workspace_process.py](../../job_applier/workspace_process.py), [cdp_client.py](../../job_applier/cdp_client.py).

<a id="g24"></a>
### G24 — Legacy workers, leases, transport tokens and older agent loops: keep off the local path

**Protects:** older HTTP/worker contracts, model selection and shared browser leases. **Challenge:** their rules are easy to confuse with the current canonical local runtime. Older paths contain extra upload, Enter-key, headed-browser and lease/telemetry restrictions. **Decision:** ordinary applications use the local session path, which already avoids API tokens, a running dashboard and expiring ownership. Keep compatibility-only checks isolated and document the callers that still need them. Remove a legacy helper only after verifying its consumers; a newer fast path alone is not proof it is unused. Shared utilities may still serve current paths. Sources: [hermes_adapter.py](../../job_applier/hermes_adapter.py), [managed_hermes_worker.py](../../job_applier/managed_hermes_worker.py), [native_hermes_session.py](../../job_applier/native_hermes_session.py), older `agent.py`/`login_guard.py`.

## Canonical skill restrictions also need review

Code is only part of the stopping behavior. The two canonical skills influence executor decisions and must agree with the new runtime contract.

| Instruction | Assessment |
|---|---|
| Use the assigned local session, configured candidate, retained credentials and approved file | Keep. Directly supports ownership and data selection. |
| Simplify fills; targeted recovery handles exceptions | Keep the user's chosen workflow. Missing Simplify recognition must lead to supported recovery/setup, not an invented employer rejection. |
| Never compete with active or unknown writers | Keep active-writer exclusion; define a real recovery for unknown. The word “unknown” must not freeze the workflow indefinitely. |
| One initial fill plus one retry per step; one mapped screen decision | Replace rigid executor prohibition with repeated-no-progress detection and action-specific uncertainty. New relevant evidence or proven non-dispatch can justify another action. |
| Never repeat an uncertain submission/account creation | Keep; specify uncertain **dispatch**, not merely that an intent row exists or a helper could not read the page. |
| Handle approved facts/defaults before asking; optional unanswered fields can remain | Keep. Known answers with broken controls need technical recovery, not another question to the user. |
| No in-run PDF extraction, resume hunting, career-history reconstruction or helper edits | Keep for this selected workflow and benchmark discipline. These are scope/performance instructions, not reasons to terminate an application with an available approved file. |
| No final resume/field audit; one sufficient authorized confirmation source | Keep. Do not reintroduce extra prerequisites through lower-level helpers. |
| Bounded calls and explicit elapsed-time reporting | Keep responsiveness and honest measurement. A time slice ending is not a failed application. |
| `blocked` followed by “handle the actual blocker”; helper exception is not employer rejection | Strengthen the distinction in tool results so the executor does not have to infer it from prose. Preserve the same live session for recovery. |

Sources: [job-apply](../../skills/productivity/job-apply/SKILL.md) and [workday-simplify](../../skills/productivity/workday-simplify/SKILL.md). No skill was changed by this assessment.

## Concrete simplification sequence

1. **Unify job identity and remove the diagnostic dead end.** Modify the existing identity helpers/callers; add no new service. Cover normal posting/application/login/confirmation flows and different-job rejection. Keep task ownership unchanged.
2. **Separate refusal from termination.** Return actionable states for waiting, inspection, required input and setup recovery. Reserve terminal outcomes for actual completion, stop, unrecoverable employer requirements or a documented inability to continue after supported recovery.
3. **Remove incidental write vetoes.** Field timing/missing telemetry, a global two-not-executed account limit, one-action-per-screen and final-submit substring checks should not act as blanket bans. Preserve the few dispatch-specific protections.
4. **Repair writer and control recovery in place.** Keep serialized writing, but refresh stale refs and permit evidence-based settlement/takeover. Scope frame failures to their controls/documents. Limit repeated unchanged actions rather than all actions of a kind.
5. **Separate submission intent, dispatch and confirmation.** Proven no-dispatch can recover; possible dispatch cannot replay. Accepted proof finishes promptly. Preserve useful evidence instead of closing it on an unrelated timer.
6. **Align the skills, caller contracts and tests.** The executor should see the minimum useful operations and explicit recovery, without low-level ownership bookkeeping or duplicate safety rituals. Existing source/caller map remains authoritative.

These are review recommendations. They do not authorize a new employer application or claim that a production fix has been deployed.

## Acceptance criteria for that implementation

Synthetic fixtures should establish these outcomes before another ordinary authorized application:

- Same job across case/locale/location/title/route/login/query/embedded-form changes continues without a new user approval.
- A genuinely different requisition, candidate, host ownership or foreign target rejects the offending write; the rightful task remains usable.
- All identity consumers agree about the same synthetic jobs, including duplicate history and target binding; persisted history is not rewritten to make the test pass.
- An unresolved job identity still permits sanitized owned diagnostics and navigation back to the assigned job. It does not grant arbitrary job-form writes.
- A timed-out read, missing performance span, helper slice ending, stale ref or temporary capacity contention does not finish an application.
- A known active writer still prevents concurrent native writes; unknown state has a tested supported recovery without resetting it arbitrarily.
- Two covered, proven not-executed clicks do not prohibit a different valid observed recovery; a possibly dispatched creation or final Submit is not replayed.
- Reference/referrer email fields do not trigger applicant-identity mismatch; a wrong actual applicant/account email does.
- A legitimate authentication control labelled Submit is handled as authentication, while final application Submit uses the one-time submission boundary.
- Required facts/defaults and sufficient confirmation work through the same shared helpers; no added final audit or second confirmation source appears.
- Slow readiness and ongoing confirmation inspection remain recoverable within explicit resource policy; requested stop still terminates the owned tree before reuse.
- Optional diagnostics may fail without losing mandatory action/dispatch bookkeeping or causing a second browser write.

Run focused regressions for the changed contracts and one final managed suite. Do not add tests merely preserving the restrictions rejected by this assessment. Real ATS support and elapsed application performance remain separate acceptance evidence.

## Audit method and validation

The preliminary number **528** was an AST count of literal exception sites across 44 selected runtime-related Python files. It was not 528 independent restrictions. The broader companion catalog scans 62 Python/JavaScript files and also includes named return reasons, inline/embedded reasons, status outputs and dynamic exception expressions. Many entries are parameter validation, normal progress or administrative-only conditions. Do not use that total as the product's count of shutdown policies.

The source snapshot fingerprint is `0d2a75118b9ea6771f1fd811433cecf161eca6a24e46a571fef234e19c642196` (hash of the enumerated source paths and bytes). The checkout contained existing uncommitted implementation changes; this review evaluates those bytes rather than claiming the Git HEAD alone identifies the code.

Review traced the canonical startup/session/host, Workday runner/auth, shared browser/frames, identity/history, writer/strategy, submission, document/answer, event and compatibility boundaries. The catalog indexes explicit named sites; silent Boolean predicates, inferred UI states, dynamic external failures and skill prose are assessed above. This is a static/caller review with read-only historical evidence, not exhaustive dynamic reachability or proof of every possible ATS response.

Read-only synthetic probes confirmed:

| Probe | Current result |
|---|---|
| Same synthetic Workday URL plus normal application suffix | Scope and history both accept. |
| Same requisition, rewritten location | Scope rejects; history recognizes the same job. |
| Same requisition, rewritten title | Scope rejects; history recognizes the same job. |
| Different requisition | Both reject identity equivalence. |
| Matching semantic field event with missing duration | `semantic_field_timing_unknown`. |
| Matching semantic field events totaling 61 seconds with 60-second field setting | `semantic_field_budget_exceeded`. |

No browser was launched, application retried, credential read, or production record edited for these probes. Documentation links, catalog coverage and source fingerprint are checked after writing the report. No runtime implementation or test contract is changed by this documentation-only audit.
