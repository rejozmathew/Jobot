# Jobot: paused implementation and independent-review handoff

**Status: PAUSED at the user's request. This is a work-in-progress checkpoint, not a working Workday release.**

- Date: 2026-09-07.
- Review branch: `review/jobbot-huron-auth-checkpoint`.
- Last published baseline: `e7111128063371423d332822f8389d247dc81845` on `jobbot-v1-windows` (`feat(jobbot): checkpoint native pilot, field telemetry and owned-tab cleanup`). The remote baseline was checked before creating this review branch.
- Scope: preserve the accumulated changes since that baseline and document the failures for a different model to assess. No new implementation, application run, deployment, or broad review was initiated for this handoff.
- No application or task-specific coding/test worker remained running at the pause check. The local dashboard is separate from application execution and was left available.

## 1. Executive assessment

The user wanted an efficient job-filling product: a headed Luna/Low worker that uses configured employer credentials, lets Simplify perform bulk filling, and understands the actual page when the extension or a selector is unavailable.

The accumulated work improves reporting and exposes more capabilities to the worker. **It does not establish a functioning live Workday authentication/application flow.** Both Huron attempts after the baseline failed at the initial application/account stage. No Huron application was submitted. No additional successful application after the baseline was verified.

The latest candidate passed **440 offline tests**, Python compilation, dashboard JavaScript syntax, and Git whitespace checks. The subsequent live attempt still failed before saved credentials were filled. This is the central acceptance gap—not a minor remaining checklist item.

The user explicitly stopped the work because it had become repeated coding/testing/debugging without corresponding product progress. The next reviewer should assess the architecture and execution approach, not simply continue adding tests or aliases and repeat the same pilot.

## 2. What the baseline already established

The baseline contained the managed queue/attempt protocol, dashboard, native subscription worker, timing/problem telemetry, and application-owned tab cleanup. A previous Tebra/Greenhouse application was independently confirmed submitted with Luna/Low. **That success predates this checkpoint; do not repeat that application or present it as validation of these changes.**

The baseline's recorded offline gate was 411 passing tests. Its own live-acceptance notes already identified the new worker's Workday navigation, authentication, upload, and confirmation paths as open gates. The older legacy Workday handler's historical success is not proof of the new `managed_hermes_worker.py` path.

## 3. Actual failures and corrected diagnosis

### Huron attempt 4: internal guard stopped Simplify before a click

Role: **Digital Senior Director — Data & Analytics, Financial Services**, Huron, requisition **JR-0016154**.

- Run: `06589da3-fa01-4177-9dba-c3d9a56f8e1e`; local attempt ID: `4`.
- UTC: `2026-09-07T19:35:52.484672+00:00` to `2026-09-07T19:36:21.711117+00:00`.
- Ledger wall duration: `29.226445` seconds.
- Worker: `gpt-5.6-luna`, Low, `openai-codex` subscription, headed.
- Outcome: `failed`; submission intent: null; owned application tab closed.
- Original final evidence was generic cleanup text. The worker's Simplify action had been rejected by Jobot's internal `browser_writer_busy` guard before the extension click code ran.

An isolated reproduction established that an **unknown** observer state was treated like a busy writer. This did not prove that Workday blocked automation or that Simplify itself was writing. The user reported that manually clicking Simplify worked.

**Incorrect diagnosis to avoid repeating:** a later inspection of the public posting found a `Start Application` control. The assistant prematurely declared its missing recognition to be the confirmed cause. The user pointed out that the relevant screen was actually Workday's Create Account/Sign In screen. A later screenshot and observer check on the explicit application URL showed a visible, enabled **`Create Account & Autofill`** control while Jobot returned unknown/no recognized action.

These are different page stages. The posting-only Start Application change passed focused tests, but did not fix the account-stage issue. The original failed tab had already been closed; the later screenshot is a reopened reproduction, not a capture of the original failure instant.

Failure-display work added visible reasons to Applications, Activity, and attempt details. The original outcome/history was preserved; subsequent explanatory annotations were late observations rather than replacement original evidence.

### Huron attempt 5: screenshot was used, credential helper still failed

- Run: `7791cb11-404f-4908-bcea-722e89899e96`; local attempt ID: `5`.
- UTC: `2026-09-07T21:27:57.297640+00:00` to `2026-09-07T21:28:36.034566+00:00`.
- Ledger wall duration: `38.736926` seconds.
- Actual connected worker/model and effort were verified in the dashboard: Luna/Low, subscription, headed.
- Outcome: `failed`; submission intent: null; owned application tab closed.
- Exact retained final cause:

```text
RuntimeError during credentials: evaluate error: Error: unexpected_auth_fields; owned target absence verified
```

The sanitized operation log showed:

```text
start -> inventory -> click -> click -> screenshot
      -> credentials (RuntimeError) -> inventory -> click
      -> credentials (RuntimeError) -> status
```

The new screenshot operation did execute. However, the credential helper rejected the form before assigning the saved credentials. `AUTH_FIND_AND_FILL` requires exactly one email candidate and one or two visible password inputs. Email discovery still depends on input type/name/id patterns; the operation does not use an LLM-selected email/password/confirmation reference mapping.

**Established:** the helper raised `unexpected_auth_fields` twice, before its fill loop. **Not established:** which actual input count or selector mismatch triggered it. The retained failure evidence does not include those counts. Do not invent a specific Workday DOM explanation without inspecting the real layout.

There is no evidence that Huron rejected the configured password, that an employer account was created, or that an application was submitted. A process exit code of zero only means the worker process completed; it does not override the failed ledger outcome.

## 4. Changes accumulated since the baseline

### Product and worker changes

1. **Local dashboard usability:** opening the loopback dashboard establishes its UI session without asking the user to paste an operator credential. Adds session recovery and a headed/headless selector wired into run settings. This is not a replacement for employer authentication and is not authorization to expose the dashboard publicly.
2. **Workday scope/navigation:** new application-scope helpers allow selected same-employer application routes, optional locale prefixes, and observed anchor navigation while retaining ownership checks. Native auth/navigation buttons are distinguished from final application submission.
3. **Failure visibility:** shared latest-attempt failure reasons feed the queue, Activity, and detailed report. Worker errors retain their cause instead of being erased by successful status reads or generic cleanup messages. Submission-unknown retains priority over earlier pre-submit errors.
4. **Configured-credential operation:** loads `accounts.default.email` and `accounts.default.password` internally through a private `credential_profile_path`; attempts native filling, internal equality checks, and an existing-account/sign-in route. Password values are not tool arguments or model results. This operation is present but failed the live pilot.
5. **Visual fallback:** adds an actual Hermes multimodal screenshot tool response with current control references. Password controls are temporarily hidden for capture without rewriting their values. The worker prompt now permits authorized employer account creation and directs screenshot use on missing/unfamiliar or unproductive actions.
6. **Control discovery and native fallback:** inventory includes native controls and official Simplify shadow-root controls with source metadata and fresh refs. A selected extension ref can be used without matching a fixed autofill label. Initial stable, unrecognized/absent extension UI can permit native work when no active writer exists; unsettled started extension work remains blocking across repeated observations. Exact-label shortcuts still exist and the implementation is not fully semantic end to end.
7. **CDP/interaction corrections:** scalar argument forwarding and async callable invocation; React-compatible credential setters; stale-ref handling; screenshot ref delivery; known event types; protection against using generic extension clicks to delegate account-password creation to Simplify.

### Complete source/test file map

Paths below are relative to the repository root; all were part of the accumulated uncommitted delta at pause.

| File | Change |
|---|---|
| `job_applier/browser_helpers/simplify_observe.js` | Adds posting-stage Start Application shortcut recognition; not the account-stage solution. |
| `job_applier/cdp_client.py` | Forwards scalar arguments and invokes async callables in CDP evaluation. |
| `job_applier/managed_hermes_worker.py` | Auth/navigation scope, configured credentials, masked vision response, extension refs, failure persistence, and worker instructions. |
| `job_applier/managed_identity.py` | Workday and shared application-scope validation helpers. |
| `job_applier/managed_reports.py` | Exposes the resolved failure reason in attempt reports. |
| `job_applier/managed_runtime.py` | Uses application scope and distinguishes stable unfamiliar UI from unsettled writers. |
| `job_applier/managed_ui.py` | Automatic local dashboard session establishment. |
| `job_applier/managed_views.py` | Resolves and displays the latest meaningful attempt failure. |
| `job_applier/simplify_boundary.py` | Adds Start navigation handling and preserves unknown/unsettled writer semantics. |
| `job_applier/static/jobbot.html` | Removes operator-token prompt and adds browser-mode control. |
| `job_applier/static/jobbot.js` | Local reconnection, browser setting, and failure/problem rendering. |
| `tests/jobbot_v1/test_auth_runtime_contract.py` | Runtime/event contracts, real JS credential-state checks, non-mutating masking, async CDP, fresh refs, and repeated-writer regression tests. |
| `tests/jobbot_v1/test_failure_reason_recovery.py` | Status/read success must not erase an unresolved action failure. |
| `tests/jobbot_v1/test_failure_reasons.py` | Failure reason persistence, prioritization, views and report coverage. |
| `tests/jobbot_v1/test_local_dashboard.py` | Direct local UI connection and retained access boundaries. |
| `tests/jobbot_v1/test_semantic_auth_fallback.py` | Initial credential, screenshot, ref discovery and native-fallback tests, several with mocked browser results. |
| `tests/jobbot_v1/test_simplify_start.py` | Posting-stage Start shortcut, navigation and worker routing. |
| `tests/jobbot_v1/test_workday_auth_targeted.py` | Workday scope/auth/navigation and anchor/scalar handling. |

This handoff and current-status pointers in `README.md` and `LIVE_PILOT_CHECKPOINT.md` are documentation additions at pause. Older stage manifests, test maps and evidence are historical snapshots, not refreshed release certifications for this branch.

## 5. Test evidence—and why it was insufficient

These results were read from local JUnit files, not inferred from agent/process exit codes:

| Gate | Passed | Failed | Meaning |
|---|---:|---:|---|
| Failure-reason full suite (`failure-reasons-final.xml`) | 416 | 1 | Separate Workday anchor test remained failing at that point. |
| Posting Start shortcut (`simplify-start-green.xml`) | 60 | 0 | Focused shortcut/navigation coverage only. |
| Initial semantic/auth subset (`semantic-auth-green.xml`) | 70 | 0 | Included mocks that concealed integration defects. |
| First subsequent full suite (`semantic-auth-final.xml`) | 438 | 1 | Inventory JS fixture lacked a newly used DOM method. |
| Final corrected full suite (`semantic-auth-verified.xml`) | 440 | 0 | Offline gate before failed Huron attempt 5; zero errors/skips, two deprecation warnings. |

The final run took 67.30 seconds in pytest's terminal summary. Python compilation, `node --check job_applier/static/jobbot.js`, and `git diff --check` also exited zero. Gemini ran the initial development/final-test delegation; the parent ran additional contract regressions and the final corrected full suite directly. No new test run was performed just to prepare this documentation.

Additional regressions exposed defects after the initial 70-pass subset: unsupported event names, a writer forgotten on a second observation, React state not updated by direct value assignment, screenshot masking that rewrote input values, stale extension refs, missing screenshot refs, account-action guard bypass, and async CDP functions not being invoked. Those were corrected before the 440-pass gate. This does **not** establish that every comparable defect is eliminated.

Several tests manufactured successful browser results instead of exercising the real form/adapter boundary. Even the later real-JavaScript tests used constructed DOM contracts. None represented the actual Huron email/password discovery layout. Consequently, the tests could be green while the first live credential step remained unusable.

For scale, the staged code delta from the baseline contains 11 production files with 601 added/76 removed lines, versus seven new test files containing 1,996 lines. These are Git diff counts, not a claim of coverage or useful progress. The reviewer should explicitly assess whether the test scaffolding is proportionate and whether it tests the right contracts.

## 6. Process challenges and unresolved decisions

- **Wrong-screen diagnosis:** the public-posting label was treated as conclusive evidence for a different login/application screen. The assistant overstated certainty before the screenshot correction.
- **Missing operational fallback:** the worker originally had no screenshot operation, hid password controls, lacked a default-credential bridge, and explicitly prohibited account creation. The presence of an LLM did not make those unavailable actions possible.
- **Fallback still ends at a rigid helper:** after vision was added, the model could see the page but could not direct the credential helper to actual field refs. The latest failure demonstrates this remaining mismatch.
- **Testing displaced product verification:** repeated subset/full-suite cycles, mock-driven false confidence, and callback/interface repairs consumed effort without proving the requested basic account flow.
- **Cleanup/evidence tension:** owned-tab closure works, but closes the exact failed form. A screenshot made later must be described as a reproduction. The current credential error omitted the field counts needed to explain it precisely.
- **Reporting is not functionality:** visible, preserved failure reasons are useful but do not establish that filling works.
- **Still-open Workday coverage:** later wizard navigation, resume/drop-zone selection, resume confirmation, contact-identity consistency, and final submission confirmation have not been demonstrated on this worker. There are remaining specialized assumptions, including the worker's resume input path. Do not claim these steps passed because authentication prevented reaching them.
- **Local portability:** the approved candidate profile and default portal-login email are distinct in the private setup. The instruction is to use configured portal credentials and retain the approved candidate contact facts where the employer allows. That distinction has not been proven through Huron's post-login form.

### Questions for the independent reviewer—not an instruction to implement

1. Is the worker/tool contract capable of letting Luna choose real fields/actions from current DOM and vision evidence, especially for private credential filling, without exposing secret values to the model?
2. Which deterministic adapters are justified, and which assumptions should be removed rather than patched with another label/selector?
3. What is the smallest real-browser contract/probe that would have caught the current failure before another full application attempt?
4. How should an unrecognized UI, an actually active writer, and uncertain completion be represented without false locks or unsafe concurrent writes?
5. What evidence should be retained before closing a failed owned tab, while preserving privacy and unrelated/user tabs?
6. Should this branch be repaired incrementally, simplified, or partially replaced? Identify what to keep/discard and the smallest next acceptance gate. Do not assume the existing architecture must be defended.

## 7. User-approved operating rules to retain

- Routine employer inspection/filling: **Luna or Terra**, with the verified pilot using **Luna / Low through the subscription provider**. No silent switch to Astra/high effort or an API-key fallback.
- Prefer bounded Gemini coding/testing work; avoid broad review loops and token-heavy speculative debugging.
- **Use configured employer email/password for native sign-in or account creation before handing the application form to Simplify.** Both password and confirmation use the configured password. Do not let Simplify generate/submit a different one.
- Existing-account feedback should lead to sign-in with the saved defaults, not password guessing or a reset. Verification barriers require the appropriate user handoff.
- If Simplify is absent or a control is unfamiliar, show the worker the actual page screenshot and current controls, then choose a contextual next action. Screenshot availability alone is not proof that fallback works.
- Headed/headless is a setting; supervised pilots should be visible as requested.
- Preserve legacy profiles, credentials, browser data and real history. No test databases may overwrite real runtime databases.
- No real application run while editing shared code/skills. No duplicate Tebra application. No Ubuntu/Unraid rollout or schedule changes.
- **Current instruction supersedes earlier run authorizations: pause and hand off.** Do not restart Huron or make further code changes without a new direction after review.

## 8. Local-only evidence and publication boundaries

The following are intentionally excluded from GitHub under ignored `artifacts/jobbot-v1-private/`:

- Original/latest worker logs, the actual login-screen screenshot `huron-actual-login-screen.png`, diagnostic model output, test JUnit XMLs, and delegation receipts.
- `windows-review-pilot/managed.db`, its historical attempts/events, local app configuration, transport credentials, approved profile/resume copies and worker spool/receipts.
- Private handoffs such as `FAILURE_REASON_HANDOFF.md` and `SEMANTIC_AUTH_HANDOFF.md`. They are historical records and may describe a now-superseded plan; this repository handoff governs the pause.

The source profile, default employer credentials and persistent browser profile remain in their existing device-local locations. No passwords, tokens, verification codes, cookies, raw model reasoning, private mailbox contents, resumes or databases are to be staged. Active-profile skill/policy changes do not travel automatically through this repository; the important operative rules are captured above instead of exporting the entire Hermes profile.

Local runtime is not portable simply by checking out the branch. In particular, configure a private credential source and a NEW synthetic database before any offline development on another device. Do not initialize over the existing named pilot or run private setup scripts blindly: some carry historical Tebra initialization paths.

## 9. Reviewer entry point

Read this document first, then inspect the diff from the published baseline:

```text
git diff e7111128063371423d332822f8389d247dc81845...HEAD -- job_applier tests/jobbot_v1 docs/jobbot-v1
```

For static orientation, start with `AUTH_FIND_AND_FILL`, `ApplicationTool.operate`, `ApplicationTool.handle`, `run_request`, and `RuntimeServices.browser_observe`; then inspect the new tests against their actual dependencies. Read older acceptance documents only with their original scope/date in mind.

**Requested reviewer deliverable:** an independent assessment of why green tests have not produced a usable live flow, a recommendation about what to retain or replace, and a short evidence-based next-step decision for the user. The checkpoint is for that decision—not permission for another autonomous implementation/test/application cycle.
