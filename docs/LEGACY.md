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
| Root `t_wd_*`, `_wd_*`, `scratch/` | Historical probes and one-off diagnostics, not the maintained test suite |

The legacy server can create/use its own database and show a different history.
Current startup is `python -m job_applier.queue_runtime serve` with the selected
private runtime configuration. Current application execution starts through
`application_runtime` or the Hermes `jobbot` tool.

## Reading older material

- [CONTEXT.md](../CONTEXT.md) records the original February development context.
- [APPLICATION_WORKFLOW.md](../APPLICATION_WORKFLOW.md) preserves an older
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
