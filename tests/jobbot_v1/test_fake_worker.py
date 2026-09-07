"""Protocol regression tests for fake worker.

Verifies:
1) Integration against real in-process FastAPI/Service (no mocked Service).
2) Worker accepts run, claims 2 jobs, emits semantic events, and finishes as ready_for_review.
3) Exactly 2 distinct attempt IDs for fixed 2 jobs, same fake-session across attempts.
4) Run marks completed and browser lease is released when next claim returns None.
5) Fake worker describes fixture-only/no portal visited, cannot mark applied or call real URLs.
6) Refuses execution when service health mode is not 'development'.
"""
from datetime import datetime, timezone
import json
import httpx
import pytest
from fastapi.testclient import TestClient

from job_applier.managed import Service, ProtocolError
from job_applier.managed_api import create_app
from job_applier.managed_client import Client
from job_applier.managed_fake_worker import run


OPERATOR_TOKEN = "synthetic-operator-token-jobbot-v1-32chars"
WORKER_TOKEN = "synthetic-worker-token-jobbot-v1-32chars"
WORKER_ID = "worker"
BASE_URL = "http://127.0.0.1:8769"


class InProcessTransport(httpx.BaseTransport):
    """In-process transport forwarding httpx requests to FastAPI TestClient.

    Guarantees no real loopback network socket is contacted.
    """

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


def ready(tmp_path, count=2, settings=None):
    """Set up a real Service with fixed candidate identity and requested jobs."""
    s = Service.create(tmp_path / "jobs.db", instance_id="synthetic-test-instance", settings=settings)
    s.identity(
        identity_id="candidate",
        person_key="person",
        email="candidate@example.test",
        profile={"facts": {"work_authorization": "fixture"}, "resume_ref": "asset:fixture-v1"},
    )
    ids = []
    for i in range(count):
        job = s.intake(url=f"https://careers.example.test/jobs/{i}", source_id=str(i))
        s.eligibility(job["id"], "ready", reason="synthetic operator approval")
        ids.append(job["id"])
    r = s.request_run(
        request_id="request-1",
        job_ids=ids,
        identity_id="candidate",
        browser_profile="fixture-browser",
    )
    return s, r, ids


def test_fake_worker_integration_lifecycle(tmp_path):
    # Set up real Service and request run with 2 jobs; do not accept beforehand.
    s, r, ids = ready(tmp_path, count=2)
    assert r["state"] == "awaiting_worker"

    # Set up real in-process FastAPI app and transport.
    app = create_app(s, operator_token=OPERATOR_TOKEN, worker_tokens={WORKER_TOKEN: WORKER_ID})
    test_client = TestClient(app, base_url=BASE_URL)
    transport = InProcessTransport(test_client)

    worker_client = Client(
        base_url=BASE_URL,
        instance_id=s.instance_id,
        token=WORKER_TOKEN,
        transport=transport,
    )

    session_id = "fake-session"
    browser_profile = "fixture-browser"

    # Execute managed fake worker.
    result = run(
        worker_client,
        run_id=r["id"],
        worker_id=WORKER_ID,
        session_id=session_id,
        browser_profile=browser_profile,
    )

    # 1. Output structure verification.
    assert result["run_id"] == r["id"]
    outcomes = result["outcomes"]
    assert len(outcomes) == 2
    attempt_ids = [o["attempt_id"] for o in outcomes]
    assert len(set(attempt_ids)) == 2  # Exactly 2 distinct attempt IDs.

    for o in outcomes:
        assert isinstance(o["attempt_id"], int)
        assert o["outcome"] == "ready_for_review"

    # 2. Verify attempts in Service, session continuity, and fixture safety.
    processed_jobs = []
    for att_id in attempt_ids:
        att = s.attempt(att_id)
        assert att["session_id"] == session_id  # Old/new attempts have same fake-session.
        assert att["worker_id"] == WORKER_ID
        assert att["browser_profile"] == browser_profile
        assert att["outcome"] == "ready_for_review"
        assert att["outcome"] != "applied"

        # Explicit fixture-only description, no portal visited.
        evidence_text = (att.get("evidence") or "").lower()
        assert any(term in evidence_text for term in ("fixture", "no portal", "synthetic", "simulated", "fake"))
        processed_jobs.append(att["job_id"])

    assert sorted(processed_jobs) == sorted(ids)

    # 3. Nonempty actual app semantic events and no real URL calls.
    for att_id in attempt_ids:
        events = s.events(att_id)
        assert len(events) > 0  # Nonempty actual app semantic events.
        for ev in events:
            assert ev["actor"] == WORKER_ID
            payload_str = json.dumps(json.loads(ev["payload_json"])).lower()
            assert "http://" not in payload_str and "https://" not in payload_str

    # 4. Cannot mark applied or write to submission ledger.
    with s.tx() as db:
        assert db.execute("SELECT COUNT(*) FROM submission_ledger").fetchone()[0] == 0
        for job_id in ids:
            job_row = dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
            assert job_row["status"] == "ready_for_review"

        # Run completed.
        run_row = dict(db.execute("SELECT * FROM runs WHERE id=?", (r["id"],)).fetchone())
        assert run_row["state"] == "completed"

        # Browser lease released.
        lease = dict(db.execute("SELECT * FROM browser_leases WHERE profile=?", (browser_profile,)).fetchone())
        assert lease["state"] == "released"

    # 5. Run completed when next claim returns None.
    claim_next = worker_client.call("claim", run_id=r["id"], worker_id=WORKER_ID)
    assert claim_next is None


def test_fake_worker_refuses_non_development_health_mode():
    """Fake worker must verify service health mode and refuse if not development."""
    class StubClient:
        def call(self, operation, **kwargs):
            if operation == "health":
                return {
                    "instance_id": "stub-instance",
                    "submission_mode": "review",
                    "settings": {"mode": "pilot", "submission_mode": "review"},
                    "mode": "pilot",
                }
            raise AssertionError(f"Unexpected worker operation called on non-dev service: {operation}")

    stub = StubClient()
    with pytest.raises((ProtocolError, ValueError, RuntimeError)):
        run(
            stub,
            run_id="stub-run-id",
            worker_id=WORKER_ID,
            session_id="fake-session",
            browser_profile="fixture-browser",
        )
