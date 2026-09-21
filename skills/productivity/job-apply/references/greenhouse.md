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
- When `email_route` is present, keep its `application_email` on the form after Simplify and before Submit or requesting a code, including reload/refill. Read codes from `verification_mailbox` through the existing jobs-mail connection. With forwarded delivery, personal mailbox access is not required; differing form and connected inbox addresses are intentional, never by themselves a blocker or a reason to request another integration. Match the original recipient, employer and request time in forwarded mail rather than requiring the outer To header to match. Inspect actual delivery; configuration alone does not prove the forwarding filter exists.

In approved submit mode, after material fields are correct and submission intent exists, use the enabled Submit control without a redundant full audit. Confirmation URL/text or an authoritative already-applied signal establishes outcome. A rejected form remains unsubmitted even if every visible input appears filled. Legacy successful forms are historical evidence, not universal current compatibility.

Start immediately after the canonical skill with `wait_seconds:0`, read this
reference while the browser prepares, then use the returned `next_operation`.
Use `jobbot` operation `greenhouse_advance` with `{"seconds":60}`. The session
host resolves ownership and the accepted current application document, including
an embed or an employer reached from LinkedIn. The helper waits for the native
form, observes existing Simplify activity, dispatches the first eligible fill and
one second automatic pass only for actual required residuals, then batches
ordinary approved answers. A call slice returns continuation, never an outcome.
Explicit supported Autofill recovery remains available after automatic passes.
Readiness and actual Autofill dispatch counts are separate observations.

Return all unresolved semantic answers together in one subsequent call:

```json
{"operation":"greenhouse_advance","parameters":{"seconds":60,"answers":[
  {"ref":"<current ref>","question_key":"<exact returned key>",
   "answer":{"value":"<offered value>","label":"<offered label>"},
   "basis":"<approved profile/saved-answer reference or approved-fact basis>"}
]}}
```

Text answers are strings and checkbox answers are booleans. Code opens, searches,
commits, reacquires and verifies each widget inside the batch. Full question labels
and current options are returned only for unresolved decisions; control failures
are separate from missing facts. Private verification stays in the existing
credentials/mail flow. Stale bindings require fresh observed refs. Do not turn
routine fields into a model/tool exchange per control. The same shared
`browser select` remains available for executor-led control recovery.

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
delayed mail and any offered resend, use the Greenhouse-only missing-email
refresh-and-refill recovery in the same owned tab/attempt. Call
`greenhouse_advance` with `{"seconds":60,"recovery":"missing_verification_email"}`;
it calls the existing owned reload and immediately resumes filling and submission.
If the slice ends, continue ordinary `greenhouse_advance` without the recovery
parameter. Do not finish using the old verification screenshot after replacement;
follow the returned current form through refill and the next Submit response.
The runner restores approved profile/saved
answers and previously verified plans with fresh refs, then submits through the
existing service. Do not replay arbitrary historical captured answers or old codes. A refreshed
Greenhouse form may submit directly or request verification again; inspect its
actual response. Neither slow filling, an upload rejection nor the presence of
an email-code prompt proves why Greenhouse requested verification.

Normal observations persist unambiguous posting/Simplify company and role
metadata into the existing job record, preserving explicit labels. Progress uses
question-level tasks under application stages; helper retries and diagnostic
details stay in collapsed Debug details. Use the canonical `progress` operation
for additional executor intent, never code values or candidate answers.
