# JobBot v1 — living Windows execution plan

## Scope and safety
Approved PRD remains authoritative. Implementer: Windows Hermes. Reversible local stages are authorized without per-edit approval; external actions, real data migration, activation, publishing and Ubuntu remain gated. No normal applications while engineering.

Baseline: `hermes-modified` / `923f2576f9c059370222ef416f50f97a8cfc9f70`. Implementation branch `jobbot-v1-windows` in a separate sibling worktree. Original checkout has only untracked supplied docs; unchanged. Supplied six documents copied byte-for-byte, originals preserved.

Private resume reference: `artifacts/jobbot-v1-private/RUNTIME_HANDOFF.md` (verified ignored). It contains actual paths, skill/helper inventory, source-inspected historical workflows and sanitized runtime evidence, not secrets/mail/transcripts. Never stage `artifacts/`.

## Verified baseline
- Original 3.14.2 interpreter, pytest 9.1.1: `JOB_APPLIER_DB_PATH=<worktree>/artifacts/baseline-synthetic.db BROWSER_USE_CDP_URL=http://127.0.0.1:1 <original>/.venv/Scripts/python.exe -m pytest tests -q` -> 11 passed, 21 existing deprecation warnings, 21.17s.
- Isolated .venv Python 3.11.15; pinned lightweight dependencies installed without modifying the original venv. Do not run root `t_wd_*` scripts: they are live browser probes, not offline tests.
- Installed Hermes v0.20.5, local 30f9955a; exact plugin registration signatures inspected. Config default and active desktop model gpt-6-astra/openai-codex. Live subscription catalog and minimal inference HTTP 200; completed response model gpt-6-astra. No fallback/API-key route.
- Production inspected read-only: no jobs running, one unfinished legacy attempt. No application worker command identified, but liveness scan alone does not resolve that attempt.
- Configured real CDP endpoint unavailable. Gmail connector metadata-only request 401; identity/dedicated scope not verified. Real browser/mail gates pending, no reset/relaunch/refresh performed.

## Design decisions
1. Extend existing `jobs`, `application_attempts`, `company_portal_accounts`; preserve old diagnostic tables. Versioned additive migrations, synthetic legacy fixtures, no live DB migration.
2. One shared service transaction boundary for API/local client/compatible queue intake. SQLite independent connections with BEGIN IMMEDIATE and durable browser leases/fencing. Expiry quarantines, never auto-reassigns. Applied/historical suppression survives email changes.
3. Authenticated loopback HTTP `/v1` operations, thin local CLI, explicit instance/config. Fixed ordered batches remain awaiting worker until accepted; no invented Hermes wake endpoint or additional scheduler.
4. Attempt events immutable/idempotent, redacted before persistence/spool, attributed to action-start attempt. Wall-clock segments/monotonic tool spans; progress separate from heartbeat; truthful pause/stop acknowledgement.
5. Staged native Hermes plugin/tool adapter uses installed interfaces. No core patch or mandatory new-session-per-job. Safe local fixture browser first; real Simplify evidence separately gated.
6. Canonical sanitized skills versioned in repo; preserve useful discovery/scheduled/CDP references. Explicit preview/stage/sync workflow, no half-written active skill and no automatic shared repair activation.
7. Existing FastAPI + plain HTML/JS stack retained. Minimal operational UI from DB, no routine screenshot/reasoning dump. Settings, helpers/lessons, external document/assessment metadata are actual storage features.

## Stages and checkpoints
### 0 — Inspect/preserve/isolate (completed)
Baseline, private handoff, provider verification, separate worktree and requirement map captured; checkpoint commit e26aecd. No live work.
### 1 — Core services
Vertical test-first slices: migrations/config+identity/intake; run acceptance+atomic claims; fencing/idempotence/unknown outcomes; accounts; events/timing/controls; safe data tools; compatibility/API/client and fake worker. Run focused and full offline tests. Independent review before stage commit.
### 2 — Adapter and skills
Inspect installed dispatch, implement native plugin automatic timing/spool/correlation/control. Staged canonical skills and bounded Simplify boundary. Fixture tests; installed integration later uses verified runtime dispatch. No legacy full-form fallback.
### 3 — UI/settings/knowledge/assets
Connect DB-driven UI and controls; settings snapshots; scoped lessons/helpers with versioned cross-session reuse; external fit/doc storage/display; XSS tests and local browser review.
### 4 — Harden/integrate/review
Run every matrix case and record evidence. Explicit isolated Windows server/browser test run using real Hermes tools and app telemetry, assertions not narration. Serial integration after code freeze. Live extension/employer/mail tests remain pending without authorization/access. Fresh reviewer, fix findings, publish release manifest/report/rollback and launch instructions. Stop before push/deploy.

## Completion gate
The requirement map is the checklist, not a green aggregate alone. Each stage report lists exact changed files, commands and outcomes, gaps and next action. A release candidate is not live acceptance. Do not call Windows/Ubuntu ready while required evidence is pending.

## Current checkpoint
Stage 1 complete for the scope in IMPLEMENTATION_PROMPTS.md lines 29–35. Reviewed source commits: `8432bd7e2db1774fd61242f3ac7c11e6eeaf575e` (core/data/legacy guards) and `503e43c88d9cf41a52cec8a130ebf958d7fc8b86` (HTTP/CLI/fake worker). Both verified in a clean detached verification worktree: first **94 passed, 1 warning, 27.45s**, then **120 passed, 2 warnings, 28.20s**. Compilation and clean status verified there. No push/deployment. The original checkout remains at the approved commit with only its supplied untracked docs.

Final targeted independent review explicitly passed S1/L8/L9 with empty security/logic lists. Fully visible verdict fields and completion status are preserved in ignored `FINAL_REVIEW_RECEIPT.json`; the source log's long narrative suffix is truncated and is NOT reconstructed. Final reviewed 18-file source hashes were checked again before and after a separate real localhost CLI/API smoke. It passed one-session/two-job assertions, 2 events per attempt, zero submissions, released lease, completed run. Final code-manifest SHA256: `cd4f860e4f25da5288e4bbc97f81f4ccd1ce445b0b6764993912f322cc7bc1ff`. Server stopped, port closed, temporary auth removed. Synthetic DB/evidence retained privately. No browser, Simplify, mailbox or inference involved.

**Next: Stage 2.** Antigravity test-only task `proc_a255b1802012` completed: `tests/jobbot_v1/test_hermes_adapter.py`, five expected RED cases because the adapter module does not exist. Primary must read/review it, rerun RED, then implement the adapter/client/hooks against the installed interfaces documented in HERMES_INTERFACE.md. Do not restart or replan. Test work remains exclusively agy Gemini 3.8 Flash Medium/High with primary review/local reruns; implementation and final integration remain primary-owned. No adapter implementation, staged canonical skills or UI yet.

Later whole-product acceptance (including scoped archive/maintenance D3) stays in the requirement map; Stage 1 completion is not release acceptance. No application/discovery skill, agent config, candidate profile, real history, browser data or cron modification. A general review-skill safety note was changed; see STAGE1_FILES.md.
