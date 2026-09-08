---
name: job-apply
description: Run repository-managed job applications with tracking.
version: 0.4.4
author: Rejo Z Mathew (rejozmathew), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jobs, managed-worker, repository-entry]
---

# Job Apply — Hermes entry point

This is the thin Hermes discovery layer. The application repository owns the procedures and executable helpers; do not copy its workflow into this profile.

## When to Use
- An authorized application or application benchmark using the configured JobBot project.
- For implementation work, inspect repository code/tests rather than starting an application.

## Procedure
1. Resolve the repository from the active Project or configured JobBot `app_repo`. Require an explicit runtime config; never choose a database by cwd or a similarly named checkout.
2. Use `read_file` on `<repo>/skills/productivity/job-apply/SKILL.md`. Its relative references resolve from that repository directory, not this entry-point directory.
3. For Workday, also read `<repo>/skills/productivity/workday-simplify/SKILL.md`. Use the shipped native `jobbot fast_forward` operation or its documented same-runtime CLI, not one-off polling scripts.
4. Follow the repository local start/session procedure. Configuration selects identity, documents and workspaces; the host resolves ownership/target. No token export, running HTTP service or expiring shared lease is required. Another harness uses the same CLI.

## Pitfalls
No in-run PDF extraction or experience/education reconstruction. Do not compete with Simplify, clear every nonblocking review warning, bypass ownership, or resubmit an uncertain application. A fresh URL does not authorize using a stale run or another candidate.

## Verification
The canonical repository skills supply submission evidence, accepted sources and measurements. A user request to apply plus those skills is sufficient; no separate benchmark prompt or historical review log is required. An updated skill or passing fixture is not evidence of a live application.
