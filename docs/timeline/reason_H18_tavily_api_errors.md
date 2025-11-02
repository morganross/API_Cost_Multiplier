# Timeline Failure Reason H18: Tavily API 400 Errors

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A significant issue contributing to the incomplete timeline is that the Tavily API is returning 400 Bad Request errors. This indicates that there is an issue with the requests being sent to the Tavily API, which is preventing the GPT-Researcher runs from gathering web content.

## Evidence

The `acm_subprocess_20251101_180022.log` file shows multiple instances of the following error:

```
2025-11-01 18:00:31,698 - acm.subproc - INFO - [OUT] Error: 400 Client Error: Bad Request for url: https://api.tavily.com/search. Failed fetching sources. Resulting in empty response.
```

This error indicates that the Tavily API is rejecting the search requests with a 400 Bad Request error. This could be due to a number of issues, including:
- An invalid API key.
- An invalid search query.
- Rate limiting.

## Impact

Because the Tavily API is returning errors, the GPT-Researcher runs are unable to gather web content. This leads to:
- Runs completing with empty or minimal content.
- Runs failing entirely due to a lack of research material.
- Missing `[GPTR_END]` entries for failed runs, which are then excluded from the timeline.

This issue is a direct cause of the "missing grounding" errors and contributes significantly to the incomplete timeline.

## Recommendations

To fix this issue, the Tavily API integration should be investigated to determine the cause of the 400 errors.

1.  **Check the Tavily API Key:** The Tavily API key should be checked to ensure that it is valid and has not expired.

2.  **Validate Search Queries:** The search queries being sent to the Tavily API should be validated to ensure that they are well-formed and do not contain any invalid characters.

3.  **Implement Rate Limiting:** If the issue is due to rate limiting, a rate limiting mechanism should be implemented to ensure that the number of requests sent to the Tavily API does not exceed the allowed limit.

By implementing these changes, the Tavily API errors should be resolved, allowing the GPT-Researcher runs to gather web content and complete successfully.
