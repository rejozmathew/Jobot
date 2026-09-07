"""S3-R4 follow-up: semantic field context ordering across tool completions."""
from datetime import datetime, timedelta, timezone
import json
import pytest

try:
    from test_ownership import accept, ready
except ImportError:
    from tests.jobbot_v1.test_ownership import accept, ready


@pytest.mark.parametrize(
    ("next_event_type", "next_payload", "expected_context"),
    [
        (
            "field_context",
            {"page": "p2", "field": "email", "category": "repair"},
            {"page": "p2", "field": "email", "category": "repair"},
        ),
        (
            "navigation_verified",
            {"evidence": "navigated to next step"},
            {},
        ),
    ],
)
def test_field_context_ordering_late_completion_does_not_reactivate_prior_scope(
    tmp_path, next_event_type, next_payload, expected_context
):
    current = [datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)]

    def tick_now():
        val = current[0].isoformat()
        current[0] += timedelta(seconds=1)
        return val

    s, r, _ = ready(tmp_path, settings={"lease_seconds": 300})
    s.now = tick_now
    accept(s, r, worker="worker")
    a = s.claim(r["id"], worker_id="worker")

    ctx_a = {"page": "p1", "field": "phone", "category": "repair"}
    s.event(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        event_id="ev-context-a",
        event_type="field_context",
        observed_at=s.now(),
        payload=ctx_a,
    )

    s.action_start(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        action_id="slow",
        tool_name="click",
        writes_browser=True,
    )

    s.event(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        event_id="ev-next",
        event_type=next_event_type,
        observed_at=s.now(),
        payload=next_payload,
    )

    s.action_end(
        a["id"],
        worker_id="worker",
        fence=a["fence"],
        action_id="slow",
        status="success",
        duration_seconds=1,
    )

    end_event = next(e for e in s.events(a["id"]) if e["id"] == "action-end:slow")
    end_payload = json.loads(end_event["payload_json"])
    assert {k: end_payload.get(k) for k in ("page", "field", "category")} == ctx_a

    app_ctx = s.application_context(a["id"], worker_id="worker")
    assert app_ctx["field_budget"]["context"] == expected_context
