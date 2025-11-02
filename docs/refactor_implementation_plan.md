# Refactor Implementation Plan

**Date:** November 1, 2025  
**Related Reports:** `timeline_generation_failure_investigation.md`, `timeline_error_analysis.md`

## Executive Summary

This document outlines a detailed implementation plan to refactor the `api_cost_multiplier` system and address the issues identified in the timeline generation failure investigation. The plan is segmented by issue category and provides specific action items for each issue.

The timeline generation is failing due to a combination of configuration errors, logging infrastructure issues, and timeline script logic issues. The most critical issues are the invalid scraper configuration, the MA run index collision, and the premature invocation of the timeline script. This plan addresses these issues by correcting the configuration, improving the logging infrastructure, and making the timeline script more robust. The goal of this refactor is to ensure that the timeline generation is reliable and accurate, even when runs fail or time out. This will provide better visibility into the performance of the system and make it easier to diagnose issues in the future. By implementing the changes outlined in this plan, the timeline generation will be more resilient and will provide a more accurate and complete picture of the system's behavior.

## 1. Configuration Errors

### 1.1. Invalid Scraper Configuration

-   **Issue:** The default scraper in `gpt-researcher` is set to "requests", which is not a valid scraper.
-   **File to Modify:** `api_cost_multiplier/gpt-researcher/gpt_researcher/config/variables/default.py`
-   **Action:** Change the value of `SCRAPER` from `"requests"` to `"tavily_extract"`.

### 1.2. Anthropic Claude Haiku max_tokens Misconfiguration

-   **Issue:** The `max_tokens` parameter for the Anthropic Claude Haiku model is set to 32000, which exceeds the model's maximum of 8192 tokens.
-   **File to Modify:** The file that sets the `max_tokens` parameter for Anthropic models (likely in the `gpt-researcher` component).
-   **Action:** Implement model-specific `max_tokens` limits to ensure that the correct value is used for each model.

## 2. Logging Infrastructure Issues

### 2.1. GPTR Subprocess Error Handling

-   **Issue:** The `gptr_subprocess.py` script does not guarantee that a `[GPTR_END]` event is logged when an exception occurs.
-   **File to Modify:** `api_cost_multiplier/functions/gptr_subprocess.py`
-   **Action:** Wrap the main execution logic in a `try...finally` block to ensure that a `[GPTR_END]` event is always logged, even when an exception occurs.

### 2.2. FPF Batch Mode Events

-   **Issue:** The FPF batch mode may not emit complete events for all runs.
-   **File to Modify:** `api_cost_multiplier/functions/fpf_runner.py`
-   **Action:** Implement per-run error handling in the batch processing loop to ensure that a `[FPF RUN_COMPLETE]` event is always logged for each run, even if an error occurs.

### 2.3. MA_runner Unique Run Identifiers

-   **Issue:** The `MA_runner.py` module does not use unique run identifiers for each MA run.
-   **File to Modify:** `api_cost_multiplier/functions/MA_runner.py`
-   **Action:** Modify the logging statements to generate unique run IDs for each MA run, for example by incorporating the model name and iteration number into the run index.

## 3. Timeline Script Logic Issues

### 3.1. Exact Start+End+Result Match

-   **Issue:** The `timeline_from_logs.py` script requires an exact match of a start event, an end event, and a result for each run.
-   **File to Modify:** `api_cost_multiplier/tools/timeline_from_logs.py`
-   **Action:** Modify the script to be more resilient to missing data, for example by allowing for partial timeline entries for runs that are missing an end event or a result.

### 3.2. t0 Filtering

-   **Issue:** The `t0` filtering logic in `timeline_from_logs.py` may exclude valid runs if the `acm_session.log` file contains data from multiple sessions.
-   **File to Modify:** `api_cost_multiplier/tools/timeline_from_logs.py`
-   **Action:** Modify the script to use a more robust method for determining the start time of the session, for example by using a unique session ID.

### 3.3. No Validation or Error Reporting

-   **Issue:** The `timeline_from_logs.py` script does not provide any validation or error reporting, which makes it difficult to diagnose issues.
-   **File to Modify:** `api_cost_multiplier/tools/timeline_from_logs.py`
-   **Action:** Modify the script to log parsing statistics, warn on excluded runs, and include a debug mode.

## 4. Data Format Issues

### 4.1. MA Model Extraction

-   **Issue:** The `timeline_from_logs.py` script's method for extracting the model name from MA log lines is fragile.
-   **File to Modify:** `api_cost_multiplier/tools/timeline_from_logs.py`
-   **Action:** Improve the regex for extracting the model name, or modify the `MA_runner.py` module to log the model name in a more structured format.

### 4.2. Timestamp Parsing

-   **Issue:** The `timeline_from_logs.py` script's method for parsing timestamps from log lines is not robust.
-   **File to Modify:** `api_cost_multiplier/tools/timeline_from_logs.py`
-   **Action:** Improve the regex for parsing timestamps, and add error handling to log a warning when a malformed timestamp is encountered.

## 5. Concurrency and Race Conditions

### 5.1. Multiple Runs Writing to the Same Log File

-   **Issue:** Multiple runs are writing to the same log file simultaneously, which can lead to interleaved log lines or incomplete writes.
-   **File to Modify:** `api_cost_multiplier/runner.py`
-   **Action:** Implement a file locking mechanism or use a centralized logging service to handle concurrent writes to the same log file.

### 5.2. Timeline Script Invoked Before All Runs Complete

-   **Issue:** The `timeline_from_logs.py` script is invoked before all runs have completed.
-   **File to Modify:** `api_cost_multiplier/runner.py`
-   **Action:** Modify the script to ensure that all runs have completed before the timeline script is invoked, for example by using `asyncio.gather` to wait for all tasks to finish.

## 6. Error Propagation Issues

### 6.1. Tavily API 400 Errors

-   **Issue:** The Tavily API is returning 400 Bad Request errors.
-   **Action:** Investigate the Tavily API integration to determine the cause of the 400 errors. This may involve checking the API key, validating search queries, and implementing rate limiting.

### 6.2. Web Scraping Failures Cascade to Run Failures

-   **Issue:** Web scraping failures are causing runs to fail.
-   **Action:** Fix the scraper configuration, as detailed in section 1.1.

### 6.3. Provider Response Validation Failures

-   **Issue:** Provider responses are failing mandatory checks.
-   **Action:** Improve prompt engineering, implement more robust validation, and add a retry mechanism.
