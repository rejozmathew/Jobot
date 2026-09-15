# Application runtime: ownership, helper map, and rationale

This is the authoritative local-session architecture, implemented on Windows in
September 2026. Older HTTP accept/claim/lease startup is **compatibility only**.
Historical failures in REVIEW_HANDOFF remain historical evidence. Actual delivery
checks and unresolved acceptance are in [RUNTIME_SIMPLIFICATION_LOG.md](RUNTIME_SIMPLIFICATION_LOG.md).

The current cross-portal request and retry contract is in
[RETRY_POLICY.md](RETRY_POLICY.md). A new request matches the existing job and
starts a fresh attempt unless successful submission is recorded. Failed,
interrupted and submission-unknown history remain intact and do not prevent
another attempt. Actual browser cleanup is a separate lifecycle responsibility.
This September 9 follow-up supersedes earlier uncertainty and same-job/account exclusion guards;
the previous 761-test checkpoint does not validate this later change.

The [first-principles stop-condition audit](STOP_CONDITION_AUDIT.md) challenges
the necessity and placement of the restrictions described here. It distinguishes
current behavior from proposed simplification and includes a source catalog and
read-only historical incidence, followed by the implemented changes and validation.

The existing runner connects native/extension observations to mapped recovery.
Per-application outcomes and detailed diagnoses are retained in the managed
database and existing attempt reports. The proposed additional Workday
authentication recovery remains unimplemented. Design rationale and prioritization
are in the implementation log; describing an implementation here does not
establish live acceptance on every ATS.

Helpers support executor reasoning across all ATSs. A helper `blocked`,
`inspection_required`, unsupported control or call-budget result does not close
the application or establish its outcome. The executor inspects the supplied
controls/options and evidence, tries a different supported interaction and
resumes progress in the owned session. Recovery timing belongs in the existing
timeline so slow cases can guide later engineering. An actual unresolved
obstacle, user stop, or submission evidence determines the eventual outcome;
a helper's matching limits do not. Shared browser/Simplify responses and the
canonical job-apply skill carry this instruction to the executor.

Missing expected controls now trigger visual recovery explicitly. Shared browser
snapshots automatically attach a masked private screenshot when no enabled native
or Simplify progress control is found, structured/frame inspection fails, or the
owned page's identity is unresolved. The result instructs the executor to read the image with
its harness image tool, inspect frames/overlays/inner scrollbars, and continue.
Capturing without inspecting is insufficient. Screenshot failure remains a
recovery diagnostic, not another finish gate. The same instruction is exposed
in the common screen recovery payload, including Workday, and in canonical skills:
inspect a fresh screenshot and remaining plausible actions before giving up.

iCIMS was already detected by hostname, but previously used the generic exact-path
matcher. Its `/jobs/<numeric-id>/.../job`, `/login` and embedded-view URLs now
compare by scheme, employer host and job id. Slugs and page-mode query parameters
do not change the job. The existing frame router, browser/credential write paths,
target binding and URL comparisons reuse that identity. Stored URL hashes and
history are not rewritten. Start/status includes `platform` and `ats_reference`
while preparing. The iCIMS reference describes the observed posting-to-Email/Next
flow without assuming later stages. iCIMS first inspects the posting/frame and
opens the observed Apply control before using Autofill on application details.

Workday's empty recruiting-source prompt has a scoped fallback after Simplify
settles. It preserves existing answers, follows parent categories to leaves,
uses native pointer selection and scrolls only the associated virtualized popup.
Named source preferences fall back to any other offered source as authorized by
the user. It retries stale/uncommitted choices and returns actual alternatives
plus the attempted path when executor judgment is needed. The existing
`fast_forward` recovery mapping accepts `screen_key` and `source_choice` to
continue with an executor-selected label. Native application entry prefers
Apply Manually and other direct Apply controls over chat. These changes are
included in the September 9 checkpoint. Attempt 44 exercised the flow and
submitted with user intervention; its remaining issues motivated the follow-up
changes below. The checkpoint's subsequent regression results are recorded below.

Workday prioritizes enabled Simplify Continue after settlement. If advancement
cannot proceed, it uses available page Autofill once before manual repair. Its
runner checkpoint uses the logical step, and the shared browser click receipt
uses page identity rather than changing field fingerprints. Polls, new tool
connections and a remaining Autofill button do not reset that attempt. The
shared Simplify boundary prefers settled enabled Continue on every ATS. Autofill
receipts and routing manual repair through first Autofill apply only to observed
Workday. A mistaken reference to Workday's Autofill
panel tab can resolve to the unique observed Autofill This Page action in the
same document. The shared screen handoff exposes approved standard answers on
every ATS. Workday also exposes the full field question behind Select One and
requests executor completion instead of returning a bare blocked result.
Source repair runs only after advancement cannot proceed; it never intercepts
an already selected Continue action. Workday selection metadata includes chips,
including suffixed IDs and chips inside an expanded prompt, instead of treating
an empty search input as an empty answer. Generic select/combobox inventory also
reports selected values. After a manual exception, a new Workday page's first
manual field-repair request uses available Autofill first and reports that the
requested individual field action has not been performed. This routing is
specific to Workday; shared instructions return every ATS to routine filling.
Choosing answers remains executor reasoning governed by the common job-apply
skill, not arbitrary yes/no generation. The human queue is invoked
only explicitly and still reuses policy/exact saved answers. These changes are
included in the requested local checkpoint; the final follow-up changes still
need live validation.

Page recovery is shared across every ATS. `browser` method `reload` deliberately
cancels the current document, so an unknown Simplify writer cannot deadlock the
refresh needed to recover it. The host queues tool calls on the physical browser; historical submission
uncertainty does not prevent recovery. CDP verifies a new document before clearing
the old writer state; subsequent observations govern new form writes. The host's
`restart` operation reuses pause/attach to stop the owned process tree and reopen
the assigned job with the same profile, session and attempt. Shared screen and
Simplify/startup handoffs expose these operations for broken pages and missing
Simplify on Workday, iCIMS, Greenhouse and proprietary sites. Executor judgment
selects further recovery; missing controls are not an application outcome.
Workday additionally recognizes its explicit Something went wrong / refresh
message and attempts one automatic reload. Shared `wait_for_page_recovery` then
observes usable native/extension controls before returning success; document
replacement alone is not application readiness. A transient missing panel returns
loading/waiting instead of a new failure. Fresh recovery responses say to continue
once the old error is gone, not refresh/restart again. New documents reset Workday
page fill receipts; rerenders do not.

The user confirmed attempt 44 submitted successfully, with employer confirmation
and 710.9 seconds recorded, but needed intervention. Its retained logs show the
executor repeated reload and restarted after the original error cleared, source
repair intercepted an enabled Continue despite a selected chip, and manual work
continued on Self Identify until the user requested Autofill. The changes above
address those observed decisions; their new behavior is awaiting live validation.

Startup instructions launch immediately after the canonical skill using
`wait_seconds:0`, overlapping host preparation with ATS-skill reading. They no
longer place ATS reading before browser startup. Optional doctor/repeated config
checks are not startup prerequisites. Metadata records runtime entry/preflight
duration plus host browser-launch, endpoint-ready and employer-navigation times.
These distinguish runtime delay from executor time before the start call; the
runtime cannot measure prompt-to-tool latency on its own. For historical attempt
43, reservation to connected was 8.85 seconds; earlier executor/preflight time
was not captured. The user requested a local checkpoint before Greenhouse work.
Python/JavaScript syntax and diff checks passed. Regression was initially deferred
under the user's prior instruction, then authorized and completed through
Antigravity/Gemini: 695 managed tests passed, with no failures or skips and four
existing deprecation warnings. Test corrections, added coverage and independently
checked evidence are in [September 9 checkpoint regression](REGRESSION_2026_09_09.md).
No new live application was run for this checkpoint or regression. The Greenhouse
follow-up implementation and its synthetic validation are recorded separately below.

The [Greenhouse recovery and application progress plan](GREENHOUSE_RECOVERY_PLAN.md)
retains the evidence and requirements from attempt 45. The implementation adds
shared committed-selection read-back, private email-code handling, dispatch-scoped
employer rejection, authoritative metadata enrichment and semantic progress.
Synthetic validation is distinct from live acceptance; attempt 45 and production
application/mail records were not changed by this engineering work. Detailed test evidence and
remaining live-acceptance limits are in [Greenhouse validation](GREENHOUSE_RECOVERY_VALIDATION_2026_09_09.md).

### Shared recovery and progress contracts

Readiness and browser observations return `next_operation` with the actual
operation and parameter shape. Workday uses `fast_forward`; other forms use
shared Simplify controls. A fresh observation after work begins prevents a stale
startup Autofill recommendation. Readiness time and the first confirmed Autofill
dispatch boundary are recorded separately; `ready_to_autofill_seconds` measures
that gap without calling it model thinking.

The shared form reader associates selected labels/chips with one combobox.
Inventory, question capture, answer history and verification use that reader.
Native SELECT still compares the exact intended label/value. Search input text
and menu highlighting are not commitment. After activation, selection reacquires
a uniquely described control and requires two stable exact reads within the
existing bounded call. Results distinguish execution from answer commitment.
The executor decides recovery from scoped current options; the helper does not
turn a mismatch into an application outcome.

Verification email interpretation belongs to the executor using the existing
Hermes Gmail skill. The LLM selects the relevant code closest to the request
timestamp and polls again if mail is delayed. `hermes_gmail.py` is only a CLI
wrapper for that existing script and selected mailbox credential; it contains
no automatic message-selection or verification algorithm. The Google client
library used by that script is included in repository requirements.

The executor enters its chosen code through ordinary browser fill, or supplies
`value` to `credentials` mode `verification` with observed input refs. The
helper fills the fields and returns commitment without a mailbox lookup or
email-eligibility decision. Group/challenge matching, guessed length/format and
the twelve-field limit are removed. An observed resend control can be activated
without a recognized group; successful activation remains successful if the
next group is absent or ambiguous. It does not require an `email_code` classification.
Group completion reports nonempty fields; `maxlength` is not a minimum code length.
Optional message/timing metadata records the executor's selection. Code fields
remain masked in screenshots and excluded from saved answers. Employer feedback
establishes acceptance or expiry; a helper miss is a continuation, not an outcome.

`submission_state` projects `none`, `not_executed`, `pending`, `incomplete`,
`rejected` or `accepted` from the existing evidence. It is reporting, never form
permission. The ordinary shared submission path observes current required work
and private verification completeness, returns `application_incomplete` for
continuation, and captures confirmation before finishing. Each explicit Submit
can activate the current control once. Previous clicks do not prohibit fields,
mailbox/credentials, answers, reload/restart, pause/resume or another explicit
Submit. A targetless submit observes only. Workday follows the current page on
each advance call. The older Hermes worker's parallel click-history restriction
and mandatory internal resume-upload receipt were also removed.

`record_submission_rejection` remains a compatibility endpoint for precise
historical evidence; ordinary continuation no longer calls or requires it.
Structured dispatch/document/frame IDs retain their exact correlation values
instead of masking numeric UUID segments. Earlier dispatch evidence is preserved
when a new cycle or replacement browser target is observed. Only recorded
success suppresses an ordinary new request. Job status aggregates concurrent
attempts so a later failure cannot erase a successful application.

`enrich_job` and owned `observe_job_metadata` fill missing company/title from one
scoped posting or unambiguous Simplify job card, preserving nonempty labels and
recording provenance/conflicts in the existing job metadata. Normal shared and
Workday observations and answer capture call this path. `backfill_job_metadata`
defaults to preview and validates exact job/attempt association with retained
answer-history evidence; it changes labels only when explicitly applied. No
production backfill is implicit in startup, migration or tests. Queue, session,
focused-job and attempt views read these labels; unresolved discovery shows the
posting link and an honest identifying/unavailable label.

`progress(stage,activity,task_id?,state?,evidence?,next_step?,source?,action_id?)`
uses the existing event ledger and supplies valid event ID/time. Completion needs
evidence. Strict externally supplied `event` identity/time requirements remain.
Shared field actions, saved-answer application, required-question requests,
private credentials, Workday source/steps and submission emit stable stage/task
context with question labels only. Actions retain this context at start; outcomes
verify commitment independently of tool dispatch. Reports project all events
before limiting completed tasks. Unresolved tasks stay visible, recovered errors
close, raw chronology stays under Debug details, and refresh preserves expansion.
Elapsed wall time, explicit input waits and unioned action intervals are separate;
unobserved gaps remain unattributed. Legacy attempts show Details not recorded
when semantic evidence is absent.

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
are read-only successful-submission sources; unfinished history does not suppress
a new request. Missing configured sources fail closed. There
is no cwd-selected database or second outcome store. `prepare_local` checks the
instance and makes an integrity-checked SQLite backup before migration 17,
which removes same-job uniqueness restrictions. Existing accounts, attempts and submissions remain. Transactions are short
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
| Application question | Full required question, offered choices and context; exact job identity + candidate scope |
| Question answer revision | Immutable human answer/source/evidence/time; current revision uses optimistic concurrency |
| Answer retry request | Durable queued/started handoff to an ordinary harness; no model or browser launched when saved |

Account lookup precedes authentication and is scoped to candidate plus verified
portal namespace. `creation_pending` records dispatch intent; it does not prove
that an account exists. A creation click proven `not_executed` by the owned browser
can move its own attempt's pending account to `creation_not_executed`, retaining
the dispatch reason and allowing bounded recovery. Uncertain dispatch remains
pending for reconciliation. Workday uses a bounded retained-credential sign-in
check for pending creation, including a prior attempt, without recreating the
account. The native email chooser can recur once after creation. Employer
evidence establishes `created_unverified` or `confirmed`. Screen handoffs include
state, timestamps and last attempt ID.

Workday account creation and sign-in use the native retained-credential routine.
The shared Simplify observer/click boundary routes Workday authentication back to
`fast_forward`; a `credential_evidence` string cannot authorize extension account
filling. Stop/Cancel still settles an active extension operation. The runner keeps
the short blank-page transition after account creation in authentication and
returns application pages to Simplify after verified sign-in. This fixes the
attempt-34 recovery path: the executor supplied a credential reference to
Simplify's Sign In & Autofill, which does not establish the password it uses.
The existing private filler also retains a document-local credential receipt.
Routine and mapped Workday auth pass its opaque token to native activation.
The shared pointer validator rechecks and, if necessary, restores the retained
values after hover, immediately before the mouse press. The CDP result, account
checkpoint, helper report and timeline retain only match/refill booleans. No
password, password hash or reusable credential value enters those records.
This closes a reproduced late-autofill gap; it does not prove that Simplify
overwrote the password in the historical attempt.

Workday privacy acknowledgements such as "I have read and understood the Privacy
Policy" are recognized even without HTML required markers; marketing and job
alerts retain their existing exclusions. Manual auth-button clicks use the
matching same-form `click_filter` pointer surface, as routine auth already does.
A browser click may omit `page_signature`: the runtime still observes the owned
page and resolves the current ref before dispatch. An explicitly mismatched
signature returns the fresh screen and recovery guidance. These corrections
address Rakuten attempt 61's consent miss and manual-click failures; their
implementation alone is not evidence of employer account acceptance.
Synthetic regressions cover native creation/sign-in across a blank transition,
rejection of extension credential references, a login form appearing between
observation and click, and credential replacement after fill or hover while
preserving case-insensitive email matching. Validation: 671 managed tests passed, with four dependency
deprecation warnings; this does not establish live employer sign-in acceptance.

Job identity and browser ownership are distinct. The shared Workday parser uses
host, career site and the complete requisition (including suffixes such as
`R100_1`); locale, display location/title and application child routes do not veto
the same job. History, target checks and confirmation use that identity. Stored
URL hashes/history are not rewritten. An owned portal login is allowed; an
explicit redirect must identify the assigned job. Browser observation checks the
full URL before and after reading; public URLs omit authentication queries.
`different_job` and `identity_unresolved` refuse the affected form write while
preserving owned snapshots/screenshots and navigation back to the assigned job.
Navigation during observation prevents quiescence.

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
   created before readiness; repeated start for the same request returns that
   session/target. A fresh request starts a new attempt under RETRY_POLICY.
3. `ensure_host` automatically launches the no-model host. It checks ownership,
   launches the configured browser, verifies actual process arguments, profile,
   mode, endpoint and fresh operable target. It observes Simplify on the application
   surface; slow loading/missing panels return setup recovery on the same target.
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
   confirmation means inspect the current form and continue actual remaining
   work. Click history does not prohibit another explicit Submit.

Native Hermes jobbot operations are convenience calls to the same functions.
Hooks can record observed provider/model/effort; requested settings remain
separate. CLI-only model evidence is unknown unless supplied by the actual harness.

### Standard application request

Change only the URL. The canonical skills select the available ATS procedure;
the user should not maintain different prompts for Workday, Greenhouse or iCIMS.
An ATS appearing in this prompt is not a claim of verified support.

```text
Apply to [JOB_URL] using this repository's canonical job-apply skill.

Detect the application platform automatically—Workday, Greenhouse, iCIMS, or another ATS—and follow its available repository procedure. Use my configured approved profile, resume, retained credentials, managed runtime, and Simplify.

I authorize submission. Continue through supported recoveries and handle required fields using approved facts. Ask only for an unresolved verification challenge or missing required information. Do not change code, skills, or configuration.

Follow the canonical submission and confirmation procedure without adding a final resume or field audit. Inspect the current form and confirmation after an uncertain click; continue unfinished work and submit the current form when appropriate. A new user request can start a fresh attempt unless success is recorded.

Report the outcome and evidence source—or the exact unresolved blocker—with total elapsed time and session/attempt IDs.
```

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

New sessions for previously attempted jobs reset the assigned employer origin's
browser storage before navigating. Session reservation derives
`fresh_employer_storage` from related job/attempt and stopped-session history, so
retry commands, queued answer retries and new conversations follow the same rule.
After verifying its owned browser/profile, the host closes restored page tabs and
uses the page's [CDP Storage.clearDataForOrigin](https://chromedevtools.github.io/devtools-protocol/tot/Storage/#method-clearDataForOrigin)
with `storageTypes:all` for the assigned job URL's origin. It records the cleared
origin in readiness. Cleanup failure stops startup before employer navigation.
This shared path has no ATS-specific branch; first attempts and paused-attempt
attachments retain their storage. Simplify's extension and separate login origin
remain authenticated. Account records, credentials, answers and submission history
are independent of browser storage and are never reset by retry.
This is an origin-scoped reset, not a new empty browser profile: unrelated origins,
including separate third-party identity-provider origins, are preserved.

Validation passed all 694 managed cases before removing 15 redundant ATS URL
combinations. That storage-cleanup checkpoint collected 679 cases; the eight retained retry cases
passed again after that test-only pruning. Browser lifecycle fixtures now wait
for actual pause acknowledgement and continue a normal authentication `waiting`
response, retaining their account-count, ownership and confirmation assertions.
The primary engineering agent ran these checks. Routine delegated validation uses
the existing authenticated Antigravity Gemini 3.8 Flash Medium workflow; a requested
Antigravity rerun has not occurred while its launch awaits approval.

The two Workday entry dialogs are separate from cookie cleanup. The fast runner
can select the posting's Sign In control for a recorded account or pending
creation; Apply opens the application-method chooser. Clearing cookies does not
change that account strategy, confirm account creation or unlock an employer
account that rejects manual sign-in.

Pause/stop acknowledgement follows actual owned process-tree termination and
abortion of active actions. Startup observes pending control before connecting.
Explicit attach requires completed pause and creates a fresh target for the new
driver on the same attempt; the previous driver is rejected. Explicit retry stops the
particular session through shared control, then starts a fresh attempt. A new
request can use another workspace without stopping the prior session. An old
unresolved submission dispatch does not prevent this new request. After a crash, a replacement host
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
the same request. Paused sessions retain their physical slot until explicit
stop or retry replaces that session. The posting and candidate account are not
exclusive resources; another configured browser can use either. Same-job successful submission suppresses duplicates
across email identities. Earlier uncertainty does not. concurrency_limit caps use.

### Headless execution and visual evidence

The pointer validator reads the browser's rendered element bounds and
`document.elementFromPoint`, then the CDP client dispatches browser input. This
does not require a visible desktop cursor, an on-screen window or LLM image
inspection for every click. A screenshot is an available diagnostic for ambiguous
UI, not a prerequisite for routine DOM/pointer validation. Screenshot pixels alone
also cannot identify an invisible HTML click layer; control metadata is needed.

`WorkspaceHost.start_browser` already supports `--headless=new` for a headless
workspace; headed workspaces request maximization. Modern Chrome shares its
headed/headless implementation, as described in the [Chrome headless documentation](https://developer.chrome.com/docs/automation-and-testing/headless).
The existing `test_native_pointer.py` exercises native pointer input in an isolated
headless browser. These capabilities do not prove the configured Brave/Simplify
workflow, authentication challenges or complete employer applications work
headlessly. A future headless trial must verify the extension, viewport and
application flow separately; no mode/configuration change was made in this review.

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
gap. Readiness reports observed panel availability; slow loading or a missing
panel returns `startup_recovery` with the operable owned target retained. Process,
profile and target ownership still must be proven. The executor verifies actual
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
| application_runtime.py | Shared request identity, start/retry and stop/pause lifecycle; early platform/reference guidance, scoped browser actions, automatic masked-image recovery after snapshot misses, field attribution, Autofill timing and answer/metadata capture |
| managed_sessions.py / migrations 15 and 17 | Session and physical workspace allocation, first-attempt/reattempt metadata and history-derived storage cleanup; same-job and account-use exclusion removed |
| workspace_host.py / workspace_process.py | Windows lifetime/readiness timing, same-attempt restart through pause/attach, employer-origin cleanup before retry navigation, queued JSON dispatch on the physical browser; no model or five-second busy veto |
| managed_client.py / managed_cli.py / managed_api.py | Two transports over shared methods; HTTP auth retained |
| managed.py / managed_runtime.py / managed_events.py / managed_views.py / managed_continuity.py | Existing policy/actions/events/duplicates consult local lifecycle or explicit legacy ownership |
| managed_identity.py | Workday host/site/full-requisition and iCIMS host/job-id comparison, history equivalence, application scope and diagnostic match states; existing frame router, runtime, credentials and binding callers share scope matching |
| managed_shared.submission_state / submission_pending and managed_events._submission_state / _submission_pending | One per-attempt evidence projection from existing ordered events; evidence reporting only; accepted alone suppresses a new requested attempt |
| workday_fast.py | Bounded Workday supervisor, direct application entry and source-choice recovery; native and CLI call the same advance function |
| workday_auth.py | Workday account decisions inside the supervisor; shared account record/coordination and private filler, no model or password storage duplication |
| cdp_client.py | Exact-target connection, verified document reload, structured evaluate_function arguments, and validated native pointer activation shared by the runner and local browser recovery |
| browser_controls.py / browser_helpers/form_controls.js | Shared form reader including Apply, committed-selection verification, posting metadata, private code groups and remaining_submission_work; iCIMS entry guidance; used by submission, browser runtime, answer capture, credentials and Workday |
| browser_frames.py / cdp_client.py channels | Shared DOM-owned application document routing below the existing browser API, isolated worlds, stale-ref rejection and root pointer mapping |
| managed_questions.py / migration 16 | Durable required questions, exact human answers/revisions and retry requests in the same database; browser-independent, success-only history suppression shared with ordinary starts |
| application_answers.py | Interprets profile salary/privacy preferences and retains best-effort private question/answer history from shared browser writes, mapped recovery and Workday advancement; contains no personal answer defaults |
| submission.py / browser_helpers/submission_observe.js | One activation per explicit call, current incomplete-form continuation, retained dispatch evidence and native/Simplify confirmation; local browser and Workday callers |
| simplify_boundary.py / browser_helpers/simplify_observe.js / simplify_click.js | Official extension observation, actuation, settlement and forward-first policy |
| browser_helpers/workday_observe.js / workday_click.js | Workday steps/errors/attachment/employer-confirmation and observed controls |
| browser_helpers/workday_source.js | Workday-only recruiting-source field/menu association, live option inventory and virtualized-menu scrolling; workday_fast drives pointer actions and verifies commitment |
| managed_credentials.py / managed_documents.py / hermes_gmail.py | Selected account-field filling, executor-supplied code entry without group/format permission, existing Hermes Gmail CLI wrapper, code screenshot masking and selected uploads; workspace host, legacy plugin and Workday callers |
| managed_shared.py / managed_events.py / managed.py | Common submission resolution, strict evidence ledger, progress convenience, existing job metadata enrichment and previewable backfill |
| managed_reports.py / managed_sessions.py / managed_views.py | Stage/task projection from the same events and actions, explicit waits/action overlap, shared labels and first-Autofill timing |
| hermes_plugin.py / integration entry | Convenience, actual conversation/model and observed request-turn identity, current session binding after retry, optional messaging capability metadata and observed human-reply provenance; no alternative form logic |
| managed_hermes_worker.py / native_hermes_session.py / hermes_adapter.py | Existing explicit legacy worker integration; never launched by local start |
| static/jobbot.html / jobbot.js / jobbot.css | Shared posting labels and stage/task progress, persistent expansion and collapsed technical debug, independent application controls |

Common policy is job-apply v0.5.9; Workday policy is workday-simplify v0.3.16, in
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
retain that page until completion, requested Stop or the configured maximum
runtime; there is no additional two-minute inspection deadline. Proven
`not_executed` dispatch or a fresh dispatch-scoped employer rejection permits
recovery in the same attempt. An intent with no
dispatch result remains uncertain. Reconcile supports the native plugin and portable CLI, records a
separate source/timestamp event, and preserves historical completion/duration.
Headed browser startup requests and verifies maximization; no automatic refresh.
One background host owns each occupied workspace, with independent parallel
session cleanup. It exits after a completed session response is delivered.

Enabled Simplify input prompts can override a cosmetic spinner after stable
observation, while real unfinished helper writes remain exclusive. Native
takeover remains separate from extension input permission. Shared form helpers
verify values and return ambiguous menu/coverage evidence instead of guessing.

An unknown writer can settle through fresh stable extension evidence (including
explicit unsupported/idle state), or the observed Simplify Stop/Cancel autofill
control via `browser simplify action:stop`. This narrowly scoped cancellation is
available to the owning local host while the extension state is active/unknown;
an unended host write still excludes another write. Stop does not declare idle:
the boundary observes stable settlement. Missing or unrecognized stop controls
retain uncertainty and return inspection. Inaccessible-frame diagnostics affect
that document's controls; readable documents retain their own routing/validation.
Local semantic timing remains telemetry and does not veto an otherwise valid
write. Legacy configured strategy checks remain on their existing callers.

After one available page Autofill settles, Workday prefers enabled native Continue in `needs_review` so that a populated
source answer such as LinkedIn does not reopen Simplify's review menu. At authorized
Review it submits without another resume or field audit. Missing attachment
evidence is not a final-submit gate. The same-portal
`jobTasks/completed/application` route is a read-only confirmation surface;
fresh approved Simplify success is sufficient without waiting for employer mail.

The existing private spool stores `answers/attempt-<id>.json`, captured during
filling and advancement. It includes company, ATS, portal namespace, job identity,
attempt/session, full question and answer, timestamp, source and available answer
basis. Repeated read-back is deduplicated; changes remain in history. Missing basis
is explicit, not inferred from a favorable answer or promoted into profile facts.
Credential, verification-code and financial-identifier controls are excluded.
Timeline checkpoints and browser results link the artifact; this does not add
another database or a final-review pass. Audit errors are reported separately
and never imply that an executed form action is safe to replay.

### Shared embedded forms and human answers

The harness uses one `browser select`/`fill`/`check` interface. Observed refs carry
document identity internally; no model chooses an iframe or Workday handler.
Non-Workday inventory includes visible DOM-owned application iframes, including
cross-origin OOPIFs, without looking for other tabs. Discovery uses the assigned
employer page's explicit application embed and rejects contradictory requisition
IDs. Workday keeps its existing observer and fast runner. Same-origin and
cross-origin native selects, ARIA menus, uploads, private credentials, answer
capture, credential masking and Simplify actions share this routing.

Refs survive a new CDP connection to the same document, but not navigation,
replacement or changed ownership. Native pointer input validates the child and
every parent iframe hit target before dispatch; overlays cannot be forced through.
Traversal is bounded to four levels, twelve application frames and the first
24 iframe owners per document. Transforms/zoom that prevent reliable coordinate
mapping and unverified redirects return diagnostics. This is shared plumbing for
recognized embedded forms, not a claim that every custom widget or ATS works.

Submission arms the parent and selected embedded document before the single
intent/click. Child confirmation is tied to its original frame ID and application
URL, including after a normal scoped redirect. Replacement frames and conflicting
query requisitions cannot supply proof. Transient messages are retained. A repeat
call after uncertain dispatch only observes; it never clicks Submit again.
Custom employer `/jobs?gh_jid=...` and `/form?gh_jid=...` aliases now also match in
intake and read-only history; meaningful unknown query keys remain distinct.

Missing facts use an additive durable queue, separate from the private observed
answer audit. `browser request_answers` first applies approved salary/privacy
policy and exact saved human answers, then queues only the remaining missing
required questions from current controls. Simplify and the executor use approved
facts before invoking that queue. Optional answer-history/progress-event errors
remain diagnostics; action ownership, dispatch intent and outcomes remain mandatory.
Failed menu interaction is a technical diagnostic, not a human question. Answers
are scoped by candidate, verified job identity, exact field/question/options and
page/section/document. Reordered or changed choices are not guessed equivalent.
The current answer can change through an optimistic revision; earlier answer
records remain immutable. Choice objects include both value and label, avoiding
duplicate HTML-value ambiguity. Passwords and verification/financial identifiers
are excluded. Approved facts are never reconstructed from a resume during a run.

`human_input` is a harness capability declaration, defaulting to no messaging and
the dashboard queue. The core imports no Discord or Hermes service. Hermes derives
availability from its actual conversation platform or offered messaging tool;
its `answer` bridge requires an observed user turn newer than the question and
its last answer, and stores a turn ID/hash as provenance. Other harnesses can
declare the same capability at start or use the dashboard without messaging.
Capabilities do not grant permission to send a message or choose a recipient.
CLI answer writes require explicit user-reply evidence. Late replies only update
answer data; they do not reclaim a stopped browser.

`park_questions` records a blocked attempt and requests stop. Host acknowledgement
releases browser/portal ownership and the slot, unlike pause. The dashboard reads
the same database and offers Save answers, Save and queue retry, and a batch queue
button. Saving never starts a browser. `answer_retries` lists ready requests for
the configured candidate; an ordinary authorized harness starts each with the
returned job/request IDs. `session_connected` marks its request started. No
scheduler or extra LLM is created. `browser apply_answers` checks current refs and
the exact question before applying a saved answer and recording its provenance.
Same-job recorded success suppresses retries across email identities. Actual
browser ownership must end before queueing. Uncertain history remains retryable;
queueing does not rewrite or reconcile the earlier submission evidence.

### Learning from successful and blocked applications

Use the existing managed attempt ID to join outcomes/timing, code and skill
versions, actions/events and the private spool artifacts. Keep the design/change
history in RUNTIME_SIMPLIFICATION_LOG rather than relying on an engineering chat.
Keep individual failure/recovery narratives in the managed database, linked to
their attempts; design documentation explains the resulting architectural choices.
Record both successful and blocked applications: successful work establishes
which recovery and answer paths were useful, while failures identify unmet cases.

| Existing record | What it contributes |
|---|---|
| Managed jobs, attempts and sessions | Employer/ATS/job linkage, final status, evidence source, original timing, driver and source version |
| Actions and event timeline | Stage, selected operation, coarse action result/duration, recovery reason and verified milestones |
| Private `answers/attempt-<id>.json` | Observed questions/answers, company and portal metadata, changes, provenance and any recorded answer basis |
| Private submission capture and screenshots | Observed native/Simplify confirmation or remaining uncertainty; source stays explicit |
| Private fast checkpoint and executor tool results | Detailed dispatch and control evidence when retained; a checkpoint is mutable working state, not a complete immutable action history |
| Retrospective operator checkpoint events | Per-attempt diagnosis, attempted recovery, evidence, resolution and provenance without rewriting execution history |
| Implementation log | Architecture, implementation rationale, checkpoint validation and deferred design proposals |

For comparisons, identify the failure mechanism (for example, a covered control
with proven non-dispatch), not only the final generic blocked/budget-limit label.
Include the attempted recovery, whether input actually dispatched, latency and
result. Separate repeated attempts on one job from independent employers/jobs;
otherwise retry-heavy debugging can distort the apparent incidence and success
rate. A submitted application is not a hiring acceptance. Later employer replies
belong to separately sourced recruiting outcomes, as described below.

Current coverage is incomplete: `action_end` records coarse status, the fast
checkpoint retains the latest dispatch, and some details remain only in executor
tool results. Historical missing answer bases and dispatch reasons remain missing.
Recovered diagnoses are stored as operator checkpoint events with
`operation:attempt_diagnosis`, `source:operator_postmortem` and structured
`category`, `error_type`, `reason_code`, `evidence`, `fallback_reason` and
`resolution` fields. Annotation timestamps describe the later review, not a
fabricated execution-time observation. Post-completion events have `stale:1` to
avoid creating active progress; they still appear in the full attempt report.
They do not alter the original outcome, timing, account state or action history.
No automated cross-attempt analysis or universal detailed failure-event capture
is claimed; these retrospective notes supplement the existing automatic records.

For a read-only review of the selected managed database:

```sql
SELECT attempt_id, recorded_at,
       json_extract(payload_json, '$.error_type') AS diagnosis,
       json_extract(payload_json, '$.evidence') AS evidence,
       json_extract(payload_json, '$.resolution') AS resolution
FROM managed_events
WHERE actor = 'operator'
  AND json_extract(payload_json, '$.operation') = 'attempt_diagnosis'
ORDER BY attempt_id, recorded_at;
```

If review shows recurring evidence loss, add the minimum sanitized fields to the
existing event/report path before considering another data store. Do not copy
passwords, mail bodies, full profiles or unrestricted DOM dumps into Git/logs, and
do not replace historical outcomes merely to simplify analysis.

Follow-up work: schedule confirmation-email correlation about 30 minutes after
submission through the existing Hermes Gmail adapter (employer, requisition/title,
recipient and attempt time; deduplicate by message ID and never treat delayed mail
as failure). Keep accepted on-page success final without waiting for this follow-up.
Later extend the same correlation to rejection, interview and recruiter-response
updates, retaining each message's source/time separately from the original
submission outcome. Ambiguous mail should await classification, never update a
different requisition. These email automations are deferred, not implemented here.
Add a candidate profile
editor exposing advertised minimum/maximum choice, fallback amount, currency,
period and routine consent; keep preferences in editable data and snapshot the
chosen policy for each run. Minimum-range selection is a future option; this
checkpoint implements the approved maximum/fallback policy.

## Verification boundaries

### Historical design: shared embedded forms and unresolved questions

The following is the retained design rationale from before the embedded-form and
answer-queue checkpoint. Current implemented behavior is described above; this
historical plan is not the execution contract or a live acceptance claim.
The existing dropdown operation supports native selects and associated ARIA
menus in the document it can inspect. A form inside another frame is a separate
observation/action-routing gap: adding more option-label matching alone will not
make those controls reachable. Employer-hosted Greenhouse validation exposed
that boundary; detailed application evidence remains in managed attempt reports.

The next delivery should extend the existing shared browser/form helpers with a
small frame-aware adapter. Keep Simplify as the bulk filler and retain the
existing application runtime, browser profile, assigned target and lifecycle.
This is not a separate Greenhouse application runner or a per-employer script.
Use the same form operations for controls in the top document and in a verified
application frame. Same-origin and cross-origin frames are separate test cases;
the latter cannot be traversed using ordinary parent-document selectors.

| Responsibility | Proposed scope and boundary |
|---|---|
| Frame discovery and routing | Associate the frame with the owned parent target and verified employer/requisition. Do not select arbitrary frames, ads, challenges or another job solely because they contain inputs. |
| Control references | Bind each observed ref to its document/frame and observation. Resolve selection, checking, filling and pointer validation in that document; reject detached, navigated or ambiguous frames. Keep Simplify panel refs distinct from employer-form refs. |
| Value operations | Reuse native-select and associated-menu behavior, including exact option matching and read-back. Preserve frame offsets and coverage checks for pointer input; do not substitute guessed coordinates or force clicks. |
| Submission and evidence | Route the observed frame control through the existing one-click submission boundary. Arm confirmation capture before dispatch, retain parent Simplify and native frame evidence with their sources, and do not automatically replay an uncertain dispatch within the same attempt. A new requested attempt follows the shared retry policy. |
| Redirects and job identity | Recognize the same requisition across verified posting/form routes, including meaningful query identifiers. Reject conflicting job identifiers; do not authorize every same-host path. Link verified aliases through the existing identity system without rewriting historical jobs. |
| ATS recognition | Use observed embedding evidence for custom hosts. Recognition may select ATS-specific procedures, but generic form operations should not depend on a Greenhouse hostname or employer name. |
| Answer policy | Present approved facts, explicit user answers and existing answer defaults consistently to the executor. Preserve contrary facts, question-type boundaries and configured exclusions. Record whether an answer came from a fact, user instruction or approved default. |
| Routine privacy consent | Extend the shared policy from checkboxes to observed select/menu acknowledgments. Require an unambiguous consent option and continue excluding marketing and job alerts. |
| Required questions | Distinguish native required/validation evidence from Simplify review warnings. Leave optional unanswered fields alone unless separately requested; use the answer type rather than applying a yes/no default to a country or text question. |

Workday retains its existing page recognition, authentication/account sequence,
mapped recovery and fast runner. Shared changes can still affect Workday, so
preserving that dispatch path is not sufficient evidence of compatibility.
Regression coverage must exercise its use of the shared helpers. Do not fold the
deferred Workday authentication exception into this delivery.

Before implementation, add focused failing regressions using synthetic forms and
isolated browser profiles, never live employer applications or production data.
Cover top-level forms, same-origin frames, cross-origin frames, ambiguous frames,
frame rerenders/navigation, populated selections, consent dropdowns, required
versus optional questions, parent overlays and frame offsets. Include verified
same-job redirects and different-job query rejection. Exercise single submission,
native/extension confirmation and uncertain-dispatch protection with fake
employer endpoints. Run relevant Workday authentication, mapped recovery,
pointer, answer-history and confirmation checks, then one final managed suite:
`.venv/Scripts/python.exe -m pytest tests/jobbot_v1 -q`. Browser fixtures establish
mechanism coverage; later ordinary authorized applications establish live ATS
acceptance. Runtime/skill changes must happen outside application benchmarks.

A second delivery can add a shared **Needs your answer** review queue. Current
answer history records observed answered questions; it is not a durable queue of
unanswered questions/options and the dashboard has no response editor yet.
Persist the exact unresolved required question, response type, observed options,
job/candidate context, reason for escalation and subsequent user answer with
provenance in the existing managed data/artifact system. Use approved facts and
applicable defaults before asking. Do not treat a control-access failure as a
request for the user to invent another answer.

The dashboard is the durable review interface: **Save answers** leaves the job
for a later batch; **Save and retry** requests an ordinary managed continuation.
Keep unresolved jobs out of that batch. Match saved answers to fresh questions
and options; old DOM references must not survive into a new session. Answers are
application-scoped unless the user explicitly approves broader reuse. An
uncertain prior submission remains truthful history and can receive a fresh
answer-driven attempt unless successful submission is recorded.

Hermes Discord can be an optional notification/reply channel over those same
question records, rather than a separate workflow or bot service. Deployment
credentials and channel routing remain in the private Hermes configuration.
Correlate authorized replies with a specific question and application. A quick
reply can continue an owned, quiescent live session; otherwise preserve the
question and release the workspace through the managed lifecycle so unrelated
applications can proceed. A chat message saying "paused" is not a lifecycle
transition, and a paused session currently retains its workspace slot. Define
the bounded waiting/parking behavior as part of that second delivery.

Implementation documentation and PRs must distinguish proposed, fixture-tested
and live-verified behavior. Identify the motivating Greenhouse validation and
related attempt IDs in the PR; keep full employer-specific diagnoses in managed
history. Update this helper map and canonical instructions when actual caller
responsibilities change. No Discord notification or application retry is
authorized merely by documenting this design.

### Current implementation

Snapshot and Workday recovery share one native/official-extension inventory in
workday_fast.observe_page/screen_inventory. workday_observe retains unique
semantic refs across routine rerenders; the existing private filler and native
click helper accept those exact mappings. fast_forward recovery performs a bounded
mapped fill/verify/action/observe step in its existing connection, then resumes
routine execution. Mapped decisions and possibly-executed actions persist in the
existing private checkpoint; actual authenticated form access confirms the account.
No new service, migration or execution framework is involved. Workday sign-in
uses native retained credentials; the shared Simplify click path rechecks for
authentication before acting. Simplify account actions and a credential-reference
string cannot replace that routine. The older Simplify sign-in interface remains
for other ATSs and distinguishes employer from extension login.
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

Selected sign-in controls may contain email only, password only, or the whole
form. A revealed password input is supported. Existing candidate/account identity
matching remains. Actual missing controls, unavailable saved
credentials and browser failures remain reported; they are helper diagnostics,
not application outcomes. The [error-return review](ERROR_RETURN_REVIEW.md)
records these removals and the retained checks with their reasons.

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
# Queue and VM additions — 2026-09-15

The current runtime can now be called by `job_applier.queue_runtime`, a separate
sequential dispatcher. `managed_queue` owns explicit queue records (migration 18),
`application_brief` assembles one fresh job's skill/mail/vision/Simplify context,
and `harvest_runtime` launches a separate discovery task. The canonical apply
runtime and its ownership/evidence rules remain authoritative; legacy HTTP
accept/claim does not become the new local dispatcher.

`hermes_gmail.mailbox_handoff` now describes either the existing Gmail wrapper or
the selected Himalaya account. It does not itself authenticate/fetch mail or claim
SMS support. `workspace_linux` provides Linux process-group supervision and private
socket/profile inspection; Windows Job Objects remain unchanged. See
[Queue and VM runbook](QUEUE_AND_VM_RUNBOOK.md) for exact boundaries and rollout.
