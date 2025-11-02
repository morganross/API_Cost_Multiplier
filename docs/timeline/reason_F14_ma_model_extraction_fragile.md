# Timeline Failure Reason F14: MA Model Extraction from Log Lines is Fragile

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A potential issue that could contribute to an incomplete timeline is that the `timeline_from_logs.py` script's method for extracting the model name from Multi-Agent (MA) log lines is fragile. If the model name is not in the expected format, it will default to "unknown", leading to an inaccurate timeline.

## Evidence

The `timeline_from_logs.py` script uses the following regular expression to extract the model name from MA log lines:

```python
model_match = re.search(r"model=([a-zA-Z0-9\-\._:]+)", line)
```

This regex assumes that the model name will be in the format `model=<model_name>`, and that the model name will only contain alphanumeric characters, hyphens, underscores, periods, and colons. If the model name contains any other characters, or if the log line is not in the expected format, the regex will fail to match, and the model name will default to "unknown".

## Impact

If the model name is not correctly extracted, the timeline will be inaccurate. This could make it difficult to track the performance of different models and to identify which models are causing issues.

## Recommendations

To fix this issue, the model extraction logic in `timeline_from_logs.py` should be made more robust.

1.  **Improve the Regex:** The regex could be improved to handle a wider range of characters in the model name.

2.  **Use a More Structured Logging Format:** The `MA_runner.py` module could be modified to log the model name in a more structured format, such as JSON. This would make it much easier for the timeline script to parse the model name accurately.

By implementing these changes, the model extraction logic will be more reliable, and the timeline script will be able to produce a more accurate and complete timeline.
