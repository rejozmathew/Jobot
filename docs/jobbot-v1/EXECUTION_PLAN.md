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
Stages 1 and 2 are implemented, independently reviewed and committed. Stage 2 commit 31217b7772b624fbb797b848a243102024e42495 also passed 281 tests from the clean detached verification worktree; two known dependency warnings. Full Stage 2 receipts/file inventory are STAGE2_EVIDENCE.md and STAGE2_FILES.md. Final independent review-stage2-final/verdict.json passed R1–R8; native installed Hermes dispatch + real isolated Chromium stand-in smoke passed two jobs/one session with automatic tool events, residual corrections, no submissions, and released leases. Official Simplify/ATS and real model-inference coverage is not claimed. All its servers stopped, ports verified closed, temporary API credentials removed.

Stage 3 is starting: maintain existing FastAPI/plain HTML/CSS/JS stack and palette, operator/monitor layout. Gemini prepared test_settings_views.py and test_operator_ui.py; only preparation tests are uncommitted, no Stage3 production changes yet. Primary corrected settings-test invented budget/model fields, nonexistent attempt getter, and inconsistent completed/blocked/remaining arithmetic; re-run RED before implementation. Next vertical slice: effective versioned settings + truthful shared data projections and protected operator API. Then operator login/static UI and app views, followed by lessons/helper catalogue/assets/assessments. Preserve the main architecture and stage order.

All testing-only work continues through configured agy Gemini 3.8 Flash Medium/High, with primary source review/local verification. Primary retains implementation, architecture and integration. No real application/account/reset, active application-skill deployment, profile/history overwrite, VM/Ubuntu/cron work, git push or deployment is authorized. Finish later with Windows acceptance and an explicit Ubuntu rollout plan, not a claimed live-portal success.
