---
name: workday-simplify
description: Execute Workday with local sessions and Simplify.
version: 0.3.6
author: Rejo Z Mathew (rejozmathew), Hermes Agent
license: MIT
platforms: [windows]
---

# Workday with Simplify

Read the canonical [job-apply](../job-apply/SKILL.md). Start the application using
its local `start` operation. Startup verifies the configured managed instance,
history, assigned headed browser, profile, fresh target and Simplify surface.
No API token, expiring lease, old target binding or additional worker is needed.

Use native `jobbot(operation="fast_forward", parameters={"seconds":60})`.
The portable equivalent resolves everything from the returned session:

```text
.venv/Scripts/python.exe -m job_applier.workday_fast session <session-id> --seconds 60
```

Optional `--config <absolute-json>` and `--driver-id <conversation-id>` follow the
shared skill. The ordinary conversation remains the application executor. The
runner contains no model and retains one CDP connection during its bounded call.

1. Confirm role, identity, approved asset and submission authorization once.
2. Call the runner for routine observe/act/wait/advance. It checks controls and
   writer state, lets Simplify fill, and prefers enabled Continue after settling.
3. `waiting`: call again. Persisted counters protect against repeated autofill;
   do not reset checkpoints to evade limits. Heartbeat is telemetry, not expiry.
4. The runner handles Workday authentication: read the existing site account,
   reuse its saved credential (or the configured retained default for a new site),
   choose Create Account or Sign In, accept the uniquely observed account
   privacy/terms checkbox, fill privately, and recheck the enabled submit control.
   It records creation pending before clicking, saves employer-confirmed creation,
   and confirms sign-in only when the application form actually opens. It then
   returns to Simplify. Later calls sign in for a confirmed/created account.
   For pending creation, including an earlier attempt, use retained credentials
   for a bounded sign-in check. Workday may return to Sign In without a creation
   confirmation. Keep the account pending until authentication is verified;
   do not attempt creation again.
   A proven undispatched click retains its reason and becomes
   `creation_not_executed`, permitting at most two undispatched attempts per
   auth mode in this session. A possibly dispatched action is not replayed.
   The screen account includes its state, timestamp and last attempt ID.
   Counters prevent repeating an uncertain create/sign-in action. Optional
   marketing consent is not selected. No generated password is silently lost.
   `authentication_required` now means a specific exception: inspect its reason
   and current controls, then use scoped browser/credentials or the configured
   mailbox for a supported recovery. An unknown checkbox, verification challenge,
   rejected credential, missing saved reference or unfamiliar auth page returns
   to the executor without closing the application. Never reset counters or
   create again while the previous account outcome is unknown.
   If the employer first offers Apple/Google/LinkedIn and **Sign in with email**,
   the runner selects the unique observed email option, then uses the native
   account form. It handles the chooser returning once after creation. For a
   mapped chooser fallback, omit `account_mode` and `credentials`: this control
   opens the password form and does not submit credentials.
   A same-site `/login?redirect=...` is supported only when the decoded redirect
   leads back to this exact requisition. Native clicks use browser pointer input;
   a dispatched click is not employer acceptance. Report account creation/sign-in
   as confirmed only after the employer supplies the corresponding evidence.
   If the user completed account creation manually, continue with sign-in and
   reconcile the account evidence; do not start another creation attempt.
   Follow the returned `recovery` handoff: inspect `browser screenshot` using
   the current executor's image capability, pair with `browser snapshot` for
   observed selectors, and use supported native controls or settled Simplify.
   Report possible changed/unsupported controls distinctly from rejected
   credentials or a verification challenge. After recovery, call the runner again;
   record the mismatch for a later helper update, never an in-run code patch.
   The handoff now includes ONE combined `screen` inventory. Map that logical
   screen once and pass the mapping directly to the existing runner:

   ```json
   {"seconds":60,"recovery":{"screen_key":"<observed>","account_mode":"sign_in","credentials":{"email_ref":"<observed wd ref>","password_ref":"<observed wd ref>"},"fields":[],"action":{"source":"native","ref":"<observed sign-in ref>"}}}
   ```

   This is `jobbot fast_forward` parameters, or the portable session `call`
   operation `fast_forward`. Omit unused credentials/account_mode/fields. Select
   all necessary native answers/checkboxes together in `fields:[{ref,value}]`;
   values are approved facts, never passwords or OTPs. Native SELECT controls
   use observed option values. The private filler resolves the mapped credential
   refs directly; the failed semantic matcher is not applied again. Unique
   semantic references refresh locally across ordinary rerenders. It persists
   action uncertainty before clicking and updates account/helper state on actual
   authentication. A lost click response does not authorize replay.

   When Simplify is enabled, consider its current controls from authentication
   onward. Use native sign-in with retained credentials unless Simplify's use of
   those credentials is established. A mapped Simplify sign-in additionally needs
   non-secret `credential_evidence`; Simplify login is distinct from employer login.
   Inspect the installed extension's settings once: retain supervised page-by-page
   operation and never enable continuous execution that can submit outside the
   existing submission boundary. Do not turn settings inspection into a project.

   `inspection_required` returns promptly for a settled recognition miss or an
   explicit writer uncertainty. The latter allows observation only until settled.
   Do not finish merely because a helper missed a field. A second screen decision
   needs new required questions, native validation, verification or unresolved
   ambiguity; values, spinners, scrolling and ordinary rerenders are not new
   reasoning problems. Return routine pages to Simplify without LLM interpretation.
   Keep going in the same application after the first successful auth/autofill.
5. `blocked`: handle only the actual required blocker with the shared session's
   `browser` operation and approved facts. One initial autofill and one retry per
   step remain the limit. Do not audit every optional field or reconstruct history.
   Use the shared `browser select`/`fill`/`check` API with the observed ref; the
   runtime resolves the control, including an embedded document, without a model
   choosing another dropdown handler. For genuinely missing required facts,
   follow job-apply's `request_answers` / optional messaging / `park_questions`
   procedure. After a saved-answer retry, use `apply_answers` with fresh refs and
   return routine advancement to this Workday runner. A control failure with a
   known answer remains a technical recovery, not a question for the user.
   Enabled `Autofill N Skills` is a separate input action; a cosmetic spinner
   does not defeat it. Counts are observed and bounded per page. Salary/privacy
   preferences use the shared profile policy; the runner applies them before
   continuing. Use shared `browser select` for native or ARIA dropdown recovery.
6. A review count does not defeat enabled Continue after quiescence. Same URL does
   not imply same step; the runner observes Workday's actual section/stepper.
   Keep populated source answers such as LinkedIn. In `needs_review`, prefer
   native Continue and let actual employer validation identify missing answers.
   Question/answer history is captured during filling and advancement.
7. At authorized Review, submit immediately through the shared boundary. Do not
   search for or verify the resume again, even if attachment evidence is absent
   from the runner or upload ledger. The runner arms confirmation capture,
   records intent and submits once.
   It captures native and Simplify confirmation with the actual source and applies
   the profile's accepted sources. Valid post-submit routes can be inspected even
   after Workday's form step disappears. Follow the shared bounded inspection and
   reconciliation procedure when evidence remains uncertain. Same-site
   `jobTasks/completed/application` is an accepted read-only completion route.
   Fresh Simplify "Application Submitted!" is sufficient when its source is
   authorized; finish without another review or email wait.
8. `applied`: read the report; do not submit or finish again. `already_applied`
   requires exact native evidence and no new submit. `submission_unknown` allows
   observation/reconciliation only. `ready_for_review` applies only in review mode.

No in-run PDF extraction, resume search, career/education reconstruction or shared
code/skill changes. Never compete with active or unknown writers. Generic browser
focus and old targets do not belong to this session. An unavailable CAPTCHA/MFA,
rejected credentials or unknown required fact is a specific blocker.

Optional diagnostic:

```text
.venv/Scripts/python.exe -m job_applier.application_runtime doctor --url <job-url>
```

Doctor alone is not live readiness. The legacy `workday_fast advance` with explicit
attempt/fence/target remains for existing HTTP integrations; it is superseded for
normal local execution. Report exact employer confirmation and honest elapsed
wall time; under ten minutes is a target, not an inferred result.
