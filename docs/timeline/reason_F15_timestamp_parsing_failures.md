# Timeline Failure Reason F15: Timestamp Parsing Failures

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A potential issue that could contribute to an incomplete timeline is that the `timeline_from_logs.py` script's method for parsing timestamps from log lines is not robust. If a timestamp is malformed, the `parse_ts()` function will return `None`, and any runs with `None` timestamps will be excluded from the timeline.

## Evidence

The `timeline_from_logs.py` script uses the following regular expression to parse timestamps from log lines:

```python
TS_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3})\b")
```

This regex assumes that the timestamp will be in the format `YYYY-MM-DD HH:MM:SS,mmm`. If the timestamp is in a different format, or if it is malformed, the regex will fail to match, and the `parse_ts()` function will return `None`.

## Impact

If a timestamp is not correctly parsed, the `RunRecord` for that run will have a `None` value for its `start_ts` or `end_ts`. Because the timeline script requires both a start and an end time to create a complete record, any run with a `None` timestamp will be excluded from the final timeline.

## Recommendations

To fix this issue, the timestamp parsing logic in `timeline_from_logs.py` should be made more robust.

1.  **Improve the Regex:** The regex could be improved to handle a wider range of timestamp formats.

2.  **Add Error Handling:** The `parse_ts()` function could be modified to log a warning when it encounters a malformed timestamp. This would make it easier to identify and debug logging issues in the future.

By implementing these changes, the timestamp parsing logic will be more reliable, and the timeline script will be less likely to exclude valid runs from the final timeline due to timestamp parsing failures.
