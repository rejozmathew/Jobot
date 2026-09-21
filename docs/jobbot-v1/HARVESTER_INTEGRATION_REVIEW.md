# Job Harvester review and prepared integration

Reviewed September 16, 2026. GitHub HEAD was verified as
`1e200932dabcc8313d79f18d80959281ad848cbc` (January 28, 2026).
The existing checkout at `C:\GitClone\job-harvester` also contains uncommitted
changes, including apply-queue endpoints and location handling. Those files were
reviewed without modification. The integration below works with the committed
`GET /latest` export; it does not depend on those uncommitted apply endpoints.
No production data, mailbox, Harvester service, schedule, or deployment was changed.

## Assessment

Reuse Harvester as an additional lead source. It already has Google Jobs search,
provider IDs, saved application-link candidates, optional scoring, CSV export,
SQLite storage, a paginated read API, and a scheduler. Keep JobBot authoritative
for candidate selection, canonical job identity, queue execution and outcomes.

These findings affect the proposed 10–20 new suitable jobs per day:

| Finding | Evidence | Effect and recommended follow-up |
| --- | --- | --- |
| Search pagination is absent | `app/sources.py`, both provider `search` methods issue one request then slice the returned array | `MAX_RESULTS=50` does not fetch 50 Google Jobs results. Add next-page token handling in Harvester. |
| Google date filtering is outdated | Google request sets `chips=date_posted:week` | Current SerpAPI documentation marks `chips` deprecated. Use current returned filters and verify freshness on employer pages. |
| Stored URL is not necessarily an employer application | Google URL selection prefers `link`, then the first `related_links`, then an apply option; `_valid_url` checks syntax only | Resolve saved apply options and confirm the employer/requisition before existing JobBot intake. An aggregator link or HTTP 200 alone is not open-status evidence. |
| Duplicate checks happen after enrichment and scoring | `Runner.run_once` calls `fetch_full_description` and `score_and_blurb` before `Store.upsert` | Move cheap source/identity lookup ahead of expensive operations; retain deliberate refresh separately. |
| Known rows are never refreshed | `Store.upsert` returns false for existing IDs/SerpAPI IDs | Stored descriptions, scores and open status may be stale. Preserve first discovery while recording later source observations. |
| Provider errors can look like empty search results | Missing key/non-200 returns `[]`; HTTP 200 is counted successful before inspecting a JSON error | Separate unavailable/error/empty outcomes and persist per-run counts. Verify the optional LinkedIn engine against the selected account before relying on it. No live provider test was performed. |
| Title matching uses substrings | `_is_senior` accepts chief/vp/director/head/lead/principal and rejects intern/junior/entry | `Senior Manager` and `Vice President` can be missed; `International` can match `intern`. Align discovery with the selected profile and use word-aware matching. |
| Estimated dates are presented as timestamps | `_normalize_date` computes relative dates from the current time | Keep these as reported dates until employer evidence establishes the original posting date. |

The current [SerpAPI Google Jobs documentation](https://serpapi.com/google-jobs-api)
documents up to 10 results per page, `next_page_token`, the deprecation of `chips`,
and the current `uds` filter mechanism. Provider documentation was checked during
review; no paid search requests were made.

## Implemented locally

The JobBot queue now displays:

- **Source:** first retained discovery reference, with expandable references for
  every additional source, its first recorded time, source ID and discovery link.
  Source strings are rendered as text. A job with no retained provenance says Unknown.
- **Added:** original `jobs.created_at` in the selected dashboard timezone.
  Rediscovery and retries do not reset it. This is JobBot intake time, not a
  Harvester insertion time, employer posting date or execution-queue time.
- **Last disposition:** newest recorded operator cancellation/restoration,
  completed application outcome, or completed dispatch outcome, with its time and
  evidence category. A new running attempt and metadata refresh do not erase it.
  If no such evidence exists, it says Not recorded; `updated_at` is not used as a guess.

These are projections over existing source, job, attempt and queue records; no
schema migration or historical rewrite is needed. Existing original-source records
that were only labeled generically remain generic. The view does not infer a feed
from the ATS hostname or attempt executor. A restoration is shown as Restored,
even when the prior attempt failed; the ordinary status column retains that outcome.

`job_applier.harvester_source` is an **offline export converter**. It accepts a
saved `/latest` JSON array, wrapped `items` response, or existing Harvester CSV.
It produces a separate unverified lead file with source references, candidate
links and explicitly reported source dates. It omits private notes, descriptions,
model scores and fit verdicts. It never connects to Harvester, writes JobBot's DB,
claims a job or enqueues an application. Invalid rows are counted separately;
partial conversion exits 1 and invalid input exits 2. Source references use the
Harvester ID, otherwise the provider ID, otherwise a canonical-link hash. Use a
consistent export format across scheduled imports to keep references stable.

```powershell
.venv/Scripts/python.exe -m job_applier.harvester_source `
  --input artifacts/jobbot-v1-private/harvester-export.json `
  --output artifacts/jobbot-v1-private/harvester-leads.json
```

When connecting later, save a read-only `/latest?wrap=true&limit=100&offset=0`
response from the actual private Harvester endpoint, paginate as needed, and
convert it. Never confuse this API pagination with the missing upstream search
pagination. No live pull client, incremental cursor or recurring import was
installed in this change.

An optional `harvest_leads_path` in the selected private runtime config supplies
the converted file to the existing discovery brief. The discovery executor checks
these candidates using its existing profile/live-posting procedure, retains their
`source_type` and `source_id`, and publishes verified records through the existing
`intake_results.py`. Omit the config field to keep the integration inactive.
No private config was changed here.

## Daily yield and additional sources

Treat 10–20 as a target for **new, unique, suitable JobBot intake**, distinct from
leads fetched, records rediscovered, retries, or applications submitted. A useful
initial plan is four discovery passes a day targeting about five verified new jobs
each, drawing from employer searches, Harvester and eventually email alerts.
This is a capacity plan, not a demonstrated yield. The current default of five
per run every four hours permits up to 30 findings daily, but duplicate or weak
matches can make the number of new suitable jobs much lower.

Before enabling, complete the Harvester pagination/filter fixes and measure a
seven-day pilot: fetched leads, employer-verified leads, duplicates, closed roles,
fit exclusions, new canonical jobs, queue entries, source errors and elapsed time.
Attribute daily new jobs to their first retained source and count each canonical
job once. Additional-source sightings should not inflate daily acquisition counts.
Use original JobBot intake timestamps for daily cohorts. Avoid raising discovery
volume blindly if verification, repeated duplicates or stalled runs are the bottleneck.
This source-yield report and target-driven top-up scheduling remain future work.

LinkedIn alert email is a compatible next feed. The existing discovery brief can
use the configured mailbox, but there is no dedicated incremental alert extractor
in this change. Use `source_type=linkedin_alert_email` and a stable
`source_id=<message-id>:<job-id-or-link-hash>` for each job within a message.
Resolve tracking links to the actual employer posting, apply the same candidate
matching and JobBot identity checks, and preserve the source reference when the
same job arrives from another feed. Raw email and private headers stay out of intake.
Persist mailbox cursors/message processing results in the selected private state
when building that connector; do not mark messages processed before their per-job
results are saved. No mailbox was connected or read for this review.

## Validation

Synthetic regressions cover multi-source rediscovery and idempotency, original
intake time, missing historical provenance, cancellation/restoration, prior outcomes
during retries, queue-only outcomes, safe dashboard rendering, export conversion,
malformed rows, CSV references, and discovery brief handoff. Antigravity runs the
tests with `gemini-3.8-flash-medium`; the primary agent reviews logs and JUnit in
ignored `artifacts/jobbot-v1-private/source-provenance-20260916/`.
The focused run passed 51 tests. The full suite passed 791 and skipped 41;
independent JUnit inspection found that the browser executable setting had not
reached pytest. A targeted rerun of those 37 browser cases passed all 37, leaving
only four Linux-specific skips: **828 distinct managed tests passed, zero failures**.
Both collapsed and expanded source columns were visually inspected using an
isolated synthetic Chrome preview at 1280 pixels wide. Diff checks passed.
Live provider availability, match quality and daily yield have not been measured.
