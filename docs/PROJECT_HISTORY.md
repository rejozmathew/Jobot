# Project history and implemented work

[Documentation index](README.md) · [Architecture](ARCHITECTURE.md) · [Engineering records](jobbot-v1/README.md)

This is a selected capability history through October 21, 2026, not an exhaustive changelog
or a retrospective submission-rate claim. Commit IDs identify implementation
checkpoints. Dated test counts and deployment evidence remain in their original
records; actual candidate/application data stays private.

## From browser-use agent to managed operations

The original application grew out of a browser-use fork. It had a JSON queue and
later a SQLite-backed FastAPI dashboard, profile-based filling, browser-use model
execution, steps and recordings. Those compatibility paths remain in the tree;
[Legacy application](LEGACY.md) explains their scope.

The September managed implementation introduced explicit instances, candidate and
settings snapshots, account state, worker ownership, event/action evidence,
submission records, document versions and a replacement operator dashboard.
The initial PRD and staged acceptance records are preserved in the
[engineering index](jobbot-v1/README.md). They describe their own checkpoints,
including unresolved issues at those times.

Local application sessions then separated ordinary harness execution from the
older HTTP accept/claim/lease protocol. The runtime owns the browser and history;
the external model executor follows the shared repository skill. The helper/caller
map and [runtime simplification log](jobbot-v1/RUNTIME_SIMPLIFICATION_LOG.md) explain
that transition and its deferred proposals.

## Capability milestones

| Period | Implemented work | References / representative commits |
|---|---|---|
| September 9 | Shared fresh-request retry semantics; native credential/code recovery; Greenhouse recovery and semantic progress | [Retry policy](jobbot-v1/RETRY_POLICY.md), `0383482`, `6ca186c`, `184717e` |
| September 15 | Managed application queue, fresh external dispatch, contextual briefs, automatic pickup, source attribution, editable discovery, reversible cancellation and desktop steering | [Queue runbook](jobbot-v1/QUEUE_AND_VM_RUNBOOK.md), [Desktop steering](jobbot-v1/DESKTOP_QUEUE_STEERING.md), `0bfe34a`, `724978d`, `0655f11` |
| September 16 | Retained browser attachment, owned-tab cleanup, immediate per-job priority, durable six-attempt automatic schedule and explicit incomplete-discovery results | `b0ee343`, `6b6bbce`, `c924326`, `7009845` |
| September 17–18 | Sortable jobs, URL editing and ordered manual queueing; LinkedIn Easy Apply; session-owned Greenhouse batches; JobNavigator route repair | `b2e6399`, `2c9e30b`, `d77a489`, `624d529` |
| September 19–21 | Shared form continuity repair, configurable overall deadlines, iCIMS/post-autofill audit, cross-source posting identity, Greenhouse refill/verification and optional email routing | [Form repair](jobbot-v1/FORM_REPAIR_20260919.md), [Cross-source identity](jobbot-v1/CROSS_SOURCE_IDENTITY.md), `eb5c19d`, `47625d0`, `879c149`, `8b33341` |
| September 27 | Persistent Pause/Resume Jobot, stronger application recovery continuity and Simplify-first ordering across callers | `4503353`, `b2574fd`, `015e793` |
| September 28–30 | Numbered bounded recovery improvements; dashboard request IDs over HTTP; Greenhouse/iCIMS handoffs; credential diagnosis; styled checkbox/radio activation | [Self-improvement #001–#005](jobbot-v1/SELF_IMPROVEMENT.md), `3ec86c8`, `8cd52ae`, `acccd42`, `f3ed384` |
| October 1 | Independent confirmed-submission alerts through the existing Hermes integration | [Submission alerts](jobbot-v1/SUBMISSION_ALERTS.md), `a18e5b4` |
| October 2 | Recovery continuity; 1–5 simultaneous applications in the existing browser profile; visible owned windows and cleanup; editable reusable answers and focused answer inbox | `5baf177`, `5b65fbb`, `5d38d82`, `bb12536`, `9628106`, `42f6714` |
| October 3 | AI generalized knowledge separated from application responses; company knowledge; account namespace and authenticated-route recovery; select-all and Activity statistics | `c1c41a3`, `655b4b4`, `aba0ff2`, `a8dd72b`, `9d91d4c`, `b0e5bbb` |
| October 4 | Validation-fixture retention fix; SQLite contention resilience, indexed/batched reporting, retained routes and improved retry/answer context | `75a6948`, `1b6776f`, [Self-improvement #009](jobbot-v1/SELF_IMPROVEMENT.md) |

### Recent changes brought into the public main branch

| Date | Implemented work | Reference |
|---|---|---|
| October 16 | Preserve verified browser-history evidence after an accepted Apply handoff, allowing delayed continuation in the same session | Self-improvement #017, `f7b9ee9` |
| October 17 | Add candidate- and portal-scoped password overrides in Accounts & history, stored in the existing private credential file | [User guide](USER_GUIDE.md#accounts--history), `af86d29` |
| October 19 | Capture questions on signed embedded forms without retaining sensitive query values; preserve exact document isolation with an opaque digest | Self-improvement #018, `6030175` |
| October 21 | Refresh the public README with synthetic dashboard screenshots, explicit Hermes/Simplify dependencies and the managed execution flow | [README](../README.md), [Screenshot provenance](images/README.md) |

The three implementation commits were developed on `self-improvement` and brought
into the public `main` branch with their synthetic regressions and current guides.
The [numbered review record](jobbot-v1/SELF_IMPROVEMENT.md) describes the bounded
fixes and validation limits. Temporary folders, private application reviews and
deployment logs are not part of this synchronization.

## What the current system now covers

- Multiple intake sources converge on durable posting identity, provenance and
  queue state. Rediscovery and retries retain earlier history.
- Operators can select jobs in order, request immediate work, pause globally,
  control one session, choose concurrency and set a deadline.
- Each queued application gets its own external executor context and owned browser
  targets. Shared browser logins and personal tabs survive ordinary cleanup.
- Simplify and shared/ATS helpers cooperate with executor recovery, including
  embedded forms, asynchronous navigation, selected account credentials and mail.
- Required human questions have an actionable inbox. Saved responses, current
  learned answers and original answer history are distinct and inspectable.
- Profile, document, account, event, progress and submission evidence support the
  dashboard's nine pages and attempt reports.
- Deployment, rollback, synthetic validation retention and numbered engineering
  reviews have explicit workflows.

## What these records do not establish

The repository contains historical plans and proposed designs that were later
changed, partially implemented or deferred. Use current guides and source for
present behavior. The current shipped application is not described by the old
“not implemented” wording in a September kickoff snapshot.

The presence of an ATS helper does not guarantee every tenant/form works. Browser
fixtures are mechanism tests; the success of one real application does not prove
universal support. Mixed models, different postings, deployments and operator
intervention prevent simple before/after speed or submission-rate claims.

The self-improvement workflow preserves successful controls, frozen source/evidence
and conditional counterfactuals. A fixed prerequisite creates a recovery opportunity;
it is not a recorded employer submission. See
[Self-improvement](jobbot-v1/SELF_IMPROVEMENT.md) for the full evidence standard.
