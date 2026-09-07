# Native Windows pilot and cleanup checkpoint

> **Historical baseline (`e711112`), not current live acceptance.** Subsequent Huron attempts failed, including a credential-field failure after a 440-pass offline suite. Work is now paused for independent review. Read [REVIEW_HANDOFF_2026-09-07.md](REVIEW_HANDOFF_2026-09-07.md) for the accumulated changes, actual outcomes, and unresolved decisions. The baseline success below must not be represented as proof of the new Workday flow.

## What is proven

- One explicitly authorized Greenhouse application was submitted by the native `gpt-5.6-luna` / Low worker through the existing `openai-codex` subscription. The employer confirmation and managed Applied ledger were independently read. Private identity, resume, employer receipt, screenshots and history remain outside Git.
- The dashboard exposes model, reasoning effort and submission mode, with actual worker/run state and completed controls. The official Simplify multi-shadow-root defect was fixed for that pilot.
- Final candidate verification: **411 passed, 0 failed, 0 errors, 0 skipped** (JUnit duration **93.691 seconds**), with the two existing deprecation warnings. Python compilation and dashboard JavaScript syntax checks passed. Gemini executed the tests; results were read back from actual JUnit output.
- A separate real headed Brave cleanup smoke used a NEW temporary profile and synthetic database, not an employer form. For both normal-success and blocked-exit cases it verified that the owned target disappeared and an unrelated target remained. Measured create/bind/close/check durations were **0.109** and **0.094 seconds**. The isolated browser process was then stopped.

## Timing and problem coverage

`attempt_report` retains wall-clock duration, phase slices, unioned model/tool intervals and uncertainty. Phase times and model/tool times are alternative views and must not be added together.

The new worker attaches safe field identifiers and labels to native action context, records measured native action time, checks field readback, and emits structured problems and later resolutions. Raw answers, selected option text, passwords and verification codes do not belong in telemetry metadata. The attempt detail UI presents field actions, Simplify results/residuals and problems.

Simplify's total operation time is counted once from its measured tool action. Its result reports residual fields and fallback reasons, but **per-field Simplify timestamps remain unknown** because the extension does not expose them. Historical missing field attribution is not reconstructed or relabeled as complete coverage.

## Owned-tab lifecycle

1. Validate the lease/fence and exact owned target before browser mutations.
2. Save an independently observed employer receipt (and screenshot when available) before successful-page closure.
3. Send `Target.closeTarget` through a **browser-level** CDP connection. A page-level connection can disappear before acknowledging its own close and stall cleanup.
4. Verify target absence, record the target closed, then finish/release the attempt.
5. Use the same cleanup on normal failed/blocked worker exits. Preserve a known employer submission even if later cleanup fails. A clicked-but-unconfirmed submit remains unknown and must not be blindly retried.

Only application-owned tabs close. Shared dashboard/user tabs and the shared browser process remain intact. A failed ownership/closure/ledger check is explicitly pending; this is not a crash-proof browser supervisor.

## Open acceptance gates

- **New native worker Workday support and live acceptance:** exact wizard/application navigation, account/login handoff, Workday-specific upload selection and confirmation. The older Workday handler's successful history does not prove this new worker path.
- Actual multi-page/account-creation pilot, including any human login/verification handoff. No account was created or reset during this checkpoint.
- Cross-application helper execution/reuse, authenticated mailbox correlation, unattended crash recovery and a new independent release review.
- Ubuntu/Unraid deployment remains separately authorized and was not performed.

This is a tested Windows development checkpoint, not full unattended acceptance. No additional employer application was started for the telemetry/cleanup changes.

## Reproducible offline checks

From the checkout, use its Python environment and a NEW ignored synthetic database:

```text
JOB_APPLIER_DB_PATH=<new-ignored-db> BROWSER_USE_CDP_URL=http://127.0.0.1:1 <python> -m pytest tests -q --tb=short --junitxml=<ignored-result.xml>
<python> -m compileall -q job_applier integrations
node --check job_applier/static/jobbot.js
git diff --check
```

Focused coverage: `test_managed_hermes_worker.py`, `test_telemetry_cleanup.py`, `test_worker_shutdown.py`, `test_worker_inventory_labels.py`, and `test_timing_reports.py` under `tests/jobbot_v1/`.
