# Agent-neutral worker protocol v1 (Stage 1 draft)

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

## Durability and data safety
- SQLite `BEGIN IMMEDIATE`, independent connections, versioned additive migrations, durable browser generation and immutable event rows.
- Existing history is not an execution queue to reset. Applied suppression is global to a requisition, independent of active email.
- New development instances require absolute explicit paths and exclusive creation. Preview and verified-copy migration/backup never overwrite source or destination. Live data migration remains separately authorized.
- Raw model thoughts, tool args/results, mail, passwords, OTPs and cookies do not belong in ordinary event storage. Allowlisted semantic payloads are sanitized before DB or spool writes.

## Implementation status
Core local services, ownership, telemetry, controls and account metadata have passing synthetic tests. Authenticated HTTP/client/CLI/data tooling are the next slice. Installed Hermes integration, actual Simplify and live mail remain pending; see the requirement map and stage evidence ledger.
