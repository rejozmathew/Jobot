---
name: workday-simplify
description: Execute Workday with local sessions and Simplify.
version: 0.3.0
author: Rejo Z Mathew (rejozmathew), Hermes Agent
license: MIT
platforms: [windows]
---

# Workday with Simplify

Read the canonical [job-apply](../job-apply/SKILL.md). Start the application using
its local `start` operation. Startup verifies the configured managed instance,
history, assigned headed browser, profile, fresh target and Simplify surface.
No API token, expiring lease, old target binding or additional worker is needed.

Use native `jobbot(operation="fast_forward", parameters={"seconds":60})`.
The portable equivalent resolves everything from the returned session:

```text
.venv/Scripts/python.exe -m job_applier.workday_fast session <session-id> --seconds 60
```

Optional `--config <absolute-json>` and `--driver-id <conversation-id>` follow the
shared skill. The ordinary conversation remains the application executor. The
runner contains no model and retains one CDP connection during its bounded call.

1. Confirm role, identity, approved asset and submission authorization once.
2. Call the runner for routine observe/act/wait/advance. It checks controls and
   writer state, lets Simplify fill, and prefers enabled Continue after settling.
3. `waiting`: call again. Persisted counters protect against repeated autofill;
   do not reset checkpoints to evade limits. Heartbeat is telemetry, not expiry.
4. The runner handles Workday authentication: read the existing site account,
   reuse its saved credential (or the configured retained default for a new site),
   choose Create Account or Sign In, accept the uniquely observed account
   privacy/terms checkbox, fill privately, and recheck the enabled submit control.
   It records creation pending before clicking, saves employer-confirmed creation,
   and confirms sign-in only when the application form actually opens. It then
   returns to Simplify. A later call reads the durable account and signs in.
   Counters prevent repeating an uncertain create/sign-in action. Optional
   marketing consent is not selected. No generated password is silently lost.
   `authentication_required` now means a specific exception: inspect its reason
   and current controls, then use scoped browser/credentials or the configured
   mailbox for a supported recovery. An unknown checkbox, verification challenge,
   rejected credential, missing saved reference or unfamiliar auth page returns
   to the executor without closing the application. Never reset counters or
   create again while the previous account outcome is unknown.
   Follow the returned `recovery` handoff: inspect `browser screenshot` using
   the current executor's image capability, pair with `browser snapshot` for
   observed selectors, and use supported native controls or settled Simplify.
   Report possible changed/unsupported controls distinctly from rejected
   credentials or a verification challenge. After recovery, call the runner again;
   record the mismatch for a later helper update, never an in-run code patch.
5. `blocked`: handle only the actual required blocker with the shared session's
   `browser` operation and approved facts. One initial autofill and one retry per
   step remain the limit. Do not audit every optional field or reconstruct history.
6. A review count does not defeat enabled Continue after quiescence. Same URL does
   not imply same step; the runner observes Workday's actual section/stepper.
7. At authorized Review, observe the correct approved attachment. The runner
   records intent, submits once and verifies the exact requisition in native
   employer evidence. Do not treat the Simplify success panel as confirmation.
8. `applied`: read the report; do not submit or finish again. `already_applied`
   requires exact native evidence and no new submit. `submission_unknown` allows
   observation/reconciliation only. `ready_for_review` applies only in review mode.

No in-run PDF extraction, resume search, career/education reconstruction or shared
code/skill changes. Never compete with active or unknown writers. Generic browser
focus and old targets do not belong to this session. An unavailable CAPTCHA/MFA,
rejected credentials or unknown required fact is a specific blocker.

Optional diagnostic:

```text
.venv/Scripts/python.exe -m job_applier.application_runtime doctor --url <job-url>
```

Doctor alone is not live readiness. The legacy `workday_fast advance` with explicit
attempt/fence/target remains for existing HTTP integrations; it is superseded for
normal local execution. Report exact employer confirmation and honest elapsed
wall time; under ten minutes is a target, not an inferred result.
