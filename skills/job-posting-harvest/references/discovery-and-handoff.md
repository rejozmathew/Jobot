# Existing discovery knowledge and new intake boundary

The preserved classifier recognizes ATS fingerprints from supplied HTML. Its dated probes are not current job counts or proof of access. Fetch only verified public HTTP(S) careers URLs; no private credential routes.

- Greenhouse public boards API is usually the simplest unauthenticated source.
- Workday CXS: POST `https://{host}/wday/cxs/{tenant}/{site}/jobs` with appliedFacets, limit, offset and searchText. Discover the tenant/site from the actual careers page; use same-origin browser fetch when required. Verify pagination and counts in code.
- A Workday burst historically caused HTTP 400 plus errorCaseId. Pace one query at a time, then a bounded cooldown; do not interpret every such response as a malformed query.
- HTTP 422 on some tenants was a login barrier; do not brute-force it. JPMC connection failures and unresolved DNS were distinct blockers. Rendered Workday search text could fail to filter the actual board.
- Phenom, Workable and proprietary boards may require rendered inspection or a direct search URL rather than an imagined public API.

The existing mail/alert pipeline and ATS probe remain source producers. Preserve their identities and useful deduplication context, but hand recovered roles to the app through the authenticated intake emitter. Do not patch active mail schedules or copy a personal mailbox. Connector identity must be verified before trusting recipient-specific links.

The emitter accepts only bounded role/source fields, keeps exact identifiers, drops unknown secret/mail fields, and returns one outcome per input. It never approves eligibility, starts a run, or updates an application to submitted. A source's historical “applied” claim is not fresh submission proof. Dynamic exclusions and the selected profile govern subsequent eligibility.

Keep feed attribution (`source_type`, `source_id`) in each record. Use feed names
such as `linkedin_alert_email`, `employer_search`, `job_harvester:google_jobs`,
or `job_harvester:linkedin`; an ATS host alone does not identify the discovery feed.
The scheduled runtime supplies `--producer`, `--discovery-run-id` and, when known,
`--discovery-profile` in its exact intake command. Preserve these command arguments.
Standalone integrations can supply their own process identity with the same flags;
the emitter otherwise identifies itself as `discovery_intake`. Do not copy process
identity from job pages or messages. JobBot retains source observations and queue
origins separately, including multiple sources for a recognized job.
