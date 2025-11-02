# Timeline Failure Reason E12: t0 Filtering May Exclude Valid Runs

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A potential issue that could contribute to an incomplete timeline is the `t0` filtering logic in `timeline_from_logs.py`. The script uses the timestamp of the last `[LOG_CFG]` entry in `acm_session.log` as the start time (`t0`) for the timeline. Any runs that started before this time will be excluded from the final timeline.

## Evidence

The `timeline_from_logs.py` script includes the following logic:

```python
# Determine t0. Prefer the run start from acm_session.log if available.
# Otherwise, fall back to the earliest event in the subprocess log.
if not complete:
    return []

t0 = run_start_ts
if not t0:
    # Fallback if acm_session.log couldn't be read or parsed
    t0 = min(r.start_ts for r in complete if r.start_ts is not None)

# Filter out events that happened before our run started
complete = [r for r in complete if r.start_ts >= t0]
```

The `run_start_ts` is determined by finding the LAST `[LOG_CFG]` entry in `acm_session.log`:

```python
if acm_log_path and os.path.isfile(acm_log_path):
    with open(acm_log_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if ACM_LOG_CFG.search(line):
                ts = parse_ts(line)
                if ts:
                    run_start_ts = ts # Keep the last one found
```

If `acm_session.log` contains data from multiple sessions, and the last `[LOG_CFG]` entry is not the one corresponding to the current session, then valid runs from the current session could be excluded from the timeline.

## Impact

If the `t0` value is not correctly determined, the timeline script may filter out valid runs that occurred after the start of the current session but before the incorrect `t0`. This would lead to an incomplete and inaccurate timeline.

## Recommendations

To fix this issue, the `t0` filtering logic in `timeline_from_logs.py` should be made more robust.

1.  **Use a Unique Session ID:** The `runner.py` script could generate a unique session ID at the start of each run and pass it to all subprocesses. This session ID could then be included in all log messages, allowing the timeline script to filter for events from the current session only.

2.  **Improve `t0` Determination:** The timeline script could be modified to look for the *first* `[LOG_CFG]` entry in the `acm_session.log` file, or to use the timestamp of the first event in the `acm_subprocess_*.log` file as a fallback.

By implementing these changes, the `t0` filtering logic will be more reliable, and the timeline script will be less likely to exclude valid runs from the final timeline.
