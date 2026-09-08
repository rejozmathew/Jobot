---
name: workday-simplify
description: Use when applying through Workday with Simplify.
version: 0.1.0
author: Rejo Z Mathew (rejozmathew), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jobs, workday, simplify]
    related_skills: [job-apply]
---

# Workday with Simplify

A Workday execution procedure, not another form filler. The repository owns this procedure and its Python/JavaScript helpers; Hermes, Codex, Claude, or another shell-capable harness reads the same files. Read the shared [job-apply skill](../job-apply/SKILL.md) first.

## When to Use
- An authorized Workday application in the managed JobBot runtime.
- A clean-thread benchmark of one supplied Workday URL.
- Not for code changes, unsolicited applications, or bypassing ownership/reconciliation.

## Prerequisites
- Explicit repository, private absolute configuration, managed identity, approved resume asset, Simplify browser and exact claimed target.
- Run preflight before intake: through your shell/`terminal`, execute `<python> -m job_applier.workday_fast doctor --config <absolute-config> --url <job-url>` from the repository. `history_matches` must be empty; unresolved prior submissions/owners require reconciliation, not a new database.
- Hermes may use native `jobbot`. Other harnesses use the same managed protocol CLI; do not impersonate a requested model. See [transport and ownership](../../../docs/jobbot-v1/APPLICATION_RUNTIME.md).
- Routine login/account creation uses the configured private credential and selected contact identity. Do not use Simplify-generated passwords. Never reset a password without explicit authorization.

## How to Run

After accepting a reserved run, claiming the exact job and binding its observed CDP target:

**Hermes native tool:** `jobbot(operation="fast_forward", parameters={"target_id":"<observed-target>","seconds":60})`.

**Any shell-capable harness:** through its shell/`terminal`, execute:

```text
<python> -m job_applier.workday_fast advance --config <absolute-config> --attempt-id <claimed-id> --fence <claimed-fence> --target-id <observed-target> --seconds 60
```

The same Python function implements both. `advance` is not intake, does not create a run or spawn a model, and requires an already accepted/claimed attempt. Tokens come only from the configured environment reference.

## Procedure
1. Confirm exact role, identity, approved asset, history and submission authorization once. Do not audit every experience/education field.
2. Run `fast_forward`/`advance`. It keeps one CDP connection for the bounded call and performs normal observe/act/wait transitions without model ticks. It checks heartbeat/control each loop and refreshes server-side writer state before every action.
3. `waiting`: continue with another bounded call while progress remains within the existing attempt budget. The checkpoint preserves per-step retry counters and pending advancement. Do not restart autofill, rename a step or reset the checkpoint to evade budgets.
4. `authentication_required`: call `jobbot browser_observe` (or the same managed protocol operation) to refresh server-side quiescence before any credential write. An idle enabled account control can settle the preceding Start action; active or unverified state cannot. Then use the returned observed unique `auth_refs` with the configured credentials helper and the native account/sign-in action. Reuse `account_strategy`; record confirmed account creation immediately. Correct only an actual wrong contact email. CAPTCHA/site verification/rejected credentials are specific blockers, not invitations to resume scraping.
5. `blocked`: address only the returned actual blocker. Prefer one supported Simplify retry after rejected advancement. The runner already permits the initial autofill plus one retry per step. A remaining required consent checkbox or known profile answer can be handled with the existing fenced native tools, then call the runner again. A changed fingerprint allows advancement after the repair without resetting the retry budget. Never reconstruct dates/education, inspect every optional template, or extract a PDF.
6. Idle plus enabled Continue wins over a review count. Native Save and Continue is the fallback only when Simplify is idle and its Continue is unavailable. Same URL does not mean same step; use the observed stepper/section. Upload success is not navigation.
7. Review with authorized submit mode and the approved attachment observed: the runner records submission intent, submits once and looks for a native employer application row matching the requisition. It does not treat the Simplify success panel as submission proof.
8. `applied`: the runner has finished the managed attempt and preserved the owned completed tab for inspection. Read the attempt report; do not submit or finish it again. `already_applied`: read native evidence and finish through the normal protocol without a new submit. `submission_unknown`: inspect/reconcile the same target; never click Submit again. `ready_for_review` is correct only in review mode, never relabel it submitted.

## Pitfalls
- `unknown` and `active` writer states never authorize manual writes. An enabled account button is not permission to let the extension generate credentials.
- Do not parse or scrape resume/PDF text during an application, on any ATS. Approved document upload is still allowed. Candidate-profile maintenance is a separate, explicit task.
- A private `fast-*.lock` means an active runner or a crashed runner needing inspection. Never delete it while an owner might still be active.
- The observer covers known English Workday labels; an unknown locale/control returns a blocker. Inspect it once; record a reusable fix for engineering afterward rather than writing a new adapter in-run.
- These tests use synthetic pages. They do not establish ten-minute live performance or universal Workday support.

## Verification
Report native employer evidence, exact managed attempt ID, wall-clock elapsed time, tool/model overhead where measured, retries and manual/user interventions. Target under ten minutes on the next straightforward application; do not claim that target until measured. Use [the benchmark prompt](../../../docs/jobbot-v1/WORKDAY_NEXT_RUN.md) and [helper map](../../../docs/jobbot-v1/APPLICATION_RUNTIME.md).
