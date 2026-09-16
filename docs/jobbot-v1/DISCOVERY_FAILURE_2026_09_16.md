# Discovery failure investigation — September 16, 2026

The Ubuntu timer was healthy and checking the saved four-hour cadence. The
10:25 and 14:26 CDT discovery runs ended without `records.json`, despite Hermes
returning process exit code zero. The earlier 06:24 run saved four records and
its intake response reported four canonical jobs with no failed items.

Both incomplete runs have retained Hermes errors from LM Studio: `Context size
has been exceeded.` The later run repeatedly compressed history before exiting;
its final reported history estimate was not the model's total active allocation.

The loaded Qwen model advertised a 100,608-token context with four concurrent
predictions. Synthetic validation against that same instance accepted a
20,015-token prompt and rejected a roughly 40,015-token prompt, both requesting
only eight output tokens. Inference-engine diagnostics identify exhausted shared
KV cache, not an unavailable search source: one slot held 39,499 tokens while
another held 61,496 tokens, exceeding the shared allocation. The engine tried
smaller batches down to one token, then returned the context error for both
active tasks. Consequently, reducing one discovery conversation below the
advertised model capacity alone does not resolve contention between clients.

The model server is shared with other conversations. Changing concurrency and
reloading it requires operator approval because it affects those conversations.
No model reload, profile change, or application restart is part of the reporting
fix below. The synthetic capacity probe is distinct from live discovery success.

## Reporting correction

`harvest_runtime` now includes `completed`, `incomplete`, or `failed` in its
returned and privately saved result, consistent with the existing dashboard
classification. The CLI exits nonzero for missing records even when Hermes
returns zero, so systemd no longer reports that incomplete run as successful.
The original executor exit code remains available. A schedule check returning
`not_due` still exits zero. Saved empty results retain existing completion
semantics; a result file remains separate from proof of successful intake.

This does not change discovery cadence, retries, result publishing, application
eligibility, or preserved historical outcomes. It adds no automatic model reload
or extra worker.

## Validation

Antigravity with `gemini-3.8-flash-medium` reproduced four failing synthetic CLI
regressions before implementation. They cover zero/nonzero executor exits with
and without records. A fifth case preserves successful `not_due` checks.
JUnit and model-capacity evidence remain in the ignored private artifacts area.
The primary agent independently checked the logs and JUnit: 45 focused tests
passed, followed by 878 passed and five skipped in the final managed suite
(883 total, no failures or errors, four dependency deprecation warnings).
`git diff --check` passed. These synthetic checks establish reporting behavior,
not successful live discovery or a model-server memory repair.
