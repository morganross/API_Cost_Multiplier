# Timeline Failure Reason E13: No Validation or Error Reporting in Timeline Script

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A significant issue contributing to the difficulty in diagnosing timeline failures is the lack of validation and error reporting in the `timeline_from_logs.py` script. The script does not report how many runs were parsed versus how many were included in the final timeline, nor does it warn when runs are excluded due to missing data. This makes it difficult to identify and debug logging issues.

## Evidence

The `timeline_from_logs.py` script silently discards `RunRecord` objects that are missing a start event, an end event, or a result. There is no logging to indicate that a run has been excluded, or why.

**Example from `timeline_from_logs.py`:**

```python
# Build final list: only records with both start and end
complete: List[RunRecord] = []
for rec in runs.values():
    if rec.start_ts and rec.end_ts and rec.result in ("success", "failure"):
        complete.append(rec)
```

If a `RunRecord` does not meet these criteria, it is simply not added to the `complete` list, and no warning or error is generated.

## Impact

This lack of validation and error reporting makes it extremely difficult to diagnose issues with the timeline generation. Without any indication that runs are being excluded, it is impossible to know whether the issue is with the logging infrastructure, the timeline script itself, or the data being logged.

## Recommendations

To fix this issue, the `timeline_from_logs.py` script should be modified to include more robust validation and error reporting.

1.  **Log Parsing Statistics:** The script should log how many runs were parsed from the log file, and how many were included in the final timeline. This will make it immediately obvious if runs are being excluded.

2.  **Warn on Excluded Runs:** The script should log a warning when it encounters a `RunRecord` that is missing one or more of the required fields. The warning should include the `run_id` and the reason for the exclusion.

3.  **Add a Debug Mode:** The script could be modified to include a debug mode that prints out detailed information about each `RunRecord` as it is processed. This would make it much easier to trace the data flow and identify issues.

By implementing these changes, the timeline script will be more transparent and easier to debug, which will help to ensure that all runs are accurately represented in the final timeline.
