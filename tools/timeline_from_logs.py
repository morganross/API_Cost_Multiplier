#!/usr/bin/env python3
"""
timeline_from_logs.py

Parse ACM logs and print a timeline with lines in the exact approved format:

start_mm:ss -- end_mm:ss (dur_mm:ss) -- ReportType, Model -- Result

ReportType:
- FPF rest
- FPF deep
- GPT-R standard
- GPT-R deep
- MA

Result: success | failure

Required input:
- --log-file must be provided (e.g., ../silky/api_cost_multiplier/logs/acm_subprocess_20231025_140000.log)
  (This contains FPF [RUN_START]/[RUN_COMPLETE] signals and GPT‑R start/end lines.)

Optional input:
- --acm-log-file can be provided to parse [RUN_START]/[FILES_WRITTEN] from the ACM main log
- --file-filter can be provided to restrict lines by substring (not commonly used)
- --no-t0-filter disables baseline (t0) filtering if needed (default: use safer t0 with fallback)

Usage examples (run from repo root):
  python ..\\silky\\api_cost_multiplier\\tools\\timeline_from_logs.py --log-file ..\\silky\\api_cost_multiplier\\logs\\acm_subprocess_YYYYMMDD_HHMMSS.log
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, List


# Timestamp prefix: "YYYY-MM-DD HH:MM:SS,mmm" or "YYYY-MM-DD HH:MM:SS.mmm"
TS_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,.](\d{3})\b")

# FPF scheduler signals (present in acm_subprocess.log)
FPF_RUN_START = re.compile(
    r"\[FPF RUN_START\]\s+id=(\S+)\s+kind=(\S+)\s+provider=(\S+)\s+model=(\S+)"
)
FPF_RUN_COMPLETE = re.compile(
    r"\[FPF RUN_COMPLETE\]\s+id=(\S+)\s+kind=(\S+)\s+provider=(\S+)\s+model=(\S+)\s+ok=(true|false)",
    re.IGNORECASE,
)

# PID-based GPT-R signals
GPTR_START = re.compile(
    r"\[GPTR_START\]\s+pid=(\d+)\s+type=(\S+)\s+model=(\S+)"
)
GPTR_END = re.compile(
    r"\[GPTR_END\]\s+pid=(\d+)\s+result=(success|failure)",
    re.IGNORECASE,
)

# MA signals
MA_START = re.compile(r"\[MA run (\d+)\] Starting research for query:")
MA_END = re.compile(r"\[MA run (\d+)\] Multi-agent report \(Markdown\) written to")

# ACM session start signal
ACM_LOG_CFG = re.compile(r"\[LOG_CFG\]")


@dataclass
class RunRecord:
    run_id: str
    report_type: str  # "FPF rest" | "FPF deep" | "GPT‑R standard" | "GPT‑R deep" | "MA"
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
    """
    Prefer 'kind' as authoritative. Use provider only as a fallback tie-breaker
    if kind is empty or unavailable.
    """
    k = (kind or "").strip().lower()
    p = (provider or "").strip().lower()
    if k == "deep":
        return "FPF deep"
    if not k and p == "openaidp":
        return "FPF deep"
    return "FPF rest"


def gptr_type_to_report_type(gptr_type: str) -> str:
    gptr_type = (gptr_type or "").strip().lower()
    return "GPT-R deep" if gptr_type == "deep" else "GPT-R standard"


def produce_timeline(
    subprocess_log_path: str,
    acm_log_path: Optional[str] = None,
    file_filter: Optional[str] = None,
    *,
    no_t0_filter: bool = False,
) -> List[RunRecord]:
    """
    Parse logs and produce a list of RunRecord with start/end/result filled when possible.
    Default printing includes complete records only in the exact required format.
    """
    # multimap: run_id -> list of records (supports repeated MA indices without overwriting)
    runs_by_id: Dict[str, List[RunRecord]] = {}

    def _get_list(rid: str) -> List[RunRecord]:
        lst = runs_by_id.get(rid)
        if lst is None:
            lst = []
            runs_by_id[rid] = lst
        return lst

    def _upsert_single(
        rid: str,
        report_type: Optional[str] = None,
        model: Optional[str] = None,
        start_ts: Optional[datetime] = None,
        end_ts: Optional[datetime] = None,
        result: Optional[str] = None,
    ) -> RunRecord:
        """
        For unique IDs (FPF id / GPTR pid-derived), maintain a single logical record at the tail of the list.
        """
        lst = _get_list(rid)
        if not lst:
            rec = RunRecord(
                run_id=rid,
                report_type=report_type or "unknown",
                model=model or "unknown",
                start_ts=start_ts,
                end_ts=end_ts,
                result=result,
            )
            lst.append(rec)
            return rec

        rec = lst[-1]

        # Update only with non-"unknown" values to avoid stomping higher-quality data.
        if report_type and report_type.strip().lower() != "unknown":
            rec.report_type = report_type

        if model and model.strip().lower() != "unknown":
            rec.model = model

        if rec.start_ts is None and start_ts is not None:
            rec.start_ts = start_ts
        if end_ts is not None:
            rec.end_ts = end_ts
        if result in ("success", "failure"):
            rec.result = result

        return rec

    # Determine session run start time (t0 candidate) from ACM log
    run_start_ts: Optional[datetime] = None
    if acm_log_path and os.path.isfile(acm_log_path):
        with open(acm_log_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if ACM_LOG_CFG.search(line):
                    ts = parse_ts(line)
                    if ts:
                        run_start_ts = ts  # keep last one found

    # Pass 1: parse acm_subprocess.log
    if os.path.isfile(subprocess_log_path):
        with open(subprocess_log_path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.rstrip("\r\n")
                ts = parse_ts(line)

                # Optional crude substring filter
                if file_filter and file_filter not in line:
                    # When provided, skip non-matching lines
                    continue

                # FPF RUN_START
                m = FPF_RUN_START.search(line)
                if m and ts:
                    run_id, kind, provider, model = m.group(1), m.group(2), m.group(3), m.group(4)
                    rtype = fpf_kind_to_report_type(kind, provider)
                    _upsert_single(run_id, report_type=rtype, model=model, start_ts=ts)
                    continue

                # FPF RUN_COMPLETE
                m = FPF_RUN_COMPLETE.search(line)
                if m and ts:
                    run_id, kind, provider, model, ok = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
                    rtype = fpf_kind_to_report_type(kind, provider)
                    _upsert_single(
                        run_id,
                        report_type=rtype,
                        model=model,
                        end_ts=ts,
                        result="success" if str(ok).lower() == "true" else "failure",
                    )
                    continue

                # GPTR_START
                m = GPTR_START.search(line)
                if m and ts:
                    pid, gptr_type, model = m.group(1), m.group(2), m.group(3)
                    run_id = f"gptr-{pid}"
                    rtype = gptr_type_to_report_type(gptr_type)
                    _upsert_single(run_id, report_type=rtype, model=model, start_ts=ts)
                    continue

                # GPTR_END
                m = GPTR_END.search(line)
                if m and ts:
                    pid, result = m.group(1), m.group(2)
                    run_id = f"gptr-{pid}"
                    _upsert_single(run_id, end_ts=ts, result=result.lower())
                    continue

                # MA_START
                m = MA_START.search(line)
                if m and ts:
                    run_index = m.group(1)
                    run_id = f"ma-{run_index}"
                    lst = _get_list(run_id)
                    # If last record complete, start a new one; else reuse the in-progress record
                    if lst and lst[-1].start_ts and lst[-1].end_ts:
                        lst.append(RunRecord(run_id=run_id, report_type="MA", model="unknown", start_ts=ts))
                    elif not lst:
                        lst.append(RunRecord(run_id=run_id, report_type="MA", model="unknown", start_ts=ts))
                    else:
                        # If in-progress without start (very unlikely), set start defensively
                        if lst[-1].start_ts is None:
                            lst[-1].start_ts = ts
                    continue

                # MA_END
                m = MA_END.search(line)
                if m and ts:
                    run_index = m.group(1)
                    run_id = f"ma-{run_index}"
                    lst = _get_list(run_id)
                    if lst:
                        rec = lst[-1]
                        if rec.end_ts is not None:
                            # Last record already complete; create a new approximate record for this artifact
                            approx_start = ts - timedelta(seconds=1)
                            new_rec = RunRecord(run_id=run_id, report_type="MA", model="unknown", start_ts=approx_start, end_ts=ts, result="success")
                            # Attempt to extract model; allow common characters such as / and +
                            model_match = re.search(r"model=([a-zA-Z0-9_\-\.:\+/]+)", line)
                            if model_match:
                                model_val = model_match.group(1)
                                if model_val.strip().lower() != "unknown":
                                    new_rec.model = model_val
                            lst.append(new_rec)
                        else:
                            rec.end_ts = ts
                            # Attempt to extract model; allow common characters such as / and +
                            model_match = re.search(r"model=([a-zA-Z0-9_\-\.:\+/]+)", line)
                            if model_match:
                                model_val = model_match.group(1)
                                if model_val.strip().lower() != "unknown":
                                    rec.model = model_val
                            rec.result = "success"
                    continue

    # Flatten complete records (default behavior: require start+end+result)
    complete: List[RunRecord] = []
    total_instances = 0
    ma_collisions = 0
    ma_incomplete_runs = 0

    for rid, lst in runs_by_id.items():
        total_instances += len(lst)
        if rid.startswith("ma-") and len(lst) > 1:
            ma_collisions += (len(lst) - 1)
        for rec in lst:
            if rec.start_ts and not rec.end_ts and rid.startswith("ma-"):
                ma_incomplete_runs += 1
            if rec.start_ts and rec.end_ts and rec.result in ("success", "failure"):
                complete.append(rec)

    # Emit concise debug metrics to stderr (do not pollute stdout timeline)
    print(
        f"DEBUG: instances_total={total_instances} complete={len(complete)} ma_collision_instances={ma_collisions} ma_incomplete_runs={ma_incomplete_runs}",
        file=sys.stderr,
    )

    # If nothing complete, nothing to print
    if not complete:
        return []

    # Determine earliest start among complete and t0 preferences
    earliest_start = min(r.start_ts for r in complete if r.start_ts is not None)  # type: ignore[arg-type]

    # Prefer the run start from acm_session.log if available and filtering is enabled.
    t0 = run_start_ts if not no_t0_filter else None

    # Warn if provided acm t0 appears later than earliest observed start by a significant margin
    if t0 and earliest_start and (t0 - earliest_start > timedelta(seconds=60)):
        print(
            "WARN: ACM t0 is later than earliest observed event by >60s; consider --no-t0-filter or correct --acm-log-file",
            file=sys.stderr,
        )

    # Fallback to earliest start when no acm t0 (or when no_t0_filter is set)
    if t0 is None:
        t0 = earliest_start

    # Apply baseline filtering unless explicitly disabled
    filtered = list(complete) if no_t0_filter else [r for r in complete if r.start_ts and r.start_ts >= t0]  # type: ignore[arg-type]
    # If filtering removed everything, fall back to earliest observed start to avoid over-filtering
    if not filtered and not no_t0_filter:
        t0 = earliest_start
        filtered = [r for r in complete if r.start_ts and r.start_ts >= t0]  # type: ignore[arg-type]

    print(
        f"DEBUG: t0={t0.isoformat() if t0 else 'None'} filtered_out={len(complete) - len(filtered)}",
        file=sys.stderr,
    )

    if not filtered:
        return []

    # Sort by start time with stable tie-breakers for determinism
    filtered.sort(key=lambda r: (r.start_ts, r.end_ts, r.run_id))

    # Print formatted lines (exact, approved format)
    for r in filtered:
        start_delta = r.start_ts - t0  # type: ignore[operator]
        end_delta = r.end_ts - t0      # type: ignore[operator]
        dur = r.end_ts - r.start_ts    # type: ignore[operator]
        start_s = to_mmss(start_delta)
        end_s = to_mmss(end_delta)
        dur_s = to_mmss(dur)
        # EXACT required format:
        # start_mm:ss -- end_mm:ss (dur_mm:ss) -- ReportType, Model -- Result
        print(f"{start_s} -- {end_s} ({dur_s}) -- {r.report_type}, {r.model} -- {r.result}")

    return filtered


def main():
    parser = argparse.ArgumentParser(description="Produce a concise timeline from ACM logs.")
    parser.add_argument("--log-file", required=True, help="Path to the subprocess log file to analyze.")
    parser.add_argument("--acm-log-file", default=None, help="Optional path to ACM main log to determine run start time.")
    parser.add_argument("--file-filter", default=None, help="Optional substring (e.g., file stem) to filter runs.")
    parser.add_argument("--no-t0-filter", action="store_true", help="Disable baseline (t0) filtering.")
    args = parser.parse_args()

    if not os.path.isfile(args.log_file):
        print(f"ERROR: log file not found: {args.log_file}", file=sys.stderr)
        sys.exit(2)

    try:
        produce_timeline(
            args.log_file,
            args.acm_log_file,
            args.file_filter,
            no_t0_filter=bool(args.no_t0_filter),
        )
    except Exception as e:
        print(f"ERROR: timeline generation failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
