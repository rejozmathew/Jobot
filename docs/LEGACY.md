# Legacy application and historical entry points

[Documentation index](README.md) · [Current setup](GETTING_STARTED.md)

The original browser-use application remains in the repository for compatibility
and historical reference. It is separate from the current managed Jobot dashboard,
local session runtime and selected managed database.

## Recognize the old path

| Legacy component | Purpose |
|---|---|
| `run_applier.py serve`, `job_applier/api.py` | Original dashboard, conventionally port 8000 |
| `run_applier.py apply`, `run-all`, `job_applier/agent.py`, `runner.py` | Original browser-use execution/queue path |
| `db_queue.py`, `queue.py`, `run_queue.py` | Older SQLite/JSON queue interfaces |
| `.env.example`, `profile.example.json`, `requirements.txt` | Original environment/profile/dependency setup |
| `step_tracker.py`, `application_tracker.py`, `browser_use_overrides/` | Original tracking, reporting and compatibility pieces |
| `platform_handlers/` | Older ATS callers; some still share current Simplify/control components |

The legacy server can create/use its own database and show a different history.
The legacy Windows/Git Bash launcher `scripts/ensure_cdp.sh` honors `CDP_PROFILE`;
when unset, it resolves the current Windows user's Local AppData folder. It no
longer assumes a particular developer's home directory.
Current startup is `python -m job_applier.queue_runtime serve` with the selected
private runtime configuration. Current application execution starts through
`application_runtime` or the Hermes `jobbot` tool.

## Reading older material

- [CONTEXT.md](legacy/CONTEXT.md) records the original February development context.
- [APPLICATION_WORKFLOW.md](legacy/APPLICATION_WORKFLOW.md) preserves an older
  Simplify-first tracker workflow. Its root-database/profile assumptions do not
  select the current managed instance.
- [Historical modernization handoff](jobbot-v1/HISTORICAL_HANDOFF.md) preserves
  September planning and acceptance language from the earlier documentation index.
- [Engineering reference index](jobbot-v1/README.md) separates current references
  from acceptance snapshots, proposals and dated validation records.

Keep historical results and dates intact. They are evidence of those checkpoints,
not current policy, support guarantees or setup instructions. In particular, older
retry caps, generic stop descriptions and experimental benchmarks must not override
the current canonical skill and shared retry policy.

Do not remove legacy modules just because a newer implementation exists. Search
their callers and inspect compatibility tests first. No legacy application was
started or migrated as part of the structured documentation rewrite.

## Public repository cleanup (October 2026)

One-off root Workday probes, scratch scripts, profile backups, a dry-run queue and
timing records were removed from the public source tree. They are not supported
entry points or test fixtures. Maintained checks live under `tests/`; current
operator procedures live under `skills/` and `docs/`. Older narrative context is
grouped under `docs/legacy/`. Root compatibility launchers remain available.

Legacy account creation no longer has a shared built-in password. An explicit
profile password takes precedence, followed by `JOB_APPLIER_FALLBACK_PASSWORD`.
When neither is configured, a cryptographically random password is saved per
portal hostname and login email in `profile.json.credentials.db` beside the
selected profile (the name follows the selected profile filename). Repeated runs
reuse it. Keep that ignored database private and include it in your private backups;
on Windows restrict the profile folder to your OS account. Existing employer
accounts still require their actual credentials. This does not change managed
runtime credential ownership or introduce a new application approval step.
