# Stage 2 evidence — verified implementation, live gates remain

## Implemented scope
Native standalone Hermes plugin and metadata-only tool/API observers; durable bounded delivery outbox; fenced session/attempt attribution; exact-target CDP binding; observable Simplify discovery/autofill/continuation; staged canonical application/discovery skills and deprecated legacy trigger; intake-only harvesting handoff. Existing FastAPI/SQLite/CLI remain the owners. No Hermes core or active application/discovery skill was changed.

## Real checks
- Latest Stage 1 + Stage 2 suite, excluding the explicitly unfinished Stage 3 preparation test: **281 passed**, two known dependency/deprecation warnings.
- Command: `JOB_APPLIER_DB_PATH=<ignored-synthetic-db> BROWSER_USE_CDP_URL=http://127.0.0.1:1 .venv/Scripts/python.exe -m pytest tests -q --tb=short --ignore=tests/jobbot_v1/test_settings_views.py`.
- `.venv/Scripts/python.exe -m compileall -q job_applier integrations skills` and `git diff --check` passed.
- Real native command, with an isolated ignored `HERMES_HOME`: `hermes plugins doctor <repo>/integrations/hermes_jobbot --ci` passed: one tool and five hooks.
- Doctor first caught unavailable-checkout import and unsupported-hook issues that unit fake contexts did not catch. Fixed by explicit configured-repository binding, unavailable bootstrapping without CWD package discovery, and only installed hook names. Native loading exposed the settings-schema shape; the manifest now uses the actual key-map schema.
- The private primary-owned `stage2_smoke.py` launched an isolated API, fixture HTTP server and new headless Brave profile. Health checks preceded actions. Installed `model_tools.handle_function_call` dispatched actual `jobbot` and `terminal` calls in one session over two reserved jobs.
- The native terminal commands exercised the actual CDP client and JavaScript against local fixture DOM: discovery, autofill change, exact synthetic name/email residual corrections, and continuation to the next step. Assertions read the browser and the actual application database. Both attempts recorded one automatic tool completion with positive measured duration; both ended `ready_for_review`, zero submission records, all leases released.
- Final replay after the seven primary review fixes passed in `artifacts/jobbot-v1-private/stage2-smoke-2ae0121bcc2b4be4aa4188465c70f44f/result.json`. Its API/static/browser processes were stopped and ports 56637/56638/56642 verified closed; temporary API credentials removed. DB and screenshots retained privately.
- Earlier failing integration attempt is preserved in a different synthetic instance as interrupted; it was not deleted or relabeled into a successful application. The helper asset's leading comment prevented callable recognition by the existing CDP client; moving the comment inside the function fixed the observed browser failure.

## Evidence limits
The Simplify surface was a **synthetic local stand-in**, not the signed-in official extension. The native-dispatch test used **explicit fixture model metadata and no model inference**. It proves actual tool dispatch/browser interaction/automatic tool telemetry, not a new live model request or Workday/Simplify submission. The requested Astra subscription route was separately verified during preflight. Official browser/mailbox/live-portal validation remains a later explicit authorization gate.

## Review status
The first independent review found seven concrete issues. Regressions failed, primary fixes landed, and the second independent review confirmed all seven corrected:
- Unknown panel state does not release writer ownership.
- Detached/background terminal work is rejected inside managed attempts.
- A new run cannot drop a live attempt binding; non-quiescent finish retains the guard.
- Native submission intent accepts required evidence under app policy.
- Recoverable preflight delivery failures retain blocked-call attribution and do not permanently poison the session.
- Private page-local value comparison detects valid-to-valid and selected-value changes without returning values/value hashes; DOM replacement is covered.
- Continue waits for a distinct page signal, rather than conflating field changes or a still-complete panel with navigation.

That re-review identified **S2-R8**, a same-URL SPA step-identity regression. Targeted actual-JavaScript regressions reproduced it. The primary fix uses non-validation headings and field key/type structure for step identity; values and validity remain separate. All three new regressions passed. Final independent review confirmed R1–R8 closed with no remaining findings; its full receipt is in the ignored review-stage2-final/verdict.json. Stage 3 tests remain preparation only at this checkpoint.

## Test delegation and scope
Unit/regression authoring and execution were assigned to the configured agy proxy using Gemini 3.8 Flash Medium/High. Primary reviewed and corrected fixture/API mismatches, implemented production changes, and reran tests. Independent review was read-only. Original user histories, credentials, browser profile, application/discovery skills, VM and cron configuration were not modified by this test run.
