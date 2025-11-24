# MA Concurrent Implementation Plan

## Current State (SEQUENTIAL)
```
ma:gpt-4.1-mini    00:00 -- 03:24 (3:24)
ma:gpt-4.1-nano    03:24 -- 06:25 (3:01)  ← Starts after gpt-4.1-mini ends
ma:gpt-4o          06:25 -- 09:38 (3:13)  ← Starts after gpt-4.1-nano ends
ma:gpt-4o-mini     09:38 -- 13:42 (4:04)  ← Starts after gpt-4o ends
ma:o4-mini         13:42 -- 23:42 (10:00) ← Starts after gpt-4o-mini ends
```

**Problem:** Each MA run waits for the previous one to complete. Total sequential time = 23:42.

---

## Desired State (TRUE CONCURRENT)
```
ma:gpt-4.1-mini    00:00 -- 03:24 (3:24) ┐
ma:gpt-4.1-nano    00:00 -- 03:01 (3:01) ├─ All 5 running simultaneously
ma:gpt-4o          00:00 -- 03:13 (3:13) │  (or limited to max_concurrent_runs=2)
ma:gpt-4o-mini     00:00 -- 04:04 (4:04) │
ma:o4-mini         00:00 -- 10:00 (10:00)┘

Expected total time: ~10:00 (slowest run duration, not sum of all)
```

---

## Root Cause Analysis

The current implementation in `runner.py` lines 1301-1340 creates tasks but they are awaited immediately in a for-loop:

```python
for j, (idx, entry) in enumerate(ma_entries):
    tasks_ma.append(asyncio.create_task(_run_ma_limited(idx, entry)))
    if j < len(ma_entries) - 1 and ma_launch_delay > 0:
        await asyncio.sleep(ma_launch_delay)
```

**Issue:** While tasks are created, the loop includes `await asyncio.sleep()` which blocks the event loop between task creations, and `process_file_run()` itself awaits immediately, preventing true parallelism.

---

## Implementation Plan

### Step 1: Refactor Task Creation Loop
**File:** `runner.py` (lines 1301-1340)

Replace the current for-loop that awaits sleep with a non-blocking task batch approach:

```python
# Create ALL tasks without awaiting in the loop
for idx, entry in ma_entries:
    tasks_ma.append(asyncio.create_task(_run_ma_limited(idx, entry)))

# Apply launch delay only for logging/visibility, not blocking
if ma_launch_delay > 0:
    # Optional: log task creation with staggered timestamps for visibility
    pass

# Await all MA tasks concurrently (not in sequence)
if tasks_ma:
    await asyncio.gather(*tasks_ma, return_exceptions=False)
```

### Step 2: Verify Semaphore Configuration
**File:** `config.yaml` (line 81)

Current config:
```yaml
multi_agent:
  enabled: true
  max_concurrent_runs: 2
  launch_delay_seconds: 0.5
```

The semaphore is set correctly to `max_concurrent_runs: 2`, but the loop blocking is preventing it from taking effect.

### Step 3: Modify `_run_ma_limited` Function
**File:** `runner.py` (inside the MA execution block)

Current structure waits for each task sequentially. Ensure the inner function respects the semaphore:

```python
async def _run_ma_limited(idx0: int, e0: dict):
    async with sem_ma:  # This will limit to max_concurrent_runs
        run_id0 = f"ma-{idx0}"
        _register_run(run_id0)
        try:
            await process_file_run(...)
        finally:
            _deregister_run(run_id0)
```

This is already correct. The problem is the **sequential loop blocking**.

### Step 4: Update Timeline Logging (if needed)
**File:** `logs/acm_session.log`

When MA runs execute truly concurrently, all will have start time ~00:00 and varying end times based on individual run duration, not cumulative.

---

## Expected Outcome After Implementation

Timeline would show:
```
ma:gpt-4.1-mini    00:00 -- 03:24 (3:24)
ma:gpt-4.1-nano    00:00 -- 03:01 (3:01)  ← Starts at 00:00, not 03:24
ma:gpt-4o          00:00 -- 03:13 (3:13)  ← Starts at 00:00, not 06:25
ma:gpt-4o-mini     00:01 -- 04:05 (4:04)  ← Slot 1 available after 3:24, so starts ~00:01
ma:o4-mini         00:01 -- 10:01 (10:00) ← Slot 2 available after 3:01, so starts ~00:01
```

(With semaphore=2, 4th and 5th tasks queue until slots free)

---

## Code Changes Required

### Change 1: Remove Sequential Loop Blocking
**Location:** `runner.py` lines 1331-1340

**Before:**
```python
for j, (idx, entry) in enumerate(ma_entries):
    tasks_ma.append(asyncio.create_task(_run_ma_limited(idx, entry)))
    if j < len(ma_entries) - 1 and ma_launch_delay > 0:
        await asyncio.sleep(ma_launch_delay)  # ← BLOCKING
```

**After:**
```python
for idx, entry in ma_entries:
    tasks_ma.append(asyncio.create_task(_run_ma_limited(idx, entry)))
    # No await/sleep in loop - tasks created instantly
```

### Change 2: Ensure Gather Doesn't Block
**Location:** `runner.py` line 1427 (or wherever MA tasks are awaited)

Verify the await is:
```python
if tasks_ma:
    await asyncio.gather(*tasks_ma, return_exceptions=False)
```

NOT nested inside another loop.

---

## Testing & Validation

1. Run `generate.py` after changes
2. Check logs: All 5 MA runs should have start time `00:00` (or very close)
3. Check timeline: 5 entries all starting around `00:00`, ending at different times
4. Total execution time should be ~10:00 (o4-mini duration) instead of ~23:42

---

## Risks

- If semaphore=2 limit is too tight, may bottleneck
- Concurrent subprocess execution uses more system resources
- If tasks fail, `return_exceptions=False` will fail the entire gather

---

## Success Criteria

✅ All MA tasks launch at approximately the same wall-clock time  
✅ Timeline shows all 5 MA runs starting at 00:00  
✅ Total MA execution time ~10:00 (longest single run)  
✅ No sequential blocking between MA tasks

