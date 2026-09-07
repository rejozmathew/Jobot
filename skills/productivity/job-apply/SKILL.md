---
name: job-apply
description: Run managed applications with evidence and continuity.
version: 0.1.0
author: Rejo Z Mathew (rejozmathew), Hermes Agent
human_first: true
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jobs, managed-worker, simplify]
    related_skills: [job-posting-harvest]
---

# Managed Job Apply

Hermes pulls one reserved job at a time through a fixed batch. Auto Job Applier owns queue, history, accounts, timing and app-owned controls. This staged version replaces conflicting execution recipes only after controlled activation; the original personal skills remain preserved.

## When to Use
- A user authorizes an application batch and the app provides a reserved run ID.
- Resume an explicitly checkpointed managed run after context/session changes.
- Not for engineering sessions, unsupported runtime combinations, or unsolicited application runs.

## Prerequisites
- The app instance, explicit configuration, selected identity and browser profile must agree with the worker.
- Installed Hermes hooks and native `jobbot` tool must be available. The requested provider/model must match observed runtime metadata; unavailable means unavailable, not another provider or credential route.
- Inspect selected profile facts and immutable attempt context. Resolve credentials through protected references; do not put credentials, verification codes, mailbox bodies or raw reasoning into ordinary logs.
- Use the approved browser and exact owned target. A bare URL or successful command is not a managed application.

## How to Run
`jobbot accept`, `jobbot next`, `jobbot checkpoint`, and `jobbot finish` below are operations on the native `jobbot` tool, not invented shell subcommands. For example, call `jobbot` with `operation="accept"` and `parameters={"run_id":"<reserved-run>"}`, then `operation="next"` to claim one job.

The fallback transport is the same app protocol through `terminal(command="<python> run_applier.py managed call --config <explicit-config> --operation <operation> --payload <payload>", workdir="<app-repo>")`. Use the configured credential environment reference with `--token-env`; never place its value in command arguments.

## Procedure
1. Accept the reserved run; request `jobbot next`. Do no form work without the returned attempt ID, owner and fence. If there is no work or pickup is unavailable, stop honestly.
2. Retain run continuity and reusable helper references. Read selected profile facts, the chosen document reference and account namespace plus identity before any login. See [accounts and mail](references/accounts-and-mail.md).
3. Confirm the live official role is still eligible under current approved policy; dynamic exclusions, location, level and explicit sponsorship restrictions matter. Existing submission evidence and uncertain prior attempts must not be bypassed.
4. On Workday, prefer native **Autofill with Resume**, then the Simplify preferred path. On each new page rediscover supported extension controls. Use [bounded flexible recovery](references/simplify.md), not a rigid screen sequence or repeated full-form reruns.
5. Inspect Need review, concrete validation errors and material fields while filling: identity/contact, correct document, location, authorization/sponsorship and required screening. Answers come from selected profile facts. Unknown or inverted questions require interpretation or clarification, not a default factual answer.
6. Prefer extension Continue Application over an ATS advancement button when available. Once the extension is observably quiescent, use approved deterministic helpers or native tools for residuals only. Preserve working filled sections.
7. Obey app-owned controls before side effects. A pause/stop request is not acknowledged until owned writers and targets are quiescent. Expired or unknown ownership requires reconciliation; stale callbacks never attach to a newer attempt.
8. At final submission, honor the app's review/submit mode and obtain submission intent before the irreversible action. In authorized submit mode, submit when ready: no redundant full final audit. Then check actual evidence once. A validation rejection is not a submission; uncertain post-click state is submission_unknown.
9. Record accurate outcome/evidence, close only completed owned targets, and `jobbot finish` with truthful quiescence. Keep an authentication blocker visible for the user if needed. Request the next reserved job in the same conversation; do not make new conversations mandatory per job.
10. Before a context handoff, `jobbot checkpoint` with a short factual summary, next step and reusable references—no private mail contents or raw reasoning. A new session uses explicit resume after ownership reconciliation.

## Pitfalls
- Healthy heartbeat is not verified progress. Use real page/field/validation milestones; avoid narrative progress claims.
- Auth gets one verified attempt or the configured short budget (approximately sixty seconds), then a precise handoff. Do not repeatedly create accounts or reset passwords.
- An account created successfully stays confirmed even if a later form page fails.
- Do not broadly restart browsers. Only operate on the verified owned process/target; absence of controls is a reportable recovery state.
- Input values can look populated without being committed. See [Greenhouse](references/greenhouse.md), [Workday](references/workday.md), and [CDP recipes](references/cdp-recipes.md).

## Verification
Report actual confirmation or review/blocked state, attempt/run IDs, real elapsed time, known phase/tool/model losses, and reusable fixes. Read the app's attempt/events views (or matching authenticated CLI operations). Missing timing detail remains unknown, not invented. Fixture success is not live Workday/Simplify proof. Do not start applications while shared implementation or skills are being edited.
