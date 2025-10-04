# Multi-Agent Response Normalization and Robustness Plan (ACM)

## 1. Introduction
This document outlines a plan to enhance the robustness of the Multi-Agent (MA) flow within the `api_cost_multiplier` (ACM) project. The primary goal is to ensure that the planner step of the MA pipeline can accept and correctly process various response formats from Large Language Models (LLMs) – including dicts, JSON strings, and narrative text – without crashing. This approach avoids direct modifications to the external `gpt-researcher` library by implementing normalization within ACM's `MA_runner.py`.

## 2. Problem Statement
During recent `generate.py` runs, certain LLMs (e.g., `gemini-2.5-flash`, `gpt-4o-mini`, `gpt-5-nano`) failed at the planner step with an `AttributeError: 'str' object has no attribute 'get'`. This occurs because the MA framework's `editor.py` expects a structured dictionary object (with keys like "title, date, sections") from the LLM when `plan.get("key")` is called. Some LLMs, despite prompting and `response_format="json"` parameters, returned plain text strings instead of dictionaries, leading to a crash.

## 3. Scope of Work
All modifications will be confined to the `api_cost_multiplier` (ACM) codebase. The `gpt-researcher` library will be treated as an external, immutable dependency.

## 4. Detailed Implementation Plan

### 4.1. Normalize Planner Output in `functions/MA_runner.py`

**Objective:** Implement a robust mechanism to convert diverse LLM outputs into a standardized dictionary format before `gpt-researcher`'s `editor.py` consumes them.

**File to Modify:** `api_cost_multiplier/functions/MA_runner.py`

**Specific Changes:**

1.  **Add necessary imports:**
    *   Import `re` for regular expression parsing.
    *   Import `datetime` for date formatting within the normalizer.
    *   Ensure required `typing` imports (`Dict`, `Any`, `Optional`) are present.

2.  **Implement `_normalize_plan_output` function:**
    *   This will be a new asynchronous helper function that takes `plan_raw` (the raw output from the LLM), `max_sections`, and `task_config` (for context) as input.
    *   **Input Type Handling:**
        *   **If `plan_raw` is already a `dict`:** Coerce its "title", "date", and "sections" fields to expected types/formats. Ensure sections are a `list[str]`. Apply `max_sections` truncation if specified.
        *   **If `plan_raw` is a `str`:**
            *   Attempt `json.loads()` directly. If successful and results in a `dict` or `list`, recursively call `_normalize_plan_output` with the parsed object.
            *   If direct `json.loads()` fails, attempt to find a JSON object (`{...}`) or a JSON list (`[...]`) within the string using regex. If found, attempt `json.loads()` on the extracted substring and recurse.
            *   **Fallback (narrative text):** If no valid JSON is found, create a minimal dictionary structure. Extract a title from the first meaningful line of the text and create a default section (e.g., "Initial Research Plan").
    *   **Guarantees:** This function will *always* return a `dict` with at least "title", "date", and "sections" keys, ensuring downstream code does not encounter `AttributeError`.
    *   **Tracing:** Include an `_raw_output_type` key in the returned dict for debugging, indicating if the original output was `dict`, `json_string`, or `string`.

3.  **Integrate `_normalize_plan_output` into `run_multi_agent_once`:**
    *   After the MA CLI subprocess completes successfully and the `md_path` to the generated report is determined:
        *   Read the content of `found_md_path`.
        *   Call `_normalize_plan_output` with this raw content and the `task_config`.
        *   **Overwrite** the content of `found_md_path` with the JSON representation of the `normalized_content` (using `json.dump`).
        *   Add robust error handling for the normalization step, logging warnings if normalization fails but allowing the original content to persist to avoid outright blocking.

### 4.2. Update Task Configuration in `functions/MA_runner.py`

**Objective:** Refine the task configuration passed to the MA CLI to provide clearer defaults and better instructions.

**File to Modify:** `api_cost_multiplier/functions/MA_runner.py` (within `run_multi_agent_runs`)

**Specific Changes:**

1.  **Enrich `task_cfg` dictionary:**
    *   When creating the `task_cfg` dictionary inside `run_multi_agent_runs`, ensure it includes standard fields expected by `gpt-researcher`'s `Multi_Agent_CLI.py` (which were previously defaults or manually patched). These ensure the MA CLI has complete context for its operation.
    *   Example fields to add/ensure:
        ```python
        task_cfg = {
            "model": model_value,
            "publish_formats": {
                "markdown": True,
                "pdf": False,  # WeasyPrint issues are separate
                "docx": True
            },
            "max_sections": max_sections_from_config_or_default, # Ensure this is passed
            "include_human_feedback": False,
            "follow_guidelines": False,
            "verbose": True,
            # query is supplied via --query-file to MA_CLI
        }
        ```

## 5. Test Plan

1.  **Modified Models-Only Test:**
    *   Re-run `generate.py` with `config.yaml` configured to only run the models that previously failed at the planner step (e.g., `gemini-2.5-flash`, `gpt-4o-mini`, `gpt-5-nano`).
    *   **Expected Results:**
        *   No `AttributeError: 'str' object has no attribute 'get'` crashes.
        *   All MA runs should complete successfully and produce a `.md` report.
        *   Inspect the generated `.md` files; they should contain JSON structures for the plan (title, date, sections).
        *   Log messages should ideally show "[MA_runner] Warning: Failed to normalize MA report..." if models did not originally return JSON, confirming the fallback path was taken.

2.  **Full Regression Test (Optional but Recommended):**
    *   Run `generate.py` with the original full set of models including those that previously succeeded.
    *   **Expected Results:** All MA runs (succeeding and previously failing) should complete without crashes and generate valid reports.

## 6. Verification Criteria

*   All MA runs complete without `AttributeError` crashes in `editor.py`.
*   Generated `.md` reports for MA runs contain a JSON structure, ensuring compatibility with `gpt-researcher`'s internal data flow.
*   The `_raw_output_type` field in the generated MA JSON reports accurately reflects whether the original model output was `dict`, `json_string`, or `string`.

## 7. Rollback Plan
In case of critical issues, revert changes to `api_cost_multiplier/functions/MA_runner.py` and `api_cost_multiplier/runner.py` to their versions prior to this implementation.
