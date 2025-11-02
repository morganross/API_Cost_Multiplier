# Timeline Failure Reason A3: MA Run Index Collision

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A critical issue causing the timeline to be incomplete is that the Multi-Agent (MA) logging system does not use unique identifiers for each run. All MA runs are logged with the same index, `[MA run 1]`, which leads to data corruption in the timeline generation script.

## Evidence

The `acm_subprocess_20251101_180022.log` file shows that all MA runs, regardless of the model being used, are logged with the same index:

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

The `timeline_from_logs.py` script uses the run index to create a unique `run_id` for each run. Because all MA runs have the same index, they all get the same `run_id`: `ma-1`.

## Impact

When the timeline script processes the log file, it creates a single `RunRecord` object for `ma-1`. As it encounters each new MA run, it overwrites the `start_ts`, `end_ts`, `result`, and `model` of this single record.

**Result:** Only the data from the *last* MA run is preserved. All previous MA runs are effectively erased from the timeline. This is why only the `o4-mini` MA run appeared in the final timeline, as it was the last one to be processed.

## Recommendations

To fix this issue, the `MA_runner.py` module must be modified to use unique run identifiers for each MA run. This can be achieved by incorporating the model name and iteration number into the run index.

**Example of improved logging:**

```
[MA run gpt-4.1-1] Starting research...
[MA run gpt-4.1-1] Multi-agent report written...
[MA run gpt-4.1-mini-1] Starting research...
[MA run gpt-4.1-mini-1] Multi-agent report written...
```

This would require changes to the logging statements in `MA_runner.py` to generate unique run IDs. Additionally, the `timeline_from_logs.py` script would need to be updated to correctly parse these new, unique run IDs.
