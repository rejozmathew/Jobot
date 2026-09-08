# Windows operator runbook

## Current local startup — September 2026

Use the existing checkout and .venv/Scripts/python.exe. The ignored
artifacts/jobbot-v1-private/runtime-config.json selects the absolute native-app.json
for windows-supervised-pilot-rejo. Application authorization for this engineering
acceptance is explicit; no further per-edit/activation gate is introduced here.

```text
.venv/Scripts/python.exe -m job_applier.application_runtime doctor
.venv/Scripts/python.exe -m job_applier.application_runtime start <job-url> --driver-id <actual-conversation-id>
.venv/Scripts/python.exe -m job_applier.application_runtime status <returned-session-id>
```

Doctor is optional; start automatically validates history and launches/verifies
the assigned headed browser. Ordinary Hermes follows the repository skills in
its own conversation with the selected application model. No API token export or
running dashboard is required. Do not run native_hermes_session as a workaround.
The existing dashboard is http://127.0.0.1:60157; its private restart script is
artifacts/jobbot-v1-private/runtime_dashboard.py. It reads the same managed DB.

Migration makes a SQLite backup before additive schema 15. Keep active files on
the local machine. Prepare separate Simplify-authenticated profiles/endpoints;
never copy live profile/cookie state. Current provisioning and acceptance limits
are in [RUNTIME_SIMPLIFICATION_LOG.md](RUNTIME_SIMPLIFICATION_LOG.md).
The authoritative configuration/ownership/helper explanation is
[APPLICATION_RUNTIME.md](APPLICATION_RUNTIME.md).

## Historical explicit HTTP worker activation

The older instructions below concern isolated preview/HTTP worker deployment.
They do not require local sessions to use HTTP auth or shared-profile leases.

This source tree is a Windows engineering candidate. Do not point it at the original runtime history, enable it in an active Hermes profile, or start real applications merely because these commands exist. Real-browser/mail/portal checks have their own authorization gates.

## Isolated development instance
Run from the selected application checkout using its Python environment:

```text
<python> run_applier.py managed preview-new --db <absolute-new-db-path>
<python> run_applier.py managed init --db <absolute-new-db-path> --instance-id <unique-instance-id>
<python> run_applier.py managed serve --config <absolute-app-config.json>
```

`init` refuses existing files/sidecars and creates development/review defaults. It never copies a real profile or application history. Put runtime files in a verified ignored/private location. Do not copy live SQLite files with ordinary filesystem copying; use the backup command.

The explicit application configuration contains paths/endpoints and **credential environment-variable names**, not credential values:

```json
{
  "instance_id": "<unique-instance-id>",
  "db_path": "<absolute-new-db-path>",
  "base_url": "http://127.0.0.1:8000",
  "operator_token_env": "JOBBOT_OPERATOR_TOKEN",
  "worker_tokens_env": "JOBBOT_WORKER_TOKENS",
  "worker_token_env": "JOBBOT_WORKER_TOKEN",
  "worker_id": "windows-hermes",
  "browser_profile": "<explicit-profile-id>",
  "provider": "openai-codex",
  "model": "gpt-5.6-luna",
  "reasoning_effort": "low",
  "skill_version": "<verified-canonical-skill-version>",
  "spool_dir": "<absolute-private-outbox-directory>"
}
```

Provide independent strong local operator/worker credentials through the existing protected environment facility. The worker-token map is JSON mapping token values to worker IDs; never paste it into chat, the runbook, ordinary logs or Git. The application does not need a provider API key. Operator browser login uses its own local API credential and an opaque HttpOnly session cookie; it is unrelated to candidate portal passwords.

## Native Hermes worker (activation is a later approved action)
The staged package is `integrations/hermes_jobbot/`. The installed native loader expects `__init__.py` with `register(ctx)` and `plugin.yaml`. No Hermes core patch is needed. `PluginContext.get_config` reads plugin-relative values under the following **settings** subtree:

```text
hermes config set plugins.entries.jobbot-worker.settings.app_repo <absolute-application-checkout>
hermes config set plugins.entries.jobbot-worker.settings.app_config <absolute-app-config.json>
```

Run those only in the intended, authorized Hermes home/profile. Copy/install the reviewed package as `plugins/jobbot-worker` using the supported native plugin workflow; inspect `hermes plugins --help` for that installation's interface. Enable only after the correct instance, identity, browser profile, credential references and quiescence are verified. Do not replace the active skill in the middle of an application.

Validation command (already exercised with an isolated home during engineering):

```text
hermes plugins doctor <absolute-staged-plugin-directory> --ci
```

The current plugin binds to the actual observed model/provider and rejects an unverified or mismatching runtime. `openai-codex` must use the intended subscription route. No automatic API-key, paid-provider or different-model fallback is authorized. A configured tool is not the same as a worker that has accepted a run.

## Operator flow

### Explicit external application worker

The native application worker used by the supervised pilot is launched separately with the installed Hermes interpreter (not a fabricated dashboard worker):

```text
<installed-hermes-python> -m job_applier.managed_hermes_worker --config <absolute-app-config.json> --hermes-root <installed-hermes-source> --wait-seconds 60
```

Run it from this checkout only after code is frozen and the authorized dashboard request exists. It honors the request's frozen provider/model/effort and submission mode; the model must be Luna or Terra through `openai-codex`, without a paid fallback. For the current live-proven path select **one Greenhouse job**, the approved candidate and exact resume. Workday wizard navigation, account handoff, upload and confirmation in this new worker are **not accepted yet**; the older Workday handler's history does not satisfy that gate.

`attempt_report` and the attempt detail UI distinguish wall/phase time, model/tool time, measured native field actions, Simplify observations/residuals and problems/resolutions. These are different timing views, not values to add together. Simplify does not expose per-field timestamps; that attribution remains unknown. Historical missing field IDs are not backfilled.

The worker saves employer confirmation evidence before closing its exact owned target. Closure uses a browser-level CDP connection, never the page connection being destroyed; it checks the ownership fence first and confirms target absence before marking closed and finishing. Normal unsuccessful exits use the same cleanup. Unrelated/dashboard tabs and the shared browser process are not closed. `cleanup_pending` or `ledger_pending` requires operator attention; a verified submission is never downgraded or automatically retried just because cleanup failed. This is not a hard-crash/unattended watchdog.

### Dashboard sequence

1. Authenticate and inspect the displayed **instance ID and resolved DB path**.
2. Register/select the intended candidate through the controlled identity service. No identity is inferred from browser position or a different process's CWD.
3. Intake jobs; inspect external source/assessment data and policy compatibility. Intake alone does not authorize execution.
4. Explicitly approve eligibility, choose jobs, candidate and exact browser profile, then request a fixed batch. The UI shows `awaiting_worker` until an external worker accepts.
5. Give the worker the stable run ID. The native `jobbot` tool uses operation `accept`, then `next`; one claimed job is processed at a time in the continuing session.
6. Honor requested versus acknowledged controls, frozen policy and ownership fences. Unknown submission/writer state requires reconciliation, not a retry from a different profile.
7. Read the app timeline and versioned resources. Unassessed is not zero; registered, selected, upload-attempted and upload-confirmed documents are distinct.

## One CLI transport
The `managed` command name precedes its flags:

```text
<python> run_applier.py managed call --config <absolute-config> --operation health
<python> run_applier.py managed call --config <absolute-config> --operation view --payload {}
<python> run_applier.py managed call --config <absolute-config> --token-env JOBBOT_WORKER_TOKEN --operation attempt_report --payload <owned-attempt-json>
```

Payloads must use the actual operation signature; inspect source/help rather than inventing overloads or retrying malformed identifiers under different names. Tokens never belong in the payload or command arguments.

## Data safety and rollback

For additive history archival, use the authenticated operator operations `archive_preview(job_ids, instance_id)` then `archive_jobs(job_ids, instance_id, expected_preview_hash, backup_destination, reason)`. Supply the preview's exact hash and a new absolute backup path. The second operation rejects changed state, live ownership, pending selected work and existing archive records; it verifies an independent backup before adding immutable archive metadata. It does not rewrite jobs, attempts, account state, sources or submissions. Default views hide archived jobs; `view(include_archived=true)` exposes them. Archived jobs cannot be requested again. This is not a history-deletion command and is not permission to touch real data.

```text
<python> run_applier.py managed backup --source <source-db> --destination <new-backup-db> --instance-id <expected-instance>
<python> run_applier.py managed migrate-copy --source <source-db> --destination <new-instance-db> --instance-id <new-instance> --expected-source-sha256 <verified-source-hash>
```

Preview and preserve first. Use a new destination, read back integrity/schema/counts, and retain the original. Existing real workers must be quiescent before any shared-runtime integration. Rollback uses the previous reviewed code/skill version plus its compatible private configuration/database plan; never reset/clean the user's checkout or restore old data over newly verified submissions/accounts. Ubuntu rollout is a later, separately authorized task, not part of this Windows activation.
