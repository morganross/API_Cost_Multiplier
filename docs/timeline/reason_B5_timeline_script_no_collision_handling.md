# Timeline Failure Reason B5: Timeline Script Doesn't Handle Run Index Collisions

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A significant issue contributing to the incomplete timeline is that the `timeline_from_logs.py` script does not handle run index collisions. The script assumes that each run will have a unique identifier, and when multiple runs share the same ID, it overwrites the data, leading to an incomplete timeline.

## Evidence

The `timeline_from_logs.py` script uses a dictionary to store `RunRecord` objects, with the `run_id` as the key. When a new run with a duplicate `run_id` is encountered, the existing `RunRecord` is overwritten.

**Example from `timeline_from_logs.py`:**

```python
# MA_START
m = MA_START.search(line)
if m and ts:
    run_index = m.group(1)  # Always "1"
    run_id = f"ma-{run_index}"  # Always "ma-1"
    rec = runs.get(run_id)
    if not rec:
        rec = RunRecord(run_id=run_id, report_type="MA", model="unknown", start_ts=ts)
        runs[run_id] = rec
    else:
        if rec.start_ts is None:
            rec.start_ts = ts  # OVERWRITES previous start_ts!
```

The script does not check if a `RunRecord` with the same `run_id` already exists and has been completed. It simply overwrites the existing record, leading to data loss.

## Impact

Because the script does not handle run index collisions, only the data from the *last* run with a given `run_id` is preserved. All previous runs with the same `run_id` are effectively erased from the timeline. This is a major contributor to the incomplete timeline, as it means that only one of a series of identical runs will ever be recorded.

## Recommendations

To fix this issue, the `timeline_from_logs.py` script should be modified to handle run index collisions gracefully. This can be achieved by:

1.  **Adding a warning for duplicate run IDs:** The script should log a warning when it encounters a duplicate `run_id` that is overwriting an existing `RunRecord`. This will make it easier to identify and debug logging issues in the future.

2.  **Implementing a more robust run tracking mechanism:** Instead of a simple dictionary, the script could use a list of `RunRecord` objects, or a dictionary where the values are lists of `RunRecord` objects. This would allow it to store all runs, even if they have the same `run_id`.

3.  **Improving the run ID generation:** The `MA_runner.py` module should be modified to generate unique run IDs for each MA run, as recommended in the `reason_A3_ma_run_index_collision.md` report. This is the most effective way to prevent run index collisions in the first place.

By implementing these changes, the timeline script will be more resilient to logging errors and will be able to produce a more accurate and complete timeline, even when run index collisions occur.
