# Requirement-to-test map

Source: ACCEPTANCE_AND_DATA.md. Exact tests/commands/results will replace planned entries as slices pass. No pending case is counted as verified.

| ID | Required scenario | Required result | Planned test group | Status |
|---|---|---|---|---|
| Q1 | Manual URL, Hermes discovery and another client supply one requisition with tracking variants | One job; multiple source records; no duplicate execution | test_core.py + test_compatibility.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| Q2 | Different requisitions at the same company; identity-bearing query parameters | Distinct jobs retained; conservative normalization | test_core.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| Q3 | Previously applied requisition arrives under new email | Historical protection/reconciliation; no automatic reapply | test_ownership.py + test_data_tools.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| Q4 | Two processes claim the same job/browser simultaneously | Exactly one active owner; test real independent DB clients | test_ownership.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| Q5 | Cron request and dashboard request repeat or overlap | Idempotent run request or visible waiting; no competing browser writers | test_ownership.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| Q6 | Unassessed, held or excluded job supplied by an integration | Intake does not bypass execution policy | test_ownership.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| Q7 | Fixed batch receives more discoveries or user changes queue order | Explicit batch policy preserved; next claim respects authorized controls | test_ownership.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| R1 | App/API restarts while external worker is alive | Active work is reconciled, not blindly marked failed | test_ownership.py + test_compatibility.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| R2 | Expired worker sends events/finish after replacement | No stale overwrite or lease revival; history attribution remains correct | test_ownership.py + test_events.py + test_safety_regressions.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| R3 | Same completion request retried; conflicting completion later | Same is idempotent; conflict is rejected/reconciled | test_ownership.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| R4 | Submit attempted and confirmation times out | submission_unknown; no blind retry | test_ownership.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| R5 | Worker heartbeat continues without useful page progress | UI distinguishes alive/stalled; configured budget recovery occurs | test_events.py + test_safety_regressions.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| R6 | Pause/stop during tool or autonomous extension activity | Requested versus acknowledged state truthful; no continuing unowned writes | test_events.py + test_safety_regressions.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| R7 | Retry after blocked/failed attempt | Prior timing/events/account facts retained, not cleared | test_ownership.py + test_safety_regressions.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| T1 | Deterministic test clock with tool/model/email/repair phases | Absolute timestamps and total duration correct; waits included | test_events.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| T2 | Overlapping calls, late hook delivery after next job starts | No double-counted total or wrong-attempt attribution | test_events.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| T3 | Clock adjustment or crash with no final event | Monotonic/segment handling or explicit uncertainty, not invented exact end | tests/jobbot_v1/test_telemetry.py (planned) | pending |
| T4 | Event API unavailable temporarily | Bounded redacted spool and idempotent replay; no fictitious progress | tests/jobbot_v1/test_telemetry.py (planned) | pending |
| T5 | Password/OTP/token/error payload and untrusted HTML | No secrets in ordinary logs/UI/alerts; HTML rendered as data | test_events.py + test_protocol.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| T6 | Routine successful application | Concise semantic timeline; no screenshot/chain-of-thought dump | tests/jobbot_v1/test_telemetry.py (planned) | pending |
| A1 | Account created/verified but application fails | Account remains available for next role | test_accounts.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| A2 | Crash around account-creation response | Stored request/credential reference supports reconciliation; no blind new account | test_accounts.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| A3 | Legacy/new emails and same/similar employers across namespaces | Correct identity/namespace; no credential reuse by company name alone | test_accounts.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| A4 | Unrelated/newest OTP versus correlated request | Only correct recipient/purpose/portal/time-matched message used; no code logged | test_accounts.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| L1 | Helper learned in job 1, matching job 2 same session | Existing helper discoverable and reused; version/outcome recorded | tests/jobbot_v1/test_knowledge.py (planned) | pending |
| L2 | New session encounters matching problem | Relevant lesson/helper supplied without relying on old transcript | tests/jobbot_v1/test_knowledge.py (planned) | pending |
| L3 | Lesson fails or helper changes during a run | Failure/version visible; no silent live shared-code replacement | tests/jobbot_v1/test_knowledge.py (planned) | pending |
| L4 | Learned shortcut suggests changing profile or exclusions | Procedure learning cannot alter factual/authorization policy | tests/jobbot_v1/test_knowledge.py (planned) | pending |
| C1 | Fake worker has no Hermes installed | Common intake/run/event/account/finish workflow still works | test_protocol.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| C2 | Worker offline or provider unsupported | UI reports actual unavailable/awaiting capability, not fake running | test_protocol.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| C3 | External fit score and supplied cover letter | Version/provenance stored; selected vs uploaded distinguished | tests/jobbot_v1/test_protocol_config_assets.py (planned) | pending |
| C4 | Tests started from different CWD or inherited real env | Explicit isolated DB/profile, or fail closed; no surprise empty/real DB | tests/jobbot_v1/test_protocol_config_assets.py (planned) | pending |
| D1 | Fresh DB plus representative old-schema fixture | Initialization and migrations work; histories preserved | test_core.py + test_data_tools.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |
| D2 | Fresh-start preview targets an existing/incorrect instance | Refuse implicit overwrite; no destructive wildcard deletion | test_data_tools.py | partial — service/HTTP fixtures pass; full scenario and integration gates not yet closed |

## Browser boundary (B1–B12)

| ID | Scenario | Evidence |
|---|---|---|
| B1 | Autofill already active after page change: do not double trigger or compete for fields. | local fixture pending; actual extension pending authorized scope |
| B2 | Autofill available but idle: prefer it and record actual start. | local fixture pending; actual extension pending authorized scope |
| B3 | Simplify Continue available: prefer it and verify navigation. | local fixture pending; actual extension pending authorized scope |
| B4 | Continue/autofill missing or stale: use bounded permitted recovery, not an infinite hunt. | local fixture pending; actual extension pending authorized scope |
| B5 | Panel reports complete while residual validation remains: page evidence wins. | local fixture pending; actual extension pending authorized scope |
| B6 | Panel cannot be read: show the limitation; do not invent its text or API. | local fixture pending; actual extension pending authorized scope |
| B7 | Field properties change without DOM-tree mutation: snapshots still detect useful progress. | local fixture pending; actual extension pending authorized scope |
| B8 | Hierarchical referral field: find a truthful selectable leaf and verify commit. | local fixture pending; actual extension pending authorized scope |
| B9 | Shared phone code across countries: select the right semantic country/code combination. | local fixture pending; actual extension pending authorized scope |
| B10 | Dependent fields or added employment rows: delta discovery without duplicate rows/full-form destructive refill. | local fixture pending; actual extension pending authorized scope |
| B11 | Unknown or inverted screening question: authoritative profile answer or explicit unresolved, not blanket Yes/No. | local fixture pending; actual extension pending authorized scope |
| B12 | Completed, blocked and unrelated tabs coexist: cleanup only eligible owned targets, never the whole browser. | local fixture pending; actual extension pending authorized scope |

## Installed/real evidence gates
- H1: installed native hook/tool dispatch, staged skill/settings load, provider routing, attempt/action correlation and controls — pending.
- H2: this Windows Hermes uses real tools with isolated local forms and real application telemetry; assertions read back exact run — pending.
- H3: actual Simplify-enabled profile safely reconciled, readable panel or explicit limitation — pending; CDP unavailable at preflight.
- H4: dedicated connector identity and correlated mail — pending; existing metadata probe 401, no messages accessed.
- W1: independent review, exact code/skill/dependency manifest and rollback report — pending.
- U1: later Ubuntu gate is deferred, never inferred from Windows.

Core matrix count verified from source: 34. All work uses synthetic data.
