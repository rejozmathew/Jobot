# Product and implementation brief: managed Hermes application runs

**Status:** specification, not implemented code or verified production behavior.

**Reviewed repository baseline:** `rejozmathew/auto-job-applier`, branch `hermes-modified`, commit `923f2576f9c059370222ef416f50f97a8cfc9f70`. Inspect the actual checkout and unpublished changes before editing. Do not reset, clean, force-checkout, or overwrite user work to match this baseline.

## 1. Goal and immediate environment

Modernize the operational harness around the working Hermes + Simplify workflow. The user needs to see what is queued, what is running, which page is blocked, true start/end/duration, what fixed a problem, and whether that fix is reused. The aim is reliable unattended operation and measurable improvement, not a new browser-agent framework.

**For this implementation, everything runs and is tested on the main Windows PC. Windows Hermes is the implementation owner and the real integration worker.** It has existing application context, skills, browser access, and helper knowledge. First capture that knowledge in files, then explicitly switch the current conversation to engineering. A long conversation is not a substitute for durable checkpoints; another engineering session can resume from the plan when necessary.

Ubuntu deployment is deferred. Write configurable, reasonably portable code, but do not require SSH, WSL, Linux testing, VM provisioning, or VM data resets to complete Windows development. A later rollout updates the existing VM rather than reinstalling its operating system.

Default product behavior remains Hermes pulling one application at a time in a continuing batch session. Simplify is the preferred bulk filler, with flexible, bounded residual recovery. The app is the system of record. Model/provider choices are configuration; do not hard-code model names, benchmark claims, or subscription entitlements into the application.

## 2. Scope

Build now: common intake; run and attempt ownership; agent-neutral APIs/client; actual Windows Hermes integration; automatic timing and meaningful progress events; account registry; reliable controls; Simplify-first policy; scoped lessons/helper discovery; effective settings; and minimal storage/display for externally supplied match assessments and documents.

Keep: existing Python/FastAPI/SQLite foundation, useful CDP utilities, working skills, discovery processes, Gmail connector, and existing profile facts. Integrate rather than discard useful modules.

Not now: another production agent, a broad native autofill rewrite, an Autograph port, a new discovery system, a frontend-framework migration, parallel browser workers, automatic cover-letter generation, automatic fit scoring, a vector database, or a new vault platform. Do not promise that this refactor alone makes every application finish in five minutes.

## 3. Separate the concepts

| Concept | Initial choice | Boundary |
|---|---|---|
| Trigger | Hermes cron/manual request; dashboard may request a run | A trigger does not own the queue or bypass reservations |
| Worker | Hermes | Adaptive reasoning and application execution |
| Bulk autofill provider | Simplify | Replaceable browser-side mechanism, not operational truth |
| Reasoning provider/model | Whatever is configured and verified in Hermes | Independent of queue, records, and UI |
| Operational state | Jobot | Authoritative intake, reservations, accounts, events, outcomes |

Discovery stays external. Hermes discovery, another discovery app, and manual URL input call the same intake service. The core application must not import Hermes-specific conversation objects to understand a job or attempt. A Hermes session ID is optional worker metadata.

The common protocol must work with a fake non-Hermes worker. No second production harness is required to demonstrate loose coupling.

## 4. Preserve batch continuity

A worker registers/accepts a visible run and claims one job at a time. It can retain its conversation across several applications. Database attempts and browser ownership are isolated per job; conversation continuity does not need to be.

Before each job, return the authoritative job/profile package, selected resume, applicable submission/market policy, account context, effective settings, and a bounded set of relevant helpers and lessons. The worker must not have to remember to search the entire repo for a helper it created earlier.

At job boundaries save useful observations and a checkpoint. At session boundaries save a compact handoff referencing durable records, not a raw transcript. A new session must be able to reuse the helper learned by a previous one. Previous employer-specific answers must not leak into the next application.

The database wins when conversation memory disagrees about account existence, an application outcome, or ownership. A timeout in a chat delivery is not proof that its detached browser/process stopped.

## 5. Unified intake and job identity

Preserve single URL, bulk/API, and manual intake. Route them through one service. Keep source type, source/external message ID, discovery timestamp, original source URL, resolved official job URL, application URL, company, title, location/country, and requisition ID when verifiable. Unknown metadata stays unknown. Multiple sources can point to the same job.

Prefer a verified portal namespace + requisition ID for deduplication; otherwise use conservative URL normalization. Strip only known tracking parameters. Do not globally remove every `rx_*`, `token`, or query parameter: some parameters can identify the job or route. Test both aliases and genuinely different requisitions. Retain safe original URLs for provenance, not password-reset/OTP tokens.

A new application email is a distinct account identity, not a different person for duplicate-submission checks. Retain a minimal trusted historical submission ledger across identities. Different roles at the same employer are not automatically duplicates.

Adding a job is not permission to execute it. Store eligibility/hold/exclusion decisions. An automatic policy may mark suitable jobs ready without individual user review, but an intake source cannot override exclusions or expand a selected batch through prompt instructions embedded in a job description.

## 6. Logical data model

Extend existing models using tested versioned migrations. The following are logical entities; do not create redundant parallel tables when existing ones can be extended safely.

**Candidate identity:** person-level key, application email, active/legacy/disabled state, authoritative profile/version reference. Keep personal defaults outside distributed code.

**Job and provenance:** fields above, eligibility decision, source records, historical suppression/reconciliation state.

**Run/batch:** trigger/request ID, requested/accepted/start/end times, selected job order or explicit selection policy, planned count, state, worker/session segments, effective settings. New discoveries do not silently grow a fixed batch.

**Attempt:** job/run/identity/worker/session IDs, observed ATS/tenant/form/page, browser profile/target ownership, start/end/outcome, current activity/phase, heartbeat, last verified progress, code/skill/helper versions, settings snapshot, elapsed/wait/repair time, submission-intent and confirmation references.

**Events:** immutable event ID, attempt/run/action correlation, event type, actor/source, observed time, recorded time, start/end/duration where appropriate, outcome and bounded sanitized payload. Retrying a request cannot duplicate events. Delayed callbacks must retain the attempt active at action start, not the next job's current ID.

**Portal account and account events:** selected identity, verified account namespace, company/platform association, username/email, credential reference, creation/verification/login/recovery state and timestamps, evidence/provenance, related attempt. No raw passwords or OTPs in ordinary DB fields or events.

**Lesson/helper:** condition, scope, suggested action, expected result, supporting attempts, version/path/tool contract, limitations, candidate/trial/verified/retired state, success/failure counts and last verification.

**Document and assessment:** externally supplied versioned resume/cover letter and fit-assessment metadata. Details are in section 13.

Track job country/form language/compensation currency and period when relevant. Unknown ATS is not the same as a confirmed proprietary form. A company landing page can redirect to an ATS. Detect and record that evidence without inventing confidence.

## 7. Claims, state, and concurrency

Use atomic claims and durable ownership, not SELECT-then-UPDATE races or only an in-process boolean. Enforce one active application owner per configured browser profile and one active attempt per job. Use lease/fencing generation or equivalent stale-owner protection.

Required semantic distinctions include requested/awaiting worker, active, waiting external, pause requested, paused, stop requested, ready for review, applied/already applied, blocked, skipped, failed, interrupted, and submission unknown. Exact enums may vary, but transitions must be documented and tested. Control state can be separate from business outcome to avoid an unnecessarily enormous enum.

Normal retry cannot resurrect an applied job. Same-result completion is idempotent. Conflicting finishes and stale owners cannot overwrite a newer outcome. Separate historical event ingestion from permission to mutate current status.

API startup must not mark all running jobs failed. Reconcile worker liveness and ownership. An expired lease does not prove the browser stopped: quarantine/reconcile the context before reassigning it. An unconfirmed submission is non-retryable until reconciled through appropriate evidence.

One process owns browser writes at a time; Simplify activity must also be considered before a native/Hermes takeover. Raw unrestricted terminal/CDP access can bypass cooperative safeguards, so do not claim database leases alone are a security sandbox. Mediate ordinary actions through the adapter, restrict shared-code/secret access where practical, and document residual limitations.

## 8. Worker interface and Hermes integration

Expose a small authenticated versioned HTTP/JSON interface and a thin local client/CLI backed by the same services. Preserve compatibility with useful existing intake/CLI operations. Bind locally by default; do not expose a powerful unauthenticated API or CDP port to the network.

Required operations: intake; request/register/accept run; atomic claim; get current job context; heartbeat/control polling; append events; account query/update; checkpoint/resume; finish/reconcile; request/ack pause/stop; register/retrieve lessons/helpers; register documents/assessments; read UI/reporting state.

Requests must include appropriate correlation, ownership and idempotency information. Return structured failure reasons (already applied, owned elsewhere, stale owner, awaiting worker, reconciliation required, unsupported capability). These are proposed interface semantics, not claims about existing commands.

A dashboard request must either reach a verified worker pickup mechanism or visibly remain awaiting worker. Keep the actual start/wakeup mechanism simple and adapter-specific. Discover the installed Hermes command/gateway facilities; do not invent an undocumented Hermes REST endpoint. The normal path can remain Hermes cron pulling work. Do not start a second competing scheduler just to support a Run button.

Implement a small Windows Hermes plugin/tool/client integration. Inspect its actual installed version and hook signatures, CLI behavior, effective profile, skill resolution, browser backend, and dedicated connector identity. Do not fork or monkey-patch Hermes core as the default solution.

Automatic tool hooks provide timings and safe operational results. Application-aware helpers or explicit milestones provide semantic facts such as Simplify settled with two residual questions. A generic tool result is not proof of a page transition or submission. Keep callbacks fast; do not spend a model call just to describe every preceding model call. Redact before local spooling or delivery. Replaying events cannot revive expired ownership.

The worker startup must prove it loaded the intended application skill and settings and connected to the intended browser profile. Missing telemetry/provider capability is visible. A session/turn end hook is not application completion.

## 9. Skills and code knowledge

Inspect the user's actual Windows skill directories. The supplied archive contains the newer `job-apply` and older `job-application-submit`, with overlapping procedures; it does not contain `job-posting-harvest`. Discover that existing skill locally, do not invent or rebuild it.

Create one canonical versioned application skill source and predictable installation/sync into the selected Hermes profile. Preserve useful old references, especially scheduled handoff, duplicate protection, and uncertain-outcome reconciliation. Deprecate overlapping active skills so a cron request cannot select the wrong execution philosophy.

Remove the old normal-path instruction that advertises `run_applier.py apply` when that path actually launches the legacy internal agent. Fix stale references to nonexistent handlers after source inspection. Replace hard-coded personal paths and kill-all-browser recipes with explicit configuration and owned-target operations.

Keep factual answers authoritative: do not default every skill question to Yes, general experience to a fixed number, or negative questions to No. Hermes can interpret wording and draft supported explanations; it cannot fabricate facts or silently alter eligibility/submission policy. Separate country-specific answers from generic mechanics.

Use the dedicated Gmail connector for correlated OTP/reset/verification messages where available. Browser mail access is a controlled fallback. Do not browse or copy the personal mailbox just because it was used in an old skill.

During engineering, record the real working flow and helpers in a private checkpoint before edits. Test with the selected staged skill version. Do not let the currently active application session read a half-written shared skill.

## 10. Simplify-first, with flexible recovery

Do not treat Simplify as a mandatory button sequence. Treat it as the preferred bulk-fill provider with observed availability and progress.

For each page:

1. Identify the correct application target, page and possible dependencies/repeaters. Check whether Simplify is already doing useful work.
2. When available and not already active, invoke its autofill. Avoid double triggers after navigation/rerenders.
3. Observe actual field value/selection changes, row creation, uploads, validation, page changes, relevant loading indicators, and readable panel status. Quiet DOM or unchanged empty-field count alone is insufficient.
4. On settled residuals, identify actual questions/options and correct answers, then resolve them in a batch where practical. Do not rerun an entire handler over a mostly completed form.
5. If Simplify is active, ensure it yielded/stopped before another writer changes the same fields. If safe takeover cannot be established, park rather than pretend it is safe.
6. Prefer Simplify Continue when usable. If absent/stale, use a bounded evidence-based portal action or recovery, then verify the page change and rediscover extension state.
7. Check high-impact profile facts and critical fields while filling. An enabled Submit button is not proof of correctness. Avoid unnecessary whole-form rereads, but do not skip evidence-based checks.
8. Under the effective authorized submission policy, durably record submission intent, perform the action, verify confirmation, and finish. Uncertain results must not trigger a blind repeated submit.

A full native form engine is not required. Use the existing useful CDP/handler primitives only for targeted repairs and return explicit unsupported/blocker results. No silent legacy full-form fallback.

Read actual offered dropdown values and scope popups to the triggering field. Handle child menus as paths to verified committed leaves. Country/code semantics must reject a wrong country sharing the same dial code. Use truthful source context or a suitable Other value for referrals; never invent an employee referral. A visible typed string is not always a committed framework selection.

Panel access is useful but not guaranteed; probe the actual DOM/frame/extension UI without assuming a public Simplify API. Report unreadable telemetry honestly and use page evidence. MutationObserver is not a complete value monitor; combine events with small value snapshots. Do not treat an extension animation as application progress.

## 11. Timing, events, controls, and browser cleanup

Main timeline: run started, account reused/created, Simplify started/settled, residual items identified/resolved, navigation attempted/verified, email wait, recovery attempted, submission confirmed, and owned tab cleaned. Include company/job/ATS/page, concise action, result, elapsed time, and evidence source. No raw private reasoning or routine screenshots.

Expanded diagnostics: bounded tool timing, error codes, retry counts, relevant sanitized field evidence, settings/code/skill versions. Screenshots are disabled by default and can be explicitly enabled for a request or diagnostic policy. Capturing one does not automatically send it to a model. Do not capture full email contents, passwords, cookies or sensitive answers indiscriminately.

Record absolute UTC requested/start/end timestamps plus chosen local display timezone. Use monotonic durations inside a process, wall time across persisted attempt segments, and mark uncertainty after crashes. Distinguish queue waiting, model/tool waiting, Simplify, residual work, email/human wait, inline engineering, verification and cleanup. Total elapsed includes waits and debugging. Do not add overlapping durations as though they were serial. Preserve retries and resumed segments.

Track heartbeat separately from last verified progress. A five-minute goal is not a stopwatch that proves success. Use configurable field/no-progress/attempt budgets; crossing the target requires a visible bounded extension, park, or escalation. Count repeated failures by semantic page/field/problem, not changing element IDs. Do not report faster performance merely because difficult jobs were abandoned.

Pause requested is not paused. Acknowledgement means actual writes are quiescent, including independent extension activity as far as the integration can establish. Show noninterruptible operations honestly. Stop prevents later claims and future writes; it cannot undo a submitted application. An observer must not become another competing browser operator.

Record tab/target ownership. Close only confirmed completed/dead owned targets, preserving blocked/uncertain tabs when needed for intervention. Never kill all Chrome/Brave processes or close unrelated user tabs. Reconcile stale blocked tabs before reusing the profile, and show preserved tabs in the UI.

## 12. Portal accounts and safe automation

An account can outlive a failed application. Record confirmed creation immediately, separately from verification and application completion. Store a secure credential reference before an authorized creation request so a crash can be reconciled without inventing a new password/account.

Account lookup is scoped to selected candidate identity and verified account namespace. Namespace may require tenant/path, not just hostname. Support verified redirect aliases; never infer shared credentials from company names. Requery context when the worker discovers a different portal.

Statuses include unknown, creation requested, created/unverified, verified, recovery required, locked, disabled. Absence means unknown, not nonexistent. Record sign-in/verification/reset events without secrets. Correlate email by intended recipient, portal/purpose and request time; never use the newest unrelated code. Bound recovery; do not rotate addresses to evade locks/challenges.

Keep passwords, OTPs, OAuth/cookie material, and reset tokens out of Git, ordinary DB telemetry, UI and alerts. Store references; retrieve secrets narrowly through the protected existing facility. File permissions are not encryption, and a worktree is not a security sandbox. Do not add a new vault dependency just to ship v1. Handle genuine human challenges as an explicit blocked state.

## 13. Learning, settings, assets, and fit scores

Record lessons independently of the current agent: condition, action, scope, expected result, supporting attempts, status, and verification history. Keep company-specific facts out of globally reusable procedural lessons. Retrieve a few relevant entries per job, not the whole database.

A helper catalogue identifies capability, version/hash, path/tool invocation, preconditions, limitations and tests. Check it before writing duplicate helpers. File existence, discoverability, compatibility, and correctness are separate requirements. Test same-session and fresh-session reuse explicitly.

Hermes may write bounded attempt-local recovery helpers. Shared skill/code changes go to an isolated repair branch/workspace, with checks and deliberate activation between attempts. Candidate observations can be saved immediately. Do not allow automatic lessons to rewrite candidate facts, company exclusions, credential rules or submit permissions. Record when a lesson fails; support demotion/retirement.

Settings separate worker, autofill provider and reasoning model, plus trigger, browser profile, market policy, allowed fallback, budget, submission mode, screenshot policy, notification and learning activation. Use one effective operational source, environment configuration for paths/endpoints, and protected secret references. Snapshot settings per attempt. Unsupported combinations are disabled/explained, not placebo controls. Keep development defaults non-submitting.

Accept externally supplied match assessments with JD/resume/profile version/hash, evaluator/model, rubric/scale, recommendation/reasons and time. Unassessed is not zero; a fit score is not a hiring probability. Intake and execution permission remain separate.

Accept versioned resume/cover-letter assets with safe private storage reference, hash, job/attempt linkage and provenance. Distinguish available, selected, upload attempted, and upload confirmed. Do not build automatic letter generation now. A required missing document is an explicit blocker. Preserve exactly what was uploaded.

## 14. UI, packaging, and verification

Keep the existing stack. Extract unwieldy inline UI into templates/static files as useful, without requiring a frontend rewrite. Views: intake/queue, current run, attempt timeline, account/history, recurring issues/lessons, and settings/health. Use simple bounded polling or existing infrastructure; no mandatory event platform.

Show selected/completed/blocked/current/remaining work, source/assessment when present, current page/activity, true timestamps/elapsed, heartbeat vs progress, control acknowledgement, worker/session, unresolved issue, and deployed code/skill/settings versions. The authenticated operator should see the resolved DB path and instance ID, so a cron CWD cannot silently create a second history.

Escape external text in the UI. Redact before persistence and alerts. Optional Discord notifications are deduplicated and limited to useful state transitions or summaries; notification failure cannot reverse a confirmed application result.

Deliver a fake worker, automated Windows tests, actual installed-Hermes integration checks and approved browser smoke tests. Distinguish fixtures from real extension/ATS evidence. No test may quietly operate a personal mailbox, active production browser, or real employer with a fabricated profile.

Development uses a separate synthetic DB, not a deletion of user history. Provide a preview/backup/new-instance workflow but do not reset real DBs in the engineering task. Retain prior reliable submission suppressions and any real new-identity account/application records. Test legacy migrations and empty initialization. Do not copy live SQLite files unsafely or publish runtime data.

Version code and sanitized canonical skills together. Preserve uncommitted work and optional older interfaces through deliberate compatibility, not blanket removal. Publish only after review and authorization. The later VM update consumes an exact reviewed commit, a private configuration/data plan, freshly installed dependencies, and a separate Ubuntu validation gate. No Ubuntu work is required in the current Windows implementation phase.
