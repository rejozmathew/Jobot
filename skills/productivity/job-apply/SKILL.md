---
name: job-apply
description: Run managed applications with evidence and continuity.
version: 0.3.0
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

The selected harness executes applications using its available browser, shell, file and mailbox capabilities. Shared procedures and helper code live in this repository, not in a personal harness profile. Auto Job Applier supplies the queue, candidate facts, documents, account history and tracking through `jobbot`. This repository is the canonical version of this skill; the loaded content and its references govern this session, including when an older personal skill has the same name. Do not invoke the legacy `run_applier.py apply` engine.

## When to Use
- A user authorizes an application batch and the app provides a reserved run ID.
- Resume an explicitly checkpointed managed run after context/session changes.
- Not for engineering sessions, unsupported runtime combinations, or unsolicited application runs.

## Prerequisites
- The app instance, explicit configuration, selected identity and browser profile must agree with the worker.
- With Hermes, use the installed hooks and native `jobbot` tool when available. Another harness uses the same authenticated managed protocol via its shell and reads these repository files directly; see [runtime ownership and transport](../../../docs/jobbot-v1/APPLICATION_RUNTIME.md). The requested provider/model must match observed runtime metadata; unavailable means unavailable, not another provider or credential route.
- Inspect selected profile facts and immutable attempt context. Resolve credentials through protected references; do not put credentials, verification codes, mailbox bodies or raw reasoning into ordinary logs.
- Use the approved browser and exact owned target. A bare URL or successful command is not a managed application.

## How to Run
`jobbot accept`, `jobbot next`, `jobbot checkpoint`, and `jobbot finish` below are operations on the native `jobbot` tool, not invented shell subcommands. For example, call `jobbot` with `operation="accept"` and `parameters={"run_id":"<reserved-run>"}`, then `operation="next"` to claim one job.

`next` includes the application context. `context` takes empty parameters; ownership identifiers are supplied by the integration. `bind_target` takes exactly `{"target_id":"<observed-CDP-target>","url":"<claimed-job-url>"}`. Do not add attempt, owner, fence or run fields to these calls.

The fallback transport is the same app protocol through `terminal(command="<python> run_applier.py managed call --config <explicit-config> --operation <operation> --payload <payload>", workdir="<app-repo>")`. Use the configured credential name with `--token-env`; it resolves from the launcher environment or an explicit private-file reference, never from a value in command arguments. For an ordinary Hermes thread without native `jobbot`, read [internal service authentication](references/internal-service-auth.md) and verify the CLI health check before claiming. Do not launch another worker conversation just to obtain credentials.

## Procedure
1. Accept the reserved run; request `jobbot next`. Do no form work without the returned attempt ID, owner and fence. If there is no work or pickup is unavailable, stop honestly.
2. Retain run continuity and reusable helper references. Read selected profile facts, the chosen document reference and account namespace plus identity before any login. See [accounts and mail](references/accounts-and-mail.md).
3. Confirm the live official role is still eligible under current approved policy; dynamic exclusions, location, level and explicit sponsorship restrictions matter. Existing submission evidence and uncertain prior attempts must not be bypassed.
4. Open a new application tab in the existing visible Simplify-enabled browser at the supplied CDP endpoint. Capture its actual CDP target ID and call `jobbot bind_target` with `target_id` and the claimed job URL. Use that exact target for browser tools or terminal/CDP helpers; never let a tool silently choose another existing tab. Confirm the visible page and call `jobbot browser_observe` with `target_id` and `cdp_url`. Resolve sign-in/create-account and ordinary email verification autonomously as described below. Then use Simplify as the primary bulk filler. On each new page rediscover supported extension controls. Use [bounded flexible recovery](references/simplify.md), not a rigid screen sequence or repeated full-form reruns.
5. Let Simplify finish before touching a form. Prefer enabled Continue over nonblocking Need review warnings; do not audit every optional field/template. Confirm identity/contact and the approved attachment, and resolve only actual required blockers using selected profile facts. Unknown or inverted material screening questions require interpretation or clarification, not an invented factual answer. On Workday use the repository [workday-simplify skill](../workday-simplify/SKILL.md) and its bounded runner, not one-off CDP polling scripts.
6. Prefer extension Continue Application over an ATS advancement button when available. Once the extension is observably quiescent, use approved deterministic helpers or native tools for residuals only. Preserve working filled sections.
   Before a residual repair, call native `jobbot` operation `milestone` with `event_type="field_context"` and payload containing stable semantic `page`, `field`, and `category` identifiers (letters, digits, `.`, `_`, `:`, `/`, `-`; at most 120 characters each). Never put field values or raw arguments in these identifiers. This context is captured at action start and charged the automatically measured tool duration across tool names. Emit a new context for a genuinely different field/page; `field_verified` or `navigation_verified` clears it, as does an empty `field_context` payload. A milestone alone is not proof of progress. When context is absent, the app reports `coarse_only`: attempt/no-progress limits still apply, but no field-specific precision is claimed. Honor budget blocks; do not rename the same problem to evade them.
7. Obey app-owned controls before side effects. A pause/stop request is not acknowledged until owned writers and targets are quiescent. Expired or unknown ownership requires reconciliation; stale callbacks never attach to a newer attempt.
8. Verify the approved resume from `context.documents.assets` is attached. If Simplify attached that exact approved file and the attachment UI verifies it, retain it; otherwise upload the local approved asset to the actual observed file input using native tools/CDP. Do not assume `#resume`. Continue through all pages. In authorized submit mode call `jobbot submission_intent` with employer-page evidence, submit automatically, and observe the actual employer confirmation. Do not stop for human review. A validation rejection is not a submission; uncertain post-click state is submission_unknown.
9. Record accurate outcome/evidence, close only completed owned targets, and `jobbot finish` with truthful quiescence. Keep an authentication blocker visible for the user if needed. Request the next reserved job in the same conversation; do not make new conversations mandatory per job.
10. Before a context handoff, `jobbot checkpoint` with a short factual summary, next step and reusable references—no private mail contents or raw reasoning. A new session uses explicit resume after ownership reconciliation.

## Shared fast-path policy (all ATS platforms)

- Simplify is the primary bulk writer. Never compete with active/unknown writer state.
- No in-run resume/PDF text extraction, filesystem hunts for another resume, or reconstruction of experience/education. Approved document upload and pre-run asset selection are still allowed; profile maintenance is a separate explicit task.
- No redundant full final audit: reuse verified profile/document context and resolve only material blockers.
- Forward progress beats clearing every review warning. Try enabled Continue after observed quiescence, then repair only a demonstrated blocker. Keep retries bounded and preserve working sections.
- Use shipped helper functions with structured arguments, not ad hoc nested Python/JavaScript strings. Screenshots and detailed field inspection are exception tools, not every polling tick.
- New writes go through the configured managed service/database. Legacy history is read-only duplicate suppression; never guess schema columns or dual-write outcomes.

## Pitfalls
- Healthy heartbeat is not verified progress. Use real page/field/validation milestones; avoid narrative progress claims.
- Ordinary email verification is part of execution, not CAPTCHA or a human handoff. A genuine CAPTCHA/MFA blocker unavailable to the tools becomes a recorded blocked job; continue the batch. Do not repeatedly create accounts or reset passwords.
- An account created successfully stays confirmed even if a later form page fails.
- Do not broadly restart browsers. Only operate on the verified owned process/target; absence of controls is a reportable recovery state.
- Input values can look populated without being committed. See [Greenhouse](references/greenhouse.md), [Workday](references/workday.md), and [CDP recipes](references/cdp-recipes.md).

## Verification
Report actual confirmation or review/blocked state, attempt/run IDs, real elapsed time, known phase/tool/model losses, and reusable fixes. Read the app's attempt/events views (or matching authenticated CLI operations). Missing timing detail remains unknown, not invented. Fixture success is not live Workday/Simplify proof. Do not start applications while shared implementation or skills are being edited.

## Private authentication and Gmail

- Read `jobbot account_strategy` for the context's portal namespace. Reuse a confirmed account. Otherwise create an account using the configured credential. Record confirmed account creation immediately with `record_account_event`; credentials remain in the private profile and events store only its reference.
- Use the actual browser capability exposed by this Hermes installation. With `browser_exec`, read its returned/API documentation and use its native page inspection, evaluation, navigation and upload methods; use one named browser session for the run. Other Hermes versions expose `browser_snapshot`/`browser_console`. Inspect the actual authentication inputs using that native capability or the exact-target CDP helper. Choose the email/username, password and optional confirmation controls yourself. Pass their **observed unique CSS selectors** as `email_ref`, `password_ref`, optional `confirmation_ref`, plus the owned `target_id`, to `jobbot credentials`. These are references to inspected controls, not guesses. The private helper supplies the configured values and returns field counts, committed-state verification, inferred account mode and a non-secret error category. Inspect and correct stale/ambiguous refs; never dump credential files or password values. Click the observed native authentication action after committed values are verified.
- Use the application contact email from the approved attempt context consistently with portal credentials, Simplify residuals and the verification mailbox. Correct a differing Simplify email before continuing. Do not silently change factual profile fields.
- The run context supplies an installed Hermes `gmail_script` and `mailbox_token_path`. Use the existing Gmail capability via `terminal`:
  `<python> -m job_applier.hermes_gmail --script <gmail_script> --token-file <mailbox_token_path> gmail search <query> --max 5`, then the same prefix followed by `gmail get <message_id>`.
  Set the terminal working directory to the supplied repository. Search narrowly for the current portal, recipient, purpose and request time. Use the actual verification link/code privately in the browser; do not include it or message bodies in milestones, ordinary logs or the final response. Password resets require separate explicit user authorization. Never send unrelated mail.
- If a recorded generated password was used successfully, preserve it in the existing protected credential store before proceeding; do not record it in JobBot event text.

## Execution and tracking contract

- You own application execution only. Read existing helpers and procedural knowledge as useful. Do not edit shared Python, write application adapters, modify the canonical skill, or delegate the application. Record observations with `jobbot observe`; Codex decides changes after the run.
- `jobbot` takes `operation` and a `parameters` object. Milestones use `event_type`, `observed_at` (UTC ISO timestamp), and a concise non-secret `payload`. Use `phase_changed`, `navigation_verified`, `field_verified`, `checkpoint` and `outcome` only for real observations. Call `browser_observe` after navigation and after Simplify settles to refresh actual writer state. Do not compete with active Simplify; observe until it finishes or a concrete blocker is established.
- Before any submit click, `submission_intent` takes `evidence`. Upload reporting uses `asset_id`, `status` (`upload_attempted` or `upload_confirmed`) and `evidence`. Account events use `namespace`, `state`, optional `credential_ref`, and `evidence`; inspect the context for its exact account namespace/state conventions.
- On failure retain the exact headed target. Record the failed operation, URL, relevant visible controls/refs and non-secret state, attempted next action and exact error. Use `target_state` with `state="preserved"` and evidence. On success close only the owned completed target and record `state="closed"`. Refresh browser observation before closing/preserving to establish quiescence. `finish` takes `outcome`, `evidence`, `quiescent=true`. Request `next` after finishing; do not let one blocked job stall the queue.
- The launcher records executor, actual model/effort, canonical skill hash, headed mode, run ID and attempt ID. Preserve these identifiers in the final result. A worker process exit is not evidence of application submission.
