---
name: workday-simplify
description: Execute Workday with local sessions and Simplify.
version: 0.3.17
author: Rejo Z Mathew (rejozmathew), Hermes Agent
license: MIT
platforms: [linux, windows]
---

# Workday with Simplify

On Linux use `.venv/bin/python` wherever an example shows the Windows virtualenv
interpreter. Use the explicitly selected VM runtime config and existing mailbox.

Read the canonical [job-apply](../job-apply/SKILL.md). Start the application using
its local `start` operation before reading this ATS detail, allowing browser
preparation to overlap this reading. Startup verifies the configured managed instance,
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

The runner records application stages and meaningful tasks in the shared
timeline. Recruiting-source repair attaches its full question to native actions
and completes only after the selected value commits. Ordinary step transitions
close the prior step; technical retries remain in Debug details. Use the canonical
`progress` operation to supply executor intent when a manual recovery needs it.
Normal observations and answer capture also enrich missing job company/title
from scoped posting metadata; existing labels and historical outcomes remain.

1. Confirm role, identity, approved asset and submission authorization once.
2. Call the runner for routine observe/act/wait/advance. It checks controls and
   writer state. After native application entry/authentication, run available
   **Autofill This Page first on each form step**, including Review, before
   Continue, skills prompts or manual field repair. Wait for settlement, then
   prefer enabled **Simplify Continue Application**, even with needs_review.
   Use helpers for residuals and executor field/screenshot recovery afterward.
   The page checkpoint and shared
   browser receipt prevent an Autofill loop across calls and changing values.
   Return every new page to the runner, including Voluntary Disclosures and
   Self Identify, after finishing a manual exception. The shared browser also
   routes a first manual field-repair request on these Workday pages through
   available Autofill first; its result identifies the field action not performed.
   This also applies to mapped non-authentication recovery: refresh the screen
   and rebind any remaining approved recovery fields after bulk filling.
   On a landing page/chooser it prefers native Apply Manually, then other direct
   Apply actions, over chat or the extension's start action. Follow an employer
   landing page's direct application link when it leads into Workday.
3. `waiting`: call again. A helper time slice ending is normal. Persisted evidence
   prevents repeating unchanged actions; newly observed controls or changed form
   evidence can support another recovery. Heartbeat is telemetry, not expiry.
   An observed Workday "Something went wrong" page that explicitly requests a
   refresh triggers one automatic reload before submission. It replaces the old
   document even when Simplify's state is unknown, then waits for fresh page
   controls. A still-initializing page returns waiting instead of an immediate
   unrecognized-screen failure. Once recovered, continue without another refresh
   or restart for the old error. Only a currently observed remaining failure
   supports further recovery; follow job-apply's shared reload guidance.
   Inspect other page failures and choose reload/restart yourself when supported
   by the evidence; no exact error matcher limits executor recovery. A real new
   document resets page fill receipts; ordinary rerenders still do not.
4. The runner handles Workday authentication: read the existing site account,
   reuse its saved credential (or the configured retained default for a new site),
   choose Create Account or Sign In, accept the uniquely observed account
   privacy/terms checkbox, fill privately, and recheck the enabled submit control.
   It records creation pending before clicking, saves employer-confirmed creation,
   and confirms sign-in only when the application form actually opens. It then
   returns to Simplify. Later calls sign in for a confirmed/created account.
   Workday account creation and sign-in use the native private credential filler
   and native controls. Do not use Simplify's **Sign In & Autofill**, **Sign In**
   or account autofill on those pages: it can substitute its generated password.
   A saved `credential_ref` is only a lookup key, not evidence of Simplify's
   password. After creation, let the login page load and call the runner again;
   it fills the retained email/password and clicks native Sign In before resuming
   Simplify on the application form.
   Native activation rechecks those values after pointer hover and restores the
   retained values if another filler replaced them. The returned `credential_check`
   reports match/refill booleans without exposing passwords. These describe the
   check immediately before dispatch; employer acceptance is separate evidence.
   For pending creation, including an earlier attempt, use retained credentials
   for a bounded sign-in check. Workday may return to Sign In without a creation
   confirmation. Keep the account pending until authentication is verified;
   do not infer that a generic invalid-password message means no account exists.
   Explicit employer feedback that the account does not exist or creation was
   rejected resolves the pending outcome and permits corrected creation. The
   helper records this evidence while preserving the earlier creation intent.
   A proven undispatched click retains its reason and becomes
   `creation_not_executed`, permitting recovery of the observed control. Prior
   undispatched clicks do not prohibit a different valid recovery. A possibly
   dispatched creation action is not replayed.
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
   A login on the owned career portal is supported; when it has a job redirect,
   that redirect must identify this requisition. Locations, titles and application
   child routes are presentation, not separate job identities. Native clicks use browser pointer input;
   a dispatched click is not employer acceptance. Report account creation/sign-in
   as confirmed only after the employer supplies the corresponding evidence.
   If the user completed account creation manually, continue with sign-in and
   reconcile the account evidence; do not start another creation attempt.
   Follow the returned `recovery` handoff: inspect `browser screenshot` using
   the current executor's image capability, pair with `browser snapshot` for
   observed selectors, and use the native authentication controls.
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

   Resume Simplify after native authentication opens the application form.
   `workday_native_authentication_required` directs the executor back to
   `fast_forward` or mapped native credentials/sign-in on this same session;
   it is not an application blocker. Simplify's Stop/Cancel remains available
   to settle an accidentally started extension account step before native work.
   Inspect the installed extension's settings once: retain supervised page-by-page
   operation and never enable continuous execution that can submit outside the
   existing submission boundary. Do not turn settings inspection into a project.

   `inspection_required` returns promptly for a settled recognition miss or an
   explicit writer uncertainty. Reobserve or use the shared observed Simplify
   Stop/Cancel recovery to establish settlement. Do not finish merely because a
   helper missed a field. A different control or materially changed mapped answer
   can be handled on the same screen; only the same possibly executed decision
   remains protected from replay. Return routine pages to Simplify without LLM interpretation.
   Keep going in the same application after the first successful auth/autofill.
5. `blocked`: handle only the actual required blocker with the shared session's
   `browser` operation and approved facts. Routine Autofill is once per page;
   recover remaining questions with the executor instead of repeating the fill.
   This is a handoff to your reasoning, not permission to end the application.
   Inspect the actual controls/options and try a different supported interaction.
   A helper timeout or retry limit does not exhaust executor recovery.
   `complete_required_answers` supplies full questions and
   `screen.answer_context`. Follow job-apply's shared required-answer sequence
   for approved facts/defaults, saved answers, executor recovery and last-resort
   human input. Workday's inventory retains the full field question even when
   its control only displays Select One; use that question when choosing.
   Do not audit every optional field or reconstruct history.
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
   Only after advancement cannot proceed, for an empty How Did You Hear About Us
   field after Simplify, the runner uses
   the Workday source prompt routine. It preserves a populated answer, follows
   nested categories/radio leaves, scrolls only the associated virtualized menu,
   retries stale/uncommitted clicks and verifies a committed field value.
   Other/company website/LinkedIn/search engines are preferences, not a fixed
   allowlist: the user permits another offered source when those are absent.
   `source_recovery.options` contains current labels and whether each opens a
   child menu; `path` shows attempted selections. Choose another offered label
   yourself and call `fast_forward` with
   `recovery:{screen_key:"<screen.screen_key>",source_choice:"<exact offered label>"}`.
   The runner reacquires live controls and follows the selected category. If the
   menu is unrecognized, inspect the owned snapshot/screenshot and use scoped
   browser controls to recover it, then resume. Do not ask the user to pick a
   source they already authorized you to choose, or finish because the helper
   could not select it. Never select a global option from another field's menu.
6. After settlement, a review count does not defeat enabled Simplify Continue.
   A selected chip counts as a value even when its search input is empty or its
   menu is open. Preserve that value; do not substitute a preferred source.
   Same URL does
   not imply same step; the runner observes Workday's actual section/stepper.
   Keep populated source answers such as LinkedIn. In `needs_review`, prefer
   native Continue and let actual employer validation identify missing answers.
   Question/answer history is captured during filling and advancement.
7. At authorized Review, submit immediately through the shared boundary. Do not
   search for or verify the resume again, even if attachment evidence is absent
   from the runner or upload ledger. The runner arms confirmation capture,
   records intent and submits at most once per explicit advance call.
   It captures native and Simplify confirmation with the actual source and applies
   the profile's accepted sources. Valid post-submit routes can be inspected even
   after Workday's form step disappears. Follow the shared inspection and
   current-form continuation procedure when evidence remains uncertain. Same-site
   `jobTasks/completed/application` is an accepted read-only completion route.
   Fresh Simplify "Application Submitted!" is sufficient when its source is
   authorized; finish without another review or email wait.
8. `applied`: read the report; do not submit or finish again. `already_applied`
   requires exact native evidence and no new submit. After `submission_unknown`,
   inspect confirmation and the current page. Continue actual unfinished fields,
   verification or browser recovery; another advance follows current controls.
   Click history does not restrict the attempt to observation. A new user application request
   starts a fresh attempt under the shared job-apply retry policy unless success
   is recorded. `ready_for_review` applies only in review mode.

No in-run PDF extraction, resume search, career/education reconstruction or shared
code/skill changes. Never compete with active writers; recover unknown state
through observation, the observed extension stop control, or explicit broken-page
reload/restart cancellation under the shared skill. Generic browser
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
