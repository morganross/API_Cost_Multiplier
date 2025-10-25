#!/usr/bin/env python3
"""
timeline_from_logs.py

Parse ACM logs and print a timeline with lines in the exact approved format:

start_mm:ss — end_mm:ss (dur_mm:ss) — ReportType, Model — Result

ReportType:
- FPF rest
- FPF deep
- GPT‑R standard
- GPT‑R deep

Result: success | failure

Default input:
- --log-file defaults to ../silky/api_cost_multiplier/logs/acm_subprocess.log
  (This contains FPF [RUN_START]/[RUN_COMPLETE] signals and GPT‑R queue/OK lines.)

Optional input:
- --acm-log-file can be provided to parse [RUN_START]/[FILES_WRITTEN] from the ACM main log,
  but this script works with the subprocess log alone.

Usage examples (run from repo root):
  python ..\silky\api_cost_multiplier\tools\timeline_from_logs.py
  python ..\silky\api_cost_multiplier\tools\timeline_from_logs.py --log-file ..\silky\api_cost_multiplier\logs\acm_subprocess.log
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple


# Timestamp prefix: "YYYY-MM-DD HH:MM:SS,mmm -"
TS_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3})\b")

# FPF scheduler signals (present in acm_subprocess.log)
FPF_RUN_START = re.compile(
    r"\[FPF RUN_START\]\s+id=(\S+)\s+kind=(\S+)\s+provider=(\S+)\s+model=(\S+)"
)
FPF_RUN_COMPLETE = re.compile(
    r"\[FPF RUN_COMPLETE\]\s+id=(\S+)\s+kind=(\S+)\s+provider=(\S+)\s+model=(\S+)\s+ok=(true|false)"
)

# GPT‑R queue scheduling lines emitted by parent
# The hyphen in "GPT‑R" is a Unicode non-breaking hyphen in our logs; use "GPT.?R" to be robust.
GPTR_QUEUE = re.compile(
    r"\[GPT.?R queue (std|deep)\].*?model[\"']\s*:\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)

# GPT‑R success line from parent:
# Example: "OK: C:\path\file.md (openai:gpt-4.1)"
GPTR_OK = re.compile(r"OK:\s+.+\s+\(([^:()]+):([^)]+)\)\s*$", re.IGNORECASE)

# GPT‑R explicit failure line (returncode != 0)
GPTR_FAIL = re.compile(r"ERROR:\s*gpt-researcher subprocess failed", re.IGNORECASE)


@dataclass
class RunRecord:
    run_id: str
    report_type: str  # "FPF rest" | "FPF deep" | "GPT‑R standard" | "GPT‑R deep"
    model: str
    start_ts: Optional[datetime] = None
    end_ts: Optional[datetime] = None
    result: Optional[str] = None  # "success" | "failure"


def parse_ts(line: str) -> Optional[datetime]:
    m = TS_PREFIX.match(line)
    if not m:
        return None
    s, ms = m.group(1), m.group(2)
    try:
        base = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        return base.replace(microsecond=int(ms) * 1000)
    except Exception:
        return None


def to_mmss(delta: timedelta) -> str:
    total_seconds = int(round(delta.total_seconds()))
    m, s = divmod(max(0, total_seconds), 60)
    return f"{m:02d}:{s:02d}"


def fpf_kind_to_report_type(kind: str) -> str:
    k = (kind or "").strip().lower()
    return "FPF deep" if k == "deep" else "FPF rest"


def gptr_lane_to_report_type(lane: str) -> str:
    lane = (lane or "").strip().lower()
    return "GPT‑R deep" if lane == "deep" else "GPT‑R standard"


def produce_timeline(
    subprocess_log_path: str,
    acm_log_path: Optional[str] = None,
    file_filter: Optional[str] = None,
) -> List[RunRecord]:
    """
    Parse logs and produce a list of RunRecord with start/end/result filled when possible.
    """
    runs: Dict[str, RunRecord] = {}  # run_id -> record
    # For mapping GPT‑R by model to the most recent "open" run without end_ts
    gptr_open_by_model: Dict[Tuple[str, str], List[str]] = {}  # (report_type, model) -> [run_ids in start order]

    earliest_ts: Optional[datetime] = None

    def register_ts(ts: Optional[datetime]) -> None:
        nonlocal earliest_ts
        if ts and (earliest_ts is None or ts < earliest_ts):
            earliest_ts = ts

    # Helper to add "open" GPT‑R run
    def gptr_open_push(report_type: str, model: str, run_id: str) -> None:
        key = (report_type, model)
        gptr_open_by_model.setdefault(key, []).append(run_id)

    # Helper to mark success for the most recent open GPT‑R run matching provider:model
    def gptr_mark_success(ts: datetime, provider: str, model: str) -> None:
        # We ignore provider in indexing because type derives from "queue std/deep";
        # we find any open run with model and standard/deep variant that hasn't ended.
        for lane in ("GPT‑R standard", "GPT‑R deep"):
            key = (lane, model)
            if key in gptr_open_by_model and gptr_open_by_model[key]:
                run_id = gptr_open_by_model[key].pop(0)  # FIFO: earliest open
                rec = runs.get(run_id)
                if rec and rec.end_ts is None:
                    rec.end_ts = ts
                    rec.result = "success"
                return

    # Helper to mark failure for the most recent open GPT‑R run (no model on the error line)
    def gptr_mark_failure(ts: datetime) -> None:
        # Try standard first, then deep, by FIFO
        for lane in ("GPT‑R standard", "GPT‑R deep"):
            # Find any lane with open run
            for (rtype, model), queue in list(gptr_open_by_model.items()):
                if rtype != lane or not queue:
                    continue
                run_id = queue.pop(0)
                rec = runs.get(run_id)
                if rec and rec.end_ts is None:
                    rec.end_ts = ts
                    rec.result = "failure"
                    return

    # Pass 1: parse acm_subprocess.log
    if os.path.isfile(subprocess_log_path):
        with open(subprocess_log_path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.rstrip("\r\n")
                ts = parse_ts(line)
                register_ts(ts)

                # Optional file filter: restrict to lines containing the .md stem
                if file_filter and (file_filter not in line):
                    # Allow through if line has no file hint at all (queue/OK lines often don't),
                    # we still want to consider them. Only reject FPF start lines with file_b filter
                    pass

                # FPF RUN_START
                m = FPF_RUN_START.search(line)
                if m and ts:
                    run_id, kind, provider, model = m.group(1), m.group(2), m.group(3), m.group(4)
                    rtype = fpf_kind_to_report_type(kind)
                    rec = runs.get(run_id)
                    if not rec:
                        rec = RunRecord(run_id=run_id, report_type=rtype, model=model, start_ts=ts)
                        runs[run_id] = rec
                    else:
                        if rec.start_ts is None:
                            rec.start_ts = ts
                        rec.report_type = rtype
                        rec.model = model
                    continue

                # FPF RUN_COMPLETE
                m = FPF_RUN_COMPLETE.search(line)
                if m and ts:
                    run_id, kind, provider, model, ok = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
                    rec = runs.get(run_id)
                    if not rec:
                        rec = RunRecord(run_id=run_id, report_type=fpf_kind_to_report_type(kind), model=model)
                        runs[run_id] = rec
                    rec.end_ts = ts
                    rec.result = "success" if str(ok).lower() == "true" else "failure"
                    # If start not known, leave start_ts None (we'll skip incomplete later)
                    continue

                # GPT‑R queue start (std/deep)
                m = GPTR_QUEUE.search(line)
                if m and ts:
                    lane, model = m.group(1), m.group(2)
                    rtype = gptr_lane_to_report_type(lane)
                    # Create a synthetic run id: gptr-<lane>-N using the timestamp ordinal
                    run_id = f"gptr-{lane}-{int(ts.timestamp())}"
                    rec = RunRecord(run_id=run_id, report_type=rtype, model=model, start_ts=ts)
                    runs[run_id] = rec
                    gptr_open_push(rtype, model, run_id)
                    continue

                # GPT‑R success OK line
                m = GPTR_OK.search(line)
                if m and ts:
                    provider, model = m.group(1), m.group(2)
                    gptr_mark_success(ts, provider, model)
                    continue

                # GPT‑R explicit failure line (rc != 0)
                if GPTR_FAIL.search(line) and ts:
                    gptr_mark_failure(ts)
                    continue

    # Optional: parse ACM main log for [RUN_START]/[FILES_WRITTEN] (not strictly needed; disabled by default)
    # If desired later, we can enrich GPT‑R starts/ends from that log too.

    # Build final list: only records with both start and end
    complete: List[RunRecord] = []
    for rec in runs.values():
        if rec.start_ts and rec.end_ts and rec.result in ("success", "failure"):
            complete.append(rec)

    # Determine t0 as earliest timestamp among complete events
    if not complete:
        return []
    t0 = min(r.start_ts for r in complete if r.start_ts is not None)
    if earliest_ts and (earliest_ts < t0):
        # Prefer earliest matched event as t0 if earlier
        t0 = earliest_ts

    # Sort by start time
    complete.sort(key=lambda r: r.start_ts)

    # Print formatted lines
    for r in complete:
        start_delta = r.start_ts - t0
        end_delta = r.end_ts - t0
        dur = r.end_ts - r.start_ts
        start_s = to_mmss(start_delta)
        end_s = to_mmss(end_delta)
        dur_s = to_mmss(dur)
        # EXACT required format:
        # start_mm:ss — end_mm:ss (dur_mm:ss) — ReportType, Model — Result
        print(f"{start_s} — {end_s} ({dur_s}) — {r.report_type}, {r.model} — {r.result}")

    return complete


def main():
    default_log = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs", "acm_subprocess.log"))
    parser = argparse.ArgumentParser(description="Produce a concise timeline from ACM logs.")
    parser.add_argument("--log-file", default=default_log, help="Path to acm_subprocess.log (default: %(default)s)")
    parser.add_argument("--acm-log-file", default=None, help="Optional path to ACM main log (unused by default).")
    parser.add_argument("--file-filter", default=None, help="Optional substring (e.g., file stem) to filter runs.")
    args = parser.parse_args()

    if not os.path.isfile(args.log_file):
        print(f"ERROR: log file not found: {args.log_file}", file=sys.stderr)
        sys.exit(2)

    try:
        produce_timeline(args.log_file, args.acm_log_file, args.file_filter)
    except Exception as e:
        print(f"ERROR: timeline generation failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
