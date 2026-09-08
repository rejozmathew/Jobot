# Auto Job Applier — repository instructions

## Application execution (any harness)

- Read `skills/productivity/job-apply/SKILL.md`; for Workday also read `skills/productivity/workday-simplify/SKILL.md`.
- These repository files are canonical. Hermes discovery is a thin entry point under `integrations/hermes_jobbot/skills/job-apply/`; other harnesses read the same canonical skills directly.
- Use the explicit configured managed app/database and a claimed owner/fence/target. Never guess `job_applier.db` from cwd, dual-write old tracking, or bypass uncertain submissions.
- Run `python -m job_applier.workday_fast doctor --config <absolute-config> --url <job-url>` before Workday intake. Use the repository virtualenv's Python.
- Use `jobbot fast_forward` or `python -m job_applier.workday_fast advance ...` for Workday's normal path. The CLI is harness-neutral; it does not launch a model.
- Simplify fills; the harness handles exceptions. No in-run PDF extraction, resume hunts or reconstruction of career/education fields, on any ATS. Approved file upload remains allowed.
- Never edit helpers/skills during an application benchmark. Follow actual controls, preserve quiescence/ownership checks and verify employer submission once.

## Engineering

- Read `docs/jobbot-v1/APPLICATION_RUNTIME.md` for helper responsibilities, shared versus Workday scope, and data ownership before adding another helper.
- Preserve dirty user changes. Never use live applications as fixtures or alter private production records to make tests pass.
- Add a focused failing regression, implement the bounded fix, then run the relevant tests and one final suite. Standard managed-suite command: `python -m pytest tests/jobbot_v1 -q`.
- Keep profiles, credentials, databases, private screenshots/transcripts, lock/checkpoint files and node fixture dependencies out of Git. Use the ignored private artifacts area for deployment-specific configuration.
- Update the helper map when adding/removing a caller or helper. A new fast path does not prove older helpers unused.
