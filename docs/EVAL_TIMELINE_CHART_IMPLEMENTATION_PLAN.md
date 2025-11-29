# Evaluation Timeline Chart Implementation Plan

**Date:** November 29, 2025  
**Feature:** Unified Eval Timeline Chart in HTML Report  
**Status:** Planning

---

## Overview

Add a new "Evaluation Timeline Chart" section to the HTML report generator that displays a comprehensive view of all evaluation runs. The chart correlates **expected runs** (from config) with **actual execution data** (from logs, database, and CSV files) in a multi-column table with phase separators, subtotals, and grand totals.

---

## Chart Design

### Visual Layout

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    EVALUATION TIMELINE CHART                                                 │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                             │
│  ┌─── EXPECTED (Config) ───┬─── ACTUAL (Logs) ───┬─── DB Results ───┬─── Costs ───┬─── Status ───┐         │
│  │ # │ Phase │ Target      │ Start │ End │ Dur   │ Rows │ First │Last│ Tokens│Cost │ Match │ Δ   │         │
│  ├───┼───────┼─────────────┼───────┼─────┼───────┼──────┼───────┼────┼───────┼─────┼───────┼─────┤         │
│  │   │ PHASE 1: PRECOMBINE-SINGLE-EVAL                                                          │         │
│  ├───┼───────┼─────────────┼───────┼─────┼───────┼──────┼───────┼────┼───────┼─────┼───────┼─────┤         │
│  │ 1 │ pre-s │ doc1.fpf... │ 12:24 │12:25│ 00:45 │  4   │ 12:24 │12:25│ 5432 │$0.01│   ✓   │ +2s │         │
│  │ 2 │ pre-s │ doc2.gptr...│ 12:25 │12:26│ 00:52 │  4   │ 12:25 │12:26│ 4211 │$0.01│   ✓   │ -1s │         │
│  │...│  ...  │    ...      │  ...  │ ... │  ...  │ ...  │  ...  │ ...│  ... │ ... │  ...  │ ... │         │
│  ├───┴───────┴─────────────┴───────┴─────┴───────┴──────┴───────┴────┴───────┴─────┴───────┴─────┤         │
│  │ SUBTOTAL Phase 1:  12 runs │ Total: 08:32 │ 48 rows │           │ 52,341 │$0.15│ 12/12 │     │         │
│  ├───────────────────────────────────────────────────────────────────────────────────────────────┤         │
│  │   │ PHASE 2: PRECOMBINE-PAIRWISE-EVAL                                                        │         │
│  ├───┼───────┼─────────────┼───────┼─────┼───────┼──────┼───────┼────┼───────┼─────┼───────┼─────┤         │
│  │13 │ pre-p │ Top1 vs Top2│ 12:33 │12:34│ 01:12 │  1   │ 12:33 │12:34│ 8234 │$0.02│   ✓   │ +5s │         │
│  │...│  ...  │    ...      │  ...  │ ... │  ...  │ ...  │  ...  │ ...│  ... │ ... │  ...  │ ... │         │
│  ├───┴───────┴─────────────┴───────┴─────┴───────┴──────┴───────┴────┴───────┴─────┴───────┴─────┤         │
│  │ SUBTOTAL Phase 2:   6 runs │ Total: 04:15 │  6 rows │           │ 31,202 │$0.08│  6/6  │     │         │
│  ├───────────────────────────────────────────────────────────────────────────────────────────────┤         │
│  │                              ... more phases ...                                              │         │
│  ├───────────────────────────────────────────────────────────────────────────────────────────────┤         │
│  │ GRAND TOTAL:        34 runs │ Total: 28:45 │ 108 rows│           │145,678 │$0.45│ 34/34 │     │         │
│  └───────────────────────────────────────────────────────────────────────────────────────────────┘         │
│                                                                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Column Definitions

| Column Group | Column | Source | Description |
|--------------|--------|--------|-------------|
| **Expected (Config)** | # | Derived | Sequential run number |
| | Phase | `config.yaml` | Phase identifier (pre-single, pre-pairwise, combiner, post-single, post-pairwise) |
| | Judge | `llm-doc-eval/config.yaml` | Judge model ID |
| | Target | `config.yaml` | Document or pair being evaluated |
| **Actual (Logs)** | Log Start | FPF JSON logs | `started_at` from FPF log |
| | Log End | FPF JSON logs | `finished_at` from FPF log |
| | Log Duration | FPF JSON logs | `finished_at - started_at` |
| **DB Results** | DB Rows | SQLite DB | Count of rows matching this run |
| | DB First | SQLite DB | `MIN(timestamp)` for this judge+doc |
| | DB Last | SQLite DB | `MAX(timestamp)` for this judge+doc |
| | DB Duration | SQLite DB | `MAX(timestamp) - MIN(timestamp)` |
| **Costs** | Tokens | FPF JSON logs | `usage.total_tokens` |
| | Cost USD | FPF JSON logs | `total_cost_usd` |
| **Status** | Match | Derived | ✓ if expected run found in actuals |
| | Δ (Delta) | Derived | Time difference: Log Duration - DB Duration |

---

## Data Sources

### 1. Expected Runs (from Config) - SPEC 1

**Files:**
- `api_cost_multiplier/config.yaml` - Main config with `runs[]`, `combine.models[]`, `eval.pairwise_top_n`
- `llm-doc-eval/config.yaml` - Judge models in `models` section

**Extraction:**
```python
# Phase 1: Pre-combine Single Eval
for judge in judges:
    for run in config["runs"]:
        yield ExpectedRun(phase="precombine-single-eval", judge=judge, target=run)

# Phase 2: Pre-combine Pairwise Eval  
for judge in judges:
    for (i, j) in combinations(range(1, pairwise_top_n + 1), 2):
        yield ExpectedRun(phase="precombine-pairwise-eval", judge=judge, target=f"Top#{i} vs Top#{j}")

# Phase 3: Combiner Generation
for cm in combine_models:
    yield ExpectedRun(phase="combiner-generation", judge=cm, target="Combine Top Reports")

# Phase 4: Post-combine Single Eval
for judge in judges:
    for target in (top_2_old + combined_new):
        yield ExpectedRun(phase="postcombine-single-eval", judge=judge, target=target)

# Phase 5: Post-combine Pairwise Eval
for judge in judges:
    for (i, j) in combinations(range(1, min(pairwise_top_n, pool_size) + 1), 2):
        yield ExpectedRun(phase="postcombine-pairwise-eval", judge=judge, target=f"Post Top#{i} vs Top#{j}")
```

### 2. Actual Runs (from FPF Logs) - SPEC 2

**Files:**
- `FilePromptForge/logs/<run_group_id>/*.json` - Individual FPF call logs
- `api_cost_multiplier/logs/eval_fpf_logs/<type>_<ts>_<id>/` - Persistent copies

**Fields Extracted:**
```python
{
    "started_at": "2025-11-28T12:24:43.028607",
    "finished_at": "2025-11-28T12:25:28.123456",
    "model": "gemini-2.5-flash",
    "config.provider": "google",
    "usage.total_tokens": 5432,
    "total_cost_usd": 0.0134,
    "run_group_id": "abc123...",
    "run_id": "e658ba02"
}
```

### 3. DB Results (from SQLite) - SPEC 3

**File:** `llm-doc-eval/llm_doc_eval/results_*.sqlite`

**Queries:**
```sql
-- For single-doc runs
SELECT 
    doc_id, model,
    COUNT(*) as row_count,
    MIN(timestamp) as first_ts,
    MAX(timestamp) as last_ts
FROM single_doc_results
GROUP BY doc_id, model;

-- For pairwise runs
SELECT 
    doc_id_1, doc_id_2, model,
    COUNT(*) as row_count,
    MIN(timestamp) as first_ts,
    MAX(timestamp) as last_ts
FROM pairwise_results
GROUP BY doc_id_1, doc_id_2, model;
```

### 4. CSV Data (Optional Fallback) - SPEC 4

**Files:**
- `exports/eval_run_*/single_doc_results_*.csv`
- `exports/eval_run_*/pairwise_results_*.csv`
- `exports/eval_run_*/elo_summary_*.csv`

Used when database is not available or for archived runs.

---

## Implementation Plan

### Phase 1: Create Data Aggregator Module

**New File:** `api_cost_multiplier/tools/eval_timeline_aggregator.py`

```python
"""
Aggregates evaluation timeline data from multiple sources:
- Config files (expected runs)
- FPF logs (actual execution)
- SQLite database (results)
- CSV exports (fallback)
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum


class EvalPhase(Enum):
    PRECOMBINE_SINGLE = "precombine-single-eval"
    PRECOMBINE_PAIRWISE = "precombine-pairwise-eval"
    COMBINER = "combiner-generation"
    POSTCOMBINE_SINGLE = "postcombine-single-eval"
    POSTCOMBINE_PAIRWISE = "postcombine-pairwise-eval"


@dataclass
class ExpectedRun:
    """Expected run from config files."""
    run_num: int
    phase: EvalPhase
    judge_model: str
    target: str  # doc_id or pair description


@dataclass
class ActualRunLog:
    """Actual run data from FPF logs."""
    run_id: str
    run_group_id: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    total_tokens: int
    total_cost_usd: float
    model: str
    provider: str


@dataclass
class DbRunResult:
    """Run results from database."""
    row_count: int
    first_timestamp: datetime
    last_timestamp: datetime
    duration_seconds: float


@dataclass
class TimelineRow:
    """Complete timeline row combining all sources."""
    # Expected (from config)
    run_num: int
    phase: str
    phase_display: str  # Short display name
    judge_model: str
    target: str
    target_short: str  # Truncated for display
    
    # Actual (from logs)
    log_start: Optional[str]
    log_end: Optional[str]
    log_duration_seconds: Optional[float]
    log_duration_display: str
    
    # DB results
    db_row_count: int
    db_first_ts: Optional[str]
    db_last_ts: Optional[str]
    db_duration_seconds: Optional[float]
    db_duration_display: str
    
    # Costs
    total_tokens: int
    total_cost_usd: float
    
    # Status
    matched: bool  # Expected run found in actual
    delta_seconds: Optional[float]  # Log duration - DB duration
    delta_display: str
    status_icon: str  # ✓, ⚠, ✗


@dataclass
class PhaseSubtotal:
    """Subtotal for a phase."""
    phase: str
    phase_display: str
    run_count: int
    total_duration_seconds: float
    total_duration_display: str
    total_db_rows: int
    total_tokens: int
    total_cost_usd: float
    matched_count: int
    expected_count: int


@dataclass
class TimelineChart:
    """Complete timeline chart data."""
    rows: List[TimelineRow]
    phase_subtotals: List[PhaseSubtotal]
    grand_total: PhaseSubtotal
    run_start: Optional[str]
    run_end: Optional[str]
    sources: Dict[str, str]  # Source file paths


class EvalTimelineAggregator:
    """Main aggregator class."""
    
    def __init__(
        self,
        config_path: str,
        eval_config_path: str,
        db_path: Optional[str] = None,
        fpf_logs_dir: Optional[str] = None,
        csv_export_dir: Optional[str] = None,
        acm_log_path: Optional[str] = None,
    ):
        self.config_path = config_path
        self.eval_config_path = eval_config_path
        self.db_path = db_path
        self.fpf_logs_dir = fpf_logs_dir
        self.csv_export_dir = csv_export_dir
        self.acm_log_path = acm_log_path
    
    def generate_expected_runs(self) -> List[ExpectedRun]:
        """Generate expected runs from config files (SPEC 1)."""
        # Implementation from SPEC 1
        ...
    
    def parse_fpf_logs(self) -> Dict[str, ActualRunLog]:
        """Parse FPF logs for actual execution data (SPEC 2)."""
        # Implementation from SPEC 2
        ...
    
    def query_db_results(self) -> Dict[str, DbRunResult]:
        """Query database for result data (SPEC 3)."""
        # Implementation from SPEC 3
        ...
    
    def load_csv_fallback(self) -> Dict[str, DbRunResult]:
        """Load CSV data as fallback (SPEC 4)."""
        # Implementation from SPEC 4
        ...
    
    def match_expected_to_actual(
        self,
        expected: List[ExpectedRun],
        actual_logs: Dict[str, ActualRunLog],
        db_results: Dict[str, DbRunResult],
    ) -> List[TimelineRow]:
        """Match expected runs to actual execution data."""
        ...
    
    def calculate_subtotals(
        self,
        rows: List[TimelineRow]
    ) -> List[PhaseSubtotal]:
        """Calculate subtotals by phase."""
        ...
    
    def generate_chart(self) -> TimelineChart:
        """Generate complete timeline chart."""
        expected = self.generate_expected_runs()
        actual_logs = self.parse_fpf_logs()
        db_results = self.query_db_results() or self.load_csv_fallback()
        
        rows = self.match_expected_to_actual(expected, actual_logs, db_results)
        subtotals = self.calculate_subtotals(rows)
        grand_total = self._calculate_grand_total(subtotals)
        
        return TimelineChart(
            rows=rows,
            phase_subtotals=subtotals,
            grand_total=grand_total,
            run_start=...,
            run_end=...,
            sources={...}
        )
```

### Phase 2: Update HTML Exporter

**File:** `api_cost_multiplier/llm-doc-eval/reporting/html_exporter.py`

**Add new function:**

```python
def generate_eval_timeline_chart_section(chart: TimelineChart) -> str:
    """
    Generate HTML for the unified evaluation timeline chart.
    
    Features:
    - Multi-column table with all data sources
    - Phase separator rows with subtotals
    - Color-coded status indicators
    - Grand total footer
    - Collapsible detail rows (optional)
    """
    
    css = """
    <style>
        .timeline-chart { width: 100%; border-collapse: collapse; font-size: 0.85em; }
        .timeline-chart th { 
            background: #343a40; color: white; padding: 8px; 
            position: sticky; top: 0; z-index: 10;
        }
        .timeline-chart td { padding: 6px 8px; border-bottom: 1px solid #dee2e6; }
        .timeline-chart tr:hover { background: #f8f9fa; }
        
        /* Column groups */
        .col-expected { background: #e3f2fd; }
        .col-logs { background: #fff3e0; }
        .col-db { background: #e8f5e9; }
        .col-costs { background: #fce4ec; }
        .col-status { background: #f3e5f5; }
        
        /* Phase separator */
        .phase-header { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; font-weight: bold; 
        }
        .phase-subtotal { 
            background: #e9ecef; font-weight: bold; 
            border-top: 2px solid #6c757d;
        }
        .grand-total { 
            background: #343a40; color: white; font-weight: bold;
            font-size: 1.1em;
        }
        
        /* Status icons */
        .status-ok { color: #28a745; }
        .status-warn { color: #ffc107; }
        .status-error { color: #dc3545; }
        .status-missing { color: #6c757d; }
        
        /* Duration bars */
        .duration-bar { 
            height: 4px; background: #17a2b8; 
            border-radius: 2px; margin-top: 2px;
        }
    </style>
    """
    
    # Build table HTML
    html_parts = [css, '<h2>Evaluation Timeline Chart</h2>']
    
    # Header row
    html_parts.append('''
    <table class="timeline-chart">
    <thead>
        <tr>
            <th colspan="4" class="col-expected">Expected (Config)</th>
            <th colspan="3" class="col-logs">Actual (Logs)</th>
            <th colspan="4" class="col-db">DB Results</th>
            <th colspan="2" class="col-costs">Costs</th>
            <th colspan="2" class="col-status">Status</th>
        </tr>
        <tr>
            <th>#</th>
            <th>Phase</th>
            <th>Judge</th>
            <th>Target</th>
            <th>Start</th>
            <th>End</th>
            <th>Duration</th>
            <th>Rows</th>
            <th>First</th>
            <th>Last</th>
            <th>Duration</th>
            <th>Tokens</th>
            <th>Cost</th>
            <th>Match</th>
            <th>Δ</th>
        </tr>
    </thead>
    <tbody>
    ''')
    
    # Render rows with phase separators
    current_phase = None
    for row in chart.rows:
        if row.phase != current_phase:
            # Phase header
            current_phase = row.phase
            html_parts.append(f'''
            <tr class="phase-header">
                <td colspan="15">{row.phase_display}</td>
            </tr>
            ''')
        
        # Data row
        html_parts.append(_render_timeline_row(row))
        
        # Check for phase subtotal
        subtotal = _find_subtotal(chart.phase_subtotals, row.phase)
        if _is_last_in_phase(chart.rows, row):
            html_parts.append(_render_subtotal_row(subtotal))
    
    # Grand total
    html_parts.append(_render_grand_total_row(chart.grand_total))
    
    html_parts.append('</tbody></table>')
    
    return '\n'.join(html_parts)
```

### Phase 3: Integration Points

**File:** `api_cost_multiplier/evaluate.py`

Update to generate timeline chart at end of evaluation:

```python
# After evaluation completes, generate timeline chart
from tools.eval_timeline_aggregator import EvalTimelineAggregator

aggregator = EvalTimelineAggregator(
    config_path=config_path,
    eval_config_path=eval_config_path,
    db_path=db_path,
    fpf_logs_dir=fpf_logs_dir,
    acm_log_path=acm_log_path,
)

timeline_chart = aggregator.generate_chart()
timeline_chart_json = asdict(timeline_chart)

# Pass to HTML generator
generate_html_report(
    ...,
    timeline_chart=timeline_chart,
)
```

**File:** `api_cost_multiplier/runner.py`

Update to pass all required paths to evaluation:

```python
# Collect paths for timeline chart
timeline_sources = {
    "config_path": config_path,
    "eval_config_path": eval_config_path,
    "db_path": db_path,
    "fpf_logs_dir": fpf_logs_dir,
    "acm_log_path": acm_log_path,
    "csv_export_dir": export_dir,
}
```

---

## File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `tools/eval_timeline_aggregator.py` | **NEW** | Main aggregator combining all data sources |
| `tools/expected_runs_generator.py` | **NEW** | Generate expected runs from config (extracted from SPEC 1) |
| `reporting/html_exporter.py` | **MODIFY** | Add `generate_eval_timeline_chart_section()` |
| `evaluate.py` | **MODIFY** | Instantiate aggregator, pass chart to HTML generator |
| `runner.py` | **MODIFY** | Collect and pass source paths |
| `regenerate_report.py` | **MODIFY** | Support timeline chart regeneration |

---

## CSS Styling

```css
/* Timeline Chart Styles */
.eval-timeline-section {
    margin: 30px 0;
    overflow-x: auto;
}

.timeline-chart {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85em;
    white-space: nowrap;
}

/* Column group backgrounds */
.timeline-chart th.grp-expected,
.timeline-chart td.grp-expected { background: #e3f2fd; }

.timeline-chart th.grp-logs,
.timeline-chart td.grp-logs { background: #fff3e0; }

.timeline-chart th.grp-db,
.timeline-chart td.grp-db { background: #e8f5e9; }

.timeline-chart th.grp-costs,
.timeline-chart td.grp-costs { background: #fce4ec; }

.timeline-chart th.grp-status,
.timeline-chart td.grp-status { background: #f3e5f5; }

/* Phase rows */
.phase-row-precombine-single { border-left: 4px solid #28a745; }
.phase-row-precombine-pairwise { border-left: 4px solid #17a2b8; }
.phase-row-combiner { border-left: 4px solid #ffc107; }
.phase-row-postcombine-single { border-left: 4px solid #6f42c1; }
.phase-row-postcombine-pairwise { border-left: 4px solid #fd7e14; }

/* Status indicators */
.status-matched { color: #28a745; font-weight: bold; }
.status-missing { color: #dc3545; font-weight: bold; }
.status-partial { color: #ffc107; font-weight: bold; }

/* Duration visual bar */
.duration-visual {
    width: 100%;
    height: 4px;
    background: #e9ecef;
    border-radius: 2px;
    overflow: hidden;
}
.duration-visual .bar {
    height: 100%;
    background: linear-gradient(90deg, #28a745, #17a2b8);
}

/* Subtotal and total rows */
.subtotal-row {
    background: #e9ecef !important;
    font-weight: bold;
    border-top: 2px solid #adb5bd;
}
.grand-total-row {
    background: #343a40 !important;
    color: white;
    font-weight: bold;
    font-size: 1.05em;
}
```

---

## JSON Schema for Timeline Chart

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "EvalTimelineChart",
  "type": "object",
  "properties": {
    "rows": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "run_num": {"type": "integer"},
          "phase": {"type": "string"},
          "phase_display": {"type": "string"},
          "judge_model": {"type": "string"},
          "target": {"type": "string"},
          "target_short": {"type": "string"},
          "log_start": {"type": ["string", "null"]},
          "log_end": {"type": ["string", "null"]},
          "log_duration_seconds": {"type": ["number", "null"]},
          "log_duration_display": {"type": "string"},
          "db_row_count": {"type": "integer"},
          "db_first_ts": {"type": ["string", "null"]},
          "db_last_ts": {"type": ["string", "null"]},
          "db_duration_seconds": {"type": ["number", "null"]},
          "db_duration_display": {"type": "string"},
          "total_tokens": {"type": "integer"},
          "total_cost_usd": {"type": "number"},
          "matched": {"type": "boolean"},
          "delta_seconds": {"type": ["number", "null"]},
          "delta_display": {"type": "string"},
          "status_icon": {"type": "string"}
        }
      }
    },
    "phase_subtotals": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "phase": {"type": "string"},
          "phase_display": {"type": "string"},
          "run_count": {"type": "integer"},
          "total_duration_seconds": {"type": "number"},
          "total_duration_display": {"type": "string"},
          "total_db_rows": {"type": "integer"},
          "total_tokens": {"type": "integer"},
          "total_cost_usd": {"type": "number"},
          "matched_count": {"type": "integer"},
          "expected_count": {"type": "integer"}
        }
      }
    },
    "grand_total": {"$ref": "#/properties/phase_subtotals/items"},
    "run_start": {"type": ["string", "null"]},
    "run_end": {"type": ["string", "null"]},
    "sources": {
      "type": "object",
      "additionalProperties": {"type": "string"}
    }
  }
}
```

---

## Testing Plan

### Unit Tests

1. **Expected Runs Generator**
   - Test with various config combinations
   - Verify phase ordering
   - Verify run count formulas

2. **FPF Log Parser**
   - Test with sample JSON logs
   - Handle missing fields gracefully
   - Time parsing edge cases

3. **DB Query Functions**
   - Test with sample SQLite databases
   - Handle empty tables
   - Verify timestamp aggregation

4. **Matching Algorithm**
   - Test exact matches
   - Test fuzzy matches (target variations)
   - Handle unmatched expected/actual

### Integration Tests

1. **Full Pipeline Test**
   - Run evaluation
   - Generate timeline chart
   - Verify all columns populated

2. **Regeneration Test**
   - Use `regenerate_report.py`
   - Verify chart matches original

---

## Dependencies

- Existing: `sqlite3`, `json`, `csv`, `datetime`, `dataclasses`
- New: None (uses standard library only)

---

## Rollout Plan

1. **Step 1:** Create `eval_timeline_aggregator.py` with tests
2. **Step 2:** Create `expected_runs_generator.py` with tests  
3. **Step 3:** Add `generate_eval_timeline_chart_section()` to HTML exporter
4. **Step 4:** Update `evaluate.py` integration
5. **Step 5:** Update `runner.py` to pass paths
6. **Step 6:** Update `regenerate_report.py`
7. **Step 7:** End-to-end testing
8. **Step 8:** Documentation update

---

## References

- SPEC 1: `docs/EVAL_RUN_CHART_SPEC.md` - Expected runs from config
- SPEC 2: `docs/EVAL_RUN_CHART_SPEC_2.md` - Actual runs from FPF logs
- SPEC 3: `docs/EVAL_RUN_CHART_SPEC_3.md` - Results from SQLite database
- SPEC 4: `docs/EVAL_RUN_CHART_SPEC_4.md` - Results from CSV exports
- Failure Analysis: `docs/FPF_COST_DATA_FAILURE_ANALYSIS.md` - Path calculation lessons learned

## Deep Dive Analysis & Findings

### 1. Architecture & Dependency Flow
*   **Dependency Direction**: The plan proposes modifying pi_cost_multiplier/llm-doc-eval/reporting/html_exporter.py to import/use TimelineChart from pi_cost_multiplier/tools/eval_timeline_aggregator.py.
    *   **Problem**: llm-doc-eval appears to be a standalone library structure. Importing from the parent pi_cost_multiplier into llm-doc-eval creates a circular or upward dependency which is bad practice.
    *   **Refinement**: html_exporter.py should accept a plain dictionary (JSON-serializable) for the chart data, not a specific class instance from the parent project. The EvalTimelineAggregator in 	ools should convert its dataclass to a dict (sdict) before passing it to the HTML generator.

### 2. File Path Corrections
*   **Correction**: The plan lists pi_cost_multiplier/llm-doc-eval/llm_doc_eval/reporting/html_exporter.py.
    *   **Actual Path**: pi_cost_multiplier/llm-doc-eval/reporting/html_exporter.py. The llm_doc_eval subdirectory is a sibling to 
eporting, not a parent.

### 3. Integration with Existing Logic
*   **Current State**: evaluate.py currently attempts to import generate_eval_timeline from 	ools.eval_timeline_from_db (if available) and passes a JSON path eval_timeline_json_path to generate_html_report.
*   **Transition**: The new EvalTimelineAggregator should supersede eval_timeline_from_db.
*   **Data Passing**: Instead of writing to a temp JSON file and passing the path, we can pass the data dictionary directly to generate_html_report as a new argument eval_timeline_data. This avoids file I/O overhead and keeps the data in memory.
*   **Legacy Support**: The existing generate_eval_timeline_section in html_exporter.py reads from a file. We should overload or replace this to accept data directly.

### 4. Data Source Specifics
*   **FPF Logs**: evaluate.py returns 
esult['fpf_logs_dirs']. The aggregator must be robust enough to handle cases where this list is empty or contains invalid paths.
*   **Config Parsing**: pi_cost_multiplier/config.yaml contains the 
uns definition. The aggregator needs to parse this to build the 'Expected' view.
    *   *Note*: The 
uns list in config.yaml defines the *generation* runs (e.g., 'fpf:google:gemini-2.5-flash'). The *evaluation* runs are defined by the cross-product of these generated docs and the *judge* models defined in llm-doc-eval/config.yaml.
    *   **Logic Check**:
        *   **Generation**: config.yaml -> 
uns list.
        *   **Evaluation**: llm-doc-eval/config.yaml -> models list (Judges).
        *   **Expected Eval Runs**: For each *Judge*, we evaluate each *Generated Doc*.
        *   **Pairwise**: For each *Judge*, we evaluate pairs of *Generated Docs*.
    *   The ExpectedRun generation logic must correctly calculate this cross-product.

### 5. Refined Implementation Steps
1.  **Create 	ools/eval_timeline_aggregator.py**: Implement the aggregator class and dataclasses. Include generate_expected_runs logic here (no need for separate file if small).
2.  **Update 
eporting/html_exporter.py**:
    *   Update generate_html_report signature to accept eval_timeline_data: Dict.
    *   Add 
ender_eval_timeline_chart(data: Dict) -> str helper function (renamed from plan to avoid confusion with existing section).
    *   Ensure it handles missing data gracefully.
3.  **Update evaluate.py**:
    *   Import EvalTimelineAggregator.
    *   After evaluation, instantiate aggregator with paths.
    *   Call ggregator.generate_chart().
    *   Convert to dict.
    *   Pass to generate_html_report.
4.  **Update 
unner.py**: Ensure it passes necessary paths (like cm_log_path) down to evaluate.py or handles the aggregation itself if evaluate.py is running in a subprocess (though evaluate.py seems to be imported and run async in some contexts, or run as script).
    *   *Correction*: 
unner.py calls evaluate.py via subprocess in some cases? No, 
unner.py imports evaluate?
    *   Checking 
unner.py: It imports evaluate and calls evaluate.run_evaluation.
    *   So passing objects in memory is possible.

### 6. Simplification Opportunities
*   **Consolidate 'Expected Runs' Logic**: The logic to determine what *should* have run is implicitly in evaluate.py (loops over models/docs). Centralizing this in the aggregator ensures the chart matches reality.
*   **Unified Data Structure**: The TimelineChart dataclass is a good intermediate representation. We can add a 	o_dict() method to it for easy serialization.

### 7. Potential Pitfalls
*   **Doc ID Matching**: Matching 'Expected' targets (e.g., 'doc1') to 'Actual' logs might be tricky if filenames are mangled or hashed.
    *   *Mitigation*: Use fuzzy matching or rely on the 
un_id / doc_id present in the FPF logs if available. The FPF logs contain config.metadata or similar if we passed it. evaluate.py passes 
un_id which includes doc_id: single-{provider}-{model}-{doc_id}-.... We can parse this 
un_id from the FPF log to extract the doc_id.

### 3rd party perspective

---
## 3rd party perspective — Technical review and enhancements

Reviewer plan: see [pro eval timeline plan.md](pro%20eval%20timeline%20plan.md:1)  
Specs reviewed:
- [EVAL_RUN_CHART_SPEC.md](silky_docs/EVAL_RUN_CHART_SPEC.md:1)
- [EVAL_RUN_CHART_SPEC_2.md](silky_docs/EVAL_RUN_CHART_SPEC_2.md:1)
- [EVAL_RUN_CHART_SPEC_3.md](silky_docs/EVAL_RUN_CHART_SPEC_3.md:1)
- [EVAL_RUN_CHART_SPEC_4.md](silky_docs/EVAL_RUN_CHART_SPEC_4.md:1)
- Failure analysis: [FPF_COST_DATA_FAILURE_ANALYSIS.md](silky_docs/FPF_COST_DATA_FAILURE_ANALYSIS.md:1)

1) Alignment summary
- Strong alignment with Specs 1–4: expected-from-config plus actuals from Logs → SQLite → CSV fallback, unified HTML section, per-phase subtotals and grand totals.
- My plan proposes the same builder/collector/joiner layering and matches formulas and loop orderings from Spec 1.
- Good coverage of rendering, schema, and pipeline hooks.

2) Critical refinements
- Dependency boundaries: avoid “upward” imports into llm-doc-eval. Pass a plain dict to the HTML exporter instead of a class instance to prevent circular deps.
- Path correctness: enforce the fixed two-level path for FPF logs per the failure analysis; add a guard that rejects paths outside api_cost_multiplier/FilePromptForge/logs.
- Phase gating: honor config eval.mode (single|pairwise|both); conditionally suppress phases; only emit combiner rows when combine.enabled is true.
- Costs/tokens: Logs are the single source of truth for tokens and cost; show “—” if unavailable rather than synthesizing from DB/CSV.
- Retries/duplicates: dedupe by (run_group_id, run_id, file_path). Keep earliest start, and only sum cost for unique run_id. Flag failure-*.json as non-success and surface in an “unplanned actuals” area or status badge.
- Matching/joining: use tiered keys:
  - Primary: (phase, judge_model, exact parsed target).
  - Secondary: (phase, judge_model, ordinal_index within phase+judge), mirroring Spec 1 loop order.
  - Tertiary: (phase only) and mark “partial”.
  - Persist a stable expected_id and expected_index for auditability and re-matching.
- Performance: scope log scanning by run_group context from ACM session or result-provided fpf_logs_dirs. Avoid global log tree scans.
- Combiner specifics: ensure the expected combiner rows reflect the hardcoded limit=2 noted in Spec 1 until made configurable.

3) Implementation deltas to incorporate
- Aggregator location: keep the aggregator under reporting/tools returning a pure dict (not a bespoke object).
  - Example public API: [python.generate_eval_timeline_chart()](../silky/api_cost_multiplier/reporting/eval_timeline_chart.py:1).
- HTML interface: exporter should take a dict (chart data) and render; keep UI-only concerns in exporter.
- Reuse or subsume existing tool logic in [../silky/api_cost_multiplier/tools/eval_timeline_from_db.py](../silky/api_cost_multiplier/tools/eval_timeline_from_db.py:1) to avoid duplicating DB parsing.
- Path tracing: write the chosen fpf_logs_dir(s) into acm_session for diagnostics, aligned with the corrected paths in the failure analysis.
- Schema add-ons: include expected_id, expected_index, and source_used = logs|sqlite|csv|config; for post phases include pool_size and pairwise_top_n actually used.

4) Rendering guidance
- Minimal but complete columns:
  - Expected: #, Phase, Type, Judge (expected), Target (expected)
  - Actual: Started, Finished, Duration
  - Cost/Tokens: Tokens, Cost
  - Status/Meta: Source (logs/sqlite/csv/config), Match (✓/partial/missing)
- Insert phase separators and per-phase subtotal rows (Σ Duration, Σ Tokens, Σ Cost, Count).
- Sticky table header; client-side sort on key columns.
- At bottom, add “Unplanned actuals” for any unmatched actual runs.

5) Edge cases and data quality
- Pairwise candidate drift: expected_index fallback is essential since actual pairs depend on previous-phase ranking.
- Time parsing: accept multiple ISO formats (strip Z/offsets) as in Specs 3/4 helpers.
- CSV-only archives: function with just CSVs (no DB/logs) and mark source accordingly.
- Numeric accuracy: show cost with 4 decimals in UI; keep raw numbers in JSON to avoid accumulation of rounding error.

6) Testing matrix
- Unit:
  - Phase detection and target extraction (from logs).
  - Expected ordering from config (including mode gating and combiner enabled/disabled).
  - Join resolver (exact/ordinal/partial).
  - Path guard and scoping behavior.
- Integration:
  - Full run with mode=both yields non-empty costs and correct totals.
  - Regeneration from historical exports.
  - Path misconfig simulation verifies fallback and visible warnings.
- Performance:
  - Large log directories; ensure scoping via run_group_id/time window.

7) Acceptance checklist (measurable)
- HTML contains “Evaluation Timeline Chart” with one row per expected run for enabled phases.
- Tokens/costs populated where logs exist; blanks when not; phase subtotals and grand totals are correct.
- eval_timeline_chart.json created next to the report, with by_phase and overall summaries populated and consistent with the table.
- No “Individual FPF Calls” emptiness when logs exist; cost totals exceed 0 for runs with FPF activity.

8) Recommended file layout (non-blocking)
- Orchestrator: [python.generate_eval_timeline_chart()](../silky/api_cost_multiplier/reporting/eval_timeline_chart.py:1)
- Logs collector: [python.actuals_from_logs](../silky/api_cost_multiplier/reporting/actuals_from_logs.py:1)
- DB collector: [python.actuals_from_db](../silky/api_cost_multiplier/reporting/actuals_from_db.py:1)
- CSV collector: [python.actuals_from_csv](../silky/api_cost_multiplier/reporting/actuals_from_csv.py:1)
- Expected plan: [python.expected_run_plan](../silky/api_cost_multiplier/reporting/expected_run_plan.py:1)
- Existing runner hook reference: [../silky/api_cost_multiplier/runner.py](../silky/api_cost_multiplier/runner.py:1)

Affirmation
- The plan is directionally correct and consistent with Specs 1–4 and the path failure analysis. Applying these refinements will harden correctness (joining, costs, paths), maintain clean dependencies, and keep performance acceptable on real runs.
---

## 4th Party Perspective  Synthesis & Final Recommendations

**Reviewer:** GitHub Copilot (Claude Opus 4.5)  
**Date:** November 29, 2025

---

### Executive Summary

Both the original plan and the 3rd party review are well-aligned. The 3rd party review adds essential production-hardening guidance. This 4th party perspective synthesizes both views, identifies remaining gaps, and provides a prioritized action list.

---

### 1. Affirmations  What's Already Correct

| Aspect | Status | Notes |
|--------|--------|-------|
| Overall architecture |  Solid | ExpectedActual join with fallback chain (LogsDBCSV) |
| Dependency direction fix |  Agreed | Pass dicts, not class instances, to html_exporter |
| Path correction (2-level) |  Critical | Already fixed in api.py per failure analysis |
| Phase gating by eval.mode | ? Important | Must suppress phases not selected |
| Logs as cost/token authority |  Correct | DB/CSV should never synthesize cost |
| Deduplication strategy |  Sound | By (run_group_id, run_id, file_path) |

---

### 2. Gaps & Concerns Identified

#### 2.1 **Missing: Failure Log Handling**
- Neither the original plan nor the deep dive explicitly addresses ailure-*.json files in FPF logs.
- **Recommendation:** Parse them, mark as status="error", include in timeline with matched=False and status_icon="". This surfaces silent failures.

#### 2.2 **Missing: Unplanned Actuals Section**
- The 3rd party review mentions this but it's not in the original schema.
- **Recommendation:** Add unplanned_actuals: List[ActualRunLog] to TimelineChart. Render as a separate collapsible table below the main chart.

#### 2.3 **Incomplete: expected_id / expected_index**
- The 3rd party review mentions adding expected_id and expected_index for auditability.
- **Recommendation:** Add these fields to TimelineRow dataclass:
  `python
  expected_id: str  # Hash of (phase, judge, target) for stable matching
  expected_index: int  # Ordinal within phase+judge for fallback matching
  source_used: str  # "logs" | "sqlite" | "csv" | "config_only"
  `

#### 2.4 **Concern: Combiner Phase Hardcoded limit=2**
- Spec 1 notes a hardcoded limit=2 for combiner. This should be made explicit.
- **Recommendation:** Add combiner_limit to the config and pass it to expected runs generator. Document the current hardcoded behavior in the chart output.

#### 2.5 **Concern: Time Window Scoping**
- Scanning all FPF logs is expensive. The 3rd party review correctly suggests scoping.
- **Recommendation:** Accept 	ime_window_start and 	ime_window_end in the aggregator constructor. Filter logs by started_at timestamp before parsing.

#### 2.6 **Missing: Retry Run Collapsing**
- Retries create multiple logs for the same (judge, target). How to display?
- **Recommendation:** Group retries under the same expected row. Show the *final successful* attempt's data. Add a etry_count field. Optionally, add a [+N retries] badge.

---

### 3. Simplification Opportunities

#### 3.1 **Merge expected_runs_generator.py into aggregator**
- As noted in the deep dive, a separate file is unnecessary. The generation logic is ~50 lines.
- **Recommendation:** Keep it as a method EvalTimelineAggregator.generate_expected_runs().

#### 3.2 **Reuse eval_timeline_from_db.py**
- The existing 	ools/eval_timeline_from_db.py already has DB+log parsing logic.
- **Recommendation:** Refactor it to be a *submodule* or *delegate* of the new aggregator. Don't duplicate logic.

#### 3.3 **JSON Artifact Alongside HTML**
- The 3rd party review suggests eval_timeline_chart.json.
- **Recommendation:** Write this JSON file in the same export directory. It enables programmatic access and debugging without re-parsing HTML.

---

### 4. Revised Schema (Additive)

`python
@dataclass
class TimelineRow:
    # ... existing fields ...
    
    # NEW: Auditability
    expected_id: str  # Stable hash for matching
    expected_index: int  # Ordinal for fallback matching
    source_used: str  # "logs" | "sqlite" | "csv" | "config_only"
    
    # NEW: Retry handling
    retry_count: int  # 0 = no retries
    is_retry: bool  # True if this row is a retry attempt

@dataclass
class TimelineChart:
    # ... existing fields ...
    
    # NEW: Unmatched actuals
    unplanned_actuals: List[Dict[str, Any]]  # Logs that didn't match expected
    
    # NEW: Metadata
    config_snapshot: Dict[str, Any]  # eval.mode, pairwise_top_n, combine.enabled
`

---

### 5. Revised Rollout Plan (Prioritized)

| Step | Task | Priority | Effort |
|------|------|----------|--------|
| 1 | Create 	ools/eval_timeline_aggregator.py skeleton with dataclasses | P0 | 2h |
| 2 | Implement generate_expected_runs() with phase gating | P0 | 2h |
| 3 | Implement parse_fpf_logs() with dedup + failure handling | P0 | 3h |
| 4 | Implement query_db_results() reusing existing logic | P1 | 1h |
| 5 | Implement match_expected_to_actual() with tiered join | P0 | 3h |
| 6 | Add ender_eval_timeline_chart() to html_exporter | P0 | 2h |
| 7 | Update evaluate.py to call aggregator | P0 | 1h |
| 8 | Write JSON artifact alongside HTML | P1 | 1h |
| 9 | Add "Unplanned Actuals" section to HTML | P2 | 1h |
| 10 | Unit tests for join logic | P1 | 2h |
| 11 | Integration test: full run with mode=both | P1 | 2h |

**Total Estimated Effort:** ~20 hours

---

### 6. Final Recommendations

1. **Start with the skeleton**  Get the dataclasses and aggregator class structure in place first. This validates the data model before writing parsing logic.

2. **Add path guards early**  Before any file I/O, validate that pf_logs_dir is under pi_cost_multiplier/FilePromptForge/logs. Log and abort if not.

3. **Test with a real run**  After step 7, run a full evaluation and verify the chart populates. Don't wait for all edge cases.

4. **Document the join logic**  The tiered matching (exactordinalpartial) is subtle. Add inline comments and a docstring explaining the algorithm.

5. **Plan for regeneration**  Ensure egenerate_report.py can produce the timeline chart from archived exports (CSV-only scenario). This is essential for post-mortem analysis.

---

### 7. Open Questions for Stakeholder

1. **Should retries be visible?**  Display as separate rows, collapsed badge, or hidden?
2. **Unplanned actuals threshold**  Show all, or only if count > 0?
3. **Combiner limit=2**  Is this intentional? Should it be configurable via config.yaml?
4. **CSV-only regeneration priority**  Is this a P0 requirement or can it be P2?

---

### Conclusion

The plan is solid and implementation-ready. The 3rd party review added critical hardening. This 4th party perspective provides the final checklist and prioritized action items. Proceed with Step 1.

**Status: APPROVED FOR IMPLEMENTATION**

---

## Implementation Progress Log

### Step 1: Create aggregator skeleton with dataclasses - COMPLETE
**Date:** November 29, 2025

Created 	ools/eval_timeline_aggregator.py with:
- **Enums:** `EvalPhase`, `SourceType`, `MatchStatus`
- **Dataclasses:** `ExpectedRun`, `ActualRunLog`, `DbRunResult`, `CsvRunData`, `TimelineRow`, `PhaseSubtotal`, `TimelineChart`
- **Helper functions:** `parse_iso_ts()`, `format_duration()`, `format_cost()`, `truncate_target()`, `validate_fpf_logs_path()`
- **Main class:** `EvalTimelineAggregator` with all config loading methods

### Step 2: Implement generate_expected_runs() - COMPLETE
**Date:** November 29, 2025

Implemented in `EvalTimelineAggregator.generate_expected_runs()`:
- Phase gating by `eval.mode` (single|pairwise|both)
- Combiner rows only when `combine.enabled`
- Correct formulas: 2 judges x 6 docs = 12 pre-single runs, etc.
- Tested: generates 34 expected runs matching config

### Step 3: Implement parse_fpf_logs() - COMPLETE
**Date:** November 29, 2025

Implemented with:
- Deduplication by `(run_group_id, run_id, file_path)`
- Failure log handling (`failure-*.json`)
- Time window filtering
- Phase/target detection from run_id pattern

### Step 4: Implement query_db_results() - COMPLETE
**Date:** November 29, 2025

Reuses logic from `eval_timeline_from_db.py`:
- Single-doc and pairwise queries
- Timestamp aggregation (MIN/MAX)
- Duration calculation

### Step 5: Implement match_expected_to_actual() - COMPLETE
**Date:** November 29, 2025

Tiered matching:
1. Exact: `(phase, judge_model, target)`
2. Ordinal: `(phase, judge_model, ordinal_index)`
3. Partial: phase-only (disabled to avoid false matches)

Also returns `unplanned_actuals` list.

### Step 6: Add render_eval_timeline_chart() to html_exporter - COMPLETE
**Date:** November 29, 2025

Added to `llm-doc-eval/reporting/html_exporter.py`:
- New function `render_eval_timeline_chart(chart_data: Dict)` - accepts dict, not classes
- CSS styling with column groups, phase separators, status icons
- Phase subtotal rows and grand total row
- Unplanned actuals section
- Updated `generate_html_report()` signature to accept `eval_timeline_chart_data`
- Updated `generate_unified_html_report()` similarly

### Step 7: Update evaluate.py to call aggregator - COMPLETE
**Date:** November 29, 2025

Modified `evaluate.py`:
- Import `EvalTimelineAggregator` with graceful fallback
- Create aggregator after evaluation completes
- Generate chart data with `to_dict()`
- Write `eval_timeline_chart.json` artifact
- Pass `eval_timeline_chart_data` to `generate_html_report()`

### Step 8: Write JSON artifact alongside HTML - COMPLETE
**Date:** November 29, 2025

JSON written to `final_export_dir/eval_timeline_chart.json`

---

**Remaining Steps:**
- Step 9: Add "Unplanned Actuals" section to HTML (P2) - Already implemented in render function
- Step 10: Unit tests for join logic (P1)
- Step 11: Integration test: full run with mode=both (P1)

**Status: CORE IMPLEMENTATION COMPLETE**


---

## Implementation Progress Log

### Step 1-8: COMPLETE
**Date:** November 29, 2025

All core implementation steps completed. See tools/eval_timeline_aggregator.py and reporting/html_exporter.py.

**Status: CORE IMPLEMENTATION COMPLETE**

