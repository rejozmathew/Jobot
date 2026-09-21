# iCIMS application pages

Read this reference while the owned browser prepares. The shared job-apply skill
controls the full application; this reference records observed iCIMS behavior.

- The hostname identifies iCIMS early. Employer branding does not make the
  outer page the complete application document. On the observed ComPsych flow,
  Apply and later Email/Next were inside the embedded iCIMS document.
- On the posting, open the observed Apply control before filling application
  details. A Simplify panel saying Autofill complete on the outer shell does not
  mean the application has opened. Do not mistake footer/contact widgets for
  applicant fields.
- Use `browser snapshot` and the returned frame-qualified refs. The shared
  router exposes the embedded controls; there is no separate application worker
  or browser profile. After Apply/navigation, get fresh refs for the new document.
- If Apply, Email, Next or an expected form is missing from the inventory, take
  and inspect an owned screenshot immediately. A returned `image_path` should
  be read with the harness image tool, such as Hermes `vision_analyze`. Inspect
  frame/scroll boundaries and overlays, then continue with the visible controls.
- The same `/jobs/<numeric-id>/` identifies the requisition across its posting,
  login and application steps. Title slugs, page-mode and embedded-view query
  parameters do not create another job. Different portals/jobs remain distinct.
- The observed first step after Apply asks for Email and Next. Fill the approved
  email using the observed ref (ordinary browser fill or the retained private
  credential helper with `email_ref` only), click Next, and inspect the actual
  response. It may lead to sign-in, account creation or further application work;
  do not assume which response will occur.
- Missing Simplify on an email/sign-in page does not prevent native interaction
  once the writer is settled. Complete the visible step and return to Simplify
  for bulk application fields. Helper next-operation suggestions do not replace
  reasoning over the current page.
- A CAPTCHA protection notice, footer or logo does not establish that a challenge
  is active. Follow Email/Next normally and inspect the site's response. Only an
  actual challenge needing the user calls for the configured human-input path.
- Continue through all actual pages and validation feedback to submission and
  accepted confirmation. Do not generalize Greenhouse's final email-code flow
  to iCIMS. If an email verification appears, use the common Hermes mail/code
  instructions and continue. No helper miss alone establishes failure.

## Owned iCIMS runner and compact recovery

Call `icims_advance` with `{"seconds":60}`. The runner follows observed stage cues,
not a fixed page count: posting/Apply, Email/Next, credentials, Candidate Profile,
questions, review and confirmation. It uses the existing frame router, shared
`browser` audit/repair, private credentials and final submission service.

After autofill, missing passwords/confirmation go through the retained private
credential helper. Empty optional Preferred Name, consent, reasons for leaving
and similar fields remain empty. An accepted resume widget is not reuploaded
merely because FileList is empty or Simplify lists Resume for review. Actual
upload/validation errors still require repair. Unknown screening answers return
as one grouped question handoff; answer with current `ref`, `question_key`,
`answer` and approved `basis`, then resume `icims_advance`.

On a page establishing Candidate Profile, observed Submit Profile (button or
input-submit) is an intermediate action. Read the resulting screening/validation
page; never record applied for profile acceptance. A repaired password can be
resubmitted even when its old server banner remains until the next request.
Final application submission uses the common submission mode/evidence policy.

For an older in-memory native schema use the current session and actual driver:

```sh
.venv/bin/python -m job_applier.application_runtime call SESSION_ID icims_advance --parameters '{"seconds":60}'
.venv/bin/python -m job_applier.application_runtime call SESSION_ID browser --parameters '{"method":"audit"}'
```

An unknown writer returns an audit plus concrete owned inspection/Stop guidance;
actual pending writers must settle before repair. Do not reload a populated form
merely for optional blanks, review counts or unfamiliar panel text. Open shadow
roots and accepted frames are supported; inaccessible/custom controls remain
explicit coverage handoffs. A helper slice or unsupported control never decides
that the application has failed.

ComPsych's entry transition and the supplied Cotiviti screenshots motivated this
flow. Synthetic fixture validation is not a verified live employer submission.
