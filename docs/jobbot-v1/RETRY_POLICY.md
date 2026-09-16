# Shared application request and retry policy

This is the authoritative policy adopted September 9, 2026 after the user
rejected blanket submission-uncertainty, same-job and account-use restrictions. It
applies to every portal, including Greenhouse, Workday and proprietary forms.
Login requirements do not affect whether another attempt can start.

September 15 operator cleanup adds one explicit exception: jobs the user marks
**Canceled** remain excluded until restored, including on rediscovery. Failed
attempts do not acquire this disposition automatically. See
[Job cleanup](JOB_CLEANUP.md) for preservation and pending-queue behavior.

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
| Explicit operator Canceled disposition | Preserve posting/account history; suppress new work until the operator restores the job. |
| Repeated call belonging to the same request | Return that request's existing session. |
| New request while a prior request has an active browser | Use another configured workspace if available; otherwise report capacity. The posting itself has no exclusive owner. |

There is no `confirmed_not_submitted` prerequisite, no operator unblock flag,
no portal-specific retry exception and no automatic rewrite of old outcomes.
An existing job imported or discovered before any application remains a first
attempt. Request metadata exposes `application_kind`: `first_attempt` or
`reattempt`. Earlier attempt IDs, events, timestamps and evidence are retained.

## Request identity and lifecycle

### Automatic queue recovery (operator request, September 15)

The sequential worker now picks up active intake automatically. An interrupted,
failed, blocked or submission-unknown request gets a fresh second request four
hours after completion, then a third 24 hours after the second completes. These
are three total attempts per automatic series, as requested by the operator.
Afterward the dashboard shows Needs attention and the retained failure reason.
An explicit new retry starts a fresh series; this is not a job-wide retry veto.
Pending user answers, explicit stops, review-only completion, cancellations and
recorded submissions retain their existing handling. Retry scheduling never ends
an in-progress application, rewrites evidence or bypasses browser cleanup.

`managed_queue.queue_reconcile` performs idempotent pickup; `attempt_schedule`
derives attempt counts and due times from durable request lineage. Both the
worker and Run next use that reconciliation. `queue_take` skips future retries
while allowing other ready jobs, and preserves one dispatched application.

The native Hermes caller supplies the observed user-turn ID as request metadata.
The shared runtime combines it with the actual conversation, configured identity
and resolved job ID to identify that request. Repeating its start call returns
the same session. A later application request has a different request identity.

Portable callers can provide `--request-id`. Without it, repeated starts reuse
the same driver's running, preparing or capacity-wait session; after it ends,
another start creates a new session. A paused or finishing session is not reused
by an unkeyed start. `retry <session-id>` stops that particular session and explicitly requests a new attempt. A different
conversation uses its own driver identity. The native caller updates its session
binding from the returned handle so subsequent browser calls use the new attempt.

Browser control is separate from retry eligibility. Shared `control_session`
performs explicit stop/pause and replacement of the particular session named by
`retry`. An ordinary new request does not stop another request for the same job.
Two browser sessions can work on the same posting or sign into the same account.
Operations on one physical workspace are queued by the host; another in-flight
call no longer causes `session_operation_busy` after five seconds. Distinct
Chrome profile directories/endpoints still require distinct workspaces.
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

Within an active attempt, click history is evidence, not permission. Form edits,
private verification, answers, reload/restart, pause/resume and another explicit
Submit remain available. The shared helper reads retained/current confirmation
before a newly requested click and activates at most once per call. A targetless
`browser submit` observes only. Workday follows its current page on another
advance call instead of always entering a confirmation-only branch.

The ordinary form inventory reports unfinished required fields and private
verification completeness without exposing values. Before dispatch, unfinished
fields return `application_incomplete`; after dispatch, validation feedback also
returns this continuation. Optional fields and an empty file input after upload
do not trigger this check. Unknown widget values are not assumed missing answers.
No special rejection proof is required to edit or continue. The legacy rejection
endpoint remains for compatibility and truthful historical resolution, not as an
unlock step. Do not relabel old clicks as not executed or invent confirmation.
Evidence files retain earlier dispatch records when a new cycle starts, including
a replacement target after browser recovery.

The older Hermes worker also permits form operations and a new explicit Submit
after a click. It no longer requires its own resume-upload receipt. Recorded
success still prevents ordinary duplicate applications. With concurrent attempts,
a later failure cannot erase successful posting status; another active attempt
keeps an unfinished posting running.

Browser leases are released on acknowledged quiescence independently of the
submission outcome. An active browser is a resource to control, not an exclusive
claim on a posting; historical uncertainty is not ownership evidence.

## Implementation and callers

| Component | Responsibility |
| --- | --- |
| `managed_identity.py` and `Service.intake` | Match URL aliases/requisitions to the existing durable job. |
| `managed_events._submission_state` | Read the existing per-attempt evidence projection. |
| `Service._assert_not_suppressed` | Suppress recorded success, including retained accepted evidence, and explicit operator cancellation. |
| `Service._eligible`, `retry`, `_complete` | Apply configured eligibility and recorded success, allow concurrent attempts, and aggregate posting status. The job-owner veto was removed. |
| `application_runtime.start` | Resolve request identity, reuse the same request or allocate an independent workspace, and enter the shared session startup path. |
| `application_runtime.control_session` | Reuse one stop/pause implementation for explicit control and retry of a particular session. |
| `application_runtime.session_call` | Route explicit retry through ordinary start with a new attempt. |
| `managed_sessions.reserve_session` | Record first-attempt/reattempt classification and existing history-derived storage cleanup. |
| `hermes_plugin._handle_local` | Supply observed request-turn metadata and retain the returned current session ID. |
| `application_runtime.history_matches` | Read legacy history for recorded successful submissions only. |
| `managed_questions.queue_answer_retries` and dashboard | Apply the same success-only history suppression to saved-answer retries. |

Migration 17 removes `uq_managed_active_job` and `one_local_job` and narrows the
legacy reservation trigger to physical browser profiles. Account coordination
returns the portal namespace without excluding another session. The shared
`browser_controls.remaining_submission_work` reader feeds the submission helper;
`submission_pending` remains a reporting projection, never a permission switch.

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

## Same-session continuation follow-up

The same-session changes remove an obsolete Workday never-resubmit test and
conflicting assertions, and adjust existing fixture expectations. No new test
cases were added and no regressions were run, as explicitly requested. Source,
diff and syntax review are the verification basis. Earlier passing suite counts
do not validate this change. Attempt 46 was separately corrected at the user's
request using retained employer-page evidence; that operational correction is
not a fixture or proof of live acceptance of the new code. See
[the research handoff](GUARDRAIL_RESEARCH_HANDOFF.md) for concrete changes and
remaining areas requiring a complete source audit.
