# Contributing

Before publishing changes, run `python scripts/check_public_tree.py` in the
repository virtual environment. This checks tracked paths and obvious credential
material without scanning ignored personal artifacts. Keep filled profiles,
credentials, resumes, databases and screenshots private. Use
`profile.json.template` for new installations; `profile.example.json` remains its
compatibility copy. A clean working tree does not remove secrets from old Git
commits: audit history separately before changing repository visibility.

[Documentation index](docs/README.md) · [Architecture](docs/ARCHITECTURE.md) · [Repository instructions](AGENTS.md)

## Work in the existing checkout

Use the original repository and its virtual environment. Inspect `git status`
before editing and preserve other work. Do not create another checkout or worktree
without a concrete need and the authorization required by the repository rules.

Read the component guide before changing it. The managed runtime is under
`job_applier/managed*`, `application_runtime.py`, `queue_runtime.py` and the workspace
modules. The original browser-use application still has callers; a new fast path
does not prove the old path unused.

## Make a bounded change

For executable behavior changes, reproduce the defect with a focused synthetic
regression, implement the bounded fix, and run the affected checks plus the final
managed suite. Use isolated candidate facts, accounts, forms and databases. Never
use live applications as fixtures or change private production history to pass a test.

Keep shared behavior in shared components and ATS-specific mechanics in the
appropriate helper. Before adding another helper, read the ownership and caller
map in [Application runtime](docs/jobbot-v1/APPLICATION_RUNTIME.md). Update that map
when a helper or caller is added or removed.

Existing repository policy requires explicit user approval before adding any new
application-execution restriction, refusal condition, retry limit, approval
requirement or blocking rule. Explain the behavior it would prevent. Removing an
unnecessary veto does not require renewed approval. Documentation is not a way to
introduce an unapproved execution rule.

## Validate using the repository environment

Standard managed suite, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/jobbot_v1 -q
```

```bash
./.venv/bin/python -m pytest tests/jobbot_v1 -q
```

Per [AGENTS.md](AGENTS.md), delegate routine execution/validation to the existing
authenticated Antigravity CLI (`agy`) with `gemini-3.8-flash-medium`. The primary
engineering agent owns source edits and independently inspects the logs and JUnit.
The validator does not delegate again or edit source unless explicitly assigned.
Keep logs and temporary fixture directories in the ignored private artifacts area.

The standard suite intentionally skips opt-in browser and platform-specific cases
when their prerequisites are absent. Inspect the affected test files for their
exact environment switches before enabling those cases. Node-based UI checks and
isolated Chromium/CDP fixtures are separate from employer validation. A skipped
test is not a passed browser check. Record environment-specific failures and
focused rechecks rather than hiding them by changing runtime behavior.

For Ubuntu fixtures, register completion/identity manifests and retain logs outside
the disposable directories as described in [Validation storage](docs/jobbot-v1/VALIDATION_STORAGE.md).

For documentation-only changes, check relative links, heading anchors, commands,
navigation coverage and factual agreement with source. Use relevant existing
documentation/interface checks; do not create a behavioral regression test solely
to assert prose wording. Do not exercise live employer applications to validate docs.

## Documentation travels with the change

Update the affected guide in the same change. Start with the
[documentation maintenance map](docs/DOCUMENTATION.md). Explain what the operator
sees, which component owns it, and any configuration, data or rollout consequence.

Keep current guides concise enough to read without the development conversation.
Keep dated evidence in the engineering records. Distinguish implemented behavior,
historical checkpoints and proposed work. Never publish private screenshots,
credentials, application answers or deployment configuration in public docs.

## Complete the change

Review the final diff, preserve unrelated edits, and create the local Git checkpoint
after validation. Follow [Operations](docs/OPERATIONS.md) to deploy the validated
files to the existing authoritative Ubuntu runtime, verify the affected services
and preserve active applications. Pushing requires the applicable authorization;
local commit/deployment authorization alone does not imply a remote push.

For a self-improvement review, additionally follow
[SELF_IMPROVEMENT.md](docs/jobbot-v1/SELF_IMPROVEMENT.md): persistent numbered/date
labels, annotated tag, matched run notes, private evidence and bounded
baseline/candidate comparisons. Routine documentation maintenance is not itself a
new numbered application-performance experiment.
