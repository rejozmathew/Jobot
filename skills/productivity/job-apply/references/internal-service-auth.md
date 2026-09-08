# Internal JobBot service authentication

This authenticates the local managed API. It is **not** the employer password, mailbox credential or model-provider key.

For an ordinary Hermes conversation without a native `jobbot` tool, use the repository CLI in the same conversation. The chosen private runtime config can resolve named worker/operator credentials from its existing environment or explicit `credential_files` references. No manual environment export, pasted secret or separate worker conversation is required for this transport.

1. Run `job_applier.workday_fast doctor --config <absolute-config>` through `terminal` in the repository.
2. Verify actual authentication with `terminal(command="<python> run_applier.py managed call --config <absolute-config> --token-env <name-from-worker_token_env> --operation health", workdir="<repository>")`.
3. Match the returned instance/database. `worker_token_available` alone is not proof that the running service accepted it.
4. Follow the managed run/claim/ownership protocol and existing application helpers. `--token-env` selects the configured name, never a token value. Operator calls and worker calls have different permissions; do not substitute one token for another.
5. If this check passes, do not report a missing shell environment variable as a blocker. If it fails, report the non-secret error; never print token files, guess another store, reset credentials or disable authentication.

Read [the connection decision and refactor record](../../../../docs/jobbot-v1/HERMES_CONNECTION.md) for exact configuration, ownership, limitations, verification and rollback. The native plugin/separate-worker launcher is a different route; do not launch it merely to obtain a credential for this chat.
