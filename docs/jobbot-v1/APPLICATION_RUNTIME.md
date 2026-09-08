# Application runtime: ownership, helper map, and rationale

For the ordinary-Hermes connection, internal API credentials, exact changed files and future consolidation plan, see [HERMES_CONNECTION.md](HERMES_CONNECTION.md). This is shared transport, not Workday logic.

This is the maintained architecture/cleanup map for managed applications. It separates shared policy, platform mechanics, harness transport and private data. It does **not** claim every historical helper is obsolete or that fixture tests prove live ATS support.

## Decisions

1. **Repository-owned procedures.** `skills/productivity/job-apply/SKILL.md` owns common application policy; `skills/productivity/workday-simplify/SKILL.md` owns Workday specifics. Any harness can read these Markdown files. Hermes is a thin entry point, not the source of the procedure.
2. **One primary managed database.** New intake, attempts, account events, assets, submission ledger and outcomes go through the configured JobBot service and its explicit absolute `db_path`. The checkout name does not choose a database. Health instance ID and database path must agree before the fast runner connects to a browser.
3. **Old database is read-only history.** `legacy_history_paths` supplies duplicate/uncertain-attempt suppression. Never dual-write, copy tables, manufacture managed attempts for old submissions, or silently change old statuses. A missing configured history source fails closed instead of creating an empty SQLite file.
4. **Credentials are references, not a database migration.** The private runtime can deliberately reference an existing private credential profile outside the checkout. That is independent of tracking ownership. No password or profile copy is committed to Git. A future credential-store move is a separate explicit operation.
5. **Simplify owns bulk filling.** The no-PDF-extraction/no-career-reconstruction policy is shared across ATS platforms. Uploading the approved PDF is allowed; extracting its text during a form run is not. Profile repair belongs to a separate preparation task.
6. **Forward-first, not perfection-first.** After proven writer quiescence, enabled Continue takes precedence over nonblocking review warnings. One initial autofill and one retry per Workday step; actual required blockers are exceptions, not a reason for a whole-form audit.
7. **One fast path, two transports.** Native `jobbot fast_forward` and `python -m job_applier.workday_fast advance` call the same `advance()` function. No new agent engine, daemon, parallel-tab pool, or database was added.

## Helper map

| File/component | Scope | Why it exists / consumer | Verification and cleanup boundary |
|---|---|---|---|
| `skills/productivity/job-apply/` | Shared procedure | Identity, documents, bounded repairs, accounts/mail, submission policy; read by every harness | Keep common rules here, not copied into every ATS skill |
| `skills/productivity/workday-simplify/` | Workday procedure | Authentication stages, same-URL steps, fast-runner actions and exception handling | New-run prompt loads it explicitly |
| `integrations/hermes_jobbot/skills/job-apply/` | Hermes discovery only | Thin installed skill pointing at repository procedure; no separate filling policy | Repository relocation needs installer/config pointer update, not skill duplication |
| `job_applier/application_runtime.py` | Shared runtime/data | Explicit config/instance validation and read-only legacy duplicate checks; used by doctor and fast entry point | `test_application_runtime.py`; does not migrate or write history |
| `job_applier/cdp_client.py` | Shared browser transport | Exact-target CDP; `evaluate_function` passes structured args via a current-document remote object instead of regex inference | `test_cdp_evaluate_function.py`; legacy `evaluate` remains compatible |
| `browser_helpers/simplify_observe.js` | Shared extension observation | Recognizes Start/Autofill/Continue/account/Submit controls, activity and review count; returns refs and fingerprints, not field values | Existing boundary/start tests plus fast-policy tests; observation is not submission evidence |
| `browser_helpers/simplify_click.js` | Shared extension actuation | Clicks an observed ref after URL/page and enabled-control checks | Returns `status: clicked`; caller still verifies the result |
| `job_applier/simplify_boundary.py` | Shared bounded primitive | Existing observation/click wrapper; opt-in `fast=True` preserves conservative callers while supporting forward-first decisions | `test_simplify_boundary.py`, `test_simplify_fast_policy.py`; not the whole Workday runner |
| `browser_helpers/workday_observe.js` | Workday metadata | Current section/stepper, native buttons, actual errors, auth selectors, approved attachment and matching application row | `test_workday_dom.py` executes shipped JS in jsdom; no resume field reconstruction |
| `browser_helpers/workday_click.js` | Workday native action | Unique observed native Continue/Submit ref; fails if DOM/URL/step became stale | Used only after server writer/ownership checks |
| `job_applier/workday_fast.py` | Workday supervisor, harness-neutral | Bounded observe/act/wait loop, compact exception reports, retry state, metrics, authorized submission and employer verification | Policy, plugin and real-managed-API fixture integration tests |
| `job_applier/hermes_plugin.py` | Hermes transport | `fast_forward` forwards existing claimed ownership to the portable runner; clears adapter attempt after verified finish | `test_workday_fast_plugin.py`; no alternate form logic |
| `job_applier/managed_runtime.py` + `managed_identity.py` | Shared safety, narrow Workday read extension | Server-owned browser observations and exact target identity; Workday Candidate Home is allowed for confirmation reads, not form writes | Confirmation-scope tests; other tenant/site/job remains out of scope |
| `job_applier/managed_credentials.py` | Shared private authentication | Existing configured credentials helper; takes observed unique native refs and verifies committed values | Preserve existing auth fixes; never log candidate secret values |
| `job_applier/managed_hermes_worker.py` | Existing managed worker | Broader pre-existing worker/legacy integration path; still uses shared boundary | Not replaced or deleted in this change. Do not confuse it with the new portable fast runner |
| `job_applier/native_hermes_session.py` | Existing Hermes launcher | Establishes native tool/hooks, observed runtime metadata and tracking | Pre-existing local work preserved; no worker launched by `advance` |
| `job_applier/hermes_gmail.py` | Existing mailbox bridge | Native Gmail capability for approved verification | Not Workday-only; not part of autofill polling |

Paths under `browser_helpers/` above are relative to `job_applier/`. Existing helpers outside this inventory have **not** been declared unused. Before cleanup, inspect static call sites and recent attempt action events, then remove only a helper with no active callers and tests proving its replacement. Do not remove historical compatibility solely because the new runner exists.

## Runtime configuration and lifecycle

Use an explicit private JSON config containing the existing service settings plus:

```json
{
  "instance_id": "<configured-instance>",
  "db_path": "<absolute-managed-database-path>",
  "base_url": "http://127.0.0.1:<service-port>",
  "worker_id": "<configured-worker>",
  "worker_token_env": "<existing-environment-reference>",
  "browser_profile": "<verified-simplify-profile>",
  "cdp_url": "http://127.0.0.1:<verified-browser-port>",
  "spool_dir": "<absolute-private-spool>",
  "legacy_history_paths": ["<absolute-read-only-legacy-database>"]
}
```

These are placeholders, not a runnable replacement for an existing config. Retain its candidate, credential/mail references and actual requested model/provider settings. Do not infer the browser from port 9222, use cwd-relative SQLite paths, or change models to satisfy an acceptance gate.

Run through your harness shell (`terminal` in Hermes):

```text
<python> -m job_applier.workday_fast doctor --config <absolute-config> --url <job-url>
```

Doctor is read-only. It reports primary path/instance, CDP/profile, old-history matches, open historical runs and whether the worker token reference is present in that process. It is not proof the service is current or that a browser extension is supported. Start/reload the configured service and native integration from this checkout before the benchmark so in-memory modules are current. Preserve/reconcile existing ownership; never reset the database to hide it.

### Intake and transport

The fast runner intentionally does not select a candidate, approve a role, reserve arbitrary work or impersonate a model. The existing app/operator flow does intake → eligibility → document selection → request_run. The selected harness does accept_run → claim → bind_target under the actual configured capability identity. The native Hermes tool supplies ownership automatically after `accept`/`next`.

A non-Hermes harness uses the existing same-service CLI:

```text
<python> run_applier.py managed call --config <absolute-config> --token-env <configured-reference-name> --operation <actual-protocol-operation> --payload <JSON-or-@private-file>
```

Use `job_applier/managed_api.py` for the operation schema. Operator and worker credentials are distinct: intake/request use the existing operator flow; browser execution uses the assigned worker. No secrets in command arguments or tracked files. The CLI launcher/config is deployment glue; the workflow and fast runner do not depend on Hermes tools.

Once a specific attempt is claimed:

```text
<python> -m job_applier.workday_fast advance --config <absolute-config> --attempt-id <id> --fence <fence> --target-id <observed-id> --seconds 60
```

Equivalent native call: `jobbot(operation="fast_forward", parameters={"target_id":"<observed-id>","seconds":60})`.

The loop holds one local CDP connection per bounded call. The managed service still does its own independent read-only browser observation before writes; this is deliberate fencing, not a claim of zero reconnects. It reads pause/stop each tick, never clears busy state based on time alone, and never retries Submit after recorded intent.

### Exceptions and state

- `authentication_required`: returns selectors, never credential values; refresh server-side `browser_observe` before the existing fenced credential helper/native sign-in action, then record confirmed account state. Stable observed account controls can settle the preceding Start action; generic login/missing/unknown signals cannot clear an active writer.
- `blocked`: repair a demonstrated required blocker or report it; no career/PDF investigation.
- `waiting`: bounded wait ended; counters persist. Reinvoke only while existing attempt/no-progress budgets permit.
- `ready_for_review`: review-mode result; not submitted.
- `applied`: native requisition row confirmed and managed outcome written; completed tab retained. No second finish/submit.
- `submission_unknown`: observation only; preserve the same target and reconcile.

Private `fast-<hash>.json` files contain step/counters/booleans/metrics; `.lock` prevents concurrent runners for the same ownership/target. They are not a second outcome database. A crash lock requires verifying no live runner before removal. The database's submission intent remains the authoritative no-repeat guard even if a checkpoint is lost.

## Measurement and verification

Action durations are recorded under `workday_fast.<action>` through existing events. Checkpoint metrics contain polling, waits, elapsed helper time and click counts. The managed attempt duration is the wall-clock source. Model/tool overhead and user intervention counts require the harness transcript/telemetry; do not label helper time as end-to-end time. Full phase/model attribution is not invented when absent.

Focused tests cover shared decisions, shadow controls, auth activity, same-URL steps, quiescence, retry persistence, read-only Candidate Home, legacy suppression, plugin routing and the actual managed API through a temporary SQLite fixture. jsdom tests use the optional local test dependency under ignored artifacts; install it with `npm install --prefix artifacts/jobbot-v1-private/dom-test --no-save --no-package-lock jsdom` before running those tests.

The next live benchmark is intentionally separate: [WORKDAY_NEXT_RUN.md](WORKDAY_NEXT_RUN.md). Target under ten minutes, not a guaranteed SLA. No engineering changes or new helper generation inside the application run.
