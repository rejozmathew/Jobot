# Shared application request and retry policy

This is the authoritative policy adopted September 9, 2026 after the user
rejected the previous cross-attempt submission-uncertainty restrictions. It
applies to every portal, including Greenhouse, Workday and proprietary forms.
Login requirements do not affect whether another attempt can start.

## Decision

Match the requested URL to a job using the existing canonical URL/requisition
identity code. The job is the durable posting; an attempt is one execution of
an application request. An existing job may have any number of attempts.

| Existing information | Behavior |
| --- | --- |
| No earlier attempt or ended startup session | Start the first attempt. |
| Failed, blocked, stopped, interrupted or otherwise unfinished attempt | Start a fresh attempt from the beginning. |
| Earlier Submit may have executed, with no recorded success | Preserve that uncertainty and allow a new requested attempt. |
| Recorded successful submission, including accepted confirmation evidence | Report already applied; suppress an ordinary duplicate. |
| Repeated call belonging to the same request | Return that request's existing session. |
| New request while a prior request has an active browser | Stop that owned browser, then start the new attempt. |

There is no `confirmed_not_submitted` prerequisite, no operator unblock flag,
no portal-specific retry exception and no automatic rewrite of old outcomes.
An existing job imported or discovered before any application remains a first
attempt. Request metadata exposes `application_kind`: `first_attempt` or
`reattempt`. Earlier attempt IDs, events, timestamps and evidence are retained.

## Request identity and lifecycle

The native Hermes caller supplies the observed user-turn ID as request metadata.
The shared runtime combines it with the actual conversation, configured identity
and resolved job ID to identify that request. Repeating its start call returns
the same session. A later application request has a different request identity.

Portable callers can provide `--request-id`. Without it, repeated starts reuse
the same driver's running, preparing or capacity-wait session; after it ends,
another start creates a new session. Starting a paused or finishing session
closes it and starts fresh. `retry <session-id>` explicitly requests a new attempt. A different
conversation uses its own driver identity. The native caller updates its session
binding from the returned handle so subsequent browser calls use the new attempt.

Browser control is separate from retry eligibility. Shared `control_session`
performs the existing stop/pause lifecycle for ordinary control and fresh starts.
It stops actual owned activity before the new browser is assigned; a pending
stop returns continuation guidance rather than a permanent job restriction.
Heartbeat age is activity telemetry, not a submission result or a job ban. The
host owns process cleanup. This change does not introduce a heartbeat timeout.

The CLI loads current source on each invocation. Already running native Hermes,
dashboard and workspace-host processes retain imported code until restarted or
reloaded. End owned applications through their normal lifecycle before replacing
an occupied host. Documentation or a local Git checkpoint alone does not prove
that an existing long-running process has loaded this policy.

Each reattempt uses the existing employer-origin storage cleanup and a fresh
target. Simplify's separate login and approved reusable employer
credentials remain available. A form without login proceeds directly to filling;
an actual login form uses the existing authentication flow. URL normalization
and form interaction may vary by portal; this retry decision does not.

## Submission history versus another attempt

`submission_state` still describes the evidence for a particular attempt. It
can remain pending even after that attempt stops. A new attempt starts with its
own empty submission intent and independent browser state.

Within one active attempt, the submission helper still records its click and
does not automatically replay an uncertain dispatch. Fresh captured employer
rejection still supports correction in that same session. These observations
are not prerequisites for a later user-requested attempt. Do not reinterpret
an old Submit as not executed merely to permit retry, and do not invent employer
confirmation or rejection evidence.

Browser leases are released on acknowledged quiescence independently of the
submission outcome. An actually active owner remains a lifecycle matter to
stop; a historical `submission_unknown` job status is not ownership evidence.

## Implementation and callers

| Component | Responsibility |
| --- | --- |
| `managed_identity.py` and `Service.intake` | Match URL aliases/requisitions to the existing durable job. |
| `managed_events._submission_state` | Read the existing per-attempt evidence projection. |
| `Service._assert_not_suppressed` | Suppress only recorded success, including retained accepted evidence. |
| `Service._assert_no_owner`, `_eligible`, `retry` | Separate actual ownership and configured eligibility from historical attempt outcomes; queue an unfinished job without reconciliation. |
| `application_runtime.start` | Resolve request identity, reuse the same request or stop an older request, and enter the shared session startup path. |
| `application_runtime.control_session` | Reuse one stop/pause implementation for control, new starts and retry. |
| `application_runtime.session_call` | Route explicit retry through ordinary start with a new attempt. |
| `managed_sessions.reserve_session` | Record first-attempt/reattempt classification and existing history-derived storage cleanup. |
| `hermes_plugin._handle_local` | Supply observed request-turn metadata and retain the returned current session ID. |
| `application_runtime.history_matches` | Read legacy history for recorded successful submissions only. |
| `managed_questions.queue_answer_retries` and dashboard | Apply the same success-only history suppression to saved-answer retries. |

Removed restrictions include the old pending-attempt scan in job suppression,
the `verify_exact_submission_before_retry` refusal, historical interrupted/unknown
status gates, duplicate retry-status/lease checks, the answer-queue uncertainty
query and its dashboard counterpart, and legacy-history suppression for unfinished
jobs. The change adds no reconciliation operation or outcome database.

## Documentation history and verification limits

The earlier runtime evolution, shared recovery, dropdowns, private verification,
metadata and progress responsibilities are documented in
[APPLICATION_RUNTIME.md](APPLICATION_RUNTIME.md). The Greenhouse
[plan](GREENHOUSE_RECOVERY_PLAN.md) and
[validation report](GREENHOUSE_RECOVERY_VALIDATION_2026_09_09.md) describe the
preceding implementation. This policy supersedes their cross-attempt retry
restrictions; their historical evidence and test results remain historical.

For this follow-up the user explicitly instructed no new tests and no regression
execution. The uncommitted draft tests for the abandoned non-submission-review
design were discarded. Three obsolete test functions (four parameterized cases)
were removed, along with obsolete retry-blocking assertions in two broader tests.
No replacement tests were added. Earlier passing suite counts do not validate
this follow-up. Source/diff review is the verification basis; no live application
or production-history reconciliation is performed as an engineering fixture.
