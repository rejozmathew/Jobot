import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]


def run_cli(db_path, *args):
    env = os.environ.copy()
    env["JOB_APPLIER_DB_PATH"] = str(db_path)
    result = subprocess.run(
        [sys.executable, str(ROOT / "run_applier.py"), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_tracking_commands_share_the_job_database(tmp_path):
    db = tmp_path / "jobs.db"
    started = json.loads(run_cli(
        db,
        "track-start",
        "https://boards.greenhouse.io/example/jobs/123",
        "--company", "Example",
        "--title", "VP Data",
        "--platform", "greenhouse",
        "--workflow", "simplify",
    ))

    run_cli(db, "track-phase", str(started["attempt_id"]), "simplify", "--note", "autofill")
    run_cli(
        db,
        "track-hiccup",
        str(started["attempt_id"]),
        "dropdown_commit",
        "--description", "Dropdown did not commit",
        "--resolution", "Clicked real option",
        "--reusable-fix", "Verify aria-invalid clears",
        "--seconds-lost", "12",
    )
    finished = json.loads(run_cli(
        db,
        "track-end",
        str(started["attempt_id"]),
        "applied",
        "--evidence", "confirmation page",
    ))

    assert finished["outcome"] == "applied"
    history = run_cli(db, "history", "--status", "applied")
    assert "Example" in history
    assert "VP Data" in history
    hiccups = run_cli(db, "hiccups", "--platform", "greenhouse")
    assert "dropdown_commit" in hiccups
    assert "Verify aria-invalid clears" in hiccups


def test_apply_uses_one_tracked_job_and_finishes_attempt(monkeypatch, capsys):
    import job_applier.runner as runner_module
    import run_applier

    calls = []

    class FakeTracker:
        def start_attempt(self, **kwargs):
            calls.append(("start", kwargs))
            return {"job_id": "job-1", "seq_id": 7, "attempt_id": 11}

        def transition_phase(self, attempt_id, phase, **kwargs):
            calls.append(("phase", attempt_id, phase, kwargs))

        def record_hiccup(self, *args, **kwargs):
            calls.append(("hiccup", args, kwargs))

        def finish_attempt(self, attempt_id, **kwargs):
            calls.append(("finish", attempt_id, kwargs))
            return {"attempt_id": attempt_id, "outcome": kwargs["outcome"]}

    class FakeQueue:
        def add(self, request):
            raise AssertionError("cmd_apply must not create a duplicate job outside the tracker")

        def get(self, job_id):
            assert job_id == "job-1"
            return SimpleNamespace(id="job-1", seq_id=7)

    class FakeRunner:
        def __init__(self, headless=False):
            self.queue = FakeQueue()

        def run_specific_sync(self, job_id):
            assert job_id == "job-1"
            return {"status": "applied", "message": "confirmation verified", "error": ""}

    monkeypatch.setattr(run_applier, "_application_tracker", lambda: FakeTracker())
    monkeypatch.setattr(runner_module, "JobRunner", FakeRunner)
    args = SimpleNamespace(
        url="https://example.com/jobs/7",
        title="VP Data",
        company="Example",
        platform="greenhouse",
        headless=False,
        dry_run=False,
        submit=False,
    )

    run_applier.cmd_apply(args)

    assert [call[0] for call in calls] == ["start", "phase", "phase", "finish"]
    assert calls[-1][2]["outcome"] == "applied"
    assert "Tracking" in capsys.readouterr().out


def test_company_account_commands_drive_sign_in_strategy(tmp_path):
    db = tmp_path / "jobs.db"
    saved = json.loads(run_cli(
        db,
        "account-set",
        "--company", "Example",
        "--platform", "workday",
        "--url", "https://example.wd5.myworkdayjobs.com/en-US/careers",
        "--email", "candidate@example.com",
        "--status", "confirmed",
    ))
    checked = json.loads(run_cli(
        db,
        "account-check",
        "--company", "Example",
        "--platform", "workday",
        "--url", "https://example.wd5.myworkdayjobs.com/en-US/careers/job/role-2",
    ))

    assert saved["status"] == "confirmed"
    assert checked["action"] == "sign_in"
    assert checked["source"] == "company_portal_account"

    started = json.loads(run_cli(
        db,
        "track-start",
        "https://example.wd5.myworkdayjobs.com/en-US/careers/job/role-2",
        "--company", "Example",
        "--title", "VP Data",
        "--platform", "workday",
    ))
    run_cli(db, "track-end", str(started["attempt_id"]), "applied", "--evidence", "confirmation")
    companies = run_cli(db, "companies", "--applied-only")
    assert "Example" in companies
    assert "workday" in companies
    assert "sign-in accounts: 1" in companies
