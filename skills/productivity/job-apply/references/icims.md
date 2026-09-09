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

This reference is based on the observed ComPsych posting-to-email transition.
It does not claim that every iCIMS application has the same later steps.
