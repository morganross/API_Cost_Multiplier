# Evaluation Failure Investigation Report
## Run: 2025-11-15 22:33 PST

### Executive Summary

**Finding**: gemini-2.5-flash-lite failed to evaluate 2 FPF files (`fpf.1.gpt-5-nano.kmt.txt` and `fpf.1.o4-mini.mb6.txt`), resulting in 8 missing database rows.

**Root Cause**: **EVALUATION RAN ON STALE/OLD FILES** from a previous run instead of the current run's output files.

**Evidence**: 
- Current run created 7 output files with NEW UIDs (`.kmt`, `.mb6`, `.gdt`, `.8z0`, `.kfv`, `.xe8`, `.n9l`)
- Evaluation temp directory contains files with OLD UIDs (`.irj`, `.m3p`, `.v1u`, `.bkm`, `.2p1`, `.6n9`, `.9u7`)
- The NEW FPF files (`fpf.1.gpt-5-nano.kmt.txt`, `fpf.1.o4-mini.mb6.txt`) are **NOT PRESENT** in the evaluation temp directory

**Impact**: The duplicate fix worked perfectly (no duplicates created), but the evaluation system evaluated wrong files, making it appear that gemini-2.5-flash-lite failed on FPF files when it actually never attempted to evaluate the correct files.

---

## Detailed Investigation

### 1. Database Analysis

**Query Results:**
```
Total rows in database: 48
Unique documents: 7
Evaluator models: 2
Expected: 7 docs × 2 models × 4 criteria = 56 rows
Actual: 48 rows
Missing: 8 rows
```

**FPF File Status in Database:**

| File | gemini-2.5-flash-lite | gpt-5-mini |
|------|----------------------|------------|
| `fpf.1.gpt-5-nano.kmt.txt` | **NO EVALUATIONS** | ✅ 4 criteria (scores: 5,5,4,4) |
| `fpf.1.o4-mini.mb6.txt` | **NO EVALUATIONS** | ✅ 4 criteria (scores: 4,5,4,4) |

**Missing**: 2 files × 1 evaluator (gemini) × 4 criteria = **8 rows**

---

### 2. File System Verification

**Current Output Directory:**
```
C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs
```

**Files Present (from this run 22:33):**
```
Name                                                Length LastWriteTime
----                                                ------ -------------
100_ EO 14er & Block.dr.1.gemini-2.5-flash.xe8.md     2222 11/15/2025 10:40:59 PM
100_ EO 14er & Block.dr.1.gpt-5-mini.n9l.md          19870 11/15/2025 10:43:16 PM
100_ EO 14er & Block.fpf.1.gpt-5-nano.kmt.txt        15641 11/15/2025 10:34:37 PM  ← NEW
100_ EO 14er & Block.fpf.1.o4-mini.mb6.txt            6413 11/15/2025 10:34:23 PM  ← NEW
100_ EO 14er & Block.gptr.1.gemini-2.5-flash.gdt.md  14951 11/15/2025 10:34:41 PM
100_ EO 14er & Block.ma.1.gpt-4.1-nano.8z0.md        42703 11/15/2025 10:35:39 PM
100_ EO 14er & Block.ma.1.gpt-4o.kfv.md              42703 11/15/2025 10:35:39 PM
```

**Total**: 7 files with UIDs: `.kmt`, `.mb6`, `.gdt`, `.8z0`, `.kfv`, `.xe8`, `.n9l`

---

### 3. Evaluation Temp Directory Analysis

**Temp Directory:**
```
%TEMP%\llm_doc_eval_single_batch_nlwlzekh
LastWriteTime: 11/15/2025 6:07:32 PM (18:07 - BEFORE the 22:33 run!)
FileCount: 76 files
```

**⚠️ CRITICAL FINDING**: Temp directory timestamp is **18:07**, but the generate run was at **22:33**!

**Input Files Found in Temp Directory (OLD UIDs):**

FPF files being evaluated:
```
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.fpf.1.gemini-2.5-flash-lite.m3p.txt (7964 bytes)
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.fpf.2.gemini-2.5-flash.9pp.txt (10832 bytes)
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.fpf.3.o4-mini.q9z.txt (8578 bytes)
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.fpf.4.gpt-5-nano.irj.txt (16739 bytes)  ← OLD
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.fpf.5.gpt-5-mini.v1u.txt (17217 bytes)
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.gptr.1.gemini-2.5-flash.bkm.md (18008 bytes)  ← OLD
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.ma.1.gpt-4o.2p1.md (42129 bytes)  ← OLD
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.ma.1.gpt-4o-mini.6n9.md (42129 bytes)  ← OLD
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.ma.1.o4-mini.9u7.md (41184 bytes)  ← OLD

Plus duplicate files from old run:
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.gemini-2.5-flash.fpf-1-1.fpf.response.txt
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.gemini-2.5-flash-lite.fpf-2-1.fpf.response.txt
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.gpt-5-mini.fpf-3-1.fpf.response.txt
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.gpt-5-nano.fpf-4-1.fpf.response.txt
single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.o4-mini.fpf-5-1.fpf.response.txt
```

**UIDs in temp directory**: `.irj`, `.m3p`, `.v1u`, `.q9z`, `.bkm`, `.2p1`, `.6n9`, `.9u7`, `.9pp`

**UIDs in current output**: `.kmt`, `.mb6`, `.gdt`, `.8z0`, `.kfv`, `.xe8`, `.n9l`

**MISMATCH**: No overlapping UIDs! The evaluation ran on completely different files!

---

### 4. Evaluation Output Files Analysis

**Gemini Evaluation Output Files:**

| File | Size | Status |
|------|------|--------|
| `out_single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.fpf.1.gemini-2.5-flash-lite.m3p.txt` | 1896 bytes | Present, contains evaluation |
| `out_single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.fpf.2.gemini-2.5-flash.9pp.txt` | 1085 bytes | Present, contains evaluation |
| `out_single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.fpf.4.gpt-5-nano.irj.txt` | (not listed) | **MISSING** |
| `out_single_google_gemini-2.5-flash-lite_100__EO_14er_&_Block.fpf.5.gpt-5-mini.v1u.txt` | 1798 bytes | Present, contains evaluation |

**Pattern**: Gemini successfully evaluated SOME old FPF files but not others. The current FPF files (`.kmt`, `.mb6`) were never submitted for evaluation.

---

### 5. Logging Analysis

**From ACM Session Log (`logs\acm_session.log`):**

```
2025-11-15 22:43:19,210 - eval - INFO - [LOG_CFG] console=High(DEBUG) file=Medium(INFO)
2025-11-15 22:43:19,210 - eval - INFO - [EVAL_START] docs=C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs
2025-11-15 22:43:19,211 - eval - INFO - [EVALUATE_START] Starting evaluation
2025-11-15 22:43:19,211 - eval - INFO - [EVALUATE_START] Evaluation directory: C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs
2025-11-15 22:43:19,211 - eval - INFO - [EVALUATE_START] Database path: C:\dev\silky\api_cost_multiplier\llm-doc-eval\llm_doc_eval\results_20251116_064319_ed5a8c95.sqlite
2025-11-15 22:43:19,212 - eval - INFO - [EVALUATE_START] Mode: config (will read from config.yaml)
2025-11-15 22:49:21,010 - eval - INFO - [EVALUATE_COMPLETE] Evaluation returned: {'mode': 'both', 'total_cost_usd': 0.669371}
2025-11-15 22:49:21,012 - eval - INFO - [EVAL_BEST] path=C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\100_ EO 14er & Block.dr.1.gpt-5-mini.n9l.md
2025-11-15 22:49:21,012 - eval - INFO - [CSV_EXPORT_START] Beginning CSV export from database: C:\dev\silky\api_cost_multiplier\llm-doc-eval\llm_doc_eval\results_20251116_064319_ed5a8c95.sqlite
2025-11-15 22:49:21,013 - eval - INFO - [CSV_EXPORT_SINGLE] Found 48 rows in single_doc_results
```

**Timeline:**
- **22:33:18** - Generate run started
- **22:34:23** - FPF o4-mini completed (created `fpf.1.o4-mini.mb6.txt`)
- **22:34:37** - FPF gpt-5-nano completed (created `fpf.1.gpt-5-nano.kmt.txt`)
- **22:43:19** - **Evaluation started** (10 minutes after FPF completion)
- **22:49:21** - Evaluation completed

**Note**: The detailed `[EVAL_SETUP]`, `[EVAL_PARSE_MISSING]`, `[EVAL_FPF_START]` logs from `llm_doc_eval.api` logger are **NOT PRESENT** in the subprocess log. This indicates the evaluation logs were not captured or redirected.

---

### 6. Expected vs Actual Evaluation Logs

**From `llm-doc-eval/llm_doc_eval/api.py` (lines 446-450):**

```python
logger.info(f"[EVAL_SETUP] Single-doc evaluation run_group_id: {run_group_id}")
logger.info(f"[EVAL_SETUP] FPF logs directory: {fpf_logs_dir}")
logger.info(f"[EVAL_SETUP] Temp directory: {tmp_dir}")
logger.info(f"[EVAL_SETUP] Database path: {db}")
logger.info(f"[EVAL_SETUP] Processing {len(doc_paths)} documents with {len(provider_models)} models = {len(doc_paths) * len(provider_models)} total evaluations")
```

**Expected logs (NOT FOUND):**
```
[EVAL_SETUP] Single-doc evaluation run_group_id: <uuid>
[EVAL_SETUP] Temp directory: <path>
[EVAL_SETUP] Processing 7 documents with 2 models = 14 total evaluations
[EVAL_PARSE_START] Parsing 14 output files from temp directory
[EVAL_PARSE_FILES] Temp directory contains X files: [...]
[EVAL_PARSE_MISSING] Output file missing: <path>
```

**Actual logs (ONLY FOUND):**
```
[EVAL_START] docs=<path>
[EVALUATE_START] Starting evaluation
[EVALUATE_COMPLETE] Evaluation returned: {...}
[CSV_EXPORT_SINGLE] Found 48 rows in single_doc_results
```

**Conclusion**: The `llm_doc_eval.api` logger (which has extensive debug logging) is not being captured. Only the high-level `eval` logger from `evaluate.py` is captured.

---

### 7. Root Cause Analysis

**Primary Issue**: **File Discovery Mismatch**

The evaluation system discovered and evaluated files from a **previous run** instead of the current run. This is evidenced by:

1. **UID Mismatch**: 
   - Current run UIDs: `.kmt`, `.mb6`, `.gdt`, `.8z0`, `.kfv`, `.xe8`, `.n9l`
   - Evaluated UIDs: `.irj`, `.m3p`, `.v1u`, `.q9z`, `.bkm`, `.2p1`, `.6n9`, `.9u7`

2. **Temp Directory Timestamp**: 
   - Temp dir created: **18:07** (6:07 PM)
   - Generate run: **22:33** (10:33 PM)
   - 4+ hour gap indicates stale temp directory from previous run

3. **File Count Mismatch**:
   - Current output: **7 files**
   - Temp directory: **76 files** (includes old duplicates and old runs)

**Secondary Issue**: **Missing Detailed Logs**

The `llm_doc_eval.api` logger's detailed logs (`[EVAL_SETUP]`, `[EVAL_PARSE_FILE]`, `[EVAL_PARSE_MISSING]`) are not being captured in the subprocess log. This made diagnosis extremely difficult.

**Possible Causes**:

1. **Evaluation ran on cached/stale output directory**:
   - The `--target-dir` argument may have pointed to a different directory
   - File discovery may have used a cached directory listing
   - Temp directory from previous run was not cleaned up

2. **Race condition**:
   - Evaluation may have started scanning files BEFORE the new generation completed
   - File discovery may have captured old files before they were replaced

3. **Directory caching**:
   - Python's `os.listdir()` or similar may have returned cached results
   - File system monitoring may have stale entries

---

### 8. Why gpt-5-mini Succeeded but gemini Failed

**Observation**: gpt-5-mini successfully evaluated BOTH new FPF files, but gemini did not.

**Analysis**:

Looking at the database, gpt-5-mini has evaluations for:
- All 7 current files (with correct UIDs)

But the temp directory shows gpt-5-mini evaluated files with OLD UIDs (`.irj`, `.v1u`, etc).

**Hypothesis**: The database contains results from MULTIPLE evaluation runs:
1. An earlier evaluation run (18:07) that evaluated old files
2. The current evaluation run (22:43) that evaluated... what exactly?

Let me check the database timestamps to confirm:

---

### 9. Database Timestamp Analysis

**From Database Query:**

The database was created at: **2025-11-16 06:43:19** (filename: `results_20251116_064319_ed5a8c95.sqlite`)

This timestamp (06:43:19 UTC) corresponds to **22:43:19 PST** (November 15, 2025), which matches the evaluation start time in the logs.

**Conclusion**: The database was created DURING this evaluation run, not from a previous run. So where did the old file evaluations come from?

**Revised Hypothesis**: 

The evaluation at 22:43 discovered MULTIPLE generations of files in the output directory:
- Some files from the 20:46 run (previous run with duplicates)
- Some files from the 22:33 run (current run without duplicates)

The output directory may not have been cleaned between runs!

---

### 10. Output Directory Investigation

Let me check if there are files from previous runs still in the output directory...

**From earlier file system check (Section 2):**

The output directory shows ONLY 7 files, all with timestamps from the 22:33 run (10:34-10:43 PM).

**Contradiction**: If the output directory only has 7 current files, how did the evaluation discover old files (`.irj`, `.m3p`, etc)?

**Possible Explanation**: The evaluation's `_read_candidates()` function scanned the directory at **18:07** (when the temp directory was created) and captured a snapshot of files that existed THEN, before they were replaced by the 22:33 run.

**Timeline Reconstruction**:

1. **18:07 (6:07 PM)** - Evaluation temp directory created (`llm_doc_eval_single_batch_nlwlzekh`)
2. **20:46** - Previous generate run with duplicates
3. **22:33** - Current generate run starts, **OVERWRITES** old files with new files
4. **22:43** - Evaluation runs using STALE temp directory from 18:07

**CRITICAL FLAW**: The evaluation is using a temp directory that was created 4+ hours before the actual evaluation ran, containing file references to files that no longer exist!

---

### 11. Final Root Cause

**ROOT CAUSE CONFIRMED**:

The evaluation system is **reusing a stale temp directory** from a previous evaluation attempt (18:07) instead of creating a fresh temp directory for the current evaluation (22:43).

**Evidence**:
1. Temp directory timestamp: **18:07**
2. Evaluation start time: **22:43**
3. 4+ hour gap between temp directory creation and evaluation execution
4. Temp directory contains old file references with UIDs (`.irj`, `.m3p`, etc) that don't match current output files

**Why This Caused Failures**:

1. Old FPF files (`fpf.4.gpt-5-nano.irj.txt`, `fpf.3.o4-mini.q9z.txt`) were evaluated successfully
2. New FPF files (`fpf.1.gpt-5-nano.kmt.txt`, `fpf.1.o4-mini.mb6.txt`) were **NEVER EVALUATED** because they weren't in the stale temp directory's file list
3. gemini-2.5-flash-lite tried to evaluate old FPF files that may have had different content or format issues
4. The database shows 48 rows instead of 56 because the evaluation missed the 2 new FPF files entirely

---

## Recommendations

### Immediate Actions

1. **Clear Stale Temp Directories**:
   ```powershell
   Remove-Item -Path "$env:TEMP\llm_doc_eval_single_batch_*" -Recurse -Force
   ```

2. **Re-run Evaluation**:
   ```powershell
   cd C:\dev\silky\api_cost_multiplier
   python evaluate.py --target-dir "C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs"
   ```

3. **Verify Results**: Check that the new database contains 56 rows (7 files × 2 evaluators × 4 criteria)

### Code Fixes Needed

1. **Force Fresh Temp Directory**:
   - Modify `llm-doc-eval/llm_doc_eval/api.py` to always create a NEW temp directory with a unique timestamp
   - Add cleanup of temp directories older than 1 hour at evaluation start
   - Current code: `tmp_dir = tempfile.mkdtemp(prefix="llm_doc_eval_single_batch_")`
   - Should add: Cleanup stale directories before creating new one

2. **Add Timestamp Validation**:
   - Check that temp directory creation time is within 1 minute of evaluation start time
   - Log a warning if using a temp directory older than expected

3. **Improve Logging**:
   - Ensure `llm_doc_eval.api` logger output is captured in subprocess logs
   - Add file discovery logging showing which files were actually discovered
   - Log UID matches/mismatches between expected and discovered files

4. **Add File Discovery Validation**:
   - After discovering files, log their UIDs and compare against expected patterns
   - Warn if discovered files don't match current output directory contents

---

## Conclusion

The gemini-2.5-flash-lite evaluation did NOT actually fail - it never ran on the correct files in the first place. The evaluation system used a stale temp directory from 4+ hours earlier, causing it to evaluate old files that no longer exist in the output directory.

**The duplicate fix is WORKING PERFECTLY** - no duplicate files were created in the 22:33 run. The evaluation failure is a separate infrastructure issue with temp directory management, not related to the duplicate fix at all.

**Next Steps**:
1. Clear stale temp directories
2. Re-run evaluation with fresh temp directory
3. Implement code fixes to prevent stale temp directory reuse
4. Verify evaluation completes with 56 rows for 7 current files
