from datetime import datetime, timedelta

from job_applier.application_tracker import ApplicationTracker


class Clock:
    def __init__(self, *values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


def test_start_reuses_job_url_and_tracks_distinct_attempts(tmp_path):
    base = datetime(2026, 9, 2, 12, 0, 0)
    tracker = ApplicationTracker(tmp_path / "jobs.db", now_fn=Clock(base, base + timedelta(seconds=10)))

    first = tracker.start_attempt(
        url="https://example.com/jobs/123?utm_source=test",
        company="Example",
        title="VP Data",
        platform="workday",
        workflow="simplify",
    )
    second = tracker.start_attempt(
        url="https://example.com/jobs/123",
        company="Example",
        title="VP Data",
        platform="workday",
        workflow="simplify",
    )

    assert first["job_id"] == second["job_id"]
    assert first["attempt_id"] != second["attempt_id"]
    assert tracker.job_history()[0]["attempt_count"] == 2


def test_phase_hiccup_and_finish_update_one_authoritative_record(tmp_path):
    base = datetime(2026, 9, 2, 12, 0, 0)
    tracker = ApplicationTracker(
        tmp_path / "jobs.db",
        now_fn=Clock(
            base,
            base + timedelta(seconds=20),
            base + timedelta(seconds=80),
            base + timedelta(seconds=110),
            base + timedelta(seconds=150),
        ),
    )
    started = tracker.start_attempt(
        url="https://boards.greenhouse.io/example/jobs/123",
        company="Example",
        title="Senior Director Analytics",
        platform="greenhouse",
        workflow="simplify+deterministic",
    )

    tracker.transition_phase(started["attempt_id"], "simplify", note="autofill")
    tracker.record_hiccup(
        started["attempt_id"],
        category="dropdown_commit",
        description="Displayed No but retained aria-invalid",
        field_label="Government official",
        resolution="Clicked the real option",
        reusable_fix="Verify displayed value, aria-invalid, and error text",
        seconds_lost=30,
    )
    tracker.transition_phase(started["attempt_id"], "verification", note="email code")
    finished = tracker.finish_attempt(
        started["attempt_id"],
        outcome="applied",
        evidence="Live confirmation page",
        note="submitted",
    )

    assert finished["duration_seconds"] == 150.0
    assert finished["phase_breakdown_seconds"] == {
        "preflight": 20.0,
        "simplify": 90.0,
        "verification": 40.0,
    }
    assert finished["slowest_phase"] == "simplify"
    assert finished["hiccups"][0]["category"] == "dropdown_commit"
    assert finished["hiccups"][0]["resolution"] == "Clicked the real option"
    assert finished["improvement_candidates"] == [
        "Verify displayed value, aria-invalid, and error text"
    ]
    assert tracker.job_history(status="applied")[0]["company"] == "Example"

    summary = tracker.hiccup_summary(platform="greenhouse")
    assert summary == [
        {
            "platform": "greenhouse",
            "category": "dropdown_commit",
            "count": 1,
            "seconds_lost": 30.0,
            "open_count": 0,
            "reusable_fixes": ["Verify displayed value, aria-invalid, and error text"],
        }
    ]


def test_open_hiccups_are_visible_by_portal(tmp_path):
    base = datetime(2026, 9, 2, 12, 0, 0)
    tracker = ApplicationTracker(tmp_path / "jobs.db", now_fn=Clock(base, base + timedelta(seconds=5)))
    started = tracker.start_attempt(
        url="https://example.wd5.myworkdayjobs.com/job/1",
        company="Example",
        title="Director Data",
        platform="workday",
        workflow="simplify",
    )
    tracker.record_hiccup(
        started["attempt_id"],
        category="login",
        description="Account creation did not advance",
        status="open",
        reusable_fix="Hand off to user after one verified attempt",
    )

    assert tracker.hiccup_summary(platform="workday")[0]["open_count"] == 1
    assert tracker.hiccup_summary(platform="greenhouse") == []


def test_prior_application_to_same_workday_company_recommends_sign_in(tmp_path):
    base = datetime(2026, 9, 2, 12, 0, 0)
    tracker = ApplicationTracker(
        tmp_path / "jobs.db",
        now_fn=Clock(base, base + timedelta(seconds=60), base + timedelta(seconds=120)),
    )
    first = tracker.start_attempt(
        url="https://example.wd5.myworkdayjobs.com/en-US/careers/job/role-1",
        company="Example Company",
        title="Director Data",
        platform="workday",
    )
    tracker.finish_attempt(first["attempt_id"], outcome="applied", evidence="confirmation")

    second = tracker.start_attempt(
        url="https://example.wd5.myworkdayjobs.com/en-US/careers/job/role-2",
        company="Example Company",
        title="VP Data",
        platform="workday",
    )

    assert second["account_strategy"] == {
        "action": "sign_in_first",
        "source": "prior_application",
        "account_status": "inferred",
        "portal_key": "example.wd5.myworkdayjobs.com",
        "email": None,
    }
    company = tracker.company_history()[0]
    assert company["company"] == "Example Company"
    assert company["role_count"] == 2
    assert company["applied_count"] == 1
    assert company["platforms"] == ["workday"]


def test_confirmed_portal_account_is_reused_and_greenhouse_needs_none(tmp_path):
    base = datetime(2026, 9, 2, 12, 0, 0)
    tracker = ApplicationTracker(tmp_path / "jobs.db", now_fn=Clock(base))
    saved = tracker.set_company_account(
        company="Example Company",
        platform="workday",
        url="https://example.wd5.myworkdayjobs.com/en-US/careers",
        email="candidate@example.com",
        status="confirmed",
        note="Created during prior application",
    )

    assert saved["portal_key"] == "example.wd5.myworkdayjobs.com"
    assert tracker.account_strategy(
        company="Example Company",
        platform="workday",
        url="https://example.wd5.myworkdayjobs.com/en-US/careers/job/new-role",
    )["action"] == "sign_in"
    assert tracker.account_strategy(
        company="Example Company",
        platform="greenhouse",
        url="https://boards.greenhouse.io/example/jobs/1",
    )["action"] == "not_required"
