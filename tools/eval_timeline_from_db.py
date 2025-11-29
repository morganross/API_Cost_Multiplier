#!/usr/bin/env python3
"""
eval_timeline_from_db.py

Generate a timeline JSON for evaluation runs by combining:
1. Database timestamps (single_doc_results, pairwise_results)
2. Log file signals ([EVAL_SINGLE_START/END], [EVAL_PAIRWISE_START/END])
3. Config file metadata
4. CSV export file paths

Usage:
    python eval_timeline_from_db.py --db-path <sqlite_db> --log-file <acm_session.log> --output <eval_timeline.json>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any


@dataclass
class EvalRecord:
    """Single evaluation timeline record."""
    eval_type: str  # "single" | "pairwise"
    run_id: str
    model: str
    doc_count: int
    start_ts: Optional[str] = None  # ISO format from logs
    end_ts: Optional[str] = None    # ISO format from logs
    db_min_ts: Optional[str] = None  # MIN(timestamp) from DB
    db_max_ts: Optional[str] = None  # MAX(timestamp) from DB
    db_row_count: int = 0
    log_duration_seconds: Optional[float] = None
    db_duration_seconds: Optional[float] = None
    result: str = "unknown"


def parse_iso_ts(ts_str: str) -> Optional[datetime]:
    """Parse ISO format timestamp."""
    if not ts_str:
        return None
    try:
        # Handle both "2025-11-28T12:00:00.123456Z" and "2025-11-28T12:00:00Z"
        ts_str = ts_str.rstrip("Z")
        if "." in ts_str:
            return datetime.fromisoformat(ts_str)
        return datetime.fromisoformat(ts_str)
    except Exception:
        return None


def parse_log_ts(line: str) -> Optional[datetime]:
    """Extract timestamp from log line prefix like '2025-11-28 12:00:00,123'"""
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,.](\d{3})", line)
    if not match:
        return None
    try:
        base = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        return base.replace(microsecond=int(match.group(2)) * 1000)
    except Exception:
        return None


def to_mmss(seconds: float) -> str:
    """Convert seconds to mm:ss format."""
    total_seconds = int(round(seconds))
    m, s = divmod(max(0, total_seconds), 60)
    return f"{m:02d}:{s:02d}"


def query_db_timestamps(db_path: str) -> Dict[str, Any]:
    """
    Query database for evaluation timestamps and row counts.
    Returns dict with single_doc and pairwise data.
    """
    result = {
        "single_doc": {
            "min_ts": None,
            "max_ts": None,
            "row_count": 0,
            "by_model": {}
        },
        "pairwise": {
            "min_ts": None,
            "max_ts": None,
            "row_count": 0,
            "by_model": {}
        }
    }
    
    if not os.path.isfile(db_path):
        return result
    
    try:
        conn = sqlite3.connect(db_path)
        
        # Single-doc results
        try:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='single_doc_results'")
            if cur.fetchone():
                # Overall stats
                cur = conn.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM single_doc_results")
                min_ts, max_ts, count = cur.fetchone()
                result["single_doc"]["min_ts"] = min_ts
                result["single_doc"]["max_ts"] = max_ts
                result["single_doc"]["row_count"] = count or 0
                
                # By model
                cur = conn.execute("""
                    SELECT model, MIN(timestamp), MAX(timestamp), COUNT(*) 
                    FROM single_doc_results 
                    GROUP BY model
                """)
                for row in cur.fetchall():
                    model, m_min, m_max, m_count = row
                    result["single_doc"]["by_model"][model] = {
                        "min_ts": m_min,
                        "max_ts": m_max,
                        "row_count": m_count
                    }
        except Exception:
            pass
        
        # Pairwise results
        try:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pairwise_results'")
            if cur.fetchone():
                # Overall stats
                cur = conn.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM pairwise_results")
                min_ts, max_ts, count = cur.fetchone()
                result["pairwise"]["min_ts"] = min_ts
                result["pairwise"]["max_ts"] = max_ts
                result["pairwise"]["row_count"] = count or 0
                
                # By model
                cur = conn.execute("""
                    SELECT model, MIN(timestamp), MAX(timestamp), COUNT(*) 
                    FROM pairwise_results 
                    GROUP BY model
                """)
                for row in cur.fetchall():
                    model, m_min, m_max, m_count = row
                    result["pairwise"]["by_model"][model] = {
                        "min_ts": m_min,
                        "max_ts": m_max,
                        "row_count": m_count
                    }
        except Exception:
            pass
        
        conn.close()
    except Exception as e:
        print(f"ERROR: Failed to query database: {e}", file=sys.stderr)
    
    return result


def parse_eval_signals_from_log(log_path: str) -> List[EvalRecord]:
    """
    Parse [EVAL_SINGLE_START/END] and [EVAL_PAIRWISE_START/END] signals from log file.
    """
    records: List[EvalRecord] = []
    pending: Dict[str, Dict[str, Any]] = {}  # key = "type:id:model" -> partial record
    
    # Patterns for eval signals
    SINGLE_START = re.compile(
        r"\[EVAL_SINGLE_START\]\s+id=(\S+)\s+models=(\S+)\s+docs=(\d+)\s+runs=(\d+)\s+timestamp=(\S+)"
    )
    SINGLE_END = re.compile(
        r"\[EVAL_SINGLE_END\]\s+id=(\S+)\s+models=(\S+)\s+docs=(\d+)\s+rows=(\d+)\s+duration=(\d+\.?\d*)s\s+result=(\S+)\s+timestamp=(\S+)"
    )
    PAIRWISE_START = re.compile(
        r"\[EVAL_PAIRWISE_START\]\s+id=(\S+)\s+model=(\S+)\s+pairs=(\d+)\s+runs=(\d+)\s+timestamp=(\S+)"
    )
    PAIRWISE_END = re.compile(
        r"\[EVAL_PAIRWISE_END\]\s+id=(\S+)\s+model=(\S+)\s+pairs=(\d+)\s+duration=(\d+\.?\d*)s\s+result=(\S+)\s+timestamp=(\S+)"
    )
    
    if not os.path.isfile(log_path):
        return records
    
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.rstrip("\r\n")
                
                # EVAL_SINGLE_START
                m = SINGLE_START.search(line)
                if m:
                    run_id, models, docs, runs, ts = m.groups()
                    key = f"single:{run_id}:{models}"
                    pending[key] = {
                        "eval_type": "single",
                        "run_id": run_id,
                        "model": models,
                        "doc_count": int(docs),
                        "start_ts": ts,
                        "runs": int(runs)
                    }
                    continue
                
                # EVAL_SINGLE_END
                m = SINGLE_END.search(line)
                if m:
                    run_id, models, docs, rows, duration, result, ts = m.groups()
                    key = f"single:{run_id}:{models}"
                    rec_data = pending.pop(key, {})
                    rec = EvalRecord(
                        eval_type="single",
                        run_id=run_id,
                        model=models,
                        doc_count=int(docs),
                        start_ts=rec_data.get("start_ts"),
                        end_ts=ts,
                        db_row_count=int(rows),
                        log_duration_seconds=float(duration),
                        result=result
                    )
                    records.append(rec)
                    continue
                
                # EVAL_PAIRWISE_START
                m = PAIRWISE_START.search(line)
                if m:
                    run_id, model, pairs, runs, ts = m.groups()
                    key = f"pairwise:{run_id}:{model}"
                    pending[key] = {
                        "eval_type": "pairwise",
                        "run_id": run_id,
                        "model": model,
                        "pairs": int(pairs),
                        "start_ts": ts,
                        "runs": int(runs)
                    }
                    continue
                
                # EVAL_PAIRWISE_END
                m = PAIRWISE_END.search(line)
                if m:
                    run_id, model, pairs, duration, result, ts = m.groups()
                    key = f"pairwise:{run_id}:{model}"
                    rec_data = pending.pop(key, {})
                    rec = EvalRecord(
                        eval_type="pairwise",
                        run_id=run_id,
                        model=model,
                        doc_count=int(pairs),  # pairs count
                        start_ts=rec_data.get("start_ts"),
                        end_ts=ts,
                        log_duration_seconds=float(duration),
                        result=result
                    )
                    records.append(rec)
                    continue
    except Exception as e:
        print(f"ERROR: Failed to parse log file: {e}", file=sys.stderr)
    
    return records


def find_csv_files(export_dir: str) -> List[str]:
    """Find CSV files in export directory."""
    csv_files = []
    if export_dir and os.path.isdir(export_dir):
        for f in os.listdir(export_dir):
            if f.endswith(".csv"):
                csv_files.append(os.path.join(export_dir, f))
    return csv_files


@dataclass
class FpfCallRecord:
    """Individual FPF call from JSON log file."""
    run_id: str
    run_group_id: Optional[str]
    model: str
    started_at: str  # ISO format
    finished_at: str  # ISO format
    duration_seconds: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    log_file: str  # Source log file path


def parse_fpf_logs(fpf_logs_dir: str, time_window_start: Optional[str] = None, time_window_end: Optional[str] = None) -> List[FpfCallRecord]:
    """
    Parse individual FPF JSON log files from a directory.
    
    Args:
        fpf_logs_dir: Directory containing FPF JSON log files (or subdirs by run_group_id)
        time_window_start: Optional ISO timestamp to filter logs (include only logs after this)
        time_window_end: Optional ISO timestamp to filter logs (include only logs before this)
    
    Returns:
        List of FpfCallRecord objects sorted by started_at
    """
    records: List[FpfCallRecord] = []
    
    if not fpf_logs_dir or not os.path.isdir(fpf_logs_dir):
        return records
    
    # Parse time window
    tw_start = parse_iso_ts(time_window_start) if time_window_start else None
    tw_end = parse_iso_ts(time_window_end) if time_window_end else None
    
    def process_log_file(log_path: str):
        """Process a single FPF JSON log file."""
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Extract required fields
            run_id = data.get("run_id", "unknown")
            run_group_id = data.get("run_group_id")
            model = data.get("model", "unknown")
            started_at = data.get("started_at", "")
            finished_at = data.get("finished_at", "")
            
            # Apply time window filter
            if tw_start or tw_end:
                log_start = parse_iso_ts(started_at)
                if log_start:
                    if tw_start and log_start < tw_start:
                        return  # Skip logs before time window
                    if tw_end and log_start > tw_end:
                        return  # Skip logs after time window
            
            # Parse timestamps for duration
            dt_start = parse_iso_ts(started_at)
            dt_end = parse_iso_ts(finished_at)
            duration_seconds = 0.0
            if dt_start and dt_end:
                duration_seconds = (dt_end - dt_start).total_seconds()
            
            # Extract usage and cost
            usage = data.get("usage", {})
            cost = data.get("cost", {})
            
            prompt_tokens = usage.get("prompt_tokens", 0) or 0
            completion_tokens = usage.get("completion_tokens", 0) or 0
            total_tokens = usage.get("total_tokens", 0) or 0
            total_cost_usd = data.get("total_cost_usd", 0.0) or cost.get("total_cost_usd", 0.0) or 0.0
            
            rec = FpfCallRecord(
                run_id=run_id,
                run_group_id=run_group_id,
                model=model,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                total_cost_usd=total_cost_usd,
                log_file=os.path.basename(log_path)
            )
            records.append(rec)
        except Exception as e:
            print(f"WARNING: Failed to parse FPF log {log_path}: {e}", file=sys.stderr)
    
    # Walk directory - handle both flat structure and subdirs by run_group_id
    for item in os.listdir(fpf_logs_dir):
        item_path = os.path.join(fpf_logs_dir, item)
        if os.path.isfile(item_path) and item.endswith(".json") and not item.startswith("failure-"):
            # Direct JSON file in fpf_logs_dir
            process_log_file(item_path)
        elif os.path.isdir(item_path) and item != "validation":
            # Subdirectory (run_group_id folder) - process its JSON files
            for subitem in os.listdir(item_path):
                if subitem.endswith(".json") and not subitem.startswith("failure-"):
                    process_log_file(os.path.join(item_path, subitem))
    
    # Sort by started_at
    records.sort(key=lambda r: r.started_at)
    return records


def generate_eval_timeline(
    db_path: str,
    log_path: Optional[str] = None,
    config_path: Optional[str] = None,
    export_dir: Optional[str] = None,
    eval_type_label: str = "eval",
    fpf_logs_dir: Optional[str] = None,
    time_window_start: Optional[str] = None,
    time_window_end: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate combined eval timeline from all sources.
    
    Args:
        db_path: Path to SQLite database
        log_path: Path to ACM session log file
        config_path: Path to config.yaml
        export_dir: Path to CSV export directory
        eval_type_label: Label like "pre_combiner" or "playoffs"
        fpf_logs_dir: Path to FPF logs directory for individual call records
        time_window_start: ISO timestamp to filter FPF logs
        time_window_end: ISO timestamp to filter FPF logs
    """
    # Query DB timestamps
    db_data = query_db_timestamps(db_path)
    
    # Parse log signals
    log_records: List[EvalRecord] = []
    if log_path:
        log_records = parse_eval_signals_from_log(log_path)
    
    # Parse individual FPF calls
    fpf_calls: List[FpfCallRecord] = []
    if fpf_logs_dir:
        fpf_calls = parse_fpf_logs(fpf_logs_dir, time_window_start, time_window_end)
    
    # Find CSV files
    csv_files = find_csv_files(export_dir)
    
    # Build combined records
    records = []
    
    # Add log-based records enriched with DB data
    for rec in log_records:
        rec_dict = asdict(rec)
        
        # Enrich with DB data if available
        if rec.eval_type == "single":
            model_data = db_data["single_doc"]["by_model"].get(rec.model, {})
            if model_data:
                rec_dict["db_min_ts"] = model_data.get("min_ts")
                rec_dict["db_max_ts"] = model_data.get("max_ts")
                rec_dict["db_row_count"] = model_data.get("row_count", 0)
                # Calculate DB duration
                if model_data.get("min_ts") and model_data.get("max_ts"):
                    try:
                        dt_min = parse_iso_ts(model_data["min_ts"])
                        dt_max = parse_iso_ts(model_data["max_ts"])
                        if dt_min and dt_max:
                            rec_dict["db_duration_seconds"] = (dt_max - dt_min).total_seconds()
                    except Exception:
                        pass
        elif rec.eval_type == "pairwise":
            model_data = db_data["pairwise"]["by_model"].get(rec.model, {})
            if model_data:
                rec_dict["db_min_ts"] = model_data.get("min_ts")
                rec_dict["db_max_ts"] = model_data.get("max_ts")
                rec_dict["db_row_count"] = model_data.get("row_count", 0)
                if model_data.get("min_ts") and model_data.get("max_ts"):
                    try:
                        dt_min = parse_iso_ts(model_data["min_ts"])
                        dt_max = parse_iso_ts(model_data["max_ts"])
                        if dt_min and dt_max:
                            rec_dict["db_duration_seconds"] = (dt_max - dt_min).total_seconds()
                    except Exception:
                        pass
        
        records.append(rec_dict)
    
    # If no log records, create records from DB data alone
    if not log_records:
        # Single-doc from DB
        for model, model_data in db_data["single_doc"]["by_model"].items():
            rec_dict = {
                "eval_type": "single",
                "run_id": "db_only",
                "model": model,
                "doc_count": 0,
                "start_ts": None,
                "end_ts": None,
                "db_min_ts": model_data.get("min_ts"),
                "db_max_ts": model_data.get("max_ts"),
                "db_row_count": model_data.get("row_count", 0),
                "log_duration_seconds": None,
                "db_duration_seconds": None,
                "result": "success" if model_data.get("row_count", 0) > 0 else "unknown"
            }
            if model_data.get("min_ts") and model_data.get("max_ts"):
                try:
                    dt_min = parse_iso_ts(model_data["min_ts"])
                    dt_max = parse_iso_ts(model_data["max_ts"])
                    if dt_min and dt_max:
                        rec_dict["db_duration_seconds"] = (dt_max - dt_min).total_seconds()
                except Exception:
                    pass
            records.append(rec_dict)
        
        # Pairwise from DB
        for model, model_data in db_data["pairwise"]["by_model"].items():
            rec_dict = {
                "eval_type": "pairwise",
                "run_id": "db_only",
                "model": model,
                "doc_count": 0,
                "start_ts": None,
                "end_ts": None,
                "db_min_ts": model_data.get("min_ts"),
                "db_max_ts": model_data.get("max_ts"),
                "db_row_count": model_data.get("row_count", 0),
                "log_duration_seconds": None,
                "db_duration_seconds": None,
                "result": "success" if model_data.get("row_count", 0) > 0 else "unknown"
            }
            if model_data.get("min_ts") and model_data.get("max_ts"):
                try:
                    dt_min = parse_iso_ts(model_data["min_ts"])
                    dt_max = parse_iso_ts(model_data["max_ts"])
                    if dt_min and dt_max:
                        rec_dict["db_duration_seconds"] = (dt_max - dt_min).total_seconds()
                except Exception:
                    pass
            records.append(rec_dict)
    
    # Calculate overall eval run times
    overall_min_ts = None
    overall_max_ts = None
    
    # From single_doc
    if db_data["single_doc"]["min_ts"]:
        overall_min_ts = db_data["single_doc"]["min_ts"]
    if db_data["single_doc"]["max_ts"]:
        overall_max_ts = db_data["single_doc"]["max_ts"]
    
    # Update with pairwise (take earlier min, later max)
    if db_data["pairwise"]["min_ts"]:
        if overall_min_ts is None or db_data["pairwise"]["min_ts"] < overall_min_ts:
            overall_min_ts = db_data["pairwise"]["min_ts"]
    if db_data["pairwise"]["max_ts"]:
        if overall_max_ts is None or db_data["pairwise"]["max_ts"] > overall_max_ts:
            overall_max_ts = db_data["pairwise"]["max_ts"]
    
    # Build output
    output = {
        "eval_type_label": eval_type_label,
        "run_start": overall_min_ts,
        "run_end": overall_max_ts,
        "records": records,
        "sources": {
            "db_path": db_path if os.path.isfile(db_path) else None,
            "log_path": log_path if log_path and os.path.isfile(log_path) else None,
            "config_path": config_path if config_path and os.path.isfile(config_path) else None,
            "csv_files": csv_files,
            "fpf_logs_dir": fpf_logs_dir if fpf_logs_dir and os.path.isdir(fpf_logs_dir) else None
        },
        "summary": {
            "single_doc_total_rows": db_data["single_doc"]["row_count"],
            "pairwise_total_rows": db_data["pairwise"]["row_count"],
            "single_doc_models": list(db_data["single_doc"]["by_model"].keys()),
            "pairwise_models": list(db_data["pairwise"]["by_model"].keys()),
            "fpf_call_count": len(fpf_calls),
            "fpf_total_cost_usd": sum(r.total_cost_usd for r in fpf_calls),
            "fpf_total_tokens": sum(r.total_tokens for r in fpf_calls)
        },
        "fpf_calls": [asdict(r) for r in fpf_calls]  # Individual FPF call records
    }
    
    return output


def main():
    parser = argparse.ArgumentParser(description="Generate eval timeline from DB and logs.")
    parser.add_argument("--db-path", required=True, help="Path to SQLite database file.")
    parser.add_argument("--log-file", default=None, help="Path to ACM session log file.")
    parser.add_argument("--config-path", default=None, help="Path to config.yaml file.")
    parser.add_argument("--export-dir", default=None, help="Path to CSV export directory.")
    parser.add_argument("--eval-type", default="eval", help="Label for eval type (pre_combiner|playoffs).")
    parser.add_argument("--fpf-logs-dir", default=None, help="Path to FPF logs directory for individual calls.")
    parser.add_argument("--time-window-start", default=None, help="ISO timestamp to filter FPF logs (start).")
    parser.add_argument("--time-window-end", default=None, help="ISO timestamp to filter FPF logs (end).")
    parser.add_argument("--output", default=None, help="Output JSON file path.")
    args = parser.parse_args()
    
    if not os.path.isfile(args.db_path):
        print(f"ERROR: Database file not found: {args.db_path}", file=sys.stderr)
        sys.exit(2)
    
    try:
        timeline = generate_eval_timeline(
            db_path=args.db_path,
            log_path=args.log_file,
            config_path=args.config_path,
            export_dir=args.export_dir,
            eval_type_label=args.eval_type,
            fpf_logs_dir=args.fpf_logs_dir,
            time_window_start=args.time_window_start,
            time_window_end=args.time_window_end
        )
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(timeline, f, indent=2)
            print(f"Eval timeline exported to: {args.output}", file=sys.stderr)
        else:
            print(json.dumps(timeline, indent=2))
            
    except Exception as e:
        print(f"ERROR: Failed to generate eval timeline: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
