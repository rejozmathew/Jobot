> Historical snapshot: this preserves the former engineering index and September implementation handoff. Its acceptance status and instructions describe those checkpoints. Use the [current documentation](../README.md) and [engineering index](README.md) for present behavior.

# JobBot modernization — Windows Hermes implementation handoff

## Current design and execution evidence

Start with [APPLICATION_RUNTIME.md](APPLICATION_RUNTIME.md) for the implemented
local-session architecture, helper ownership, evidence storage and deferred work.
[RUNTIME_SIMPLIFICATION_LOG.md](RUNTIME_SIMPLIFICATION_LOG.md) records the design's
evolution, checkpoint commits, verification and deferred design proposals. Read
its current entries before interpreting older review documents. Per-application
outcomes, detailed diagnoses and evidence belong in the managed database and its
private artifacts; existing attempt reports expose retrospective annotations.
Engineering checks do not establish universal ATS or headless Simplify support.

[STOP_CONDITION_AUDIT.md](STOP_CONDITION_AUDIT.md) assesses application restrictions
from first principles, distinguishes essential ownership/submission protections
from recoverable helper failures, and records proposed removals and narrower
checks. Its [source catalog](STOP_CONDITION_CATALOG.md) indexes the current guard
sites. These are assessment documents, not a claim that the proposed changes are
implemented.

Additional Workday authentication recovery is deferred pending broader evidence
from distinct applications. The runtime document contains the standard request
prompt for any ATS and describes how to retrieve stored application diagnoses.
[WORKDAY_NEXT_RUN.md](WORKDAY_NEXT_RUN.md) describes measurement and preserves
historical benchmark instructions; it does not authorize another application.

## Historical runtime review

[REVIEW_HANDOFF.md](REVIEW_HANDOFF.md) preserves the earlier internal-auth fix,
browser/service outage and independent-review questions. Those observations
describe that checkpoint, not current runtime availability.

## Ordinary Hermes connection

[HERMES_CONNECTION.md](HERMES_CONNECTION.md) documents the verified environment-free internal-auth connection, CLI entry, role boundaries, file-level ownership, limitations and later refactor plan. It does not require a dashboard worker conversation.

## Current Workday fast-path engineering

The later authorized Simplify-first improvements are documented in [APPLICATION_RUNTIME.md](APPLICATION_RUNTIME.md): repository-owned skills, shared versus Workday helper responsibilities, explicit managed data ownership and harness-neutral execution. Use [WORKDAY_NEXT_RUN.md](WORKDAY_NEXT_RUN.md) for the separate clean-thread live benchmark. Offline verification does not establish live performance or universal Workday support.

## Historical paused checkpoint (2026-09-07)

Start with [the current review handoff](REVIEW_HANDOFF_2026-09-07.md). It records all accumulated changes since `e711112`, two failed Huron attempts, the latest 440-pass offline gate, and the still-unresolved credential-field failure. **This is not a working Workday release.** The user paused further implementation and application runs; the historical kickoff below is not an instruction to resume them.

Review snapshot: `review/jobbot-huron-auth-checkpoint`. Private runtime data and credentials remain outside Git. The remaining text preserves the original implementation brief and its historical evidence links.

## Original implementation brief

Prepared: 2026-09-06.

Implementation checkpoint: the original specification below is preserved. Current evidence is in [STAGE3_EVIDENCE.md](STAGE3_EVIDENCE.md), [STAGE4_EVIDENCE.md](STAGE4_EVIDENCE.md) and the [34-ID acceptance ledger](ACCEPTANCE_LEDGER.md). Follow [WINDOWS_RUNBOOK.md](WINDOWS_RUNBOOK.md) for gated activation/rollback; [LATER_UBUNTU_ROLLOUT.md](LATER_UBUNTU_ROLLOUT.md) remains a plan only. The reviewed Windows engineering candidate is **not fully accepted for live applications**.

This is a specification and instruction package. It does not contain an implemented application, and it is not a report of passed application tests.

## Final decision

Use the existing **Windows Hermes** as the primary builder and integration tester, using the strongest appropriate model actually available through its configured provider. Retain the current job-application conversation long enough to capture its working knowledge and explicitly switch into an engineering task. Do not continue applying to jobs while rewriting the same application or shared skills.

All implementation and current testing happen on the main Windows PC. Ubuntu is not a prerequisite. After Windows acceptance and review, publish sanitized code and skills to GitHub and perform a separate update/validation of the existing `ubuntubot` installation.

Codex is optional as a fresh reviewer, not a required coordinator or middleman. Do not have Codex and Hermes simultaneously edit the same checkout. This choice is about preserving the user's tested workflow, not a claim that one harness is universally superior.

## Files

| File | Purpose |
|---|---|
| `PRD.md` | Authoritative behavior, architecture, boundaries, and scope |
| `IMPLEMENTATION_PROMPTS.md` | Kickoff for the current Windows Hermes conversation and staged checkpoints |
| `ACCEPTANCE_AND_DATA.md` | Windows acceptance checks, safe fresh test data, and evidence requirements |
| `LATER_UBUNTU_ROLLOUT.md` | Deferred GitHub-to-VM update, private data migration, and verification |
| `SOURCE_NOTES.md` | Reviewed baseline, supplied skills, official documentation, and evidence limits |

Put these files under `docs/jobbot-v1/` in the Windows repository. The builder creates a living `EXECUTION_PLAN.md` and requirement-to-test map there. Capture private runtime details outside Git in a verified ignored location. The plan records what has been done; it must not silently change the PRD.

## Start

Paste the kickoff in `IMPLEMENTATION_PROMPTS.md` into the existing Windows Hermes job-application conversation. It instructs Hermes to inspect the actual checkout and skills, preserve working knowledge, create an implementation branch without discarding local changes, initialize separate synthetic test data, and then implement in stages.

One coordinated task is preferred over many unrelated prompts. The stage prompts are checkpoints or resumption instructions, not a request to start five agents. Continue reversible local engineering without asking after every file change. Credentials, destructive changes, live external actions, and deployment remain explicit boundaries.

## What stays

Hermes reasons and applies sequentially in bounded batch sessions. Simplify handles bulk filling. The app owns the queue, account registry, attempt state, concise timeline, timing, controls, and durable procedural lessons. Multiple discovery tools and manual URLs feed one intake service. The worker protocol is independent of Hermes, model choice, and autofill provider.

## What not to do

Do not rewrite the autofill engine, rebuild Hermes, port Autograph broadly, replace the frontend framework, or add cover-letter generation to this release. Do not wipe existing databases or copy credentials/browser profiles into Git. Do not debug against Ubuntu yet. Do not claim Windows tests establish Ubuntu production readiness.

The first Windows database is a new synthetic development instance, not a deletion of the old database. A real Windows pilot's submissions/accounts are real history and must survive eventual migration. A new email address does not justify applying again to a previously submitted requisition.
# Current queue and VM handoff

See [single-job queue and existing Ubuntu VM runbook](QUEUE_AND_VM_RUNBOOK.md)
for the new dashboard launcher, manual/API/discovery intake, sequential Hermes
dispatch, email context, additive migration and deployment templates. This does
not mean the user's VM or any employer portal was live-validated by this change.
