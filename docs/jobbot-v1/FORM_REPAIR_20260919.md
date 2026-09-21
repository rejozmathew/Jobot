# Form execution and application time limit — September 19, 2026

The observed RGP registration page was simple, but runtime advice recommended
Autofill while the identity gate rejected it. Shared continuity now preserves
explicit requisition evidence and observed owned navigation across application
steps. Recovery snapshots keep the field inventory. Routine repairs use existing
verified form operations in a grouped call, with exact upload guidance and a
compact required-field list. The effective Ubuntu Apply handoff overlays were
retained in the repository before extending this behavior.

Settings now exposes an application time limit in minutes, defaulting to 30,
with an Off option. A dispatch freezes the limit and deadline; manual start
freezes an equivalent session budget. Model calls, user-input waits and recovery
count. Waiting in the dispatch queue does not count. Same-dispatch replacements and reloads do
not reset the deadline. The queue, desktop monitor and browser host enforce the
deadline outside model reasoning. Native Hermes cancellation is scoped to the
exact task and verified through its active-session API; shared services and
unrelated tabs remain outside that cancellation. Browser cleanup can interrupt
a stuck helper instead of waiting for its action lock.
The stable native task ID survives chat compression; an explicit attach to a
different chat refreshes that mapping rather than cancelling the previous driver.

Expiry records a specific timeout reason and keeps history, saved answers and
submission evidence. A pending Submit remains uncertain; recorded success stays
successful. Scheduling resumes only after executor/browser cleanup. An unreachable
Hermes backend remains pending, without claiming that remote inference stopped.
Dedicated retry summaries were deliberately deferred.

The user authorized the new deadline and deployment to the existing Ubuntu
runtime. No additional retry limit, consent policy or application stop rule was
introduced. Settings edits apply to future attempts.

## Validation

Antigravity with `gemini-3.8-flash-medium` ran the regressions; the primary agent
inspects the actual logs and JUnit. Initial deadline/identity tests reproduced
12 failures. The additional batch/continuity tests reproduced four failures.
The expanded focused run passed 206 tests with one Linux-only skip, including
isolated-browser form repair. Native task identity regressions reproduced the
compression and driver replacement cases; the final targeted run passed 29 tests
with one Linux-only skip. A full managed run passed 988 tests with five Linux-only
skips. The final frozen-source run covered 994 cases: 988 passed, five Linux-only
cases skipped, and one version-metadata assertion failed because the local Git
checkpoint changed HEAD during the run. With HEAD stable, all three tests in that
module passed. No implementation change was needed for that validation race.

On the deployed Ubuntu files, 114 of 115 affected tests initially passed. The
Settings UI test needed the existing Node executable added to the noninteractive
SSH PATH; that exact case then passed. All 14 Linux platform tests passed,
including the Windows-skipped process/socket cases. A disposable-process check
also exercised `application_deadline.stop_process`: the owned child exited with
SIGKILL, the supervisor remained alive, and repeated cleanup succeeded. No employer
application or private profile was used as a test fixture, and no live Hermes
application was interrupted for validation.

Logs and JUnit remain in the ignored private artifacts area: `repair-final.*`,
`repair-version-green.*`, `repair-deployed.*`, `repair-deployed-ui-green.*`,
`repair-linux-platform.*`, and `repair-linux-stop-process.json`.

## Deployment

Completed on the existing authoritative Ubuntu runtime from local implementation
checkpoint `eb5c19d`. Queue pickup was paused through its normal control API while
the existing application finished; no active application was stopped to deploy.
The deployment checked all original source hashes and saved source plus SQLite
backups in the configured private spool under `deployments/form-repair-20260919`.
It applied 23 changed files and verified all 26 bundle files, preserving the
independent route-reconciliation overlay and private runtime configuration.

Both `jobbot-dashboard.service` and `jobbot-queue.service` are active. The dashboard
serves the new controls, and the versioned settings API durably saved the effective
30-minute limit in revision 11. The queue's prior enabled state was restored only
after validation. Settings edits apply to subsequent attempts; existing submission
history, answer history and retry scheduling were retained.
