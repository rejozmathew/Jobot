# Source and process attribution

The dashboard's **Source → Origin details** separates a discovery feed from
the process that supplied the job and the process that placed it in the execution
queue. **Added** remains the original JobBot intake time. The original source
timestamp and source identity are never overwritten by rediscovery.

| Entry point | Feed | Recorded process | Queue origin |
| --- | --- | --- | --- |
| Dashboard Add job | manual | dashboard | Automatic pickup when the worker collects it |
| Dashboard Retry selected | Retains original feeds | dashboard on the new queue entry | manual_retry |
| Queue CLI enqueue | manual for supplied URLs | queue_cli | manual_enqueue or manual_retry |
| Managed CLI call | Caller-supplied feed or existing manual default | managed_cli unless explicitly supplied | api_request unless explicitly supplied |
| Direct application start with a URL | manual | application_runtime | No dispatch queue entry created by this intake |
| Legacy managed queue bridge | legacy_cli | legacy_cli | No new dispatcher origin inferred |
| Scheduled Hermes discovery | Per-record employer_search, linkedin_alert_email, or retained Harvester feed | hermes_scheduled_discovery | discovery for explicit handoff |
| Manual Hermes harvest runtime | Per-record feed | hermes_manual_discovery | discovery for explicit handoff |
| Standalone discovery emitter | Per-record feed | discovery_intake, or explicit --producer | discovery for explicit handoff |
| Automatic intake / restored job / retry | Retains original feeds | queue_worker on the queue entry | automatic_intake / automatic_restore / automatic_retry |
| Answers retry | Retains original feeds | queue_worker | answer_retry |
| Direct external API/local Service caller | Supplied source information | Supplied producer, otherwise Not recorded | Supplied enqueue_origin, otherwise Not recorded |

Scheduled discovery embeds `--producer`, `--discovery-run-id` and, when explicitly
selected with `--profile`, `--discovery-profile` in the canonical emitter command.
The run ID is the actual `discovery_runs.id`. Command context is passed to both
intake and enqueue; role records cannot override it with model/page-supplied
producer fields. The caller supplies its feed reference in `source_type` and
`source_id`. A converted Job Harvester export retains its feed while Hermes is
recorded as the process that verified and imported it. The offline converter is
not itself a live importer or scheduler.

External integrations can send optional `producer`, `discovery_run_id` and
`discovery_profile` arguments to intake, then the same context plus
`enqueue_origin` to queue_enqueue. For the emitter, pass those fields as CLI
options, separately from the input JSON records. These are caller-reported
identifiers, not an authenticated audit of an arbitrary external process.
Unknown callers remain usable; absent attribution adds no application restriction.

Migration 21 adds `source_observations` and four nullable dispatch columns.
Source observations retain each distinct supplying process/profile/run while
replaying the same context is idempotent. Queue attribution is written only when
a queue item is actually created. An enqueue request that returns an existing
item never takes credit for creating that item. Automatic retries record the
worker as their producer and retain the original entry in Queue entry history.

Historical sources such as `greenhouse` remain exactly as recorded. No process
is backfilled from an ATS hostname, request prefix, executor, or guessed schedule.
A later observation does not prove who originally created a historical row;
the UI says Seen by / Observed and retains separate timestamps. Historical queue
entries with no provenance show Not recorded. Pending requests created before
deployment keep that label when they execute.

Validation uses synthetic data only: rediscovery, multiple runs, unchanged
timestamps, actual-run command handoff, queue idempotency, automatic pickup and
retries, optional metadata, UUID preservation, migration from schema 20, and
safe dashboard rendering. Production jobs are never inserted as test fixtures.

September 16 Windows validation: all five initial regressions failed before the
implementation. The focused integration run passed 51 tests; expanded coverage
and the final source/dashboard check passed 13 tests. The complete managed suite
reported 843 passed, five Linux-only skips and one headed browser pause timeout.
That lifecycle test passed its isolated rerun (93.69 seconds): 844 distinct tests
passed. The full suite took 442.26 seconds and reported four existing deprecation
warnings. The source and expanded queue-history panels were visually inspected
at 1280 pixels using an isolated synthetic database/browser. No production
application was used as a fixture.

Antigravity delegation was attempted as required by repository workflow, but
automatic approval review rejected external repository-context transfer. Tests
were run locally as the permitted alternative; JUnit/logs were inspected directly.
Evidence is under ignored `artifacts/jobbot-v1-private/process-provenance-20260916/`.
