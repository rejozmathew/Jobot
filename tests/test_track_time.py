import importlib.util
import json
from pathlib import Path


def load_module():
    path = Path(__file__).parents[1] / "track_time.py"
    spec = importlib.util.spec_from_file_location("track_time", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure(module, tmp_path, times):
    module.ROOT = str(tmp_path)
    module.LOG = str(tmp_path / "timing_log.jsonl")
    clock = iter(times)
    module._now = lambda: next(clock)


def test_tracks_phase_breakdown_and_removes_marker(tmp_path):
    tracker = load_module()
    configure(tracker, tmp_path, [100.0, 130.0, 190.0, 250.0])

    tracker.cmd_start("Example Co", "workday")
    tracker.cmd_phase("Example Co", "workday", "simplify", "autofill")
    tracker.cmd_phase("Example Co", "workday", "residual_fields", "dropdown")
    tracker.cmd_end("Example Co", "workday", "applied", "confirmed")

    record = json.loads(Path(tracker.LOG).read_text().strip())
    assert record["time_breakdown_seconds"] == {
        "preflight": 30.0,
        "simplify": 60.0,
        "residual_fields": 60.0,
    }
    assert record["largest_loss_phase"] == "simplify"
    assert record["phase_notes"] == {
        "simplify": ["autofill"],
        "residual_fields": ["dropdown"],
    }
    assert not Path(tracker._marker_path("Example Co", "workday")).exists()


def test_attempt_markers_are_isolated_by_company(tmp_path):
    tracker = load_module()
    configure(tracker, tmp_path, [100.0, 100.0, 110.0, 110.0])

    tracker.cmd_start("Alpha", "greenhouse")
    tracker.cmd_start("Beta", "workday")

    assert tracker._marker_path("Alpha", "greenhouse") != tracker._marker_path("Beta", "workday")
    assert Path(tracker._marker_path("Alpha", "greenhouse")).exists()
    assert Path(tracker._marker_path("Beta", "workday")).exists()


def test_report_shows_slowest_phase_and_aggregate_bottleneck(tmp_path, capsys):
    tracker = load_module()
    tracker.ROOT = str(tmp_path)
    tracker.LOG = str(tmp_path / "timing_log.jsonl")
    records = [
        {
            "company": "Alpha",
            "form_type": "greenhouse",
            "attempt_seconds": 240.0,
            "handler_seconds": 30.0,
            "overhead_seconds": 210.0,
            "outcome": "applied",
            "meets_target": True,
            "time_breakdown_seconds": {"simplify": 80.0, "residual_fields": 160.0},
            "largest_loss_phase": "residual_fields",
            "phase_notes": {"residual_fields": ["dropdown would not commit"]},
        },
        {
            "company": "Beta",
            "form_type": "workday",
            "attempt_seconds": 360.0,
            "handler_seconds": None,
            "overhead_seconds": None,
            "outcome": "blocked",
            "meets_target": False,
            "time_breakdown_seconds": {"login": 300.0, "verification": 60.0},
            "largest_loss_phase": "login",
        },
    ]
    Path(tracker.LOG).write_text("".join(json.dumps(r) + "\n" for r in records))

    tracker.cmd_report()
    output = capsys.readouterr().out

    assert "slowest" in output
    assert "residual_fields" in output
    assert "login" in output
    assert "Aggregate lost-time breakdown" in output
    assert "login: 300.0s" in output
    assert "dropdown would not commit" in output
