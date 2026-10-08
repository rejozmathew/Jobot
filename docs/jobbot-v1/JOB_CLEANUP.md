# Job cleanup and cancellation

Use **Applications → Jobs → Select unfinished → Cancel selected** to clear old
test jobs or applications you no longer want to pursue. **Needs attention**
narrows the list to recorded problems; search narrows it by company, role or URL.
Selection applies to the visible list and excludes submitted and canceled jobs.
Cancellation rechecks submission evidence in its transaction, so a job that
submitted after selection is left unchanged. Earlier cancellation reasons are
also retained. Needs attention includes queue failures before an attempt starts.
Choose a reason before canceling. No jobs are canceled automatically because of
failure, age or number of attempts.

Choose **Manually applied** when you submitted the application yourself. This
saves that cancellation reason and removes the job from the unfinished queue;
it does not change recorded application outcomes. The job remains available
under **Canceled**, where you can restore it if needed.

Cancellation is an operator disposition, separate from the application outcome:

- The posting, URL aliases, discovery sources, attempts and submission evidence
  stay in the database. Rediscovery matches the existing canceled posting.
- Candidate profiles, resumes, portal accounts, credential references and account
  confirmation history are retained. Another job on the same portal can reuse
  its existing account through the ordinary account resolver.
- Pending dispatch requests and answer retries are canceled; pending legacy run
  entries are skipped. New requests for the canceled posting are suppressed.
- If an application is in progress, cancellation requests its existing Stop
  lifecycle. The browser must still acknowledge shutdown; the dashboard does not
  claim it has stopped or that an in-flight submission was prevented. A legacy
  multi-job run uses its existing run-wide stop operation for an active attempt.
- **Canceled → select jobs → Restore selected** removes the disposition. Restore
  does not queue work, clear earlier outcomes or bypass recorded submission
  success. Select restored jobs and queue them when ready.

Completed sessions are grouped under collapsed **Recent history** on the front
page. Current sessions remain visible regardless of the number of old sessions.
Application details and debug evidence expand on demand; polling preserves the
operator's expansion choices.

## Implementation and ownership

October 8 extends this operator choice to corroborated company/title matches
when duplicate matching is in `enforce` mode. A rediscovered matching listing is
excluded as canceled, not already applied. Restoring the original or dismissing
an incorrect pair removes this matching-based exclusion. The matcher never copies
the canceled disposition, suppresses a job merely because an attempt failed, or
stops an active dispatch for a different matching job. See
[Cross-source matching](CROSS_SOURCE_IDENTITY.md).

Migration 19 adds disposition, reason and change timestamp columns to `jobs`.
Existing records default to active; no old application outcome is rewritten.
`ArchiveServices.set_job_disposition` owns the operator mutation and updates
pending queue records in one transaction. The same operation applies to existing
identity-linked posting records. `Service._assert_not_suppressed` enforces the
explicit cancellation alongside its existing successful-submission suppression.
`EventServices._control` shares the existing run stop operation with cancellation.
`managed_api` exposes the mutation only to the operator. The dashboard renders the
disposition separately from the retained outcome and filters the returned jobs.
The older preview/backup/archive maintenance operation remains available.

The user explicitly approved exclusion until restoration on September 15, 2026.
This is a requested operator action, not a new automatic failure/retry policy.
Only synthetic databases, sessions and DOM/browser fixtures validate this change.
Restart services through the normal deployment procedure so the selected managed
database receives migration 19 and long-running processes load the new code.

## Validation — September 15, 2026

The authenticated Antigravity CLI (`gemini-3.8-flash-medium`) ran the tests;
the primary agent inspected the logs and JUnit. Evidence stays under ignored
`artifacts/jobbot-v1-private/cleanup-20260915/`.

The first five cleanup regressions failed before implementation. Added stale
selection and dispatch-failure checks also failed before their fixes. The final
focused group passed 38 tests with no failures or skips, covering cleanup,
dashboard rendering, embedded forms and real isolated browser lifecycle.

The first full run exposed an outdated fake DOM and seven confirmation fixtures
whose required fields were still empty. The DOM stub now models form values and
label lookup; confirmation fixtures commit their required answers before testing
submission. No application submission or form-filling code changed. A lifecycle
pause timed out in that run and passed unchanged in the focused recheck.

The primary agent also inspected a real browser preview with synthetic jobs and
16 ended sessions, exercised filtered bulk cancellation and restoration, and
verified that restoring did not enqueue work. The preview was shut down afterward.
No production job, account, application or mailbox was used as a fixture.

The concluding managed suite passed **783 tests**, with no failures or errors;
four Linux-only tests were skipped on Windows. Pytest took 335.22 seconds. The
primary independently verified all 787 JUnit cases, including seven cleanup
regressions, the preserved history scroll position and both browser lifecycle
cases. Final evidence is `verified-final.log` / `verified-final.xml`; the focused
recheck is `verified-focused.log` / `verified-focused.xml`. Existing deprecation
warnings concern Starlette/AnyIO, Pydantic and WebSockets.
