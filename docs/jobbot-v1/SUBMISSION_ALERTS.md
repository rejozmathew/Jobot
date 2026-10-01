# Confirmed-submission alerts through Hermes

`job_applier.hermes_notifications` watches the explicitly selected managed
submission ledger read-only. An `applied` attempt with a durable ledger entry
sends this message through the installed `hermes send` CLI:

```text
Application submitted
Company: Example Company
Role: Example Role
```

Submit intent, an executor's exit code, uncertain outcomes and `already_applied`
do not generate a new-submission alert. Confirmed manual reconciliation to
`applied` is included. Company and role come from the managed job record; missing
metadata is stated explicitly. External text cannot trigger mentions or Hermes
media directives. No candidate answers, email, resume or confirmation transcript
is sent.

Add this optional section to the existing private runtime configuration:

```json
"submission_notifications": {
  "target": "discord:REPLACE_WITH_ALERTS_CHANNEL_ID",
  "hermes_executable": "/home/REPLACE/.local/bin/hermes",
  "profile_home": "/home/REPLACE/.hermes"
}
```

Keep Discord credentials in that Hermes profile's private configuration. This
uses Hermes's existing Discord integration and needs neither a model nor a
running gateway. A gateway/reply handler is a separate concern.

Run `python -m job_applier.hermes_notifications --config /absolute/runtime.json once`
before enabling the service. First initialization skips existing submission
history, so activation does not flood the channel. Use the supplied
`deploy/systemd/jobbot-notifications.service` with paths adapted to the existing
checkout. It polls every five seconds independently of queue/browser services;
no application-service restart is necessary to add this observer.

Delivered job IDs and pending retries persist in the private spool's
`notifications/submissions.json`. An OS lock prevents concurrent pollers;
checkpoints replace atomically. Failed sends retry with a delay capped at five
minutes and never alter an application result or occupy its workspace. Ordinary
restarts do not replay acknowledged messages. If the process dies after Discord
accepts a message but before its local checkpoint is saved, a retry can duplicate
that message: Hermes's send CLI does not offer a transaction with this receipt.

To disable delivery, stop `jobbot-notifications.service` or set
`submission_notifications.enabled` to `false` and restart only that service.
Retain the checkpoint when re-enabling. No managed database migration, application
restriction, or "Need your answer" Discord reply flow is introduced.

Synthetic validation is in `tests/jobbot_v1/test_submission_notifications.py`.
Deployment verification checks actual channel access, service state, source
hashes and an explicitly labelled setup message; it does not fabricate a live
application to exercise an alert.
