# Greenhouse recovery and progress implementation — September 9

The six tracks in [the authorized plan](GREENHOUSE_RECOVERY_PLAN.md) are
implemented in the original checkout. The implementation baseline was local
checkpoint `54324f5`. Final verification passed all 761 tests, with no failures,
errors or skips, in 352.84 seconds. The results below retain the failures found
and corrected during engineering.

This report records checkpoint `184717e`. The later
[shared retry policy](RETRY_POLICY.md) supersedes its cross-attempt uncertainty
restrictions and advances job-apply to `0.5.7` and workday-simplify to `0.3.15`.
The 761-test result below applies
only to the preceding implementation. The user prohibited new tests and further
regression execution for the follow-up; its review basis is source/diff inspection.

## Delivered behavior

| Area | Implementation and evidence |
| --- | --- |
| Initial filling | Readiness and observations return platform-appropriate calls. Greenhouse uses shared Simplify Autofill; Workday retains its runner. First Autofill and startup timing are distinct. |
| Shared selections | Inventory, question capture, history and exact verification agree on committed labels beside empty inputs. Filter text/highlighting do not count. Real page and embedded fixtures cover delayed rerender, unrelated menus and exact selection. |
| Private verification | Configured mailbox handoff, recipient/portal/employer/purpose/time correlation and complete-group private filling. Real top-page and embedded fixtures cover fresh resend, stable unlabeled refs, no partial fill on changed refs, and screenshot/history protection. No provider TTL is assumed. |
| Submission recovery | Fresh employer rejection resolves its own action/document/frame and cycle. Two consecutive synthetic rejections can each be corrected before one successful submission. Unknown dispatch, stale/cross-frame errors, failed reconciliation and contradictory success remain protected. |
| Job labels | Missing company/role are enriched in the existing job record, preserving labels/outcomes and verified URL aliases. Backfill previews exact job/attempt evidence separately. All portal views use the same labels and discovery status. |
| Progress | Stage/task projection precedes display limits. Field, Workday, private verification, answer-queue and submission producers attach meaningful activities. Completion requires evidence; actual input waits and unioned action durations stay separate. Debug chronology is collapsed and expansion survives refresh. |

Canonical procedure is job-apply `0.5.6` and workday-simplify `0.3.14`.
Contracts, callers and the helper map are in [APPLICATION_RUNTIME.md](APPLICATION_RUNTIME.md#shared-recovery-and-progress-contracts).

## Validation

The authenticated Antigravity CLI ran the tests with `gemini-3.8-flash-medium`,
the repository virtualenv, installed jsdom fixtures and an explicitly configured
Brave executable. The primary engineering agent made implementation/test changes
and independently inspected the combined logs and JUnit case results.

| Check | Recorded result |
| --- | --- |
| Selection before implementation | 6 failures, 2 passes |
| Routing/metadata before implementation | 10 failures |
| Private verification before implementation | 14 failures |
| Submission rejection before implementation | 5 failures, 7 passes |
| Retry protection before implementation | 1 failure, 1 pass |
| Semantic progress before implementation | 6 failures |
| Combined focused recovery checks | 91 passes, 2 failures exposing unstable unlabeled verification refs |
| Private verification and embedded forms after that fix | 42 passes; no failures/errors/skips |
| First complete managed suite | 754 passes, 6 failures; no errors/skips; 284.84 seconds |
| Recheck of affected files | 43 passes, 1 obsolete lifecycle expectation; no errors/skips; 110.72 seconds |
| Full suite after runtime fixes | 760 passes, 1 browser-fixture startup failure; no errors/skips; 368.31 seconds |
| Startup readiness recheck | 1 pass; no failures/errors/skips; 1.39 seconds |
| Full suite after fixture correction | 760 passes, 1 Windows process-lookup timeout before browser launch; no errors/skips; 299.39 seconds |
| Lifecycle environment recheck | 1 pass without code changes; no failures/errors/skips; 92.81 seconds |
| JavaScript syntax | Three separate `node --check` invocations passed for the dashboard, form controls and submission observer |
| Final complete managed suite | **761 passes; no failures/errors/skips; 352.84 seconds** |

The final suite retained four existing deprecation warnings: AnyIO's
`BlockingPortal` alias, Pydantic class-based configuration, `websockets.legacy`
and `WebSocketServerProtocol`. The primary checked both the full log and all
761 JUnit case results, as well as each separate JavaScript syntax result.

Focused checks also found and corrected fixture issues: explicit UTF-8 and a
stubbed bootstrap request for the real dashboard DOM test, a cross-frame test
flag that needed a shared DOM attribute, and an older Workday activity-label
expectation. One mistyped test filename collected no tests; that run is retained
as an invocation error and is not counted as validation.

The complete suite identified two implementation causes: metadata enrichment
rejected already verified alternate posting URLs, and a conditional import
shadowed the shared field helper during ordinary runtime filling. The fixes
preserve existing identity evidence and remove the import shadowing. Two older
DOM fixture models also needed standard attribute/selector methods used by the
expanded masking and progress UI. Their behavioral assertions remain, with
mask visibility/restoration checked explicitly.

The lifecycle recheck then reached its old assertion that an actual successful
fill leaves the progress timestamp unchanged. It now checks that the real
65-second idle gap leaves progress unchanged and the subsequent verified fill
advances it. This retains the no-heartbeat/no-expiring-lease test while exercising
the new automatic field evidence.

The next full run passed all those cases and exposed a Windows sharing race:
the synthetic browser's startup file existed while its write handle still
prevented reading. The fixture now waits for readable, valid port data within
its original 15-second deadline. Application startup behavior and the embedded
Simplify routing assertions are unchanged.

The following full run encountered an existing Windows process-enumeration
timeout before creating the lifecycle browser. Primary inspection of its
isolated session record identified `Get-CimInstance Win32_Process` exceeding its
10-second limit. That run passed the other 760 cases. The ownership check and
timeout were retained. The separate lifecycle recheck passed without code
changes, including the real idle gap, crash isolation and driver handoff.

The real dashboard HTML, JavaScript and stylesheet were rendered with synthetic
records at 1440×1080 and 600×1000. Primary visual inspection confirmed readable
stage/task layouts, a compact completed stage, visible active/recovering questions
and collapsed Debug details. The preview used no managed database or live API.

## Reproduction and retained evidence

From the original checkout:

```powershell
$env:JOBBOT_BROWSER_TEST_EXE = 'C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe'
$env:PYTHONIOENCODING = 'utf-8'
.venv/Scripts/python.exe -m pytest tests/jobbot_v1 -q
```

Delegated runs disable the optional pytest cache and use fresh basetemp, combined
logs and JUnit under the ignored `artifacts/jobbot-v1-private/greenhouse-20260909`
directory. The descriptive prefixes in the table correspond to the retained
`selection-*`, `runtime-*`, `verification-*`, `rejection-*`, `retry-*`,
`progress-*`, `recovery-integration`, `final-suite`, `final-verified`, `final-clean`
and `final-confirmed` evidence. Delegation
prompts/results remain private too.

All employer forms, mailbox messages, profiles, databases and screenshot previews
used here are synthetic. No live application was submitted, no real mailbox was
read, no production metadata backfill ran, and attempt 45 was not rewritten or
retried. Live ATS acceptance and actual provider expiry behavior remain untested.
