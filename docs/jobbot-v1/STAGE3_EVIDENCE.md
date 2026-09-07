# Stage 3 evidence — reviewed Windows implementation

## Current implemented scope
- Versioned effective settings, optimistic version checks, requested worker-model matching, company/market policy checks, and frozen active-attempt lease settings.
- Operator cookie login/logout and authenticated views, using the original FastAPI/plain HTML/CSS/JavaScript stack and existing palette.
- Queue selection and fixed run requests; explicit requested/acknowledged controls; attempts, overlap-aware timing, uncertainty and structured issues.
- Scoped candidate lessons, manual activation/demotion/retirement and verification history; versioned helper catalogue with file/hash checks and quiescent activation.
- External resume/cover-letter metadata, effective job/attempt selection, upload-state history and external versioned assessments. No internal document generation or scoring.
- Worker-owned account events and mail-correlation metadata; verified namespace aliases; separate created/unverified, verified, recovery and locked states. No mailbox is opened by these services.
- Explicit target metadata and bounded extensions; stale owners cannot retag targets or revive expired leases.
- Native next/context retrieves the authoritative job package and bounded resources; missing required documents block submission intent; idle control acknowledgements use the existing run-level operation.
- Health/version evidence and focused job/page/activity/issue context are exposed to the operator without labeling a completed attempt as active.

## Verified commands and results
Final full command (no archive or other test exclusion):
`JOB_APPLIER_DB_PATH=<ignored-synthetic-db> BROWSER_USE_CDP_URL=http://127.0.0.1:1 .venv/Scripts/python.exe -m pytest tests -q --tb=short --junitxml=artifacts/jobbot-v1-private/closeout-tests.xml`

Result: **361 passed**, two known deprecation warnings; JUnit suite time 82.263 seconds. Compilation, `node.exe --check job_applier/static/jobbot.js`, and `git diff --check` passed in the same exit-0 command chain. All 361 cases and absence of failures/errors/skips were separately checked from JUnit XML.

Targeted RED→GREEN cycles included settings/view contracts and real effects, UI cookie security, learning/catalogue, documents/assessments, resource API roles, interval-union timing, owned account/mail operations, budgets/targets, context retrieval/document precedence, timing uncertainty, and operator versions/context. Test-only work was delegated to agy Gemini 3.8 Flash Medium/High and reviewed/exercised by primary Windows Hermes. One proxy 502 left a complete test file; it was inspected and run locally rather than discarding it or changing provider.

## Real browser UI scenario
`artifacts/jobbot-v1-private/ui_smoke.py` created a new synthetic instance and a separate headless Brave profile. Explicit readiness checks preceded interaction. Actual page assertions verified operator login; instance display; injected markup rendered as literal text; fixed selection/request; awaiting-worker state before acceptance; requested pause versus acknowledged pause; resume/stop; event timeline; timezone save; and logout. Synthetic worker state transitions were supplied through the real service, not represented as a live application worker.

The final UI rerun recorded zero submissions. Queue and timeline screenshots were inspected and were readable without overlapping controls. Current evidence is retained at `artifacts/jobbot-v1-private/ui-smoke-eb2157a502e24136a7c82f68df76c71a/result.json` and adjacent screenshots. API/browser processes were stopped, ports 60156/60157 verified closed, and temporary credentials removed. The UI test is not official Simplify/ATS or live model-inference evidence.

## Gate status
Independent review **passed** against `artifacts/jobbot-v1-private/review-stage3-closeout`, including its explicit `managed_context.py` import amendment. All five prior findings (S3-R1..R5) were closed with no security/logic blockers. A separate bounded review of `review-field-ordering` also passed: late completion retains original action attribution without reviving a cleared or newer semantic field. Both new ordering cases were observed failing before the fix, then passed; the combined targeted run passed 13 tests.

Final source hashes were verified against the original 21-file snapshot and both approved amendments. Scoped additive archival also passed all three tests and independent review. Native installed-Hermes/Brave validation was rerun after the last production amendment; see STAGE4_EVIDENCE.md. This is a reviewed implementation candidate, **not live release acceptance**. ACCEPTANCE_LEDGER.md accounts for all 34 core IDs and explicitly lists unexercised live/helper-use scenarios. No production history/profile, active application/discovery skill, VM/cron, or remote Git state was changed.
