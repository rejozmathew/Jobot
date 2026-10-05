# Project documentation

This is the reading guide for the current **JobBot Application Operations** system.
The documentation was reviewed against the repository through October 4, 2026,
including the changes in `1b6776f`. Runtime settings and private deployment
configuration remain authoritative for a particular installation.

## Start here

| You want to… | Read |
|---|---|
| Understand the project in five minutes | [Root README](../README.md) |
| Set up a development environment or reconnect an existing installation | [Getting started](GETTING_STARTED.md) |
| Understand every dashboard page and everyday controls | [User guide](USER_GUIDE.md) |
| Understand components, processes and application execution | [Architecture](ARCHITECTURE.md) |
| Locate settings, configuration and their precedence | [Configuration](CONFIGURATION.md) |
| Understand jobs, attempts, accounts, answers and evidence | [Data model](DATA_MODEL.md) |
| Operate, diagnose, update or roll back the Ubuntu runtime | [Operations](OPERATIONS.md) |
| Understand Hermes, Simplify, discovery, mail and alerts | [Integrations](INTEGRATIONS.md) |
| Make and validate a change | [Contributing](../CONTRIBUTING.md) |
| Keep these documents current | [Documentation maintenance](DOCUMENTATION.md) |
| Understand how the project reached this point | [Project history](PROJECT_HISTORY.md) |
| Find detailed engineering records and older plans | [Engineering reference index](jobbot-v1/README.md) |
| Work on the original browser-use application | [Legacy application](LEGACY.md) |

Suggested first read: README → User guide → Architecture → Getting started.
Maintainers should then read Configuration, Data model and Operations.

## Which document governs what?

These guides describe implemented behavior. They do not create application
permissions, new finish conditions or retry restrictions.

- [AGENTS.md](../AGENTS.md) contains repository engineering and execution rules.
- [The canonical job-apply skill](../skills/productivity/job-apply/SKILL.md)
  contains the execution procedure for every harness. Workday also uses
  [workday-simplify](../skills/productivity/workday-simplify/SKILL.md).
- [Retry policy](jobbot-v1/RETRY_POLICY.md) defines request identity and retry
  behavior. Automatic queue scheduling and recovery within an active attempt
  are separate concepts.
- [Application runtime reference](jobbot-v1/APPLICATION_RUNTIME.md) contains
  implementation details and the canonical helper/caller map.
- [Self-improvement](jobbot-v1/SELF_IMPROVEMENT.md) describes evidence-driven
  engineering reviews and their numbered change records.

Historical plans, acceptance snapshots and run reports remain available for
traceability. Their dates, old restrictions, test counts and deployment status
describe their own checkpoints. They are not current setup instructions or a
claim that every employer portal works.

## Documentation scope

The public repository documents software, interfaces, operator behavior and
sanitized examples. Candidate facts, credentials, actual application records,
screenshots, mailbox contents, deployment manifests and machine-specific launchers
belong in the existing private configuration/artifact locations.

There is no separate generated documentation site or build step. Markdown and
Mermaid diagrams render in GitHub and compatible editors. Update the relevant
guides with the code change, following the [maintenance map](DOCUMENTATION.md).
