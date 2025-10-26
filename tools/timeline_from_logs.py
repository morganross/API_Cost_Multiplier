#!/usr/bin/env python3
"""
timeline_from_logs.py

Parse ACM logs and print a timeline with lines in the exact approved format:

start_mm:ss — end_mm:ss (dur_mm:ss) — ReportType, Model — Result

ReportType:
- FPF rest
- FPF deep
- GPT-R standard
- GPT-R deep

Result: success | failure

Required input:
- --log-file must be provided (e.g., ../silky/api_cost_multiplier/logs/acm_subprocess_20231025_140000.log)
  (This contains FPF [RUN_START]/[RUN_COMPLETE] signals and GPT‑R start/end lines.)

Optional input:
- --acm-log-file can be provided to parse [RUN_START]/[FILES_WRITTEN] from the ACM main log,
  but this script works with the subprocess log alone.

Usage examples (run from repo root):
  python ..\\silky\\api_cost_multiplier\\tools\\timeline_from_logs.py --log-file ..\\silky\\api_cost_multiplier\\logs\\acm_subprocess_YYYYMMDD_HHMMSS.log
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

# New PID-based GPT-R signals
GPTR_START = re.compile(
    r"\[GPTR_START\]\s+pid=(\d+)\s+type=(\S+)\s+model=(\S+)"
)
GPTR_END = re.compile(
    r"\[GPTR_END\]\s+pid=(\d+)\s+result=(success|failure)"
)

# MA signals
MA_START = re.compile(r"\[MA run (\d+)\] Starting research for query:")
MA_END = re.compile(r"\[MA run (\d+)\] Multi-agent report \(Markdown\) written to")

# ACM session start signal
ACM_LOG_CFG = re.compile(r"\[LOG_CFG\]")


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


def fpf_kind_to_report_type(kind: str, provider: str = "") -> str:
    k = (kind or "").strip().lower()
    p = (provider or "").strip().lower()
    if k == "deep" or p == "openaidp":
        return "FPF deep"
    return "FPF rest"


def gptr_type_to_report_type(gptr_type: str) -> str:
    gptr_type = (gptr_type or "").strip().lower()
    return "GPT-R deep" if gptr_type == "deep" else "GPT-R standard"


def produce_timeline(
    subprocess_log_path: str,
    acm_log_path: Optional[str] = None,
    file_filter: Optional[str] = None,
) -> List[RunRecord]:
    """
    Parse logs and produce a list of RunRecord with start/end/result filled when possible.
    """
    runs: Dict[str, RunRecord] = {}  # run_id (FPF id or GPTR pid) -> record
    
    # Find the start time of the most recent run from the ACM session log.
    # This will be our t0, the baseline for the timeline.
    run_start_ts: Optional[datetime] = None
    if acm_log_path and os.path.isfile(acm_log_path):
        with open(acm_log_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if ACM_LOG_CFG.search(line):
                    ts = parse_ts(line)
                    if ts:
                        run_start_ts = ts # Keep the last one found

    # Pass 1: parse acm_subprocess.log
    if os.path.isfile(subprocess_log_path):
        with open(subprocess_log_path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.rstrip("\r\n")
                ts = parse_ts(line)

                # Optional file filter: restrict to lines containing the .md stem
                if file_filter and (file_filter not in line):
                    # Allow through if line has no file hint at all (queue/OK lines often don't),
                    # we still want to consider them. Only reject FPF start lines with file_b filter
                    pass

                # FPF RUN_START
                m = FPF_RUN_START.search(line)
                if m and ts:
                    run_id, kind, provider, model = m.group(1), m.group(2), m.group(3), m.group(4)
                    rtype = fpf_kind_to_report_type(kind, provider)
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
                        rec = RunRecord(run_id=run_id, report_type=fpf_kind_to_report_type(kind, provider), model=model)
                        runs[run_id] = rec
                    rec.end_ts = ts
                    rec.result = "success" if str(ok).lower() == "true" else "failure"
                    continue

                # GPTR_START
                m = GPTR_START.search(line)
                if m and ts:
                    pid, gptr_type, model = m.group(1), m.group(2), m.group(3)
                    run_id = f"gptr-{pid}"
                    rtype = gptr_type_to_report_type(gptr_type)
                    rec = runs.get(run_id)
                    if not rec:
                        rec = RunRecord(run_id=run_id, report_type=rtype, model=model, start_ts=ts)
                        runs[run_id] = rec
                    else: # Should not happen if PIDs are unique, but handle defensively
                        if rec.start_ts is None:
                            rec.start_ts = ts
                        rec.report_type = rtype
                        rec.model = model
                    continue

                # GPTR_END
                m = GPTR_END.search(line)
                if m and ts:
                    pid, result = m.group(1), m.group(2)
                    run_id = f"gptr-{pid}"
                    rec = runs.get(run_id)
                    if rec:
                        rec.end_ts = ts
                        rec.result = result
                    continue
                
                # MA_START
                m = MA_START.search(line)
                if m and ts:
                    run_index = m.group(1)
                    # Model is not directly available in MA_START, will be inferred from MA_END or left as "unknown"
                    run_id = f"ma-{run_index}"
                    rec = runs.get(run_id)
                    if not rec:
                        rec = RunRecord(run_id=run_id, report_type="MA", model="unknown", start_ts=ts)
                        runs[run_id] = rec
                    else:
                        if rec.start_ts is None:
                            rec.start_ts = ts
                    continue

                # MA_END
                m = MA_END.search(line)
                if m and ts:
                    run_index = m.group(1)
                    run_id = f"ma-{run_index}"
                    rec = runs.get(run_id)
                    if rec:
                        rec.end_ts = ts
                        # Attempt to extract model from the line if available, otherwise keep "unknown"
                        model_match = re.search(r"model=([a-zA-Z0-9\-\._:]+)", line)
                        if model_match:
                            rec.model = model_match.group(1)
                        rec.result = "success" # Assume success if report written
                    continue

    # Optional: parse ACM main log for [RUN_START]/[FILES_WRITTEN] (not strictly needed; disabled by default)
    # If desired later, we can enrich GPT‑R starts/ends from that log too.

    # Build final list: only records with both start and end
    complete: List[RunRecord] = []
    for rec in runs.values():
        if rec.start_ts and rec.end_ts and rec.result in ("success", "failure"):
            complete.append(rec)
    
    # Debug print: show all parsed runs before filtering
    print(f"DEBUG: Parsed runs (before t0 filter): {runs}", file=sys.stderr)
    print(f"DEBUG: Complete runs (before t0 filter): {complete}", file=sys.stderr)

    # Determine t0. Prefer the run start from acm_session.log if available.
    # Otherwise, fall back to the earliest event in the subprocess log.
    if not complete:
        return []
    
    t0 = run_start_ts
    if not t0:
        # Fallback if acm_session.log couldn't be read or parsed
        t0 = min(r.start_ts for r in complete if r.start_ts is not None)
    
    # Filter out events that happened before our run started
    complete = [r for r in complete if r.start_ts >= t0]
    if not complete:
        return []

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
        # start_mm:ss -- end_mm:ss (dur_mm:ss) -- ReportType, Model -- Result
        print(f"{start_s} -- {end_s} ({dur_s}) -- {r.report_type}, {r.model} -- {r.result}")

    return complete


def main():
    parser = argparse.ArgumentParser(description="Produce a concise timeline from ACM logs.")
    parser.add_argument("--log-file", required=True, help="Path to the subprocess log file to analyze.")
    parser.add_argument("--acm-log-file", default=None, help="Optional path to ACM main log to determine run start time.")
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
