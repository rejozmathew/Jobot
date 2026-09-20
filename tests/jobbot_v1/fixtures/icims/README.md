# Synthetic browser fixtures

These files are original test material based on the *visible behavior* in the
screenshots. They are not copied from a real iCIMS page and do not establish actual
iCIMS selectors. Do not add production code keyed on these fixture IDs or the
`window.fixture` API. Production detection must use semantic DOM/native evidence.

The initial profile uses property-only autofill, nine filled employment sections,
13 optional blanks, two required blank passwords, an accepted-looking resume
widget and 15 Simplify review rows. The exact optional-field counts are synthetic,
not a reconstructed count from the real Cotiviti application.

The panel uses the actual demonstrated completion/button wording in an open shadow
root. It intentionally does NOT include the old Simplify observer's special
`Synthetic fixture; not official Simplify support` marker or `data-status`
override. Tests of parsing must exercise real rendered text, not a fixture-only
shortcut. The emitter can present active, unknown, complete and needs-review states.

## Pages and scenarios

Serve this directory using the existing test server or a temporary localhost-only
server. `icims-flow.html` starts on Candidate Profile. A normal successful local
profile submit advances to Screening Questions, then Review, then Received.
Nothing is transmitted to an employer.

Query `?scenario=` supports `profile`, `screening`, `review`, `optional-invalid`,
`checkboxes`, `two-forms`, `shadow`, `closed-shadow`, `hidden-required`,
`upload-error`, `active`, and `unknown`. The existing test server supplies same-origin and cross-origin
application frames for the shared CDP routing tests.

`window.fixture` is TEST CONTROL ONLY: reset profile/screening, set Simplify state,
add a conditional required field, replace a password node, add 100/500/1000 fields,
and inspect event/submit counters. Do not use it in production extraction.

The closed-shadow variant deliberately gives ordinary DOM inspection no access to
its internals. A reader cannot enumerate unknown closed-root fields from this
fixture's source; it must expose uncertainty about the opaque widget instead.

Native HTML validation prevents submitting missing native-required fields. The
server-style error banner deliberately persists after filling until profile
submission, to expose a stale-banner repair loop. Test code supplies only fake
credentials; no real credential values are needed or included.

## Jobbot integration coverage

`test_form_audit.py` and `test_icims_fast.py` inline these assets in the existing
isolated local browser server. Top-level integration uses its plain owned route;
frame coverage uses the server's established same-job frame identity mechanism.
The original handoff's standalone smoke script and result are not included here.
Only the tests invoking Jobbot's real reader/service/dispatch count as runtime
validation. No production code uses `window.fixture` or its control IDs.
