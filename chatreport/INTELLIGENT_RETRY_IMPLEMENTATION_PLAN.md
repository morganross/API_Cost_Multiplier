# Intelligent Retry Implementation Plan for FPF Validation Failures

**Created:** 2025-11-16  
**Context:** Greenbag4 had 2/14 evaluation failures due to gemini-2.5-flash-lite validation issues  
**Goal:** Implement intelligent retry with 92-100% evaluation success rate  

---

## Problem Statement

**Current Behavior:**
- FPF validation failures exit with code 0 (success)
- fpf_runner.py only retries on non-zero exit codes
- 2 evaluations permanently lost in greenbag4 (ab2b6e81, 8e389e4a)
- Both failures: gemini-2.5-flash-lite missing grounding metadata

**Root Cause:**
```python
# In fpf_runner.py line 425
if process.returncode != 0:  # ← Never triggers for validation failures
    # retry logic here...
```

**Impact:** 85.7% evaluation success (12/14) vs potential 100% with retry

---

## Architecture: 4-Layer Intelligent Retry System

### **Layer 1: Exit Code Protocol** (Primary Signal)
**File:** `FilePromptForge/file_handler.py`  
**Change:** Catch ValidationError and exit with specific codes

**Exit Code Mapping:**
- `0` = Success (validation passed)
- `1` = Validation failure: missing grounding only
- `2` = Validation failure: missing reasoning only  
- `3` = Validation failure: missing both grounding and reasoning
- `4` = Validation failure: unknown type
- `5` = Other errors (network, API, etc.)

**Implementation:**
```python
# In file_handler.py, wrap assert_grounding_and_reasoning call:

try:
    _ge.assert_grounding_and_reasoning(raw_json, provider=provider)
    # ... existing success path ...
except _ge.ValidationError as ve:
    LOG.error("Validation failed: %s", ve)
    print(f"[VALIDATION FAILED] {ve}", file=sys.stderr, flush=True)
    
    # Exit with specific code based on what's missing
    if ve.missing_grounding and ve.missing_reasoning:
        sys.exit(3)  # Both missing
    elif ve.missing_grounding:
        sys.exit(1)  # Grounding only
    elif ve.missing_reasoning:
        sys.exit(2)  # Reasoning only
    else:
        sys.exit(4)  # Unknown validation error
except Exception as e:
    LOG.exception("Unexpected error during FPF execution")
    print(f"[FPF ERROR] {e}", file=sys.stderr, flush=True)
    sys.exit(5)
```

**Why First:** 
- Standard Unix convention
- Works immediately with existing retry infrastructure
- Single point of truth (exit code)
- No file system dependency

**Deployment Risk:** LOW (isolated change, clear error handling)

---

### **Layer 2: Failure Report Detection** (Fallback Signal)
**File:** `functions/fpf_runner.py`  
**Function:** `_run_once_sync()` (after line ~420)

**Add after subprocess completion:**
```python
# After process.wait() and thread joins (around line 420)
if process.returncode == 0:
    # Check for validation failure reports (Layer 1 fallback)
    validation_log_dir = Path(_FPF_DIR) / "logs" / "validation"
    
    if validation_log_dir.exists():
        # Look for recent failure reports (last 5 seconds)
        import time
        cutoff_time = time.time() - 5
        
        recent_failures = []
        for report_file in validation_log_dir.glob("*-FAILURE-REPORT.json"):
            if report_file.stat().st_mtime > cutoff_time:
                recent_failures.append(report_file)
        
        if recent_failures:
            # Found validation failure despite exit code 0
            logger.warning(f"FPF run {run_index}: exit code 0 but found failure report (Layer 1 missed)")
            
            try:
                with open(recent_failures[0], 'r', encoding='utf-8') as f:
                    failure_data = json.load(f)
                
                missing = failure_data.get("missing", [])
                has_grounding = not any("grounding" in m for m in missing)
                has_reasoning = not any("reasoning" in m for m in missing)
                
                # Override returncode to trigger retry
                if not has_grounding and not has_reasoning:
                    process.returncode = 3
                elif not has_grounding:
                    process.returncode = 1
                elif not has_reasoning:
                    process.returncode = 2
                else:
                    process.returncode = 4
                
                logger.info(f"Set returncode={process.returncode} based on failure report")
                
            except Exception as e:
                logger.error(f"Failed to parse failure report: {e}")
```

**Why Second:**
- Catches cases where Layer 1 fails or isn't deployed yet
- Uses existing failure reports (no new infrastructure)
- Backward compatible (no changes if Layer 1 works)

**Deployment Risk:** LOW (pure detection, doesn't change FPF)

---

### **Layer 3: Enhanced Retry Logic** (Action)
**File:** `functions/fpf_runner.py`  
**Section:** Lines 425-530 (existing retry logic)

**Modify retry detection:**
```python
if process.returncode != 0:
    stderr_out = "\n".join(stderr_lines)
    
    # Detect validation failures by exit code
    is_validation_failure = process.returncode in (1, 2, 3, 4)
    
    if is_validation_failure:
        # Map exit code to error category
        validation_type_map = {
            1: ErrorCategory.VALIDATION_GROUNDING,
            2: ErrorCategory.VALIDATION_REASONING,
            3: ErrorCategory.VALIDATION_BOTH,
            4: ErrorCategory.VALIDATION_BOTH,  # Unknown, treat as both
        }
        error_category = validation_type_map.get(process.returncode)
        
        if _HAS_ERROR_CLASSIFIER:
            retry_strategy = get_retry_strategy(error_category)
            max_retries = retry_strategy.max_retries  # Should be 2
        else:
            max_retries = 2  # Fallback
        
        logger.warning(f"FPF run {run_index}: validation failure (code {process.returncode}), category={error_category.value if error_category else 'unknown'}, max_retries={max_retries}")
    
    else:
        # Non-validation errors: use existing classification
        exc = RuntimeError(f"FilePromptForge run {run_index} failed with exit code {process.returncode}")
        
        if _HAS_ERROR_CLASSIFIER:
            error_category = classify_error(exc, stderr_text=stderr_out)
            retry_strategy = get_retry_strategy(error_category)
            max_retries = retry_strategy.max_retries
        else:
            error_category = None
            max_retries = 1 if _should_retry_for_validation(stderr_out) else 0
    
    # Retry loop (existing code continues...)
    for attempt in range(1, max_retries + 1):
        logger.warning(f"FilePromptForge run {run_index} failed (attempt {attempt}/{max_retries}), retrying...")
        
        # Calculate backoff delay
        if is_validation_failure:
            # Exponential backoff for validation: 1s, 2s, 4s
            delay_ms = 1000 * (2 ** (attempt - 1))
            logger.info(f"Validation retry backoff: {delay_ms}ms")
            import time
            time.sleep(delay_ms / 1000.0)
        elif _HAS_ERROR_CLASSIFIER and error_category:
            delay_ms = calculate_backoff_delay(error_category, attempt)
            if delay_ms > 0:
                logger.info(f"Backing off {delay_ms}ms before retry attempt {attempt}")
                import time
                time.sleep(delay_ms / 1000.0)
        
        # Prepare retry with enhanced instructions
        use_retry_file_a = use_file_a_path
        
        if is_validation_failure:
            # Use validation-specific enhancement
            try:
                failure_type = {
                    1: "grounding",
                    2: "reasoning",
                    3: "both",
                    4: "both"
                }.get(process.returncode, "both")
                
                use_retry_file_a = _ensure_enhanced_instructions_validation(
                    file_a_path, run_temp, failure_type, attempt
                )
                logger.info(f"Applied validation-enhanced prompt for {failure_type} failure (attempt {attempt})")
            except Exception as e:
                logger.warning(f"Failed to apply validation enhancement: {e}")
                # Fallback to generic enhancement
                try:
                    use_retry_file_a = _ensure_enhanced_instructions(file_a_path, run_temp, "retry")
                except Exception:
                    pass
        
        elif _HAS_ERROR_CLASSIFIER and error_category and retry_strategy.prompt_enhancement:
            # Use generic enhancement for other retryable errors
            try:
                use_retry_file_a = _ensure_enhanced_instructions(file_a_path, run_temp, "retry")
            except Exception as e:
                logger.warning(f"Failed to apply enhanced preamble: {e}")
        
        # ... existing retry subprocess code continues ...
```

**Why Third:**
- Leverages exit codes from Layers 1-2
- Uses existing retry infrastructure
- Adds intelligent backoff timing
- Enables targeted prompt enhancement

**Deployment Risk:** MEDIUM (modifies retry flow, extensive testing needed)

---

### **Layer 4: Prompt Enhancement Templates** (Targeted Fixes)
**File:** `functions/fpf_runner.py`  
**New Function:** Add after existing `_ensure_enhanced_instructions()`

```python
def _build_validation_enhanced_preamble(failure_type: str, attempt_number: int) -> str:
    """
    Build enhanced instructions based on specific validation failure type.
    
    Args:
        failure_type: One of "grounding", "reasoning", or "both"
        attempt_number: Which retry attempt (1, 2, etc.) - increases urgency
    
    Returns:
        Enhanced preamble text to prepend to file_a content
    """
    urgency_level = ["CRITICAL", "MANDATORY", "ABSOLUTE"][min(attempt_number - 1, 2)]
    
    preamble = f"\n{'='*80}\n"
    preamble += f"{urgency_level} VALIDATION REQUIREMENTS (Retry Attempt {attempt_number})\n"
    preamble += f"{'='*80}\n\n"
    preamble += "YOUR PREVIOUS RESPONSE WAS REJECTED. You must fix the following issues:\n\n"
    
    if failure_type in ("grounding", "both"):
        preamble += "**GROUNDING REQUIREMENTS:**\n"
        preamble += "1. You MUST use Google Search tools to search the web for factual information\n"
        preamble += "2. Your response MUST include groundingMetadata with webSearchQueries\n"
        preamble += "3. Include at least 5 specific search queries you performed\n"
        preamble += "4. Cite sources using [1], [2], [3] notation in your text\n"
        preamble += "5. Include 'searchEntryPoint' with rendered search chips\n"
        preamble += "6. DO NOT claim to search the web without actually searching\n"
        preamble += "7. DO NOT return empty groundingMetadata: {}\n\n"
    
    if failure_type in ("reasoning", "both"):
        preamble += "**REASONING REQUIREMENTS:**\n"
        preamble += "1. Your response MUST include explicit reasoning/rationale\n"
        preamble += "2. Add a 'Reasoning' or 'Analysis' section explaining your thought process\n"
        preamble += "3. Show step-by-step how you arrived at each conclusion\n"
        preamble += "4. Explain why you chose specific scores or judgments\n"
        preamble += "5. Include content.parts[].text with substantial reasoning text\n"
        preamble += "6. DO NOT provide bare scores without explanation\n\n"
    
    preamble += f"**CONSEQUENCES:**\n"
    preamble += f"- This is retry attempt {attempt_number}\n"
    preamble += f"- Your response will be validated against these requirements\n"
    preamble += f"- Failure means this evaluation cannot be completed\n"
    preamble += f"- You MUST include both grounding AND reasoning to pass validation\n\n"
    preamble += f"{'='*80}\n\n"
    
    return preamble


def _ensure_enhanced_instructions_validation(
    file_a_path: str,
    run_temp: str,
    failure_type: str,
    attempt_number: int
) -> str:
    """
    Create enhanced version of file_a with validation-specific requirements.
    
    Args:
        file_a_path: Original file_a path
        run_temp: Temp directory for this run
        failure_type: "grounding", "reasoning", or "both"
        attempt_number: Which retry attempt (1, 2, etc.)
    
    Returns:
        Path to enhanced file_a
    """
    try:
        with open(file_a_path, "r", encoding="utf-8") as f:
            original_content = f.read()
        
        # Build targeted enhancement
        enhanced_preamble = _build_validation_enhanced_preamble(failure_type, attempt_number)
        
        # Prepend to original content
        enhanced_content = enhanced_preamble + original_content
        
        # Write to new file
        enhanced_path = os.path.join(run_temp, f"file_a_enhanced_validation_{failure_type}_attempt{attempt_number}.txt")
        with open(enhanced_path, "w", encoding="utf-8") as f:
            f.write(enhanced_content)
        
        logger.debug(f"Created validation-enhanced file_a at {enhanced_path} ({len(enhanced_preamble)} chars added)")
        return enhanced_path
        
    except Exception as e:
        logger.error(f"Failed to create validation-enhanced file_a: {e}")
        return file_a_path  # Fallback to original
```

**Why Fourth:**
- Targeted fixes based on specific failure mode
- Escalating urgency across retry attempts
- Explicit instructions for Gemini API requirements
- Reusable across different failure scenarios

**Deployment Risk:** LOW (pure function, well-isolated)

---

## Implementation Steps

### **Phase 1: Foundation (30 min)**

**Step 1.1:** Add exit code handling to `file_handler.py`
- Location: Where `assert_grounding_and_reasoning()` is called
- Change: Wrap in try/except with specific exit codes
- Test: Run FPF with known validation failure

**Step 1.2:** Verify exit codes propagate
- Run: `python fpf_main.py --config ... --file-a ... --file-b ...` with failing scenario
- Check: `echo $LASTEXITCODE` shows 1, 2, or 3
- Debug: Add print statements if needed

### **Phase 2: Detection (20 min)**

**Step 2.1:** Add failure report detection to `fpf_runner.py`
- Location: After `process.wait()` in `_run_once_sync()`
- Change: Check for recent failure reports if exit code 0
- Test: Use existing greenbag4 failure reports

**Step 2.2:** Verify detection triggers
- Run: Small eval test with 1 document
- Check: Logs show "Set returncode=X based on failure report"
- Debug: Print failure report paths found

### **Phase 3: Retry Logic (40 min)**

**Step 3.1:** Modify retry detection logic
- Location: Lines 425-442 in `fpf_runner.py`
- Change: Detect validation failures by exit code
- Map: Exit codes → ErrorCategory enums

**Step 3.2:** Add validation-specific backoff
- Location: Within retry loop
- Change: Use exponential backoff for validation failures
- Test: Verify 1s, 2s, 4s delays in logs

**Step 3.3:** Integrate prompt enhancement
- Location: Within retry loop, before retry subprocess
- Change: Call `_ensure_enhanced_instructions_validation()`
- Test: Verify enhanced file created

### **Phase 4: Enhancement (25 min)**

**Step 4.1:** Add `_build_validation_enhanced_preamble()`
- Location: New function in `fpf_runner.py`
- Content: Failure-type-specific instructions
- Test: Call function directly, inspect output

**Step 4.2:** Add `_ensure_enhanced_instructions_validation()`
- Location: New function in `fpf_runner.py`
- Content: File creation with enhanced preamble
- Test: Verify file created with correct content

### **Phase 5: Testing (30 min)**

**Step 5.1:** Unit test individual functions
- Test: `_build_validation_enhanced_preamble()` for each failure type
- Test: Exit code detection logic
- Test: Failure report parsing

**Step 5.2:** Integration test with mock failures
- Create: Test files that will fail validation
- Run: Through fpf_runner
- Verify: Retry triggered, logs show correct flow

**Step 5.3:** Real-world test with greenbag4 scenarios
- Use: Existing failure cases (ab2b6e81, 8e389e4a)
- Simulate: Retry behavior
- Verify: Enhanced prompts would have helped

### **Phase 6: Documentation (10 min)**

**Step 6.1:** Update FilePromptForge README
- Document: New exit codes
- Explain: What each code means
- Add: Example error scenarios

**Step 6.2:** Add docstrings
- Functions: All new functions fully documented
- Logic: Complex sections explained with comments
- Examples: Usage examples in docstrings

**Step 6.3:** Update greenbag timeline
- Note: Retry implementation added
- Track: Before/after success rates
- Document: Lessons learned

---

## Expected Outcomes

### **Metrics**

**Before Implementation:**
```
Greenbag4 Evaluation Results:
- Total evaluations: 14 (7 docs × 2 evaluators)
- Successful: 12 (85.7%)
- Failed: 2 (14.3%)
  - ab2b6e81: FPF o4-mini / gemini-2.5-flash-lite (grounding missing)
  - 8e389e4a: MA gpt-4.1-nano / gemini-2.5-flash-lite (both missing)
- Retry attempts: 0 (retry logic never triggered)
```

**After Implementation (Conservative Estimate):**
```
Expected Greenbag5 Results:
- Total evaluations: 14
- First-attempt success: 12 (85.7%)
- Validation failures: 2
  - Retry attempt 1: 1 success (50% recovery)
  - Retry attempt 2: 1 success (50% recovery)
- Final successful: 14 (100%)
- Failed: 0 (0%)
```

**After Implementation (Realistic Estimate):**
```
Expected with gemini-2.5-flash-lite variability:
- Total evaluations: 14
- First-attempt success: 12 (85.7%)
- Validation failures: 2
  - Retry attempt 1: 1 success (50% recovery)
  - Retry attempt 2: 0 success (stubborn failure)
- Final successful: 13 (92.9%)
- Failed: 1 (7.1%)
```

### **Cost Analysis**

**API Cost Impact:**
```
Per Retry Attempt:
- Input tokens: ~3,500 (document + enhanced prompt)
- Output tokens: ~300 (evaluation response)
- Gemini 2.5 Flash Lite pricing: ~$0.0003/retry

Greenbag5 Expected:
- 2 validation failures × 2 retries = 4 retry attempts
- Total additional cost: ~$0.0012
- Benefit: 1-2 additional successful evaluations
- ROI: 50-100% improvement in completion rate for <$0.01
```

### **Performance Impact**

**Time Analysis:**
```
Retry Overhead per Failure:
- Backoff delays: 1s + 2s = 3s
- API calls: 2 × 4s = 8s
- Total: ~11s per failure

Greenbag5 Expected:
- 2 failures × 11s = 22s additional runtime
- Original runtime: ~6 minutes
- New runtime: ~6.5 minutes
- Impact: +8% runtime for +7-14% success rate
```

### **Reliability Improvement**

**Failure Modes Addressed:**
1. ✅ Empty groundingMetadata (Layer 4 explicitly requires web searches)
2. ✅ Missing reasoning text (Layer 4 demands step-by-step explanations)
3. ✅ Silent validation failures (Layers 1-2 ensure detection)
4. ✅ No retry on validation errors (Layer 3 enables retries)

**Failure Modes Remaining:**
1. ⚠️ Gemini API fundamental issues (content filtering, quota)
2. ⚠️ Model capability limits (cannot generate required content)
3. ⚠️ Persistent validation failures (max 2 retries)

---

## Risk Assessment

### **High Risks** 🔴

None identified - all changes are well-isolated and backward compatible.

### **Medium Risks** 🟡

**Risk 1: Exit code changes affect external tools**
- **Impact:** Tools expecting exit code 0 may interpret 1-3 as failure
- **Mitigation:** Document new exit codes, provide compatibility flag
- **Probability:** Low (fpf_runner is only consumer)

**Risk 2: Retry loop infinite recursion**
- **Impact:** Endless retries consume API quota
- **Mitigation:** Hard cap at 2 retries (already in error_classifier)
- **Probability:** Very Low (explicit loop control)

**Risk 3: Enhanced prompts change evaluation behavior**
- **Impact:** Scores may differ from non-retry evaluations
- **Mitigation:** Only applies to retries, not first attempts
- **Probability:** Low (same criteria, more explicit instructions)

### **Low Risks** 🟢

**Risk 4: File system race conditions**
- **Impact:** Failure report not found despite recent creation
- **Mitigation:** 5-second window, timestamp checking
- **Probability:** Very Low (local file system)

**Risk 5: Increased log verbosity**
- **Impact:** Larger log files, harder to parse
- **Mitigation:** Structured logging, clear markers
- **Probability:** Acceptable (better debugging worth it)

---

## Validation Plan

### **Pre-Deployment Tests**

**Test 1: Exit Code Verification**
```bash
# Run FPF with known validation failure
python fpf_main.py --config test_config.yaml --file-a failing_doc.txt --file-b url.txt
echo $LASTEXITCODE
# Expected: 1, 2, or 3 (not 0)
```

**Test 2: Failure Report Detection**
```python
# Create mock failure report
# Run fpf_runner with exit code 0
# Verify returncode override
assert process.returncode in (1, 2, 3)
```

**Test 3: Retry Triggering**
```python
# Force validation failure
# Verify retry log messages appear
# Check enhanced file_a created
assert "retry attempt 1" in logs
```

**Test 4: Enhanced Prompt Content**
```python
# Generate enhanced prompt
preamble = _build_validation_enhanced_preamble("grounding", 1)
assert "MUST use Google Search" in preamble
assert "webSearchQueries" in preamble
```

### **Post-Deployment Monitoring**

**Monitor 1: Success Rate Tracking**
```
Track per evaluation run:
- First-attempt success rate
- Retry success rate (attempt 1)
- Retry success rate (attempt 2)
- Final success rate
- Compare to baseline (greenbag4: 85.7%)
```

**Monitor 2: Failure Analysis**
```
For each remaining failure:
- What failure type? (grounding/reasoning/both)
- How many retry attempts?
- What was different in enhanced prompts?
- Is pattern persistent across models?
```

**Monitor 3: Performance Metrics**
```
Track per evaluation run:
- Total runtime
- Retry overhead (seconds)
- API cost increase
- Cost per additional success
```

---

## Rollback Plan

### **Trigger Conditions**

Rollback if any of these occur:
1. Success rate drops below 85% (worse than baseline)
2. Runtime increases >25% (unacceptable overhead)
3. Retry loop causes infinite recursion (safety issue)
4. API costs increase >10× (quota issue)

### **Rollback Procedure**

**Step 1:** Revert exit code changes (10 min)
```bash
git checkout HEAD~1 FilePromptForge/file_handler.py
git checkout HEAD~1 functions/fpf_runner.py
```

**Step 2:** Verify rollback (5 min)
```bash
# Run simple test
python generate.py --preset test_single_doc
# Check logs for old behavior (no retry attempts)
```

**Step 3:** Document rollback reason (5 min)
- Record what triggered rollback
- Capture metrics at time of rollback
- Identify specific failure mode
- Plan alternative approach

---

## Success Criteria

### **Phase 1 Success (Foundation)**
- ✅ FPF exits with code 1-3 for validation failures
- ✅ Exit code 0 only for successful validations
- ✅ Exit codes propagate to fpf_runner
- ✅ Logs show "Validation failed: ..." with exit code

### **Phase 2 Success (Detection)**
- ✅ Failure reports detected within 5 seconds
- ✅ Return code overridden when failure report found
- ✅ Logs show "Set returncode=X based on failure report"
- ✅ Layer 2 catches Layer 1 misses

### **Phase 3 Success (Retry Logic)**
- ✅ Retry triggered on exit codes 1-3
- ✅ Exponential backoff delays logged (1s, 2s, 4s)
- ✅ Max 2 retry attempts per failure
- ✅ Enhanced prompt applied on retry
- ✅ Existing non-validation retry logic preserved

### **Phase 4 Success (Enhancement)**
- ✅ Enhanced preamble includes failure-specific instructions
- ✅ Grounding failures get search requirements
- ✅ Reasoning failures get explanation requirements
- ✅ Escalating urgency across attempts
- ✅ Enhanced file created before retry subprocess

### **Overall Success Criteria**
- 🎯 Evaluation success rate: ≥92% (13/14 or 14/14)
- 🎯 Retry recovery rate: ≥50% (1/2 failures recovered)
- 🎯 Runtime overhead: ≤15% increase
- 🎯 API cost increase: ≤5%
- 🎯 Zero infinite retry loops
- 🎯 Backward compatible with existing generate.py

---

## Next Steps

1. **Approve this plan** ✋ (requires user confirmation)
2. **Implement Phase 1** (exit codes)
3. **Test Phase 1** (verify exit codes work)
4. **Implement Phase 2** (failure detection)
5. **Test Phase 2** (verify detection works)
6. **Implement Phase 3** (retry logic)
7. **Implement Phase 4** (prompt enhancement)
8. **Integration test** (full flow)
9. **Deploy to greenbag5** (real-world test)
10. **Analyze results** (success rate improvement)

---

## References

- **error_classifier.py**: Defines ErrorCategory.VALIDATION_GROUNDING, VALIDATION_REASONING, VALIDATION_BOTH
- **grounding_enforcer.py**: Raises ValidationError with missing_grounding/missing_reasoning flags
- **fpf_runner.py**: Existing retry logic (lines 425-530)
- **Greenbag4 failures**: 
  - ab2b6e81: FPF o4-mini / gemini-2.5-flash-lite (grounding)
  - 8e389e4a: MA gpt-4.1-nano / gemini-2.5-flash-lite (both)

---

**END OF IMPLEMENTATION PLAN**
