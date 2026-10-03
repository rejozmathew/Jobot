# Activity statistics

Activity opens with application results, followed by current applications,
recent session history, and paginated attempt history. Selecting an attempt
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
- Distinct jobs: unique job IDs among those attempts.
- Queue dispatches: queue records actually started in the same period. Pending
  queue entries are excluded. Dispatches and attempts are independent counts;
  a dispatch may create multiple attempts, and an attempt may start directly.
- Recorded outcomes: the current stored outcome for completed attempts in the
  start-date cohort. Completion may fall outside the selected dates. Unfinished
  attempts appear as In progress. Missing completed outcomes remain visible as
  Outcome not recorded. All other recorded outcome values are retained.
- New submissions: completed attempts recorded as `applied`. `already_applied`
  appears separately and does not count as a new submission.
- Per-attempt rate: new submissions divided by all cohort attempts.
- Per-job rate: distinct jobs with a new submission in the cohort divided by
  all distinct jobs in the cohort. Repeated successful attempts for one job
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
