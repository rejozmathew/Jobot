# Getting started

[Documentation index](README.md) · [Configuration](CONFIGURATION.md) · [Operations](OPERATIONS.md)

## Choose the correct entry point

The current application is the managed JobBot runtime. Use the repository virtual
environment and explicitly selected configuration. `run_applier.py serve` starts
the historical dashboard and can show a different database.

| Task | Current entry point |
|---|---|
| Open the dashboard | `python -m job_applier.queue_runtime serve` |
| Run the queue worker | `python -m job_applier.queue_runtime watch` |
| Inspect queue state | `python -m job_applier.queue_runtime status` |
| Start one application from a harness | `python -m job_applier.application_runtime start` |
| Launch/attach the retained browser | `python -m job_applier.workspace_attachment --config …` |
| Read/call managed service operations | `python run_applier.py managed call` |
| Create a new isolated development instance | `python run_applier.py managed init` |

Commands below run from the repository root. On Windows use
`.\.venv\Scripts\python.exe`; on Ubuntu use `./.venv/bin/python`.

## Existing installation

Existing installations already have a candidate, resume asset, history, browser
profile and private runtime configuration. Reuse those records.

Configuration selection is: explicit `--config`, then `JOBBOT_CONFIG`, then the
private pointer at `artifacts/jobbot-v1-private/runtime-config.json`. The pointer
contains `{"config_path":"/absolute/path/to/runtime.json"}`. A pointer is local
installation state, not a file shipped by a fresh checkout.

Windows, with an existing selected pointer:

```powershell
.\.venv\Scripts\python.exe -m job_applier.queue_runtime status
.\.venv\Scripts\python.exe -m job_applier.queue_runtime serve
```

Or explicitly select the existing private runtime:

```powershell
$env:JOBBOT_CONFIG = 'C:\absolute\path\to\existing-runtime.json'
.\.venv\Scripts\python.exe -m job_applier.queue_runtime status
```

Ubuntu:

```bash
export JOBBOT_CONFIG=/absolute/path/to/existing-runtime.json
./.venv/bin/python -m job_applier.queue_runtime status
```

Read the dashboard address from that configuration's `base_url`; `60158` is the
example/default queue-server port, not a discovery mechanism. Open the configured
URL and check the selected instance in **Advanced**, the queue worker state in
**Applications**, and the selected candidate and resume.

The existing Windows private launcher
`python -m artifacts.jobbot-v1-private.runtime_dashboard` may be used where
installed. It is not part of the tracked package. On Ubuntu, use the installed
services rather than starting a second server or dispatcher. See
[Operations](OPERATIONS.md) for read-only status commands.

When the existing browser workspace needs to be opened, its configured launcher
retains its profile and debugging endpoint:

```bash
./.venv/bin/python -m job_applier.workspace_attachment --config /absolute/path/to/existing-runtime.json
```

Leave that browser available while the queue runs. If it was opened without
debugging enabled, use the existing launcher setup described in the
[queue/VM runbook](jobbot-v1/QUEUE_AND_VM_RUNBOOK.md).

## New development checkout

Python 3.11 is the current Windows validation baseline. The pinned managed-worker
dependencies are in [requirements-jobbot-lock.txt](../requirements-jobbot-lock.txt).
Use those for isolated managed-service development. The broader
[requirements.txt](../requirements.txt) includes browser-use and the original
application dependencies; it is not an equivalent reproducible lock file.

Create a virtual environment only if this checkout does not already have one:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-jobbot-lock.txt
```

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install -r requirements-jobbot-lock.txt
```

Many managed tests need only the pinned Python environment. Browser fixtures have
additional explicit prerequisites such as Node and an available Chromium-family
browser. The [contributor guide](../CONTRIBUTING.md) explains opt-in validation.
Hermes and Simplify are separately installed integrations, not supplied by this
dependency lock.

### Create a synthetic database and verify the service

This example creates a new **development / review-only** instance. Choose a new
filename; `init` deliberately does not overwrite an existing database. No browser,
employer URL, real candidate or live application is involved.

```powershell
$demoRoot = Join-Path (Get-Location).Path 'artifacts\jobbot-v1-private\docs-demo'
New-Item -ItemType Directory -Force -Path $demoRoot | Out-Null
$demoDb = Join-Path $demoRoot 'managed.db'
.\.venv\Scripts\python.exe run_applier.py managed init --db $demoDb --instance-id docs-demo
$demoJson = @{
    transport = 'local'
    instance_id = 'docs-demo'
    db_path = $demoDb
} | ConvertTo-Json
$demoConfig = Join-Path $demoRoot 'runtime.json'
[IO.File]::WriteAllText($demoConfig, $demoJson, [Text.UTF8Encoding]::new($false))
.\.venv\Scripts\python.exe run_applier.py managed call --config $demoConfig --operation health
```

Expected result: the selected `instance_id`, schema version and review-only
settings. These minimal fields support local service access; they do not provision
a browser, queue executor or dashboard server.

### Provisioning a full runtime

Use [deploy/runtime.ubuntu.example.json](../deploy/runtime.ubuntu.example.json) as
a field reference, replacing every placeholder with the installation's own values.
Provision these pieces explicitly:

1. A managed instance, candidate identity and factual profile.
2. A registered resume asset with a valid local storage reference and SHA-256.
3. Private credential/answer-policy references and, where needed, mailbox access.
4. A configured browser workspace with the official Simplify extension and a
   loopback CDP endpoint; an existing-mode workspace also selects
   `connection_mode: "existing"`.
5. An authenticated external executor and separate discovery configuration if used.
6. Dashboard credentials and a loopback base URL if serving the HTTP UI.

Candidate and document operations are described in [Data model](DATA_MODEL.md)
and [Integrations](INTEGRATIONS.md). Configuration names and their scope are in
[Configuration](CONFIGURATION.md). There is no wizard that creates private
employer accounts, imports production history or supplies authenticated providers.

## First operator walkthrough

For an already provisioned installation:

1. Open **Profile** and verify the intended candidate and resume asset.
2. Check **Settings** for the application model, concurrency and time limit.
3. In **Applications**, check submission mode under application options. Add the
   intended official posting URL. Active intake can be picked up automatically.
4. Select the desired job(s) and use **Queue selected**, or use a row's **Apply now**
   action. Check worker status if the saved request waits.
5. Watch the expanded job or **Activity** for current progress and the final evidence.
6. Answer a required unresolved question in **Needs your answer**, then use its
   ready-to-retry workflow when all necessary answers are available.

[The user guide](USER_GUIDE.md) explains the controls and their side effects.

## Direct harness execution

For a requested application, read the canonical
[job-apply skill](../skills/productivity/job-apply/SKILL.md) and follow its startup
procedure. The shape of the portable command is:

```bash
./.venv/bin/python -m job_applier.application_runtime start \
  'https://employer.example/jobs/role' \
  --config /absolute/path/to/existing-runtime.json \
  --driver-id ACTUAL_CONVERSATION_ID --request-id UNIQUE_REQUEST_ID --wait-seconds 0
```

Replace the placeholders with the requested job and actual conversation/request
identity. Repeated calls for that request retain the same request ID. Local start
performs readiness checks itself; a separate doctor call is optional diagnostics,
not an additional per-application prerequisite.
