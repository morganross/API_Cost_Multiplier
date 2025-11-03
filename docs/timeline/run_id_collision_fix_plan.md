# Run ID Collision and FPF Discrepancy Fix Plan

**Date:** November 2, 2025
**Owner:** Cline AI Assistant

## Summary

This plan addresses the `run_id` collision issues observed in the timeline generation, specifically focusing on the FPF discrepancy where a "deep" FPF run was incorrectly attributed a "rest" model in the timeline output. It also clarifies the current naming behavior for FPF and MA runs. The proposed fix is purely within `timeline_from_logs.py` to ensure accurate model attribution for FPF deep runs, adhering to the "timeline-only" constraint.

## Current Naming Behavior and Collision Analysis

### FPF `run_id` Logic (`fpf_runner.py`)

-   **Purpose of `fpf_runner.py`:** This module orchestrates the execution of FilePromptForge (FPF) runs, either individually or in batches, by invoking the external `fpf_main.py` script. It's responsible for preparing run configurations and capturing FPF's output.
-   **`run_id` Generation:** `fpf_runner.py` generates `run_id`s for FPF runs using the format `fpf-{idx+1}-{rep}`, where `idx` is the index of the run within a batch and `rep` is the iteration number.
-   **Collision Source:** In `runner.py`, FPF runs are often split into separate batches (e.g., `fpf_openaidp` and `fpf_rest`). When `fpf_runner.py` is called for each of these batches, its internal `idx` resets to 0. This means that the first run in the `fpf_openaidp` batch and the first run in the `fpf_rest` batch will both generate the `run_id` `fpf-1-1`. This leads to a collision in the `acm_subprocess_*.log` file, as two distinct FPF runs are logged with the same `id`.

### ACM MA `run_id` Logic (`runner.py`)

-   **Purpose of `runner.py`:** This is the central orchestration script for the entire `api_cost_multiplier` pipeline. It manages the execution of FPF, GPT-Researcher, and Multi-Agent (MA) runs.
-   **MA `run_id` Generation:** For Multi-Agent runs, `runner.py` directly logs `[MA run {iterations}]` events to the `acm.subproc` logger. The `{iterations}` value is typically a constant (e.g., 1) for a single configured MA run.
-   **Collision Source:** When multiple MA models are configured and run sequentially (e.g., `gpt-4.1-mini` then `gpt-4.1-nano`), `runner.py` logs each with `[MA run 1]`. This results in all MA runs having the `run_id` `ma-1` in the logs, causing a collision.

### Summary of Collision Problem

Both FPF and MA logging mechanisms, as currently implemented, produce `run_id`s that are not globally unique across all runs within a single `generate.py` execution. This leads to `run_id` collisions in the `acm_subprocess_*.log`, making it difficult for `timeline_from_logs.py` to accurately track and attribute details to each individual run.

## Detailed Fix: Enhancing `timeline_from_logs.py` for FPF Discrepancy

This fix specifically targets the FPF discrepancy where a "deep" FPF run's model was incorrectly attributed in the timeline due to a `run_id` collision. The solution is implemented purely within `timeline_from_logs.py`, adhering to the "timeline-only" constraint.

**File to be edited:** `api_cost_multiplier/tools/timeline_from_logs.py`

**Purpose of `timeline_from_logs.py`:** This script parses the `acm_subprocess_*.log` (and optionally `acm_session.log`) to generate a human-readable timeline of runs. It aggregates log entries into `RunRecord` objects and prints them in a standardized format.

**Problem:** The `_upsert_single` function's defensive logic for updating the `model` field (only if `rec.model` is "unknown" or empty) causes a mismatch when a `run_id` collision occurs between an "FPF rest" run and an "FPF deep" run. The `report_type` might update to "FPF deep", but the `model` remains the "rest" model if it was set first.

**Fix:** Modify the `_upsert_single` function to ensure that if a `report_type` is provided and it's "FPF deep", the `model` is always updated to the provided `model`, overriding any previous "rest" model. This prioritizes the more specific "deep" model when a collision occurs.

**Code Snippet (Changes to `timeline_from_logs.py`):**

```python
# In timeline_from_logs.py, modify the _upsert_single function:

def _upsert_single(rid: str, report_type: Optional[str] = None, model: Optional[str] = None,
                   start_ts: Optional[datetime] = None, end_ts: Optional[datetime] = None,
                   result: Optional[str] = None) -> RunRecord:
    lst = _get_list(rid)
    if not lst:
        rec = RunRecord(run_id=rid, report_type=report_type or "unknown", model=model or "unknown",
                        start_ts=start_ts, end_ts=end_ts, result=result)
        lst.append(rec)
        return rec
    rec = lst[-1]
    
    # Always update report_type if provided
    if report_type:
        rec.report_type = report_type
    
    # Update model if provided. Prioritize if the new report_type is "FPF deep"
    # or if the current model is unknown/empty.
    # This ensures the model is correctly attributed to the latest event for this run_id.
    if model:
        if rec.model == "unknown" or not rec.model:
            rec.model = model
        elif report_type == "FPF deep" and rec.report_type == "FPF deep" and model != rec.model:
            # If both are deep, and model is different, prefer the new model
            rec.model = model
        elif report_type == "FPF deep" and rec.report_type != "FPF deep":
            # If the new event makes it deep, always update the model
            rec.model = model
    
    if rec.start_ts is None and start_ts is not None:
        rec.start_ts = start_ts
    if end_ts is not None:
        rec.end_ts = end_ts
    if result in ("success", "failure"):
        rec.result = result
    return rec
