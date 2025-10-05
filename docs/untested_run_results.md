# Untested Runs — Results summary
Date: 2025-10-04 21:21 (local)

This file records the runs executed by `python api_cost_multiplier/generate.py` after replacing `config.yaml` with the test config targeting untested registry models. It lists each run in order, whether it succeeded or failed, and notes (error messages or saved output paths).

Context
- Test config used: api_cost_multiplier/config.yaml (temporary test config — outputs written to api_cost_multiplier/test/mdoutputs_untested)
- One input file processed: api_cost_multiplier/test/mdinputs/commerce/Census Bureau.md
- The runner executed 10 runs (index 0..9). Below are their outcomes.

Runs (in execution order)
1) Run #0
- type: gptr
- provider: openai
- model: codex-mini
- Result: FAIL
- Notes: gpt-researcher subprocess failed; error during JSON parsing / repair:
  "the JSON object must be str, bytes or bytearray, not NoneType" — reported as:
  "gpt-researcher failed: gpt-researcher programmatic run failed: expected string or bytes-like object, got 'NoneType'".
  No report saved.

2) Run #1
- type: gptr
- provider: openai
- model: o3-pro
- Result: FAIL
- Notes: Same JSON / programmatic error as Run #0:
  "expected string or bytes-like object, got 'NoneType'".
  No report saved.

3) Run #2
- type: gptr
- provider: openai
- model: o1
- Result: SUCCESS
- Saved output: temp_gpt_researcher_reports\research_report_0ef6a765-7ecb-4ed5-940e-d483e87f613d.md
- Saved copy: C:\dev\silky\api_cost_multiplier\test\mdoutputs_untested\commerce
- Notes: gpt-researcher produced a Markdown research report (model canonical id printed as openai:o1).

4) Run #3
- type: gptr
- provider: openai
- model: o1-preview
- Result: FAIL
- Notes: JSON/programmatic error: "expected string or bytes-like object, got 'NoneType'".
  No report saved.

5) Run #4
- type: gptr
- provider: google_genai
- model: gemini-live-2.5-flash-preview
- Result: FAIL
- Notes: Provider API returned model-not-found for this name:
  "404 models/gemini-live-2.5-flash-preview is not found for API version v1beta, or is not supported for generateContent."
  Followed by the JSON/programmatic error from gpt-researcher.
  No report saved.

6) Run #5
- type: gptr
- provider: anthropic
- model: claude-opus-4-1-20250805
- Result: SUCCESS
- Saved output: temp_gpt_researcher_reports\research_report_ad6bf8ee-fb61-465b-83aa-9b5f9ce4d5cf.md
- Saved copy: C:\dev\silky\api_cost_multiplier\test\mdoutputs_untested\commerce
- Notes: The runner auto-installed langchain-anthropic and produced a report.

7) Run #6
- type: gptr
- provider: anthropic
- model: claude-opus-4-20250514-thinking
- Result: FAIL
- Notes: JSON/programmatic error: "expected string or bytes-like object, got 'NoneType'".
  No report saved.

8) Run #7
- type: gptr
- provider: anthropic
- model: claude-3-7-sonnet-latest
- Result: SUCCESS
- Saved output: temp_gpt_researcher_reports\research_report_7f576b74-c5cf-4cac-99e8-f6ec39942483.md
- Saved copy: C:\dev\silky\api_cost_multiplier\test\mdoutputs_untested\commerce

9) Run #8
- type: gptr
- provider: anthropic
- model: claude-3-5-haiku-latest
- Result: SUCCESS
- Saved output: temp_gpt_researcher_reports\research_report_e3da8aa9-6f38-4476-8b69-bd00ba0f343f.md
- Saved copy: C:\dev\silky\api_cost_multiplier\test\mdoutputs_untested\commerce

10) Run #9
- type: None / invalid (empty)
- provider: None
- model: None
- Result: FAIL (skipped)
- Notes: Runner encountered an empty/unknown run entry and skipped it: "ERROR: Unknown run type ''. Skipping."

Summary
- Successful runs (reports produced and copied to test/mdoutputs_untested/commerce):
  - openai:o1
  - anthropic:claude-opus-4-1-20250805
  - anthropic:claude-3-7-sonnet-latest
  - anthropic:claude-3-5-haiku-latest

- Failed runs:
  - openai:codex-mini (JSON/programmatic error)
  - openai:o3-pro (JSON/programmatic error)
  - openai:o1-preview (JSON/programmatic error)
  - google_genai:gemini-live-2.5-flash-preview (model-not-found + JSON error)
  - anthropic:claude-opus-4-20250514-thinking (JSON/programmatic error)
  - one invalid run entry (empty) was skipped

Recommendations
- Model-not-found (Google gemini-live preview): verify provider support and API availability (model name and API version). If unavailable, remove from registry or use a supported model name.
- JSON/programmatic errors ("NoneType" when reading/parsing LLM output): these come from the gpt-researcher wrapper expecting JSON/text that wasn't produced (or returned as None). Possible actions:
  - Re-run the failing models individually to capture full subprocess logs.
  - Validate provider credentials and environment variables (some providers returned partial responses).
  - Temporarily limit to "openai" or "anthropic" models that succeeded to confirm pipeline health.
- The empty run entry suggests the test config may have an extra blank item; double-check config.yaml formatting to remove stray entries.

Next actions I can perform (pick one):
- A) Save this summary to docs (already done by this file).
- B) Re-run only the failed runs one-by-one to capture detailed logs (I'll need approval since this may call external APIs).
- C) Restore the original config (api_cost_multiplier/config.yaml.bak) and stop.
- D) Fix the empty run entry (if you want) and re-run the test set.

Which would you like me to do next?
