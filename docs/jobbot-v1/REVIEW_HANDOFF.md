# Independent review handoff — ordinary Hermes application runtime

## Read this first

**This branch is a review checkpoint, not a working-live-application release.** The user requested a new GitHub branch so another model can assess why ordinary Hermes application execution keeps stopping at runtime boundaries. Do not resume applications merely because the code and tests are present.

- Branch: `review/hermes-jobbot-runtime-handoff`
- Parent checkpoint: `da6c84d` on `review/jobbot-huron-auth-checkpoint`
- Repository: `rejozmathew/auto-job-applier`
- Windows source checkout: `C:/GitClone/auto-job-applier-jobbot-v1`
- Review delta: `git diff da6c84d..HEAD`
- This snapshot includes the existing uncommitted auth/mail/native-launcher work as well as the newer Workday supervisor, canonical skills, internal-auth bridge and documentation. It is intentionally the combined candidate; do not attribute every change to the last credential fix.

The local private runtime, tokens, candidate profile, resume, browser profile, databases, checkpoints and transcripts are **not published**. This branch preserves source and a sanitized incident record, not a deployable copy of the user's private environment. No original branch history is rewritten.

## Product requirement and constraints

Desired experience: **tell an ordinary Hermes conversation to apply to a URL; that same conversation uses repository-owned helpers, Simplify and managed tracking.** No mandatory dashboard visit, separate worker conversation, manual token export or long configuration prompt. A dashboard-triggered worker can be an alternate route later, not an implicit fallback now.

- Simplify is the primary filler; wait while it writes, use enabled Continue after settling, and repair only actual required blockers.
- No in-run PDF extraction, career/education reconstruction, exhaustive form auditing or competing form writers.
- Repository skills are canonical; Hermes discovery is thin; another harness should use the same runtime implementation.
- Explicit managed config/database for new activity; legacy database is read-only duplicate history. No migration/dual-writing or guessed SQLite paths.
- Preserve correct identity/document, truthful screening answers, ownership/fences, pause/stop and uncertain-submission protection. Verify exact employer confirmation once.
- Under ten minutes is a target, **not an achieved benchmark for this new route**.
- User wants a small, coherent application eventually. Identify duplicated lifecycle responsibilities and retirement criteria; avoid another broad redesign or speculative helper pile.

## Evidence chronology — distinguish facts from reports

### 1. Workday supervisor engineering

The code added a portable observe/act/wait runner, Workday DOM helpers, bounded recovery, shared CDP function invocation and canonical/thin skills. Synthetic managed-API and isolated CDP tests passed; see [WORKDAY_FAST_VERIFICATION.md](WORKDAY_FAST_VERIFICATION.md).

An earlier GAIG R9045 application was already submitted using the prior workflow. It must not be resubmitted and is **not** live acceptance evidence for this new ordinary-Hermes path.

### 2. Ordinary Hermes was blocked on internal authentication

The user reported no native `jobbot` tool and no `JOBBOT_PILOT_WORKER` environment variable. The portable CLI returned `credential_unavailable` before claim. Local preflight and duplicate checks were not proof of API authentication.

Implemented: shared `credential(name, config)` preserves environment precedence and optionally resolves an exact private JSON path/key from `credential_files`. The selected ignored native config was wired to its existing worker/operator entries. No secret values were added to tracked files or rotated.

Verified then: environment-free worker and operator health succeeded against the configured local managed API; the actual CLI health command passed; worker access to operator `view` was rejected with `role_forbidden`. Focused tests and the managed suite passed. This proved authentication **at that time**, not durable service/browser readiness.

Details, config schema, roles and rollback: [HERMES_CONNECTION.md](HERMES_CONNECTION.md).

### 3. Resumed Credit Acceptance application still failed

User-supplied report, not independently replayed:

- Role: Credit Acceptance, Senior Director, Marketing Insights and Planning, requisition R13799.
- Authentication and duplicate checks passed.
- Same previously blocked job retried to queued, then placed in run `72ba512e-e49f-412e-a1d3-01556c0f0f19`.
- Attempt `8`, fence `8`, worker `windows-hermes-supervised`.
- Binding was refused once because the old target belonged to a prior attempt.
- CDP `http://127.0.0.1:9223` reportedly became unavailable while binding. An open Brave window showed an unrelated YouTube tab; the exact Workday target could not be safely observed/rebound.
- Attempt reportedly expired; no submission intent or submit action was recorded. The run was left preserved for reconciliation.

The quoted run/attempt identifiers are investigation anchors, **not authority to claim, retry, reconcile or submit**.

### 4. Latest read-only diagnosis in the coordinating thread

Directly verified:

- TCP connection to `127.0.0.1:9223` failed; `/json/version` raised a connection error.
- Windows process metadata showed a running main `brave.exe` process, but no `--remote-debugging-port`, `--user-data-dir` or `--profile-directory` flags in that process's command line. This does not prove where the lost automation profile went or why it stopped.
- A later request for attempt 8 through the configured managed client failed with connection refused / `api_unavailable`. Thus the configured service was also unreachable **at diagnosis time**. It may have been healthy earlier, as the user's report states.
- `application_runtime.inspect_runtime` validates CDP URL shape/configuration; it does **not** probe live browser/extension health.
- `managed_runtime.bind_target` rejects an open/preserved target owned by a different attempt. This is a safety rule, not permission to erase the old target.
- `FastRunner.run` sends heartbeats while its loop is active. This alone does not prove coverage during intake, target binding, model deliberation, authentication exceptions or gaps between bounded CLI calls.

Not determined: why the browser/service stopped, whether a launcher/parent lifetime killed either, which process owned the original browser, whether an exact old target still exists, or the authoritative current attempt state after the failed API read.

**No runtime-recovery implementation was made after this diagnosis.** No service/browser restart, tab manipulation, lease reconciliation, database mutation or submission occurred in the coordinating thread. The user instead asked for this GitHub checkpoint.

## Priority review questions

Return concrete file/line evidence and distinguish confirmed defects from missing coverage or operational hypotheses:

1. **Entry-point completeness:** Does the portable path actually cover intake, document selection, requested/observed runtime identity, accept/claim, bind, credentials, heartbeat, advancement and terminal recording in one ordinary chat? Which pieces still depend on native plugin hooks or the separate launcher? Authentication alone is insufficient.
2. **Startup/lifetime:** Who owns the managed API and automation-enabled Brave process? Are they attached to a short-lived tool/session? What minimal idempotent readiness/launch boundary is missing? Do not assume an arbitrary open browser has the right profile or extension.
3. **Claim ordering and liveness:** Can an attempt be claimed before real API/browser/extension readiness? Trace heartbeat behavior before the runner and across bounded calls/exception handling. Is an independent lease keeper needed, and where should it live?
4. **Recovery correctness:** Trace expired attempts, quarantined browser leases, preserved targets, operator `reconcile`, `retry` and target rebinding together. How can the intended exact target be recovered without weakening ownership or fabricating quiescence? A dead endpoint alone does not prove no writer exists.
5. **Native/portable parity:** `native_hermes_session.py` requires the profile skill to resolve directly to the canonical skill, while the installed skill is now a thin repository entry. The separate worker main still takes its token from environment. Assess these as route-specific incompatibilities, not proof that the already-tested CLI credential resolver failed.
6. **Submission safety:** Re-check fresh identity and blocker checks, persisted intent, exact-requisition confirmation, and post-submit writer settlement. Passing synthetic snapshots do not prove real Simplify/Workday behavior.
7. **Smallest consolidation:** Recommend one bounded next implementation with measurable acceptance criteria. Identify which existing component should own it and what can be retired only after replacement coverage. Do not propose bypassing the managed ledger as a shortcut.

## Suggested reading order

1. This handoff, `AGENTS.md`, [APPLICATION_RUNTIME.md](APPLICATION_RUNTIME.md), [HERMES_CONNECTION.md](HERMES_CONNECTION.md).
2. `skills/productivity/job-apply/SKILL.md`, its internal-service-auth reference, `skills/productivity/workday-simplify/SKILL.md`, and the thin integration skill.
3. `job_applier/application_runtime.py`, `managed_cli.py`, `managed_client.py`, `workday_fast.py`.
4. `managed.py` (accept/claim/reconcile/retry), `managed_runtime.py` (target ownership/observation), `managed_events.py` (heartbeat/status), and relevant lease/safety definitions traced from actual callers.
5. `hermes_plugin.py`, `managed_hermes_worker.py`, `native_hermes_session.py`, `managed_credentials.py`, `hermes_gmail.py`.
6. Workday/Simplify browser helpers and focused tests. Consult the helper map before declaring an older helper unused.

## Reproduction and test boundaries

Use a separate review checkout and synthetic fixtures. Project dependency instructions are in the repository manifests; the Windows implementation used `.venv/Scripts/python.exe`. Standard command:

```text
python -m pytest tests/jobbot_v1 -q
```

DOM fixtures require Node and local jsdom:

```text
npm install --prefix artifacts/jobbot-v1-private/dom-test --no-save --no-package-lock jsdom
```

Do not delete the whole private-artifacts directory on the user's machine; it also contains real runtime data. On another machine create only synthetic configuration and databases. Never use live records to make tests pass.

Prior verified full managed run: **508 passed, 2 dependency deprecation warnings**. The checkpoint's final rerun result is recorded below after execution. Neither result certifies native dashboard launching, a live Workday application, durable browser/service startup, or lease recovery.

## Reviewer deliverable

Read-only review first. Return:
- a short explanation of why the user-visible path remains incomplete;
- ranked concrete blockers with file/line references and evidence;
- unknowns requiring safe runtime observation, separated from source-proven bugs;
- the smallest proposed correction and focused failing regressions;
- an end-to-end acceptance checklist from fresh ordinary Hermes thread through authenticated service, verified browser, owned attempt, maintained lease, authorized submission and exact recorded confirmation;
- a concise consolidation plan and helper retirement criteria.

Do not launch a model worker, touch production credentials/browser/databases, change code or settings, commit further changes, or submit applications as part of the review. A later implementation requires separate direction.

## Checkpoint verification

Final checkpoint rerun: **508 passed, 2 warnings in 147.16 seconds**, exit code 0, using the standard managed suite with `--junitxml=artifacts/jobbot-v1-private/review-runtime-checkpoint-tests.xml`. Warnings are the existing Starlette/AnyIO alias and Pydantic class-config deprecations. This was a synthetic test run, not a live application.

`git diff --check` passed. A scoped publication screen of all candidate source/doc/test files found one credential-literal pattern in `test_workday_fast_integration.py`; inspection confirmed it is an explicitly synthetic TestClient fixture token, not a production credential. The selected private config, auth store and managed database are Git-ignored and excluded. This pattern screen is not a comprehensive security review; that is part of the independent review requested here.

The original checkpoint branch is preserved. The new branch includes the combined source changes without production refactoring during publication. Private files and fixture dependencies are intentionally excluded from the checkpoint. The source/document file list is the commit diff; do not interpret exclusion of private artifacts as deletion from the local machine.
