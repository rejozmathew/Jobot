# Windows closeout changed-file inventory

Source checkpoint: `c0cdf6a8b91871260a09aef077de12103aeeec70`. Full source tree identity and changed-file blob hashes: RELEASE_MANIFEST.json. Documentation is committed separately. No ignored runtime artifact or credential is included.

| File | Change |
|---|---|
| `job_applier/hermes_plugin.py` | Exposes authoritative application context, semantic milestones and idle control acknowledgement through native Hermes. |
| `job_applier/managed.py` | Connects the existing service to settings, views, resources, reports, runtime and archival mixins. |
| `job_applier/managed_accounts.py` | Fences atomic account mutations/replays and resolves verified tenant/account/mail namespaces. |
| `job_applier/managed_api.py` | Adds authenticated operator/worker resource routes and operator-only scoped archival. |
| `job_applier/managed_archive.py` | Binds archive preview to the exact snapshot, verifies independent backup and inserts immutable metadata. |
| `job_applier/managed_context.py` | Builds candidate/job/doc/resource/account context and exposes honest field-budget scope. |
| `job_applier/managed_continuity.py` | Preserves effective settings and current ownership across worker continuation. |
| `job_applier/managed_documents.py` | Stores immutable externally produced assets/assessments and explicit selection/upload history. |
| `job_applier/managed_events.py` | Correlates native measured actions to start-time semantic context and exposes timing uncertainty. |
| `job_applier/managed_learning.py` | Stores scoped lessons/helper versions, controlled activation and verification/outcome history. |
| `job_applier/managed_migrations.py` | Adds canonical schema extensions, event context, document/mail resources and immutable archive metadata. |
| `job_applier/managed_reports.py` | Builds reproducible interval/phase reports with overlap handling and honest unknown timing. |
| `job_applier/managed_runtime.py` | Enforces semantic budgets, exact target identity and bounded extensions; handles delayed scope ordering. |
| `job_applier/managed_settings.py` | Validates/version-controls effective settings and freezes active execution policy. |
| `job_applier/managed_ui.py` | Serves cookie-authenticated operator UI and protects mutations. |
| `job_applier/managed_versions.py` | Collects operator-visible installed/version evidence without asserting unavailable information. |
| `job_applier/managed_views.py` | Projects queue/run/attempt/account state and shared lease/action timing uncertainty. |
| `job_applier/static/jobbot.css` | Styles the operational UI with the existing dark palette and readable state/timing layout. |
| `job_applier/static/jobbot.html` | Defines the operational queue, controls, resource, account and settings screens. |
| `job_applier/static/jobbot.js` | Wires authenticated UI actions and renders untrusted metadata as text. |
| `requirements-jobbot-lock.txt` | Pins the tested isolated runtime including Windows timezone data. |
| `skills/productivity/job-apply/SKILL.md` | Updates the staged application recipe for authoritative context, semantic budgets and owned control flow. |
| `tests/jobbot_v1/test_document_timing_gaps.py` | Regression coverage for document timing gaps. |
| `tests/jobbot_v1/test_documents_assessments.py` | Regression coverage for documents assessments. |
| `tests/jobbot_v1/test_field_context_ordering.py` | Regression coverage for field context ordering. |
| `tests/jobbot_v1/test_history_archive.py` | Regression coverage for history archive. |
| `tests/jobbot_v1/test_learning_catalogue.py` | Regression coverage for learning catalogue. |
| `tests/jobbot_v1/test_operator_context_versions.py` | Regression coverage for operator context versions. |
| `tests/jobbot_v1/test_operator_ui.py` | Regression coverage for operator ui. |
| `tests/jobbot_v1/test_owned_account_events.py` | Regression coverage for owned account events. |
| `tests/jobbot_v1/test_owned_mail_protocol.py` | Regression coverage for owned mail protocol. |
| `tests/jobbot_v1/test_resource_protocol.py` | Regression coverage for resource protocol. |
| `tests/jobbot_v1/test_runtime_budgets_targets.py` | Regression coverage for runtime budgets targets. |
| `tests/jobbot_v1/test_settings_effects.py` | Regression coverage for settings effects. |
| `tests/jobbot_v1/test_settings_views.py` | Regression coverage for settings views. |
| `tests/jobbot_v1/test_stage3_review_closeout.py` | Regression coverage for stage3 review closeout. |
| `tests/jobbot_v1/test_strategy_policy.py` | Regression coverage for strategy policy. |
| `tests/jobbot_v1/test_timing_reports.py` | Regression coverage for timing reports. |
| `tests/jobbot_v1/test_worker_context_gaps.py` | Regression coverage for worker context gaps. |
| `docs/jobbot-v1/EXECUTION_PLAN.md` | Records the current reviewed checkpoint and the remaining authorization-dependent gates. |
| `docs/jobbot-v1/README.md` | Links the implementation evidence without rewriting the original specification. |
| `docs/jobbot-v1/REQUIREMENT_TEST_MAP.md` | Points the historical planning map to the final current acceptance ledger. |
| `docs/jobbot-v1/WORKER_PROTOCOL.md` | Documents semantic field context, namespace rules and operator-only archival. |
| `docs/jobbot-v1/ACCEPTANCE_LEDGER.md` | Accounts for all 34 required core IDs and explicitly separates local evidence from pending live cases. |
| `docs/jobbot-v1/STAGE3_EVIDENCE.md` | Records reviewed functionality, red/green fixes and final complete regression results. |
| `docs/jobbot-v1/STAGE4_EVIDENCE.md` | Records actual native/UI scenarios, cleanup, harness issues and acceptance boundaries. |
| `docs/jobbot-v1/WINDOWS_RUNBOOK.md` | Provides reviewed activation, explicit pilot scope and nondestructive rollback instructions. |
| `docs/jobbot-v1/RELEASE_MANIFEST.json` | Identifies the exact source tree and hashes the reviewed changed files; disallows deployment claims. |
| `docs/jobbot-v1/CHANGED_FILES.md` | Lists every changed source/test/document with a one-line summary. |

Unchanged future rollout plan: `docs/jobbot-v1/LATER_UBUNTU_ROLLOUT.md`. No Ubuntu action was taken.
