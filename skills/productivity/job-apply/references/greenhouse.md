# Greenhouse and controlled-input knowledge

Keep question answers as selected profile facts with one canonical semantic concept, rather than accumulating nearly identical wording variants. Inspect `id`, `name`, label and kind before choosing an interaction. Required fields can be enforced by React without a plain HTML required attribute.

Preserved reliable approaches:
- Simplify first; deterministic/CDP logic repairs residuals, not the whole form.
- React-select text alone is not a committed selection. Open the correct widget, filter, inspect its actual options, commit the exact option and verify validation clears. Global listboxes may be portals; the phone dialer can create an unrelated listbox, so bind the right control first.
- Keyboard commit may need a real option click when aria-invalid persists.
- Prefer native widget interactions for Ashby-style Yes/No buttons. Changing a hidden checkbox does not reliably update framework state.
- A required conditional follow-up may need a truthful “not applicable” value, but only when the selected facts justify it.
- Preferred-name fields can be present or required. File input values may remain empty for browser privacy; verify the attachment chip and selected document identity instead.
- Emailed security codes use `credentials` mode `verification`: inspect the observed group, request a fresh code through its observed resend control after interruption, then fill the complete group privately and submit promptly. Pass refs and challenge identity only; never issue one ordinary fill call per character or expose a code to the human-answer queue.

In approved submit mode, after material fields are correct and submission intent exists, use the enabled Submit control without a redundant full audit. Confirmation URL/text or an authoritative already-applied signal establishes outcome. A rejected form remains unsubmitted even if every visible input appears filled. Legacy successful forms are historical evidence, not universal current compatibility.

Start immediately after the canonical skill with `wait_seconds:0`, read this
reference while the browser prepares, then use the returned `next_operation`.
Enabled Autofill uses shared `browser simplify`, not Workday `fast_forward`.
Readiness and first Autofill dispatch are separate timing observations.

For a React-style combobox, `browser select` checks the selected label beside
the search input and reacquires the control after a rerender. An open widget
can already be answered. A filter value or highlighted menu option is not an
answer. Use the exact approved option, including veteran/disability fields;
when recovering with `press`, supply the intended label and require `committed`.
On mismatch inspect the actual selection/options and continue recovery.

A fresh employer “Invalid security code”, “Expired security code” or required
field rejection captured after Submit can return `submission_rejected` and
`submission_pending:false`. Correct it in the owned session, request/fill a fresh
code if appropriate and submit with a new intent. Old errors, missing responses
and a generic failed reconciliation do not authorize another submission.

Normal observations persist unambiguous posting/Simplify company and role
metadata into the existing job record, preserving explicit labels. Progress uses
question-level tasks under application stages; helper retries and diagnostic
details stay in collapsed Debug details. Use the canonical `progress` operation
for additional executor intent, never code values or candidate answers.
