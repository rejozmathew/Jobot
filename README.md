# Jobot

**Jobot Application Operations** coordinates job discovery, an application queue,
external AI executors, Simplify-assisted browser sessions and evidence-backed
application history. It runs locally with an existing Windows or Ubuntu setup and
provides a dashboard for operating and reviewing the workflow.

Start with the [documentation index](docs/README.md),
[dashboard user guide](docs/USER_GUIDE.md) or [architecture](docs/ARCHITECTURE.md).
The project was previously named Auto Job Applier / JobBot. Its GitHub repository
is now [rejozmathew/Jobot](https://github.com/rejozmathew/Jobot).

## Set up Jobot for yourself

Start with [the first-time installation guide](docs/GETTING_STARTED.md#first-time-personal-installation).
It covers Windows and Ubuntu, your own candidate profile and resume, the private
database/configuration, Hermes, email verification, Simplify, Discord and startup.
Use the current `main` branch. Repository access is required while this project is private.

1. Clone Jobot and install the pinned Python dependencies in its virtual environment.
2. Install Hermes and authenticate your own model provider. Enable terminal,
   file/skill access and screenshot/vision support on the machine running Jobot.
3. Copy [profile.json.template](profile.json.template) into your private installation,
   fill in your own facts, then create the runtime and register your resume.
4. Install Simplify Copilot in Jobot's browser profile, sign in to your own
   Simplify account and complete your profile there, including education and work history.
5. Make Hermes discover the bundled [job-apply entry skill](integrations/hermes_jobbot/skills/job-apply/SKILL.md).
   The full [application procedure](skills/productivity/job-apply/SKILL.md),
   [Workday procedure](skills/productivity/workday-simplify/SKILL.md) and their
   references are all in this repository. No separate private skill download is needed.
6. Connect your application mailbox through Hermes's Himalaya or Google Workspace
   skill. Configure Discord if you want bot conversations or submission alerts.
7. Verify setup, open the dashboard and choose your submission settings before
   starting the queue or requesting an application.

Hermes is the documented executor; another compatible harness can use the same
CLI. Mail access supports employer verification. Discord and the native Hermes
`jobbot` plugin are optional. The guide explains both the portable skill/CLI route
and the native plugin route, and where each upstream integration comes from.

Existing command/module names (`jobbot`, `job_applier`, `JOBBOT_CONFIG`), service
names and `docs/jobbot-v1/` paths remain compatible. Existing installations can keep
their current checkout directory; new clones can use `Jobot`.

For an existing clone, update the remote with
`git remote set-url origin https://github.com/rejozmathew/Jobot.git`.
The maintained application history from `self-improvement` is included in `main`;
that development branch remains available.

## What it does

- Brings manual URLs and discovery/integration sources into one durable job history.
- Queues selected jobs in order, supports per-job Apply now, scheduled retries,
  cancellation/restoration and persistent Pause/Resume Jobot.
- Runs 1–5 queued applications with separate executor conversations and owned
  application windows, using the operator's selected model and deadline.
- Uses Simplify for broad filling, shared browser controls and Workday, Greenhouse,
  iCIMS and LinkedIn helpers, with executor recovery for exceptions.
- Collects unresolved questions, saves human responses and maintains editable,
  versioned learned answers with source history.
- Tracks candidate profiles, resume versions, portal account state, application
  progress, timings and confirmation evidence.
- Supports manual password overrides for tracked portal accounts in **Accounts &
  history**, using the existing private credential file.
- Reports distinct postings, attempts, new submissions and already-applied results;
  optionally sends confirmed-submission alerts through the existing Hermes setup.

An ATS helper is not a guarantee that every employer form works. Recorded evidence
establishes an outcome; a Submit click or executor exit code alone does not.

## How it fits together

```mermaid
flowchart LR
    Intake[Manual entry / discovery] --> Queue[Managed queue and history]
    UI[Operator dashboard] <--> Queue
    Queue --> Executor[External application executor]
    Executor --> Runtime[Owned local browser session]
    Runtime --> Forms[Simplify + shared and ATS helpers]
    Forms --> Portal[Employer portal]
    Runtime --> Evidence[Outcome and evidence]
    Evidence --> Queue
```

Jobot owns the records, scheduling, browser targets, lifecycle and reports. The
external executor reasons about the application. Helpers assist it; their call
budgets and recovery handoffs do not decide when an application is over. The
operator's overall time limit defaults to 30 minutes and can be changed or turned off.

## Run an existing installation

Use this repository's virtual environment and the existing private runtime
configuration. With the local runtime pointer already installed:

```powershell
.\.venv\Scripts\python.exe -m job_applier.queue_runtime status
.\.venv\Scripts\python.exe -m job_applier.queue_runtime serve
```

On Ubuntu, use `./.venv/bin/python` and the installed services; inspect their state
instead of starting a second dispatcher. The dashboard URL comes from the selected
config's `base_url` (example/default port: 60158).

The dashboard and queue worker are independent. `queue_runtime watch` is the
worker entry point; a working dashboard alone does not mean a worker is online.
Local application execution uses `application_runtime start` or the Hermes
`jobbot` tool and does not require a dashboard or HTTP API token.

For a fresh development checkout, synthetic setup and provisioning requirements,
read [Getting started](docs/GETTING_STARTED.md). Private candidate records,
credentials, browser profiles, authenticated providers and deployment launchers
are not included in Git.

`python run_applier.py serve` starts the **legacy** browser-use dashboard, commonly
on port 8000 with different history. See [Legacy application](docs/LEGACY.md) if you
intend to work on that path.

## Documentation

| Topic | Guide |
|---|---|
| Every dashboard page and operator action | [User guide](docs/USER_GUIDE.md) |
| Components, processes and execution flow | [Architecture](docs/ARCHITECTURE.md) |
| Setup and runtime selection | [Getting started](docs/GETTING_STARTED.md), [Configuration](docs/CONFIGURATION.md) |
| Jobs, attempts, answers and evidence | [Data model](docs/DATA_MODEL.md) |
| Hermes, Simplify, discovery, mail and APIs | [Integrations](docs/INTEGRATIONS.md) |
| Services, troubleshooting, deployment and rollback | [Operations](docs/OPERATIONS.md) |
| Implemented milestones and detailed records | [Project history](docs/PROJECT_HISTORY.md), [Engineering index](docs/jobbot-v1/README.md) |
| Development and keeping docs current | [Contributing](CONTRIBUTING.md), [Documentation maintenance](docs/DOCUMENTATION.md) |

## Repository map

| Path | Purpose |
|---|---|
| `job_applier/` | Managed service, runtime, queue, browser ownership, helpers and retained legacy modules |
| `job_applier/static/` | Dashboard HTML, JavaScript and CSS; no frontend build step |
| `skills/productivity/` | Canonical application procedures shared across harnesses |
| `skills/job-posting-harvest/` | Discovery procedure and intake utilities |
| `integrations/` | Hermes plugin and existing JobNavigator bridge maintenance |
| `deploy/` | Sanitized runtime example and systemd templates |
| `tests/jobbot_v1/` | Maintained synthetic managed-runtime and browser/UI regressions |
| `docs/` | Current guides, detailed engineering references and historical evidence |
| `artifacts/` | Ignored private runtime/validation artifacts; never a public data bundle |

## Development

Read [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md). Use synthetic
fixtures and the repository virtual environment. The standard managed suite is:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/jobbot_v1 -q
```

Follow the repository's delegated validation, local checkpoint and authoritative
Ubuntu deployment workflow. Update the affected docs in the same change using
[the maintenance map](docs/DOCUMENTATION.md).

The project builds on browser-use and integrates an external executor and the
Simplify browser extension.
