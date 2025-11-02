# Timeline Failure Reason A2: Missing FPF RUN_COMPLETE Events

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

Another primary reason for the incomplete timeline is that FilePromptForge (FPF) runs that time out or fail do not consistently emit a `[FPF RUN_COMPLETE]` log event. The timeline generation script (`timeline_from_logs.py`) requires both a `[FPF RUN_START]` and a `[FPF RUN_COMPLETE]` event to create a complete `RunRecord` for a given FPF run. If the end event is missing, the run is excluded from the final timeline.

## Evidence

In the `acm_subprocess_20251101_180022.log` file, we can see that 9 FPF runs were started, but only 6 `[FPF RUN_COMPLETE]` events were logged.

- **FPF Runs Started:** 9
- **FPF Runs Completed:** 6

**Example of a failed FPF run:**

- **Start Event:**
  ```
  2025-11-01 18:00:22,619 - acm.subproc - INFO - [FPF RUN_START] id=fpf-1-1 kind=deep provider=openaidp model=o4-mini-deep-research
  ```

- **Completion Event (with failure):**
  ```
  2025-11-01 18:31:42,813 - acm.subproc - INFO - [FPF RUN_COMPLETE] id=fpf-1-1 kind=deep provider=openaidp model=o4-mini-deep-research ok=false
  ```
  This run took over 31 minutes and was correctly marked as a failure.

**Missing Completion Events:**

Three FPF runs did not have a corresponding `[FPF RUN_COMPLETE]` event in the log. This could be due to:
- The FPF subprocess timing out before it could log the completion event.
- An unhandled exception in the FPF subprocess that prevented the completion event from being logged.
- The `runner.py` script terminating before the FPF subprocesses had a chance to finish.

## Impact

Because the `[FPF RUN_COMPLETE]` event is missing for these three runs, the `timeline_from_logs.py` script cannot determine their end time or result. As a result, the `RunRecord` objects for these runs are considered incomplete and are discarded, leading to their omission from the final timeline.

## Recommendations

To fix this issue, the FPF runner logic in `fpf_runner.py` and the orchestration in `runner.py` should be improved to ensure that a `[FPF RUN_COMPLETE]` event is always logged, even when a run times out or fails.

1.  **Implement Robust Timeout Handling:** The `fpf_runner.py` should have a timeout mechanism for each FPF run. If a run times out, it should explicitly log a `[FPF RUN_COMPLETE]` event with `ok=false`.

2.  **Improve Exception Handling:** The FPF subprocess execution should be wrapped in a `try...finally` block to ensure that a `[FPF RUN_COMPLETE]` event is logged even if an unhandled exception occurs.

3.  **Ensure All Subprocesses Complete:** The `runner.py` script should wait for all FPF subprocesses to complete before exiting. This can be achieved using `asyncio.gather` or similar mechanisms to wait for all FPF tasks to finish.

By implementing these changes, every `[FPF RUN_START]` will have a corresponding `[FPF RUN_COMPLETE]`, allowing the timeline script to accurately track all FPF runs, including those that fail or time out.
