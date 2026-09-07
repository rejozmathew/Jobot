---
name: job-posting-harvest
description: Discover verified roles and hand them to shared intake.
version: 0.1.0
author: Rejo Z Mathew (rejozmathew), Hermes Agent
human_first: true
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jobs, research, intake]
    related_skills: [job-apply]
---

# Job Posting Harvest

Preserve the existing discovery approach and change its output/handoff to the shared app intake. Discovery has no auto-apply behavior and does not approve eligibility or claim work.

## When to Use
Find live official roles for the selected candidate profile, verify links, or import an existing alert/ATS result batch. Do not invent listings when a source is blocked.

## Procedure
1. Read target level, location, work-authorization constraints and dynamic exclusions from selected policy. A senior-manager/IC role is not automatically level-equivalent to senior leadership.
2. Re-verify the dated [ATS map](references/ats-map-2026-08.md). Use `web_search`, `web_extract`, the configured browser, and the preserved [ATS classifier](scripts/ats_probe.py) as appropriate; never assume a stored host remains current.
3. Greenhouse public API: `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs`. Workday CXS searches use the verified host, tenant and site in a same-origin context. See [discovery and handoff](references/discovery-and-handoff.md).
4. Validate official-live status and explicit incompatibilities before any form work. Apply the verdict set **Strong apply / Apply / Apply with caveats / Skip**, with honest level, gaps and sponsorship risk; no fabricated fit scores.
5. Account for every recovered role, including closed, excluded, incompatible, weaker-fit and blocked items. Keep source IDs and original URLs; deduplicate through app identity rules, not blanket query stripping.
6. Send bounded records through [intake_results.py](scripts/intake_results.py): `terminal(command="<python> skills/job-posting-harvest/scripts/intake_results.py --config <explicit-config> --input <records-json> --dry-run", workdir="<app-repo>")` previews without writes. After approval omit the preview flag to publish to intake only. Report every per-item outcome and actual counts.

## Pitfalls
Workday WAF/challenge responses, a login wall, DNS lookup failures and CORS failures are different states. Avoid bursts and speculative hostnames. Never bypass login barriers or rewrite payloads simply because a WAF rejected a burst. Verify helper availability; workspace auto-import is not guaranteed.

## Verification
Read back canonical job/source rows through the app. Imported postings remain held for eligibility review. No automatic application or submission can be inferred from an import. Source failures remain visible, with direct official links when available. Raw emails, credentials and private mailbox contents are not intake payloads.
