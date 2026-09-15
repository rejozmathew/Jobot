# Single-job queue and existing Ubuntu VM rollout

Status: implementation and synthetic verification, not a completed deployment to
the user's Unraid VM. The actual VM's Hermes/email/browser combination has not
been inspected here. Preserve the existing VM, Hermes home, authenticated
providers, Himalaya account and browser extension setup.

## What runs where

`Hermes discovery -> intake -> explicit dispatch queue -> one fresh Hermes application -> recorded attempt/evidence`.

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
It selects the new row but does not silently execute it. Open application options
to check the candidate, exact resume and submission mode. **Queue selected** adds
explicit requests. **Run next now** requests one job as soon as the configured
browser is free. **Enable automatic queue** enables periodic pickup; the default
interval is three hours after the preceding dispatch returns. Pausing automatic
pickup does not terminate an application already in progress. Its own expanded
row has Pause and Stop controls. Application details and diagnostic messages are
collapsed on the main view; the queue worker's online/offline state is explicit.

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
Do not run `once` alongside the installed watcher. Neither imports arbitrary held
jobs automatically. Review mode remains review until the operator chooses submit.

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
Recovery does not replay a launched request automatically. Recorded success
suppresses rediscovery. A fresh explicit retry remains allowed after blocked,
failed, interrupted or uncertain history; old evidence stays intact. Automatic
queue seriality does not change the existing manual multi-workspace retry policy.
The Answers page's explicitly queued retries also feed the dispatcher for the
configured candidate. Browser closure must still be acknowledged before pickup.

There is no new whole-application timeout or automatic cross-attempt retry policy.
An executor that never exits or a browser whose cleanup cannot be verified can
hold the queue. Inspect its expanded row; do not delete locks or fabricate a
stopped/submitted state. Unclosed pre-rollout sessions must be accounted for.

## Daily discovery and other intake sources

For on-demand discovery:

```sh
python -m job_applier.harvest_runtime --enqueue
```

The fresh discovery brief loads the configured candidate's preferences and
exclusions. It can use employer/ATS sources and existing email alerts. It must
verify every direct employer URL and live status, preserve requisition identity,
and report unsupported or inaccessible sources rather than inventing listings.
Only **Strong apply / Apply** verdicts are eligible for the explicit `--enqueue`
handoff. **Apply with caveats / Skip** remain intake records, not automatic work.
Omit `--enqueue` to collect for review. Scheduling this task enables that standing
handoff authorization; it does not change the application's submission mode.

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
Raw executor stdout is not copied into JobBot logs; ordinary Hermes conversation
history and private task/result files remain available to the operator.

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

The timer is explicitly 08:00 America/Chicago; change it deliberately for another
timezone. Services use private umasks. Queue/harvest service shutdown targets their
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
