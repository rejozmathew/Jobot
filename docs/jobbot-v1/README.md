# Engineering reference index

[Current documentation](../README.md) · [Architecture](../ARCHITECTURE.md) · [Project history](../PROJECT_HISTORY.md)

This directory contains both current detailed references and historical engineering
records. Read the guides one level above for a coherent introduction. A dated
checkpoint, proposal or old deployment plan does not override current source,
repository instructions or the canonical application skill.

## Current detailed references

| Reference | Scope |
|---|---|
| [Application runtime](APPLICATION_RUNTIME.md) | Local-session design, recovery, ownership, helper/caller map and implementation updates |
| [Retry policy](RETRY_POLICY.md) | Request identity, preserved attempt history and retry semantics |
| [Queue and VM runbook](QUEUE_AND_VM_RUNBOOK.md) | Queue scheduling, retained browser, concurrency and Ubuntu operation; earlier rollout notes retain their dates |
| [Activity statistics](ACTIVITY_STATS.md) | Cohorts, rates, deduplicated postings and outcome accounting |
| [Cross-source identity](CROSS_SOURCE_IDENTITY.md) | Posting identity and source preservation |
| [Source/process attribution](SOURCE_PROCESS_ATTRIBUTION.md) | Discovery producer and dispatch provenance |
| [Job cleanup](JOB_CLEANUP.md) | Reversible cancellation/restoration and retained history |
| [Submission alerts](SUBMISSION_ALERTS.md) | Optional confirmed-submission observer and delivery receipts |
| [Validation storage](VALIDATION_STORAGE.md) | Disposable synthetic fixtures, completion records and Ubuntu retention |
| [Self-improvement](SELF_IMPROVEMENT.md) | Evidence-driven review procedure and numbered implementation records |
| [Runtime simplification log](RUNTIME_SIMPLIFICATION_LOG.md) | Design evolution, rationale, checkpoints and explicitly deferred proposals |

## Integration and platform references

| Reference | Scope |
|---|---|
| [Desktop queue steering](DESKTOP_QUEUE_STEERING.md) | Native executor conversations and queue association |
| [Hermes connection](HERMES_CONNECTION.md) | Harness connection and implementation responsibilities; includes earlier compatibility context |
| [Hermes interface](HERMES_INTERFACE.md) | Earlier explicit worker interface contract |
| [Worker protocol](WORKER_PROTOCOL.md) | Managed worker protocol; ordinary local start uses the current session interface |
| [Harvester integration review](HARVESTER_INTEGRATION_REVIEW.md) | External source integration and evidence limitations |
| [Windows runbook](WINDOWS_RUNBOOK.md) | Historical Windows provisioning/acceptance and private launcher context |
| [Workday fast verification](WORKDAY_FAST_VERIFICATION.md) | Focused helper validation and its limits |
| [Workday next run](WORKDAY_NEXT_RUN.md) | Benchmark/measurement instructions; does not request a new live application |
| [Form repair, September 19](FORM_REPAIR_20260919.md) | Implemented shared form repair and validation record |
| [Greenhouse recovery validation, September 9](GREENHOUSE_RECOVERY_VALIDATION_2026_09_09.md) | Dated recovery validation evidence |

The canonical executable procedures are
[job-apply](../../skills/productivity/job-apply/SKILL.md) and
[workday-simplify](../../skills/productivity/workday-simplify/SKILL.md).
The [JobNavigator bridge guide](../../integrations/jobnavigator_bridge/README.md)
lives with its maintenance patches.

## Original specification and acceptance package

These files preserve the original planned design and staged acceptance. Statements
such as “not implemented,” “paused” or “not accepted” belong to those checkpoints.
They are not a current description of the deployed managed runtime.

| Record | Purpose |
|---|---|
| [Historical handoff](HISTORICAL_HANDOFF.md) | Former index and September kickoff/paused checkpoint, preserved intact |
| [PRD](PRD.md) | Initial product and behavior specification |
| [Implementation prompts](IMPLEMENTATION_PROMPTS.md) | Original staged engineering prompts |
| [Execution plan](EXECUTION_PLAN.md) | Staged implementation tracking |
| [Acceptance and data](ACCEPTANCE_AND_DATA.md) | Original acceptance/data handling plan |
| [Acceptance ledger](ACCEPTANCE_LEDGER.md) | Requirement acceptance checkpoint |
| [Requirement/test map](REQUIREMENT_TEST_MAP.md) | Original requirement-to-test mapping |
| [Source notes](SOURCE_NOTES.md) | Baseline and research references |
| [Later Ubuntu rollout](LATER_UBUNTU_ROLLOUT.md) | Earlier rollout proposal; current operations are in the current guides/runbook |
| [Stage 1 evidence](STAGE1_EVIDENCE.md), [files](STAGE1_FILES.md) | Initial implementation checkpoint |
| [Stage 2 evidence](STAGE2_EVIDENCE.md), [files](STAGE2_FILES.md) | Second-stage checkpoint |
| [Stage 3 evidence](STAGE3_EVIDENCE.md) | Third-stage checkpoint |
| [Stage 4 evidence](STAGE4_EVIDENCE.md) | Fourth-stage checkpoint |
| [Changed files](CHANGED_FILES.md), [release manifest](RELEASE_MANIFEST.json) | File inventory at the recorded release, not a live deployment manifest |

## Dated reviews, audits and proposals

| Record | Scope |
|---|---|
| [Review handoff](REVIEW_HANDOFF.md), [September 7 handoff](REVIEW_HANDOFF_2026-09-07.md) | Earlier runtime incidents and independent review questions |
| [Review notes](REVIEW_NOTES.md), [assessment September 15](ASSESSMENT_2026-09-15.md) | Dated engineering assessments |
| [Live pilot checkpoint](LIVE_PILOT_CHECKPOINT.md) | Recorded pilot state |
| [Regression September 9](REGRESSION_2026_09_09.md) | Dated synthetic regression results |
| [Discovery failure September 16](DISCOVERY_FAILURE_2026_09_16.md) | Discovery incident investigation |
| [Error-return review](ERROR_RETURN_REVIEW.md) | Error and recovery analysis |
| [Stop-condition audit](STOP_CONDITION_AUDIT.md), [catalog](STOP_CONDITION_CATALOG.md) | Audit and source catalog; proposals are not automatically implemented policy |
| [Guardrail research handoff](GUARDRAIL_RESEARCH_HANDOFF.md) | Research/review handoff |
| [Greenhouse recovery plan](GREENHOUSE_RECOVERY_PLAN.md) | Design proposal; later implementation/evidence is linked above |

Keep private per-application reports, screenshots, credentials and deployment
manifests in the existing ignored artifacts area. Maintain these indexes using
[Documentation maintenance](../DOCUMENTATION.md).
