# Timeline Failure Reason G16: Concurrency and Race Conditions

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A potential issue that could contribute to an incomplete timeline is that multiple runs are writing to the same log file simultaneously. FPF batch mode, GPTR concurrent runs, and MA runs all write to the same subprocess log, which can lead to interleaved log lines or incomplete writes.

## Evidence

The `runner.py` script launches multiple subprocesses that all write to the same `acm_subprocess_*.log` file. There is no file locking mechanism in place to ensure that writes are atomic. This could lead to race conditions where multiple processes try to write to the log file at the same time, resulting in corrupted or incomplete log entries.

## Impact

If log lines are interleaved or incomplete, the `timeline_from_logs.py` script may not be able to parse them correctly. This could lead to missing start events, end events, or results, which would cause the corresponding runs to be excluded from the final timeline.

## Recommendations

To fix this issue, the logging infrastructure should be improved to handle concurrent writes to the same log file.

1.  **Implement File Locking:** A file locking mechanism could be implemented to ensure that only one process can write to the log file at a time. This would prevent interleaved log lines and ensure that all log entries are complete.

2.  **Use a Centralized Logging Service:** A more robust solution would be to use a centralized logging service that can handle concurrent writes from multiple processes. This would also provide a more scalable and reliable logging infrastructure for the entire application.

By implementing these changes, the logging infrastructure will be more resilient to concurrency issues, and the timeline script will be more likely to receive complete and accurate log data.
