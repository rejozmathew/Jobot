# Runtime simplification implementation log

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
