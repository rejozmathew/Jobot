# Workday knowledge preserved

Earlier execution recorded a real confirmation and the authoritative “You've already applied for this job” signal. Candidate Home can label a submitted application “In Progress”; that label alone is not submission truth. These historical observations do not validate this new adapter on live Workday.

Prefer the actual `/apply` anchor target when the posting's JS-intercepted Apply button does not navigate. Default to Autofill with Resume, then Simplify on each page. Preserve parsed work history; inspect degree/field-of-study mappings and residuals rather than starting again.

Account reuse is keyed by verified login namespace plus selected identity. Sign in to a confirmed account; do not repeat creation. An auth attempt that does not advance within the bounded budget becomes a user handoff on the exact tab. A failed form later must not erase a known account.

Preserved implementation pitfalls:
- Clear controlled inputs before typing; appending can duplicate identity or credential text.
- State/region choice follows the profile's exact priority, not the first vaguely matching option.
- The phone country-code combobox is distinct from generic search fields.
- Legacy profile address mapping was under `identity.address`; inspect the selected schema rather than guessing.
- Uncommitted React radio/date state can keep advancement disabled. Commit the truthful selected fact with real interactions and input/change/blur as necessary. Do not change disability/demographic answers merely to enable a button.
- Maintenance pages can interrupt a surviving draft. Use bounded observation and resume, not a new account or speculative submission.
- Earlier deterministic self-ID code had syntax/fixture evidence but incomplete live coverage. Keep that distinction.

Use existing `platform_handlers/workday.py` and `bu_compat.py` selectively after owner binding. Workday LLM fallback remains disabled in the approved deterministic path. A legacy dry run could still create an account, so it is not an offline-development safety boundary. Submission truth is the confirmation/already-applied signal; do not navigate back merely to repeat a successful confirmation check.
