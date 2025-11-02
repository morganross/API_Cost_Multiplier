# Multi-Agent (MA) Failure Impact on Timeline Generation

**Date:** November 1, 2025  
**Investigator:** Cline AI Assistant  
**Related Report:** `timeline_generation_failure_investigation.md`

## Executive Summary

This report addresses the user's question regarding how Multi-Agent (MA) failures, specifically run index collisions, can cause the timeline generation script (`timeline_from_logs.py`) to fail or produce incomplete results. While MA runs and the timeline script might seem unrelated at first glance, a critical flaw in the MA logging mechanism directly leads to data corruption within the timeline generation process.

## The Problem: MA Run Index Collision

The `timeline_from_logs.py` script parses the `acm_subprocess_*.log` file to identify start and end events for various runs (FPF, GPT-Researcher, MA). It uses unique identifiers (like PIDs for GPT-Researcher or `run_id` for FPF) to track individual runs.

For Multi-Agent runs, the `MA_runner.py` module logs events using a format similar to `[MA run X]`. However, during the previous `generate.py` execution, it was observed that all iterations of MA runs were logged with the same index: `[MA run 1]`.

**Example from `acm_subprocess_20251101_180022.log`:**

```
2025-11-01 18:12:24,088 - acm.subproc - INFO - [MA run 1] Starting research for query: ... (gpt-4.1)
2025-11-01 18:13:23,888 - acm.subproc - INFO - [MA run 1] Multi-agent report (Markdown) written to ... model=gpt-4.1
2025-11-01 18:13:23,892 - acm.subproc - INFO - [MA run 1] Starting research for query: ... (gpt-4.1-mini)
2025-11-01 18:13:49,127 - acm.subproc - INFO - [MA run 1] Multi-agent report (Markdown) written to ... model=gpt-4.1-mini
2025-11-01 18:13:49,137 - acm.subproc - INFO - [MA run 1] Starting research for query: ... (gpt-4.1-nano)
2025-11-01 18:14:36,817 - acm.subproc - INFO - [MA run 1] Multi-agent report (Markdown) written to ... model=gpt-4.1-nano
2025-11-01 18:14:36,822 - acm.subproc - INFO - [MA run 1] Starting research for query: ... (o4-mini)
2025-11-01 18:15:26,088 - acm.subproc - INFO - [MA run 1] Multi-agent report (Markdown) written to ... model=o4-mini
```

## How This Causes Timeline Failure

The `timeline_from_logs.py` script maintains a dictionary (`runs`) to store `RunRecord` objects, using the `run_id` (e.g., "ma-1") as the key.

When the timeline script encounters multiple `[MA run 1]` entries:

1.  **First MA run (e.g., `gpt-4.1`):** A `RunRecord` for `ma-1` is created with its `start_ts`. When its `Multi-agent report written` entry is found, its `end_ts`, `result`, and `model` are updated.
2.  **Subsequent MA runs (e.g., `gpt-4.1-mini`, `gpt-4.1-nano`, `o4-mini`):** Each subsequent MA run also logs its start and end events with `run_id="ma-1"`. Because the `run_id` is not unique for each distinct MA run, the timeline script **overwrites the `start_ts`, `end_ts`, `result`, and `model` of the *same* `RunRecord` object (`ma-1`)** with the data from the latest MA run it processes.

**Consequence:**

By the time the `timeline_from_logs.py` script finishes parsing the entire `acm_subprocess_*.log`, the `RunRecord` for `ma-1` will only contain the data (start time, end time, model, result) of the *last* MA run that completed. All previous MA runs are effectively erased from the `runs` dictionary due to this collision.

This is why only one MA entry (`MA, o4-mini`) appeared in the final timeline. It was the last MA run to be processed and thus the only one whose data remained in the `ma-1` record. The other MA runs, despite having completed, were not represented in the timeline because their data was overwritten.

## Conclusion

The MA failure to use unique run identifiers directly causes the timeline script to produce an incomplete and inaccurate timeline. The timeline script is not "failing" in its parsing logic for a single run, but rather the input data it receives from the MA logging is fundamentally flawed due to the lack of unique run IDs, leading to data loss within the `runs` tracking dictionary. This is a critical issue that needs to be addressed in the `MA_runner.py` module to ensure proper timeline generation.
