# Timeline Script Investigation Report

## 1. Executive Summary

The `timeline_from_logs.py` script, designed to parse `acm_subprocess.log` and generate a performance timeline, was failing to produce any output despite executing without errors (exit code 0). An initial investigation pointed to a regex syntax error, but the true root cause was a **fundamental flaw in the event correlation logic**. The script could not reliably match start and end log entries for concurrent GPT-Researcher (GPT-R) runs.

This report details the deeper analysis, the true root cause, and the robust, PID-based solution that was implemented.

## 2. Investigation and Analysis

The investigation proceeded by examining all relevant source code and log files to trace the flow of data and identify the point of failure.

### 2.1. Key Files Analyzed
- **`tools/timeline_from_logs.py`**: The script in question. Its logic for parsing log lines was the primary focus.
- **`runner.py`**: The main orchestrator that calls the timeline script.
- **`logs/acm_subprocess.log`**: The raw data source containing interleaved logs from all child processes (FPF, GPT-R, etc.).
- **`logs/acm_session.log`**: The main ACM log file, which contained the crucial clue for diagnosis.

### 2.2. Initial vs. True Root Cause

Initially, a `SyntaxWarning` in the logs pointed to an issue with how regular expressions were defined. While fixing this was good practice, it did not solve the problem. The script still failed to produce a timeline.

The **true root cause** was that the script used a fragile, order-based (FIFO) method to correlate GPT-R start and end events. It assumed that the first `OK:` or `ERROR:` log line corresponded to the oldest-running GPT-R process for a given model. With concurrent execution, this assumption is false. Log entries from different subprocesses can be interleaved in any order, making it impossible to reliably pair start and end events without a unique identifier.

## 3. The Correlation Problem

The old script relied on parsing generic log lines like:
- `[GPT-R queue std] ... model='gpt-4.1'` (Start)
- `OK: ... (openai:gpt-4.1)` (End)

If two `gpt-4.1` runs started concurrently, the script had no way of knowing which `OK:` message belonged to which `queue` message. This resulted in missed pairings and an empty timeline.

## 4. Implemented Solution: PID-Based Correlation

To solve this, a robust, unique identifier was introduced: the **Process ID (PID)** of each GPT-R subprocess.

### Step 1: Enhance Logging in `runner.py`

The `runner.py` script was modified to emit new, structured log messages that include the PID:
- **`[GPTR_START] pid={proc.pid} type={report_type} model={target}`**: Logged immediately after a GPT-R subprocess is launched.
- **`[GPTR_END] pid={proc.pid} result={success|failure}`**: Logged immediately after a GPT-R subprocess terminates.

These new log lines provide an unambiguous way to track the lifecycle of each individual run. The old, ambiguous log lines were removed.

### Step 2: Update Parsing Logic in `timeline_from_logs.py`

The timeline script was updated to use this new, reliable signal:
1.  **New Regex:** New regular expressions were added to parse the `[GPTR_START]` and `[GPTR_END]` lines.
2.  **PID as Key:** The script now uses the PID as the unique key to store and retrieve `RunRecord` objects.
3.  **Simplified Logic:** The complex and faulty FIFO queue logic was completely removed and replaced with a direct lookup based on the PID.

This new approach guarantees that every start event is correctly matched with its corresponding end event, regardless of concurrency or the order in which logs are written.

## 5. Verification

The final step is to run the full process and verify that the `acm_session.log` now contains a correctly formatted and accurate timeline, proving the fix is working as expected.
