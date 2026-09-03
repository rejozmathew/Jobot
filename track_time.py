#!/usr/bin/env python3
"""Legacy JSONL timing tracker.

Use ``run_applier.py track-start/track-phase/track-hiccup/track-end`` for all
new applications. Those commands write to the authoritative ``job_applier.db``.
This module remains only to read and preserve historical ``timing_log.jsonl``
records collected before unified SQLite tracking.

Target: <= 5 minutes per application, including login, user waits, debugging,
and submission verification.

Usage:
  python track_time.py start <company> <platform>
  python track_time.py phase <company> <platform> <phase> [--note TEXT]
  python track_time.py end <company> <platform> <outcome> [--note TEXT]
  python track_time.py report

Recommended phases: preflight, login, simplify, handler, residual_fields,
user_wait, debugging, verification, cleanup.
"""
import glob
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "timing_log.jsonl")
TARGET_S = 5 * 60


def _now():
    return time.time()


def _marker_path(company, platform):
    key = f"{company.strip().lower()}|{platform.strip().lower()}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")[:32] or "job"
    return os.path.join(ROOT, f".timing_start.{slug}.{digest}.json")


def _read_marker(company, platform):
    path = _marker_path(company, platform)
    try:
        with open(path, encoding="utf-8") as f:
            return path, json.load(f)
    except FileNotFoundError:
        # Backward compatibility with the original single-marker implementation.
        legacy = os.path.join(ROOT, ".timing_start.json")
        try:
            with open(legacy, encoding="utf-8") as f:
                marker = json.load(f)
            if marker.get("company") == company and marker.get("platform") == platform:
                marker.setdefault("current_phase", "preflight")
                marker.setdefault("phase_started_at", marker.get("ts"))
                marker.setdefault("current_phase_note", "")
                marker.setdefault("phases", [])
                return legacy, marker
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    return path, None


def _write_marker(path, marker):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(marker, f, indent=2)


def cmd_start(company, platform):
    now = _now()
    path = _marker_path(company, platform)
    marker = {
        "company": company,
        "platform": platform,
        "ts": now,
        "current_phase": "preflight",
        "phase_started_at": now,
        "current_phase_note": "",
        "phases": [],
    }
    _write_marker(path, marker)
    print(f"[start] {company} ({platform}) {now:.0f}")


def _close_current_phase(marker, now):
    phase = marker.get("current_phase")
    started = marker.get("phase_started_at")
    if not phase or started is None:
        return
    marker.setdefault("phases", []).append({
        "phase": phase,
        "seconds": round(max(0.0, now - started), 1),
        "note": marker.get("current_phase_note", ""),
    })


def cmd_phase(company, platform, phase, note=""):
    path, marker = _read_marker(company, platform)
    if not marker:
        raise SystemExit(f"no active timing attempt for {company} ({platform})")
    now = _now()
    _close_current_phase(marker, now)
    marker["current_phase"] = phase
    marker["phase_started_at"] = now
    marker["current_phase_note"] = note
    _write_marker(path, marker)
    print(f"[phase] {company} ({platform}) -> {phase}")


def _latest_trace_dir(since_ts=None):
    dirs = sorted(
        glob.glob(os.path.join(ROOT, "artifacts", "job-*")),
        key=os.path.getmtime,
        reverse=True,
    )
    if since_ts is not None:
        dirs = [d for d in dirs if os.path.getmtime(d) >= since_ts - 5]
    return dirs[0] if dirs else None


def _handler_seconds(trace_dir):
    """Return deterministic-handler elapsed seconds from a trace directory."""
    trace = os.path.join(trace_dir, "trace.jsonl")
    if not os.path.exists(trace):
        return None
    start_ts = end_ts = None
    for line in open(trace, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except Exception:
            continue
        ts = record.get("ts")
        if not ts:
            continue
        try:
            parsed = datetime.fromisoformat(ts)
        except Exception:
            continue
        if start_ts is None or parsed < start_ts:
            start_ts = parsed
        if end_ts is None or parsed > end_ts:
            end_ts = parsed
    if start_ts and end_ts:
        return round((end_ts - start_ts).total_seconds(), 1)
    return None


def _summarize_phases(phases):
    breakdown = {}
    notes = defaultdict(list)
    for entry in phases:
        phase = entry.get("phase") or "unclassified"
        breakdown[phase] = round(breakdown.get(phase, 0.0) + float(entry.get("seconds") or 0), 1)
        if entry.get("note"):
            notes[phase].append(entry["note"])
    largest = max(breakdown, key=breakdown.get) if breakdown else None
    losses = [
        {"phase": phase, "seconds": seconds, "notes": notes.get(phase, [])}
        for phase, seconds in sorted(breakdown.items(), key=lambda item: item[1], reverse=True)
    ]
    return breakdown, dict(notes), largest, losses


def cmd_end(company, platform, outcome, note=""):
    now = _now()
    path, marker = _read_marker(company, platform)
    attempt_s = None
    phases = []
    if marker:
        attempt_s = round(now - marker["ts"], 1)
        _close_current_phase(marker, now)
        phases = marker.get("phases", [])

    breakdown, phase_notes, largest, losses = _summarize_phases(phases)
    handler_s = breakdown.get("handler")
    if handler_s is None and marker and len(phases) <= 1:
        trace_dir = _latest_trace_dir(marker.get("ts"))
        handler_s = _handler_seconds(trace_dir) if trace_dir else None

    record = {
        "company": company,
        "platform": platform,
        "form_type": platform,
        "attempt_seconds": attempt_s,
        "handler_seconds": handler_s,
        "overhead_seconds": round(attempt_s - handler_s, 1)
        if attempt_s is not None and handler_s is not None else None,
        "time_breakdown_seconds": breakdown,
        "largest_loss_phase": largest,
        "phase_notes": phase_notes,
        "loss_summary": losses,
        "outcome": outcome,
        "target_seconds": TARGET_S,
        "meets_target": attempt_s is not None and attempt_s <= TARGET_S,
        "note": note,
        "logged_at": datetime.now().isoformat(),
    }
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    if marker and os.path.exists(path):
        os.remove(path)
    print(json.dumps(record, indent=1))


def cmd_report():
    if not os.path.exists(LOG):
        print("no timing_log.jsonl yet")
        return
    records = [json.loads(line) for line in open(LOG, encoding="utf-8") if line.strip()]
    print(
        f"{'company':14} {'form':11} {'attempt':>8} {'handler':>8} "
        f"{'overhead':>8} {'slowest':18} {'outcome':10} {'<=5min':>6}"
    )
    aggregate = defaultdict(float)
    for record in records:
        attempt = record.get("attempt_seconds")
        handler = record.get("handler_seconds")
        overhead = record.get("overhead_seconds")
        breakdown = record.get("time_breakdown_seconds") or {}
        for phase, seconds in breakdown.items():
            aggregate[phase] += float(seconds or 0)
        slowest = record.get("largest_loss_phase") or "-"
        print(
            f"{record['company'][:14]:14} {record.get('form_type', '?')[:11]:11} "
            f"{str(attempt if attempt is not None else '-'):>8} "
            f"{str(handler if handler is not None else '-'):>8} "
            f"{str(overhead if overhead is not None else '-'):>8} "
            f"{slowest[:18]:18} {record.get('outcome', '?')[:10]:10} "
            f"{'YES' if record.get('meets_target') else 'no':>6}"
        )
        for phase, notes in (record.get("phase_notes") or {}).items():
            if notes:
                print(f"  loss[{phase}]: {'; '.join(notes)}")
    passing = [record for record in records if record.get("meets_target")]
    print(f"\n{len(passing)}/{len(records)} meet the 5-min target")
    if aggregate:
        print("\nAggregate lost-time breakdown:")
        for phase, seconds in sorted(aggregate.items(), key=lambda item: item[1], reverse=True):
            print(f"  {phase}: {round(seconds, 1)}s")


def _option(args, name):
    if name not in args:
        return ""
    index = args.index(name)
    return args[index + 1] if index + 1 < len(args) else ""


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
    elif args[0] == "start" and len(args) >= 3:
        cmd_start(args[1], args[2])
    elif args[0] == "phase" and len(args) >= 4:
        cmd_phase(args[1], args[2], args[3], _option(args, "--note"))
    elif args[0] == "end" and len(args) >= 4:
        cmd_end(args[1], args[2], args[3], _option(args, "--note"))
    elif args[0] == "report":
        cmd_report()
    else:
        raise SystemExit(__doc__)
