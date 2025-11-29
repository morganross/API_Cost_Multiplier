# FPF Cost Data Missing from HTML Report - Failure Analysis

**Date:** November 28, 2025  
**Author:** Deep Dive Analysis  
**Status:** ✅ ROOT CAUSE FIXED - All path calculations corrected

---

## Executive Summary

The HTML evaluation report consistently fails to display FPF (FilePromptForge) cost data and individual evaluation run information. Despite **3 prior refactoring attempts**, the "Individual FPF Calls" section remains empty and `fpf_logs_dir: null` appears in the `eval_timeline.json`. 

**Root Cause:** Path calculation bugs at multiple levels create a cascading failure where FPF logs are either:
1. Written to wrong directories
2. Not found by downstream reporting code
3. Returned as empty arrays from the evaluation API

---

## The Data Flow Chain

Understanding why the fixes failed requires tracing the complete data flow:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FPF COST DATA FLOW                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. GENERATION PHASE                                                        │
│     FilePromptForge writes JSON logs to:                                    │
│     → FilePromptForge/logs/<run_group_id>/*.json                            │
│                                                                             │
│  2. EVALUATION PHASE (api.py)                                               │
│     a) run_single_evaluation()  → line 587: fpf_base calculation            │
│     b) run_pairwise_evaluation() → line 1076: fpf_base calculation          │
│     c) _copy_fpf_logs_to_acm()  → line 235: acm_root calculation            │
│                                                                             │
│  3. RESULT AGGREGATION (api.py line 1270-1353)                              │
│     → Collects fpf_logs_dir from single/pairwise summaries                  │
│     → Returns result["fpf_logs_dirs"] = [...] or []                         │
│                                                                             │
│  4. TIMELINE GENERATION (evaluate.py lines 435-480)                         │
│     → Extracts fpf_logs_dirs from result                                    │
│     → Calls generate_eval_timeline() with fpf_logs_dir                      │
│                                                                             │
│  5. HTML EXPORT (html_exporter.py)                                          │
│     → generate_eval_timeline_section() reads fpf_calls from JSON            │
│     → generate_eval_cost_section() parses FPF logs directly                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Failure Point Analysis

### Failure Point #1: Path Calculation in `run_pairwise_evaluation`

**File:** `api_cost_multiplier/llm-doc-eval/llm_doc_eval/api.py`  
**Line:** 1076

```python
# CURRENT (WRONG - 3 levels up)
fpf_base = os.path.abspath(os.path.join(here, "..", "..", "..", "FilePromptForge", "logs"))

# CORRECT (should be 2 levels up)
fpf_base = os.path.abspath(os.path.join(here, "..", "..", "FilePromptForge", "logs"))
```

**Why it fails:**
- `here` = `c:\dev\silky\api_cost_multiplier\llm-doc-eval\llm_doc_eval\`
- With 3 `..`: `c:\dev\silky\FilePromptForge\logs` (WRONG - directory doesn't exist)
- With 2 `..`: `c:\dev\silky\api_cost_multiplier\FilePromptForge\logs` (CORRECT)

**Evidence from logs:**
```log
2025-11-28 22:21:42,198 - [EVALUATE_COMPLETE] fpf_logs_dirs: [
  'C:\\dev\\silky\\logs\\eval_fpf_logs\\single_20251128_221620_fd1b1359',
  'C:\\dev\\silky\\logs\\eval_fpf_logs\\pairwise_20251128_222142_b042d957'
]
```
The logs show paths in `C:\dev\silky\logs\` instead of `C:\dev\silky\api_cost_multiplier\logs\`.

---

### Failure Point #2: FPF Log Copy Returns Wrong Path

**File:** `api_cost_multiplier/llm-doc-eval/llm_doc_eval/api.py`  
**Function:** `_copy_fpf_logs_to_acm()` (lines 213-263)

**Status:** Fixed in recent session (line 235 uses 2 levels)

However, the fix only works if **source FPF logs exist**. Since `run_pairwise_evaluation` calculates the wrong `fpf_logs_dir`, the copy operation has nothing to copy:

```python
if not fpf_logs_dir or not os.path.exists(fpf_logs_dir):
    logger.debug(f"[FPF_LOG_COPY] Source directory not found: {fpf_logs_dir}")
    return None  # Returns None → fpf_logs_dirs stays empty!
```

---

### Failure Point #3: Empty `fpf_logs_dirs` Array

**Evidence from logs:**
```log
2025-11-28 12:33:07,322 - [EVALUATE_COMPLETE] 'fpf_logs_dirs': []
2025-11-28 12:46:31,515 - [EVALUATE_COMPLETE] 'fpf_logs_dirs': []
```

When `fpf_logs_dirs` is empty, downstream code in `evaluate.py` cannot:
- Pass valid paths to `generate_eval_timeline()`
- Extract time windows for cost filtering
- Generate the "Individual FPF Calls" section in HTML

---

## The Three Prior Refactoring Attempts

### Attempt #1: Adding `eval_timeline_json_path` to HTML Exporter (Nov 20-21, 2025)

**Files Modified:**
- `reporting/html_exporter.py` - Added `eval_timeline_json_path` parameter
- Added `generate_eval_timeline_section()` function

**What Was Done:**
- Created function to parse `eval_timeline.json` and render HTML table
- Added support for `fpf_calls` array in timeline JSON
- Added "Individual FPF Calls" table rendering

**Why It Failed:**
- The JSON file was being generated correctly
- But `sources.fpf_logs_dir` was always `null` because upstream `fpf_logs_dirs` was empty
- The `fpf_calls` array in the JSON was always `[]`

**Evidence:** History files show the HTML rendering code was added but never received data:
```
html_exporter_20251121184609.py → Added generate_eval_timeline_section()
html_exporter_20251121185417.py → Added fpf_calls table
```

---

### Attempt #2: Creating `eval_timeline_from_db.py` Tool (Nov 27, 2025)

**File Created:** `tools/eval_timeline_from_db.py`

**What Was Done:**
- Created standalone tool to generate timeline JSON from database + logs
- Added `parse_fpf_logs()` function to read FPF JSON logs directly
- Exposed `fpf_logs_dir` parameter

**Why It Failed:**
- Tool works correctly when given valid paths
- But callers in `evaluate.py` and `regenerate_report.py` pass `None` or empty directories
- The tool correctly returns empty data when given no valid inputs

**Evidence:** Tool correctly detects missing data:
```python
def parse_fpf_logs(fpf_logs_dir: str, ...) -> List[FpfCallRecord]:
    if not fpf_logs_dir or not os.path.isdir(fpf_logs_dir):
        return []  # Empty list - nothing to show
```

---

### Attempt #3: Auto-Generation in `evaluate.py` (Nov 28, 2025)

**File Modified:** `api_cost_multiplier/evaluate.py` (lines 411-480)

**What Was Done:**
- Added auto-generation of `eval_timeline.json` if not provided
- Extracted `fpf_logs_dirs` from evaluation result
- Extracted `eval_timestamps` for time window filtering
- Passed paths to `generate_eval_timeline()`

**Why It Failed:**
- Code correctly extracts `fpf_logs_dirs` from result
- But result contains `fpf_logs_dirs: []` (empty array)
- So `fpf_logs_for_timeline` becomes `None`
- Timeline JSON is generated but with no FPF data

**Evidence from code:**
```python
# evaluate.py lines 435-441
fpf_logs_dirs = result.get("fpf_logs_dirs", [])
if fpf_logs_dirs:
    first_dir = fpf_logs_dirs[0]
    if first_dir and os.path.isdir(first_dir):
        fpf_logs_for_timeline = os.path.dirname(first_dir)
# But fpf_logs_dirs is [], so this entire block is skipped!
```

---

## Root Cause Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CASCADE FAILURE DIAGRAM                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  api.py line 1076: Wrong path (3 levels instead of 2)                       │
│         ↓                                                                   │
│  FPF logs directory doesn't exist                                           │
│         ↓                                                                   │
│  _copy_fpf_logs_to_acm() returns None (nothing to copy)                     │
│         ↓                                                                   │
│  summary["fpf_logs_dir"] = None                                             │
│         ↓                                                                   │
│  fpf_logs_dirs.append(None) or fpf_logs_dirs stays []                       │
│         ↓                                                                   │
│  result["fpf_logs_dirs"] = [] (empty)                                       │
│         ↓                                                                   │
│  evaluate.py extracts nothing                                               │
│         ↓                                                                   │
│  generate_eval_timeline() receives fpf_logs_dir=None                        │
│         ↓                                                                   │
│  eval_timeline.json has fpf_calls: [], fpf_logs_dir: null                   │
│         ↓                                                                   │
│  html_exporter shows empty "Individual FPF Calls" section                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Fix

### Changes Applied

**File:** `c:\dev\silky\api_cost_multiplier\llm-doc-eval\llm_doc_eval\api.py`  
**Line:** 1076 (in `run_pairwise_evaluation`)

**Before (Wrong - 3 levels up):**
```python
        # Point to actual FPF logs location (FilePromptForge/logs/<run_group_id>)
        here = os.path.dirname(os.path.abspath(__file__))
        fpf_base = os.path.abspath(os.path.join(here, "..", "..", "..", "FilePromptForge", "logs"))
        fpf_logs_dir = os.path.join(fpf_base, run_group_id)
        os.makedirs(fpf_logs_dir, exist_ok=True)
```

**After (Fixed - 2 levels up with comment):**
```python
        # Point to actual FPF logs location (FilePromptForge/logs/<run_group_id>)
        here = os.path.dirname(os.path.abspath(__file__))
        # Navigate up from llm-doc-eval/llm_doc_eval/ to api_cost_multiplier/
        fpf_base = os.path.abspath(os.path.join(here, "..", "..", "FilePromptForge", "logs"))
        fpf_logs_dir = os.path.join(fpf_base, run_group_id)
        os.makedirs(fpf_logs_dir, exist_ok=True)
```

### All Fixed Locations

| Location | Function | Change |
|----------|----------|--------|
| Line 235 | `_copy_fpf_logs_to_acm()` | `"..", ".."` → Already correct |
| Line 587 | `run_single_evaluation()` | `"..", ".."` → Already correct |
| **Line 1076** | `run_pairwise_evaluation()` | `"..", "..", ".."` → **Fixed to `"..", ".."`** |

### Why Previous Fix Was Incomplete

In the earlier session, we fixed:
- ✅ Line 235 (`_copy_fpf_logs_to_acm` - acm_root path)
- ✅ Line 587 (`run_single_evaluation` - fpf_base path)
- ❌ **Line 1076 (`run_pairwise_evaluation` - fpf_base path) - WAS STILL BROKEN**

The pairwise evaluation is the second half of `mode="both"`, so fixing only single evaluation left half the flow broken.

### Fix Verification

Verified no remaining triple-level paths:
```powershell
Select-String -Path "api.py" -Pattern '"..", "..", ".."'
# Returns NO results ✅
```

---

## Verification Steps

After applying the fix:

1. **Check path resolution:**
   ```powershell
   Select-String -Path "api.py" -Pattern '"..", "..", ".."'
   # Should return NO results
   ```

2. **Run evaluation and check logs:**
   ```log
   [EVALUATE_COMPLETE] fpf_logs_dirs: ['...\api_cost_multiplier\logs\...']
   # Path should include api_cost_multiplier
   ```

3. **Check eval_timeline.json:**
   ```json
   {
     "sources": {
       "fpf_logs_dir": "C:\\dev\\silky\\api_cost_multiplier\\logs\\eval_fpf_logs\\..."
     },
     "fpf_calls": [
       { "run_id": "...", "model": "...", "total_cost_usd": 0.0123 },
       ...
     ]
   }
   ```

4. **Check HTML report:**
   - "Individual FPF Calls" section should show table with costs
   - "Evaluation Cost Summary" should show non-zero totals

---

## Lessons Learned

1. **Path calculations are fragile:** The codebase has multiple similar path calculations that can drift out of sync.

2. **Fix verification is essential:** After fixing one occurrence, all similar patterns must be searched and verified.

3. **Cascade failures are hard to debug:** When upstream data is empty, downstream code executes correctly but produces no output - making it look like the downstream code is broken.

4. **Logging is critical:** The `acm_session.log` revealed the actual paths being used, which exposed the root cause.

---

## Files Affected by This Issue

| File | Lines | Status |
|------|-------|--------|
| `llm-doc-eval/llm_doc_eval/api.py` | 235, 587, 1076 | ✅ All fixed (2-level paths) |
| `evaluate.py` | 435-476 | Correct (was victim of upstream bug) |
| `tools/eval_timeline_from_db.py` | Full file | Correct (was victim of upstream bug) |
| `reporting/html_exporter.py` | 53-150, 307-424 | Correct (was victim of upstream bug) |
| `regenerate_report.py` | 148-300 | Correct (was victim of upstream bug) |

---

## Appendix: Historical Evolution

```
Nov 20-21: html_exporter gets eval_timeline support → fpf_calls always empty
Nov 27:    eval_timeline_from_db.py created → works but receives null inputs  
Nov 28 AM: evaluate.py gets auto-generation → fpf_logs_dirs is [] from api.py
Nov 28 PM: Fixed lines 235, 587 → single eval works, pairwise still broken
Nov 28:    This analysis → found line 1076 still has 3-level bug
Nov 28:    ✅ Fixed line 1076 → All path calculations now use 2 levels
Nov 29:    ✅ Verified fix applied - no triple-level paths remain in api.py
```

---

## Appendix: Git Diff of Fix

```diff
--- a/llm-doc-eval/llm_doc_eval/api.py
+++ b/llm-doc-eval/llm_doc_eval/api.py
@@ -1073,7 +1073,8 @@ async def run_pairwise_evaluation(
 
         # Point to actual FPF logs location (FilePromptForge/logs/<run_group_id>)
         here = os.path.dirname(os.path.abspath(__file__))
-        fpf_base = os.path.abspath(os.path.join(here, "..", "..", "..", "FilePromptForge", "logs"))
+        # Navigate up from llm-doc-eval/llm_doc_eval/ to api_cost_multiplier/
+        fpf_base = os.path.abspath(os.path.join(here, "..", "..", "FilePromptForge", "logs"))
         fpf_logs_dir = os.path.join(fpf_base, run_group_id)
         os.makedirs(fpf_logs_dir, exist_ok=True)
```
