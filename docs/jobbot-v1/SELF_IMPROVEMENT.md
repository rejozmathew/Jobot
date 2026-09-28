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
