# Single-job queue and existing Ubuntu VM rollout

The existing Ubuntu deployment was updated on September 15, 2026. The queue
feedback and four-hour discovery settings were validated in Windows and deployed
to the existing VM checkout. Preserve the existing VM, Hermes
home, authenticated providers, Himalaya account and browser extension setup.

## What runs where

`Hermes discovery -> active intake -> automatic dispatch queue -> one fresh Hermes application -> recorded attempt/evidence`.

JobBot owns the selected managed database, deduplication, queue, submission mode,
history, browser ownership, controls and reports. Hermes is a replaceable external
executor, not embedded into the database service. The discovery task never opens
applications. A queued application never discovers or launches another job.

The new launcher is `python -m job_applier.queue_runtime`. Do not use the legacy
`run_applier.py serve` / root `job_applier.db` or the HTTP accept/claim worker as
the local queue launcher. The current private runtime pointer, or explicit
`JOBBOT_CONFIG`, identifies the actual managed instance. The dashboard and queue
worker are independent processes; a working web page does not mean a worker is online.

## Everyday use

In the dashboard, **Add a job** accepts its official URL and optional company/title.
The worker automatically queues active intake using its configured candidate and
resume. No second enqueue click is required. Existing cancellation, recorded
submission, exclusions, explicit eligibility holds and pending-answer work remain
respected. A discovery `Skip` verdict stays held unless the operator previously
approved the job for execution. Open application
options to check submission mode. **Run next now** collects active intake and starts
one ready job as soon as the configured browser is free. **Enable automatic queue**
enables periodic execution; the VM checks every 60 seconds. Pausing automatic
pickup does not terminate an application already in progress. Its own expanded
row has Pause and Stop controls. Application details and diagnostic messages are
collapsed on the main view; the queue worker's online/offline state is explicit.

New active postings briefly show **Awaiting automatic pickup**, then **Queued**.
Interrupted, failed, blocked and submission-unknown outcomes schedule a fresh
request after **4 hours**; a third attempt waits **24 hours after the second ends**.
The operator requested these three total attempts and spaced recovery on September
15. Retry due times derive from durable parent request IDs and completion times,
so restarting the worker does not reset them. Other ready jobs can run while a
retry waits. After the third unsuccessful attempt, **Needs attention** retains the
reason. **Retry selected** explicitly starts another series after it ends; there
is no permanent job ban. Recorded success and cancellation still suppress work.
User stops and completed review-only results do not restart automatically.

The dashboard separates ready jobs from scheduled retries and shows the next
application check, retry due time, attempt number and failure reason. **Run next
now** does not accelerate a future retry. Canceled records remain under **Show →
Canceled / All jobs** and may be restored without deleting history.

Jobs display Country and Posted date. Discovery retains verified `country` and
`posted_at` fields; the date is the original publication date, never inferred
from an update or intake timestamp. Missing dates remain Unavailable. Existing
explicit United States locations can supply the displayed country without
rewriting old records or guessing the country of an unspecified remote role.

CLI equivalents, after selecting the private configuration:

```sh
export JOBBOT_CONFIG=/absolute/path/to/existing-runtime.json
python -m job_applier.queue_runtime status
python -m job_applier.queue_runtime enqueue 'https://employer.example/jobs/role'
python -m job_applier.queue_runtime enqueue --job-id EXISTING_JOB_ID --retry
python -m job_applier.queue_runtime run-next
python -m job_applier.queue_runtime resume
python -m job_applier.queue_runtime pause
```

Use the repository's virtualenv Python, not an unrelated system interpreter.
Global `--config /absolute/path` goes **before** the queue subcommand; the
environment variable works for both queue and application-runtime commands.
`once` directly dispatches one queued job; `watch` stays running for the dashboard
and periodic triggers. Both share a nonblocking per-instance dispatcher lock.
Do not run `once` alongside the installed watcher. Ordinary new intake no longer
requires promotion from its default held state; explicit holds remain respected.
Review mode remains review until the operator chooses submit.

## Fresh application context and outcomes

Each queued item has a selected candidate, selected resume and durable request ID.
It gets its own private configuration and task file, then a fresh Hermes CLI
invocation. No `--continue`/`--resume` is used, and an inherited conversation ID is
removed. The brief points to the exact canonical skill, current runtime/context
and platform references, and repeats Simplify, screenshot/vision, credentials,
Himalaya/Gmail, email/SMS/CAPTCHA and evidence requirements. A file capture alone
is not visual inspection. The executor must actually use its image/vision tool.

Email verification is not a CAPTCHA. Use the configured mailbox for matching
recipient/employer/request time and check delivery before asking for human help.
Prefer an offered email method over unavailable phone verification. SMS-only or
authenticator approval needs the corresponding actual channel or human input.
A genuine image CAPTCHA is recorded as blocked rather than bypassed. Secrets,
mail bodies and codes must not enter progress or reusable answer history.

Queue completion uses the stored application outcome, not a successful CLI exit.
An executor that exits without evidence is interrupted, never marked applied.
Recovery creates a separate delayed request after an unsuccessful attempt ends.
Recorded success suppresses rediscovery. A fresh explicit retry remains allowed after blocked,
failed, interrupted or uncertain history; old evidence stays intact. Automatic
queue seriality does not change the existing manual multi-workspace retry policy.
The Answers page's explicitly queued retries also feed the dispatcher for the
configured candidate. Browser closure must still be acknowledged before pickup.

There is no new whole-application timeout.
An executor that never exits or a browser whose cleanup cannot be verified can
hold the queue. Inspect its expanded row; do not delete locks or fabricate a
stopped/submitted state. Unclosed pre-rollout sessions must be accounted for.

## Discovery settings and other intake sources

Open **Settings → Job discovery** to set **Maximum jobs per discovery run** and
**Discover jobs every (hours)**. Defaults are **5 jobs every 4 hours**. Settings
are saved in JobBot's versioned managed database, not the private runtime JSON.
The former `harvest_batch_size` config field is superseded by
`discovery_batch_size`; transfer any nondefault value into Settings during rollout.
Discovery prioritizes the strongest verified matches and may return fewer; it
should not broaden candidate preferences to fill the batch.

The systemd timer checks once a minute. `harvest_runtime --scheduled` reads the
current settings and last discovery start from the selected managed database.
It launches Hermes only when due. Frequency is measured from the last start,
in elapsed UTC hours; changing it recalculates the next due time immediately.
A long run remains single-instance under the existing harvest lock. A manual run
without `--scheduled` starts immediately and resets the next scheduled due time.
Failed/interrupted runs remain visible and the next scheduled check uses the same
configured interval. Application pickup uses its separate queue interval.

The dashboard shows the job limit, interval, executor, last start/outcome, next
due time and whether schedule checks are arriving. An executor exit is not proof
of discovered jobs or successful intake. Old private result files remain intact;
the new status history begins with the first run after this update.

For on-demand discovery:

```sh
python -m job_applier.harvest_runtime --enqueue
```

The fresh discovery brief loads the configured candidate's preferences and
exclusions. It can use employer/ATS sources and existing email alerts. It must
verify every direct employer URL and live status, preserve requisition identity,
and report unsupported or inaccessible sources rather than inventing listings.
The optional explicit `--enqueue` handoff still selects **Strong apply / Apply**.
The running automatic worker now also picks up other active intake, including
ordinary caveated records; **Skip**, exclusions and explicit holds remain out.
Omitting `--enqueue` only omits that immediate handoff: pause automatic execution
to collect active jobs without running them. Discovery never changes submission mode.

Other scripts or a different harness can supply sanitized JSON records:

```sh
python skills/job-posting-harvest/scripts/intake_results.py \
  --config "$JOBBOT_CONFIG" --input /private/path/jobs.json --enqueue
```

Required record fields are `url`, `source_type`, `source_id`; add company, title,
location and verdict. For enqueue, verdict must be Strong apply or Apply. Validated
namespace/requisition/identity evidence are optional. `--dry-run` performs no
writes, even with `--enqueue`. Local transport needs no dashboard/API token.
For an already authenticated remote integration, operator-only `intake` and
`queue_enqueue` endpoints provide the same separation. Do not make the API public
or give a worker token operator privileges.

Discovery remains an LLM-mediated workflow, not a guarantee of daily suitable jobs.
CLI completion is recorded separately from actual source rows and queue entries.
An executor that exits without saving its result file is shown as **Incomplete**,
even when the CLI returns exit code zero. A saved result file alone still does
not prove intake or application submission; inspect the corresponding job rows.
Raw executor stdout is not copied into JobBot logs; ordinary Hermes conversation
history and private task/result files remain available to the operator.

### Discovery context on local models

Use the optional private `harvest_hermes_command` argv to select a dedicated
Hermes profile for discovery. It uses the same `{prompt_file}` substitution as
`hermes_command`. When omitted, discovery retains the existing command. An
explicit invalid override is reported rather than silently choosing another
executor. The application queue continues to use `hermes_command`.

On the inspected VM, Qwen's loaded context was 100,608 tokens. The installed
Hermes compressor raised the configured 50% trigger to 75%, or 75,456 tokens.
Live searches overflowed before finishing. An absolute 35,000-token trigger
avoids that percentage floor and leaves more room for tool responses and output.
`deploy/hermes-discovery.yaml` contains the discovery-only compression settings,
including a shorter recent history and earlier pruning of large tool results.

Create the profile with the installed CLI (no active-profile switch):

```sh
hermes profile create jobbot-discovery --clone-from default --no-alias
```

Merge the YAML fragment into that profile's private `config.yaml`, preserving
its existing model, provider, credentials and tools. Back up the profile config
first. Do not replace the entire config with the fragment. Set
`harvest_hermes_command` to the existing absolute Hermes executable followed by
`--profile jobbot-discovery chat --oneshot --pass-session-id --query-file
{prompt_file}` (retain any existing operator CLI flags). The fragment and command
are deployment choices; JobBot does not modify the general Hermes profile.

The discovery brief keeps bulk search output in private scratch files and asks
the executor to save verified findings to `checkpoint.json` after each role.
The next run receives the latest unfinished run's checkpoint when present and
must revalidate those leads against live postings and current policy. The final
`records.json` is written only when the search is finished, then published through
the existing intake command. A checkpoint alone remains **Incomplete** and does
not enqueue applications. Saved findings survive context compaction and a later
executor interruption; no successful application is replayed by this recovery.

## Existing VM cutover

1. Pause application execution on the old machine and account for open sessions.
   Back up the **selected managed DB** using SQLite backup, not a copy of a live
   WAL file or the similarly named historical root database. Keep one machine
   authoritative during cutover. Preserve earlier attempts and submission ledger.
2. Update the existing VM checkout with the validated branch checkpoint. Create
   a Linux virtualenv and install `requirements-jobbot-lock.txt`. Do not copy a
   Windows virtualenv, wipe Hermes, rebuild the VM or transfer encrypted Chrome
   cookies as a substitute for the existing VM login.
3. Copy the managed snapshot and approved assets privately. Register the Linux
   resume through the profile UI/asset API and select its returned ID. Correct all
   Windows file references in the private runtime config, including the selected
   resume, profile, policy, spool and any retained history DBs. Do not silently
   switch candidates or create a new empty history database.
4. Adapt `deploy/runtime.ubuntu.example.json` using the real existing instance,
   candidate, resume, browser and email paths. The template is intentionally not
   runnable until those values are supplied. The exact Hermes executable path
   matters to systemd because the shell's PATH and activation are not inherited.
   Confirm the installed `hermes chat --help` supports the selected command.
   Default code uses `-q` with a private task-file instruction for compatibility;
   the template uses `--query-file`. Existing Hermes model/provider settings stay
   authoritative unless explicitly set in the configured command. Do not load a
   restrictive toolset that removes terminal, email or image/vision access.
   Check the installed thin `job-apply` skill points to this checkout; refresh an
   outdated copy from `integrations/hermes_jobbot/skills/job-apply`. Older copies
   may retain the removed blanket refusal after uncertain submission history.
5. Keep the existing Himalaya account/config; select `mailbox_provider=himalaya`.
   Executable presence is not authenticated mailbox proof. Verify account access
   without printing credentials or old private mail. Ensure the intended candidate
   email matches the selected account. Email access does not imply SMS access.
6. Use the persistent **VM-local** browser profile with signed-in Simplify. Do not
   run another Chrome instance on that same profile. Headed automation needs the
   actual graphical login/display and its authorization, not an invented DISPLAY.
   No browser mode here guarantees avoidance of employer anti-bot challenges.

First start, in that existing environment:

```sh
export JOBBOT_CONFIG=/absolute/path/to/runtime.json
.venv/bin/python -m job_applier.queue_runtime doctor
.venv/bin/python -m job_applier.queue_runtime serve
# Separate terminal, same selected configuration:
.venv/bin/python -m job_applier.queue_runtime watch
```

The launcher backs up the selected database before additive migration 18. The
queue starts paused with no invented jobs. Doctor is non-invasive and is not
proof of an authenticated email/browser session, vision tools or ATS completion.
No employer-application benchmark is required merely to inspect configuration.

### User services

Templates are in `deploy/systemd/`. Edit the checkout paths to the existing VM
checkout. Keep the private config at the selected path, or adjust `JOBBOT_CONFIG`
in every service. Put optional absolute `HERMES_HOME`, PATH or token environment
settings in private `~/.config/jobbot/runtime.env`, never in Git. Restrict private
data/config directories to the owner and files to mode 600.

From the actual logged-in VM desktop, import the real display environment:

```sh
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY
mkdir -p ~/.config/systemd/user
cp deploy/systemd/jobbot-*.service deploy/systemd/jobbot-harvest.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now jobbot-dashboard.service jobbot-queue.service
systemctl --user enable --now jobbot-harvest.timer
systemctl --user status jobbot-queue.service jobbot-dashboard.service
systemctl --user list-timers jobbot-harvest.timer
```

The minute timer is only a wakeup; the saved JobBot settings control discovery.
Dates display in JobBot's selected timezone. Services use private umasks. Queue/harvest service shutdown targets their
own systemd control groups. User-service persistence may require enabling user
lingering, but lingering **does not create or preserve a graphical desktop**.
VM auto-start/login/display availability must be verified on the actual machine.
Linux process-group supervision is not a claim of containment for arbitrary
descendants that deliberately detach into a different session; systemd cgroups
provide the additional service-level cleanup boundary.

The dashboard remains loopback-only. Open it in the VM or use an SSH tunnel to
port 60158; do not change its bind address to a wildcard to make access convenient.
Check worker online state separately from web availability, then choose automatic
pickup or Run next. No services or timer were installed during this code review.

### Updating an existing discovery schedule

After deploying the validated changes to the existing VM checkout, preserve the
actual checkout path in the installed harvest service and add `--scheduled` to
its existing `ExecStart`. Install the updated timer and reload systemd. Do not
install the minute timer with an old service that lacks `--scheduled`, or it will
launch discovery every minute. This does not restart the application worker:

```sh
cp deploy/systemd/jobbot-harvest.timer ~/.config/systemd/user/jobbot-harvest.timer
systemctl --user daemon-reload
systemctl --user restart jobbot-harvest.timer
systemctl --user list-timers jobbot-harvest.timer
```

Restart the dashboard through its normal deployment procedure to expose the new
settings and apply the backed-up additive migration 20. The migration adds only
discovery run/check records; it does not rewrite job/application history. Later
frequency and job-limit changes need only **Save settings**, not a service restart.

## Local validation — September 15, 2026

Antigravity (`gemini-3.8-flash-medium`) ran synthetic regression tests; the primary
agent independently inspected logs and JUnit. Queue labeling/empty-trigger tests
failed before their fixes, as did the discovery cadence/status tests before their
implementation. The focused suite passed 41 tests. The full managed suite with
isolated Chrome fixtures passed **793 tests**, with four Linux-only skips and no
failures or errors. A final nine-test run verified the discovery UI, live settings
changes and the wording that distinguishes manual discovery from schedule checks.
Evidence is in ignored `artifacts/jobbot-v1-private/queue-feedback-20260915/`.
No production application, database or VM service was changed by validation.
