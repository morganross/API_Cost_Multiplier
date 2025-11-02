# Timeline Failure Reason D10: MA_runner Doesn't Use Unique Run Identifiers

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A significant issue contributing to the incomplete timeline is that the `MA_runner.py` module does not use unique run identifiers for each Multi-Agent (MA) run. The `iterations` parameter is passed to the `run_multi_agent_runs` function, but it is not used to create unique run IDs for each iteration.

## Evidence

The `MA_runner.py` module logs all MA runs with the same index, `[MA run 1]`, regardless of the model being used or the iteration number. This is because the `run_multi_agent_runs` function does not incorporate the iteration number or model name into the run ID.

## Impact

Because all MA runs have the same `run_id`, the timeline script overwrites the data for each run, and only the data from the *last* run is preserved. This leads to an incomplete and inaccurate timeline.

## Recommendations

To fix this issue, the `MA_runner.py` module must be modified to generate unique run identifiers for each MA run. This can be achieved by incorporating the model name and iteration number into the run index.

**Example of improved logging:**

```
[MA run gpt-4.1-1] Starting research...
[MA run gpt-4.1-1] Multi-agent report written...
[MA run gpt-4.1-2] Starting research...
[MA run gpt-4.1-2] Multi-agent report written...
```

This would require changes to the logging statements in `MA_runner.py` to generate unique run IDs. Additionally, the `timeline_from_logs.py` script would need to be updated to correctly parse these new, unique run IDs.
