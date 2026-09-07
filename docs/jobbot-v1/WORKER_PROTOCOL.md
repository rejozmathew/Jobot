# Agent-neutral worker protocol v1

This is an implementation contract, not evidence of live portal success. `Service` remains the single transaction boundary over existing jobs, attempts and company account tables. No internal agent loop or alternative autofill framework is introduced.

## Roles and connection
- Bind only to loopback. Each connection supplies `Authorization: Bearer <local credential>` and `X-JobBot-Instance: <exact id>`; never place credentials in URLs, browser localStorage, ordinary logs or committed settings.
- Separate operator credentials and worker credentials bound to a worker ID. Operator controls policy, identity, intake eligibility, run requests and reconciliation; worker claims only after accepting a run and reporting capabilities. Operator credentials do not impersonate a worker.
- No browser Origin or a verified same-origin local UI is accepted; cross-origin callers are rejected. Unknown methods and unexpected arguments fail closed. Diagnostics never echo raw request data or secrets.
- `POST /v1/<operation>` carries named service arguments directly. This is a static operation registry, never arbitrary `getattr` execution. `GET /v1/health` is authenticated.

## Lifecycle
1. Operator intakes canonical requisitions with provenance and records explicit eligibility. Unassessed/excluded jobs cannot be claimed.
2. `request_run` freezes ordered membership, candidate identity and settings, with an idempotent request ID. State is `awaiting_worker` until a real worker accepts.
3. `accept_run` supplies worker/session IDs, protocol version, skill version, browser-profile identifier, actual provider/model and telemetry capability. A declared capability is not proof of successful live provider routing; integration records that separately.
4. `claim` atomically obtains one job and the browser lease. Response snapshots identity facts, settings, versions and fencing generation. Both DB job ownership and browser ownership must be free. Keep the same conversation across the batch by default.
5. Worker records action start/end automatically through its host adapter; semantic progress is independent from heartbeat. Every action keeps its start-time attempt ID. Late completion stays in that attempt's history and cannot advance the next job.
6. `submission_intent` precedes any allowed irreversible submit. Review/development mode rejects live submission. A post-intent timeout becomes `submission_unknown`, never a blind retry.
7. `finish` requires a recognized outcome and evidence for success. Quiescence is checked against pending actions and extension-writer state, not merely a boolean assertion. Exact retries are idempotent; conflicts/stale owners rejected.
8. Claim next only after the prior job is terminal and browser ownership released. No automatic lease stealing on expiry. Crash/expiry/unknown submission requires explicit operator reconciliation with evidence.

## Controls
`pause`/`stop` first become requested. The adapter blocks new actions and waits for dispatched calls and autonomous extension activity to end (or explicitly proves the owned browser stopped). Only then acknowledge. Paused leases remain owned and heartbeat continues. Stop acknowledgement prevents later claims; finish records the terminal attempt. UI must distinguish requested versus acknowledged and worker alive versus useful progress.

## Accounts and verification mail
Accounts are scoped by explicit candidate identity plus portal namespace, not employer name. Metadata includes protected credential references only. Pending/ambiguous registration is reconciled, not recreated. Account confirmation survives a failed application. Legacy account identity is never silently reclassified.

Mail correlation operates on request metadata: exact recipient, sender, purpose, namespace and bounded time window. It returns a message identifier, not an OTP/body. Multiple matches are ambiguous. This local matcher does not prove connector identity, sender authenticity, mailbox scope or successful live code extraction; those remain authorized integration tests.

Account context, worker account events and mail requests share one job-bound resolver: verified namespace/requisition evidence preserves tenant paths; otherwise an exact operator-verified alias may resolve the job host. Unverified metadata never grants a tenant. New worker account mutations and mail requests are fenced within the same transaction. Completed attempts permit only exact cached account-request replay; novel late observations require operator reconciliation and cannot overwrite a newer account record.

## Semantic field timing and targets
`event` type `field_context` carries stable `page`, `field`, `category` identifiers, never raw field values. The native `milestone` operation forwards that semantic event. Every `action_start` captures the context; `action_end` associates automatically measured duration with it. Field limits are cumulative across tools for the same context; unknown measurements block rather than count as zero. Empty context or verified navigation/field completion clears context. Without semantic context, responses expose `coarse_only` and retain attempt/no-progress limits. Merely changing context is not verified progress.

Target binding uses the full canonical job identity (including identity-bearing query parameters), stored as a separate identity key from the safe display URL. A hostname/account alias alone does not prove requisition ownership. Alternate origins require an explicit verified job URL identity; only the same-origin conventional `/apply` child with unchanged identity query is implicit. Unknown redirects are reconciliation work, not an excuse to select the nearest matching tab.

Reports and operator views derive uncertainty from unfinished/unmeasured actions and expired, quarantined or mismatching ownership. `completed_at` remains null after a crash; displayed wall time is not a claim of continuous execution.

## Durability and data safety
- SQLite `BEGIN IMMEDIATE`, independent connections, versioned additive migrations, durable browser generation and immutable event rows.
- Existing history is not an execution queue to reset. Applied suppression is global to a requisition, independent of active email.
- New development instances require absolute explicit paths and exclusive creation. Preview and verified-copy migration/backup never overwrite source or destination. Live data migration remains separately authorized.
- Raw model thoughts, tool args/results, mail, passwords, OTPs and cookies do not belong in ordinary event storage. Allowlisted semantic payloads are sanitized before DB or spool writes.

## Implementation status
Core services, authenticated HTTP/client/CLI, native Hermes adapter/plugin and operator/resource services are implemented. See the current stage evidence and acceptance ledger for independently reviewed source and actual execution results. Local/native fixture success is not official Simplify, live employer, or live mailbox acceptance.
