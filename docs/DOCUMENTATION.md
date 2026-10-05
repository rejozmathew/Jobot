# Keeping documentation current

[Documentation index](README.md) · [Contributing](../CONTRIBUTING.md)

Documentation is part of the implementation change. Update it when behavior,
screens, configuration, storage, integration contracts or operational steps change.
This is a contributor workflow, not an additional gate on application execution.

## Document ownership

| Document | Owns | Avoid putting here |
|---|---|---|
| [README](../README.md) | Project purpose, capabilities, current startup and navigation | Detailed migration history or private installation values |
| [User guide](USER_GUIDE.md) | Page purpose, exact visible controls, expected effects and common tasks | Internal implementation details that do not help an operator |
| [Architecture](ARCHITECTURE.md) | Component boundaries, runtime/data flow, rationale and limitations | Every chronological fix or full API payload |
| [Getting started](GETTING_STARTED.md) | Existing installation entry points and isolated development setup | An invented production bootstrap |
| [Configuration](CONFIGURATION.md) | Field purpose, precedence, defaults and update scope | Secrets or copies of live runtime JSON |
| [Data model](DATA_MODEL.md) | Entities, relationships, authoritative storage and evidence semantics | Exhaustive SQL duplicated from migrations |
| [Integrations](INTEGRATIONS.md) | Public entry points and external component responsibilities | Reimplementation of canonical application instructions |
| [Operations](OPERATIONS.md) | Process map, diagnostics, backup, deployment and rollback | Machine-specific credentials or evidence dumps |
| [Project history](PROJECT_HISTORY.md) | Major capability milestones and links to supporting records | Routine test logs or per-application outcomes |
| [Engineering reference](jobbot-v1/README.md) | Findable current references, historical reports and proposals | Undated claims that every historical plan is current |
| [Runtime reference](jobbot-v1/APPLICATION_RUNTIME.md) | Detailed execution design and canonical helper/caller map | Personal answers or production transcripts |

## Change-to-document map

| Change | Update |
|---|---|
| Add/rename/remove a dashboard page or action | User guide page map and section; relevant README capability |
| Queue ordering, retries, pause or concurrency | User guide, Architecture, Configuration where relevant, Retry policy / Queue runbook |
| Deadline or lifecycle semantics | Architecture, User guide, Configuration, Operations and canonical runtime/skill references |
| New runtime field or environment selection | Configuration, sanitized example and Getting started command if affected |
| New table or changed record ownership | Data model, Architecture if the boundary changes, migration/runbook notes |
| New helper or caller | Canonical helper map, Architecture/Integrations summary, relevant skill reference |
| Changed submission or evidence semantics | Data model, User guide Activity section, Retry policy and affected evidence references |
| New integration or service | Integrations, Operations, Configuration and source/deployment examples |
| New setup requirement or validation command | Getting started and Contributing |
| Deployment/rollback/storage change | Operations and the corresponding detailed runbook |
| Significant new capability | README summary and Project history with dated source/evidence |
| Internal refactor with unchanged behavior | Update affected architecture/source references, or explain why no guide changes are needed |

Use the existing canonical document rather than maintaining another independent
copy of retry policy, helper authority or application instructions. A short summary
and a link are better than two conflicting checklists.

## Review checklist

1. Check the actual implementation, visible labels and test behavior. A plan or old
   conversation does not establish what is implemented.
2. Describe current behavior and the user's task first. Include the setting's
   default, where it is changed, and when changes take effect if relevant.
3. Verify every local path/link and any heading anchor. Use relative links inside
   repository Markdown so GitHub and local readers can navigate it.
4. Check commands against current CLI parsers. Label placeholders and OS-specific
   syntax. Do not run a command that starts an employer application merely to test
   that its example is valid.
5. Distinguish current runtime, optional integration, compatibility path, historical
   checkpoint and unimplemented proposal. Label dated evidence explicitly.
6. Check privacy: use synthetic examples and neutral paths. Keep actual profiles,
   credentials, database exports, transcripts and deployment manifests private.
7. State validation limits. Record skipped checks and avoid turning synthetic
   success into a production performance claim.

The [pull request template](../.github/pull_request_template.md) prompts for the
documentation impact, validation and rollout. Local-only changes follow the same
review even when no PR is opened.

## Adding a document

Use the existing guide unless a new topic needs a separate substantial reference.
For a new guide, include its purpose, intended reader, links back to the index,
current behavior, relevant source files, operating steps/examples and limits.
Add it to the documentation index and the maintenance map where appropriate.

Use Mermaid for small architecture/relationship diagrams. Keep prose as well so
the document still works in viewers without Mermaid. Screenshots are optional and
must use synthetic/redacted content; do not include private application captures.

When a design becomes implemented, update the current guide and link the old design
as rationale. When a guide becomes obsolete, add a prominent historical notice and
link its replacement. Preserve dated records rather than silently rewriting their
reported outcomes or test counts.

## Version and evidence conventions

The initial structured guide set is reviewed through October 4, 2026 at `1b6776f`.
Update review dates only for documents actually checked. Git history identifies
the exact changes; do not maintain a manual release number on every page.

Use [Project history](PROJECT_HISTORY.md) for meaningful capability milestones.
Use the existing self-improvement log for numbered reviews and detailed validation.
Private deployment manifests retain source commit, hashes, backups, timestamps and
test evidence. None of these records is a substitute for a current operator guide.

No scheduled documentation automation is required for this workflow. Keeping docs
with the implementation change avoids waiting for a later periodic rewrite.
