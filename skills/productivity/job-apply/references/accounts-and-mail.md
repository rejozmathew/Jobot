# Namespace, identity and protected verification

Before login, read the app's account strategy for the exact login namespace and selected identity. A namespace is the validated host/tenant key used by the app, not an arbitrary URL or a company-display-name match. Preserve identifiers as supplied; a malformed namespace is an error, not a cue to silently rewrite it.

Confirmed accounts take the sign-in path. Unknown/reconciliation states require bounded investigation; pending creation must be confirmed or reconciled before another create request. Register a confirmed creation immediately, independently of later application outcomes. Keep credential references in metadata; credential values stay in the protected provider/profile store.

Before any verification flow, verify the active connector's mailbox identity. Correlate recipient identity, namespace, purpose, sender and request-time window. Ambiguous, unrelated or older messages are rejected. Do not use only company name plus newest-message ordering. Never expose codes, reset links or private message bodies in tool summaries, ordinary events, logs or handoffs.

An auth/reset/verification challenge beyond one verified attempt or the configured short budget becomes an explicit checkpoint. Leave only the owned intervention target open. No repeated password resets or assumed account creation; no permanent caching of code values.
