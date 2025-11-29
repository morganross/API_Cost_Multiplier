# Evaluation Run Chart Specification (From Logs)

This document describes how to programmatically generate the evaluation run chart by **parsing FPF logs** rather than predicting from config.

---

## Why Parse Logs Instead of Config?

| Approach | Pros | Cons |
| :--- | :--- | :--- |
| **From Config** | Predictable, no execution needed | Doesn't reflect actual runs, failures, retries |
| **From Logs** | Ground truth, includes timing/cost | Requires completed run, more parsing |

**Recommendation:** Use logs for post-run reports; use config for pre-run planning.

---

## Log Sources

| Source | Path | Contains |
| :--- | :--- | :--- |
| **FPF Per-Run JSON** | `FilePromptForge/logs/*.json` | Individual API calls with full request/response |
| **FPF Grouped Logs** | `FilePromptForge/logs/<run_group_id>/*.json` | Same, grouped by eval batch |
| **Eval Copied Logs** | `api_cost_multiplier/logs/eval_fpf_logs/<type>_<ts>_<id>/` | Persistent copies of eval FPF logs |
| **ACM Session Log** | `api_cost_multiplier/logs/acm_session.log` | Timeline events, phase markers |
| **Eval Database** | `llm-doc-eval/llm_doc_eval/results_*.sqlite` | Evaluation results, scores, doc_ids |

---

## FPF Log JSON Schema (Key Fields for Chart)

```json
{
  "run_group_id": "abc123def456...",   // Links to eval batch (32-char UUID hex)
  "run_id": "e658ba02",                 // Unique run ID (8-char)
  "started_at": "2025-11-28T22:21:43.272589",
  "finished_at": "2025-11-28T22:22:19.157075",
  "model": "gemini-2.5-flash",
  "config": {
    "provider": "google",
    "model": "gemini-2.5-flash"
  },
  "request": {
    "contents": [
      {
        "parts": [
          {"text": "...prompt containing doc_id or criteria..."}
        ]
      }
    ]
  },
  "usage": {
    "prompt_tokens": 5655,
    "completion_tokens": 4665,
    "total_tokens": 20645
  },
  "total_cost_usd": 0.013359
}
```

---

## Chart Column Definitions

| Column | Source | Extraction Method |
| :--- | :--- | :--- |
| **Run #** | Derived | Sort by `started_at`, assign sequential number |
| **Phase** | Request text | Parse prompt for phase markers (see below) |
| **Judge Model** | `config.provider` + `config.model` | Direct field access |
| **Target** | Request text | Parse prompt for doc filename or pair labels |
| **Started** | `started_at` | Direct field access |
| **Duration** | `finished_at - started_at` | Calculate delta |
| **Tokens** | `usage.total_tokens` | Direct field access |
| **Cost** | `total_cost_usd` | Direct field access |
| **Status** | File exists vs failure- prefix | Check filename pattern |

---

## Phase Detection Logic

Parse the FPF request prompt text to identify the evaluation phase:

```python
def detect_phase(prompt_text: str, run_group_context: dict) -> str:
    """
    Detect evaluation phase from prompt content.
    
    Args:
        prompt_text: The full prompt text from FPF request
        run_group_context: Context about run groups (from ACM log parsing)
    
    Returns:
        Phase label string
    """
    prompt_lower = prompt_text.lower()
    
    # Check for pairwise markers
    if "document a" in prompt_lower and "document b" in prompt_lower:
        if run_group_context.get("is_postcombine"):
            return "postcombine-pairwise-eval"
        return "precombine-pairwise-eval"
    
    # Check for combiner generation (not eval)
    if "gold standard" in prompt_lower or "combine" in prompt_lower:
        if "report a" in prompt_lower and "report b" in prompt_lower:
            return "combiner-generation"
    
    # Single doc eval (default for eval runs)
    if "evaluate" in prompt_lower or "criteria" in prompt_lower:
        # Detect pre vs post combine from run_group timing
        if run_group_context.get("is_postcombine"):
            return "postcombine-single-eval"
        return "precombine-single-eval"
    
    # Generation runs (not eval)
    return "generation"
```

---

## Target Extraction Logic

```python
import re

def extract_target(prompt_text: str, phase: str) -> str:
    """
    Extract the target document(s) being evaluated.
    
    Args:
        prompt_text: The full prompt text
        phase: The detected phase
    
    Returns:
        Target description string
    """
    if "pairwise" in phase:
        # Look for document labels
        # Pattern: filenames like "doc.fpf.1.model.uid.txt"
        files = re.findall(r'[\w\-]+\.(?:fpf|gptr|dr|ma|CR)\.\d+\.[\w\-]+\.[a-z0-9]+\.(?:md|txt)', prompt_text)
        if len(files) >= 2:
            return f"{files[0]} vs {files[1]}"
        return "Pair (files not parsed)"
    
    elif phase == "combiner-generation":
        return "Combine Top Reports → New Doc"
    
    else:
        # Single doc - find filename
        files = re.findall(r'[\w\-]+\.(?:fpf|gptr|dr|ma|CR)\.\d+\.[\w\-]+\.[a-z0-9]+\.(?:md|txt)', prompt_text)
        if files:
            return files[0]
        
        # Fallback: look for any .md or .txt
        files = re.findall(r'[\w\-]+\.(?:md|txt)', prompt_text)
        if files:
            return files[0]
        
        return "Unknown target"
```

---

## Run Group Context Detection

```python
def build_run_group_context(acm_log_path: str) -> dict:
    """
    Parse ACM session log to build context about run groups.
    
    Returns dict mapping run_group_id to metadata:
    {
        "abc123...": {
            "is_postcombine": False,
            "phase_hint": "precombine-single-eval",
            "started_at": datetime,
        },
        ...
    }
    """
    import re
    from datetime import datetime
    
    context = {}
    current_phase = "precombine"
    
    with open(acm_log_path, "r", encoding="utf-8") as f:
        for line in f:
            # Detect combiner trigger
            if "TRIGGERING PLAYOFFS EVALUATION" in line or "is_combined_run=True" in line:
                current_phase = "postcombine"
            
            # Detect run group start
            match = re.search(r'\[EVAL_SINGLE_START\] id=([a-f0-9]+)', line)
            if match:
                gid = match.group(1)
                context[gid] = {
                    "is_postcombine": current_phase == "postcombine",
                    "phase_hint": f"{current_phase}-single-eval",
                }
            
            match = re.search(r'\[EVAL_PAIRWISE_START\] id=([a-f0-9]+)', line)
            if match:
                gid = match.group(1)
                context[gid] = {
                    "is_postcombine": current_phase == "postcombine",
                    "phase_hint": f"{current_phase}-pairwise-eval",
                }
    
    return context
```

---

## Complete Chart Generation Script

```python
#!/usr/bin/env python3
"""
Generate Evaluation Run Chart from FPF Logs

Usage:
    python generate_eval_chart.py --fpf-logs FilePromptForge/logs --acm-log logs/acm_session.log
"""

import os
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class EvalRun:
    """Represents a single evaluation run."""
    run_num: int
    phase: str
    judge_model: str
    target: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    total_tokens: int
    total_cost_usd: float
    status: str
    run_id: str
    run_group_id: str
    file_path: str


def parse_fpf_log(file_path: str) -> Optional[Dict[str, Any]]:
    """Parse a single FPF JSON log file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def collect_fpf_logs(log_dir: str) -> List[Dict[str, Any]]:
    """Collect all FPF JSON logs from directory."""
    logs = []
    log_path = Path(log_dir)
    
    for root, dirs, files in os.walk(log_path):
        for filename in files:
            if not filename.endswith(".json"):
                continue
            if filename.startswith("failure-"):
                continue
            
            file_path = os.path.join(root, filename)
            data = parse_fpf_log(file_path)
            if data:
                data["_file_path"] = file_path
                logs.append(data)
    
    return logs


def extract_prompt_text(log_data: Dict[str, Any]) -> str:
    """Extract prompt text from FPF log request."""
    request = log_data.get("request") or {}
    contents = request.get("contents") or []
    
    texts = []
    for content in contents:
        parts = content.get("parts") or []
        for part in parts:
            if isinstance(part, dict) and "text" in part:
                texts.append(part["text"])
    
    return "\n".join(texts)


def build_eval_run(
    log_data: Dict[str, Any],
    run_num: int,
    run_group_context: Dict[str, Any]
) -> EvalRun:
    """Build EvalRun from FPF log data."""
    
    # Extract basic fields
    config = log_data.get("config") or {}
    usage = log_data.get("usage") or {}
    run_group_id = log_data.get("run_group_id") or ""
    
    # Parse timestamps
    started = datetime.fromisoformat(log_data.get("started_at", "1970-01-01"))
    finished = datetime.fromisoformat(log_data.get("finished_at", "1970-01-01"))
    duration = (finished - started).total_seconds()
    
    # Get judge model
    provider = config.get("provider", "unknown")
    model = log_data.get("model") or config.get("model", "unknown")
    judge_model = f"{provider}:{model}"
    
    # Extract prompt and detect phase/target
    prompt_text = extract_prompt_text(log_data)
    group_ctx = run_group_context.get(run_group_id, {})
    
    phase = detect_phase(prompt_text, group_ctx)
    target = extract_target(prompt_text, phase)
    
    return EvalRun(
        run_num=run_num,
        phase=phase,
        judge_model=judge_model,
        target=target,
        started_at=started,
        finished_at=finished,
        duration_seconds=duration,
        total_tokens=usage.get("total_tokens", 0),
        total_cost_usd=log_data.get("total_cost_usd", 0.0) or 0.0,
        status="success",
        run_id=log_data.get("run_id", "unknown"),
        run_group_id=run_group_id,
        file_path=log_data.get("_file_path", ""),
    )


def generate_chart(
    fpf_log_dir: str,
    acm_log_path: Optional[str] = None,
    time_start: Optional[datetime] = None,
    time_end: Optional[datetime] = None,
) -> List[EvalRun]:
    """
    Generate evaluation run chart from FPF logs.
    
    Args:
        fpf_log_dir: Path to FilePromptForge/logs
        acm_log_path: Optional path to ACM session log for context
        time_start: Optional filter start time
        time_end: Optional filter end time
    
    Returns:
        List of EvalRun objects sorted by start time
    """
    # Build run group context from ACM log
    run_group_context = {}
    if acm_log_path and os.path.exists(acm_log_path):
        run_group_context = build_run_group_context(acm_log_path)
    
    # Collect and parse FPF logs
    logs = collect_fpf_logs(fpf_log_dir)
    
    # Filter by time if specified
    if time_start or time_end:
        filtered = []
        for log in logs:
            started = datetime.fromisoformat(log.get("started_at", "1970-01-01"))
            if time_start and started < time_start:
                continue
            if time_end and started > time_end:
                continue
            filtered.append(log)
        logs = filtered
    
    # Sort by start time
    logs.sort(key=lambda x: x.get("started_at", ""))
    
    # Build EvalRun objects
    runs = []
    for i, log_data in enumerate(logs, start=1):
        run = build_eval_run(log_data, i, run_group_context)
        runs.append(run)
    
    return runs


def format_chart_markdown(runs: List[EvalRun]) -> str:
    """Format runs as Markdown table."""
    lines = [
        "| Run # | Phase | Judge Model | Target | Duration | Tokens | Cost |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    
    current_phase = None
    for run in runs:
        # Add phase separator
        if run.phase != current_phase:
            current_phase = run.phase
            lines.append(f"| | **{current_phase.upper()}** | | | | | |")
        
        lines.append(
            f"| **{run.run_num}** | `{run.phase}` | `{run.judge_model}` | "
            f"{run.target[:40]}{'...' if len(run.target) > 40 else ''} | "
            f"{run.duration_seconds:.1f}s | {run.total_tokens:,} | "
            f"${run.total_cost_usd:.4f} |"
        )
    
    # Summary
    total_cost = sum(r.total_cost_usd for r in runs)
    total_tokens = sum(r.total_tokens for r in runs)
    total_duration = sum(r.duration_seconds for r in runs)
    
    lines.append("")
    lines.append("**Summary:**")
    lines.append(f"- Total Runs: {len(runs)}")
    lines.append(f"- Total Cost: ${total_cost:.4f}")
    lines.append(f"- Total Tokens: {total_tokens:,}")
    lines.append(f"- Total Duration: {total_duration:.1f}s ({total_duration/60:.1f} min)")
    
    return "\n".join(lines)


def format_chart_json(runs: List[EvalRun]) -> str:
    """Format runs as JSON."""
    data = {
        "runs": [
            {
                "run_num": r.run_num,
                "phase": r.phase,
                "judge_model": r.judge_model,
                "target": r.target,
                "started_at": r.started_at.isoformat(),
                "finished_at": r.finished_at.isoformat(),
                "duration_seconds": r.duration_seconds,
                "total_tokens": r.total_tokens,
                "total_cost_usd": r.total_cost_usd,
                "status": r.status,
                "run_id": r.run_id,
                "run_group_id": r.run_group_id,
            }
            for r in runs
        ],
        "summary": {
            "total_runs": len(runs),
            "total_cost_usd": sum(r.total_cost_usd for r in runs),
            "total_tokens": sum(r.total_tokens for r in runs),
            "total_duration_seconds": sum(r.duration_seconds for r in runs),
            "by_phase": {},
        }
    }
    
    # Group by phase
    for run in runs:
        phase = run.phase
        if phase not in data["summary"]["by_phase"]:
            data["summary"]["by_phase"][phase] = {"count": 0, "cost": 0.0, "tokens": 0}
        data["summary"]["by_phase"][phase]["count"] += 1
        data["summary"]["by_phase"][phase]["cost"] += run.total_cost_usd
        data["summary"]["by_phase"][phase]["tokens"] += run.total_tokens
    
    return json.dumps(data, indent=2)


# ============================================================================
# Helper functions (from earlier in this spec)
# ============================================================================

def detect_phase(prompt_text: str, run_group_context: dict) -> str:
    """Detect evaluation phase from prompt content."""
    prompt_lower = prompt_text.lower()
    
    if "document a" in prompt_lower and "document b" in prompt_lower:
        if run_group_context.get("is_postcombine"):
            return "postcombine-pairwise-eval"
        return "precombine-pairwise-eval"
    
    if "gold standard" in prompt_lower or "combine" in prompt_lower:
        if "report a" in prompt_lower and "report b" in prompt_lower:
            return "combiner-generation"
    
    if "evaluate" in prompt_lower or "criteria" in prompt_lower:
        if run_group_context.get("is_postcombine"):
            return "postcombine-single-eval"
        return "precombine-single-eval"
    
    return "generation"


def extract_target(prompt_text: str, phase: str) -> str:
    """Extract the target document(s) being evaluated."""
    import re
    
    if "pairwise" in phase:
        files = re.findall(
            r'[\w\-]+\.(?:fpf|gptr|dr|ma|CR)\.\d+\.[\w\-]+\.[a-z0-9]+\.(?:md|txt)',
            prompt_text
        )
        if len(files) >= 2:
            return f"{files[0]} vs {files[1]}"
        return "Pair (files not parsed)"
    
    elif phase == "combiner-generation":
        return "Combine Top Reports → New Doc"
    
    else:
        files = re.findall(
            r'[\w\-]+\.(?:fpf|gptr|dr|ma|CR)\.\d+\.[\w\-]+\.[a-z0-9]+\.(?:md|txt)',
            prompt_text
        )
        if files:
            return files[0]
        files = re.findall(r'[\w\-]+\.(?:md|txt)', prompt_text)
        if files:
            return files[0]
        return "Unknown target"


def build_run_group_context(acm_log_path: str) -> dict:
    """Parse ACM session log to build context about run groups."""
    import re
    
    context = {}
    current_phase = "precombine"
    
    try:
        with open(acm_log_path, "r", encoding="utf-8") as f:
            for line in f:
                if "TRIGGERING PLAYOFFS EVALUATION" in line or "is_combined_run=True" in line:
                    current_phase = "postcombine"
                
                match = re.search(r'\[EVAL_SINGLE_START\] id=([a-f0-9]+)', line)
                if match:
                    gid = match.group(1)
                    context[gid] = {
                        "is_postcombine": current_phase == "postcombine",
                        "phase_hint": f"{current_phase}-single-eval",
                    }
                
                match = re.search(r'\[EVAL_PAIRWISE_START\] id=([a-f0-9]+)', line)
                if match:
                    gid = match.group(1)
                    context[gid] = {
                        "is_postcombine": current_phase == "postcombine",
                        "phase_hint": f"{current_phase}-pairwise-eval",
                    }
    except Exception:
        pass
    
    return context


# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Eval Run Chart from FPF Logs")
    parser.add_argument("--fpf-logs", required=True, help="Path to FilePromptForge/logs")
    parser.add_argument("--acm-log", help="Path to ACM session log")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    args = parser.parse_args()
    
    runs = generate_chart(args.fpf_logs, args.acm_log)
    
    if args.format == "json":
        output = format_chart_json(runs)
    else:
        output = format_chart_markdown(runs)
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Chart written to {args.output}")
    else:
        print(output)
```

---

## Output Formats

### Markdown Table

```markdown
| Run # | Phase | Judge Model | Target | Duration | Tokens | Cost |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| | **PRECOMBINE-SINGLE-EVAL** | | | | | |
| **1** | `precombine-single-eval` | `google:gemini-2.5-flash` | doc.fpf.1.gemini-2.5-flash.abc.txt | 12.3s | 5,432 | $0.0134 |
| **2** | `precombine-single-eval` | `google:gemini-2.5-flash` | doc.fpf.1.gpt-5-mini.def.txt | 8.7s | 4,211 | $0.0098 |
...
```

### JSON

```json
{
  "runs": [
    {
      "run_num": 1,
      "phase": "precombine-single-eval",
      "judge_model": "google:gemini-2.5-flash",
      "target": "doc.fpf.1.gemini-2.5-flash.abc.txt",
      "started_at": "2025-11-28T22:21:43",
      "finished_at": "2025-11-28T22:21:55",
      "duration_seconds": 12.3,
      "total_tokens": 5432,
      "total_cost_usd": 0.0134,
      "status": "success",
      "run_id": "abc12345",
      "run_group_id": "def67890..."
    }
  ],
  "summary": {
    "total_runs": 34,
    "total_cost_usd": 0.4523,
    "total_tokens": 145678,
    "total_duration_seconds": 423.5,
    "by_phase": {
      "precombine-single-eval": {"count": 12, "cost": 0.15, "tokens": 50000},
      "precombine-pairwise-eval": {"count": 6, "cost": 0.08, "tokens": 25000},
      ...
    }
  }
}
```

---

## Usage Examples

```bash
# Generate Markdown chart from most recent run
python tools/generate_eval_chart.py \
    --fpf-logs FilePromptForge/logs \
    --acm-log logs/acm_session.log \
    --format markdown

# Generate JSON for programmatic use
python tools/generate_eval_chart.py \
    --fpf-logs FilePromptForge/logs \
    --acm-log logs/acm_session.log \
    --format json \
    --output eval_chart.json

# Parse specific eval batch logs
python tools/generate_eval_chart.py \
    --fpf-logs logs/eval_fpf_logs/single_20251128_123456_abc12345 \
    --format markdown
```

---

## Integration with HTML Report

The JSON output can be embedded in the unified HTML report:

```python
# In reporting/html_exporter.py
from tools.generate_eval_chart import generate_chart, format_chart_json

def generate_unified_html_report(..., fpf_log_dir=None, acm_log_path=None):
    # Generate eval run chart
    if fpf_log_dir:
        runs = generate_chart(fpf_log_dir, acm_log_path)
        eval_chart_json = format_chart_json(runs)
        # Embed in HTML template
        ...
```
