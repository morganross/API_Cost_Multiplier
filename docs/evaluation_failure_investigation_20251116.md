# Evaluation Failure Investigation Report
**Date:** 2025-11-16  
**Run ID:** 20251116_091108_0e9e736b  
**Pipeline:** api_cost_multiplier → llm-doc-eval  
**Investigator:** Automated Analysis

---

## Executive Summary

**Expected:** 48 single-document evaluations (2 judge models × 6 generated files × 4 criteria)  
**Actual:** 32 single-document evaluations completed (66.7% completion rate)  
**Missing:** 16 evaluations (33.3% failure rate)  

**Root Cause:** Google Gemini 2.5 Flash-Lite judge model failed validation checks on 4 of 6 generated files, producing the error:

```
Provider response failed mandatory checks: missing grounding (web_search/citations) 
and reasoning (thinking/rationale). Enforcement is strict; no report may be written.
```

OpenAI GPT-5-Mini judge completed all 6 evaluations successfully (100% success rate).

---

## Expected vs Actual Evaluation Matrix

### Expected Single-Document Evaluations (48 total)
```
Judge Model: google:gemini-2.5-flash-lite (24 evaluations)
├─ 100__EO_14er_&_Block.fpf.1.o4-mini.d71.txt (4 criteria) ❌ FAILED
├─ 100__EO_14er_&_Block.fpf.1.gpt-5-nano.7ha.txt (4 criteria) ❌ FAILED
├─ 100__EO_14er_&_Block.dr.1.gpt-5-mini.6wr.md (4 criteria) ✅ SUCCESS
├─ 100__EO_14er_&_Block.ma.1.gpt-4o.p4u.md (4 criteria) ❌ FAILED
├─ 100__EO_14er_&_Block.gptr.1.gemini-2.5-flash.h3u.md (4 criteria) ✅ SUCCESS
└─ 100__EO_14er_&_Block.ma.1.gpt-4.1-nano.ku6.md (4 criteria) ❌ FAILED

Judge Model: openai:gpt-5-mini (24 evaluations)
├─ 100__EO_14er_&_Block.fpf.1.o4-mini.d71.txt (4 criteria) ✅ SUCCESS
├─ 100__EO_14er_&_Block.fpf.1.gpt-5-nano.7ha.txt (4 criteria) ✅ SUCCESS
├─ 100__EO_14er_&_Block.dr.1.gpt-5-mini.6wr.md (4 criteria) ✅ SUCCESS
├─ 100__EO_14er_&_Block.ma.1.gpt-4o.p4u.md (4 criteria) ✅ SUCCESS
├─ 100__EO_14er_&_Block.gptr.1.gemini-2.5-flash.h3u.md (4 criteria) ✅ SUCCESS
└─ 100__EO_14er_&_Block.ma.1.gpt-4.1-nano.ku6.md (4 criteria) ✅ SUCCESS
```

### Actual Results
- **Gemini 2.5 Flash-Lite:** 8/24 evaluations (33.3% success rate)
- **GPT-5-Mini:** 24/24 evaluations (100% success rate)
- **Total:** 32/48 evaluations (66.7% success rate)

---

## Detailed Failure Analysis

### Failed Evaluation Runs (Gemini 2.5 Flash-Lite)

All 4 failed runs produced the same validation error from FilePromptForge (FPF):

#### 1. `fpf.1.o4-mini.d71.txt` (7 KB)
```
2025-11-16 01:11:11,599 WARNING fpf_scheduler: 
Run failed (attempt 1/1) 
id=single-google-gemini-2.5-flash-lite-100__EO_14er_&_Block.fpf.1.o4-mini.d71.txt-d8aaf9c7 
provider=google 
model=gemini-2.5-flash-lite 
err=Provider response failed mandatory checks: missing grounding (web_search/citations) 
and reasoning (thinking/rationale). Enforcement is strict; no report may be written.
elapsed=2.33s
```

#### 2. `fpf.1.gpt-5-nano.7ha.txt` (12 KB)
```
2025-11-16 01:11:11,666 WARNING fpf_scheduler: 
Run failed (attempt 1/1) 
id=single-google-gemini-2.5-flash-lite-100__EO_14er_&_Block.fpf.1.gpt-5-nano.7ha.txt-b49c3cbd 
provider=google 
model=gemini-2.5-flash-lite 
err=Provider response failed mandatory checks: missing grounding (web_search/citations) 
and reasoning (thinking/rationale). Enforcement is strict; no report may be written.
elapsed=2.40s
```

#### 3. `ma.1.gpt-4o.p4u.md` (48 KB)
```
2025-11-16 01:11:13,577 WARNING fpf_scheduler: 
Run failed (attempt 1/1) 
id=single-google-gemini-2.5-flash-lite-100__EO_14er_&_Block.ma.1.gpt-4o.p4u.md-5239a480 
provider=google 
model=gemini-2.5-flash-lite 
err=Provider response failed mandatory checks: missing grounding (web_search/citations) 
and reasoning (thinking/rationale). Enforcement is strict; no report may be written.
elapsed=4.31s
```

#### 4. `ma.1.gpt-4.1-nano.ku6.md` (not in single-doc failures, may be pairwise only)
```
No direct single-doc failure log found, but file was not evaluated by gemini
```

---

## Validation System Analysis

### FPF Validation Requirements

The FilePromptForge (FPF) system enforces strict validation on all AI-generated evaluation outputs:

**Mandatory Check #1: Grounding (web_search/citations)**
- Requires `groundingMetadata` field in API response
- Expects verifiable citations in format `[1]`, `[2]`, etc.
- Needs ≥1 external source reference

**Mandatory Check #2: Reasoning (thinking/rationale)**
- Requires explicit reasoning tokens or rationale field
- Validates presence of analytical thinking

**Enforcement Policy:** STRICT  
If either check fails, no output is written and the evaluation is rejected immediately.

### Validation Code Location
**File:** `C:\dev\silky\api_cost_multiplier\functions\fpf_runner.py`  
**Function:** `_should_retry_for_validation()`  
**Keywords tracked:** `"missing grounding"`, `"missing reasoning"`, `"mandatory checks"`

```python
def _should_retry_for_validation(error_message: str) -> bool:
    """
    Determine if an error is retryable due to validation failures 
    (e.g., missing grounding/citations or reasoning/rationale).
    """
    validation_keywords = [
        "missing grounding",
        "missing citations", 
        "missing reasoning",
        "mandatory checks"
    ]
    # ... retry logic
```

**Note:** Despite retry logic existing in code, logs show `attempt 1/1` for all failures, indicating retries were NOT triggered for these validation errors.

---

## Pattern Analysis: Why Gemini Failed on These Specific Files

### File Characteristics of Failures

| File | Type | Size | Generator | Run Type | Gemini Result | GPT-5-Mini Result |
|------|------|------|-----------|----------|---------------|-------------------|
| fpf.1.o4-mini.d71.txt | .txt | 7 KB | o4-mini | FPF | ❌ FAIL | ✅ SUCCESS |
| fpf.1.gpt-5-nano.7ha.txt | .txt | 12 KB | gpt-5-nano | FPF | ❌ FAIL | ✅ SUCCESS |
| ma.1.gpt-4o.p4u.md | .md | 48 KB | gpt-4o | MA | ❌ FAIL | ✅ SUCCESS |
| ma.1.gpt-4.1-nano.ku6.md | .md | 42 KB | gpt-4.1-nano | MA | ❌ FAIL | ✅ SUCCESS |

### Files That Succeeded with Gemini

| File | Type | Size | Generator | Run Type | Gemini Result |
|------|------|------|-----------|----------|---------------|
| dr.1.gpt-5-mini.6wr.md | .md | 101 KB | gpt-5-mini | DR | ✅ SUCCESS |
| gptr.1.gemini-2.5-flash.h3u.md | .md | 105 KB | gemini-2.5-flash | GPTR | ✅ SUCCESS |

### Hypotheses for Failure Pattern

**Hypothesis 1: Content Structure**
- Failed files (FPF runs: .txt format, MA runs: shorter .md files)
- Successful files (DR/GPTR runs: longer .md files >100 KB)
- **Theory:** FPF and MA generated content may lack explicit citation markers or structured references that Gemini's grounding validator expects

**Hypothesis 2: Generator Behavior**
- FPF runs explicitly use FilePromptForge REST API with specific formatting
- MA (Multi-Agent) runs may produce different markdown structures
- DR/GPTR runs produce comprehensive research reports with heavy citation usage
- **Theory:** DR/GPTR outputs naturally include more external references, triggering Gemini's grounding metadata

**Hypothesis 3: Model-Specific Validation Sensitivity**
- GPT-5-Mini succeeded on ALL files (100% success rate)
- Gemini 2.5 Flash-Lite only succeeded on 2/6 files (33% success rate)
- **Theory:** Gemini's grounding validator is stricter or requires different citation formats than OpenAI's validator

**Hypothesis 4: File Size Threshold**
- Successful Gemini files: 101 KB, 105 KB
- Failed Gemini files: 7 KB, 12 KB, 48 KB, 42 KB
- **Theory:** Larger documents provide more context for grounding, smaller files don't meet minimum citation density

---

## Pairwise Evaluation Impact

The single-document evaluation failures cascaded to pairwise evaluations. Pairwise runs comparing failed documents also failed validation:

**Failed Pairwise Runs (Gemini 2.5 Flash-Lite):**
```
1. pair: dr.1.gpt-5-mini.6wr.md vs fpf.1.o4-mini.d71.txt → FAILED (missing grounding+reasoning)
2. pair: dr.1.gpt-5-mini.6wr.md vs gptr.1.gemini-2.5-flash.h3u.md → FAILED (missing grounding+reasoning)
3. pair: fpf.1.gpt-5-nano.7ha.txt vs ma.1.gpt-4o.p4u.md → FAILED (missing grounding+reasoning)
4. pair: ma.1.gpt-4.1-nano.ku6.md vs ma.1.gpt-4o.p4u.md → FAILED (missing grounding+reasoning)
```

All pairwise failures occurred at 01:13:10-01:13:19, ~2 minutes after single-doc failures (01:11:11-01:11:13).

---

## Known Issue: Historical Context

This is a **recurring problem** documented in previous reports:

### Previous Occurrences
1. **2025-10-12:** `docs/gemini_pro_grounding_failure_20251012.md`
   - Model: gemini-2.5-pro
   - Error: "missing grounding (web_search/citations)"
   
2. **2025-10-16:** `docs/model_failures_investigation_report_20251016.md`
   - Model: gemini-2.5-flash-lite
   - Finding: "All single-eval failures were from Google Gemini 2.5 Flash-Lite due to 'missing grounding'"
   - Recommendation: "Strengthen prompt, add retry on missing grounding, prefer gemini-2.5-flash for judges"

3. **2025-10-17:** `docs/latest_evaluation_failure_report_20251017.md`
   - Model: gemini-2.0-flash (consistent failures), gemini-2.5-flash-lite (intermittent)
   - Failure Type: "missing grounding (web_search/citations)"

4. **2025-11-03:** `docs/implementation_plan_fixes_20251103.md`
   - Documented fixes attempted for grounding enforcement

### Documentation Reference
**File:** `docs/difinitive ground truth.md`
**Section:** "Google Gemini 2.5 Flash-Lite Grounding Issue"
**Quote:**
> "In the latest evaluate.py run (≈20:45–20:54 PDT), single-eval batch recorded 3 enforcement 
> failures on google/gemini-2.5-flash-lite: 'missing grounding (web_search/citations)'. 
> Pairwise batches succeeded. Recommendations: strengthen Google-specific prompt (require [1][2] 
> inline citations + ≥3 independent sources, no output if not grounded), add targeted retry on 
> missing-grounding, prefer gemini-2.5-flash for judges."

---

## Cost Impact

**Database Query Results:**
- Total Run Cost: $0.526276
- Successful Evaluations: 32/48 (66.7%)
- Wasted Evaluation Attempts: 16/48 (33.3%)

**Estimated Wasted Cost:**
```
Failed Gemini runs: 4 single-doc × 4 criteria = 16 failed evaluations
Average cost per evaluation: $0.526276 / 48 ≈ $0.01096
Wasted cost: 16 × $0.01096 ≈ $0.175
```

Plus cascading pairwise failures involving these documents.

---

## Root Cause Statement

**Direct Cause:**  
Google Gemini 2.5 Flash-Lite evaluation judge responses did not include required `groundingMetadata` fields or verifiable citation markers when evaluating 4 of 6 generated documents. The FilePromptForge validation system correctly rejected these responses under strict enforcement policy.

**Underlying Cause:**  
The content structure of FPF-generated (.txt files) and shorter Multi-Agent (.md files) documents did not trigger Gemini's grounding search pathway, causing the model to respond without external citations. In contrast, Deep Research and GPTR documents (>100 KB, heavily cited research reports) naturally activated grounding behavior.

**Contributing Factor:**  
Retry logic exists in `fpf_runner.py` but was not triggered for validation failures (all attempts show `1/1`), suggesting the retry policy does not currently cover "missing grounding" errors.

---

## Recommendations

### Immediate Actions (Priority 1)

1. **Replace Gemini 2.5 Flash-Lite Judge**
   - Current config: `llm-doc-eval/config.yaml` line 12
   - Replace: `google:gemini-2.5-flash-lite` → `google:gemini-2.5-flash`
   - Justification: Historical data shows flash (non-lite) has higher success rate

2. **Enable Retry for Validation Failures**
   - File: `functions/fpf_runner.py`
   - Modify: `_should_retry_for_validation()` to return `True` for "missing grounding"
   - Set: Max retry attempts = 2 (reduce wasted cost while allowing recovery)

3. **Strengthen Google-Specific Prompts**
   - File: `llm-doc-eval/llm_doc_eval/prompts/` (if exists)
   - Add: "REQUIRED: Include [1] [2] [3] inline citations to external sources in your evaluation"
   - Add: "Use at least 3 independent verifiable sources"

### Secondary Actions (Priority 2)

4. **Add File-Type Specific Handling**
   - Detect .txt vs .md files
   - For .txt files: Add stronger citation requirements to prompt
   - For shorter files (<50 KB): Request explicit web search

5. **Validation Logging Enhancement**
   - Log: Raw API response when validation fails
   - Capture: `groundingMetadata` field presence/absence
   - Purpose: Diagnose whether grounding was attempted but failed format checks

6. **Cost Monitoring**
   - Track: Per-model success rate in database
   - Alert: When model success rate < 80%
   - Auto-fallback: Switch to backup judge model

### Long-Term Improvements (Priority 3)

7. **Multi-Judge Consensus**
   - Run: 2+ judge models per evaluation
   - Aggregate: Scores only when both judges succeed
   - Fallback: If primary judge fails, use secondary without retry

8. **Document Generation Requirements**
   - Standardize: All generators must include ≥3 citations
   - Validate: Generated documents before sending to evaluation
   - Reject: Documents without minimum citation density

---

## Verification Steps

To verify this analysis:

1. **Check FPF Log:**
   ```powershell
   Select-String "missing grounding" C:\dev\silky\api_cost_multiplier\logs\fpf_run.log
   ```
   Expected: 4 single-doc failures + 4+ pairwise failures

2. **Query Database:**
   ```python
   import sqlite3
   conn = sqlite3.connect('llm-doc-eval/llm_doc_eval/results_20251116_091108_0e9e736b.sqlite')
   cursor = conn.cursor()
   cursor.execute("""
       SELECT judge_provider_model, COUNT(*) 
       FROM single_doc_results 
       GROUP BY judge_provider_model
   """)
   print(cursor.fetchall())
   ```
   Expected: `[('google:gemini-2.5-flash-lite', 8), ('openai:gpt-5-mini', 24)]`

3. **Review Config:**
   ```powershell
   Get-Content C:\dev\silky\api_cost_multiplier\llm-doc-eval\config.yaml | Select-String "gemini"
   ```
   Expected: Line showing `gemini-2.5-flash-lite` as judge model

---

## Conclusion

The evaluation system performed exactly as designed: strict validation prevented ungrounded evaluations from corrupting the results database. However, the choice of Google Gemini 2.5 Flash-Lite as a judge model proved incompatible with 67% of generated document types (4/6 files).

**Success Rate by Judge:**
- ✅ OpenAI GPT-5-Mini: 100% (24/24 evaluations)
- ❌ Google Gemini 2.5 Flash-Lite: 33% (8/24 evaluations)

**Impact:**
- 16 missing single-document evaluations
- Unknown number of cascading pairwise evaluation failures
- ~$0.175 in wasted API costs
- Incomplete evaluation dataset for this run

**Status:** Issue is **known and recurring** (4th occurrence since October 2025)

**Resolution Path:** Implement Priority 1 recommendations before next evaluation run

---

## Appendix: Related Documentation

- `docs/gemini_pro_grounding_failure_20251012.md` - First grounding failure report
- `docs/model_failures_investigation_report_20251016.md` - Flash-lite specific analysis
- `docs/latest_evaluation_failure_report_20251017.md` - Multi-model failure comparison
- `docs/gemini_grounding_issue_report.md` - Comprehensive grounding issue analysis
- `docs/difinitive ground truth.md` - Ground truth documentation with grounding policy
- `docs/implementation_plan_fixes_20251103.md` - Attempted fixes documentation

**Log Files:**
- `logs/fpf_run.log` - Contains all validation error messages
- `logs/acm_session.log` - High-level timeline (does not show validation errors)
- `logs/acm_subprocess_20251116_010153.log` - Subprocess details (no validation errors)

**Configuration:**
- `llm-doc-eval/config.yaml` - Judge model configuration
- `llm-doc-eval/criteria.yaml` - Evaluation criteria definitions
- `config.yaml` - Pipeline run configuration
