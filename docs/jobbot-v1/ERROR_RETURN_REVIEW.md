# Credential and submission error-return review

September 9, 2026. Reviewed the complete credential helper, submission flow and
the other matches visible in the supplied screenshots. This is not a claim to
have removed every questionable condition throughout the repository.

## Removed or relaxed

| Condition | Why unnecessary; implemented behavior |
| --- | --- |
| `verification_group_changed` and matching a challenge token/full ordered group | Classification is a convenience. Fill now uses the executor's selected input refs without requiring a recognized group. |
| `verification_length_mismatch`, including the word-character regex | A guessed length or alphabet cannot decide whether the chosen email code may be entered. The helper splits the supplied value across selected fields; the employer decides acceptance. |
| Code-group completion compares entered length with `maxlength` | `maxlength` is an upper bound, not a required code length. Completion now reports whether the observed fields contain text; empty fields still trigger ordinary continuation before Submit. |
| An inspection finding no recognized groups counted as a failed action | Local and older Hermes callers now record successful inspection whenever it returned a groups list, including an empty list. |
| Twelve verification refs maximum | An arbitrary helper limit. Removed. |
| `invalid_verification_parameters` / `invalid_credential_parameters` for extra keys | Unused metadata does not prevent the requested supported operation. Removed. |
| Resend must belong to the matching code group | The executor selects an observed resend control directly. It does not need a group match or code-field refs. |
| Successful resend becomes an error if the next scan has zero/multiple groups | Successful activation remains reported, with its timestamp. Group suggestions are optional. |
| Both email and password refs mandatory in `FILL_SELECTED` | Multi-step sign-in pages may show only one. Fill whichever credential fields the executor selected. |
| Password input must have `type=password` | Revealing a password changes the input to text. Both types are supported. |
| Legacy Workday `BLOCKED` / `FAILED` wrapper response as a bare action error | Preserve its observed context and ask the executor to inspect and continue recovery. It does not decide the application outcome. |
| Three external-SSO guesses saying `Call done(success=false) immediately` | A hostname change alone does not establish a corporate-login obstacle. Return the observed redirect and continue through available candidate options. |
| Account-exists response forbidding another account-helper call | Report the employer message and suggest the available sign-in/password recovery path. |

## Retained credential diagnostics

These report that a requested helper operation could not be performed or verified.
The public credential entry point includes continuation guidance on an error.

| Condition | Reason retained |
| --- | --- |
| `missing_email_ref` when no credential refs at all were supplied | There is no selected destination. Supplying just a password or confirmation ref is now sufficient. |
| `invalid_*_ref`, `ambiguous_or_stale_*_ref`, `verification_refs_changed` | Invalid syntax, no actual matching element, or multiple matches cannot identify a destination. This no longer compares verification refs to a heuristic group. |
| `unavailable_*_control`, `verification_control_unavailable` | The referenced control is detached, hidden, disabled, read-only, or unsupported by the input setter. Inspect/recover or use an appropriate browser operation. |
| `incorrect_*_control_type` | The account filler targets email/text and password/text inputs. Assigning a password to a checkbox's value property would not fill a sign-in field. |
| `duplicate_control_ref`, `duplicate_verification_control` | Two requested writes to the same element do not represent two distinct fields. Refresh the selected refs. |
| `values_not_committed`, `verification_values_not_committed` | The page did not retain the requested values. Reporting success would be false. This is field-write feedback, not code eligibility. |
| `observed_verification_refs_required` | Refs must be a list of strings for this call. The arbitrary count limit is gone. |
| `observed_resend_control_required` | Now only means no resend destination was supplied, not that its group failed approval. |
| `verification_resend_unconfirmed` | The click helper did not confirm activation. Its result and recovery instruction are returned. |
| `invalid_verification_action` | Unknown operation name; available operations remain inspect, fill and resend. |
| `*_controls_must_share_document` | A single grouped browser evaluation operates in one document. Separate browser fills remain available for controls in different frames. |
| `saved_credential_reference_unavailable`, `configured_credentials_unavailable`, `credential_configuration_invalid` | The selected saved account cannot be resolved or its credentials/configuration are missing. Silently substituting another password would not be a correct recovery. |
| `candidate_credential_identity_mismatch` | Retained candidate/account identity check. An alternate login identity would need a separate decision; this change does not authorize one. |
| `credential_target_scope_mismatch`, `verification_target_scope_mismatch` | Existing application-scope checks remain for credential destinations. This review did not broaden the shared URL matcher; it can still need a separate fix for a legitimate redirect. |
| `credential_transport_failed`, `verification_transport_failed` | Actual connection/evaluation exceptions. Their messages can contain secrets, so only the exception type is exposed. |
| Credential receipt recheck before Workday sign-in | Existing check/refill confirms that the selected credentials still occupy the intended controls. It reports actual page changes, not email-message eligibility. |

## Submission and the other screenshot matches

- `click_error=None`, assignment from a failed click result, and the exception
  assignment in `submission.py` only collect diagnostics. They do not authorize
  or refuse a click and were retained. Missing confirmation remains unknown,
  with recovery guidance; it does not turn into a successful application.
- The current unfinished-field/verification observation before Submit remains. It
  hands visible remaining work back to the executor in the same session, addressing
  the user's earlier premature-submit complaint. It does not freeze subsequent edits.
- The existing active-session, target-scope, writer-quiescence and user-selected
  evidence-source checks remain. Confirmation must still support an applied
  result; a helper observation alone is not permission to invent success.
- The remaining `element_handlers.py` action errors describe missing active
  pages, failed interactions/uploads, malformed results, absent configured
  inputs, employer feedback, or missing confirmation for a success claim.
  They do not justify treating a helper miss as the application's outcome.
- `runner.py` records returned outcomes, exceptions and actual cancellation.
  Its six `error=` matches do not add credential/submission permission gates.
- `hermes_plugin.py`'s `heartbeat_unavailable` records an exception in the older
  background heartbeat. That assignment alone neither closes nor refuses an application.
- `migrate.py` copies historical error text; `queue.py` initializes it empty.
- `workspace_process.py`'s `use_last_error=True` is a Windows API setting.
- `workday_observe.js` recognizes the employer's refresh error to offer recovery.
- The eight `platform_handlers/workday.py` matches identify employer validation
  feedback and choose repair controls/options; they are not permission checks.
- `static/jobbot.js`'s `error=false` selects a notice's display style.

No regression or live application was run. Only obsolete existing expectations
were aligned; no tests were added. Source review and syntax checks do not establish
live employer acceptance. Already-running hosts retain their imported code until
a fresh host is started.

Automatic approval review initially rejected committing/pushing the broader change
that also removed candidate/account matching and the pre-submit completeness check.
It cited wrong-account/incomplete-application risk. Those two checks are retained
in the narrowed change; code entry follows the user-authorized executor selection.
