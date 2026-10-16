# Interfaces and integrations

[Documentation index](README.md) · [Architecture](ARCHITECTURE.md)

## Local runtime interface

Optional company/title duplicate matching uses a separately configured LM Studio
embedding endpoint. Only company and role text is sent; cached vectors and
reversible matching decisions live in the managed database. It runs outside
application tools and database transactions. See
[Cross-source identity](jobbot-v1/CROSS_SOURCE_IDENTITY.md).

The existing Discord submission observer can also send a previous-day numerical
summary at 08:00 America/Chicago. It shares its existing sender, channel and
private receipt file; individual submission messages retain their current path.
See [Submission alerts](jobbot-v1/SUBMISSION_ALERTS.md#daily-numerical-summary).

`job_applier.application_runtime` is the portable entry for ordinary application
sessions. The Hermes `jobbot` tool is a convenience adapter around this interface;
another shell-capable harness uses the same canonical skills and private config.

The runtime supports `start`, `status`, `call`, `stop`, `pause`, `attach`, `restart`,
`retry`, `reconcile`, `doctor`, `sessions` and `answer_retries`. `call` takes the
session ID, operation and a JSON parameter object. The session resolves the owned
workspace and target. It is not an unscoped browser-control endpoint.

The application procedure and ATS operations are documented in
[job-apply](../skills/productivity/job-apply/SKILL.md) and its references. Workday's
session-scoped CLI is:

```text
python -m job_applier.workday_fast session SESSION_ID --seconds 60
```

That is a helper slice in an existing application, not a model launcher or a final
application budget. Helpers return to the executor for unfamiliar controls and
supported recovery. Do not add an independent application service for an ATS helper.

## Managed service and HTTP API

The same managed operations are accessible through an in-process `LocalClient` or
the optional FastAPI server. `managed_api.OPERATOR`, `WORKER` and `READS` define
the actual operation sets. `Service` methods define their argument contracts.

| Route | Purpose |
|---|---|
| `GET /` | Serve the operator dashboard and establish the local UI session |
| `GET /static/jobbot.js`, `/static/jobbot.css` | Serve tracked frontend assets |
| `GET /session` | Return the authenticated operator instance |
| `POST /login`, `/logout` | Compatibility login/session lifecycle |
| `GET /v1/health` | Authenticated instance health and source evidence |
| `POST /v1/{operation}` | Invoke a permitted managed service operation with a JSON body |
| `POST /v1/upload_asset` | Register an uploaded local resume/cover-letter asset |

Programmatic HTTP requests use `Authorization: Bearer …` and
`X-JobBot-Instance: …`. The local browser uses an HttpOnly session cookie and
the instance header. Operator and worker identities are separate. The tracked API
enforces loopback host and same-origin restrictions. OpenAPI/Swagger routes are
disabled; source method signatures and tests are the interface reference.

Example local read, requiring only a selected config and no HTTP token:

```text
python run_applier.py managed call --config /absolute/runtime.json --operation settings_view
```

For larger payloads, `managed call --payload @/absolute/payload.json` reads a JSON
object from a file. Avoid putting private answers or credentials in shell history.

Operator operations include intake, profile/settings, queue controls, questions,
answer library, reports, assets and metadata. Worker operations retain the older
accept/claim/fence protocol. Those HTTP worker calls are compatibility paths; an
ordinary local application starts through `application_runtime`.

## Hermes executor

For a fresh installation, follow the [Hermes skills and plugin setup](GETTING_STARTED.md#5-connect-hermes-to-the-repository).
That guide also covers [mailbox authentication](GETTING_STARTED.md#6-connect-your-application-mailbox)
and [optional Discord setup](GETTING_STARTED.md#7-optional-discord-bot-and-submission-alerts).
The entry skill and native plugin ship in this repository; email skills come
from Hermes. They require the new user's own credentials.

`integrations/hermes_jobbot/` contains plugin registration and the thin discovery
skill entry. The canonical procedure stays under `skills/productivity/`.
`hermes_plugin.py` binds tool calls to the actual conversation/request, while the
workspace runtime owns data and browser operations.

Queue dispatch can launch a configured Hermes CLI command or a steerable native
desktop session. `hermes_desktop.py` retains native conversation identity, terminal
receipts, continuation and cleanup association. It does not infer application
success from the model process exiting normally.

Provider credentials and model availability come from the installed Hermes
configuration. `model_settings.py` maps supported choices to the executor. Discovery
has its own command/profile; changing the application model does not implicitly
change discovery. Read [Desktop queue steering](jobbot-v1/DESKTOP_QUEUE_STEERING.md),
[Hermes connection](jobbot-v1/HERMES_CONNECTION.md) and the older
[worker protocol](jobbot-v1/WORKER_PROTOCOL.md) for their respective scopes.

## Simplify and employer portals

Simplify is installed in the selected Chromium-family browser profile. Jobot's
shared boundary observes availability, starts Autofill and tracks settlement.
Selected credentials use the private native credential path; Simplify fills
supported application fields before residual work.

Workday, Greenhouse, iCIMS and LinkedIn Easy Apply have specialized helpers. Shared
form controls, frames, answers, credential operations and submission evidence are
used across portals. Unsupported forms return to executor inspection and recovery;
helper recognition is not a universal compatibility certification.

See [Architecture](ARCHITECTURE.md) and the [helper map](jobbot-v1/APPLICATION_RUNTIME.md).

## Discovery and external intake

`harvest_runtime.py` launches separate discovery work from
[job-posting-harvest](../skills/job-posting-harvest/SKILL.md). It records each run's
completion state and source provenance. Discovery submits verified postings to
intake; an application executor does not discover or start another job.

The scheduled service template uses `--enqueue`, which allows qualifying discovery
verdicts into the queue under the existing policy. Discovery-only/manual-review
intake is different. Pausing Jobot prevents new scheduled discovery as well as new
queued application admission.

`harvester_source.py` supports external Harvester intake. The existing JobNavigator
integration has its own bridge/state installation; this repository contains bounded
patches, regression tests and route-enrichment support, not a replacement bridge.
`resolve_routes.py` observes pending posting routes and sends verified route updates
back through the installed bridge flow. See the
[bridge maintenance guide](../integrations/jobnavigator_bridge/README.md),
[Harvester review](jobbot-v1/HARVESTER_INTEGRATION_REVIEW.md) and
[source attribution](jobbot-v1/SOURCE_PROCESS_ATTRIBUTION.md).

## Mailbox and account verification

The selected private configuration describes the existing Gmail/Hermes wrapper or
Himalaya account. Mail requests retain candidate, employer and timing context.
`email_routing.py` supports an approved form-recipient/verification-inbox split,
including forwarded verification messages. The addresses need not be identical.

The executor uses the actual available mailbox and current application evidence.
The host fills selected credentials/codes without exposing them in public history.
No mail body, code or password belongs in documentation. See the canonical
[accounts and mail reference](../skills/productivity/job-apply/references/accounts-and-mail.md).

## Answer learning and submission alerts

The dashboard process owns `AnswerLearner`, which uses the installed Hermes
auxiliary inference client without tools or a browser. It reads durable learning
work and preserves application responses even when inference is unavailable.
This is distinct from activated procedural lessons and application executors.

Settings exposes **Discovery model** and **Answer learning model** independently;
both default to **Same as application model**. Explicit separate selections use
the installed Hermes credentials and provider catalog. Jobot does not change the
global Hermes profile when these settings change.

### Model call inventory

| Path | Model selection |
|---|---|
| Queued application / Hermes Desktop or CLI | Application model setting; otherwise the configured executor default |
| Discovery search, assessment and intake generation | Discovery model setting; shares the application model by default |
| Answer synthesis, company knowledge and semantic answer matching | Answer learning model setting; shares the application model by default |
| Hermes internal tool inference, vision and compression | Hermes auxiliary routing, active model context and installed task overrides/fallback configuration |
| Managed HTTP worker / native compatibility runner | Attested request settings; these are not additional discovery workers |
| Original browser-use application | Legacy `OPENAI_MODEL` environment setting (the historical `.env.example` names Qwen); separate from the managed dashboard |
| Browser helpers, Simplify bridge, mailbox/notification plumbing, external Harvester import | No Jobot-owned model call; external products retain their own configuration |

The catalog may list local Qwen models without selecting them. Hermes auxiliary
overrides and fallbacks are owned by the installed Hermes configuration, not this
dashboard. Audit those alongside the primary selections when investigating observed
model traffic; a static code search alone cannot establish the deployed model.

Optional `hermes_notifications.py` reads confirmed new submissions and uses the
installed `hermes send` integration. Delivery receipts/retries live in the private
spool. It does not send candidate answers, resumes or full transcripts, and does
not implement a reply channel for unresolved questions. A crash after send but
before checkpoint can duplicate an alert. See [Submission alerts](jobbot-v1/SUBMISSION_ALERTS.md).
