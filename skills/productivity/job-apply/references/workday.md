# Workday execution

The canonical Workday-specific procedure is [workday-simplify](../../workday-simplify/SKILL.md). Read that file rather than maintaining a second Workday recipe here.

The shared job-apply skill still owns identity, documents, budgets, private account/mail handling and outcome recording. Workday adds authentication form stages, same-URL step detection, native advancement and requisition-specific submission confirmation.

Use the shipped `job_applier.workday_fast` runner; no in-run PDF extraction or independent career reconstruction. Runtime/data ownership and the helper inventory are in [APPLICATION_RUNTIME.md](../../../../docs/jobbot-v1/APPLICATION_RUNTIME.md).
