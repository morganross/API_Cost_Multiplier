# Timeline Failure Reason D9: FPF Batch Mode Events

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A potential issue contributing to the incomplete timeline is that the FilePromptForge (FPF) batch mode may not emit complete events for all runs. If an error occurs during batch processing, it's possible that individual run completion events are not logged, leading to their exclusion from the timeline.

## Evidence

The `acm_subprocess_20251101_180022.log` file shows that 9 FPF runs were started, but only 6 `[FPF RUN_COMPLETE]` events were logged. While some of these may be due to timeouts, it's also possible that errors in the batch processing prevented the completion events from being logged.

## Impact

If a `[FPF RUN_COMPLETE]` event is not logged for a given run, the `timeline_from_logs.py` script cannot determine its end time or result. As a result, the `RunRecord` for that run is considered incomplete and is discarded, leading to its omission from the final timeline.

## Recommendations

To fix this issue, the FPF batch processing logic in `fpf_runner.py` should be improved to ensure that a `[FPF RUN_COMPLETE]` event is always logged for each run in the batch, even if an error occurs.

1.  **Implement Per-Run Error Handling:** The batch processing loop in `fpf_runner.py` should wrap each individual run in a `try...except` block. If a run fails, it should log a `[FPF RUN_COMPLETE]` event with `ok=false` for that specific run and then continue to the next run in the batch.

2.  **Ensure Batch Completion Logging:** The batch processing logic should also ensure that a final log message is emitted when the entire batch is complete, indicating how many runs succeeded and how many failed.

By implementing these changes, the FPF batch mode will be more resilient to errors and will provide more accurate and complete logging, allowing the timeline script to track all FPF runs, including those that fail.
