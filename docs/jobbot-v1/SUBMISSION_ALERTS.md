# Confirmed-submission alerts through Hermes

## Daily numerical summary

The same notification service can send a previous-calendar-day summary at
08:00 America/Chicago. Enable it inside the existing private
`submission_notifications` configuration:

```json
"daily_summary": {
  "enabled": true,
  "time": "08:00",
  "timezone": "America/Chicago"
}
```

It uses the existing Discord target and sends numbers only. No new gateway,
model, app automation or independent cron job is needed. First activation starts
with today's report tomorrow; it does not announce historical days. The existing
private `notifications/submissions.json` stores per-day receipts, frozen report
counts and failed-send retries. Restarts resume pending delivery without
replaying acknowledged reports. Downtime can delay delivery; missed reports are
delivered one at a time after the configured morning time. The same rare
send-before-checkpoint crash limitation as individual alerts applies.

Counts have deliberately different units:

- **Jobs submitted:** distinct postings with a new submission completed that day;
  affirmative already-applied evidence and earlier recorded success are excluded.
- **Jobs attempted / application attempts:** distinct postings / all attempts
  started that day, including failed retries.
- **Attempts used for submitted jobs:** all attempts up to the first new
  submission for those postings, including attempts on earlier days.
- **Duplicate jobs skipped:** distinct incoming job records actually refused at
  admission, counted on their first recorded skip date for the candidate.
  Matching old records during backfill is not a skipped application, and repeated
  reconciliation polls do not inflate the count.
- **Already-applied results:** distinct postings with that reported result
  completed that day.
- **Attempted jobs without submission by day end:** attempted postings with no
  retained successful submission by the end of the day; not a permanent failure.
- **Jobs reaching the 6-attempt automatic limit:** distinct postings whose
  unsuccessful sixth dispatch in a retry series ended that day. An explicit
  later retry can still start a new series. These are dispatch-series milestones,
  not a claim that each series created exactly six browser sessions.

Day boundaries follow daylight saving time. Counts overlap and are not expected
to sum to attempts. A late completion appears on its completion date; it does not
rewrite a delivered summary. Reports use the configured candidate and preserve
original application outcomes. Existing observed aliases and accepted matching
decisions deduplicate posting counts; contradictory semantic chains cannot merge
distinct requisitions. The separate Activity page retains its documented
start-date cohort semantics.

Preview without sending:

```text
python -m job_applier.daily_summary --config /absolute/runtime.json --date 2026-10-07 --timezone America/Chicago
```

`test_daily_summary.py` covers synthetic counts, midnight/completion boundaries,
daylight saving, duplicate skips, retry exhaustion and delivery retries.

## Individual submission alerts

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
