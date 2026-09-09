# Application runtime: ownership, helper map, and rationale

This is the authoritative local-session architecture, implemented on Windows in
September 2026. Older HTTP accept/claim/lease startup is **compatibility only**.
Historical failures in REVIEW_HANDOFF remain historical evidence. Actual delivery
checks and unresolved acceptance are in [RUNTIME_SIMPLIFICATION_LOG.md](RUNTIME_SIMPLIFICATION_LOG.md).

Live Wiley attempt 14 stopped prematurely at sign-in. The focused follow-up
connects observed native/extension controls to one mapped recovery step in the
existing runner. Current live proof and remaining limitations are in the log's
opening entry; do not infer acceptance from the implementation described here.

## Before and after

```text
Before: conversation -> API token + running HTTP service -> expiring shared lease
        -> manually available browser/old target -> bounded helper
After:  conversation -> local start -> existing Service/database -> preparing session
        -> automatic workspace host -> verified fresh headed target
        -> existing Simplify/Workday/account/document helpers -> submission evidence
        dashboard + authenticated HTTP -> same Service/database
```

The previous coupling made service/token/browser setup prerequisites and treated
model gaps like loss of ownership. A small host without an LLM now retains the OS
lock and browser tree between CLI calls. Its cost is one host and one browser per
occupied workspace, bounded by configuration. No renewal loop grants permission.

## Responsibilities and records

| Component | Responsibility |
|---|---|
| Engineering agent | Shared code/skills and synthetic diagnosis; employer form work is not executor acceptance |
| Ordinary conversation | Selected model reasons, uses approved facts/mail/Simplify, handles exceptions, submits and verifies |
| Service/database | Eligibility, ownership, accounts, documents, actions, attempts, submission policy and outcomes |
| Workspace host | No model; OS ownership, automatic launch, readiness, scoped requests and stop-before-reuse |
| Workspace | Persistent authenticated Simplify profile, unique loopback CDP endpoint and browser instance |
| Dashboard | Observe same records and request independent pause/stop; optional for applications |
| HTTP | Existing authenticated compatibility API; cannot seize locally configured profiles/sessions |

One absolute configured `db_path` remains authoritative. `legacy_history_paths`
are read-only duplicate/uncertainty sources; missing sources fail closed. There
is no cwd-selected database or second outcome store. `prepare_local` checks the
instance and makes an integrity-checked SQLite backup before additive migration
15. Existing accounts, attempts and submissions remain. Transactions are short
state updates; browser/model/mail work stays outside them. Existing SQLite busy
handling remains in the shared connection layer.

| Record | Meaning and lifetime |
|---|---|
| Job | Canonical requisition, eligibility/outcome; persists across retries |
| Attempt | Execution history created after live readiness and retained |
| Session | One application's lifecycle and attached conversation; repeated start is idempotent |
| Workspace | Persistent directory/endpoint; at most one non-ended session |
| Target | Fresh owned tab; never inherited from an earlier attempt |
| Account | Candidate + portal history; survives failed applications |
| Account coordination | Short person + portal lock during authentication; release after auth or stop; other portals independent |
| Host lock | Exclusive OS file handle held in profile until host exits |
| Process identity | PID plus OS creation time, protecting against PID reuse |
| Fence | Existing generation retained for service compatibility; local authority also requires session/current driver/host |
| Heartbeat | Driver activity telemetry, with no authorization expiry |
| Fast checkpoint/lock | Private counters plus OS lock for competing calls; not an outcome store; crash releases lock |

Account lookup precedes authentication and is scoped to candidate plus verified
portal namespace. `creation_pending` records dispatch intent; it does not prove
that an account exists. A creation click proven `not_executed` by the owned browser
can move its own attempt's pending account to `creation_not_executed`, retaining
the dispatch reason and allowing bounded recovery. Uncertain dispatch remains
pending for reconciliation; employer evidence establishes `created_unverified`
or `confirmed`. Screen handoffs include state, timestamps and last attempt ID.

## Actual startup and call sequence

Configuration selection is `--config`, then `JOBBOT_CONFIG`, then the ignored
`artifacts/jobbot-v1-private/runtime-config.json` pointer containing `config_path`.
The selected private runtime is
`artifacts/jobbot-v1-private/windows-review-pilot/native-app.json`.
Use the actual checkout and its virtualenv. CLI reads `HERMES_SESSION_ID`, or takes
`--driver-id` with the actual conversation ID. Another conversation uses its own ID.

```text
.venv/Scripts/python.exe -m job_applier.application_runtime start <job-url>
.venv/Scripts/python.exe -m job_applier.application_runtime start --job-id <job-id>
.venv/Scripts/python.exe -m job_applier.application_runtime status <session-id>
.venv/Scripts/python.exe -m job_applier.workday_fast session <session-id> --seconds 60
.venv/Scripts/python.exe -m job_applier.application_runtime call <session-id> browser --parameters @<private-json-file>
.venv/Scripts/python.exe -m job_applier.application_runtime pause <session-id>
.venv/Scripts/python.exe -m job_applier.application_runtime attach <session-id>
.venv/Scripts/python.exe -m job_applier.application_runtime stop <session-id>
.venv/Scripts/python.exe -m job_applier.application_runtime retry <session-id>
```

These templates use implemented operations. `application_runtime doctor --url
<url>` is an optional read-only diagnostic, not a token/service/lease startup gate.
Generic local service calls use `run_applier.py managed call --config <path>
--transport local --operation <name>`; browser writes require the session host.

1. `application_runtime.start` resolves identity/config, checks read-only history,
   calls existing intake/eligibility, and selects the configured approved resume.
   `authorize_requested_urls:true` allows requested held URLs under standing
   authorization; exclusions and duplicate policy still apply.
2. `SessionServices.reserve_session` atomically records preparing/capacity_wait,
   candidate, resume, request/model evidence and an idempotency key. No attempt is
   created before readiness; repeated start returns the same session/target.
3. `ensure_host` automatically launches the no-model host. It checks ownership,
   launches the configured browser, verifies actual process arguments, profile,
   mode, endpoint, fresh operable target and Simplify on the supported application
   surface. It does not require a panel on about:blank.
4. `session_connected` creates the managed attempt and binds the fresh target.
   The compact handle resolves low-level IDs and includes existing application
   context: identity, approved assets, account strategy and helpers/lessons.
5. `session_call` sends JSON through a local Windows named pipe. Host dispatch
   supplies exact session/driver/host authority and invokes the shared operations.
   No HTTP token, model launch, global CDP setting or desktop focus is involved.
6. `workday_fast.advance` performs bounded routine observation/advancement using
   Simplify. The conversation handles actual blockers with scoped credentials,
   browser, account and mailbox helpers. Writer quiescence, forward-first behavior
   and selected-asset verification remain intact.
7. Existing submission_intent precedes one submit; finish records exact employer
   evidence. The host stops its browser before releasing the slot. Missing
   confirmation means submission_unknown. The executor must not repeat Submit.

Native Hermes jobbot operations are convenience calls to the same functions.
Hooks can record observed provider/model/effort; requested settings remain
separate. CLI-only model evidence is unknown unless supplied by the actual harness.

## Windows lifecycle, recovery and parallelism

`workspace_process` creates the browser suspended, assigns it to a Windows Job
Object with kill-on-close, then resumes it. The detached host retains that object
and the profile lock across CLI exit. Tests exercise real shell-exit survival and
child/grandchild death on host kill; detached Popen alone is not the proof.

A healthy owned browser is retained during its session. Current policy stops it
on finish/pause/stop instead of keeping it warm across applications; the persistent
profile remains. Idle hosts exit after 60 seconds. Externally running browsers
are never adopted or killed. Startup checks endpoint and OS command-line inventory
before launching against a profile. Old profile aliases consult legacy reservations;
migration guards reject old-version acquisition of locally configured profiles.

Pause/stop acknowledgement follows actual owned process-tree termination and
abortion of active actions. Startup observes pending control before connecting.
Explicit attach requires completed pause and creates a fresh target for the new
driver on the same attempt; the previous driver is rejected. Retry requires ended
ownership and no unresolved submission intent. After a crash, a replacement host
checks recorded process identities before classifying the lost session. It never
replays an uncertain command. Orphan activity/unconfirmed host launch remains
isolated with an actionable reason; a definitely unstarted failure releases its slot.

Host life, driver activity, browser writer state and verified progress are
separate. Driver age over 120 seconds is visible but does not revoke permission.
Host telemetry cannot manufacture progress. Optional maximum_runtime_seconds
(60..86400) actually stops the owned browser; it is not a lease timeout. Request,
preparing, connected and ended times preserve total elapsed wall time; queue and
startup time are available separately. Ten minutes is a measured target.

Two distinct configured directories/endpoints allow two independent sessions.
A third gets capacity_wait and occupants; repeated start retries capacity with
the same request. Paused sessions retain their slot. Same-job uncertainty blocks
that job across email identities, not another workspace. concurrency_limit caps use.

## Configuration, provisioning and credentials

Local config requires transport:local, instance_id, absolute db_path, identity_id,
resume_asset_id, spool_dir, legacy_history_paths and workspaces. Each workspace has
id, absolute user_data_dir/browser_executable, unique 127.0.0.1 cdp_url and mode
(default headed). Optional legacy_profiles maps known earlier IDs. Preserve the
selected model/provider and explicit credential_profile_path, gmail_script and
mailbox_token_path references. Private config, assets, browser/auth state, logs,
backups, checkpoints and test artifacts stay out of Git.

Prepare each production workspace separately with official authenticated Simplify;
never clone live cookies/profile state. An empty second profile is an installation
gap. Readiness proves panel availability; the executor must still verify actual
Simplify/account/contact identities. require_simplify:false is development-only.
Headless fixtures do not establish headless Simplify. Real official-service
concurrency requires two simultaneous authenticated extension sessions.

The portable CLI needs no native Hermes plugin installation. Native setup is in
[HERMES_CONNECTION.md](HERMES_CONNECTION.md). HTTP keeps environment-first,
explicit-file-fallback credential resolution, roles, instance checks and legacy
leases. Local execution uses OS/database access, not an unauthenticated network API.

## Helper map and canonical procedure

| Component | Scope and consumer |
|---|---|
| application_runtime.py | Shared high-level startup/control, scoped browser exceptions, history |
| managed_sessions.py / migration 15 | Existing ledger session/workspace/account coordination and mixed-version guards |
| workspace_host.py / workspace_process.py | Windows lifetime, readiness, scoped JSON dispatch; no model |
| managed_client.py / managed_cli.py / managed_api.py | Two transports over shared methods; HTTP auth retained |
| managed.py / managed_runtime.py / managed_events.py / managed_views.py / managed_continuity.py | Existing policy/actions/events/duplicates consult local lifecycle or explicit legacy ownership |
| managed_identity.py | Shared target scope, including Workday details-to-job redirects with exact host, career site, full requisition slug and allowed child route |
| workday_fast.py | Bounded Workday supervisor; native and CLI call the same advance function |
| workday_auth.py | Workday account decisions inside the supervisor; shared account record/coordination and private filler, no model or password storage duplication |
| cdp_client.py | Exact-target connection, structured evaluate_function arguments, and validated native pointer activation shared by the runner and local browser recovery |
| browser_controls.py / browser_helpers/form_controls.js | Shared native form inventory, verified text/select/check/keyboard exceptions; Workday retains its site-specific inventory |
| application_answers.py | Interprets allowlisted candidate profile salary/privacy preferences for the shared browser operation and Workday runner; contains no personal answer defaults |
| submission.py / browser_helpers/submission_observe.js | Shared one-click boundary, transient native/Simplify confirmation capture, scoped redirect inspection, private evidence and truthful outcome |
| simplify_boundary.py / browser_helpers/simplify_observe.js / simplify_click.js | Official extension observation, actuation, settlement and forward-first policy |
| browser_helpers/workday_observe.js / workday_click.js | Workday steps/errors/attachment/employer-confirmation and observed controls |
| managed_credentials.py / managed_documents.py / hermes_gmail.py | Private credentials and shared screenshot masking (local and legacy callers), hash-checked selected-asset uploads, configured correlated mailbox |
| hermes_plugin.py / integration entry | Convenience and actual session/model metadata; no alternative form logic |
| managed_hermes_worker.py / native_hermes_session.py / hermes_adapter.py | Existing explicit legacy worker integration; never launched by local start |
| static/jobbot.html / jobbot.js | Existing dashboard, parallel session/process/driver/model/progress and independent controls |

Common policy is job-apply v0.4.5; Workday policy is workday-simplify v0.3.3, in
skills/productivity. Hermes discovery is thin. Source fingerprint/revision and
canonical skill hash are recorded at start. No shared helper/skill edits during
an application benchmark. Review observations afterward and load the revision
on the next application. Trace all callers before declaring older helpers unused.

Optional `answer_policy_profile_path` selects a private editable JSON profile.
Only its allowlisted `application_answer_policy` preferences are projected into
the managed candidate at start, before the immutable attempt snapshot. Other
candidate fields stay managed; credentials remain in `credential_profile_path`.
Without this option, the managed profile remains the source. Supported policy:
`salary_expectation:{use_posted_range_max,fallback_amount,currency,period}`,
`routine_privacy_consent:boolean`, and `submission_evidence_sources` containing
`employer`, `simplify`, `user_reported`. Fallback is not a minimum/floor. Multiple
advertised ranges require the applicable range from the executor. No historical
attempt answer or outcome is rewritten when preferences change.

Submission capture is armed on the owned CDP target before activation. Evidence
survives ordinary scoped redirects and is persisted in the private spool. A
possibly dispatched submit is never replayed. Native and Simplify proof carry
separate sources; absence of approved evidence returns uncertainty. Local hosts
retain that page for 120 seconds of inspection, then stop the owned process tree
and retire. Reconcile supports the native plugin and portable CLI, records a
separate source/timestamp event, and preserves historical completion/duration.
Headed browser startup requests and verifies maximization; no automatic refresh.
One background host owns each occupied workspace, with independent parallel
session cleanup. It exits after a completed session response is delivered.

Enabled Simplify input prompts can override a cosmetic spinner after stable
observation, while real unfinished helper writes remain exclusive. Native
takeover remains separate from extension input permission. Shared form helpers
verify values and return ambiguous menu/coverage evidence instead of guessing.

Follow-up work: correlate application-confirmation email through the existing
Hermes Gmail adapter (employer, requisition/title, recipient and attempt time;
deduplicate old mail; never treat delayed mail as failure). Add a candidate profile
editor exposing advertised minimum/maximum choice, fallback amount, currency,
period and routine consent; keep preferences in editable data and snapshot the
chosen policy for each run. Minimum-range selection is a future option; this
checkpoint implements the approved maximum/fallback policy.

## Verification boundaries

Snapshot and Workday recovery share one native/official-extension inventory in
workday_fast.observe_page/screen_inventory. workday_observe retains unique
semantic refs across routine rerenders; the existing private filler and native
click helper accept those exact mappings. fast_forward recovery performs a bounded
mapped fill/verify/action/observe step in its existing connection, then resumes
routine execution. Mapped decisions and possibly-executed actions persist in the
existing private checkpoint; actual authenticated form access confirms the account.
No new service, migration or execution framework is involved. Simplify sign-in is
callable, distinguishes employer from extension login and requires separate
evidence of retained credential use. Enabled controls alone do not establish it.
Settled unrecognized UI returns actionable context promptly; writer uncertainty
remains an observation-only condition. Accepted mapped-step counts are recorded,
but are not a measurement of every model interpretation outside this interface.

The shared credential resolver selects the account ledger's saved reference. The
canonical default is credential:profile/accounts/default, resolved privately from
the explicitly configured credential_profile_path accounts.default. Optional
credential_account_keys maps a saved reference to another account key in that
same configured private file. An unavailable saved reference fails specifically;
it never silently borrows the default password. No credential values enter the
managed DB, events, helper checkpoint or model output.

For local Workday sessions the fast runner supplies the existing session account
coordination callback to workday_auth. It performs one fresh observed action at
a time, including the account privacy/terms checkbox and disabled-until-filled
submit buttons. It persists creation_pending before creating, records an explicit
employer creation confirmation immediately, and confirms sign-in only on an actual
application form. Counters survive calls and prevent replay of uncertain account
actions. Mail verification, rejected credentials, ambiguous consent or unfamiliar
controls return a specific authentication_required result to the ordinary executor.
The browser remains available for scoped recovery. Other ATS and legacy HTTP
execution retain their existing executor-driven auth path using the shared filler.
Simplify-generated password capture is not implemented: no documented retrieval
contract has been verified, so the current flow uses retained configured credentials.

Authentication handoffs distinguish unsupported/possibly changed controls from
rejected credentials, verification, configuration and an unconfirmed action. They
return observed non-secret control metadata, an owned screenshot command and a
bounded recovery instruction for the current executor. The reason/next step is
persisted once in the existing recovery timeline. browser screenshot writes a
unique PNG beneath the configured private spool, masks credentials with the same
shared mask as the legacy browser, and restores it even if capture fails. The
ordinary Hermes vision_analyze tool accepts that local image path; snapshot returns
fresh selectors for the subsequent scoped action. Missing vision capability stays
explicit and DOM inspection remains available. The runtime launches no model or
additional worker; the harness uses its existing image capability (native vision
when supported). This path never switches browser profiles or edits helpers in-run.

The existing immutable event timeline carries executor stage/activity/next-step
updates, helper observations and recoveries. Session cards show the latest semantic
update and recent steps, separately from host/driver liveness. The Workday runner
records a changed step/action once rather than on every poll. The host records a
helper exception and returns it without ending the session; the executor chooses
the supported recovery and records its explanation. Neither an activity update nor
a successful low-level tool call proves form progress. Old attempts without these
updates remain incomplete evidence and are not backfilled as successful steps.

Final automation runs the supported python -m pytest tests/jobbot_v1 -q suite,
with JOBBOT_BROWSER_TEST_EXE enabling real Windows lifecycle coverage. Destructive
checks use synthetic DBs/profiles. JUnit and phase evidence stay in ignored artifacts.
Official Simplify, mailbox challenges, employer submission and under-ten-minute
performance require separate ordinary-Hermes evidence. The implementation log
contains actual commands/results, durations and remaining blockers.
