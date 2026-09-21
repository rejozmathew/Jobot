---
name: job-apply
description: Run repository-managed job applications with tracking.
version: 0.4.7
author: Rejo Z Mathew (rejozmathew), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jobs, managed-worker, repository-entry]
---

# Job Apply — Hermes entry point

The repository owns application procedures and helpers; keep the workflow there.

## When to Use
- An authorized application or application benchmark using the configured JobBot project.
- For implementation work, inspect code/tests without starting an application.

## Procedure
1. Resolve the repository from the active Project or configured JobBot `app_repo`. Require an explicit runtime config; never choose a database by cwd or a similarly named checkout.
2. Use `read_file` on `<repo>/skills/productivity/job-apply/SKILL.md`. Its relative references resolve from that repository directory, not this entry-point directory.
3. Immediately use the canonical local start command with `wait_seconds:0`; read ATS detail while the browser prepares. No exploration, doctor, repeated reads or planning turn before start. Configuration selects identity, documents and workspaces; the host resolves ownership/target.
4. For Workday, read `<repo>/skills/productivity/workday-simplify/SKILL.md` during startup, check session readiness/context and use `jobbot fast_forward` or its documented CLI. No token, HTTP service or expiring lease is required.

5. For Greenhouse, read `<repo>/skills/productivity/job-apply/references/greenhouse.md` and use `jobbot greenhouse_advance` with `{"seconds":60}`. Return grouped approved answers and resume this operation, including after missing-email reload recovery.

## Pitfalls
No in-run PDF extraction or experience/education reconstruction. Do not compete with Simplify, clear every nonblocking review warning, or bypass ownership. A prior submit click or uncertain history is not a blanket veto: continue the current form's verification/edits and follow the canonical retry policy for a fresh explicit request. Recorded successful submission suppresses duplicates. A fresh URL does not authorize using a stale run or another candidate.

## Verification
The canonical repository skills supply submission evidence, accepted sources and measurements. A user request to apply plus those skills is sufficient; no separate benchmark prompt or historical review log is required. An updated skill or passing fixture is not evidence of a live application.
