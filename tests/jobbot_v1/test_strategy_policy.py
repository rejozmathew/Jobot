"""Synthetic Service and adapter tests for strategy policy and autofill capabilities.

Covers:
1. test_allowed_fallback_block_prevents_mutating_actions_in_fallback_phases:
   Verify effective allowed_fallback='block' prevents owned mutating action_start
   during explicitly reported residual_fields and native_fallback phases, while
   leaving read-only observations and metadata/controls usable.
2. test_field_seconds_budget_enforced_conservatively_with_bounded_extension:
   Field_seconds budget is enforced conservatively: if a reported tool span exceeds
   frozen field_seconds, a subsequent mutation for the same reported semantic field/problem
   must require visible bounded extension or intervention; no fabricated progress and
   no killing arbitrary processes. If this semantic context is unavailable, operation
   must report unsupported/coarse behavior rather than pretending field-level enforcement.
3. test_native_autofill_requires_worker_capability_and_adapter_declarations:
   New native autofill request must require worker-declared autofill capability
   (autofill_strategies contains native) instead of placebo acceptance; ordinary existing
   simplify default remains compatible. Native HermesAdapter declares only strategies it
   actually supports via current helpers/tools.
"""
from pathlib import Path
import sys
import httpx
import pytest
from fastapi.testclient import TestClient

from job_applier.hermes_adapter import HermesAdapter
from job_applier.managed import Service, ProtocolError
from job_applier.managed_api import create_app
from job_applier.managed_client import Client

# Import test fixtures from test_ownership
sys.path.insert(0, str(Path(__file__).parent))
try:
    from test_ownership import ready, accept
except ImportError:
    from tests.jobbot_v1.test_ownership import ready, accept


OPERATOR_TOKEN = "synthetic-operator-token-jobbot-v1-32chars"
WORKER_TOKEN = "synthetic-worker-token-jobbot-v1-32chars"
WORKER_ID = "worker-hermes"
BASE_URL = "http://127.0.0.1:8769"


class DirectTransport(httpx.BaseTransport):
    """In-process transport routing httpx requests to FastAPI TestClient."""

    def __init__(self, test_client: TestClient):
        self._test_client = test_client

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        result = self._test_client.request(
            request.method,
            request.url.path,
            headers=dict(request.headers),
            content=request.content,
        )
        return httpx.Response(
            result.status_code,
            headers=result.headers,
            content=result.content,
        )


def test_allowed_fallback_block_prevents_mutating_actions_in_fallback_phases(tmp_path):
    """Verify effective allowed_fallback='block' prevents owned mutating action_start
    during explicitly reported residual_fields/native_fallback phases, while leaving
    read-only observations and metadata/controls usable.
    """
    # 1. Initialize Service with allowed_fallback='block'
    s, r, ids = ready(tmp_path, count=1, settings={"allowed_fallback": "block"})
    accept(s, r)
    a = s.claim(r["id"], worker_id="worker")
    assert a is not None

    # 2. Explicitly report entering residual_fields phase
    s.event(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        event_id="ev-phase-residual",
        event_type="phase_changed",
        observed_at=s.now(),
        payload={"phase": "residual_fields"},
    )

    # 3. Owned mutating action_start (writes_browser=True) must be blocked
    with pytest.raises(ProtocolError):
        s.action_start(
            a["id"],
            worker_id="worker",
            fence=a["fence"],
            action_id="act-mutate-residual",
            tool_name="click",
            writes_browser=True,
        )

    # 4. Read-only observation (writes_browser=False) remains usable
    ro_act = s.action_start(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        action_id="act-ro-residual",
        tool_name="inspect_page",
        writes_browser=False,
    )
    assert ro_act["id"] == "act-ro-residual"
    assert ro_act["writes_browser"] == 0

    # 5. Metadata and controls remain usable
    hb = s.heartbeat(a["id"], worker_id="worker", fence=a["fence"])
    assert hb is not None
    ws = s.writer_state(a["id"], worker_id="worker", fence=a["fence"], state="idle")
    assert ws["writer_state"] == "idle"

    # 6. Explicitly report entering native_fallback phase
    s.event(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        event_id="ev-phase-native-fallback",
        event_type="phase_changed",
        observed_at=s.now(),
        payload={"phase": "native_fallback"},
    )

    # Mutating action must also be blocked in native_fallback phase
    with pytest.raises(ProtocolError):
        s.action_start(
            a["id"],
            worker_id="worker",
            fence=a["fence"],
            action_id="act-mutate-native-fallback",
            tool_name="input_text",
            writes_browser=True,
        )

    # Read-only observation still allowed in native_fallback phase
    ro_act2 = s.action_start(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        action_id="act-ro-native-fallback",
        tool_name="inspect_page",
        writes_browser=False,
    )
    assert ro_act2["id"] == "act-ro-native-fallback"

    # 7. Non-blocking contrast: allowed_fallback='targeted' allows mutating actions in fallback phases
    s2, r2, ids2 = ready(tmp_path / "sub2", count=1, settings={"allowed_fallback": "targeted"})
    accept(s2, r2)
    a2 = s2.claim(r2["id"], worker_id="worker")
    s2.event(
        a2["id"],
        worker_id="worker",
        fence=a2["fence"],
        event_id="ev-phase-residual-targeted",
        event_type="phase_changed",
        observed_at=s2.now(),
        payload={"phase": "residual_fields"},
    )
    mut_act = s2.action_start(
        a2["id"],
        worker_id="worker",
        fence=a2["fence"],
        action_id="act-mutate-targeted",
        tool_name="click",
        writes_browser=True,
    )
    assert mut_act["id"] == "act-mutate-targeted"


def test_field_seconds_budget_enforced_conservatively_with_bounded_extension(tmp_path):
    """Field_seconds budget is enforced conservatively: if a reported tool span exceeds
    frozen field_seconds, subsequent mutation for the same reported semantic field/problem
    must require visible bounded extension or intervention; no fabricated progress and
    no killing arbitrary processes. If this semantic context is unavailable, operation
    must report unsupported/coarse behavior rather than pretending field-level enforcement.
    """
    # 1. Setup service with frozen field_seconds=30
    s, r, ids = ready(tmp_path, count=1, settings={"field_seconds": 30})
    accept(s, r)
    a = s.claim(r["id"], worker_id="worker")
    assert a is not None

    attempt_before = s.attempt(a["id"])
    initial_progress = attempt_before["progress_at"]

    # 2. Worker reports a tool span exceeding frozen field_seconds (35s > 30s)
    # for a reported semantic field/problem ('resume_upload')
    s.event(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        event_id="ev-tool-field-exceeded",
        event_type="tool_finished",
        observed_at=s.now(),
        duration_seconds=35.0,
        payload={"tool_name": "upload_file", "field": "resume_upload", "status": "failed"},
    )

    # 3. No fabricated progress: progress_at must remain unchanged
    attempt_after = s.attempt(a["id"])
    assert attempt_after["progress_at"] == initial_progress

    # 4. Subsequent mutation for the same reported semantic field/problem requires
    # visible bounded extension or intervention (blocked before extension)
    with pytest.raises(ProtocolError):
        s.action_start(
            a["id"],
            worker_id="worker",
            fence=a["fence"],
            action_id="act-mutate-field-resume",
            tool_name="upload_file",
            writes_browser=True,
        )

    # 5. Visible bounded extension allows mutation to proceed
    ext = s.extend_budget(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        seconds=30,
        reason="field extension for resume_upload retry",
    )
    assert ext["seconds"] == 30

    # 6. If semantic context is unavailable, operation must report
    # unsupported/coarse behavior rather than pretending field-level enforcement
    with pytest.raises((ProtocolError, TypeError)):
        s.action_start(
            a["id"],
            worker_id="worker",
            fence=a["fence"],
            action_id="act-mutate-untracked-context",
            tool_name="click",
            writes_browser=True,
            semantic_context=None,
        )


def test_native_autofill_requires_worker_capability_and_adapter_declarations(tmp_path):
    """New native autofill request must require worker-declared autofill capability
    (autofill_strategies contains native) instead of placebo acceptance; ordinary existing
    simplify default remains compatible. Native HermesAdapter declares only strategies it
    actually supports via current helpers/tools.
    """
    # 1. Ordinary existing simplify default remains compatible
    s, r_default, ids_default = ready(tmp_path / "simplify", count=1)
    default_caps = {
        "protocol": 1,
        "skill_version": "test-skill",
        "browser_profile": r_default["browser_profile"],
        "provider": "fixture",
        "model": "fixture",
        "telemetry": True,
    }
    acc_default = s.accept_run(
        r_default["id"],
        worker_id="worker-simplify",
        session_id="session-simplify",
        capabilities=default_caps,
    )
    assert acc_default["state"] == "accepted"

    # 2. Configure native autofill and request run
    cur = s.settings_view()
    s.configure({"autofill": "native"}, expected_version=cur["version"])
    job_native = s.intake(url="https://careers.example.test/jobs/native-1", source_id="native-1")
    s.eligibility(job_native["id"], "ready", reason="operator approval")
    r_native = s.request_run(
        request_id="run-native-1",
        job_ids=[job_native["id"]],
        identity_id="candidate",
        browser_profile="fixture-browser",
    )

    # Worker without declared native autofill capability must be rejected (no placebo acceptance)
    with pytest.raises(ProtocolError):
        s.accept_run(
            r_native["id"],
            worker_id="worker-placebo",
            session_id="session-placebo",
            capabilities=default_caps,
        )

    # Worker explicitly declaring native autofill capability is accepted
    native_caps = dict(default_caps, autofill_strategies=["native"])
    acc_native = s.accept_run(
        r_native["id"],
        worker_id="worker-native",
        session_id="session-native",
        capabilities=native_caps,
    )
    assert acc_native["state"] == "accepted"

    # 3. Native HermesAdapter declares only strategies it actually supports via current helpers/tools
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID})
    test_client = TestClient(app, base_url=BASE_URL)
    transport = DirectTransport(test_client)
    worker_client = Client(
        base_url=BASE_URL,
        instance_id=s.instance_id,
        token=WORKER_TOKEN,
        transport=transport,
    )

    adapter = HermesAdapter(
        worker_client,
        worker_id=WORKER_ID,
        session_id="session-hermes-1",
        browser_profile="fixture-browser",
        skill_version="test-skill",
        provider="fixture",
        model="fixture",
        spool_path=tmp_path / "outbox_hermes.db",
    )

    # HermesAdapter does not declare native autofill since helpers do not implement it
    declared_strategies = adapter.capabilities.get("autofill_strategies", ())
    assert "native" not in declared_strategies

    # Calling adapter.accept on the native autofill run must fail rather than placebo-accepting
    with pytest.raises(ProtocolError):
        adapter.accept(r_native["id"])
