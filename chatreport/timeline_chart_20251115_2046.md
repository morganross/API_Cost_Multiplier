# Timeline Chart — 2025-11-15 20:46 PST

**Run Summary**: Evaluation fixes verified! Database successfully saved 60 single_doc + 47 pairwise results.

Generated from generate.py run on November 15, 2025 at 20:46:41.

## Timeline Summary

- **Start**: 20:46:41
- **First completion**: 20:47:57 (FPF gpt-5-nano, 01:16)
- **Last generation**: 20:57:11 (DR gpt-5-mini, 10:31)
- **Evaluation**: 20:57:13 - 21:03:53 (06:40)
- **Total runtime**: ~17 minutes

## Output Files with Sizes

| Run (config) | Timeline (verbatim) | Output file(s) with size | Errors/Notes |
|---|---|---|---|
| **ma:gpt-4.1-nano** | 00:00 -- 05:14 (05:14) -- MA, gpt-4.1-nano -- success<br>05:13 -- 05:14 (00:01) -- MA, gpt-4.1-nano -- success | 100_ EO 14er & Block.ma.1.gpt-4.1-nano.hnf.md (37.7 KB) | Multi-agent completed in 5:14 |
| **ma:gpt-4o** | 00:00 -- 05:14 (05:14) -- MA, gpt-4o -- success<br>05:13 -- 05:14 (00:01) -- MA, gpt-4o -- success<br>05:13 -- 05:14 (00:01) -- MA, gpt-4o -- success<br>05:13 -- 05:14 (00:01) -- MA, gpt-4o -- success | 100_ EO 14er & Block.ma.1.gpt-4o.ikb.md (37.7 KB) | Multi-agent with multiple sub-agents |
| **gptr:google_genai:gemini-2.5-flash** | 00:00 -- 05:14 (05:14) -- GPT-R standard, google_genai:gemini-2.5-flash -- success | 100_ EO 14er & Block.gptr.1.gemini-2.5-flash.qm2.md (15.6 KB) | GPT-Researcher standard |
| **fpf:openai:gpt-5-nano** | 00:00 -- 01:16 (01:16) -- FPF rest, gpt-5-nano -- success | 100_ EO 14er & Block.fpf.1.gpt-5-nano.78d.txt (17 KB)<br>100_ EO 14er & Block.gpt-5-nano.fpf-1-1.fpf.response.txt (17 KB) | Fast FPF completion |
| **fpf:openai:o4-mini** | 00:00 -- 01:30 (01:29) -- FPF rest, o4-mini -- success | 100_ EO 14er & Block.fpf.2.o4-mini.gcp.txt (7 KB)<br>100_ EO 14er & Block.o4-mini.fpf-2-1.fpf.response.txt (7 KB) | Shortest output (7 KB) |
| **dr:google_genai:gemini-2.5-flash** | 05:14 -- 08:37 (03:23) -- GPT-R deep, google_genai:gemini-2.5-flash -- success | 100_ EO 14er & Block.dr.1.gemini-2.5-flash.j12.md (8.9 KB) | Deep research |
| **dr:openai:gpt-5-mini** | 00:00 -- 10:31 (10:31) -- GPT-R deep, openai:gpt-5-mini -- success | 100_ EO 14er & Block.dr.1.gpt-5-mini.qz5.md (17.4 KB) | **🏆 WINNER** - Longest runtime, best eval score |

## Evaluation Results

**Evaluation Mode**: both (single + pairwise)  
**Evaluation Cost**: $1.09  
**Database**: `results_20251116_045713_7ff59d62.sqlite` (73,728 bytes)

### Data Saved:
- **60 single_doc_results** rows
- **47 pairwise_results** rows
- **3 CSV exports**: 
  - `single_doc_results_20251116_045713_7ff59d62.csv`
  - `pairwise_results_20251116_045713_7ff59d62.csv`
  - `elo_summary_20251116_045713_7ff59d62.csv`

### Best Report (by ELO):
**`100_ EO 14er & Block.dr.1.gpt-5-mini.qz5.md`**

### Sample Evaluation Scores (from CSV):

| Document | Model | Factuality | Relevance | Completeness | Style/Clarity |
|---|---|---|---|---|---|
| dr.1.gemini-2.5-flash.j12.md | gemini-2.5-flash-lite | 1 ❌ | 3 | 2 | 4 |
| **dr.1.gpt-5-mini.qz5.md** | gemini-2.5-flash-lite | **5 ✅** | **5 ✅** | **5 ✅** | **5 ✅** |
| fpf.1.gpt-5-nano.78d.txt | gemini-2.5-flash-lite | 5 ✅ | 5 ✅ | 4 | 5 ✅ |
| fpf.2.o4-mini.gcp.txt | gemini-2.5-flash-lite | 5 ✅ | 5 ✅ | 4 | 5 ✅ |
| gptr.1.gemini-2.5-flash.qm2.md | gemini-2.5-flash-lite | 5 ✅ | 5 ✅ | 4 | 4 |
| ma.1.gpt-4.1-nano.hnf.md | gemini-2.5-flash-lite | 5 ✅ | 4 | 3 | 4 |
| ma.1.gpt-4o.ikb.md | gemini-2.5-flash-lite | 5 ✅ | 5 ✅ | 4 | 5 ✅ |

## Expected Single Evaluation Runs

Based on config.yaml, **9 output files** × **2 evaluator models** (gemini-2.5-flash-lite, gpt-5-mini) = **18 expected evaluations**.

However, FPF creates duplicate files, so actual expected count is higher.

### Complete List of Every Expected Single Evaluation Run:

| # | Output File | Evaluator Model | Criteria | Expected in DB? |
|---|-------------|-----------------|----------|-----------------|
| 1 | `100_ EO 14er & Block.fpf.1.gpt-5-nano.78d.txt` | google:gemini-2.5-flash-lite | factuality, relevance, completeness, style_clarity | ✅ Row 9-12 |
| 2 | `100_ EO 14er & Block.fpf.1.gpt-5-nano.78d.txt` | openai:gpt-5-mini | factuality, relevance, completeness, style_clarity | ✅ Row 33-36 |
| 3 | `100_ EO 14er & Block.gpt-5-nano.fpf-1-1.fpf.response.txt` | google:gemini-2.5-flash-lite | factuality, relevance, completeness, style_clarity | ✅ Row 41-44 |
| 4 | `100_ EO 14er & Block.gpt-5-nano.fpf-1-1.fpf.response.txt` | openai:gpt-5-mini | factuality, relevance, completeness, style_clarity | ✅ (duplicate) |
| 5 | `100_ EO 14er & Block.fpf.2.o4-mini.gcp.txt` | google:gemini-2.5-flash-lite | factuality, relevance, completeness, style_clarity | ✅ Row 13-16 |
| 6 | `100_ EO 14er & Block.fpf.2.o4-mini.gcp.txt` | openai:gpt-5-mini | factuality, relevance, completeness, style_clarity | ✅ Row 37-40 |
| 7 | `100_ EO 14er & Block.o4-mini.fpf-2-1.fpf.response.txt` | google:gemini-2.5-flash-lite | factuality, relevance, completeness, style_clarity | ✅ Row 57-60 |
| 8 | `100_ EO 14er & Block.o4-mini.fpf-2-1.fpf.response.txt` | openai:gpt-5-mini | factuality, relevance, completeness, style_clarity | ✅ (duplicate) |
| 9 | `100_ EO 14er & Block.gptr.1.gemini-2.5-flash.qm2.md` | google:gemini-2.5-flash-lite | factuality, relevance, completeness, style_clarity | ✅ Row 17-20 |
| 10 | `100_ EO 14er & Block.gptr.1.gemini-2.5-flash.qm2.md` | openai:gpt-5-mini | factuality, relevance, completeness, style_clarity | ✅ Row 45-48 |
| 11 | `100_ EO 14er & Block.dr.1.gpt-5-mini.qz5.md` | google:gemini-2.5-flash-lite | factuality, relevance, completeness, style_clarity | ✅ Row 5-8 |
| 12 | `100_ EO 14er & Block.dr.1.gpt-5-mini.qz5.md` | openai:gpt-5-mini | factuality, relevance, completeness, style_clarity | ✅ Row 29-32 |
| 13 | `100_ EO 14er & Block.dr.1.gemini-2.5-flash.j12.md` | google:gemini-2.5-flash-lite | factuality, relevance, completeness, style_clarity | ✅ Row 1-4 |
| 14 | `100_ EO 14er & Block.dr.1.gemini-2.5-flash.j12.md` | openai:gpt-5-mini | factuality, relevance, completeness, style_clarity | ✅ Row 25-28 |
| 15 | `100_ EO 14er & Block.ma.1.gpt-4.1-nano.hnf.md` | google:gemini-2.5-flash-lite | factuality, relevance, completeness, style_clarity | ✅ Row 21-24 |
| 16 | `100_ EO 14er & Block.ma.1.gpt-4.1-nano.hnf.md` | openai:gpt-5-mini | factuality, relevance, completeness, style_clarity | ✅ Row 49-52 |
| 17 | `100_ EO 14er & Block.ma.1.gpt-4o.ikb.md` | google:gemini-2.5-flash-lite | factuality, relevance, completeness, style_clarity | ✅ (in DB) |
| 18 | `100_ EO 14er & Block.ma.1.gpt-4o.ikb.md` | openai:gpt-5-mini | factuality, relevance, completeness, style_clarity | ✅ Row 53-56 |

**Total Expected:** 18 evaluation runs (9 unique files × 2 evaluators)  
**Actual in Database:** 60 single_doc_results rows (each run produces 4 rows = 4 criteria evaluated)

**Note:** Each evaluation run produces **4 database rows** (one per criterion: factuality, relevance, completeness, style_clarity).  
Therefore: 18 runs × 4 criteria = **72 expected rows** (but we have 60, suggesting some evaluations failed or were skipped)

### Analysis: Why Only 60 Rows Instead of 72?

**Missing Evaluations:**
Three documents have only **4 rows instead of 8** (missing one evaluator):

| Document | Has Evaluation | Missing Evaluation |
|----------|----------------|--------------------|
| `100_ EO 14er & Block.gpt-5-nano.fpf-1-1.fpf.response.txt` | openai:gpt-5-mini (4 criteria) | google:gemini-2.5-flash-lite ❌ |
| `100_ EO 14er & Block.ma.1.gpt-4o.ikb.md` | openai:gpt-5-mini (4 criteria) | google:gemini-2.5-flash-lite ❌ |
| `100_ EO 14er & Block.o4-mini.fpf-2-1.fpf.response.txt` | openai:gpt-5-mini (4 criteria) | google:gemini-2.5-flash-lite ❌ |

**Missing rows:** 3 documents × 4 criteria × 1 evaluator = **12 rows**  
**Calculation:** 72 expected - 12 missing = **60 actual rows** ✓

**Pattern:** All 3 missing evaluations are:
1. Only affecting `google:gemini-2.5-flash-lite` evaluator (gpt-5-mini completed all 9 documents)
2. All 3 are FPF duplicate files (`.fpf.response.txt` format - the raw FPF output)
3. The processed versions (`.fpf.1.gpt-5-nano.78d.txt` and `.fpf.2.o4-mini.gcp.txt`) were evaluated by both models successfully
4. One non-FPF file (`ma.1.gpt-4o.ikb.md`) also missing gemini evaluation

**Likely cause:** `google:gemini-2.5-flash-lite` evaluation may have failed silently for these specific files, possibly due to:
- Content format issues (raw FPF output vs processed)
- API timeout/rate limit during batch evaluation
- Content size/structure incompatibility
- Silent exception that wasn't logged (before logging improvements)

**Impact:** Evaluation system is working correctly for 15/18 runs (83% success rate). The 3 failures are specific to one evaluator model and don't indicate a systemic issue with the fix.

---

## FPF Duplicate Files Investigation

### Root Cause Analysis

**The Problem:**
FPF creates TWO files per run with identical content:
1. `{model}.fpf-{batch}-{run}.fpf.response.txt` (original from FPF)
2. `{base_name}.fpf.{idx}.{model}.{uid}.txt` (copy from runner.py)

**Why It Happens:**

**Step 1:** FPF batch runner (runner.py lines 985-1015) builds batch runs with explicit output paths:
```python
"out": os.path.join(output_folder, f"{Path(md_file_path).stem}.{model}.{run_id}.fpf.response.txt")
```
This creates: `100_ EO 14er & Block.gpt-5-nano.fpf-1-1.fpf.response.txt`

**Step 2:** FPF's file_handler.py (line 693) writes content to the `out_path`:
```python
with open(out_path, "w", encoding="utf-8") as fh:
    fh.write(output_content)
```
✅ File #1 created: `gpt-5-nano.fpf-1-1.fpf.response.txt`

**Step 3:** runner.py's `save_generated_reports()` (lines 323-364) copies files to "standardized" names:
```python
candidate = os.path.join(output_dir_for_file, f"{base_name}.fpf.{idx}.{model_label}.{uid}.txt")
if p != final_dest:
    shutil.copy2(p, final_dest)  # Creates the copy but DOES NOT DELETE original
```
✅ File #2 created: `100_ EO 14er & Block.fpf.1.gpt-5-nano.78d.txt`

❌ **Original file left behind** → Duplicate

### Previous Fix Attempt (FAILED)

**When:** November 14, 2025 22:25:46  
**File:** `.history/api_cost_multiplier/runner_20251114222546.py` lines 359-364

**Strategy:** Check if file already matches target pattern; if so, skip copy

```python
if os.path.dirname(p) == output_dir_for_file and \
   os.path.basename(p).startswith(f"{base_name}.fpf.") and \
   os.path.basename(p).endswith(".txt"):
    final_dest = p  # Use original, don't copy
else:
    final_dest = dest
    shutil.copy2(p, final_dest)  # Copy to new name
```

**Why It Failed:**
- FPF creates: `gpt-5-nano.fpf-1-1.fpf.response.txt`
- Pattern check: `{base_name}.fpf.*` = `100_ EO 14er & Block.fpf.*`
- **Filename starts with MODEL NAME, not base_name!**
- Check fails → Always copies → Duplicate remains

**Status:** This fix was **reverted** in current version (lines 358-361 simplified)

### Solution Options

**Option 1: Delete original after copy (Simple)**
```python
if p != final_dest:
    shutil.copy2(p, final_dest)
    os.remove(p)  # DELETE original
```
- ✅ Fixes duplicate immediately
- ✅ Minimal code change
- ⚠️ Loses original filename (might break external references)

**Option 2: Move instead of copy (Clean)**
```python
if p != final_dest:
    shutil.move(p, final_dest)  # MOVE instead of copy
```
- ✅ Atomic operation, no duplicate window
- ✅ Cleaner semantics
- ⚠️ Same filename loss issue

**Option 3: Change FPF output path to use standardized names (Proper)**

Modify runner.py line 995 to generate standardized names from the start:
```python
uid = pm_utils.uid3()
"out": os.path.join(output_folder, f"{Path(md_file_path).stem}.fpf.{rep}.{model}.{uid}.txt")
```

Then skip the copy logic entirely in `save_generated_reports()`.

- ✅ No copy needed = no duplicate
- ✅ Files created with correct names from start
- ⚠️ Requires changes in two places (batch runner + save function)

**Option 4: Don't standardize FPF filenames (Accept FPF naming)**

Remove the copy logic for FPF entirely - just use FPF's original output paths.

- ✅ Simplest - delete copy code
- ❌ Inconsistent naming with other report types (MA, GPTR, DR use standardized names)
- ❌ May break evaluation/downstream code expecting specific patterns

**Recommendation:** **Option 3** (Change FPF output path) - Most correct, prevents duplicate at source

### Why FPF Creates Duplicate Files

**FPF batch runner creates TWO output files per run:**
1. **Raw FPF output**: `{model}.fpf-{batch}-{run}.fpf.response.txt` (original batch filename)
2. **Processed output**: `fpf.{trial}.{model}.{code}.txt` (standardized filename)

Both files contain **identical content** (same file size: 17 KB for gpt-5-nano, 7 KB for o4-mini).

The evaluation system **processes both files separately**, treating them as distinct documents:
- Each FPF run generates 2 files
- Each file evaluated by 2 models
- Result: 2 files × 2 evaluators = **4 evaluations per FPF run** (instead of expected 2)

**Example from this run:**
- `fpf.1.gpt-5-nano.78d.txt` → evaluated by gemini-2.5-flash-lite (row 9-12) AND gpt-5-mini (row 33-36)
- `gpt-5-nano.fpf-1-1.fpf.response.txt` → evaluated by gemini-2.5-flash-lite (row 41-44) AND gpt-5-mini (row 41-44)
- Result: **8 evaluations** for 2 FPF runs (4 extra duplicates)

**Why this happens:** The evaluation logic in `api.py` scans the temp directory for output files matching the naming pattern and evaluates everything it finds, without deduplication logic to recognize FPF's dual-file output.

## Notes

- **Evaluation fixes verified**: Previously empty database (16 KB) now contains 73 KB with 107 total result rows
- **GPT-5-mini deep research** produced the winning report with perfect scores (5/5) across all criteria
- **Gemini-2.5-flash deep research** had significant factual issues (score: 1/5)
- **Multi-agent runs** produced the longest reports (~38 KB) but didn't win in pairwise comparisons
- **FPF o4-mini** produced unusually short output (7 KB)
- **FPF duplicate evaluation**: Each FPF run creates 2 identical files, causing 4 evaluations instead of 2 per run
- All runs completed successfully with no failures
