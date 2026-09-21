# September 9 checkpoint regression

The user authorized regression testing of the current Workday/shared-runtime
checkpoint and existing Greenhouse/portal behavior. Runtime baseline: `68a7865`;
the later `3ccd2ed` commit adds the Greenhouse recovery and progress plan only.
The planned Greenhouse changes are not represented as implemented or tested.

Execution uses the authenticated Antigravity CLI with
`gemini-3.8-flash-medium`, the repository virtualenv, installed jsdom fixtures,
and Brave for isolated synthetic browser tests. The primary engineering agent
owns test corrections and independently inspects pytest logs and JUnit.

## Results

| Run | Result | Pytest duration |
| --- | --- | --- |
| Initial focused checkpoint coverage | 117 passed, 12 failed; no errors/skips | 37.91 seconds |
| Corrected focused coverage plus new cases | 145 passed; no failures/errors/skips | 46.28 seconds |
| First managed suite | 694 passed, 1 failed; no errors/skips | 299.27 seconds |
| Corrected boundary-policy test file | 14 passed; no failures/errors/skips | 0.80 seconds |
| Final managed suite after remaining expectation correction | 695 passed; no failures/errors/skips | 283.86 seconds |

The final pytest process exited 0. Its JUnit contains 695 cases across 85 test
classes, including both real isolated browser lifecycle cases. Four existing
deprecation warnings concern Starlette/AnyIO, Pydantic and WebSockets. There are
no skipped browser or jsdom cases. Changed test syntax and Git diff checks pass.
No application-runtime source changes were needed for this regression pass.

The initial focused failures were five obsolete behavior assertions and seven
incomplete fixture cases. No runtime source change was required by those
failures. Updated expectations follow the already accepted behavior: enabled
Simplify Continue takes priority; a changed field fingerprint does not restart
Autofill on the same Workday page. Fixtures constructed with `__new__` now
initialize startup timing, and the bounded-advancement fixture supplies the
no-source-field handoff instead of calling a DOM helper on a nonexistent page.
The full suite exposed one additional obsolete assertion that the default
Simplify boundary should stop at needs-review despite enabled Continue. That
assertion now follows the same shared advancement policy as the fast boundary.

Sixteen new synthetic cases cover:

- Continue before Autofill/source repair across ready, complete and needs-review.
- First Autofill on ordinary and disclosure pages, persisted fill receipts and
  document replacement versus ordinary rerenders.
- Selected source chips inside an open prompt, full question labels, menu
  ownership, category-arrow and radio-label targets, and direct Apply Manually.
- Nested source traversal with an offered fallback and a noncommitting click.
- Loading-to-ready recovery, serialized reload cancellation, protection of an
  unresolved submission, and document replacement in an isolated real browser.

## Reproduction and evidence

From the original checkout, use its virtualenv:

```powershell
$env:JOBBOT_BROWSER_TEST_EXE = 'C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe'
$env:PYTHONIOENCODING = 'utf-8'
.venv/Scripts/python.exe -m pytest tests/jobbot_v1 -q
```

The delegated runs additionally use `-p no:cacheprovider` and fresh basetemp,
combined-output log and JUnit paths under the ignored private directory
`artifacts/jobbot-v1-private/regression-20260909`. Evidence files are
`focused.log` / `focused.xml`, `recheck.log` / `recheck.xml`, and
`final.log` / `final.xml` retain the initial passes and failures.
`policy-recheck.log` / `policy-recheck.xml` and
`final-verified.log` / `final-verified.xml` record the concluding checks.
Delegation prompts and results remain there too.

No live employer application, mailbox, saved candidate profile or production
database is used as a test fixture. Synthetic passes do not establish live
Greenhouse acceptance, correct expiry handling, or delivery of the saved
[Greenhouse recovery and application progress plan](GREENHOUSE_RECOVERY_PLAN.md).
