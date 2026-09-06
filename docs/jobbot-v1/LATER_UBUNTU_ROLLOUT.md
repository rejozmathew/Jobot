# Later rollout: Windows accepted release to existing Ubuntu VM

This document is deferred. Do not execute it during the Windows implementation/test phase.

## 1. Publish the right things

Commit/review/publish application source, sanitized canonical skills/references/helpers, migrations, tests, dependency metadata, configuration examples and installation/update instructions. Use an approved branch/commit; do not merge or force-push by implication.

Keep real `.env`, profile facts, passwords/tokens, mailbox contents, resumes, runtime databases, browser user-data, private lessons, diagnostic spools and backups out of Git. Ignore rules do not untrack previously committed files. Inspect staged/tracked paths and report concerns without printing secrets; any credential rotation or history rewrite is separately authorized work.

Export a manifest with code commit, skill/helper hashes, schema version, expected runtime capabilities and tested dependency versions. This gives Ubuntu a defined release, not an ambiguous 'copy everything'.

## 2. Update the existing installation

After authorization, inspect `ubuntubot`, login ownership, actual repo/service paths, dirty worktree, database instance, installed Hermes/profile, active workers, and the existing headed Chrome/Simplify profile. Preserve this installation; no OS reinstall, global browser kill, or wholesale profile copy.

Back up/reconcile before changing active state. Deploy the approved commit and skill source. Create a new Linux virtual environment and install dependencies from the tested definition; do not copy the Windows `.venv` or binaries. Configure Linux paths and process/service commands explicitly. Preserve the existing graphical browser session or restart it in a controlled way when required.

Keep Codex optional. The Windows Hermes builder may administer the rollout through authorized SSH; a VM-local worker should run steady-state applications. SSH terminal access alone does not prove the browser tool is targeting the VM's browser. Confirm the actual CDP endpoint/target. Keep CDP on loopback; use a protected tunnel for remote diagnostics rather than exposing it.

## 3. Transfer skills and data differently

Shared skills/helpers come from the reviewed code release. Check effective skill resolution so a stale profile-local copy does not override the new one. Preserve private relevant lessons in an explicit migration and keep credentials separate.

Disposable Windows test data is never deployed as production. If the Windows pilot performed real account creations or submissions, export/import those privately with their IDs, namespace, identity and evidence. Reconcile any existing VM data before import; do not overwrite a newer VM database with an older Windows copy.

Keep historical-submission suppression across old/new email identities. Preserve account creation even where the associated application failed. Store credential references; reconnect/authenticate private providers using their supported flow rather than copying whole credential directories or browser cookies.

Disable the Windows application trigger at the agreed cutover before Ubuntu becomes the sole active owner. Two independent databases cannot enforce a shared single-flight rule by themselves.

## 4. Ubuntu verification

Run the core tests and installed integration against the actual VM environment. Check Python/dependencies, Linux paths/case sensitivity/permissions, service working directory, DB instance/schema, settings, skill/helper versions, display/session and browser ownership, Simplify availability, dedicated mailbox identity, notification destination, and provider/model configuration.

Use an explicit test run before re-enabling unattended work. Verify the timeline, account reuse, residual questions, continuation, acknowledged controls and safe tab cleanup. Do not treat a Windows pass as this validation. Start real applications only under the approved rollout policy.

Record result and failures. If rollback is needed, preserve post-cutover account/submission events and unknown outcomes; do not blindly restore an old DB and lose external-action history. Retain a known previous release/config and tested schema/data recovery procedure.

The final outcome is a controlled update of the existing VM, followed by verification—not a promise that cross-platform deployment requires zero adjustments.
