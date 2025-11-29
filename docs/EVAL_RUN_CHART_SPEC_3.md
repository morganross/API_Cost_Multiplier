# Evaluation Run Chart Specification 3: From SQLite Database

**Purpose:** Generate evaluation run charts programmatically using only data from the SQLite database files.

---

## Database Schema

### Tables Available

```sql
-- Single document evaluations
CREATE TABLE single_doc_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT,
    model TEXT,           -- Judge model (e.g., "openai_gpt-5.1")
    criterion TEXT,       -- Evaluation criterion name
    score INTEGER,        -- 1-5 score
    reason TEXT,
    timestamp TEXT        -- ISO format
);

-- Pairwise comparisons
CREATE TABLE pairwise_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id_1 TEXT,
    doc_id_2 TEXT,
    model TEXT,           -- Judge model
    winner_doc_id TEXT,
    reason TEXT,
    timestamp TEXT        -- ISO format
);

-- Run metadata
CREATE TABLE run_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

---

## Chart Generation from Database

### Step 1: Connect and Query

```python
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class EvalRunRecord:
    """Single evaluation run record for charting."""
    phase: str              # "precombine-single", "precombine-pairwise", etc.
    eval_type: str          # "single" or "pairwise"
    judge_model: str
    doc_count: int
    row_count: int
    first_ts: str           # ISO format
    last_ts: str            # ISO format
    duration_seconds: float
    status: str             # "success", "partial", "empty"


def connect_db(db_path: str) -> sqlite3.Connection:
    """Connect to SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
```

### Step 2: Extract Single-Doc Evaluation Runs

```python
def get_single_doc_runs(conn: sqlite3.Connection) -> List[EvalRunRecord]:
    """
    Extract single-doc evaluation runs grouped by judge model.
    Each model's evaluations form one "run".
    """
    records = []
    
    cursor = conn.execute("""
        SELECT 
            model,
            COUNT(DISTINCT doc_id) as doc_count,
            COUNT(*) as row_count,
            MIN(timestamp) as first_ts,
            MAX(timestamp) as last_ts
        FROM single_doc_results
        GROUP BY model
        ORDER BY MIN(timestamp)
    """)
    
    for row in cursor.fetchall():
        first_ts = row["first_ts"]
        last_ts = row["last_ts"]
        duration = calculate_duration(first_ts, last_ts)
        
        record = EvalRunRecord(
            phase="single-eval",
            eval_type="single",
            judge_model=row["model"],
            doc_count=row["doc_count"],
            row_count=row["row_count"],
            first_ts=first_ts,
            last_ts=last_ts,
            duration_seconds=duration,
            status="success" if row["row_count"] > 0 else "empty"
        )
        records.append(record)
    
    return records


def calculate_duration(start_ts: str, end_ts: str) -> float:
    """Calculate duration in seconds between two ISO timestamps."""
    if not start_ts or not end_ts:
        return 0.0
    try:
        # Handle various ISO formats
        for fmt in ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
            try:
                start = datetime.strptime(start_ts.split("Z")[0], fmt)
                end = datetime.strptime(end_ts.split("Z")[0], fmt)
                return (end - start).total_seconds()
            except ValueError:
                continue
    except Exception:
        pass
    return 0.0
```

### Step 3: Extract Pairwise Evaluation Runs

```python
def get_pairwise_runs(conn: sqlite3.Connection) -> List[EvalRunRecord]:
    """
    Extract pairwise evaluation runs grouped by judge model.
    """
    records = []
    
    cursor = conn.execute("""
        SELECT 
            model,
            COUNT(DISTINCT doc_id_1 || '|' || doc_id_2) as pair_count,
            COUNT(*) as row_count,
            MIN(timestamp) as first_ts,
            MAX(timestamp) as last_ts
        FROM pairwise_results
        GROUP BY model
        ORDER BY MIN(timestamp)
    """)
    
    for row in cursor.fetchall():
        first_ts = row["first_ts"]
        last_ts = row["last_ts"]
        duration = calculate_duration(first_ts, last_ts)
        
        record = EvalRunRecord(
            phase="pairwise-eval",
            eval_type="pairwise",
            judge_model=row["model"],
            doc_count=row["pair_count"],  # Number of unique pairs
            row_count=row["row_count"],
            first_ts=first_ts,
            last_ts=last_ts,
            duration_seconds=duration,
            status="success" if row["row_count"] > 0 else "empty"
        )
        records.append(record)
    
    return records
```

### Step 4: Get Run Metadata

```python
def get_run_metadata(conn: sqlite3.Connection) -> Dict[str, str]:
    """Extract run metadata from database."""
    metadata = {}
    try:
        cursor = conn.execute("SELECT key, value FROM run_metadata")
        for row in cursor.fetchall():
            metadata[row["key"]] = row["value"]
    except sqlite3.OperationalError:
        pass  # Table may not exist
    return metadata
```

### Step 5: Infer Phase from Context

```python
def infer_phase(db_path: str, metadata: Dict[str, str]) -> str:
    """
    Infer evaluation phase from database path or metadata.
    
    Database naming convention:
    - results_YYYYMMDD_HHMMSS_<hash>.sqlite
    
    Phase indicators:
    - "pre" in path → precombine
    - "playoffs" in path → postcombine
    - Multiple databases → compare timestamps
    """
    db_name = db_path.lower()
    
    if "pre" in db_name or "precombine" in db_name:
        return "precombine"
    elif "playoff" in db_name or "post" in db_name:
        return "postcombine"
    elif "combiner" in db_name:
        return "combiner"
    
    # Check metadata
    eval_type = metadata.get("eval_type", "")
    if "pre" in eval_type.lower():
        return "precombine"
    elif "playoff" in eval_type.lower() or "post" in eval_type.lower():
        return "postcombine"
    
    return "unknown"
```

### Step 6: Generate Complete Chart

```python
def generate_chart_from_db(db_path: str) -> Dict[str, Any]:
    """
    Generate complete evaluation run chart from a single database.
    
    Returns:
        Dict with chart data ready for rendering.
    """
    conn = connect_db(db_path)
    
    try:
        # Get metadata
        metadata = get_run_metadata(conn)
        phase = infer_phase(db_path, metadata)
        
        # Get all runs
        single_runs = get_single_doc_runs(conn)
        pairwise_runs = get_pairwise_runs(conn)
        
        # Update phase prefixes
        for run in single_runs:
            run.phase = f"{phase}-single-eval"
        for run in pairwise_runs:
            run.phase = f"{phase}-pairwise-eval"
        
        # Combine and sort by timestamp
        all_runs = single_runs + pairwise_runs
        all_runs.sort(key=lambda r: r.first_ts or "")
        
        # Calculate summary stats
        total_single_rows = sum(r.row_count for r in single_runs)
        total_pairwise_rows = sum(r.row_count for r in pairwise_runs)
        total_duration = sum(r.duration_seconds for r in all_runs)
        
        # Get overall time window
        all_timestamps = [r.first_ts for r in all_runs if r.first_ts] + \
                        [r.last_ts for r in all_runs if r.last_ts]
        run_start = min(all_timestamps) if all_timestamps else None
        run_end = max(all_timestamps) if all_timestamps else None
        
        chart = {
            "source": "sqlite_database",
            "database_path": db_path,
            "phase": phase,
            "run_start": run_start,
            "run_end": run_end,
            "metadata": metadata,
            "runs": [asdict(r) for r in all_runs],
            "summary": {
                "total_runs": len(all_runs),
                "single_eval_runs": len(single_runs),
                "pairwise_eval_runs": len(pairwise_runs),
                "total_single_rows": total_single_rows,
                "total_pairwise_rows": total_pairwise_rows,
                "total_duration_seconds": total_duration,
                "judge_models": list(set(r.judge_model for r in all_runs))
            }
        }
        
        return chart
        
    finally:
        conn.close()
```

---

## Multi-Database Chart (Pre + Playoffs)

```python
def generate_unified_chart_from_dbs(
    pre_db_path: str,
    playoffs_db_path: str
) -> Dict[str, Any]:
    """
    Generate unified chart from pre-combiner and playoffs databases.
    """
    pre_chart = generate_chart_from_db(pre_db_path)
    playoffs_chart = generate_chart_from_db(playoffs_db_path)
    
    # Update phases explicitly
    for run in pre_chart["runs"]:
        if "precombine" not in run["phase"]:
            run["phase"] = f"precombine-{run['phase']}"
    
    for run in playoffs_chart["runs"]:
        if "postcombine" not in run["phase"]:
            run["phase"] = f"postcombine-{run['phase']}"
    
    # Combine runs
    all_runs = pre_chart["runs"] + playoffs_chart["runs"]
    all_runs.sort(key=lambda r: r.get("first_ts") or "")
    
    unified = {
        "source": "multiple_sqlite_databases",
        "databases": {
            "pre_combiner": pre_db_path,
            "playoffs": playoffs_db_path
        },
        "run_start": pre_chart["run_start"],
        "run_end": playoffs_chart["run_end"],
        "runs": all_runs,
        "phases": {
            "precombine": pre_chart["summary"],
            "postcombine": playoffs_chart["summary"]
        },
        "summary": {
            "total_runs": len(all_runs),
            "total_single_rows": (pre_chart["summary"]["total_single_rows"] + 
                                  playoffs_chart["summary"]["total_single_rows"]),
            "total_pairwise_rows": (pre_chart["summary"]["total_pairwise_rows"] + 
                                    playoffs_chart["summary"]["total_pairwise_rows"]),
            "all_judge_models": list(set(
                pre_chart["summary"]["judge_models"] + 
                playoffs_chart["summary"]["judge_models"]
            ))
        }
    }
    
    return unified
```

---

## Advanced Queries

### Get Document Rankings by ELO

```python
def get_elo_rankings(conn: sqlite3.Connection, 
                     k_factor: float = 32.0, 
                     initial: float = 1000.0) -> Dict[str, float]:
    """Calculate ELO ratings from pairwise results."""
    ratings: Dict[str, float] = {}
    
    cursor = conn.execute(
        "SELECT doc_id_1, doc_id_2, winner_doc_id FROM pairwise_results ORDER BY id ASC"
    )
    
    for doc1, doc2, winner in cursor.fetchall():
        if doc1 not in ratings:
            ratings[doc1] = initial
        if doc2 not in ratings:
            ratings[doc2] = initial
        
        r1, r2 = ratings[doc1], ratings[doc2]
        e1 = 1.0 / (1.0 + 10.0 ** ((r2 - r1) / 400.0))
        e2 = 1.0 - e1
        
        if winner == doc1:
            s1, s2 = 1.0, 0.0
        elif winner == doc2:
            s1, s2 = 0.0, 1.0
        else:
            s1 = s2 = 0.5
        
        ratings[doc1] = r1 + k_factor * (s1 - e1)
        ratings[doc2] = r2 + k_factor * (s2 - e2)
    
    return ratings
```

### Get Criteria Score Breakdown

```python
def get_criteria_breakdown(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    """Get score breakdown by criterion across all documents."""
    breakdown = {}
    
    cursor = conn.execute("""
        SELECT 
            criterion,
            AVG(score) as avg_score,
            MIN(score) as min_score,
            MAX(score) as max_score,
            COUNT(*) as eval_count
        FROM single_doc_results
        GROUP BY criterion
        ORDER BY criterion
    """)
    
    for row in cursor.fetchall():
        breakdown[row["criterion"]] = {
            "avg_score": round(row["avg_score"], 2),
            "min_score": row["min_score"],
            "max_score": row["max_score"],
            "eval_count": row["eval_count"]
        }
    
    return breakdown
```

### Get Judge Model Agreement

```python
def get_judge_agreement(conn: sqlite3.Connection) -> Dict[str, float]:
    """
    Calculate agreement rate between judge models on pairwise decisions.
    """
    # Get all unique doc pairs
    cursor = conn.execute("""
        SELECT doc_id_1, doc_id_2, model, winner_doc_id
        FROM pairwise_results
        ORDER BY doc_id_1, doc_id_2, model
    """)
    
    pairs: Dict[str, Dict[str, str]] = defaultdict(dict)
    for row in cursor.fetchall():
        pair_key = f"{row['doc_id_1']}|{row['doc_id_2']}"
        pairs[pair_key][row["model"]] = row["winner_doc_id"]
    
    # Calculate agreement
    agreements = 0
    total_comparisons = 0
    
    for pair_key, model_decisions in pairs.items():
        models = list(model_decisions.keys())
        for i in range(len(models)):
            for j in range(i + 1, len(models)):
                total_comparisons += 1
                if model_decisions[models[i]] == model_decisions[models[j]]:
                    agreements += 1
    
    agreement_rate = agreements / total_comparisons if total_comparisons > 0 else 0.0
    
    return {
        "agreement_rate": round(agreement_rate, 4),
        "agreements": agreements,
        "total_comparisons": total_comparisons
    }
```

---

## Output Formats

### JSON Chart Export

```python
def export_chart_json(chart: Dict[str, Any], output_path: str) -> None:
    """Export chart to JSON file."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chart, f, indent=2, ensure_ascii=False)
```

### Markdown Table Export

```python
def export_chart_markdown(chart: Dict[str, Any], output_path: str) -> None:
    """Export chart as Markdown table."""
    lines = [
        f"# Evaluation Run Chart",
        f"",
        f"**Source:** {chart['source']}",
        f"**Run Period:** {chart.get('run_start', 'N/A')} → {chart.get('run_end', 'N/A')}",
        f"",
        f"## Runs",
        f"",
        f"| # | Phase | Type | Judge Model | Docs | Rows | Duration | Status |",
        f"|---|-------|------|-------------|------|------|----------|--------|"
    ]
    
    for i, run in enumerate(chart["runs"], 1):
        duration_mmss = format_duration(run["duration_seconds"])
        lines.append(
            f"| {i} | {run['phase']} | {run['eval_type']} | "
            f"{run['judge_model']} | {run['doc_count']} | {run['row_count']} | "
            f"{duration_mmss} | {run['status']} |"
        )
    
    lines.extend([
        f"",
        f"## Summary",
        f"",
        f"- **Total Runs:** {chart['summary']['total_runs']}",
        f"- **Single Eval Rows:** {chart['summary']['total_single_rows']}",
        f"- **Pairwise Rows:** {chart['summary']['total_pairwise_rows']}",
        f"- **Judge Models:** {', '.join(chart['summary'].get('judge_models', []))}",
    ])
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def format_duration(seconds: float) -> str:
    """Format seconds as mm:ss."""
    total = int(seconds)
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"
```

---

## CLI Usage

```python
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate eval chart from SQLite database")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--playoffs-db", help="Optional playoffs database for unified chart")
    parser.add_argument("--output", help="Output file path (JSON or MD)")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    
    args = parser.parse_args()
    
    if args.playoffs_db:
        chart = generate_unified_chart_from_dbs(args.db, args.playoffs_db)
    else:
        chart = generate_chart_from_db(args.db)
    
    if args.output:
        if args.format == "markdown":
            export_chart_markdown(chart, args.output)
        else:
            export_chart_json(chart, args.output)
        print(f"Chart exported to: {args.output}")
    else:
        print(json.dumps(chart, indent=2))
```

---

## Example Output

```json
{
  "source": "sqlite_database",
  "database_path": "results_20251128_202442_569f1952.sqlite",
  "phase": "precombine",
  "run_start": "2025-11-28T12:24:43.028607",
  "run_end": "2025-11-28T12:33:07.322243",
  "runs": [
    {
      "phase": "precombine-single-eval",
      "eval_type": "single",
      "judge_model": "openai_gpt-5.1",
      "doc_count": 6,
      "row_count": 24,
      "first_ts": "2025-11-28T12:24:43.028607",
      "last_ts": "2025-11-28T12:26:15.123456",
      "duration_seconds": 92.09,
      "status": "success"
    },
    {
      "phase": "precombine-single-eval",
      "eval_type": "single",
      "judge_model": "google_gemini-2.5-pro",
      "doc_count": 6,
      "row_count": 24,
      "first_ts": "2025-11-28T12:26:15.234567",
      "last_ts": "2025-11-28T12:28:46.912334",
      "duration_seconds": 151.68,
      "status": "success"
    },
    {
      "phase": "precombine-pairwise-eval",
      "eval_type": "pairwise",
      "judge_model": "openai_gpt-5.1",
      "doc_count": 3,
      "row_count": 3,
      "first_ts": "2025-11-28T12:28:46.956961",
      "last_ts": "2025-11-28T12:30:12.345678",
      "duration_seconds": 85.39,
      "status": "success"
    }
  ],
  "summary": {
    "total_runs": 4,
    "single_eval_runs": 2,
    "pairwise_eval_runs": 2,
    "total_single_rows": 48,
    "total_pairwise_rows": 6,
    "total_duration_seconds": 503.84,
    "judge_models": ["openai_gpt-5.1", "google_gemini-2.5-pro"]
  }
}
```
