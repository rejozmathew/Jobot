# Hermes-to-JobBot connection

## Current local session route — September 2026

Ordinary Hermes uses the canonical repository skill and the selected ignored
runtime-config pointer. From the actual checkout, its terminal executes:

```text
.venv/Scripts/python.exe -m job_applier.application_runtime start <job-url>
.venv/Scripts/python.exe -m job_applier.workday_fast session <returned-session-id> --seconds 60
```

The CLI reads HERMES_SESSION_ID; if the installed harness does not export it,
pass --driver-id with that conversation's actual ID. No JobBot API token or
dashboard is required. This does not spawn another application model.
The selected configuration supplies candidate, resume, browser pool and private
credential/mail references. Read [APPLICATION_RUNTIME.md](APPLICATION_RUNTIME.md)
for the authoritative lifecycle, call sequence, configuration and helper map.

Native jobbot convenience is optional. Existing integrations/hermes_jobbot loads
PluginController using plugin settings app_repo and app_config. With local config,
start/browser/fast_forward/pause/stop/attach/retry call the same shared runtime and
record model/provider/effort observed through native hooks. Missing model evidence
stays unknown. The portable CLI works without installing this plugin globally.
Never change the ordinary conversation's configured model or billing route merely
to satisfy a runtime check. Canonical job-apply is v0.4.0, Workday v0.2.0.

## Historical HTTP credential repair (superseded for local startup)

Everything below describes the earlier HTTP compatibility path and its historical
verification. It is retained as evidence, not an ordinary local startup checklist.

**Later status:** Authentication succeeded after this fix, but resumed execution subsequently failed on browser connectivity and ownership/lease recovery. The configured managed service was also unreachable during the later diagnosis. See [REVIEW_HANDOFF.md](REVIEW_HANDOFF.md) for evidence and unknowns. The historical health checks below do not imply that either process is currently running.

## User-facing goal

An ordinary Hermes conversation accepts a job URL and executes through the repository's shared application helpers and managed tracking. The user should not export service tokens, paste secrets into prompts, open the dashboard, or launch another worker conversation merely to authenticate.

This change repairs **internal service authentication for the portable CLI**. It does not install a native `jobbot` tool in every Hermes runtime or prove an end-to-end live application.

## What failed, and why

The managed JobBot launcher supplies worker/operator tokens in its child-process environment. An ordinary Hermes chat's shell did not inherit `JOBBOT_PILOT_WORKER`. The native JobBot tool was also absent, and the documented CLI fallback previously used only `os.environ`. Duplicate checks could pass while execution remained unauthenticated.

The missing token is **not** a Workday password, mailbox credential or model-provider key. It is a local JobBot API credential. The existing private JSON store already held separate operator and worker values; no additional account or new secret was needed.

## Connection path

```text
ordinary Hermes conversation (same thread)
  -> repository skill
  -> terminal: existing managed CLI / workday_fast advance
  -> credential(name, selected configuration)
       1. existing launcher environment, if supplied
       2. exact named private JSON reference, if explicitly configured
  -> loopback managed API, instance + role validation
  -> existing managed queue/ownership/tracking
```

No separate LLM is launched by this transport. Workday filling still uses the existing Simplify supervisor and exact owned target. Operator intake and worker execution are different API roles, even when coordinated from the same chat.

### Explicit configuration, not secret discovery

The selected private runtime configuration may contain this optional mapping:

```json
{
  "operator_token_env": "JOBBOT_OPERATOR_TOKEN",
  "worker_token_env": "JOBBOT_WORKER_TOKEN",
  "credential_files": {
    "JOBBOT_OPERATOR_TOKEN": {
      "path": "<absolute-path-to-private-auth.json>",
      "key": "operator"
    },
    "JOBBOT_WORKER_TOKEN": {
      "path": "<absolute-path-to-private-auth.json>",
      "key": "worker"
    }
  }
}
```

`*_token_env` and `--token-env` retain their existing names for compatibility. They now select a named credential: environment first, explicit file fallback second. The JSON configuration above contains references only. The secret JSON file remains private, excluded from Git, and must be accessible only to the intended OS user/service.

Rules:
- Only the selected configuration's exact name/path/key is consulted. No filesystem hunt, implicit alternate store, default credential, or borrowing of another role's token.
- Paths must be absolute; unreadable/malformed files, missing keys, non-string/empty values and oversized stores fail with `credential_unavailable`.
- Existing environment credentials keep precedence. An invalid/stale environment value is not silently replaced after server rejection.
- Tokens stay in process memory and the Authorization header to the existing loopback-only client. They are not printed, copied to source, passed on command lines, exported globally or written into application checkpoints.
- Server instance checks, worker-role binding, ownership fences, model checks, pause/stop and duplicate suppression are unchanged. Having a credential does not authorize bypassing them.

## Ordinary Hermes procedure

1. Resolve the repository and explicit private runtime config from the user's/project context. Read canonical `job-apply` and Workday instructions.
2. Run `workday_fast doctor`. Its `worker_token_available` means a local named credential resolves; it is **not** server-authentication proof.
3. Run the read-only worker health command. `--token-env` takes the name from `worker_token_env`, never its value:

```text
<python> run_applier.py managed call --config <absolute-config> --token-env <worker_token_env-name> --operation health
```

Through Hermes, use `terminal(command="...", workdir="<repository>")`. Confirm the returned instance and database match the chosen config. Operator-side commands use the configured operator reference; use operator permission only for user-authorized operator operations.

4. Proceed with the existing managed intake/accept/claim and exact-target flow, then `job_applier.workday_fast advance`. Use actual API signatures; native tool labels like `next` are not always the same as API names (`claim`). Preserve the current conversation—do not start `managed_hermes_worker` or `native_hermes_session` merely to obtain credentials.
5. If a different blocker appears, report that exact blocker. Do not rotate keys, weaken role checks, clear old runs, alter settings/model, or resubmit to make authentication appear successful.

No Hermes restart or manual environment export is required for the **portable CLI credential fix**, because it reads the selected config in each subprocess. A service restart may still be needed for unrelated server-code changes; successful health does not prove a running process reloaded all source files.

## Files and consumers

| File | Responsibility / change |
|---|---|
| `job_applier/managed_cli.py` | Shared named credential resolver; generic managed calls can use configured file references. Existing environment-only callers remain compatible. |
| `job_applier/application_runtime.py` | Doctor reports credential availability through the same resolver rather than inspecting only the shell environment. |
| `job_applier/workday_fast.py` | Portable `advance` authenticates through that resolver; no worker/model is spawned. |
| `tests/jobbot_v1/test_configured_credentials.py` | Environment-free resolution, precedence, failures, role-name isolation, safe output, doctor and CLI-entry regression tests. |
| Selected private `native-app.json` | Explicit references to existing worker/operator entries in its sibling private auth store; no secret values added. |
| `skills/productivity/job-apply/references/internal-service-auth.md` | Short agent-facing instructions pointing to this canonical explanation. |
| `skills/productivity/job-apply/SKILL.md` | Discovers the reference and clarifies fallback authentication. |
| `docs/jobbot-v1/WORKDAY_NEXT_RUN.md` | Replaces the old environment-only bootstrap instruction with ordinary-shell health verification. |
| `docs/jobbot-v1/APPLICATION_RUNTIME.md` | Links this connection decision as part of the shared helper map. |
| `docs/jobbot-v1/README.md` | Makes this decision discoverable from the project documentation index. |

This is shared transport/authentication, **not Workday-specific code**. `workday_fast` is one consumer. Candidate portal credentials and mailbox access remain separate existing helpers.

## Verification and scope

- The reported failure was reproduced with absent worker environment. The added tests first failed; after implementation the initial focused credentials/managed-CLI/runtime run returned **20 passed**.
- Read-only health against the already-running configured service succeeded for both worker and operator references while the worker environment was still absent.
- The actual documented `run_applier.py managed call ... --token-env JOBBOT_PILOT_WORKER --operation health` invocation succeeded from an ordinary tool shell.
- Doctor now reports `worker_token_available: true` for that selected configuration without an environment export.
- A read-only operator-view request using the worker credential was rejected with `role_forbidden`, verifying the fallback did not collapse role separation.
- Final managed suite: **508 passed**, with two pre-existing dependency deprecation warnings. JUnit evidence: ignored `artifacts/jobbot-v1-private/hermes-connection-tests.xml`.
- One bounded independent read-only review found no blockers in the credential resolver and callers. `git diff --check` passed; the selected auth store and runtime config were confirmed Git-ignored.
- Health confirms the intended managed instance/database, not job acceptance or form execution. No real application was claimed/submitted, no browser was driven, and no job outcome/history was altered for this verification.
- Only the selected local config was wired; no other Hermes profile, token store, global environment or service credential was changed.

## Known boundaries and future consolidation

This is an interim local-desktop bridge, not the final application architecture:

1. **One stable application entry point.** Consolidate intake, candidate selection, document selection, run creation, actual-runtime verification, claiming and execution into a documented API/command instead of requiring a harness to compose raw protocol calls.
2. **One runtime descriptor.** Consolidate pilot/app/native config copies, transient service endpoints and launcher environment references. Keep one explicit instance/database authority and publish server readiness without exposing tokens.
3. **Credential lifecycle.** Move plaintext private JSON into the chosen OS keyring/credential broker if stronger local isolation is required. Consider short-lived session-scoped worker tokens. File references currently trust the same OS-user boundary; they are not per-chat isolation.
4. **Harness adapters.** Make native Hermes registration optional and use the same underlying entry point as CLI/dashboard. A native plugin or separate-worker launcher still has its own environment/setup requirements; this fix does not silently install/enable them.
5. **Dashboard parity.** Verify a running worker and loaded source version before presenting a request as execution. Dashboard Start currently requests a run and can wait for a worker. Its worker path is separate from the ordinary-chat path.
6. **Launcher/skill compatibility.** The existing `native_hermes_session.py` checks that the active profile skill resolves directly to the canonical skill; the current profile resolves to a thin entry instead. Reconcile that check before certifying the separate dashboard/native-worker route. It is not invoked by this CLI connection fix.
7. **Startup/version checks.** Distinguish configured, authenticated, worker-ready, claimed and browser-ready states. Do not infer loaded in-memory code from a source hash read from disk.
8. **Retirement criteria.** Delete interim credential-file support only after the replacement supports ordinary shells, preserves role separation and passes the same environment-free regression/health tests. Migrate references deliberately; do not delete private runtime directories containing databases/history as cleanup.

## Rollback

Remove only the selected config's `credential_files` references to return it to environment-only resolution. Preserve the existing auth store and database. The resolver is additive, so old launcher environments continue working. Source rollback must preserve unrelated dirty work. Never compensate for a failed token by changing submission outcomes or disabling API authentication.
