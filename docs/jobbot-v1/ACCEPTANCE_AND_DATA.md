# Windows acceptance and data-safety plan

These are required test scenarios to implement/run, not claims of tests already passed. The builder must maintain a requirement-to-test map with exact commands, environment/commit, pass/fail/pending results, and evidence. Parameterize related cases instead of creating redundant paperwork.

## 1. Three kinds of tests, all on Windows now

**Automated core tests:** temporary SQLite instances, synthetic candidate/job data, fake email/provider results, and a fake non-Hermes worker against the real services/API. No personal credentials, real employers, or active browser targets.

**Installed integration:** real Windows Hermes hooks/tools/profile and the staged app, with explicit test run and browser context. Verify correlation, model/provider resolution, skill version and controls. A simulated panel is useful for logic tests but does not prove real Simplify integration.

**Authorized live smoke test:** actual user-selected role and truthful candidate materials, using the actual Simplify extension. Stop at Review unless submission is specifically authorized. Account creation, autosave, password reset, email verification and file upload can have effects before Submit; do not call them harmless purely because the final click is disabled.

Ubuntu is not a gate for this phase. Portability is designed into paths/configuration, but later Linux validation remains a separate requirement.

## 2. Core and protocol acceptance matrix

| ID | Scenario | Required result |
|---|---|---|
| Q1 | Manual URL, Hermes discovery and another client supply one requisition with tracking variants | One job; multiple source records; no duplicate execution |
| Q2 | Different requisitions at the same company; identity-bearing query parameters | Distinct jobs retained; conservative normalization |
| Q3 | Previously applied requisition arrives under new email | Historical protection/reconciliation; no automatic reapply |
| Q4 | Two processes claim the same job/browser simultaneously | Exactly one active owner; test real independent DB clients |
| Q5 | Cron request and dashboard request repeat or overlap | Idempotent run request or visible waiting; no competing browser writers |
| Q6 | Unassessed, held or excluded job supplied by an integration | Intake does not bypass execution policy |
| Q7 | Fixed batch receives more discoveries or user changes queue order | Explicit batch policy preserved; next claim respects authorized controls |
| R1 | App/API restarts while external worker is alive | Active work is reconciled, not blindly marked failed |
| R2 | Expired worker sends events/finish after replacement | No stale overwrite or lease revival; history attribution remains correct |
| R3 | Same completion request retried; conflicting completion later | Same is idempotent; conflict is rejected/reconciled |
| R4 | Submit attempted and confirmation times out | submission_unknown; no blind retry |
| R5 | Worker heartbeat continues without useful page progress | UI distinguishes alive/stalled; configured budget recovery occurs |
| R6 | Pause/stop during tool or autonomous extension activity | Requested versus acknowledged state truthful; no continuing unowned writes |
| R7 | Retry after blocked/failed attempt | Prior timing/events/account facts retained, not cleared |
| T1 | Deterministic test clock with tool/model/email/repair phases | Absolute timestamps and total duration correct; waits included |
| T2 | Overlapping calls, late hook delivery after next job starts | No double-counted total or wrong-attempt attribution |
| T3 | Clock adjustment or crash with no final event | Monotonic/segment handling or explicit uncertainty, not invented exact end |
| T4 | Event API unavailable temporarily | Bounded redacted spool and idempotent replay; no fictitious progress |
| T5 | Password/OTP/token/error payload and untrusted HTML | No secrets in ordinary logs/UI/alerts; HTML rendered as data |
| T6 | Routine successful application | Concise semantic timeline; no screenshot/chain-of-thought dump |
| A1 | Account created/verified but application fails | Account remains available for next role |
| A2 | Crash around account-creation response | Stored request/credential reference supports reconciliation; no blind new account |
| A3 | Legacy/new emails and same/similar employers across namespaces | Correct identity/namespace; no credential reuse by company name alone |
| A4 | Unrelated/newest OTP versus correlated request | Only correct recipient/purpose/portal/time-matched message used; no code logged |
| L1 | Helper learned in job 1, matching job 2 same session | Existing helper discoverable and reused; version/outcome recorded |
| L2 | New session encounters matching problem | Relevant lesson/helper supplied without relying on old transcript |
| L3 | Lesson fails or helper changes during a run | Failure/version visible; no silent live shared-code replacement |
| L4 | Learned shortcut suggests changing profile or exclusions | Procedure learning cannot alter factual/authorization policy |
| C1 | Fake worker has no Hermes installed | Common intake/run/event/account/finish workflow still works |
| C2 | Worker offline or provider unsupported | UI reports actual unavailable/awaiting capability, not fake running |
| C3 | External fit score and supplied cover letter | Version/provenance stored; selected vs uploaded distinguished |
| C4 | Tests started from different CWD or inherited real env | Explicit isolated DB/profile, or fail closed; no surprise empty/real DB |
| D1 | Fresh DB plus representative old-schema fixture | Initialization and migrations work; histories preserved |
| D2 | Fresh-start preview targets an existing/incorrect instance | Refuse implicit overwrite; no destructive wildcard deletion |

## 3. Browser/provider integration scenarios

Observe these first in local fixtures, then verify applicable ones in the real extension under authorized scope:

- Autofill already active after page change: do not double trigger or compete for fields.
- Autofill available but idle: prefer it and record actual start.
- Simplify Continue available: prefer it and verify navigation.
- Continue/autofill missing or stale: use bounded permitted recovery, not an infinite hunt.
- Panel reports complete while residual validation remains: page evidence wins.
- Panel cannot be read: show the limitation; do not invent its text or API.
- Field properties change without DOM-tree mutation: snapshots still detect useful progress.
- Hierarchical referral field: find a truthful selectable leaf and verify commit.
- Shared phone code across countries: select the right semantic country/code combination.
- Dependent fields or added employment rows: delta discovery without duplicate rows/full-form destructive refill.
- Unknown or inverted screening question: authoritative profile answer or explicit unresolved, not blanket Yes/No.
- Completed, blocked and unrelated tabs coexist: cleanup only eligible owned targets, never the whole browser.

Do not have an autonomous old run and the new test run using the same browser profile simultaneously. Record and quiesce the old owner first. A fixture proxy and an actual extension are different evidence levels.

## 4. Database fresh start: do not wipe first

Start development by choosing a NEW test DB and synthetic profile. Leave the existing Windows DB and all VM data alone. There is no need to erase historical emails to write code.

Use distinct instance IDs/paths for disposable development and a real Windows pilot. New pilot accounts/submissions are real records, even when produced during testing. Never throw them away as fixtures.

For an authorized live fresh start, first inventory the actual resolved DB paths for UI, CLI, cron and Hermes. Do not assume they share a file or that the VM copy matches Windows. Summarize counts and identities without dumping secrets.

Archive each source through SQLite's online backup facility or a verified consistent offline process. Validate integrity and relevant record counts, save the source path/schema/version/time/hash, and use restrictive access. Do not ordinary-copy just a live database while ignoring WAL/journal state. Do not delete journal/sidecar files to make a backup appear clean.

Create a fresh target path only after checking it does not exist; initialize through migrations. Keep trustworthy prior-submission keys/evidence in a minimal suppression ledger. Keep unverified/uncertain outcomes held for reconciliation. Preserve any legitimate records already using the new identity. Do not relabel old accounts with the new email.

Only change the active configuration at a controlled cutover with no live application owner. Read back the same DB instance/path from every process before enabling work. Rollback must preserve any external actions performed after cutover; restoring an older snapshot blindly can lose knowledge of new submissions.

No production reset is part of ordinary development. Implement preview/backup/init tooling and test it using fixtures; execute it against real data only with explicit authorization.

## 5. Windows release gate

The release report must identify the exact commit, interpreter/dependencies, installed Hermes version/provider/model, effective skill versions, resolved test DB/profile/browser context, actual test commands, and failures/skips/pending items.

Core automated tests and the fake worker prove the operational protocol, not ATS reliability. Actual installed-Hermes and Simplify checks must be separately recorded. A few successful live roles are smoke tests, not a statistical success-rate benchmark. Report total time, interventions, wrong-answer checks, fallback usage and blockers honestly.

Acceptance requires no unreviewed critical regression, no destructive data operation, and no implicit live activation. Publish sanitized source/skills only after permission. The later Ubuntu rollout is separate and must repeat environment-specific checks before being called ready.
