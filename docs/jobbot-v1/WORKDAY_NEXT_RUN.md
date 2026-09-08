# Clean-thread Workday benchmark

## Before timing

- Open a fresh conversation in the JobBot project using the configured application model (not the engineering model by accident).
- Start/reload the existing configured JobBot service/native integration from the updated checkout so the process imports the new helpers. Do not overwrite the database or clear historical runs.
- Resolve the existing private config and credentials through their configured references. Ordinary Hermes shells can use the configured `credential_files` fallback without inheriting launcher environment variables. Read [internal connection setup](HERMES_CONNECTION.md), then verify authenticated CLI worker health; do not paste secrets or launch a separate worker conversation.
- Run `workday_fast doctor` with the proposed URL. Check old submission history, exact new database, configured browser and any unresolved ownership. If reconciliation is needed, resolve it explicitly before the timed application—not by changing the old outcome.
- Establish the authorized managed run and exact claimed attempt. If intake/startup needs work, report that separately from browser execution; do not quietly exclude it from the total user-visible time.

## Copy-ready prompt (fill placeholders)

> Apply to this Workday role: **<WORKDAY_URL>**. I authorize submission of this application using my approved profile/resume and configured portal credentials.
>
> Use the project at **<REPOSITORY>** and its explicit private runtime config **<CONFIG_PATH>**. Read `skills/productivity/job-apply/SKILL.md` and `skills/productivity/workday-simplify/SKILL.md` from that repository—not a stale personal copy. Run the preflight/legacy duplicate check. Use the existing configured managed app/database for new tracking; do not create or migrate a database.
>
> Use the repository's **`jobbot fast_forward` / `job_applier.workday_fast advance`** path under a properly claimed attempt and exact Simplify-enabled target. Do not rewrite helpers, spawn an engineering agent, scrape PDFs, reconstruct experience/education or audit every optional field. Let Simplify finish, follow enabled Continue, and handle only actual required blockers. Use configured native credentials rather than generated passwords; do not reset passwords.
>
> Target **under 10 minutes to verified submission** for the application itself. Record total time from this request as well as browser-application time, startup/reconciliation overhead, helper wait/click metrics and manual/user interventions. Don't exclude delays without showing them. Submit once in authorized mode, verify the employer's exact requisition status, and record the outcome in the managed database. If a real blocker occurs, preserve the page and give me the exact blocker instead of starting a rabbit hole.

## Report format

| Measurement | Actual result |
|---|---|
| Total request → confirmed outcome | measured or unavailable |
| Startup/intake/reconciliation | measured separately |
| Browser application → employer confirmation | measured |
| Helper elapsed/wait/clicks | private checkpoint + action events |
| Autofill retries | per-step counters |
| Manual repairs | count + semantic category, no private values |
| User interventions | count + reason |
| Native employer evidence | exact role/requisition/status |
| Managed attempt | exact ID and read-back outcome |

No speed claim until the live measurement exists. Do not reapply to the previous GAIG R9045 test role; the legacy-history check suppresses it.
