# Focused independent review — Stage 1 core (closed for Stage 1)

Read-only reviewer examined a hashed seven-file core snapshot predating protocol/data/legacy-compatibility additions. The verdict was **not passed**: 2 security and 7 lifecycle/identity concerns. Findings are source-derived until confirmed by tests. Primary Windows Hermes owns fixes; Antigravity Gemini 3.8 Flash High writes/runs regressions only. No reviewer edits/tests/external actions occurred.

| ID | Finding | Regression / disposition |
|---|---|---|
| S1 | Secrets can bypass event filtering through settings, metadata, capabilities or finish evidence/key | `test_review_security.py`; closed: reproduced, primary fix, independent re-review |
| S2 | Quoted JSON credential strings bypass text filtering | `test_review_security.py`; closed: reproduced, primary fix, independent re-review |
| L1 | Another browser profile can reclaim an unreconciled quarantined job | `test_review_lifecycle.py`; closed |
| L2 | Enriching an existing URL with verified identity fails to suppress alternate URL | `test_review_identity.py`; closed |
| L3 | Historical tracking URLs/duplicate legacy rows can bypass suppression | Copy-migration now normalizes simple rows, but duplicate-history preservation needs `test_review_identity.py`; closed |
| L4 | Submission intent can be created after pause/stop acknowledgement | `test_review_lifecycle.py`; closed |
| L5 | Idle/between-job pause has no acknowledgement path | Primary-designed `ack_run_control` regression passed; independently closed |
| L6 | Offset timestamps are compared lexically, refreshing stale progress | `test_review_lifecycle.py`; closed |
| L7 | Replayed non-applied reconciliation resets timestamps/duration | `test_review_lifecycle.py`; closed |

Reviewer also suggested legacy runner gating. Since snapshot, primary implemented that boundary and `test_compatibility.py` passed locally. This does not dismiss other findings. Later API/UI/adapter omissions were explicitly excluded from this review, and no full release approval is claimed.

Additional primary test reviews corrected actual interface/schema mismatches: `action_end(status=...)`, event `actor` / `payload_json`, and a repeated completed-run claim returning None. These are exercised by the fixture-only fake worker, never a real application.

## Final dispositions

- Second review independently closed S2/L1–L7, kept structured-token S1, and added L8 (successful quarantine could not release) and L9 (successful historical attempts hidden by latest failure).
- Primary reproduced the remaining cases: eight failures and one valid-metadata control pass. Fixed recursive token-field rejection, same-outcome lease release with immutable audit and no history/ledger rewrite, and migration-7 recovery of confirmed historical successes. Nine focused tests passed; full suite 120 passed.
- Final targeted review returned `passed: true`, empty security/logic lists and fixed IDs S1/L8/L9. Its completed-log essential verdict fields are preserved verbatim as parsed fields in private FINAL_REVIEW_RECEIPT.json; no truncated narrative is invented. Source hashes independently matched all 18 reviewed files.
- Core and protocol commits were independently exercised from a clean verification worktree (94 and 120 passing tests respectively). This closes Stage 1, not live employer/Simplify/mail or full-release acceptance.
