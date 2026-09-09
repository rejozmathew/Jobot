# Namespace, identity and protected verification

Before login, read the app's account strategy for the exact login namespace and selected identity. A namespace is the validated host/tenant key used by the app, not an arbitrary URL or a company-display-name match. Preserve identifiers as supplied; a malformed namespace is an error, not a cue to silently rewrite it.

Confirmed accounts take the sign-in path. Unknown/reconciliation states require bounded investigation; pending creation must be confirmed or reconciled before another create request. Register a confirmed creation immediately, independently of later application outcomes. Keep credential references in metadata; credential values stay in the protected provider/profile store.

Use Hermes Gmail to read the relevant verification email. The LLM selects the code closest to the actual request timestamp and rechecks if mail is delayed. JobBot does not apply a second sender, template, timestamp or ambiguity veto. Enter the selected code with browser fill or the code-field helper, keeping it out of summaries and reusable answer history.

Use the connected Gmail capability for ordinary account verification links/codes and genuinely needed recovery. This is normal autonomous execution. Only an unavoidable CAPTCHA/MFA or a demonstrated unavailable capability is a blocker. Preserve that owned target and record the outcome, then continue to the next queued job. Do not repeat password resets, assume account creation, or permanently cache verification codes.
