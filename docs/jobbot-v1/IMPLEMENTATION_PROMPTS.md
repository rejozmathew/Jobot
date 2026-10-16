# Prompts for Windows Hermes

Use one PRD and one living execution plan. The kickoff can drive all reversible local stages; the later prompts are checkpoints/resume instructions, not instructions to launch concurrent authors.

## 1. Kickoff: paste into the existing Windows job-application conversation

```text
We are changing the objective of this conversation from applying to jobs to engineering the application workflow. You, Windows Hermes, are the primary implementer and integration tester. Do not start another normal application run while editing the same shared code or skills.

Read docs/jobbot-v1/README.md, PRD.md, ACCEPTANCE_AND_DATA.md, and this IMPLEMENTATION_PROMPTS.md. The approved baseline is rejozmathew/auto-job-applier, branch hermes-modified, last reviewed commit 923f2576f9c059370222ef416f50f97a8cfc9f70. Inspect the actual checkout, branch, active processes and uncommitted changes first. Preserve all user work; do not reset/clean/force-checkout. Use a separate implementation branch or worktree safely.

First capture your working knowledge: actual skill/helper locations, successful Simplify sequence, known failure patterns and workarounds, actual application/DB/browser configuration paths, installed Hermes version, effective provider/model, and connector identity. Write a concise private runtime handoff in a verified ignored location, with no passwords, tokens, OTPs, cookies, private email contents, or raw reasoning. Inspect files rather than relying only on conversation memory. Distinguish tested behavior from assumptions. Preserve the job-apply, old useful references and actual job-posting-harvest knowledge; do not copy the whole Hermes profile or personal mailbox.

Verify the configured model actually resolves to the requested Astra model through the intended subscription provider. Do not silently switch to an API key, paid fallback, or a different model. If unavailable, report the available configuration instead of pretending it is active.

Then create docs/jobbot-v1/EXECUTION_PLAN.md and a requirement-to-test map. Implement stages 1–4 below, with tests and small reviewable commits, continuing reversible Windows engineering without asking after every file edit. Maintain a checkpoint so a new session can resume if this conversation becomes too large.

The product remains Hermes pulling one reserved job at a time through a batch, with continuity and reusable helpers; Jobot owns queue/history/accounts/timing/controls. Simplify is preferred but recovery is flexible. The core worker protocol is agent-neutral. Do not replace this with mandatory fresh-per-job conversations, an internal agent rewrite, or another autofill framework.

Use a NEW synthetic Windows development database and isolated test configuration. Do not delete, relabel, or overwrite existing runtime histories, profiles, credentials or browser data. Do not modify Ubuntu, Unraid, VM schedules, or VM databases. Do not start real job submissions, account creation or password resets during offline development. Do not change unrelated cron tasks. Existing real workers must be quiescent before shared-runtime integration testing.

At each stage report changed files, exact commands/tests run and their real outcomes, remaining gaps, and next action. Check installed Hermes tool/hook interfaces rather than inventing commands or APIs. If credentials or a live external test require authorization, complete unrelated local work and mark that test pending. Fixture success is not proof that live Workday/Simplify works.

After offline implementation, run an isolated Windows integration scenario using your own real tools and the app's telemetry. An end-to-end test passes from assertions and observed evidence, not because you narrate that it worked. Use a separate explicit test run, not simultaneous coding and uncontrolled real applications. Finish with a reviewed Windows release candidate and a later Ubuntu rollout plan; do not deploy or push without authorization.
```

## 2. Implementation stages

### Stage 1 — baseline, data, and shared services

Inspect existing code/tests/skills; confirm known issues before changing them. Create explicit development paths and synthetic data with submissions disabled. Preserve baseline test failures in the report.

Implement versioned migrations and the shared intake, job/identity/account, run/attempt, atomic-claim, ownership, timing/event and control services. Adapt existing API/CLI routes to the same services. Stop applied-job resurrection, duplicate active attempts, broad startup failure cleanup, and historical-step deletion on retry. Handle uncertain submission and stale-worker state explicitly.

Provide a fake non-Hermes worker and test genuine service behavior, including concurrent clients and idempotent retries. Add preview/backup/new-instance tooling without running it on user data. Do not make a brand-new UI or browser integration a prerequisite to testing the core.

### Stage 2 — Windows Hermes integration and Simplify behavior

Inspect actual installed hook/tool signatures and invocation support. Implement a small adapter/client with automatic redacted timings, attempt/action correlation, durable event delivery, control checks, and coarse semantic milestones. Preserve batch sessions and checkpointing. Do not fork Hermes core.

Consolidate the canonical application skill and helpful references; deprecate conflicting old trigger instructions. Remove the legacy internal-agent command as the normal execution path, hard-coded personal paths, kill-all-browser recipes, and blanket factual answers. Change discovery output/handoff only using the actual existing harvesting skill.

Implement the small Simplify boundary: discovery, observable status, autofill trigger, preferred continuation, and explicit residual/fallback reasons. Preserve reasoning freedom, handle missing/stale controls, verify page/field changes, and coordinate single-writer takeover. Tests first use representative local forms and sanitized extension observations, not fake claims that Simplify officially supports those fixtures.

### Stage 3 — UI, effective settings, learning, and optional metadata

Connect the UI to external runs/attempts rather than the old runner's in-memory state. Show queue/batch/current job/page/activity, true timing, last heartbeat versus progress, issue, and acknowledged controls. Keep routine screenshots and raw reasoning off. Escape untrusted text.

Implement worker/autofill/model separation in effective settings, explicit fallback, market/submission policy, budgets, and deployment/skill version visibility. Unsupported options must not appear functional.

Implement relevant lesson/helper retrieval and versioned reuse, including across a new session. Keep shared code/skill activation controlled. Accept and display externally supplied fit assessments and versioned resume/cover-letter metadata; do not implement generation/scoring.

### Stage 4 — Windows hardening and integration

Run the acceptance matrix with temporary data. Exercise restart/concurrency/delayed-event cases, secret redaction, truthful controls, correct account identity and unknown outcomes, tab ownership, all intake routes, and helper continuity.

Then exercise the actual Windows Hermes adapter and existing Simplify-enabled browser serially under an explicitly selected test run. Verify what the real panel permits; do not hard-code nonexistent controls or silently fake completion. Start with safe fixtures; any real job/account/submission is separately authorized. Preserve real pilot accounts/submissions as real history.

Prepare sanitized Git diff, exact test report, user-facing launch instructions, version manifest and rollback notes. Do not involve Ubuntu yet. Fix findings; stop at the Windows release gate, not at a confident summary with tests missing.

## 3. Independent review prompt — optional Codex or fresh Hermes review session

```text
Review the implementation diff against docs/jobbot-v1/PRD.md and ACCEPTANCE_AND_DATA.md. Do not rely on the implementer's summary. Inspect code and execute focused checks against isolated Windows test data. Do not edit the running application or browse real jobs during this review.

Prioritize duplicate claims, stale events, applied-job resurrection, restart recovery, uncertain submissions, account namespace/identity, automatic timing, pause/stop acknowledgement while Simplify is active, silent legacy fallback, preservation of batch context, fresh-session helper reuse, secret/UI injection, and destructive data-reset behavior. Check that optional scores/documents are real storage features, not placebo UI.

Return concrete findings with file/line and reproduction or reasoning, distinguishing confirmed bugs from risks. Report exactly which tests were run and what remains unverified. Do not lower requirements to obtain passing tests or fabricate live integration results.
```

## 4. Resume prompt after context compaction or a new session

```text
Read docs/jobbot-v1/README.md, PRD.md, EXECUTION_PLAN.md, the requirement-to-test map, and the private runtime handoff. Inspect actual git status/diff. Resume the recorded Windows engineering stage. Do not restart the design, erase user work, or assume an old tool/API still matches the installed runtime. Reuse existing helpers before creating alternatives. Continue reversible local work; report actual tests and remaining external gates.
```

## 5. Later Ubuntu update prompt — do not execute in the Windows phase

```text
The Windows release candidate has been accepted and published. Update the existing ubuntubot installation to the explicitly approved commit using docs/jobbot-v1/LATER_UBUNTU_ROLLOUT.md. This is a separate authorized rollout, not a reinstall or an instruction to copy the entire Windows directory.

Inspect the existing VM services, checkout, configured DB/identity, Hermes/skills, browser/Simplify profile and active attempts. Preserve existing data and sessions. Create verified backups and show the intended code/data/config changes. Recreate Linux dependencies, install the same sanitized skills, preserve/reconnect dedicated credentials privately, and use explicit Linux paths. Do not copy the Windows virtual environment, browser cookies, or disposable test DB.

Reconcile and transfer any real Windows pilot account/submission history privately, without overwriting newer VM records. Ensure only one machine applies for the real identity. Validate core tests plus actual graphical/Hermes/Simplify/mail integration before enabling unattended operation. Record the actual result and remaining issues; do not declare Ubuntu ready from Windows tests alone.
```
