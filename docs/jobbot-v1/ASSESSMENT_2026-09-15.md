# Jobot capability and deployment assessment — 15 September 2026

## Verdict

**The platform can complete some real applications. It is not demonstrated to work
reliably across most Workday employers, all Greenhouse forms, or arbitrary portals.**
Greenhouse has the strongest existing evidence. Workday has both completion and
recent authentication failures. iCIMS and other ATS families remain best-effort.
The sensible next phase is controlled operation with clear recorded outcomes, not
another broad employer-testing campaign or a claim of universal automation.

This review inspected the current `codex/runtime-simplification` worktree at
`C:\GitClone\auto-job-applier-jobbot-v1`, its remote branch reference, runtime
configuration references, source, canonical skills, tests and the selected managed
database. The source baseline includes the September 14 authentication repairs.
This assessment did not submit new applications, open private mail, alter the
production database/configuration or install services on the user's Unraid VM.

Verified source baseline: `cf2d2f1af044583fc008a9f12092194acb21fd1d`, also the
remote branch head when rechecked during this review.

## Evidence, not an invented success rate

The inspected database has **66 attempts**: 7 applied, 28 blocked, 4 failed,
25 interrupted, 1 submission-unknown and 1 unfinished. These include repeated
engineering/debug sessions and reconciled outcomes. **7/66 is not a meaningful
production success rate.** Neither helper fixtures nor these counts establish
coverage across employer-specific forms or predict daily throughput.

| Portal family | Existing positive evidence | Limitations / recent counter-evidence | Deployment expectation |
|---|---|---|---|
| Greenhouse | Tebra, Philo and GitLab have recorded employer confirmation evidence | Employer variants, residual custom questions and email verification can still fail; three completions are not universal acceptance | Best-supported starting set; proceed using current helpers and existing mailbox |
| Workday | Fresenius Medical Care has employer Application Submitted evidence; Magellan has a user-reported confirmation/email reconciliation | The Magellan reconciliation is not proof of unattended execution. September 14 Rakuten/Ebates attempts failed in account creation/login/recovery despite recent helper fixes | Supported but fragile, particularly authentication; retain executor-led recovery |
| iCIMS | No recorded success in the inspected ledger | ComPsych interrupted attempts and HarperCollins target/redirect handoff blockage; routing support exists but acceptance is unproved | Opportunistic best-effort, not a dependable default |
| Custom form | Accordion has a recorded submission confirmation modal | One custom employer form does not establish arbitrary-form capability | Try when the observed controls are supported; record precise residual blockers |
| Taleo | UnitedHealth has a reconciled Application complete record | Imported/reconciled evidence rather than a newly observed end-to-end run in this review | Some historical evidence, low confidence in broad coverage |
| Lever / Ashby / other | Shared form/frame tools and generic execution paths exist | Fi and SentiLink attempts were interrupted; no recorded success for these families in the inspected ledger | Implementation coverage, not proven completion capability |

Evidence source: selected managed DB, `application_attempts` and
`submission_ledger`, joined with job labels/URLs. The dashboard/attempt report
retains the exact source evidence; this public assessment does not publish private
screenshots, candidate data, mail bodies or credential paths. Reconciliation and
user-reported evidence are explicitly weaker than independently observed runtime
completion. Two session records were unclosed at inspection: one capacity-wait
record from September 10 and one connected record from September 14. Unclosed
records alone do not establish that their browser processes are still alive.

## Concrete gaps found before this change

**The current UI Start action was not a dispatcher.** In the local-session mode,
it displayed an instruction to give the URL to the application conversation and
returned. Legacy request-run/worker code was present, but it was not the correct
current-runtime orchestration path. Intake existed independently of execution.

**Mailbox reminders were Gmail-specific.** The current handoff knew the configured
Gmail script/token references. It did not expose the VM's requested Himalaya
configuration. Existing skills mentioned important recovery techniques, but a
long multi-job conversation was still expected to retain the relevant context.

**The thin Hermes entry contradicted the canonical retry policy.** It still said
not to resubmit an uncertain application, while the canonical branch explicitly
allows current-form verification/edits and new explicit retries after uncertainty.
That conflict could contribute to hesitation; the inspected records do not prove
which instruction controlled any individual run. The thin entry has been aligned
with the canonical policy, without weakening recorded-success suppression.

**Progress overwhelmed the default view.** Every session's stages, timings and
metadata were visible together, while manual intake was hidden. Some controls
implied model/browser configuration they did not actually enforce in local mode.

**Ubuntu was not simply a copy-and-run deployment.** The process launcher raised a
Windows-only exception, and profile-in-use inspection was also Windows-only.
There was an older deferred rollout document rather than a completed VM rollout.

## Implemented in this engineering pass

### 1. Explicit durable queue and fresh per-job context

Migration 18 adds dispatch entries and scheduler state to the existing managed DB.
Intake alone does not execute. Manual selections or explicitly authorized discovery
enqueue work; the dispatcher launches one fresh external Hermes CLI conversation
per job. Candidate/resume/request IDs are explicit. Saved-answer retry requests
also feed the same queue for the configured identity. Existing manual session and
retry policies remain intact; uncertain history was not turned into a new lock.

Every application receives the canonical skill paths and its own task/config,
ATS reminders, account/context retrieval instructions, Simplify guidance, visual
inspection reminders, existing email mechanism, phone/channel distinctions and
submission/evidence requirements. Startup still verifies the actual browser and
selected files. This reduces dependence on conversational memory; it does not
guarantee an LLM will obey every instruction or that its vision tool is enabled.

### 2. Honest email/challenge handling

The handoff supports the selected Himalaya account/config/executable as well as
the existing Gmail wrapper. It follows installed CLI help rather than assuming
one version's mailbox syntax. Ordinary email OTPs, links and email-vs-phone choices
are not classified as image CAPTCHA. SMS-only or authenticator flows need actual
access or human input. A genuine image CAPTCHA is a recorded blocker, not an
attempt to bypass protection. A protection logo alone is not an active challenge.

This is a **context/integration handoff**, not an independently verified mailbox
connection or a new email client. `available` reports executable/reference presence;
`connection_verified` remains false until actual authenticated use is observed.

### 3. Compact UI and functional actions

The main application view now shows compact status rows; details, stages, timings,
failure reasons and debug information expand on demand. Existing history and
controls are retained rather than deleted. Manual Add a job is visible. Queue
selected, Run next now and automatic-queue controls use the new queue endpoints.
Worker online/offline is distinct from the page being available. Resume selection
is explicit rather than silently using whichever file was most recently imported.

Legacy model/browser controls are hidden for the local dispatcher so they do not
promise changes to the separate Hermes/runtime configuration. Settings inputs are
no longer reset on every polling refresh when the settings version is unchanged.
This is a cleanup of the current UI, not a replacement with an older database/API.

### 4. Daily discovery, replaceable executor and VM scaffolding

A separate discovery task reads current candidate preferences/exclusions, verifies
live employer links and passes records through existing intake. Explicit enqueue
accepts Strong apply / Apply verdicts; caveats and skipped roles are not automatic
application work. Rediscovery is idempotent. It can use available employer/ATS
sources and email alerts, without making scraping or daily job availability promises.

Ubuntu user-service and daily timer templates are supplied. Default automatic
application pickup is once every three hours; Run next can request an earlier
pickup. Each job receives a fresh subprocess, not a continued multi-job chat.
Hermes remains replaceable through a command-list/prompt-file interface.

Linux-owned process-group lifecycle, profile detection and private sockets have
been added and checked on Ubuntu under WSL. Review caught and corrected a
supervisor parent-death signal that would have prevented cleanup. Tests cover
host death and descendants in the supervised process group; this is not a claim
of universal containment of processes that deliberately leave that group.
Systemd service-level control-group cleanup provides an additional boundary.

## What remains unverified or operationally important

The changes are not installed/running on the actual Unraid VM. Its exact checkout,
Hermes executable/version/home, selected model/tools, graphical display, persistent
Simplify login and Himalaya account access still need environment verification.
No current live application was used to certify this combination. Repeated CAPTCHA
or employer WAF challenges remain possible; this pass did not solve browser trust.

The new dashboard launcher must be restarted on the selected instance to expose
new queue endpoints and perform its backed-up additive migration. Loading changed
static files into an old running Python server is not a complete deployment.
Queue rows can wait indefinitely for a truly active executor or unconfirmed browser
cleanup; no new whole-application timeout or cross-attempt retry limit was imposed.
The UI must not label a plain CLI exit or a stopped process as successful submission.

Before cutover, account for unclosed sessions and keep one authoritative machine.
Preserve the managed DB and approved assets; register Linux-local asset paths and
select the right IDs. Do not wipe Hermes, copy a Windows virtualenv/profile as a
substitute for VM authentication, or create an empty DB that loses applied history.

## Verification record

The untouched baseline full suite was independently inspected: **748 tests,
706 passed, 5 failures, 37 skipped, 0 errors**. Four failures expected historical
retry/resume/upload restrictions removed by the branch's documented retry policy;
their expectations were updated to retain submission authorization, real evidence,
workspace isolation and immutable prior history without reinstating blanket vetoes.
The fifth was a dashboard DOM harness timeout; its assertions now exercise the
explicitly requested collapsed default view and preserved expansion.

New synthetic tests cover queue atomicity/deduplication, explicit retries, successful
submission suppression, operator authorization, one-job context, mailbox metadata,
fresh CLI invocation, executor-exit evidence handling, browser single-flight,
crash recovery, saved answers, discovery handoff and UI behavior. Linux-specific
tests ran on Ubuntu under WSL with no employer sites or user browser profiles.
Final verification: **780 collected, 739 passed, 41 skipped, 0 failures and 0
errors** in 181.033 seconds on Windows. The 14 Linux-specific checks also passed
on Ubuntu under WSL, with none skipped. JavaScript syntax, Git diff checks, CLI
help entry points and a rendered synthetic dashboard check passed. Skipped
Windows tests remain skipped; this does not turn them into live application proof.

The underlying local reports are
`artifacts/jobbot-v1-private/assessment-final-v3-2026-09-15.xml` and
`artifacts/jobbot-v1-private/linux-actual-2026-09-15.xml`. Private test artifacts
are not published in Git. The delivery summary identifies the local checkpoint;
no branch push, running-dashboard restart, production DB migration or VM service
installation was performed during this engineering pass.

## Use and handoff

See [QUEUE_AND_VM_RUNBOOK.md](QUEUE_AND_VM_RUNBOOK.md) for the exact commands,
existing-VM migration steps, service setup and remaining limits. Use **Add a job →
Queue selected → Run next now**, or enable the queue worker and scheduled discovery.
Operate first on portals with existing positive evidence and retain best-effort
handling for others. The product should tell the operator what actually happened,
not promise that every portal is solved.
