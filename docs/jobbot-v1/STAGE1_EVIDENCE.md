# Stage 1 evidence ledger (closed — NOT release acceptance)

Environment: Windows, isolated sibling worktree `jobbot-v1-windows`, Python 3.11.15 `.venv/Scripts/python.exe`, synthetic pytest temp DBs. Original baseline commit `923f2576f9c059370222ef416f50f97a8cfc9f70`; documentation checkpoint `e26aecd`. No live applications or shared runtime migration.

## Test ownership
Gemini 3.8 Flash High is used **only** for tests through existing `http://127.0.0.1:8010/v1/chat/completions`; catalog and agy 1.1.27 model inventory verified. Private request/result briefs are ignored under artifacts/jobbot-v1-private. Primary Hermes implements services, reviews tests and reruns locally. Proxy response/model and actual local test output, not helper prose, determine acceptance.

## Execution log
1. `.venv/Scripts/python.exe -m pytest tests/jobbot_v1/test_ownership.py -q` -> RED: 4 failed (missing `Service.identity`), 0.56s; independent Gemini RED run also observed 4 failures, with 2 existing core tests passing.
2. After ownership implementation, `.venv/Scripts/python.exe -m pytest tests/jobbot_v1 -q` -> 6 passed, 1 existing warning, 1.84s.
3. Gemini authored `test_events.py` and improved child-process cleanup in `test_ownership.py`; primary reviewed both. Primary tightened race assertion to require one claimed + one rejected, not one claimed + arbitrary error, and guarded cleanup for unstarted processes.
4. `.venv/Scripts/python.exe -m pytest tests/jobbot_v1/test_events.py -q` -> RED: 8 failed for missing event/action/control/status methods, 1.63s (matching Gemini's RED result).
5. After telemetry/control implementation, `.venv/Scripts/python.exe -m pytest tests/jobbot_v1 -q` -> 14 passed, 1 existing warning, 3.95s.
6. Combined baseline/new selected tests initially -> 1 failed, 24 passed: old runner eagerly imported the uninstalled legacy `browser_use` framework even when mocked execution did not use it. Primary moved that import into `_create_agent`; did not install another autofill stack or run the legacy agent.
7. Exact selected regression command:
   ```bash
   JOB_APPLIER_DB_PATH=C:/GitClone/auto-job-applier-jobbot-v1/artifacts/regression-synthetic.db BROWSER_USE_CDP_URL=http://127.0.0.1:1 .venv/Scripts/python.exe -m pytest tests/test_application_tracker.py tests/test_tracking_cli.py tests/test_track_time.py tests/jobbot_v1/test_core.py tests/jobbot_v1/test_ownership.py tests/jobbot_v1/test_events.py -q
   ```
   -> **25 passed, 1 pre-existing Pydantic warning, 9.48s**, exit 0.
8. `.venv/Scripts/python.exe -m compileall -q job_applier/managed.py job_applier/managed_migrations.py job_applier/managed_events.py job_applier/managed_redaction.py job_applier/managed_shared.py job_applier/runner.py` -> exit 0.
9. `git diff --check` -> exit 0 (line-ending notice only).

## Initial vertical-slice files (historical)
- `job_applier/managed.py`: explicit-instance service, intake/identity/run snapshots, atomic claims, ownership/fences, finish/reconciliation/retry.
- `job_applier/managed_migrations.py`: additive versioned schema over original jobs/attempt/account tables; durable run/browser/event/action state.
- `job_applier/managed_shared.py`: protocol exception and serialization/ID primitives.
- `job_applier/managed_events.py`: immutable sanitized events, action duration tracking, verified progress, truthful controls and status.
- `job_applier/managed_redaction.py`: allowlisted semantic payloads; raw arguments/results/reasoning and secret fields not persisted.
- `job_applier/runner.py`: legacy agent import becomes lazy; legacy execution otherwise unchanged in this slice.
- `tests/jobbot_v1/test_core.py`: synthetic instance/intake identity tests.
- `tests/jobbot_v1/test_ownership.py`: independent-process claim, expiry, idempotence and submission-unknown tests.
- `tests/jobbot_v1/test_events.py`: Gemini-authored telemetry/control tests, reviewed and executed by primary.
- `requirements-jobbot-lock.txt`: actual installed lightweight environment dependency versions.
- `docs/jobbot-v1/EXECUTION_PLAN.md`: checkpoint and user-specified test delegation ownership.
- This evidence ledger.

Outside repo: active profile `skills/software-development/requesting-code-review/SKILL.md` maintenance note overrides unsafe old recipes (masked test exits, stashing/resetting dirty user work, indiscriminate staging, delegated production auto-fix contrary to user ownership). No job-apply/harvest/browser profile change.

## Additional verified slices
- Safety/account RED: `.venv/Scripts/python.exe -m pytest tests/jobbot_v1/test_safety_regressions.py tests/jobbot_v1/test_accounts.py -q` -> 8 failed (four concrete safety defects, four missing account APIs). Primary fixed active-writer finish, stale reconciliation, secret-bearing profile rejection and immutable budgets; implemented metadata account/correlated mail services. Full offline suite then **33 passed, 1 warning, 10.66s**. Gemini independently reported the same 33-test baseline green.
- Protocol/data RED initially reported missing modules (2 collection errors). Primary corrected Gemini client fixture's absent transport fallback to an explicit in-process transport before it could contact a real localhost service. Implemented authenticated API/client and verified SQLite data-copy/backup tools. Focused `.venv/Scripts/python.exe -m pytest tests/jobbot_v1/test_protocol.py tests/jobbot_v1/test_data_tools.py -q` -> **13 passed, 2 warnings, 2.26s**.
- Compatibility RED: 5 failed, 1 passed. Primary corrected test use of nonexistent `add_url` and `sources.url` to the actual `add(AddJobRequest)` and `sources.original_url` contract. Reproduced meaningful RED (duplicate intake, unsafe legacy writes/cleanup). Routed managed legacy intake to shared service, bound queue sessions to their actual manager, guarded legacy writes and legacy runner before cleanup. Useful report reads preserved.
- Latest exact full command: `JOB_APPLIER_DB_PATH=C:/GitClone/auto-job-applier-jobbot-v1/artifacts/regression-synthetic.db BROWSER_USE_CDP_URL=http://127.0.0.1:1 .venv/Scripts/python.exe -m pytest tests -q` -> **52 passed, 2 warnings, 15.68s**, exit 0. Warnings: old Pydantic Config and installed Starlette/AnyIO alias deprecation.
- Original checkout rechecked: still hermes-modified at approved 923f2576..., only original untracked docs. Ignored handoff/brief paths verified with git check-ignore.

Additional files since earlier inventory: `job_applier/managed_accounts.py`, `managed_api.py`, `managed_client.py`, `managed_data.py`; existing `database.py`, `db_queue.py`, `application_tracker.py`; tests `test_accounts.py`, `test_safety_regressions.py`, `test_protocol.py`, `test_data_tools.py`, `test_compatibility.py`; docs `WORKER_PROTOCOL.md` and requirement map. CLI/continuity and review fixes are still in progress; final inventory must come from Git and include all new files.

## Earlier checkpoint (superseded by closure below)
Service fixtures are not full Q/R/T acceptance. Account/correlation tests and stricter safety regressions are assigned to Gemini. Primary must review their RED results, fix services, rerun full offline regression, then complete authenticated protocol/CLI, safe data tooling and compatibility guards. Independent release review not yet done. Windows real-tool/extension/mail evidence remains pending; no Ubuntu change, push or deployment.


## Review regressions and current gate
- First focused review failed S1/S2/L1–L7. Primary reproduced them with agy-authored `test_review_security.py`, `test_review_lifecycle.py`, `test_review_identity.py`; fixed pre-persistence secret checks, quoted-secret filtering, durable identity-key relationships, global uncertain-owner blocking, historical suppression, pending-control gating, idle control acknowledgement and UTC progress comparisons.
- `test_managed_cli.py` + `test_continuity.py`: 9 failed/3 passed RED → 12 passed.
- `test_fake_worker.py`: missing module RED; primary review corrected actual `actor` / `payload_json` assertions (no vacuous checks) and completed-run claim idempotence → 2 passed.
- `test_protocol_types.py`: 8 failed/1 passed RED → strict JSON booleans and positive integer ownership IDs at the API boundary.
- Latest exact full command: `JOB_APPLIER_DB_PATH=C:/GitClone/auto-job-applier-jobbot-v1/artifacts/regression-synthetic.db BROWSER_USE_CDP_URL=http://127.0.0.1:1 .venv/Scripts/python.exe -m pytest tests -q --tb=short && .venv/Scripts/python.exe -m compileall -q job_applier run_applier.py && git diff --check` → **111 passed, 2 warnings in 32.64s**, chain exit 0.

## Real-process Stage 1 transport smoke (not live ATS acceptance)
Primary ran ignored `protocol_smoke.py prepare`, a tracked background `serve`, authenticated `health`, then `exercise` against a new synthetic DB/config. The exercise invoked the public CLI separately for intake, reservation, fake worker, attempt status and events, then read the database projection. Assertions passed: fixed two jobs, single session, two events each, no submitted rows, released lease, completed run. No model inference, browser, portal, account action or email occurred. Main startup/worker commands used clean subprocess environments with temporary local-only credentials. Primary terminated the exact owned process, verified the port closed and removed those credentials; retained DB and result evidence privately. This smoke preceded final strict-request-type hardening; that change is covered by protocol tests and the final release integration must exercise the final code again.

Second independent read-only source review is pending; Stage 1 is not yet marked reviewed/committed. Stages 2–4 remain unimplemented except interface discovery. No Windows release candidate or deployment claimed.

## Stage 1 closure and exact verification

Final review regressions: `.venv/Scripts/python.exe -m pytest tests/jobbot_v1/test_final_review_regressions.py -q --tb=short` → 9 passed (eight genuine RED failures plus one already-valid metadata case before fixes). Full worktree regression/compile/diff command → **120 passed, 2 warnings in 34.88s**, exit 0.

Reviewed commits:
- `8432bd7e2db1774fd61242f3ac7c11e6eeaf575e`: core/data/compatibility foundation, 26 explicitly staged files.
- `503e43c88d9cf41a52cec8a130ebf958d7fc8b86`: authenticated protocol and CLI, nine explicitly staged files.

Created a clean detached verification worktree at `C:/GitClone/auto-job-applier-jobbot-verify`. At each commit ran:
```bash
JOB_APPLIER_DB_PATH=C:/GitClone/auto-job-applier-jobbot-v1/artifacts/verify-core.db BROWSER_USE_CDP_URL=http://127.0.0.1:1 C:/GitClone/auto-job-applier-jobbot-v1/.venv/Scripts/python.exe -m pytest tests -q --tb=short
C:/GitClone/auto-job-applier-jobbot-v1/.venv/Scripts/python.exe -m compileall -q job_applier run_applier.py
git status --short
```
Foundation: **94 passed, 1 warning in 27.45s**, compile success, clean. At the second commit, the DB environment path was `artifacts/verify-protocol.db`: **120 passed, 2 warnings in 28.20s**, compile success, clean. Only a normal detached switch in this newly created clean verification worktree was used; no reset/clean/force, no original checkout change.

Final code-pinned real-process smoke: same `protocol_smoke.py prepare/serve/health/exercise` commands, new synthetic instance, public CLI and authenticated actual localhost server. Assertions again passed. Final source-manifest hash `cd4f860e4f25da5288e4bbc97f81f4ccd1ce445b0b6764993912f322cc7bc1ff` matched before and after. Owned server was killed, its closed port verified, and temporary API credentials deleted. Artifact directory: `artifacts/jobbot-v1-private/protocol-smoke-41a6b6aa3e1944039c51020e19bf5a9b/`. DB/result/manifest retained; no inference/browser/portal/account/email action.

Full authored source inventory: STAGE1_FILES.md. Review dispositions: REVIEW_NOTES.md. Stage 2 begins with the five Antigravity-authored adapter RED tests; no Stage 2 production code was included in these commits. Full Windows RC and Ubuntu readiness remain unclaimed.
