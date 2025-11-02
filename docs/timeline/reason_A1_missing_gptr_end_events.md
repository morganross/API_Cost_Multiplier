# Timeline Failure Reason A1: Missing GPT-Researcher End Events

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

One of the primary reasons for the incomplete timeline is that GPT-Researcher subprocesses that encounter errors do not reliably emit a `[GPTR_END]` log event. The timeline generation script (`timeline_from_logs.py`) requires both a `[GPTR_START]` and a `[GPTR_END]` event to create a complete `RunRecord` for a given run. If the end event is missing, the run is excluded from the final timeline.

## Evidence

In the `acm_subprocess_20251101_180022.log` file, we can see an example of this with PID 17208:

- **Start Event:**
  ```
  2025-11-01 18:00:31,441 - acm.subproc - INFO - [GPTR_START] pid=17208 type=deep model=anthropic:claude-3-5-haiku-latest
  ```

- **Error Encountered:**
  ```
  2025-11-01 18:01:06,220 - acm.subproc - INFO - [OUT] Error in generate_report: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'max_tokens: 32000 > 8192, which is the maximum allowed number of output tokens for claude-3-5-haiku-20241022'}, 'request_id': 'req_011CUiABQiCrWqtSUduisrn6'}
  ```

- **Missing End Event:** There is no corresponding `[GPTR_END] pid=17208` entry in the log file.

## Impact

Because the `[GPTR_END]` event is missing, the `timeline_from_logs.py` script cannot determine the end time or result of the run. As a result, the `RunRecord` for this run is considered incomplete and is discarded, leading to its omission from the final timeline.

## Recommendations

To fix this issue, the error handling in `gptr_subprocess.py` should be improved to ensure that a `[GPTR_END]` event is always logged, even when an exception occurs. This can be achieved by wrapping the main execution logic in a `try...finally` block:

```python
# In gptr_subprocess.py

try:
    # Main execution logic
    # ...
    SUBPROC_LOGGER.info(f"[GPTR_END] pid={os.getpid()} result=success")
except Exception as e:
    SUBPROC_LOGGER.error(f"Unhandled exception: {e}")
finally:
    # Ensure end event is logged even on failure
    SUBPROC_LOGGER.info(f"[GPTR_END] pid={os.getpid()} result=failure")
```

This will guarantee that every `[GPTR_START]` has a corresponding `[GPTR_END]`, allowing the timeline script to accurately track all GPT-Researcher runs, including those that fail.
