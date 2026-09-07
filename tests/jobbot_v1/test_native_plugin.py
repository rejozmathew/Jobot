"""Unit registration tests for native Hermes JobBot plugin.

Verifies:
1. Manifest plugin.yaml contains actual fields (name, version, provides_tools, provides_hooks)
   without invented entrypoint fields.
2. Registration with minimal fake context implementing ONLY actual installed APIs:
   get_config, register_tool, register_hook, on_unload. Registration returns handle objects.
3. When config is absent: no run created or API contacted; 'jobbot' is registered with
   check_fn false/unavailable, callbacks registered, cleanup registered, override=False.
4. Tool handler accepts args and session_id in kwargs, returning JSON structured unavailable error
   when config is absent.
5. Unsupported context missing required public methods fails before partial registration.
6. Worker configuration is retrieved via get_config('app_config') explicit path.
"""
import importlib.util
import json
from pathlib import Path
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "integrations" / "hermes_jobbot"
INIT_PATH = PLUGIN_DIR / "__init__.py"
MANIFEST_PATH = PLUGIN_DIR / "plugin.yaml"

REQUIRED_HOOKS = [
    "pre_tool_call",
    "post_tool_call",
    "pre_api_request",
    "post_api_request",
    "api_request_error",
]


def get_plugin_register():
    assert INIT_PATH.is_file(), f"Plugin entrypoint not found: {INIT_PATH}"
    spec = importlib.util.spec_from_file_location("integrations.hermes_jobbot", INIT_PATH)
    assert spec is not None and spec.loader is not None, f"Failed to load spec for {INIT_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "register"), f"Module {INIT_PATH} does not define register(ctx)"
    return mod.register


class Handle:
    def __init__(self, kind: str, name: str):
        self.kind = kind
        self.name = name

    def __repr__(self):
        return f"<Handle kind={self.kind} name={self.name}>"


class FakePluginContext:
    """Minimal fake context implementing ONLY actual installed PluginContext APIs."""

    def __init__(self, settings=None):
        self._settings = settings or {}
        self.tools = {}
        self.hooks = {}
        self.unloads = []

    def get_config(self, key, default=None):
        return self._settings.get(key, default)

    def register_tool(
        self,
        name,
        toolset,
        schema,
        handler,
        check_fn=None,
        requires_env=None,
        is_async=False,
        description="",
        emoji="",
        override=False,
    ):
        handle = Handle("tool", name)
        self.tools[name] = {
            "handle": handle,
            "toolset": toolset,
            "schema": schema,
            "handler": handler,
            "check_fn": check_fn,
            "requires_env": requires_env,
            "is_async": is_async,
            "description": description,
            "emoji": emoji,
            "override": override,
        }
        return handle

    def register_hook(self, name, callback):
        handle = Handle("hook", name)
        self.hooks.setdefault(name, []).append((handle, callback))
        return handle

    def on_unload(self, callback):
        handle = Handle("unload", f"unload_{len(self.unloads)}")
        self.unloads.append((handle, callback))
        return handle


def test_plugin_manifest_structure():
    assert MANIFEST_PATH.is_file(), f"Plugin manifest not found: {MANIFEST_PATH}"
    content = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(content, dict), "Manifest must be a valid YAML mapping"

    for field in ("name", "version", "provides_tools", "provides_hooks"):
        assert field in content, f"Manifest missing actual field: '{field}'"
    assert "entrypoint" not in content, "Manifest must not invent entrypoint field"

    assert "jobbot" in content["provides_tools"], "Manifest provides_tools must include 'jobbot'"
    assert set(REQUIRED_HOOKS).issubset(set(content["provides_hooks"])), (
        f"Manifest missing required hooks: {set(REQUIRED_HOOKS) - set(content['provides_hooks'])}"
    )


def test_registration_when_config_absent():
    register = get_plugin_register()
    ctx = FakePluginContext(settings={})

    register(ctx)

    assert "jobbot" in ctx.tools, "Tool 'jobbot' was not registered"
    tool_entry = ctx.tools["jobbot"]
    assert isinstance(tool_entry["handle"], Handle), "register_tool must return a handle"
    assert tool_entry["override"] is False, "Tool registration must have override=False"

    assert callable(tool_entry["check_fn"]), "check_fn must be callable"
    assert tool_entry["check_fn"]() is False, "check_fn must evaluate to False when config absent"

    for hook_name in REQUIRED_HOOKS:
        assert hook_name in ctx.hooks, f"Required hook '{hook_name}' was not registered"
        hook_entries = ctx.hooks[hook_name]
        assert len(hook_entries) >= 1, f"No callback registered for hook '{hook_name}'"
        handle, cb = hook_entries[0]
        assert isinstance(handle, Handle), f"register_hook('{hook_name}') must return a handle"
        assert callable(cb), f"Callback for hook '{hook_name}' must be callable"

    assert len(ctx.unloads) >= 1, "Cleanup callback must be registered via on_unload"
    unload_handle, unload_cb = ctx.unloads[0]
    assert isinstance(unload_handle, Handle), "on_unload must return a handle"
    assert callable(unload_cb), "on_unload callback must be callable"

    handler = tool_entry["handler"]
    res = handler(args={"action": "query_state"}, session_id="session-test-1")
    if isinstance(res, str):
        res = json.loads(res)
    assert isinstance(res, dict), "Handler must return a dictionary or JSON object"
    assert (
        res.get("status") in ("unavailable", "error")
        or "error" in res
        or res.get("available") is False
    ), f"Expected structured unavailable error, got: {res}"


def test_unsupported_context_fails_before_partial_registration():
    register = get_plugin_register()

    class MissingOnUnloadContext:
        def __init__(self):
            self.tools = {}
            self.hooks = {}

        def get_config(self, key, default=None):
            return None

        def register_tool(self, name, *args, **kwargs):
            handle = Handle("tool", name)
            self.tools[name] = handle
            return handle

        def register_hook(self, name, callback):
            handle = Handle("hook", name)
            self.hooks.setdefault(name, []).append((handle, callback))
            return handle

    broken_ctx = MissingOnUnloadContext()
    with pytest.raises((AttributeError, TypeError, ValueError)):
        register(broken_ctx)

    assert len(broken_ctx.tools) == 0, (
        f"Partial registration occurred: {len(broken_ctx.tools)} tools registered before failure"
    )
    assert len(broken_ctx.hooks) == 0, (
        f"Partial registration occurred: {len(broken_ctx.hooks)} hooks registered before failure"
    )


def test_worker_configuration_reads_explicit_app_config():
    register = get_plugin_register()
    accessed_keys = []

    class ConfigTrackingContext(FakePluginContext):
        def get_config(self, key, default=None):
            accessed_keys.append(key)
            return super().get_config(key, default)

    ctx = ConfigTrackingContext(settings={"app_config": "C:/fake/path/app_config.json", "app_repo": str(REPO_ROOT)})
    register(ctx)

    assert "app_config" in accessed_keys, (
        f"Expected get_config('app_config') to be queried, got queries for: {accessed_keys}"
    )
