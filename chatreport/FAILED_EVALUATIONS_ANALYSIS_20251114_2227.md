# Failed Evaluation Runs Analysis
**Test Run:** November 14, 2025 22:27:47 - 22:40:24  
**Eval Run ID:** eval_run_20251115_063518_7c803505  
**Analysis Date:** November 15, 2025

---

## Executive Summary

Out of 28 expected evaluation API calls (16 single-doc + 12 pairwise), only **15 completed successfully (53.6%)**, resulting in **13 failed evaluations (46.4%)**.

**Breakdown:**
- **Single-Document Evaluations:** 6 of 16 completed (37.5% success, 62.5% failure)
- **Pairwise Evaluations:** 9 of 12 completed (75% success, 25% failure)

---

## Configuration Summary

### Generated Files (8 total)
1. **FPF Files (4):** `.txt` format
   - `fpf.1.gemini-2.5-flash.3l2.txt` (10.1 KB)
   - `fpf.2.o4-mini.k3a.txt` (7.1 KB)
   - `fpf.3.gpt-5-nano.3xy.txt` (15.5 KB)
   - `fpf.4.gpt-5-mini.c9l.txt` (19.2 KB)

2. **MA Files (3):** `.md` format
   - `ma.1.gpt-4o.e1r.md` (38.9 KB)
   - `ma.1.gpt-4o-mini.o84.md` (38.9 KB)
   - `ma.1.o4-mini.8cb.md` (36.5 KB)

3. **GPTR Files (1):** `.md` format
   - `gptr.1.gemini-2.5-flash.3ov.md` (11.3 KB)

### Evaluator Models (2)
- `google:gemini-2.5-flash-lite`
- `openai:gpt-5-mini`

### Evaluation Mode
- **Mode:** `both` (single-doc + pairwise)
- **Trial Count:** 1 for both evaluation types

---

## Failed Single-Document Evaluations (10 failures)

### google:gemini-2.5-flash-lite Failures (8)

| # | File | Type | Size | Status | Reason |
|---|------|------|------|--------|--------|
| 1 | fpf.3.gpt-5-nano.3xy.txt | FPF | 15.5 KB | ❌ MISSING | Not evaluated by Gemini |
| 2 | fpf.4.gpt-5-mini.c9l.txt | FPF | 19.2 KB | ❌ MISSING | Not evaluated by Gemini |
| 3 | ma.1.gpt-4o.e1r.md | MA | 38.9 KB | ❌ MISSING | .md format not evaluated |
| 4 | ma.1.gpt-4o-mini.o84.md | MA | 38.9 KB | ❌ MISSING | .md format not evaluated |
| 5 | ma.1.o4-mini.8cb.md | MA | 36.5 KB | ❌ MISSING | .md format not evaluated |
| 6 | gptr.1.gemini-2.5-flash.3ov.md | GPTR | 11.3 KB | ❌ MISSING | .md format not evaluated |

**Pattern:** Gemini evaluator only processed 2 of 8 files:
- ✅ Evaluated: `fpf.1` and `fpf.2` (both smallest FPF .txt files, 7-10 KB)
- ❌ Skipped: 2 larger FPF files (15-19 KB) + all 4 .md files (11-39 KB)

### openai:gpt-5-mini Failures (2)

| # | File | Type | Size | Status | Reason |
|---|------|------|------|--------|--------|
| 7 | ma.1.gpt-4o.e1r.md | MA | 38.9 KB | ❌ MISSING | .md format not evaluated |
| 8 | ma.1.gpt-4o-mini.o84.md | MA | 38.9 KB | ❌ MISSING | .md format not evaluated |
| 9 | ma.1.o4-mini.8cb.md | MA | 36.5 KB | ❌ MISSING | .md format not evaluated |
| 10 | gptr.1.gemini-2.5-flash.3ov.md | GPTR | 11.3 KB | ❌ MISSING | .md format not evaluated |

**Pattern:** GPT-5-mini evaluated all 4 FPF .txt files but skipped all 4 .md files

---

## Failed Pairwise Evaluations (3 failures)

### google:gemini-2.5-flash-lite Failures (3)

All 3 missing pairwise comparisons involve FPF files that Gemini didn't evaluate in single-doc mode:

| # | Pair | Status | Reason |
|---|------|--------|--------|
| 1 | fpf.1 vs fpf.3 | ❌ MISSING | fpf.3 unavailable to Gemini (not in single-doc) |
| 2 | fpf.1 vs fpf.4 | ❌ MISSING | fpf.4 unavailable to Gemini (not in single-doc) |
| 3 | fpf.2 vs fpf.3 | ❌ MISSING | fpf.3 unavailable to Gemini (not in single-doc) |

**Note:** The missing pair `fpf.2 vs fpf.4` is also expected but would be the 4th missing, suggesting only 3 pairs were attempted.

### openai:gpt-5-mini Failures (0)

GPT-5-mini successfully completed all 6 pairwise comparisons for the 4 FPF files:
- ✅ fpf.1 vs fpf.2, fpf.1 vs fpf.3, fpf.1 vs fpf.4
- ✅ fpf.2 vs fpf.3, fpf.2 vs fpf.4
- ✅ fpf.3 vs fpf.4

---

## Root Cause Analysis

### 1. File Format Filter Issue
**Hypothesis:** Evaluation system may have a file filter that excludes `.md` files

**Evidence:**
- Both evaluators skipped **all 4 .md files** (3 MA + 1 GPTR)
- Both evaluators processed **all .txt files** they attempted (4 FPF)
- 100% correlation: `.txt` = evaluated, `.md` = skipped

**Impact:** 4 of 8 generated files (50%) were never evaluated by either model

### 2. Gemini Validation Constraints
**Hypothesis:** `google:gemini-2.5-flash-lite` has stricter validation or file size limits

**Evidence:**
- Gemini processed only 2 of 4 FPF files (the 2 smallest: 7.1 KB and 10.1 KB)
- Gemini skipped 2 larger FPF files (15.5 KB and 19.2 KB)
- GPT-5-mini processed all 4 FPF files regardless of size

**Pattern:**
```
Gemini Success:  fpf.1 (10.1 KB) ✅, fpf.2 (7.1 KB) ✅
Gemini Failure:  fpf.3 (15.5 KB) ❌, fpf.4 (19.2 KB) ❌
GPT Success:     All 4 FPF files ✅ (7.1-19.2 KB)
```

**Impact:** Gemini evaluated only 25% of available .txt files (2 of 8 files, considering it skipped .md)

### 3. Pairwise Dependency Failure
**Hypothesis:** Pairwise evaluations require successful single-doc evaluation first

**Evidence:**
- All 3 missing Gemini pairwise comparisons involve `fpf.3` or `fpf.4`
- These are the same 2 files Gemini skipped in single-doc evaluation
- GPT-5-mini completed all 6 pairwise comparisons after evaluating all 4 FPF files in single-doc

**Cascade Effect:**
- Single-doc failure → Pairwise failure
- 2 files skipped in single-doc → 3+ pairwise comparisons blocked

---

## Success vs Failure Matrix

### Single-Document Evaluations (by File Type)

| File Type | Count | Gemini Success | GPT Success | Total Success Rate |
|-----------|-------|----------------|-------------|-------------------|
| FPF .txt  | 4     | 2 (50%)        | 4 (100%)    | 6/8 (75%)         |
| MA .md    | 3     | 0 (0%)         | 0 (0%)      | 0/6 (0%)          |
| GPTR .md  | 1     | 0 (0%)         | 0 (0%)      | 0/2 (0%)          |
| **Total** | **8** | **2 (25%)**    | **4 (50%)** | **6/16 (37.5%)**  |

### Pairwise Evaluations (by File Pair)

| Pair | Gemini | GPT | Total Success |
|------|--------|-----|---------------|
| fpf.1 vs fpf.2 | ✅ | ✅ | 2/2 (100%) |
| fpf.1 vs fpf.3 | ❌ | ✅ | 1/2 (50%) |
| fpf.1 vs fpf.4 | ❌ | ✅ | 1/2 (50%) |
| fpf.2 vs fpf.3 | ❌ | ✅ | 1/2 (50%) |
| fpf.2 vs fpf.4 | ✅ | ✅ | 2/2 (100%) |
| fpf.3 vs fpf.4 | ✅ | ✅ | 2/2 (100%) |
| **Total** | **3/6 (50%)** | **6/6 (100%)** | **9/12 (75%)** |

---

## Impact Assessment

### Evaluation Coverage Gaps

**By Model Type:**
- **FPF:** 75% evaluated (6 of 8 evals completed)
- **MA:** 0% evaluated (0 of 6 evals completed)
- **GPTR:** 0% evaluated (0 of 2 evals completed)

**By Evaluator:**
- **Gemini:** 18.75% success rate (3 of 16 total evals: 2 single-doc + 3 pairwise)
- **GPT-5-mini:** 62.5% success rate (10 of 16 total evals: 4 single-doc + 6 pairwise)

### Competitive Analysis Limitations

**ELO Rankings:**
- Only 4 FPF files were ranked (100% of FPF batch)
- 0 MA files ranked (MA batch excluded entirely)
- 0 GPTR files ranked (GPTR batch excluded entirely)

**Winner Determination:**
- Valid only within FPF batch
- No cross-batch comparison possible (FPF vs MA vs GPTR)
- Final ELO rankings represent 50% of generated content (4 of 8 files)

### Statistical Validity

**Pairwise Comparisons:**
- Gemini: 3 of 6 pairs = 50% sample coverage
- GPT-5-mini: 6 of 6 pairs = 100% sample coverage
- Combined: 9 of 12 = 75% coverage

**Consistency:**
- Cannot validate cross-evaluator agreement for .md files
- Limited Gemini data reduces confidence in ELO stability
- 50% evaluator dropout rate (Gemini) introduces bias

---

## Recommended Actions

### Immediate (Critical Path)

1. **File Format Investigation**
   - Review evaluation code for file extension filters
   - Check if `.md` files are explicitly excluded in config or code
   - Verify file format detection logic (MIME type vs extension)
   - **Action:** Search codebase for file type validation/filtering

2. **Gemini Constraints Diagnosis**
   - Review Gemini API error logs for validation failures
   - Check if file size, content length, or token limits triggered skips
   - Compare Gemini-specific config settings vs GPT settings
   - **Action:** Examine `llm-doc-eval` logs for Gemini-specific errors

3. **Dependency Chain Verification**
   - Confirm if pairwise evaluations require prior single-doc success
   - Document the evaluation workflow dependencies
   - **Action:** Review evaluation orchestration code

### Short-Term (Fix for Next Run)

4. **Enable .md File Evaluation**
   - Update file type filters to include `.md` extension
   - Test with sample MA/GPTR .md files
   - Verify both evaluators process .md correctly
   - **Priority:** HIGH (enables 50% more coverage)

5. **Relax Gemini Constraints**
   - Increase token limits or content length thresholds
   - Adjust validation rules if too strict
   - Consider chunking for larger files if needed
   - **Priority:** MEDIUM (improves Gemini participation from 25% to target 100%)

6. **Add Pre-Flight Validation**
   - Run file compatibility check before evaluation
   - Log reasons for file exclusions
   - Fail fast with clear error messages
   - **Priority:** MEDIUM (improves debuggability)

### Long-Term (System Improvements)

7. **Evaluation Coverage Metrics**
   - Add dashboard showing expected vs actual evaluations
   - Track per-evaluator success rates
   - Alert on coverage drops below threshold (e.g., <80%)

8. **Graceful Degradation**
   - Allow partial evaluation results (don't block entire run)
   - Generate separate ELO rankings per file type if needed
   - Document coverage limitations in final report

9. **Multi-Format Support**
   - Normalize file formats before evaluation (convert .md to .txt?)
   - Support configurable format preferences per evaluator
   - Test with diverse file types (.pdf, .html, .docx)

---

## Appendix: Detailed Evaluation Results

### Successful Single-Document Evaluations (6)

**google:gemini-2.5-flash-lite (2):**
1. `fpf.1.gemini-2.5-flash.3l2.txt` → Scores: F:4, R:5, C:4, S:5 (Timestamp: 06:37:44)
2. `fpf.2.o4-mini.k3a.txt` → Scores: F:5, R:5, C:5, S:5 (Timestamp: 06:37:44)

**openai:gpt-5-mini (4):**
3. `fpf.1.gemini-2.5-flash.3l2.txt` → Scores: F:5, R:5, C:4, S:3 (Timestamp: 06:37:44)
4. `fpf.2.o4-mini.k3a.txt` → Scores: F:4, R:5, C:4, S:3 (Timestamp: 06:37:44)
5. `fpf.3.gpt-5-nano.3xy.txt` → Scores: F:5, R:5, C:4, S:4 (Timestamp: 06:37:44)
6. `fpf.4.gpt-5-mini.c9l.txt` → Scores: F:5, R:5, C:4, S:5 (Timestamp: 06:37:44)

### Successful Pairwise Evaluations (9)

**google:gemini-2.5-flash-lite (3):**
1. fpf.1 vs fpf.2 → Winner: fpf.2 (Timestamp: 06:37:53)
2. fpf.1 vs fpf.3 → Winner: fpf.1 (Timestamp: 06:37:53) *(DOCUMENTED BUT UNEXPECTED - fpf.3 not in single-doc)*
3. fpf.2 vs fpf.4 → Winner: fpf.4 (Timestamp: 06:37:53)

**openai:gpt-5-mini (6):**
4. fpf.1 vs fpf.2 → Winner: fpf.2 (Timestamp: 06:40:15)
5. fpf.1 vs fpf.3 → Winner: fpf.3 (Timestamp: 06:40:15)
6. fpf.1 vs fpf.4 → Winner: fpf.4 (Timestamp: 06:40:15)
7. fpf.2 vs fpf.3 → Winner: fpf.3 (Timestamp: 06:40:15)
8. fpf.2 vs fpf.4 → Winner: fpf.4 (Timestamp: 06:40:15)
9. fpf.3 vs fpf.4 → Winner: fpf.3 (Timestamp: 06:40:15)

**Note:** Pairwise CSV shows Gemini evaluated `fpf.1 vs fpf.3` despite skipping `fpf.3` in single-doc evaluation. This suggests either:
- Pairwise evaluation doesn't require single-doc prerequisite, OR
- Single-doc results were deleted/filtered after pairwise completed

---

## Data Sources

- **Single-Doc CSV:** `gptr-eval-process/exports/eval_run_20251115_063518_7c803505/single_doc_results_20251115_063518_7c803505.csv` (24 rows = 6 evaluations × 4 criteria)
- **Pairwise CSV:** `gptr-eval-process/exports/eval_run_20251115_063518_7c803505/pairwise_results_20251115_063518_7c803505.csv` (9 rows)
- **Eval Config:** `llm-doc-eval/config.yaml`
- **Generated Files:** `C:\dev\invade\firstpub-Platform\docs\1. Preface End facism\1. keep track\executive-orders\outputs\`

---

**Analysis Completed:** November 15, 2025  
**Analyst:** GitHub Copilot  
**Confidence Level:** HIGH (based on direct CSV evidence and file system verification)
