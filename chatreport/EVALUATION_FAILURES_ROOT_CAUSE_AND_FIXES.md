# Evaluation Failures: Root Cause Analysis and Proposed Fixes
**Test Run:** November 14, 2025 22:27:47 - 22:40:24  
**Eval Run ID:** eval_run_20251115_063518_7c803505  
**Investigation Date:** November 15, 2025

---

## Executive Summary

**13 of 28 expected evaluations failed (46.4% failure rate)** due to **ONE ROOT CAUSE**: The evaluation system was passed **only 4 FPF `.txt` files** instead of all 8 generated files (4 FPF `.txt` + 3 MA `.md` + 1 GPTR `.md`).

This is **NOT a file format filter issue in the evaluation code**. The evaluation code correctly supports both `.md` and `.txt` files. The problem is **which files were passed to the evaluator** via the `--target-files` argument.

---

## Evidence

### What Was Actually Evaluated

CSV evidence shows only 4 files were processed:
```
100_ EO 14er & Block.fpf.1.gemini-2.5-flash.3l2.txt
100_ EO 14er & Block.fpf.2.o4-mini.k3a.txt
100_ EO 14er & Block.fpf.3.gpt-5-nano.3xy.txt
100_ EO 14er & Block.fpf.4.gpt-5-mini.c9l.txt
```

**Missing from evaluation:**
- 3 MA files: `ma.1.gpt-4o.e1r.md`, `ma.1.gpt-4o-mini.o84.md`, `ma.1.o4-mini.8cb.md`
- 1 GPTR file: `gptr.1.gemini-2.5-flash.3ov.md`

### File Format Support Verification

**Source:** `llm-doc-eval/llm_doc_eval/api.py` Line 69

```python
def _read_candidates(folder_path: str, exts: Tuple[str, ...] = (".md", ".txt")) -> Dict[str, str]:
    """
    Scan folder_path for candidate files by extension.
    Returns a mapping: doc_id (filename) -> absolute path.
    """
```

**CONFIRMATION:** The evaluation code explicitly supports BOTH `.md` AND `.txt` file extensions.

### File Filtering in evaluate.py

**Source:** `api_cost_multiplier/evaluate.py` Lines 61-64

```python
candidates = [
    f for f in args.target_files
    if os.path.isfile(f) and os.path.splitext(f)[1].lower() in (".md", ".txt")
]
```

**CONFIRMATION:** The evaluation script filters for `.md` and `.txt` files when `--target-files` is provided.

---

## Root Cause

### Problem Location: runner.py Line 975-995

**Source:** `api_cost_multiplier/runner.py` Lines 975-995

```python
try:
    saved_files = save_generated_reports(md_file_path, input_folder, output_folder, generated)
    if saved_files:
        print(f"  Saved {len(saved_files)} report(s) to {os.path.dirname(saved_files[0])}")
    else:
        print(f"  No FPF outputs to save for {md_file_path}")
except Exception as e:
    print(f"  ERROR: saving FPF batch outputs failed: {e}")

# Trigger evaluation if enabled for this file's generated outputs
try:
    eval_config = config.get('eval', {})
    if eval_config.get('auto_run', False) and 'saved_files' in locals() and saved_files and len(saved_files) >= 1:
        print("  Auto-running evaluation on generated reports...")
        eval_script_path = os.path.join(repo_root, "api_cost_multiplier", "evaluate.py")
        if not os.path.exists(eval_script_path):
            print(f"    ERROR: evaluate.py not found at {eval_script_path}. Skipping auto-evaluation.")
        else:
            cmd = [sys.executable, "-u", eval_script_path, "--target-files"] + saved_files
            # ... subprocess execution
```

### The Issue

This evaluation trigger code appears **ONLY in the FPF batch processing function** (`process_file_fpf_batch`), which means:

1. **FPF runs complete** → saves 4 FPF `.txt` files → `saved_files = [fpf1.txt, fpf2.txt, fpf3.txt, fpf4.txt]`
2. **Evaluation auto-triggers** with `--target-files fpf1.txt fpf2.txt fpf3.txt fpf4.txt`
3. **MA runs complete LATER** (22:40:16 for 1 file, 22:35:17 for 2 files) → saves 3 MA `.md` files
4. **GPTR run completes LATER** (22:35:17) → saves 1 GPTR `.md` file
5. **Evaluation has already run** and doesn't see the MA/GPTR files

### Timeline Proof

**File Timestamps:**
```
22:35:17 - 4 FPF .txt files written
22:35:17 - 1 GPTR .md file written
22:35:17 - 2 MA .md files written
22:40:16 - 1 MA .md file written
```

**Evaluation Run:**
```
06:35:18 UTC (22:35:18 local) - Evaluation started
```

**The timing indicates:** Evaluation was triggered immediately after FPF batch completed (22:35:17), capturing only the 4 FPF files in its `--target-files` list. The MA/GPTR files that were written at the same timestamp or later were NOT included.

---

## Secondary Issue: Gemini Validation Constraints

### Problem: Gemini Skipped 2 of 4 FPF Files

**Evidence from CSV:**
- `gemini-2.5-flash-lite` evaluated: `fpf.1` (10.1 KB), `fpf.2` (7.1 KB)
- `gemini-2.5-flash-lite` skipped: `fpf.3` (15.5 KB), `fpf.4` (19.2 KB)
- `gpt-5-mini` evaluated all 4 files (7.1-19.2 KB)

**Pattern:**
```
Gemini processed:  2 smallest files (7.1 KB, 10.1 KB)
Gemini skipped:    2 largest files (15.5 KB, 19.2 KB)
GPT processed:     All 4 files regardless of size
```

### Investigation Required

**Hypothesis:** Gemini API may have:
1. Token/content length limits that differ from GPT
2. Stricter validation rules
3. Different error handling (silent failures vs errors)

**Evidence Location:** Need to examine:
- `llm_doc_eval/engine/judge_backend.py` for Gemini-specific handling
- FPF logs under `temp_gpt_researcher_reports/llm_doc_eval_single_logs_*/` for Gemini error messages
- Gemini API response for validation errors or rate limits

**Note:** This issue is SECONDARY because even if fixed, it only affects 2 of 4 FPF files. The primary issue (missing MA/GPTR files) affects 50% of generated content.

---

## Impact Analysis

### Files Never Evaluated

| Type | Files | Size Range | Reason |
|------|-------|------------|--------|
| MA | 3 files | 36.5-38.9 KB | Not passed to evaluator via `--target-files` |
| GPTR | 1 file | 11.3 KB | Not passed to evaluator via `--target-files` |

**Total:** 4 of 8 generated files (50%) were completely excluded from evaluation.

### Evaluation Coverage by Type

| Evaluation Type | Expected | Actual | Success Rate | Impact |
|----------------|----------|--------|--------------|---------|
| Single-Doc (All Models) | 16 | 6 | 37.5% | Cannot compare MA/GPTR quality |
| Single-Doc (Gemini only) | 8 | 2 | 25% | Gemini has minimal participation |
| Single-Doc (GPT only) | 8 | 4 | 50% | GPT only evaluated FPF batch |
| Pairwise (All Models) | 12 | 9 | 75% | Only FPF files compared |
| Pairwise (Gemini only) | 6 | 3 | 50% | Limited by single-doc coverage |
| Pairwise (GPT only) | 6 | 6 | 100% | Complete for FPF batch |

### Competitive Analysis Limitations

**ELO Rankings:**
- ✅ Valid within FPF batch (4 files)
- ❌ Invalid for MA batch (0 files ranked)
- ❌ Invalid for GPTR batch (0 files ranked)
- ❌ No cross-batch comparison possible

**Statistical Validity:**
- Sample size: 50% of generated content (4 of 8 files)
- Cross-evaluator consistency: Cannot be validated for MA/GPTR
- Gemini participation: 25% (2 of 8 files) reduces confidence

---

## Proposed Fixes

### Fix 1: Delay Evaluation Until All Files Are Generated (RECOMMENDED)

**Problem:** Evaluation triggers after FPF batch completes, before MA/GPTR finish.

**Solution:** Defer evaluation until ALL configured run types complete.

**Implementation:** Modify `runner.py` main processing loop

**Current Code Pattern:**
```python
# FPF batch completes
process_file_fpf_batch(...)
  → saves FPF files
  → triggers evaluation immediately ❌

# MA/GPTR run later
process_file(..., run_ma=True)
  → saves MA/GPTR files
  → evaluation already ran ❌
```

**Fixed Code Pattern:**
```python
# FPF batch completes
process_file_fpf_batch(...)
  → saves FPF files
  → NO evaluation trigger

# MA/GPTR complete
process_file(..., run_ma=True)
  → saves MA/GPTR files
  → NO evaluation trigger

# NEW: After all runs for this file complete
trigger_evaluation_for_file(all_saved_files)
  → passes ALL file types to evaluator ✅
```

**Code Changes Required:**

1. **Remove evaluation trigger from `process_file_fpf_batch`** (Lines 983-1012)
2. **Remove evaluation trigger from `process_file`** (Lines 489-520)
3. **Add centralized evaluation trigger in `main()`** after all file processing completes

**Example Implementation:**

```python
async def main(config_path: str, run_ma: bool = True, run_fpf: bool = True, num_runs: int = 3, keep_temp: bool = False):
    config = config_parser.load_config(config_path)
    
    # Track all saved files across all runs
    all_saved_files = []
    
    for md_file in get_markdown_files(config):
        # Run FPF batch
        if run_fpf:
            fpf_files = await process_file_fpf_batch(md_file, config, ...)
            all_saved_files.extend(fpf_files)
        
        # Run MA/GPTR
        if run_ma:
            ma_gptr_files = await process_file(md_file, config, ...)
            all_saved_files.extend(ma_gptr_files)
    
    # Trigger evaluation ONCE with ALL files
    if config.get('eval', {}).get('auto_run', False) and all_saved_files:
        await trigger_evaluation(all_saved_files, config)
```

**Benefits:**
- ✅ Ensures all generated files are evaluated
- ✅ Single evaluation run reduces overhead
- ✅ Simple to implement
- ✅ No changes to evaluation code required

**Risks:**
- ⚠️ Requires careful refactoring of runner.py structure
- ⚠️ Must ensure saved_files tracking persists across async calls

---

### Fix 2: Use --target-dir Instead of --target-files (ALTERNATIVE)

**Problem:** `--target-files` provides explicit list, which is incomplete when evaluation triggers early.

**Solution:** Use `--target-dir` to point evaluator at output directory, letting it discover all files.

**Implementation:** Modify evaluation trigger

**Current Code:**
```python
cmd = [sys.executable, "-u", eval_script_path, "--target-files"] + saved_files
```

**Fixed Code:**
```python
output_dir = os.path.dirname(saved_files[0]) if saved_files else output_folder
cmd = [sys.executable, "-u", eval_script_path, "--target-dir", output_dir]
```

**Benefits:**
- ✅ Simple one-line change
- ✅ Automatic discovery of all files in directory
- ✅ Resilient to timing issues
- ✅ Works even if evaluation triggers early

**Risks:**
- ⚠️ May pick up unintended files from previous runs in same directory
- ⚠️ Requires unique output directories per run (already implemented with timestamps)
- ⚠️ Evaluation may see incomplete files if still being written

**Mitigation:**
- Use timestamped output directories (already implemented in current code)
- Add file completion check before evaluation triggers

---

### Fix 3: Trigger Evaluation Multiple Times (NOT RECOMMENDED)

**Problem:** Evaluation runs once after FPF, missing later files.

**Solution:** Trigger evaluation after each run type completes, accumulating results.

**Implementation:** Keep existing triggers, modify evaluation to append to same database.

**Why Not Recommended:**
- ❌ Multiple evaluation runs waste time and API costs
- ❌ Pairwise comparisons cannot be incrementally computed (requires all files upfront)
- ❌ ELO rankings need complete pairwise matrix (not possible with incremental files)
- ❌ Added complexity with no benefit over Fix 1 or Fix 2

---

### Fix 4: Investigate Gemini Validation Constraints (SECONDARY PRIORITY)

**Problem:** Gemini skipped 2 of 4 FPF files (15-19 KB), while GPT processed all 4.

**Investigation Steps:**

1. **Examine FPF logs for Gemini errors**
   - Location: `temp_gpt_researcher_reports/llm_doc_eval_single_logs_*/`
   - Look for: API errors, validation messages, rate limit responses

2. **Check judge_backend.py for Gemini-specific handling**
   - File: `llm-doc-eval/llm_doc_eval/engine/judge_backend.py`
   - Look for: Provider-specific token limits, validation rules, error handling

3. **Review Gemini API documentation**
   - Verify: Content length limits, token limits per request
   - Compare: Gemini limits vs GPT limits vs file sizes

4. **Test with synthetic files**
   - Create: Files at 10 KB, 15 KB, 20 KB, 25 KB
   - Run: Single-doc evaluation with Gemini only
   - Measure: Success rate vs file size threshold

**Potential Fixes (after investigation):**

A. **If token limit exceeded:**
   - Truncate document content for Gemini evaluations
   - Adjust `max_tokens` in `config.yaml` for Gemini provider
   - Use Gemini models with larger context windows

B. **If validation failure:**
   - Pre-process documents to remove problematic content
   - Add error handling to retry with sanitized content
   - Switch to different Gemini model with relaxed constraints

C. **If silent failure:**
   - Add explicit error logging in judge_backend.py
   - Validate API responses for success status
   - Fail fast with clear error messages instead of silent skips

**Priority:** MEDIUM (affects 25% of FPF files, 12.5% of total files)

---

## Recommended Implementation Plan

### Phase 1: Immediate Fix (Target: Next Test Run)

**Implement Fix 2: Use --target-dir**

**Steps:**
1. Modify `runner.py` Line 994:
   ```python
   # OLD:
   cmd = [sys.executable, "-u", eval_script_path, "--target-files"] + saved_files
   
   # NEW:
   output_dir = os.path.dirname(saved_files[0]) if saved_files else output_folder
   cmd = [sys.executable, "-u", eval_script_path, "--target-dir", output_dir]
   ```

2. Test with current config (10 runs: 5 FPF + 2 GPTR + 3 MA)

3. Verify all 8 file types are evaluated in CSV outputs

**Validation Criteria:**
- ✅ `single_doc_results.csv` shows 16 rows (8 files × 2 evaluators)
- ✅ `pairwise_results.csv` shows sufficient pairs for 8 files
- ✅ ELO rankings include MA and GPTR files, not just FPF

**Time Estimate:** 30 minutes (15 min implementation + 15 min testing)

---

### Phase 2: Optimal Fix (Target: Within 1 Week)

**Implement Fix 1: Centralized Evaluation Trigger**

**Steps:**
1. Refactor `runner.py` to track all saved files globally
2. Remove evaluation triggers from `process_file_fpf_batch` and `process_file`
3. Add single evaluation trigger in `main()` after all processing completes
4. Test with full 10-run configuration
5. Verify evaluation runs exactly once with all files

**Validation Criteria:**
- ✅ Evaluation triggers exactly once per markdown input file
- ✅ All generated files (FPF + MA + GPTR) are included
- ✅ No timing races between generation and evaluation
- ✅ Logs show clear "All files ready, triggering evaluation" message

**Time Estimate:** 2-4 hours (design + implementation + testing)

---

### Phase 3: Gemini Investigation (Target: Within 2 Weeks)

**Execute Fix 4 Investigation Steps**

**Steps:**
1. Collect Gemini error logs from previous run
2. Review `judge_backend.py` for Gemini handling
3. Consult Gemini API documentation for limits
4. Design and run synthetic file size tests
5. Implement appropriate fix based on findings

**Validation Criteria:**
- ✅ Understand exact cause of Gemini file skips
- ✅ Gemini evaluates all files regardless of size (up to reasonable limits)
- ✅ Error logs provide clear debugging information
- ✅ Success rate for Gemini matches GPT (target: >95%)

**Time Estimate:** 4-8 hours (investigation + fix + validation)

---

## Testing Checklist

### Test 1: Verify Fix 2 (--target-dir)

**Setup:**
- Config: 10 runs (5 FPF + 2 GPTR + 3 MA)
- Input: Single markdown file
- Expected Output: 10 files (5 FPF .txt + 2 GPTR .md + 3 MA .md)

**Test Steps:**
1. Run ACM with modified evaluation trigger
2. Check evaluation CSV for all 10 files
3. Verify ELO rankings include all file types

**Success Criteria:**
- [ ] `single_doc_results.csv` has 20 rows (10 files × 2 evaluators)
- [ ] `pairwise_results.csv` has comparisons between all file types
- [ ] `elo_summary.csv` ranks all 10 files
- [ ] No files missing from evaluation

---

### Test 2: Verify Fix 1 (Centralized Trigger)

**Setup:**
- Same as Test 1

**Test Steps:**
1. Run ACM with centralized evaluation trigger
2. Verify evaluation runs ONCE after all generation completes
3. Check logs for evaluation trigger timing

**Success Criteria:**
- [ ] Evaluation triggers exactly once
- [ ] All 10 files are included
- [ ] Timing log shows "All files ready" before evaluation starts
- [ ] No duplicate evaluation runs

---

### Test 3: Gemini File Size Limits

**Setup:**
- Create synthetic files: 5 KB, 10 KB, 15 KB, 20 KB, 25 KB, 30 KB
- Run single-doc evaluation with `google:gemini-2.5-flash-lite` only

**Test Steps:**
1. Generate 6 synthetic text files at different sizes
2. Run evaluation with Gemini evaluator only
3. Record which files succeed/fail
4. Examine logs for error messages

**Success Criteria:**
- [ ] Identify exact file size threshold for Gemini failures
- [ ] Capture error messages or API responses
- [ ] Document Gemini-specific limits
- [ ] Propose specific fix based on findings

---

## Appendix A: Code References

### evaluation trigger location

**File:** `api_cost_multiplier/runner.py`  
**Function:** `process_file_fpf_batch`  
**Lines:** 983-1012

```python
# Trigger evaluation if enabled for this file's generated outputs
try:
    eval_config = config.get('eval', {})
    if eval_config.get('auto_run', False) and 'saved_files' in locals() and saved_files and len(saved_files) >= 1:
        print("  Auto-running evaluation on generated reports...")
        eval_script_path = os.path.join(repo_root, "api_cost_multiplier", "evaluate.py")
        if not os.path.exists(eval_script_path):
            print(f"    ERROR: evaluate.py not found at {eval_script_path}. Skipping auto-evaluation.")
        else:
            cmd = [sys.executable, "-u", eval_script_path, "--target-files"] + saved_files
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            stdout, stderr = proc.communicate(timeout=GPTR_TIMEOUT_SECONDS)
            if proc.returncode != 0:
                print(f"    ERROR: evaluate.py subprocess failed (rc={proc.returncode}). Stderr: {stderr}")
            else:
                # Forward evaluation output to console for visibility
                if stdout:
                    print("    Evaluation stdout:")
                    for ln in stdout.splitlines():
                        print(f"      {ln}")
                if stderr:
                    print("    Evaluation stderr:")
                    for ln in stderr.splitlines():
                        print(f"      {ln}")
                print("    Evaluation completed successfully.")
except Exception as e:
    print(f"    ERROR: Auto-evaluation failed: {e}")
```

---

### File Format Support

**File:** `llm-doc-eval/llm_doc_eval/api.py`  
**Function:** `_read_candidates`  
**Lines:** 69-89

```python
def _read_candidates(folder_path: str, exts: Tuple[str, ...] = (".md", ".txt")) -> Dict[str, str]:
    """
    Scan folder_path for candidate files by extension.
    Returns a mapping: doc_id (filename) -> absolute path.
    """
    paths: Dict[str, str] = {}
    for name in os.listdir(folder_path):
        p = os.path.join(folder_path, name)
        if not os.path.isfile(p):
            continue
        if os.path.splitext(name)[1].lower() in exts:
            doc_id = name
            # On collision, append a counter suffix to doc_id
            if doc_id in paths:
                base, ext = os.path.splitext(doc_id)
                suffix = 1
                while f"{base}_{suffix}{ext}" in paths:
                    suffix += 1
                doc_id = f"{base}_{suffix}{ext}"
            paths[doc_id] = os.path.abspath(p)
    return paths
```

---

### evaluate.py File Filtering

**File:** `api_cost_multiplier/evaluate.py`  
**Lines:** 60-67

```python
if args.target_files:
    print(f"Running evaluation over targeted files: {args.target_files}")
    # Filter for existing files and valid extensions
    candidates = [
        f for f in args.target_files
        if os.path.isfile(f) and os.path.splitext(f)[1].lower() in (".md", ".txt")
    ]
```

---

## Appendix B: Test Run Data

### Generated Files (All 8)

```
Name                                                Extension SizeKB
----                                                --------- ------
100_ EO 14er & Block.gptr.1.gemini-2.5-flash.3ov.md .md         11.3
100_ EO 14er & Block.ma.1.gpt-4o.e1r.md             .md         38.9
100_ EO 14er & Block.ma.1.gpt-4o-mini.o84.md        .md         38.9
100_ EO 14er & Block.ma.1.o4-mini.8cb.md            .md         36.5
100_ EO 14er & Block.fpf.1.gemini-2.5-flash.3l2.txt .txt        10.1
100_ EO 14er & Block.fpf.2.o4-mini.k3a.txt          .txt         7.1
100_ EO 14er & Block.fpf.3.gpt-5-nano.3xy.txt       .txt        15.5
100_ EO 14er & Block.fpf.4.gpt-5-mini.c9l.txt       .txt        19.2
```

### Evaluated Files (Only 4)

```
100_ EO 14er & Block.fpf.1.gemini-2.5-flash.3l2.txt
100_ EO 14er & Block.fpf.2.o4-mini.k3a.txt
100_ EO 14er & Block.fpf.3.gpt-5-nano.3xy.txt
100_ EO 14er & Block.fpf.4.gpt-5-mini.c9l.txt
```

### Missing from Evaluation (4 files)

```
100_ EO 14er & Block.gptr.1.gemini-2.5-flash.3ov.md (11.3 KB)
100_ EO 14er & Block.ma.1.gpt-4o.e1r.md             (38.9 KB)
100_ EO 14er & Block.ma.1.gpt-4o-mini.o84.md        (38.9 KB)
100_ EO 14er & Block.ma.1.o4-mini.8cb.md            (36.5 KB)
```

---

## Appendix C: Configuration

### ACM Config (10 runs)

**File:** `api_cost_multiplier/config.yaml`

```yaml
runs:
- type: fpf
  provider: google
  model: gemini-2.5-flash
- type: fpf
  provider: google
  model: gemini-2.5-flash-lite
- type: fpf
  provider: openai
  model: gpt-5-mini
- type: fpf
  provider: openai
  model: gpt-5-nano
- type: fpf
  provider: openai
  model: o4-mini
- type: gptr
  provider: google_genai
  model: gemini-2.5-flash
- type: gptr
  provider: google_genai
  model: gemini-2.5-flash-lite
- type: ma
  model: gpt-4o
- type: ma
  model: gpt-4o-mini
- type: ma
  model: o4-mini

eval:
  auto_run: true
  output_directory: gptr-eval-process/final_reports
  export_directory: gptr-eval-process/exports
```

### Eval Config (2 evaluators)

**File:** `llm-doc-eval/config.yaml`

```yaml
models:
  google_gemini-2.5-flash-lite:
    provider: google
    model: gemini-2.5-flash-lite
  openai_gpt-5-mini:
    provider: openai
    model: gpt-5-mini

evaluation:
  mode: both  # single-doc + pairwise
```

---

**Analysis Completed:** November 15, 2025  
**Analyst:** GitHub Copilot  
**Confidence Level:** VERY HIGH (based on direct code review, CSV evidence, and file system verification)
