# Timeline Failure Reason G17: Timeline Script Invoked Before All Runs Complete

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A significant issue contributing to the incomplete timeline is that the `timeline_from_logs.py` script is invoked before all runs have completed. This means that any runs that are still in progress when the timeline script is invoked will not be included in the final timeline.

## Evidence

The `acm_session.log` file shows that the timeline script was invoked at `18:15:26,369`. However, the `acm_subprocess_20251101_180022.log` file shows that the `openaidp` FPF run did not complete until `18:31:42,813`.

**Timeline script invocation:**
```
2025-11-01 18:15:26,369 - acm - INFO - [TIMELINE]
```

**`openaidp` FPF run completion:**
```
2025-11-01 18:31:42,813 - acm.subproc - INFO - [FPF RUN_COMPLETE] id=fpf-1-1 kind=deep provider=openaidp model=o4-mini-deep-research ok=false
```

This clearly shows that the timeline script was invoked before the `openaidp` FPF run had completed.

## Impact

Because the timeline script is invoked prematurely, any runs that are still in progress will not have a `[GPTR_END]` or `[FPF RUN_COMPLETE]` event in the log file. As a result, these runs will be excluded from the final timeline.

## Recommendations

To fix this issue, the `runner.py` script should be modified to ensure that all runs have completed before the timeline script is invoked.

1.  **Wait for All Background Tasks:** The `runner.py` script should use `asyncio.gather` or a similar mechanism to wait for all FPF, GPT-Researcher, and MA tasks to complete before invoking the timeline script.

2.  **Implement a Finalization Step:** A finalization step could be added to the `runner.py` script that is only executed after all runs have completed. This step would be responsible for invoking the timeline script.

By implementing these changes, the timeline script will only be invoked after all runs have completed, ensuring that all runs are included in the final timeline.
