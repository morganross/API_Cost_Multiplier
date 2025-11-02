# Timeline Failure Reason D8: GPTR Subprocess Error Handling

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A significant issue contributing to the incomplete timeline is that the error handling in `gptr_subprocess.py` does not guarantee that a `[GPTR_END]` event is logged when an exception occurs. This leads to incomplete `RunRecord` objects and their exclusion from the final timeline.

## Evidence

The `acm_subprocess_20251101_180022.log` file shows that PID 17208 (Deep Research, claude-3-5-haiku-latest) failed with an Anthropic API error, but no `[GPTR_END]` event was logged for this run. This indicates that the exception was not caught in a way that would allow for a final log message to be emitted.

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
