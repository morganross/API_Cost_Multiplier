# Evaluation Run Chart Specification 4: From CSV Export Files

**Purpose:** Generate evaluation run charts programmatically using the CSV export files created after each evaluation run.

---

## CSV File Structure

After each evaluation run, CSV files are exported to:
```
gptr-eval-process/exports/eval_run_YYYYMMDD_HHMMSS_<hash>/
├── single_doc_results_YYYYMMDD_HHMMSS_<hash>.csv
├── pairwise_results_YYYYMMDD_HHMMSS_<hash>.csv
├── elo_summary_YYYYMMDD_HHMMSS_<hash>.csv
└── eval_timeline.json  (if generated)
```

### Single Doc Results CSV Schema

```csv
id,doc_id,model,criterion,score,reason,timestamp
1,report.fpf.1.gemini.xyz.txt,openai_gpt-5.1,Accuracy,4,"Good accuracy...",2025-11-28T12:24:43.028607
2,report.fpf.1.gemini.xyz.txt,openai_gpt-5.1,Completeness,5,"Very complete...",2025-11-28T12:24:45.123456
...
```

### Pairwise Results CSV Schema

```csv
id,doc_id_1,doc_id_2,model,winner_doc_id,reason,timestamp
1,report.fpf.1.gemini.xyz.txt,report.gptr.1.gpt.abc.md,openai_gpt-5.1,report.fpf.1.gemini.xyz.txt,"Better structure...",2025-11-28T12:28:46.956961
...
```

### ELO Summary CSV Schema

```csv
doc_id,elo_rating,rank
report.fpf.1.gemini.xyz.txt,1064.5,1
report.gptr.1.gpt.abc.md,1032.2,2
...
```

---

## Chart Generation from CSV Files

### Step 1: Discover and Load CSVs

```python
import csv
import os
import glob
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class EvalRunRecord:
    """Single evaluation run record for charting."""
    phase: str              
    eval_type: str          
    judge_model: str
    doc_count: int
    row_count: int
    first_ts: str           
    last_ts: str            
    duration_seconds: float
    status: str             


def discover_csv_files(export_dir: str) -> Dict[str, str]:
    """
    Discover CSV files in an export directory.
    
    Returns:
        Dict mapping file type to path:
        {
            "single_doc": "/path/to/single_doc_results_*.csv",
            "pairwise": "/path/to/pairwise_results_*.csv",
            "elo": "/path/to/elo_summary_*.csv"
        }
    """
    files = {}
    
    # Find single doc results
    single_files = glob.glob(os.path.join(export_dir, "single_doc_results_*.csv"))
    if single_files:
        files["single_doc"] = single_files[0]
    
    # Find pairwise results
    pairwise_files = glob.glob(os.path.join(export_dir, "pairwise_results_*.csv"))
    if pairwise_files:
        files["pairwise"] = pairwise_files[0]
    
    # Find ELO summary
    elo_files = glob.glob(os.path.join(export_dir, "elo_summary_*.csv"))
    if elo_files:
        files["elo"] = elo_files[0]
    
    return files


def load_csv(csv_path: str) -> List[Dict[str, Any]]:
    """Load CSV file into list of dicts."""
    rows = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows
```

### Step 2: Extract Single-Doc Runs from CSV

```python
def get_single_doc_runs_from_csv(csv_path: str) -> List[EvalRunRecord]:
    """
    Extract single-doc evaluation runs grouped by judge model.
    """
    if not csv_path or not os.path.exists(csv_path):
        return []
    
    rows = load_csv(csv_path)
    if not rows:
        return []
    
    # Group by model
    by_model: Dict[str, List[Dict]] = {}
    for row in rows:
        model = row.get("model", "unknown")
        if model not in by_model:
            by_model[model] = []
        by_model[model].append(row)
    
    records = []
    for model, model_rows in by_model.items():
        # Get unique doc_ids
        doc_ids = set(r.get("doc_id", "") for r in model_rows)
        
        # Get timestamp range
        timestamps = [r.get("timestamp", "") for r in model_rows if r.get("timestamp")]
        timestamps.sort()
        
        first_ts = timestamps[0] if timestamps else ""
        last_ts = timestamps[-1] if timestamps else ""
        duration = calculate_duration(first_ts, last_ts)
        
        record = EvalRunRecord(
            phase="single-eval",
            eval_type="single",
            judge_model=model,
            doc_count=len(doc_ids),
            row_count=len(model_rows),
            first_ts=first_ts,
            last_ts=last_ts,
            duration_seconds=duration,
            status="success" if len(model_rows) > 0 else "empty"
        )
        records.append(record)
    
    # Sort by first timestamp
    records.sort(key=lambda r: r.first_ts or "")
    return records


def calculate_duration(start_ts: str, end_ts: str) -> float:
    """Calculate duration in seconds between two ISO timestamps."""
    if not start_ts or not end_ts:
        return 0.0
    try:
        for fmt in ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
            try:
                start = datetime.strptime(start_ts.split("Z")[0].split("+")[0], fmt)
                end = datetime.strptime(end_ts.split("Z")[0].split("+")[0], fmt)
                return (end - start).total_seconds()
            except ValueError:
                continue
    except Exception:
        pass
    return 0.0
```

### Step 3: Extract Pairwise Runs from CSV

```python
def get_pairwise_runs_from_csv(csv_path: str) -> List[EvalRunRecord]:
    """
    Extract pairwise evaluation runs grouped by judge model.
    """
    if not csv_path or not os.path.exists(csv_path):
        return []
    
    rows = load_csv(csv_path)
    if not rows:
        return []
    
    # Group by model
    by_model: Dict[str, List[Dict]] = {}
    for row in rows:
        model = row.get("model", "unknown")
        if model not in by_model:
            by_model[model] = []
        by_model[model].append(row)
    
    records = []
    for model, model_rows in by_model.items():
        # Get unique pairs
        pairs = set()
        for r in model_rows:
            d1, d2 = r.get("doc_id_1", ""), r.get("doc_id_2", "")
            pairs.add((min(d1, d2), max(d1, d2)))
        
        # Get timestamp range
        timestamps = [r.get("timestamp", "") for r in model_rows if r.get("timestamp")]
        timestamps.sort()
        
        first_ts = timestamps[0] if timestamps else ""
        last_ts = timestamps[-1] if timestamps else ""
        duration = calculate_duration(first_ts, last_ts)
        
        record = EvalRunRecord(
            phase="pairwise-eval",
            eval_type="pairwise",
            judge_model=model,
            doc_count=len(pairs),
            row_count=len(model_rows),
            first_ts=first_ts,
            last_ts=last_ts,
            duration_seconds=duration,
            status="success" if len(model_rows) > 0 else "empty"
        )
        records.append(record)
    
    records.sort(key=lambda r: r.first_ts or "")
    return records
```

### Step 4: Load ELO Rankings from CSV

```python
def get_elo_rankings_from_csv(csv_path: str) -> List[Dict[str, Any]]:
    """
    Load ELO rankings from CSV file.
    
    Returns:
        List of dicts with doc_id, elo_rating, rank
    """
    if not csv_path or not os.path.exists(csv_path):
        return []
    
    rows = load_csv(csv_path)
    rankings = []
    
    for row in rows:
        rankings.append({
            "doc_id": row.get("doc_id", ""),
            "elo_rating": float(row.get("elo_rating", 1000)),
            "rank": int(row.get("rank", 0))
        })
    
    # Sort by rank
    rankings.sort(key=lambda r: r["rank"])
    return rankings
```

### Step 5: Infer Phase from Directory Name

```python
def infer_phase_from_path(export_dir: str) -> str:
    """
    Infer evaluation phase from export directory name.
    
    Expected format: eval_run_YYYYMMDD_HHMMSS_<hash>
    With optional prefix: pre_eval_run_*, playoffs_eval_run_*
    """
    dir_name = os.path.basename(export_dir).lower()
    
    if "pre" in dir_name:
        return "precombine"
    elif "playoff" in dir_name or "post" in dir_name:
        return "postcombine"
    elif "combiner" in dir_name:
        return "combiner"
    
    return "eval"
```

### Step 6: Generate Complete Chart from Export Directory

```python
def generate_chart_from_csv_dir(export_dir: str) -> Dict[str, Any]:
    """
    Generate complete evaluation run chart from a CSV export directory.
    
    Args:
        export_dir: Path to export directory containing CSV files
        
    Returns:
        Dict with chart data ready for rendering.
    """
    # Discover CSV files
    csv_files = discover_csv_files(export_dir)
    
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in: {export_dir}")
    
    # Infer phase
    phase = infer_phase_from_path(export_dir)
    
    # Extract runs
    single_runs = get_single_doc_runs_from_csv(csv_files.get("single_doc", ""))
    pairwise_runs = get_pairwise_runs_from_csv(csv_files.get("pairwise", ""))
    
    # Update phase prefixes
    for run in single_runs:
        run.phase = f"{phase}-single-eval"
    for run in pairwise_runs:
        run.phase = f"{phase}-pairwise-eval"
    
    # Combine and sort
    all_runs = single_runs + pairwise_runs
    all_runs.sort(key=lambda r: r.first_ts or "")
    
    # Load ELO rankings if available
    elo_rankings = get_elo_rankings_from_csv(csv_files.get("elo", ""))
    
    # Calculate summary
    total_single_rows = sum(r.row_count for r in single_runs)
    total_pairwise_rows = sum(r.row_count for r in pairwise_runs)
    total_duration = sum(r.duration_seconds for r in all_runs)
    
    # Get time window
    all_ts = [r.first_ts for r in all_runs if r.first_ts] + \
             [r.last_ts for r in all_runs if r.last_ts]
    run_start = min(all_ts) if all_ts else None
    run_end = max(all_ts) if all_ts else None
    
    chart = {
        "source": "csv_export",
        "export_directory": export_dir,
        "csv_files": csv_files,
        "phase": phase,
        "run_start": run_start,
        "run_end": run_end,
        "runs": [asdict(r) for r in all_runs],
        "elo_rankings": elo_rankings,
        "summary": {
            "total_runs": len(all_runs),
            "single_eval_runs": len(single_runs),
            "pairwise_eval_runs": len(pairwise_runs),
            "total_single_rows": total_single_rows,
            "total_pairwise_rows": total_pairwise_rows,
            "total_duration_seconds": total_duration,
            "judge_models": list(set(r.judge_model for r in all_runs)),
            "documents_evaluated": len(elo_rankings) if elo_rankings else 0
        }
    }
    
    return chart
```

---

## Multi-Directory Chart (Multiple Export Folders)

```python
def generate_unified_chart_from_csv_dirs(
    export_dirs: List[str],
    phase_labels: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Generate unified chart from multiple CSV export directories.
    
    Args:
        export_dirs: List of export directory paths
        phase_labels: Optional dict mapping dir path to phase label
        
    Returns:
        Unified chart combining all exports.
    """
    all_runs = []
    all_elo = []
    phase_summaries = {}
    csv_sources = {}
    
    for export_dir in export_dirs:
        chart = generate_chart_from_csv_dir(export_dir)
        
        # Override phase label if provided
        if phase_labels and export_dir in phase_labels:
            phase = phase_labels[export_dir]
            for run in chart["runs"]:
                run["phase"] = f"{phase}-{run['eval_type']}-eval"
            chart["phase"] = phase
        
        all_runs.extend(chart["runs"])
        all_elo.extend(chart.get("elo_rankings", []))
        phase_summaries[chart["phase"]] = chart["summary"]
        csv_sources[chart["phase"]] = chart["csv_files"]
    
    # Sort all runs by timestamp
    all_runs.sort(key=lambda r: r.get("first_ts") or "")
    
    # Deduplicate ELO rankings (keep highest rating if duplicates)
    elo_by_doc = {}
    for elo in all_elo:
        doc_id = elo["doc_id"]
        if doc_id not in elo_by_doc or elo["elo_rating"] > elo_by_doc[doc_id]["elo_rating"]:
            elo_by_doc[doc_id] = elo
    
    final_elo = sorted(elo_by_doc.values(), key=lambda x: -x["elo_rating"])
    for i, elo in enumerate(final_elo, 1):
        elo["rank"] = i
    
    # Calculate unified summary
    all_ts = [r.get("first_ts") for r in all_runs if r.get("first_ts")] + \
             [r.get("last_ts") for r in all_runs if r.get("last_ts")]
    
    unified = {
        "source": "multiple_csv_exports",
        "export_directories": export_dirs,
        "csv_sources": csv_sources,
        "run_start": min(all_ts) if all_ts else None,
        "run_end": max(all_ts) if all_ts else None,
        "runs": all_runs,
        "elo_rankings": final_elo,
        "phase_summaries": phase_summaries,
        "summary": {
            "total_runs": len(all_runs),
            "total_single_rows": sum(s["total_single_rows"] for s in phase_summaries.values()),
            "total_pairwise_rows": sum(s["total_pairwise_rows"] for s in phase_summaries.values()),
            "all_judge_models": list(set(
                model 
                for s in phase_summaries.values() 
                for model in s.get("judge_models", [])
            )),
            "total_documents": len(final_elo)
        }
    }
    
    return unified
```

---

## Score Analysis from Single-Doc CSV

```python
def analyze_single_doc_scores(csv_path: str) -> Dict[str, Any]:
    """
    Analyze scores from single-doc results CSV.
    
    Returns detailed breakdown by document, criterion, and model.
    """
    rows = load_csv(csv_path)
    
    # By document
    by_doc: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        doc_id = row.get("doc_id", "")
        if doc_id not in by_doc:
            by_doc[doc_id] = {
                "scores": [],
                "by_criterion": {},
                "by_model": {}
            }
        
        score = int(row.get("score", 0))
        criterion = row.get("criterion", "")
        model = row.get("model", "")
        
        by_doc[doc_id]["scores"].append(score)
        
        if criterion not in by_doc[doc_id]["by_criterion"]:
            by_doc[doc_id]["by_criterion"][criterion] = []
        by_doc[doc_id]["by_criterion"][criterion].append(score)
        
        if model not in by_doc[doc_id]["by_model"]:
            by_doc[doc_id]["by_model"][model] = []
        by_doc[doc_id]["by_model"][model].append(score)
    
    # Calculate aggregates
    doc_summaries = []
    for doc_id, data in by_doc.items():
        scores = data["scores"]
        doc_summaries.append({
            "doc_id": doc_id,
            "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
            "total_score": sum(scores),
            "max_possible": len(scores) * 5,
            "score_pct": round((sum(scores) / (len(scores) * 5)) * 100, 1) if scores else 0,
            "eval_count": len(scores),
            "by_criterion": {
                k: round(sum(v) / len(v), 2) 
                for k, v in data["by_criterion"].items()
            },
            "by_model": {
                k: round(sum(v) / len(v), 2)
                for k, v in data["by_model"].items()
            }
        })
    
    # Sort by score percentage descending
    doc_summaries.sort(key=lambda x: -x["score_pct"])
    
    # Overall stats
    all_scores = [s for d in by_doc.values() for s in d["scores"]]
    
    return {
        "documents": doc_summaries,
        "overall": {
            "total_evaluations": len(all_scores),
            "avg_score": round(sum(all_scores) / len(all_scores), 2) if all_scores else 0,
            "score_distribution": {
                i: all_scores.count(i) for i in range(1, 6)
            }
        }
    }
```

---

## Output Formats

### JSON Export

```python
def export_chart_json(chart: Dict[str, Any], output_path: str) -> None:
    """Export chart to JSON file."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chart, f, indent=2, ensure_ascii=False)


def format_duration(seconds: float) -> str:
    """Format seconds as mm:ss."""
    total = int(seconds)
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"
```

### Markdown Table Export

```python
def export_chart_markdown(chart: Dict[str, Any], output_path: str) -> None:
    """Export chart as Markdown table."""
    lines = [
        f"# Evaluation Run Chart (from CSV)",
        f"",
        f"**Source:** {chart['source']}",
        f"**Export Directory:** {chart.get('export_directory', 'Multiple')}",
        f"**Run Period:** {chart.get('run_start', 'N/A')} → {chart.get('run_end', 'N/A')}",
        f"",
        f"## Evaluation Runs",
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
    
    # Add ELO rankings if present
    if chart.get("elo_rankings"):
        lines.extend([
            f"",
            f"## ELO Rankings",
            f"",
            f"| Rank | Document | ELO Rating |",
            f"|------|----------|------------|"
        ])
        for elo in chart["elo_rankings"][:10]:  # Top 10
            lines.append(f"| {elo['rank']} | `{elo['doc_id'][:40]}...` | {elo['elo_rating']:.1f} |")
    
    lines.extend([
        f"",
        f"## Summary",
        f"",
        f"- **Total Runs:** {chart['summary']['total_runs']}",
        f"- **Single Eval Rows:** {chart['summary']['total_single_rows']}",
        f"- **Pairwise Rows:** {chart['summary']['total_pairwise_rows']}",
        f"- **Judge Models:** {', '.join(chart['summary'].get('judge_models', []))}",
        f"- **Documents Evaluated:** {chart['summary'].get('documents_evaluated', 'N/A')}",
    ])
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
```

### HTML Table Export

```python
def export_chart_html(chart: Dict[str, Any], output_path: str) -> None:
    """Export chart as standalone HTML file."""
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Evaluation Run Chart</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background-color: #f8f9fa; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .success {{ color: #28a745; }}
        .empty {{ color: #dc3545; }}
        .summary {{ background: #e9ecef; padding: 15px; border-radius: 5px; margin: 20px 0; }}
    </style>
</head>
<body>
    <h1>Evaluation Run Chart</h1>
    <p><strong>Source:</strong> {chart['source']}</p>
    <p><strong>Run Period:</strong> {chart.get('run_start', 'N/A')} → {chart.get('run_end', 'N/A')}</p>
    
    <h2>Evaluation Runs</h2>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Phase</th>
                <th>Type</th>
                <th>Judge Model</th>
                <th>Docs</th>
                <th>Rows</th>
                <th>Duration</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
"""
    
    for i, run in enumerate(chart["runs"], 1):
        duration_mmss = format_duration(run["duration_seconds"])
        status_class = "success" if run["status"] == "success" else "empty"
        html += f"""            <tr>
                <td>{i}</td>
                <td>{run['phase']}</td>
                <td>{run['eval_type']}</td>
                <td>{run['judge_model']}</td>
                <td>{run['doc_count']}</td>
                <td>{run['row_count']}</td>
                <td>{duration_mmss}</td>
                <td class="{status_class}">{run['status']}</td>
            </tr>
"""
    
    html += f"""        </tbody>
    </table>
    
    <div class="summary">
        <h3>Summary</h3>
        <ul>
            <li><strong>Total Runs:</strong> {chart['summary']['total_runs']}</li>
            <li><strong>Single Eval Rows:</strong> {chart['summary']['total_single_rows']}</li>
            <li><strong>Pairwise Rows:</strong> {chart['summary']['total_pairwise_rows']}</li>
            <li><strong>Judge Models:</strong> {', '.join(chart['summary'].get('judge_models', []))}</li>
        </ul>
    </div>
</body>
</html>"""
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
```

---

## CLI Usage

```python
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate eval chart from CSV export files")
    parser.add_argument("--dir", required=True, help="Export directory containing CSV files")
    parser.add_argument("--dirs", nargs="+", help="Multiple export directories for unified chart")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--format", choices=["json", "markdown", "html"], default="json")
    parser.add_argument("--analyze", action="store_true", help="Include detailed score analysis")
    
    args = parser.parse_args()
    
    if args.dirs:
        chart = generate_unified_chart_from_csv_dirs(args.dirs)
    else:
        chart = generate_chart_from_csv_dir(args.dir)
    
    # Add score analysis if requested
    if args.analyze:
        csv_files = discover_csv_files(args.dir)
        if csv_files.get("single_doc"):
            chart["score_analysis"] = analyze_single_doc_scores(csv_files["single_doc"])
    
    if args.output:
        if args.format == "markdown":
            export_chart_markdown(chart, args.output)
        elif args.format == "html":
            export_chart_html(chart, args.output)
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
  "source": "csv_export",
  "export_directory": "gptr-eval-process/exports/eval_run_20251128_202442_569f1952",
  "csv_files": {
    "single_doc": "single_doc_results_20251128_202442_569f1952.csv",
    "pairwise": "pairwise_results_20251128_202442_569f1952.csv",
    "elo": "elo_summary_20251128_202442_569f1952.csv"
  },
  "phase": "eval",
  "run_start": "2025-11-28T12:24:43.028607",
  "run_end": "2025-11-28T12:33:07.322243",
  "runs": [
    {
      "phase": "eval-single-eval",
      "eval_type": "single",
      "judge_model": "openai_gpt-5.1",
      "doc_count": 6,
      "row_count": 24,
      "first_ts": "2025-11-28T12:24:43.028607",
      "last_ts": "2025-11-28T12:26:15.123456",
      "duration_seconds": 92.09,
      "status": "success"
    }
  ],
  "elo_rankings": [
    {"doc_id": "report.fpf.1.gemini.xyz.txt", "elo_rating": 1064.5, "rank": 1},
    {"doc_id": "report.gptr.1.gpt.abc.md", "elo_rating": 1032.2, "rank": 2}
  ],
  "summary": {
    "total_runs": 4,
    "single_eval_runs": 2,
    "pairwise_eval_runs": 2,
    "total_single_rows": 48,
    "total_pairwise_rows": 6,
    "judge_models": ["openai_gpt-5.1", "google_gemini-2.5-pro"],
    "documents_evaluated": 6
  }
}
```

---

## Comparison: CSV vs SQLite vs Config

| Aspect | Spec 1 (Config) | Spec 2 (Logs) | Spec 3 (SQLite) | Spec 4 (CSV) |
|--------|-----------------|---------------|-----------------|--------------|
| **When to Use** | Pre-run planning | Post-run with FPF logs | Post-run with DB access | Post-run with exports |
| **Data Freshness** | Expected/planned | Real-time during run | Final persisted | Exported snapshot |
| **Includes Costs** | Estimated | Actual FPF costs | No | No |
| **Includes Timing** | No | Yes (from logs) | Yes (from timestamps) | Yes (from timestamps) |
| **ELO Rankings** | No | No | Yes (calculated) | Yes (pre-calculated) |
| **Portability** | Requires config | Requires logs | Requires DB file | Just CSV files |
| **Best For** | Planning | Cost tracking | Full analysis | Sharing/archiving |
