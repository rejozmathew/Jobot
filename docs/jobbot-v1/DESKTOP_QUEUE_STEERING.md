# Desktop steering for queued applications

The legacy queue command starts `hermes chat --oneshot` with no interactive
stdin. Hermes Desktop can read that CLI conversation's stored transcript, but
its send handler cannot acquire the CLI's active-session lease. This is why a
visible conversation could reject a correction as "open somewhere else".

The optional `hermes_desktop` transport creates the application in the existing
desktop backend through its native JSON-RPC WebSocket. Opening that conversation
in Desktop attaches to the same live session. Ordinary busy-input behavior and
the native `session.steer` / redirect controls remain Hermes responsibilities.
Jobot does not remove ownership locks or run a second agent for corrections.

New application prompts begin with the assigned company and role, which Hermes
uses for the visible chat label. The desktop adapter keeps that heading before
its task marker, skill list and conversation ID; those internal details remain
in the prompt and receipt for ownership and reconnect handling. Testing only the
unwrapped application brief does not cover this desktop title contract.

Select it in the private runtime configuration:

```json
{
  "hermes_desktop": {
    "profile_home": "/home/example/.hermes",
    "skills": ["browser-tab-hygiene"],
    "yolo": true
  }
}
```

`yolo` is per-session and should mirror the deployment's existing `--yolo`
selection; omit it to inherit native approvals. The application model/provider
inherit the selected Hermes profile by default. Jobot Settings can explicitly
override the application provider/model for new dispatches using the catalog from
that profile. The selection is passed to `session.create`, not written back to
the global profile, and a running application retains its existing model.
Discovery retains its own CLI command
and profile. The old application CLI command remains available when the
`hermes_desktop` selection is removed.

On Linux the transport finds the profile's existing `hermes serve` process and
its owned loopback listening socket, preferring the Electron-owned backend.
It handles Desktop's random port without storing the bootstrap token. An
explicit local HTTP `url` can select a backend on other platforms. The desktop
backend must be running, just as the configured CLI must exist for CLI dispatch.

The private `dispatch/<request>/desktop-session.json` receipt contains runtime
and stored conversation IDs plus the backend process identity. The monitor
stays alive through working and human-input states. Reconnects monitor the same
session without resubmitting its prompt. If the monitor dies, queue recovery
checks the native session before closing its application browser. Backend exit
returns to the existing interrupted-attempt handling. Native idle state and
monitor exit never establish successful submission; the recorded Jobot outcome
remains authoritative.

Existing CLI-owned runs keep their owner until they exit. This setting changes
new queue dispatches and does not force-take an active conversation. Preserve
active child processes when restarting the dispatcher during deployment.

## Email diagnosis

The reported extra character was present in the executor's commentary, while
the candidate record, selected private profile, email form field, and observed
verification recipient agreed on the correct address. The brief now includes
`application_email` directly from the selected candidate and instructs the
executor to copy observed values exactly when reporting a discrepancy. A claim
in earlier commentary is not evidence that the form or mailbox was changed.
This does not establish why the employer's verification email was not delivered.

## Validation — September 15, 2026

Antigravity `gemini-3.8-flash-medium` ran the failing regressions before the
implementation, then the focused tests and full managed suite. The final suite
reported 798 passed and 42 skipped; six additional staged Linux transport tests
passed on Ubuntu. A harmless native conversation, using a terminal sleep rather
than a live application, accepted a correction from a second desktop connection
and returned the corrected response. Private logs, JUnit files, and session
receipts remain in the ignored artifacts/spool locations.
