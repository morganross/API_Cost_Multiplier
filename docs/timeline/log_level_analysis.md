# Log Level Analysis for Timeline Generation

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Executive Summary

This report analyzes the log level settings for each component (`acm`, `fpf`, `gpt-r`, `ma`, and `eval`) and how they could affect the generation of the timeline. The investigation concludes that the log level settings are **not** the primary cause of the timeline generation failure. The timeline script should function correctly even with the least verbose log level settings, as all necessary events are logged at the `INFO` level or below.

## Analysis of Log Level Settings

### `acm` Logger

-   **Configuration:** The `acm` logger is configured in `runner.py` using `logging_levels.py`.
-   **Log Levels:** The default log levels are "Low" for the console (which maps to `logging.WARNING`) and "Medium" for the file (which maps to `logging.INFO`).
-   **Impact on Timeline:** The `[RUN_START]` and `[FILES_WRITTEN]` events are logged at the `INFO` level, so they are captured by the file log even at the default "Medium" level.

### `eval` Logger

-   **Configuration:** The `eval` logger is configured in `evaluate.py` using `logging_levels.py`.
-   **Log Levels:** The `config.yaml` sets `console_level` to "high" (DEBUG) and `file_level` to "Medium" (INFO).
-   **Impact on Timeline:** The `[EVAL_START]`, `[EVAL_BEST]`, `[EVAL_EXPORTS]`, and `[EVAL_COST]` events are logged at the `INFO` level, so they are captured by the file log.

### `gpt-researcher` Logger

-   **Configuration:** The "scraper" logger is configured in `gpt_researcher/utils/logger.py`.
-   **Log Levels:** The logger's level is hardcoded to `logging.INFO`. This is not affected by `config.yaml`.
-   **Impact on Timeline:** The `[GPTR_START]` and `[GPTR_END]` events are logged by the `SUBPROC_LOGGER` in `runner.py`, not the `gpt-researcher`'s internal logger. The `SUBPROC_LOGGER` is configured to log at the `INFO` level, so these events are captured.

### `fpf` Logger

-   **Configuration:** The `fpf_runner.py` script configures its own logger.
-   **Log Levels:** The logger is hardcoded to `logging.DEBUG` for both console and file output. This is not affected by `config.yaml`.
-   **Impact on Timeline:** The `[FPF RUN_START]` and `[FPF RUN_COMPLETE]` events are logged at the `INFO` level, so they are captured.

### `ma` Logger

-   **Configuration:** The `MA_runner.py` script does not configure its own logger; it relies on the logger configured in `runner.py`.
-   **Log Levels:** The `[MA run X]` events are logged at the `INFO` level, so they are captured by the `acm` logger's file handler.

## Conclusion

The log level settings are not the cause of the timeline generation failure. The timeline script is designed to work with the default log levels, and all necessary events are logged at a level that should be captured by the file logs.

The root causes of the timeline failure are:
-   **Missing end events for failed runs:** When a run fails, it does not always log an end event, which causes the timeline script to exclude it.
-   **MA run index collision:** All MA runs are logged with the same index, causing the timeline script to overwrite the data for each run.
-   **Premature timeline generation:** The timeline script is invoked before all runs have completed.

These issues are detailed in the `timeline_generation_failure_investigation.md` report and the individual reports in the `/docs/timeline/` directory.
