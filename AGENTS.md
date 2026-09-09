# Auto Job Applier — repository instructions

## Application execution (any harness)

- Read `skills/productivity/job-apply/SKILL.md`; for Workday also read `skills/productivity/workday-simplify/SKILL.md`.
- These repository files are canonical. Hermes discovery is a thin entry point under `integrations/hermes_jobbot/skills/job-apply/`; other harnesses read the same canonical skills directly.
- Start through `jobbot start` or `python -m job_applier.application_runtime start <url>` using the selected private configuration and actual conversation ID. No API token, running dashboard or expiring browser lease is required locally. Never guess a database, dual-write history or bypass uncertain submission.
- Use the repository virtualenv. `application_runtime doctor` is an optional read-only diagnostic; start performs configuration/history and real browser readiness checks automatically.
- Use `jobbot fast_forward` or `python -m job_applier.workday_fast session <session-id> --seconds 60` for Workday. Session-scoped calls resolve ownership and target. The CLI is harness-neutral and launches no model. Explicit HTTP accept/claim/advance is legacy compatibility only.
- Simplify fills; the harness handles exceptions. No in-run PDF extraction, resume hunts or reconstruction of career/education fields, on any ATS. Approved file upload remains allowed.
- Never edit helpers/skills during an application benchmark. Follow actual controls, preserve quiescence/ownership checks and verify submission once using the canonical skill's evidence policy; report the actual evidence source.

## Engineering

- Read `docs/jobbot-v1/APPLICATION_RUNTIME.md` for helper responsibilities, shared versus Workday scope, and data ownership before adding another helper.
- Preserve dirty user changes. Never use live applications as fixtures or alter private production records to make tests pass.
- Add a focused failing regression, implement the bounded fix, then run the relevant tests and one final suite. Standard managed-suite command: `python -m pytest tests/jobbot_v1 -q`.
- Delegate routine test execution and validation to the existing authenticated Antigravity CLI (`agy`) with `gemini-3.8-flash-medium`. The primary engineering agent owns implementation changes and independently checks the reported logs/JUnit; an assigned validation worker should not delegate again or edit source unless explicitly asked.
- Commit each completed, validated engineering change as a local Git checkpoint before reporting completion. Do not leave completed changes awaiting a separate commit request; pushing still requires authorization.
- Keep profiles, credentials, databases, private screenshots/transcripts, lock/checkpoint files and node fixture dependencies out of Git. Use the ignored private artifacts area for deployment-specific configuration.
- Update the helper map when adding/removing a caller or helper. A new fast path does not prove older helpers unused.
