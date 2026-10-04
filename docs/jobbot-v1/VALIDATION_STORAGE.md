# Synthetic validation storage

On October 4, 2026, the existing Ubuntu VM's 40 GB disk had about 1 GB free.
Several gigabytes were completed synthetic browser profiles under `~/.cache`.
Previous cleanup scripts abandoned all cleanup whenever any same-user process
had protected `/proc` metadata. Chromium sandbox processes, systemd and ssh-agent
normally protect some of that metadata, so completed fixtures accumulated.

`scripts/cleanup_validation_fixtures.py` removes only explicitly registered,
completed validation directories. It verifies the saved report hash and each
directory's device, inode and owner, restricts removal to known synthetic names
directly under the selected cache root, and checks live process references. An
unreadable command line retains candidates; protected optional environment,
memory-map or descriptor metadata is recorded without globally vetoing cleanup.
Zombie and exited processes do not retain fixtures. Reports and logs are retained.
The utility does not clean application storage, personal browser profiles, Hermes
history, package caches, deployment backups or arbitrary cache folders.

The user systemd service and daily timer in `deploy/systemd` use the existing
Ubuntu runtime path. They can run alongside applications without restarting them.
The scheduled cleanup keeps registered fixtures for at least 24 hours after both
directory modification and completion-record modification. A dry run is the
default; `--apply` performs removal. Inspect its JSON result and the service journal.

## Registering a validation run

Before starting synthetic tests, save a private `<label>-fixtures.json` with
`phase: "running"` and the exact directory identities from `path.lstat()`:

```json
{
  "phase": "running",
  "directories": {
    "/home/USER/.cache/jvb-UNIQUE": {"device": 1, "inode": 2, "uid": 1000},
    "/home/USER/.cache/jvt-UNIQUE": {"device": 1, "inode": 3, "uid": 1000}
  }
}
```

Use fresh short `jvb-`/`jvt-` directories for pytest `--basetemp` and `TMPDIR`;
long paths can exceed browser socket limits. After the test process exits and
its owned browser fixtures are closed, update the record to `phase: "completed"`,
save integer `pytest_exit` and `report_sha256` (SHA-256 of the final JUnit report).
The report defaults to `<label>.xml` beside the manifest. Alternatively set
`report_path` to an absolute `.xml` file in that same private directory.
Preserve logs/JUnit outside fixture directories. Completed failing runs can also
be cleaned after the retention interval; their reports remain available.

Do not adopt arbitrary existing directories into this registry. Legacy fixtures
can be registered only after checking their original synthetic runner and final
JUnit/log evidence, capturing their current identities and inspecting references.
Unregistered, running, recently modified or identity-changed directories stay put.
