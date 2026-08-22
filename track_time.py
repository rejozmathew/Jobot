#!/usr/bin/env python3
"""Per-application time + form-type tracker (the success metric).

Target: <= 5 min per application end-to-end.

Usage:
  python track_time.py start <company> <platform>   # mark attempt start (my wall-clock)
  python track_time.py end <company> <platform> <outcome> [--note TEXT]
      # computes my wall-clock (start->now) + handler time (from latest trace),
      # appends one line to timing_log.jsonl, prints a summary line.
  python track_time.py report
      # prints the table of all logged attempts.

'handler_seconds' = time the deterministic engine spent on the form (run:start ->
platform_handler_outcome in the latest artifacts trace). 'attempt_seconds' = my
total wall-clock for that job including probes/debug. The gap is the overhead I'm
trying to drive to ~0.
"""
import json, os, sys, time, glob
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "timing_log.jsonl")
MARK = os.path.join(ROOT, ".timing_start.json")
TARGET_S = 5 * 60


def _now():
    return time.time()


def cmd_start(company, platform):
    with open(MARK, "w") as f:
        json.dump({"company": company, "platform": platform, "ts": _now()}, f)
    print(f"[start] {company} ({platform}) {_now():.0f}")


def _latest_trace_dir():
    dirs = sorted(glob.glob(os.path.join(ROOT, "artifacts", "job-*")),
                  key=os.path.getmtime, reverse=True)
    return dirs[0] if dirs else None


def _handler_seconds(trace_dir):
    """Return (handler_seconds, form_type, outcome, first_ts, last_ts) from trace."""
    trace = os.path.join(trace_dir, "trace.jsonl")
    if not os.path.exists(trace):
        return None
    start_ts = end_ts = None
    form_type = None
    outcome = None
    for line in open(trace):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        ts = r.get("ts")
        if ts:
            try:
                t = datetime.fromisoformat(ts)
                if start_ts is None or t < start_ts:
                    start_ts = t
                if end_ts is None or t > end_ts:
                    end_ts = t
            except Exception:
                pass
        if r.get("event") == "platform_handler_detected":
            form_type = r.get("platform")
        if r.get("event") == "platform_handler_outcome":
            outcome = r.get("result")
    if start_ts and end_ts:
        return round((end_ts - start_ts).total_seconds(), 1)
    return None


def cmd_end(company, platform, outcome, note=""):
    start = _now()
    try:
        with open(MARK) as f:
            m = json.load(f)
        attempt_s = round(start - m["ts"], 1)
    except Exception:
        attempt_s = None
    tdir = _latest_trace_dir()
    handler_s = _handler_seconds(tdir) if tdir else None
    rec = {
        "company": company,
        "platform": platform,
        "form_type": platform,
        "attempt_seconds": attempt_s,
        "handler_seconds": handler_s,
        "overhead_seconds": round(attempt_s - handler_s, 1) if (attempt_s is not None and handler_s is not None) else None,
        "outcome": outcome,
        "target_seconds": TARGET_S,
        "meets_target": (attempt_s is not None and attempt_s <= TARGET_S),
        "note": note,
        "logged_at": datetime.now().isoformat(),
    }
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=1))


def cmd_report():
    if not os.path.exists(LOG):
        print("no timing_log.jsonl yet")
        return
    recs = [json.loads(l) for l in open(LOG) if l.strip()]
    print(f"{'company':14} {'form':11} {'attempt':>8} {'handler':>8} {'overhead':>8} {'outcome':10} {'<=5min':>6}")
    for r in recs:
        a = r.get("attempt_seconds")
        h = r.get("handler_seconds")
        o = r.get("overhead_seconds")
        print(f"{r['company'][:14]:14} {r.get('form_type','?')[:11]:11} "
              f"{str(a if a is not None else '-'):>8} {str(h if h is not None else '-'):>8} "
              f"{str(o if o is not None else '-'):>8} {r.get('outcome','?')[:10]:10} "
              f"{'YES' if r.get('meets_target') else 'no':>6}")
    ok = [r for r in recs if r.get("meets_target")]
    print(f"\n{len(ok)}/{len(recs)} meet the 5-min target")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
    elif args[0] == "start":
        cmd_start(args[1], args[2])
    elif args[0] == "end":
        note = ""
        if "--note" in args:
            i = args.index("--note")
            note = args[i + 1] if i + 1 < len(args) else ""
        cmd_end(args[1], args[2], args[3], note)
    elif args[0] == "report":
        cmd_report()
