# Timeline Failure Reason E11: Timeline Script Requires Exact Start+End+Result Match

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A significant issue contributing to the incomplete timeline is that the `timeline_from_logs.py` script requires an exact match of a start event, an end event, and a result for each run. If any of these three fields are missing, the run is excluded from the final timeline.

## Evidence

The `timeline_from_logs.py` script includes the following logic:

```python
# Build final list: only records with both start and end
complete: List[RunRecord] = []
for rec in runs.values():
    if rec.start_ts and rec.end_ts and rec.result in ("success", "failure"):
        complete.append(rec)
```

This code explicitly checks for the presence of `start_ts`, `end_ts`, and a `result` of either "success" or "failure". If any of these conditions are not met, the `RunRecord` is not added to the `complete` list and is therefore excluded from the final timeline.

## Impact

This strict requirement means that any run that fails to log a start event, an end event, or a result will be silently ignored by the timeline script. This is a major contributor to the incomplete timeline, as it means that any run that fails in a way that prevents it from logging all three required fields will not be represented in the final output.

## Recommendations

To fix this issue, the `timeline_from_logs.py` script should be modified to be more resilient to missing data. This can be achieved by:

1.  **Allowing for partial timeline entries:** The script could be modified to generate partial timeline entries for runs that are missing an end event or a result. For example, a run with a start event but no end event could be listed as "in-progress" or "timed-out".

2.  **Adding more robust error reporting:** The script should log a warning when it encounters a `RunRecord` that is missing one or more of the required fields. This will make it easier to identify and debug logging issues in the future.

By implementing these changes, the timeline script will be more resilient to missing data and will be able to produce a more accurate and complete timeline, even when some runs fail to log all the required information.
