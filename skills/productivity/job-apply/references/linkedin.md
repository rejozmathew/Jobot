# LinkedIn applications

Read the canonical job-apply skill first. Start with the selected configuration,
current conversation and normal owned workspace. A LinkedIn hostname identifies
the portal, not the application type. Observe the assigned job and actual account
state. Discovery authentication does not establish browser authentication.

For **confirmed Easy Apply**, use the registered native operation:

```text
jobbot(operation="linkedin_easy_apply", parameters={"seconds":60})
.venv/bin/python -m job_applier.application_runtime call <session-id> linkedin_easy_apply --parameters '{"seconds":60}'
```

Use `.venv/Scripts/python.exe` on Windows. This helper connects to the current
owned page. It opens/reuses the Easy Apply dialog, runs available Simplify
Autofill first on each form step and waits for settlement, then batches residual
approved answers and selected résumé handling and advances Next/Review.
A missing extension permits supported native recovery.
It preserves prefilled answers and does not change follow-company choices.

`questions_required` returns a batch of full labels/options/current refs. Resolve
them from the approved context and exact saved answers using ordinary browser
fill/select/check. For genuinely missing required information, use the existing
`browser request_answers` / human-answer workflow. Resume `linkedin_easy_apply`
in this same session after answers or technical recovery. `inspection_required`
and an elapsed call slice are executor handoffs, never automatic finish outcomes.
Inspect the owned screenshot when a control is missing; use shared reload/restart
or a supported native control, then continue. Never discard the draft automatically.

`ready_for_review` preserves configured review mode. In configured submit mode the
helper calls Jobbot's existing guarded submit operation. Report its actual evidence
source; a click or disappearing modal is insufficient. LinkedIn's “Your application
was sent to …” confirmation is supported on the assigned job. An observed already-
applied state is recorded through existing history and does not submit again.

For **external Apply**, follow the observed employer URL through the existing
correlated target handoff and corresponding ATS handler. Preserve discovery
provenance and original job/history identity. A popup alone or missing external
URL does not establish Easy Apply. Unknown classification stays for inspection.

Use the configured browser account. Handle actual sign-in/MFA/challenges using the
canonical authentication and recovery procedure. Do not import donor credentials,
defaults or guesses about work authorization/citizenship. A résumé mismatch is a
recovery handoff; select/upload the approved asset and inspect actual evidence.

Source and local changes: `third_party/godsscion-linkedin/UPSTREAM.md`.
