# Cross-source duplicate matching

Shared intake identifies supported ATS postings independently of discovery feed,
company display name, title and mutable imported requisition labels. This applies
to every employer; there are no company names, employer domains or live job IDs
in the matching code or fixtures.

For Greenhouse, the board token plus public posting ID identify the posting.
The posting ID is distinct from the employer's `requisition_id` field. A hosted
board URL supplies both. A custom employer URL must supply a consistent `gh_jid`
and a verified namespace or a corroborating `greenhouse:board:posting` source
reference. This supports arbitrary employer URL paths and HTTP/HTTPS aliases
without inferring a board from a company name or matching a bare number across
unrelated employers. Unknown query parameters remain part of the identity.
The same intake entry point uses the existing Workday, LinkedIn and iCIMS
identity readers. No new network call or availability dependency is introduced.

The posting key takes precedence over rediscovered requisition labels. Incoming
conflicting labels do not create a new job, overwrite retained titles or attach
the incorrect requisition as an alias. Existing source provenance is retained.
Generic source IDs and company/title similarity alone do not merge records.
Missing or conflicting posting evidence falls back to existing URL/identity
handling; it does not create a new execution refusal.

Migration 23 adds posting aliases to existing jobs and their retained source URLs.
It preserves all job rows, attempts, source records, evidence and original keys.
Ordinary queue reconciliation removes pending work whose linked history already
records success or explicit cancellation. Active dispatches remain owned by
their existing executor. Unsuccessful and uncertain attempts remain retryable.

The helper/caller map is in [RETRY_POLICY.md](RETRY_POLICY.md). Browser navigation
scope remains separate from intake identity. This change does not read arbitrary
inbox confirmations or infer a successful application from rediscovery metadata;
the existing evidence reconciliation operation records user-provided completion.

Validation uses fictional employers and synthetic databases in
`test_cross_source_duplicates.py`, plus the existing identity, intake and queue
suites. The regression includes wrong incoming titles/requisition labels,
multiple discovery sources, different ATS URL forms, historical aliases, opaque
queries, conflicting IDs, and continued retry eligibility for uncertain history.
