# Activity statistics

[Dashboard guide](../USER_GUIDE.md#activity) · [Data model](../DATA_MODEL.md)

Activity opens with application results, followed by current applications
and paginated attempt history. Selecting an attempt
opens its existing evidence and timeline. Legacy selected-run controls and
diagnostics remain available in a collapsed section.

The period selector offers Today, Last 7 days, Last 30 days, Lifetime and
Custom dates. Calendar dates use the saved JobBot timezone. Seven/thirty-day
windows include today; custom endpoints include both selected dates. Day
boundaries follow daylight-saving changes. The results reflect the database
as of the displayed update time and exclude future start timestamps.

`activity_stats` is an operator-only read operation in `ReportServices`.
It reads the authoritative database without changing attempts, job status,
dispatch policy or submission evidence. There are no migrations or new helpers.

- Application attempts: all attempts started in the selected period, including
  retries and attempts for jobs later canceled or archived.
- Distinct jobs: postings among those attempts, deduplicated through connected
  observed identity aliases, including links through records outside the cohort.
  `recorded_jobs` separately preserves the raw unique job-ID count.
- Queue dispatches: queue records actually started in the same period. Pending
  queue entries are excluded. Dispatches and attempts are independent counts;
  a dispatch may create multiple attempts, and an attempt may start directly.
- Reported outcomes: the current outcome classification for completed attempts in
  the start-date cohort. Explicit prior-application evidence is reported as
  `already_applied`, even if an older stored row says `applied`; raw rows are not
  rewritten. `recorded_outcomes` preserves the original stored counts and each
  history row retains `recorded_outcome`. Completion may fall outside the selected
  dates. Unfinished
  attempts appear as In progress. Missing completed outcomes remain visible as
  Outcome not recorded. All other recorded outcome values are retained.
- New submissions: completed attempts reported as `applied`, excluding affirmative
  already-applied evidence. `already_applied` appears separately and does not count
  as a new submission.
- Per-attempt rate: new submissions divided by all cohort attempts.
- Per-job rate: distinct postings with a new submission in the cohort divided by
  all distinct postings in the cohort. Repeated successful attempts for one posting
  count once in this numerator.

Empty cohorts show zero counts and an unavailable rate, rather than inventing
zero success. ID endpoints describe the minimum/maximum ID in the cohort;
gaps do not imply missing attempts. Pagination changes only history rows, not
the aggregate counts. Saved job status, queue outcomes and the submission ledger
do not manufacture attempt outcomes or backfill missing historical evidence.

Synthetic coverage in `tests/jobbot_v1/test_activity_stats.py` checks date
boundaries, timezone offsets and legacy UTC timestamps, daylight-saving days,
retry deduplication, complete aggregates despite pagination, archived/canceled
jobs, empty cohorts, API authorization, period switching and stale responses.
