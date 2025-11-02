# Timeline Failure Reason C7: Anthropic Claude Haiku max_tokens Misconfiguration

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A significant issue contributing to the incomplete timeline is a misconfiguration of the `max_tokens` parameter for the Anthropic Claude Haiku model. The code attempts to use a `max_tokens` value of 32000, which exceeds the model's maximum of 8192 tokens, causing API 400 errors and run failures.

## Evidence

The `acm_subprocess_20251101_180022.log` file shows the following error for PID 17208 (Deep Research, claude-3-5-haiku-latest):

```
2025-11-01 18:01:06,220 - acm.subproc - INFO - [OUT] Error in generate_report: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'max_tokens: 32000 > 8192, which is the maximum allowed number of output tokens for claude-3-5-haiku-20241022'}, 'request_id': 'req_011CUiABQiCrWqtSUduisrn6'}
```

This error indicates that the `max_tokens` parameter was set to 32000, which is greater than the maximum allowed value of 8192 for the `claude-3-5-haiku-20241022` model.

## Impact

This misconfiguration causes the Anthropic API to reject the request with a 400 Bad Request error. This, in turn, causes the GPT-Researcher run to fail. Because the run fails, a `[GPTR_END]` event is not logged, and the run is excluded from the final timeline.

## Recommendations

To fix this issue, the code that sets the `max_tokens` parameter for Anthropic models should be modified to respect the model's maximum token limit.

1.  **Identify the code that sets `max_tokens`:** The code that sets the `max_tokens` parameter needs to be located. This is likely in the `gpt-researcher` component, possibly in a file that handles LLM provider interactions.

2.  **Implement model-specific `max_tokens` limits:** The code should be modified to use a lower `max_tokens` value when interacting with the Anthropic Claude Haiku model. This could be done by:
    *   Hardcoding a lower value for this specific model.
    *   Querying the model's metadata to determine the correct `max_tokens` value.
    *   Adding a configuration option to specify the `max_tokens` value for each model.

By implementing these changes, the `max_tokens` parameter will be set to a valid value for the Anthropic Claude Haiku model, preventing API errors and allowing the run to complete successfully.
