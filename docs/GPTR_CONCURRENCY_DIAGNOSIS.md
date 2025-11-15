# GPTR Concurrency Issues - Diagnosis

## Problem Statement

Two related issues observed in Nov 14 17:00 run:

1. **First GPTR task takes 20x longer than expected** (14m 8s instead of ~45s)
2. **All remaining GPTR tasks wait until first task completes before running concurrently**

Expected: All 7 GPTR standard tasks should run in parallel from the start.  
Actual: First task runs alone for 14m 8s, then remaining 6 tasks queue up and start.

---

## Root Cause Analysis

### Issue #1: First GPTR Task Duration (14m 8s)

**Timeline:**
- GPTR std gemini-2.5-flash starts: 17:00:24
- GPTR std gemini-2.5-flash ends: 17:14:32
- Duration: 14 minutes 8 seconds

**Normal GPTR duration:** 30-60 seconds (observed with other models)

**Why so long?**
The first GPTR task is running on the same resource that MA tasks need. MA tasks (4x concurrent) occupy the system resources from 17:00:24-17:14:32. The first GPTR task appears to be competing with MA tasks for compute/API resources, causing it to run 20x slower.

**Diagnosis:** Resource contention. The first GPTR task is **not** isolated—it shares semaphore slots or system resources with MA tasks.

---

### Issue #2: All Tasks Wait for First Task to Finish

**Timeline:**
- Task 1 (gemini-2.5-flash) launches: 17:00:24
- Task 1 ends: 17:14:32
- Task 2 (gemini-2.5-flash-lite) launches: 17:14:32 ← waits 14m 8s
- Tasks 3-7 launch: 17:17:28-17:17:30 ← wait even longer

**Why?**
Code in runner.py lines 1343-1350 shows a **blocking gate**:

```python
while True:
    hr = tracker.headroom(low_watermark=1)
    if hr.get("ready", False):
        break
    await asyncio.sleep(0.5)
```

This gate checks FPF headroom **before creating any GPTR tasks**. It blocks the entire task creation loop. Once the first task is created and the gate condition passes, the loop continues—but only one task at a time.

The issue: Tasks are created **inside** the blocking loop, not before it. This serializes task creation.

---

## Are They Related?

**YES. They are the same root cause.**

**The Sequence:**

1. Gate blocks at line 1347, waiting for FPF headroom
2. Headroom becomes available around 17:00:24 (when FPF finishes initial phase)
3. First GPTR task is created and immediately runs
4. Loop continues, but first task is still running, occupying semaphore slot
5. First task runs slowly (14m 8s) because it competes with MA tasks for resources
6. When first task finally ends at 17:14:32, headroom gate is re-evaluated
7. Remaining 6 tasks are created rapidly and launched concurrently

**The fundamental problem:** The headroom gate prevents all GPTR tasks from being queued upfront. Instead, they're queued one-at-a-time as previous tasks complete.

---

## Solution

Move the headroom gate **outside** the task creation loop. Create all GPTR tasks immediately, then enforce the headroom gate on task **execution**, not **creation**.

**Before (current):**
```
Gate checks headroom → Task 1 created → Task 1 runs → Task 1 ends → Gate re-checks → Task 2 created → Task 2 runs...
(sequential)
```

**After (proposed):**
```
All tasks created immediately → Gate checks headroom → Tasks run concurrently as headroom allows
(parallel)
```

This way:
- All 7 GPTR tasks are queued at t=0
- Semaphore limits concurrent execution to 11
- Gate ensures FPF is not overwhelmed
- Result: Better resource utilization, no 14m 8s delays on first task

---

## Technical Details

**Current code flow:**
1. Line 1343-1350: Gate blocks waiting for FPF headroom
2. Line 1366: Semaphore created (max_conc=11)
3. Line 1378: Tasks created in loop **inside** semaphore/after gate
4. First task launches while gate is "open"
5. Subsequent tasks wait for gate to re-evaluate

**Required fix:**
1. Create gate as background coroutine (non-blocking)
2. Create all GPTR tasks upfront (lines 1378 should execute for all entries immediately)
3. Let semaphore manage concurrency (already working correctly)

---

## Expected Improvement

- First GPTR task duration: 14m 8s → ~45s (16x faster)
- Total runtime: 26m 37s → ~24-25m (~8-10% improvement)
- All GPTR tasks launch concurrently instead of serially
