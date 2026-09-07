# Stage 4 — Windows engineering candidate, live acceptance pending

## Result
The reviewed implementation is available on `jobbot-v1-windows` in the isolated Windows worktree. The offline candidate passed the complete regression suite and real installed-Hermes/Brave plus operator-UI scenarios. This is **not** full live/unattended acceptance. See ACCEPTANCE_LEDGER.md for every required core ID and explicit partial/pending boundaries; RELEASE_MANIFEST.json identifies the exact source checkpoint. WINDOWS_RUNBOOK.md provides gated activation and rollback; LATER_UBUNTU_ROLLOUT.md remains a future plan only.

## Final verification
- Complete tests: **361 passed**, 2 known Starlette/AnyIO and Pydantic deprecation warnings, no exclusions or skips. JUnit suite time: 82.263 seconds; pytest terminal result: 82.31 seconds.
- `.venv/Scripts/python.exe -m compileall -q job_applier integrations skills`: exit 0.
- `node.exe --check job_applier/static/jobbot.js`: exit 0.
- `git diff --check`: exit 0 (Git reported only LF/CRLF normalization notices).
- Independent Stage 3 closeout: PASS, all S3-R1..R5 closed, no security/logic blockers. Source snapshot has 21 files and an explicit context-import amendment.
- Separate delayed-field-context amendment: PASS, no security/logic blockers. Two parametrized regressions observed RED, then GREEN; combined targeted suite: 13 passed. Start attribution survives a later field/navigation marker without reactivating the old field.
- Current production source hashes matched both independently reviewed snapshots/amendments before checkpointing.
- Additive scoped archive: 3 tests passed; independent review passed. Preview binds instance/fingerprint/selection; source remains unchanged until operator approval; writer lock spans verified independent backup and immutable archive metadata insertion. Existing records, retry audit and submission suppression are retained.

## Final native integration (after last production edit)
`artifacts/jobbot-v1-private/stage2_smoke.py` prepared a fresh synthetic DB, generated local-only temporary authentication, plugin home and headless Brave profile. Application, fixture server and CDP readiness were verified before the scenario.

Actual execution through installed Hermes `tools.model_tools.handle_function_call` and native plugin hooks completed:
1. Acceptance and two single-job claims in one persistent worker session.
2. Authoritative application context and explicit semantic field milestones.
3. Actual browser work through native terminal dispatch against local stand-in forms.
4. Automatic measured tool spans attributed to their original field/attempt; UI model metadata explicitly remained a fixture.
5. Quiescent finish, idle pause request/acknowledgement, refused claim while paused, resume and next job.
6. Run exhausted/completed, two terminal attempts, zero submission ledger records and released browser lease, verified by direct SQLite readback.

Final native command returned exit 0 and `passed: true`. Evidence: `artifacts/jobbot-v1-private/stage2-smoke-09b04fb0e14c41439e6fc7c493c581f6/result.json`; session count 1, attempt count 2, automatic measured tool events 1 per attempt. Ports 56168/56169/56170 were verified closed after stopping only the test processes; temporary local auth was removed. This did **not** invoke model inference or the official Simplify extension.

## Operator browser integration
A separate real Playwright/Brave scenario verified login/logout, instance/DB identity, literal rendering of injected HTML (no created image element or script execution), selected fixed-batch request, awaiting-worker state, pending versus acknowledged pause, resume/stop, timeline and timezone-setting persistence. Synthetic worker transitions used the actual service; they were not claimed as a real application agent.

Evidence: `artifacts/jobbot-v1-private/ui-smoke-eb2157a502e24136a7c82f68df76c71a/result.json`, `queue.png`, `timeline.png`. Screenshots were visually inspected. Zero submissions and released lease were read back. Ports 60156/60157 were verified closed; temporary local auth removed.

## Test-harness issues resolved honestly
- Background shells initially used an old receipt because foreground exports were not inherited. Only isolated development fixtures were involved; those processes were stopped. Exact final receipt paths and explicit instance health checks prevented reuse.
- The first native readback assertion expected an event `payload` field instead of actual `payload_json`. The assertion was corrected; completed DB state was verified, and the entire native scenario was subsequently rerun successfully in a fresh instance after the last code edit.
- A shell/PTY Node wrapper reported `stdin is not a tty`; the bare `node.exe` check succeeded. These were not fabricated as first-attempt passes.

## Required gates still open
- Integrated subscription-Astra reasoning plus managed browser work on an authorized employer role. Earlier minimal subscription-provider preflight is recorded in EXECUTION_PLAN.md; fixture metadata is not substitute proof.
- Official Simplify/Workday/ATS behavior, hierarchical/referral/phone/dependent-row semantics and mixed real/unrelated-tab cleanup.
- Dedicated mailbox identity/access and a real correlated verification flow.
- Actual versioned helper execution/reuse across applications, not only catalogue/context metadata.
- Real external document upload and review-only stopping behavior; accounts, uploads and autosave require explicit permitted scope even without final submission.

These cannot be silently waived. No real application, new account/reset, live history/profile migration, shared skill activation, Ubuntu/Unraid/cron changes, push or deployment occurred. Test credentials, DBs, screenshots, raw receipts and provider artifacts remain ignored, not part of the source handoff.
