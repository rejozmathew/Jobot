# Greenhouse and controlled-input knowledge

Keep question answers as selected profile facts with one canonical semantic concept, rather than accumulating nearly identical wording variants. Inspect `id`, `name`, label and kind before choosing an interaction. Required fields can be enforced by React without a plain HTML required attribute.

Preserved reliable approaches:
- Simplify first; deterministic/CDP logic repairs residuals, not the whole form.
- React-select text alone is not a committed selection. Open the correct widget, filter, inspect its actual options, commit the exact option and verify validation clears. Global listboxes may be portals; the phone dialer can create an unrelated listbox, so bind the right control first.
- Keyboard commit may need a real option click when aria-invalid persists.
- Prefer native widget interactions for Ashby-style Yes/No buttons. Changing a hidden checkbox does not reliably update framework state.
- A required conditional follow-up may need a truthful “not applicable” value, but only when the selected facts justify it.
- Preferred-name fields can be present or required. Greenhouse may clear or remove a file input after displaying an attachment; its empty value alone is not an upload failure. A filename chip alone is not proof of acceptance when the employer also shows "Resume/CV is required." Follow the canonical resume-error recovery immediately: inspect the screenshot, remove the Resume/CV attachment through its X/Remove control, reacquire that widget's input, and upload the approved asset there. The only remaining file input can be Cover Letter's. Preserve actual validation messages and follow the employer response after reattachment.
- Read security emails through the configured mailbox handoff (Himalaya or Hermes Gmail). The LLM chooses the relevant code closest to the request time, rechecking delayed mail within the shared recovery window below. Enter it with ordinary browser fill or pass `value` with the observed group to `credentials` mode `verification`; then submit and follow the employer response. No separate mailbox verifier decides whether entry is allowed.

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

Follow the shared continuation policy after Submit. Visible unfinished fields,
verification or validation feedback return `application_incomplete`; complete
them in this session, request/fill a fresh code when appropriate and submit the
current form. Historical click uncertainty never locks form edits or recovery
and requires no special rejection-proof operation. Actual accepted confirmation
establishes success. A new request may start a fresh attempt unless success is
recorded. These are common application rules, not a Greenhouse exception.

If the expected email code remains undelivered for about 1–2 minutes from the
employer's request, after checking the exact recipient, configured mailbox,
delayed mail and any offered resend, use the shared
refresh-and-refill recovery in the same owned tab/attempt. Let Simplify fill the
new form, correct actual residual questions, and submit promptly. A refreshed
Greenhouse form may submit directly or request verification again; inspect its
actual response. Neither slow filling, an upload rejection nor the presence of
an email-code prompt proves why Greenhouse requested verification.

Normal observations persist unambiguous posting/Simplify company and role
metadata into the existing job record, preserving explicit labels. Progress uses
question-level tasks under application stages; helper retries and diagnostic
details stay in collapsed Debug details. Use the canonical `progress` operation
for additional executor intent, never code values or candidate answers.
