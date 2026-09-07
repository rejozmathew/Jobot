# Windows acceptance ledger

This ledger distinguishes exercised code from live product acceptance. It does not replace the PRD. Final consolidated run: **361 passed, 2 known deprecation warnings, no excluded or skipped tests**; test result is held at `artifacts/jobbot-v1-private/closeout-tests.xml`. The semantic-context ordering follow-up passed both parametrized cases, independent review, the full suite, and a fresh native browser run.

## Exact consolidated command
```text
JOB_APPLIER_DB_PATH=<absolute-ignored-synthetic-db> BROWSER_USE_CDP_URL=http://127.0.0.1:1 .venv/Scripts/python.exe -m pytest tests -q --tb=short --junitxml=artifacts/jobbot-v1-private/closeout-tests.xml
```
All test paths below are relative to `tests/jobbot_v1/`. Every one of the 34 required core/protocol IDs is accounted for; PASS means only the evidence level explicitly named.

| ID | Source tests | Exercised behavior | Status / boundary |
|---|---|---|---|
| Q1 | `test_core.py`, `test_harvest_handoff.py` | Shared intake and provenance | PASS (synthetic) |
| Q2 | `test_core.py`, `test_review_identity.py`, `test_stage3_review_closeout.py` | Requisition queries, aliases and owned target identity | PASS (synthetic) |
| Q3 | `test_ownership.py`, `test_data_tools.py` | Applied suppression survives identity/migration | PASS (synthetic) |
| Q4 | `test_ownership.py` | Independent process claims; one owner | PASS (real local DB processes) |
| Q5 | `test_ownership.py`, `test_protocol.py` | Idempotent/overlapping batch requests | PASS (synthetic) |
| Q6 | `test_ownership.py`, `test_settings_effects.py` | Unassessed/excluded/policy refusal | PASS (synthetic) |
| Q7 | `test_ownership.py`, `test_settings_effects.py` | Fixed membership and frozen policy | PASS (synthetic) |
| R1 | `test_ownership.py`, `test_continuity.py` | Reopen with live/expired ownership | PASS (synthetic) |
| R2 | `test_safety_regressions.py`, `test_stage3_review_closeout.py` | Stale events/account mutations/fences | PASS (synthetic) |
| R3 | `test_events.py`, `test_final_review_regressions.py` | Exact replay and conflict refusal | PASS (synthetic) |
| R4 | `test_ownership.py`, `test_stage2_adapter_review.py` | Submission intent and unknown outcome hold | PASS (synthetic; no real submit) |
| R5 | `test_events.py`, `test_runtime_budgets_targets.py`, `test_stage3_review_closeout.py`, `test_field_context_ordering.py` | Alive vs useful progress; measured semantic budgets; delayed completion cannot restore old scope | PASS (synthetic + final native measured field context) |
| R6 | `test_events.py`, `test_safety_regressions.py`, `test_stage2_boundary_review.py` | Pending writers/extension vs control acknowledgement | PASS (synthetic + isolated native idle pause/resume) |
| R7 | `test_ownership.py`, `test_owned_account_events.py` | Retries preserve earlier records | PASS (synthetic) |
| T1 | `test_events.py`, `test_timing_reports.py` | Absolute timestamps, wait-inclusive wall time | PASS (deterministic clocks) |
| T2 | `test_timing_reports.py`, `test_adapter_model_hooks.py`, `test_stage2_adapter_review.py` | Overlap union and original-attempt correlation | PASS (synthetic + native measured tool spans) |
| T3 | `test_stage3_review_closeout.py`, `test_document_timing_gaps.py` | Crash/unfinished/lost ownership uncertainty | PASS (synthetic) |
| T4 | `test_hermes_adapter.py`, `test_adapter_control_retry.py` | Bounded outbox/replay | PASS (synthetic outage) |
| T5 | `test_review_security.py`, `test_operator_ui.py`, `test_events.py` | Secret rejection and untrusted HTML | PASS (synthetic + real browser literal-markup assertion) |
| T6 | `test_native_plugin.py`, `test_timing_reports.py` | Metadata-only event shape; no raw arguments/reasoning | PASS (synthetic + native terminal hooks) |
| A1 | `test_accounts.py`, `test_owned_account_events.py` | Confirmed account survives failed application | PASS (synthetic) |
| A2 | `test_accounts.py`, `test_stage3_review_closeout.py` | Request replay/pending state and stale mutation rejection | PASS (synthetic) |
| A3 | `test_accounts.py`, `test_review_identity.py`, `test_stage3_review_closeout.py` | Identity/tenant scoping, not company-name reuse | PASS (synthetic) |
| A4 | `test_accounts.py`, `test_owned_mail_protocol.py` | Recipient/purpose/sender/namespace/time correlation | PASS (metadata fixtures only; live mailbox pending) |
| L1 | `test_learning_catalogue.py`, `test_resource_protocol.py` | Helper registration/discovery/version/outcome metadata | PARTIAL: real helper execution/reuse across two applications not exercised |
| L2 | `test_learning_catalogue.py`, `test_worker_context_gaps.py`, `test_continuity.py` | Persistent contextual lessons/helpers across sessions | PASS (synthetic service/context); live worker use pending |
| L3 | `test_learning_catalogue.py` | Tamper/version checks, quiescent activation and outcome history | PASS (synthetic) |
| L4 | `test_learning_catalogue.py`, `test_resource_protocol.py` | Procedural learning cannot override candidate facts/policy | PASS (synthetic) |
| C1 | `test_fake_worker.py`, `test_protocol.py` | Agent-neutral worker through shared HTTP services | PASS (non-Hermes worker) |
| C2 | `test_operator_ui.py`, `test_settings_effects.py`, `test_plugin_configured.py` | Awaiting/mismatched/unavailable worker states | PASS (synthetic + actual browser awaiting-worker) |
| C3 | `test_documents_assessments.py`, `test_document_timing_gaps.py` | External score/assets, selected vs uploaded, required document gate | PASS (metadata fixtures; real ATS upload pending) |
| C4 | `test_managed_cli.py`, `test_data_tools.py`, `test_compatibility.py` | Explicit instance/CWD/env isolation | PASS (synthetic) |
| D1 | `test_core.py`, `test_data_tools.py` | Fresh schema and additive verified-copy migration | PASS (synthetic) |
| D2 | `test_data_tools.py`, `test_history_archive.py` | Refuse wrong/existing instance; preview, backup and additive archive | PASS (synthetic) |

## Browser/provider gates
The separate native scenario exercised real installed Hermes dispatch and real Brave on two local stand-in forms in one worker session, with measured tool events and idle pause/ack/resume. The operator scenario exercised real UI login, selection/request, requested vs acknowledged controls, timeline, settings and logout. Both databases were read back with zero submissions and released leases; all five test ports were verified closed. These were isolated synthetic instances, not employer portals.

- Autofill active/idle, preferred Continue, stale/missing/unreadable panel, residual validation and property/SPA step changes: local boundary/JavaScript fixtures (`test_simplify_boundary.py`, `test_stage2_boundary_review.py`, `test_spa_step_identity.py`) plus the real-browser stand-in. **Actual Simplify extension: pending.**
- Hierarchical referral leaf, shared phone country/code, dependent employment rows, and unknown/inverted questions: preserved staged recipes and generic invariants are not end-to-end proof. **Actual semantic portal interactions: pending.**
- Owned-target identity/metadata and exact CDP attachment: local tests (`test_runtime_budgets_targets.py`, `test_owned_cdp.py`, `test_stage3_review_closeout.py`). **Mixed real employer/blocked/unrelated-tab cleanup: pending.**
- Subscription Astra routing: earlier minimal provider preflight passed as recorded in the private handoff; the final native fixture intentionally used fixture model metadata, not inference. **One integrated Astra reasoning + managed-browser application: pending.**
- Dedicated mailbox identity and real verification correlation: **pending authenticated, authorized connector scope**; no personal mailbox was ingested.
- Real employer pilot: **pending explicit role/materials/action authorization**. Review-only can still create accounts, upload files or autosave; those effects need permission. No real applications, account creation/reset, deployment, push, or Ubuntu/Unraid/cron changes occurred.

The Windows candidate is therefore not fully accepted for live/unattended applications. Open items above are not hidden behind the passing unit count.
