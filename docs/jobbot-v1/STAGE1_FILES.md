# Stage 1 authored file inventory

Paths are relative to the implementation worktree. This covers source/specification/test changes since the approved baseline; Stage 2 adapter test preparation is excluded. Environment dependencies, caches, generated review snapshots and synthetic data are not source files. No active job-apply or harvest skill was modified.

| File | Change |
|---|---|
| `docs/jobbot-v1/STAGE1_FILES.md` | Exact authored source inventory and private/tooling scope notes. |
| `docs/jobbot-v1/ACCEPTANCE_AND_DATA.md` | Preserved copy of the user-provided approved specification; original stays untouched. |
| `docs/jobbot-v1/EXECUTION_PLAN.md` | Living execution plan documentation and evidence. |
| `docs/jobbot-v1/HERMES_INTERFACE.md` | Living hermes interface documentation and evidence. |
| `docs/jobbot-v1/IMPLEMENTATION_PROMPTS.md` | Preserved copy of the user-provided approved specification; original stays untouched. |
| `docs/jobbot-v1/LATER_UBUNTU_ROLLOUT.md` | Preserved copy of the user-provided approved specification; original stays untouched. |
| `docs/jobbot-v1/PRD.md` | Preserved copy of the user-provided approved specification; original stays untouched. |
| `docs/jobbot-v1/README.md` | Preserved copy of the user-provided approved specification; original stays untouched. |
| `docs/jobbot-v1/REQUIREMENT_TEST_MAP.md` | Living requirement test map documentation and evidence. |
| `docs/jobbot-v1/REVIEW_NOTES.md` | Living review notes documentation and evidence. |
| `docs/jobbot-v1/SOURCE_NOTES.md` | Preserved copy of the user-provided approved specification; original stays untouched. |
| `docs/jobbot-v1/STAGE1_EVIDENCE.md` | Living stage1 evidence documentation and evidence. |
| `docs/jobbot-v1/WORKER_PROTOCOL.md` | Living worker protocol documentation and evidence. |
| `job_applier/application_tracker.py` | Fail-closed legacy tracking writes; existing read-only history remains available. |
| `job_applier/database.py` | Managed-instance detection without changing legacy ORM histories. |
| `job_applier/db_queue.py` | Shared managed intake/read support; legacy mutation/startup-cleanup protection. |
| `job_applier/managed.py` | Shared intake, identity, fixed batches, atomic claims, leases, suppression and completion services. |
| `job_applier/managed_accounts.py` | Portal/identity account metadata and time-bounded verification-mail correlation. |
| `job_applier/managed_api.py` | Authenticated loopback protocol with instance, worker and input-type enforcement. |
| `job_applier/managed_cli.py` | Explicit managed subcommands; no legacy environment/profile fallback. |
| `job_applier/managed_client.py` | Agent-neutral HTTP client with explicit instance and credential binding. |
| `job_applier/managed_continuity.py` | Durable checkpoints and controlled batch-session resume. |
| `job_applier/managed_data.py` | Read-only previews, non-overwriting backup and verified-source migration copies. |
| `job_applier/managed_events.py` | Immutable events, action timing, heartbeat/progress distinction and cooperative controls. |
| `job_applier/managed_fake_worker.py` | Synthetic non-Hermes worker exercising the shared HTTP protocol without portals. |
| `job_applier/managed_identity.py` | Conservative URL keys and verified alias relationships for duplicate suppression. |
| `job_applier/managed_migrations.py` | Additive migrations through version 7, including historical-success suppression. |
| `job_applier/managed_redaction.py` | Allowlisted event payloads and recursive credential-field rejection. |
| `job_applier/managed_shared.py` | Shared protocol primitives and guarded legacy writer decorator. |
| `job_applier/runner.py` | Block legacy execution on managed instances and lazily import the opt-in legacy agent. |
| `requirements-jobbot-lock.txt` | Pin the isolated Windows development dependency set. |
| `run_applier.py` | Route managed commands before legacy .env/DB/browser imports. |
| `tests/jobbot_v1/test_accounts.py` | Accounts slice API tests (expected RED). |
| `tests/jobbot_v1/test_compatibility.py` | Compatibility acceptance tests for legacy components against managed databases. |
| `tests/jobbot_v1/test_continuity.py` | Acceptance tests for managed run continuity, checkpoints, and multi-session resumption. |
| `tests/jobbot_v1/test_core.py` | Offline JobBot acceptance — no credentials, employers or live browsers. |
| `tests/jobbot_v1/test_data_tools.py` | Data tools acceptance tests for JobBot managed fresh starts, migrations, and backups. |
| `tests/jobbot_v1/test_events.py` | Regression coverage for events. |
| `tests/jobbot_v1/test_fake_worker.py` | Protocol regression tests for fake worker. |
| `tests/jobbot_v1/test_final_review_regressions.py` | Narrowly scoped regression tests from primary decision brief. |
| `tests/jobbot_v1/test_managed_cli.py` | Acceptance tests for managed CLI entrypoint contracts. |
| `tests/jobbot_v1/test_ownership.py` | Regression coverage for ownership. |
| `tests/jobbot_v1/test_protocol.py` | Protocol acceptance tests for JobBot managed API and client. |
| `tests/jobbot_v1/test_protocol_types.py` | Protocol type enforcement and requisition query token acceptance tests. |
| `tests/jobbot_v1/test_review_identity.py` | Reviewer regression tests for JobBot identity deduplication and migration contracts. |
| `tests/jobbot_v1/test_review_lifecycle.py` | Reviewer regression tests for JobBot lifecycle and control contracts. |
| `tests/jobbot_v1/test_review_security.py` | Targeted security regression tests for independent review S1/S2 (expected RED). |
| `tests/jobbot_v1/test_safety_regressions.py` | Safety regression tests for jobbot_v1 contracts (expected RED). |

## Private and tooling-only files

- `artifacts/jobbot-v1-private/RUNTIME_HANDOFF.md`: verified ignored runtime/source knowledge, no credentials or mailbox contents.
- The same ignored directory contains runtime inventory/provider/connector evidence, test-only Antigravity briefs and responses, frozen review manifests and local protocol smoke scripts/results. Synthetic DB/configs are retained there; smoke API credentials were removed after server shutdown. These are not release content.
- An active-profile general `requesting-code-review/SKILL.md` safety note was amended to prohibit masked test exits, destructive dirty-work baselines, broad staging and delegated production fixes. This procedural tooling change is outside the product worktree. Application/discovery skills, agent configuration, candidate profiles, real history and browser data were not changed.
