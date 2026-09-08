# Workday fast path — implementation and verification

## Delivered

Repository-owned shared application policy plus a Workday execution skill, portable bounded runner/CLI, thin Hermes transport/discovery, explicit managed configuration, and read-only legacy duplicate suppression. No real application was started or submitted in this engineering task. The ten-minute target remains a live benchmark target, not a measured result.

## Executed verification

- Baseline Simplify tests: 31 passed.
- Regression tests were exercised RED/GREEN for forward progress, writer state, retry limits, explicit CDP argument handling, DOM metadata, state persistence, duplicate suppression, portable/Hermes routing and post-submit confirmation.
- Full managed suite: `python -m pytest tests/jobbot_v1 -q --junitxml=artifacts/jobbot-v1-private/workday-fast-final-tests.xml` ran 498 tests: 496 passed, two skill-document contract checks failed (human-first metadata and explicit no-redundant-final-audit wording).
- Corrected those document contracts. Added the regression/fix for settling a preceding Start action only when a stable known account control is observed. Targeted recheck of staged skills, application skills, browser observation and Workday API integration: 54 passed.
- Programmatic union of the full-suite and recheck JUnit reports: **499 distinct tests with latest results passing; no failed or skipped tests**. This is combined coverage, not a claim that one final command printed “499 passed.”
- Full run emitted existing Starlette/AnyIO and Pydantic deprecation warnings; dependencies were not rewritten for this task.
- Synthetic end-to-end tests use the actual managed service/API and temporary database, replacing browser observations only: Continue → submission intent → matching simulated employer confirmation → attempt and job read-back `applied`. Both panel-present and panel-disappeared confirmation paths passed.
- Real isolated Chrome/CDP smoke against a synthetic localhost page: explicit structured/nested function arguments; shadow-root Simplify observation; actual Simplify Continue click; native Workday step observation and native click; final Review step observed. No employer page, real credentials or live application used. The isolated test browser was closed and no matching fixture Chrome process remained.
- Basic static checks on added runtime modules found no scanned embedded-secret, shell-execution, unsafe-deserialization or SQL-interpolation patterns. `git diff --check` passed.
- Active rejo `job-apply` skill was read back through `skill_view`: it resolves to the thin repository entry. Canonical workflow files remain in the repository.
- Doctor with the explicit native runtime configuration recognized GAIG R9045 as previously applied in the configured legacy history. No migration, legacy write, duplicate submission or historical outcome change was performed.

Local JUnit reports and smoke script are under ignored `artifacts/jobbot-v1-private/`. DOM tests require Node and the test-only fixture dependency:

```text
npm install --prefix artifacts/jobbot-v1-private/dom-test --no-save --no-package-lock jsdom
python -m pytest tests/jobbot_v1/test_workday_dom.py -q
```

The private directory also contains runtime data; never delete it wholesale as test cleanup.

## Independent review

One bounded read-only review identified submission blocker checks, fresh identity checking, unknown-state authentication handoff, fast-navigation progress accounting and missing-panel post-submit quiescence. These were addressed or verified with focused regressions. No broad review/refactor loop or second application was run. Gemini supplied a bounded initial helper patch but timed out before reporting completion; its output was independently inspected, corrected where needed and tested by the coordinator.

## Changed files and responsibilities

Paths are relative to this checkout. This list excludes pre-existing unrelated auth/mail/native-launcher changes.

| File | Change / purpose |
|---|---|
| `AGENTS.md` | Makes repository-owned execution instructions discoverable to other harnesses and records engineering boundaries. |
| `job_applier/application_runtime.py` | Explicit configuration preflight and read-only legacy duplicate matching; no implicit DB selection or migration. |
| `job_applier/workday_fast.py` | Portable Workday policy, bounded observe/act/wait runner, resumable metrics/checkpoint and CLI. |
| `job_applier/simplify_boundary.py` | Workday fast policy, observed account/submit control normalization and bounded retry behavior. |
| `job_applier/browser_helpers/simplify_observe.js` | Shared shadow-root observation, expanded action vocabulary and active account-step detection. |
| `job_applier/browser_helpers/workday_observe.js` | Workday step, unique native controls, auth references, blocker/attachment metadata and exact-requisition confirmation. |
| `job_applier/browser_helpers/workday_click.js` | Scoped unique native click from an observed step/URL; no fuzzy text clicking. |
| `job_applier/cdp_client.py` | Explicit structured function evaluation bound to a real JavaScript execution context. |
| `job_applier/managed_identity.py` | Same-tenant/career-site Candidate Home read scope; rejects other sites and tenants. |
| `job_applier/managed_runtime.py` | Server-owned writer/quiescence checks for known account transitions and post-submit native confirmation. |
| `job_applier/hermes_plugin.py` | Thin `fast_forward` transport to the portable runner; preserves existing auth changes. |
| `skills/productivity/job-apply/SKILL.md` | Canonical cross-ATS policy, explicit runtime ownership and portable Workday entry. |
| `skills/productivity/job-apply/references/simplify.md` | Shared Simplify-first operating policy and anti-detour rules. |
| `skills/productivity/job-apply/references/workday.md` | Redirects Workday detail to its repository-owned execution skill. |
| `skills/productivity/workday-simplify/SKILL.md` | Workday-specific procedure, authentication handoff, state/retry rules and benchmark entry. |
| `integrations/hermes_jobbot/skills/job-apply/SKILL.md` | Thin Hermes discovery entry; no second copy of the workflow. |
| `docs/jobbot-v1/APPLICATION_RUNTIME.md` | Helper consumers, shared/Workday boundaries, rationale, database ownership and cleanup guidance. |
| `docs/jobbot-v1/WORKDAY_NEXT_RUN.md` | Copy-ready clean-thread benchmark prompt and prerequisites. |
| `docs/jobbot-v1/README.md` | Links the new engineering work while retaining the historical paused checkpoint. |
| `docs/jobbot-v1/WORKDAY_FAST_VERIFICATION.md` | This evidence record and file-level change map. |
| `tests/jobbot_v1/test_application_runtime.py` | Explicit config, legacy duplicate history and portable entry contracts. |
| `tests/jobbot_v1/test_application_skills.py` | Portable skill structure, links and thin-entry separation. |
| `tests/jobbot_v1/test_cdp_evaluate_function.py` | Function/context binding and structured argument regressions. |
| `tests/jobbot_v1/test_simplify_fast_policy.py` | Continue/review precedence, known controls, busy account steps and bounded policy. |
| `tests/jobbot_v1/test_workday_confirmation_scope.py` | Candidate Home scope isolation. |
| `tests/jobbot_v1/test_workday_dom.py` | Executed JavaScript DOM fixtures for Workday metadata and confirmation matching. |
| `tests/jobbot_v1/test_workday_fast.py` | Runner policy, stop/intent safety, progress, retries, resumed state and outcome read-back. |
| `tests/jobbot_v1/test_workday_fast_integration.py` | Real managed API/temporary DB flow, missing-panel finish and account writer settlement. |
| `tests/jobbot_v1/test_workday_fast_plugin.py` | Hermes delegates to the portable runner instead of duplicating it. |

## Local integration changes

- Added `legacy_history_paths` to the selected ignored native runtime configuration, pointing at the existing legacy application database.
- Retargeted only rejo's verified `job-apply` junction to the tracked thin entry. The canonical repository skill was preserved; other Hermes profiles were not changed.
- Existing managed database remains the new-attempt tracking authority. Existing credential/document references remain explicit private configuration, not silently copied data.
- Pre-existing uncommitted auth/mail/native-launcher work was preserved. This engineering task did not commit or push the combined dirty checkout.

## Remaining acceptance

Reload/start JobBot from this updated checkout before the fresh benchmark; an already-running server/plugin may still hold old Python code. Resolve stale run ownership through normal controls rather than relabeling history. Run the new URL only after that preflight, with the configured worker credentials available. Follow `WORKDAY_NEXT_RUN.md` and record actual time, tool round trips, retries and intervention counts. This document does not certify a live Workday run or a sub-ten-minute result.
