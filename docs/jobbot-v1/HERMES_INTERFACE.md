# Installed Hermes adapter contract — source inspection

Scope: Stage 2 discovery, not evidence that an adapter has been installed or invoked. Windows runtime inventory is in the private ignored handoff. No Hermes core/profile changes are authorized by this document.

Sources: [official plugin guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/), [official hooks guide](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks/), and the installed source at the inventoried Hermes installation. Installed version reported `v0.20.5 (2026.8.19)`; local source contains the following signatures. Future installations must recheck compatibility.

## Verified callable boundaries

- `hermes_cli.plugins.PluginContext.register_tool(name, toolset, schema, handler, check_fn=None, requires_env=None, is_async=False, description='', emoji='', override=False)`.
- `PluginContext.register_hook(hook_name, callback)`; callbacks accept named fields plus `**kwargs` for additive compatibility.
- Tool handlers accept `(args, **kwargs)` and return JSON strings. Installed `model_tools.handle_function_call` dispatches `task_id` and `session_id` to `tools.registry.registry.dispatch`, which forwards them to the handler. Do not invent handler `tool_call_id`: it is present on hooks, not this handler dispatch.
- `pre_tool_call`/`post_tool_call` receive `tool_name`, `args`, `task_id`, `session_id`, `tool_call_id`, `turn_id`, `api_request_id`. Post also carries `duration_ms`, `status`, `error_type`, `error_message`, `result` and middleware trace.
- Installed `handle_function_call` measures tool duration using a monotonic clock. Its post hook is an observer; a successful HTTP response from a job portal is not supplied or inferred by the hook.
- Pre-tool blocking directive is exactly `{'action': 'block', 'message': '<nonempty reason>'}`. Merely throwing an exception is unsafe because hook errors may be isolated. New adapter failures must explicitly return the block directive.
- Pre-tool invocation is single-fire: installed agent-loop path can pass `skip_pre_tool_call_hook=True` after checking itself. Do not wrap/patch Hermes core to fire hooks twice.
- `pre_api_request`, `post_api_request`, `api_request_error` are observer hooks. Model/provider IDs, request correlation, `api_duration` and token usage are suitable telemetry inputs. Raw `request`, `response`, message/history/error fields must not enter app persistence, even if upstream labels an envelope sanitized.

## Implementation requirements, not yet claimed working

1. Use one managed worker tool/client and standard registration/hooks. No internal agent rewrite, per-job model spawn, credential/provider switch, built-in tool override or fake plugin API version.
2. Bind the app run/attempt to the actual handler session. Freeze attempt/action correlation at pre-tool time; post-tool delivery must use that snapshot even after the session advances.
3. Persist only an allowlisted event envelope in an isolated outbox. Deliver idempotently; after telemetry/ownership failures, future mutating actions must be blocked until safely recovered. Do not persist tool arguments/results, reasoning, mail, headers or credentials.
4. Controls and claimed browser ownership are authoritative. Monitoring Simplify must not compete with its active writer; a timeout is a recorded recovery boundary, not evidence that an extension stopped.
5. Inspect actual plugin manifest/loading support before writing a manifest. Use a deliberately isolated plugin home for real dispatch tests. Current profile activation remains a separate release action.
6. Registering callbacks in a fixture is not H1/H2 acceptance. The final primary integration must invoke the actual installed dispatch and assert app telemetry for real safe local tools. Existing Simplify/CDP and mailbox tests remain separately gated.

This file records observed interfaces only. All planned adapter/skill/helper work remains governed by the approved PRD and current execution checkpoint.
