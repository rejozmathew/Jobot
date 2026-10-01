# Evidence-driven application improvements

Engineering iterations use `self-improvement`, derived from
`codex/runtime-simplification` on September 27, 2026. Work in the original checkout.
The Codex daily task reviews the previous America/Chicago calendar day at 09:00.
The application executor itself does not edit code or deploy changes.

For each review, preserve a private report with the snapshot time, deployed source
commit/file manifest, attempt and dispatch counts, confirmed submissions, unique
jobs, elapsed time, retries, executor failures and portal breakdown. Separate
failures of the model/runtime from employer obstacles and user interventions.
Attribute attempts spanning a deployment to their actual source/version evidence;
do not infer performance gains from fixtures or a partial day.

Use exact recorded evidence to propose a bounded change. Prefer a shared fix when
the same cause applies across portals. Add a synthetic failing regression, implement,
review the diff, and delegate routine validation to authenticated Antigravity
`gemini-3.8-flash-medium`. Independently inspect logs/JUnit and run the required
final `python -m pytest tests/jobbot_v1 -q` suite. Do not use live applications as
fixtures or manufacture production outcomes for tests.

The initial deployment disables optional automatic background memory/skill reviews
in the selected Ubuntu Hermes profile to reduce competing model requests. This is
a profile-wide private configuration change, backed up separately from Git. It does
not cancel an already running review or reload the model. The installed Hermes
version also suppresses bare `/refine`; explicitly focused refinement and separate
review delegation remain available. Restore the backed-up setting to reverse it.

Commit each validated iteration and push the existing remote's `self-improvement`
branch. Deploy only intended files to the authoritative Ubuntu runtime after the
current application finishes. Pause pickup when needed, retain its prior state,
back up changed files, verify prior hashes and preserve unrelated deployed changes,
private configuration, databases, accounts and browser profiles. Reload affected
idle services, verify source hashes/services, restore pickup and record the deployed
commit, timestamp and file manifest privately. Preserve active applications through
the existing lifecycle; a deployment is never a reason to terminate one.

## Run labels and public notes

Use a sequential run number and the America/Chicago review date, starting with
the first explicitly numbered run below. Check existing run notes and remote tags
before choosing the next number. Commit subjects use
`Self-improvement #NNN (YYYY-MM-DD): <concrete change>`. Multiple checkpoints for
one review share its run number.

Publish an annotated tag `self-improvement-NNN-YYYY-MM-DD` pointing to the exact
validated, deployed code commit. Its description and an entry below explain the
problem, behavior changes, validation, deployment time and remaining limitations.
Keep the same run label, source commit and tag in the private Ubuntu deployment
record. A documentation-only follow-up records its separate commit without
changing which executable source was deployed. Preserve published history and
existing tags; append corrections instead of moving a run's identity. Detailed
job records, account information, answers and transcripts remain private.

### Self-improvement #001 — 2026-09-28

Code commit: `67a22fc2ad3bdca663f5e58aac9105b476b7cc24`.
Tag: `self-improvement-001-2026-09-28`.
Ubuntu deployed: September 28, 2026 at 10:01:23 America/Chicago (15:01:23 UTC),
after the active application finished. GitHub branch: `self-improvement`.

Delayed form navigation could lose the owned application route after a helper's
browser connection closed. The iCIMS posting Apply path also bypassed the shared
navigation handoff. This run:

- Retains verified same-origin main-document navigation history across helper
  connections, including delayed document changes and push/replaceState.
- Routes iCIMS Apply through the shared same-tab/popup handoff and refreshes
  embedded-form context and derived profile/email facts after adoption.
- Uses fresh final-submit control classification consistently for Autofill,
  audit and the existing review/submission path.
- Updates the integration test to discover the installed Hermes interpreter and
  isolate its temporary home; production Hermes configuration is unchanged.

Validation: the final managed suite passed 1,055 tests with 111 skips; focused
route-history and iCIMS/Autofill suites passed 67 and 52 tests respectively.
Ubuntu synthetic validation passed all 132 tests. All 80 cumulative deployed file
hashes, authenticated health, dashboard access and services were verified, and
queue pickup was restored. Private configuration and the existing pause behavior
were preserved. The first numbered label was added after the code had already
been published; the original code commit remains unchanged.

Cross-host SSO account-principal handling remains a separate issue. This release
does not claim a measured increase in submission rate or a reduction in GPU use;
those require post-deployment application evidence.

The daily task can make these tested improvements under the operator's standing
authorization. New execution restrictions, refusal conditions or retry limits still
require explicit approval. If the evidence does not support a fix, record that fact
and continue observation. Serving-engine changes require engine-side evidence or a
synthetic reproduction; a decoder error alone does not prove GPU memory exhaustion.

### Self-improvement #002 — 2026-09-28

Tag: [`self-improvement-002-2026-09-28`](https://github.com/rejozmathew/auto-job-applier/releases/tag/self-improvement-002-2026-09-28).
The annotated tag identifies the deployed code commit and records the verified
Ubuntu deployment timestamp and post-deployment checks. The matching private
Ubuntu manifest retains file hashes and backups. GitHub branch: `self-improvement`.

Opening the dashboard over LAN HTTP exposed a browser compatibility bug:
`crypto.randomUUID()` requires a secure context. Manual Add Job failed while
constructing its payload, before sending an intake request. Four queue/start/retry
paths used the same unsupported call.

All five actions now share a request ID function. It uses native `randomUUID`
where available and otherwise creates UUID v4 identifiers with the browser's
HTTP-compatible `getRandomValues`. Distinct actions receive distinct identifiers;
authentication retries retain the original request identity. This changes no
application permissions, queue policy, recovery limits or operator deadlines.

Validation reproduced six failures before the fix. All 51 focused tests passed,
and the final managed suite passed 1,066 tests with 111 skips. Synthetic dashboard
tests exercise all five actual handlers with and without native UUID support and
verify authenticated retry identity. No live application was used as a fixture.

Deployment updates the dashboard asset, synthetic regression and these notes at
an idle application boundary. The dashboard serves the asset directly from disk,
so no service restart is needed; existing browser tabs must reload. Ubuntu fixture
results, served-asset hash, service health and cumulative file verification are
recorded in the tag and private run record. This fixes dashboard request failures;
it does not establish an increase in employer-portal submission success.

### Self-improvement #003 — 2026-09-28

Tag: [`self-improvement-003-2026-09-28`](https://github.com/rejozmathew/auto-job-applier/releases/tag/self-improvement-003-2026-09-28).
The annotated tag identifies the validated code commit and verified Ubuntu
deployment time. Matching private run records retain test reports, file hashes
and rollback copies. GitHub branch: `self-improvement`.

Recent Greenhouse helper calls returned `invalid_question` when an observed
control had a missing or oversized question identity. This stopped the whole
residual batch and sent supported fields back to the model. The runner now
finishes the supported fields and returns scoped metadata diagnostics without
field values. Unreadable required, rejected or explicitly planned controls still
receive recovery; an unrelated optional control no longer aborts the batch.
Conditional changes refresh the diagnostic's required/rejected classification.
Exact question bindings, verified answer history and ownership checks remain in
use; labels and question identities are never invented or truncated.

An iCIMS synthetic fixture reproduced a second premature handoff: Continue's
response arrived after the existing 150 ms pause. The runner now observes an
intermediate click for up to five seconds, resuming that window across helper
connections without an automatic duplicate click. The operator explicitly
approved this observation window. Incidental optional-field and footer changes
do not count as a response. A new step, document or actionable validation resumes
normal handling. An unchanged page clears the receipt and returns the existing
recovery handoff; later retries remain possible. Helper slices, operator stop and
the overall application deadline still apply.

Available Simplify remains first on each non-authentication form step. Native
credential handling remains the authentication path. Tests cover Simplify on the
new iCIMS step before residual inspection, including delayed transitions and a
new browser connection. No universal page delay, model/provider change or new
GPU inference layer is introduced. Workday's current behavior is retained and
included in regression validation.

Validation first reproduced eight Greenhouse failures, two delayed-transition
failures and two duplicate-click failures caused by reordered fields. The
combined Windows browser/helper suite passed 205 tests. After the ordering fix,
all 59 affected iCIMS and shared Autofill checks passed. The final managed suite
passed 1,066 tests with 130 skips (125 opt-in browser cases and five Linux-only
cases). Post-deployment Ubuntu results are recorded in the annotated tag and
private run record. All application fixtures use synthetic data and isolated
profiles.

These changes remove reproduced helper failures and unnecessary model handoffs.
They do not establish an end-to-end speedup or a higher submission rate. Recent
operator-assisted Greenhouse attempts are not autonomous timing benchmarks;
production comparisons must retain intervention and deployed-version context.

### Self-improvement #004 — 2026-09-29

Tag: [`self-improvement-004-2026-09-29`](https://github.com/rejozmathew/auto-job-applier/releases/tag/self-improvement-004-2026-09-29).
The annotated tag identifies the validated code commit, Ubuntu deployment time
and final test counts. The matching private report and deployment manifest retain
the daily audit, source fingerprints, hashes, backups and validation logs.
GitHub branch: `self-improvement`.

Credential calls could report that Simplify needed to settle even when the
browser was idle and the actual obstacle was an unresolved or mismatched job
identity. This sent recovery toward the wrong subsystem. The shared workspace
host now reports the existing job-identity error codes for those two causes and
directs the executor to inspect a fresh owned screenshot and recover the route
in the same session. Actual Simplify settlement failures keep their existing
diagnosis. The change applies to employer credentials and email verification
across portals; it adds no denial, permission requirement or retry limit.

Synthetic regressions reproduced four incorrect diagnoses before the fix. They
exercise the real host dispatch and private test database, verify that denied
calls do not reach credential handling, preserve the session and its metadata,
and then complete a credential call in the same session after corrected browser
evidence. Recovery events omit the private observation payload. Focused browser,
account, Workday and Simplify tests and the final managed suite are delegated to
authenticated Antigravity; Ubuntu repeats the focused suite against deployed
files with isolated synthetic fixtures and short private disk-backed paths.

This corrects recovery guidance; it does not implement cross-host SSO account
handoff or repair missing posting URLs. The preceding day's attempts finished
before #003 deployed, and some submissions were operator-assisted. They cannot
establish a production speed or submission-rate gain from #003 or this run.

### Self-improvement #005 — 2026-09-30

Tag: `self-improvement-005-2026-09-30`. The local annotated tag identifies the
validated source checkpoint. Private Ubuntu deployment notes retain the matching
run label, timestamp, file hashes, backups and synthetic validation evidence.

Retained application screenshots show a visible consent choice while shared
native activation returns `hidden_control`. Styled native checkboxes and radio
buttons can expose a zero-size input and a separate visible label. Previously
the pointer helper only used the input rectangle, returning routine work to the
executor's model and visual recovery loop.

The shared pointer helper now uses that input's own visible, uniquely associated
native label when its rectangle has zero width or height. The semantic input
remains the observed target. Activation uses trusted browser pointer events and
fresh hit tests; interactive label children and overlays are not clicked as a
substitute. The existing form operation verifies the committed checked state and
does not toggle a correctly populated control again. No employer, hostname or ATS
branch is added. Simplify order, ownership, credentials, frame checks, answer
policy, deadlines and retry behavior are preserved; no new execution restriction
or approval gate is introduced.

Six synthetic regressions first reproduced the failure for checkboxes/radios on
top-level, same-origin and cross-origin embedded forms. Coverage also checks
trusted events, repeated checks, explicit unchecking, disabled controls, overlays,
unrelated labels and interactive children. Relevant existing shared-form,
embedded-frame, Workday authentication and native-pointer checks accompany the
focused suite, followed by the standard managed suite. Exact final counts and
Ubuntu deployment verification are retained in the private run record and tag.
Windows validation passed all 70 focused checks; the final managed suite passed
1,075 tests with 140 opt-in browser/Linux-only skips. An initial isolated Hermes
startup timeout passed unchanged on focused recheck before the clean final run.

The timing investigation also found costly model requests, large contexts,
compression, repeated inspections and incorrect specialized-helper routing.
This change fixes one reproduced shared handoff; it does not establish a
ten-minute application duration or an unattended end-to-end speedup. Later
ordinary applications must measure those outcomes with source and assistance
provenance. Private application records and screenshots remain outside Git.
