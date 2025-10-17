# Model Failures Investigation Report
Date: 2025-10-16

Author: Cline

Executive Summary
- Objective: Investigate what failed and why during the latest evaluation run, focusing on provider/model behavior (Google Gemini 2.5 Flash / Flash-Lite, OpenAI GPT‑5 family), strict enforcement policies (grounding + reasoning), and code paths that translate policy into runtime decisions.
- Key Finding: All single-eval failures in the observed batch were from Google Gemini 2.5 Flash‑Lite due to “missing grounding (web_search/citations)” signals under strict enforcement. Other Google variants (2.5 Flash) and OpenAI (gpt‑5‑nano/mini) succeeded. Pairwise batches completed successfully.
- Root Causes (most likely):
  1) Provider intermittency for grounding signals: Despite tools enabling web search, Gemini responses may omit groundingMetadata/citations intermittently.
  2) Prompt determinism: Single‑call, prompt‑only grounding instructions may be insufficiently strong/deterministic for Flash‑Lite, making citations/grounding metadata less reliable under load or certain inputs.
  3) Strict enforcement (by design): The pipeline’s non‑configurable assertions refuse to write any output lacking both grounding and reasoning; this surfaces provider missignals as failures rather than degraded outputs.
- Recommendations:
  - Strengthen Google‑specific prompt preface for single‑call runs: require numeric citations [1][2], minimum number of independent sources (≥3), and explicit “no output if not grounded.”
  - Add targeted retry on “missing grounding” with bounded jitter, observing provider QPS.
  - Prefer gemini‑2.5‑flash over flash‑lite for evaluations where consistent grounding is required (tradeoff: latency/cost).
  - Ensure minimal failure artifacts are captured to accelerate triage (already implemented in google adapter).
  - Consider operational knobs: conservative concurrency and timeouts; for OpenAI set search_context_size only when supported.

Table of Contents
1. Data Sources and Methods
2. What Failed in the Observed Run
3. Enforcement Architecture (Grounding + Reasoning)
4. Provider Adapters and Payload Shaping
5. External Capabilities Research (Google and OpenAI)
6. Root Cause Analysis
7. Recommendations and Remediations
8. Operational Considerations and Cost
9. Risks of Relaxing Enforcement
10. Appendix: Logs, Code References, and Links

1) Data Sources and Methods
- Codebase review (key files):
  - FilePromptForge core:
    - File: FilePromptForge/file_handler.py
      - Builds provider payloads via adapters, posts to provider endpoints, asserts mandatory signals, writes consolidated per‑run logs with normalized usage and cost, computes total_cost_usd via pricing index.
    - File: FilePromptForge/grounding_enforcer.py
      - detect_grounding: heuristics for web_search/citations detection (tools, URLs, Gemini groundingMetadata).
      - detect_reasoning: provider‑aware + generic reasoning extraction signals.
      - assert_grounding_and_reasoning: raises RuntimeError if either is missing.
  - Provider adapters:
    - File: FilePromptForge/providers/google/fpf_google_main.py
      - ALLOWED_MODELS: gemini‑2.5‑pro, 2.5‑flash, 2.5‑flash‑lite, etc.
      - build_payload: enforces tools=[{google_search:{}}], never sets response schema; for json=true use prompt‑only instruction with “return only JSON.”
      - extract_reasoning: uses groundingMetadata and content.parts text as reasoning signal.
      - execute_and_verify: executes request and applies assert_grounding_and_reasoning; writes a minimal failure artifact for debugging.
    - File: FilePromptForge/providers/openai/fpf_openai_main.py
      - ALLOWED_MODELS: gpt‑5 family (gpt‑5, gpt‑5‑mini, gpt‑5‑nano), o4‑mini, o3.
      - build_payload: tools=[{type:"web_search"}], tool_choice="auto"; enforces reasoning={"effort":"high"} for models known to support reasoning; structured outputs toggled if json=true.
      - execute_and_verify: executes Responses API and enforces grounding + reasoning.
- Run output (latest evaluate.py execution):
  - Single‑eval batch: “12 run(s)”, “9 succeeded, 3 failed.”
  - Failures: all reported as “Provider response failed mandatory checks: missing grounding (web_search/citations)” and all correspond to gemini‑2.5‑flash‑lite.
  - Successes: gemini‑2.5‑flash, OpenAI gpt‑5‑nano/mini succeeded multiple times; pairwise batches succeeded across providers.
  - Final printed line: [EVAL COST] total_cost_usd=0.212696 (as required).
- Internal docs:
  - api_cost_multiplier/docs/gemini_pro_grounding_failure_20251012.md (incident analysis of intermittent grounding omission for 2.5 Pro, later success).
- External research (documentation and guides):
  - Gemini API Grounding with Google Search (ai.google.dev)
  - Gemini model catalog (ai.google.dev/models, Vertex AI docs)
  - OpenAI Responses API web_search tool guide (platform.openai.com)
  - OpenAI Responses API migration and reasoning model guidance

2) What Failed in the Observed Run
- Single evaluation (“stdin batch with 12 runs”):
  - 3 failures, 9 successes.
  - All 3 failures were from Google gemini‑2.5‑flash‑lite and share the same enforcement error:
    - “missing grounding (web_search/citations). Enforcement is strict; no report may be written.”
- Other models in same run:
  - gemini‑2.5‑flash: succeeded; consolidated per‑run logs were written.
  - OpenAI gpt‑5‑nano, gpt‑5‑mini: multiple successes recorded; consolidated logs written; no enforcement failures.
- Pairwise evaluation batches:
  - All batches reported completed successfully (3/3 each time).
- Result artifacting:
  - For Google adapter, when enforcement fails, a small failure artifact may be written capturing provider and minimal summary to accelerate triage (confirmed in code).
  - For successful runs, consolidated per‑run JSON logs capture:
    - run_group_id, provider response, normalized usage, total_cost_usd, human_text (if parseable), reasoning snippets, and web_search entries.

3) Enforcement Architecture (Grounding + Reasoning)
- Mandatory policy (non‑configurable):
  - Both grounding and reasoning must be present; otherwise raise and refuse to write output.
  - Enforced at multiple layers:
    - Provider adapter execute_and_verify -> verify_helpers.assert_grounding_and_reasoning
    - file_handler.run -> after HTTP call -> assert_grounding_and_reasoning again (+ last‑chance detect_grounding before file write).
- Grounding detection (grounding_enforcer.detect_grounding):
  - Positive signals:
    - Top‑level tool_calls/tools with content.
    - Presence of URLs/citations in outputs/content (http/https, “Citation:”, “[source]”).
    - Gemini‑specific: candidates[i].groundingMetadata with webSearchQueries, groundingSupports, confidenceScores, searchEntryPoint; or citations/citationMetadata in candidates or content.parts.
- Reasoning detection (grounding_enforcer.detect_reasoning):
  - Provider‑specific extraction hook if available (e.g., google extract_reasoning).
  - Fallback: generic reasoning fields at top level or within output blocks, or text content parts (Gemini often intermixes).
- Outcome of enforcement:
  - Deterministic pass/fail surface: provider omission of any required signal causes a hard failure.
  - This is a safety mechanism to prevent ungrounded outputs from entering reports.

4) Provider Adapters and Payload Shaping
- Google (fpf_google_main.py):
  - tools: [{ "google_search": {} }] enforced in every payload.
  - generationConfig: sets maxOutputTokens, temperature, topP if present.
  - JSON handling: if cfg["json"] is true, uses prompt‑only JSON instruction; never sets responseMimeType or schema for Gemini.
  - Reasoning extraction:
    - Prefers groundingMetadata.webSearchQueries, then groundingSupports/confidenceScores, then fallback to content.parts text.
  - Dynamic endpoint:
    - file_handler computes endpoint from model name: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
- OpenAI (fpf_openai_main.py):
  - tools: [{ "type": "web_search" }], tool_choice="auto"; optionally sets search_context_size (supported by some gpt‑5 variants).
  - reasoning: mandatory; payload["reasoning"]={"effort":"high"} for gpt‑5/o‑series; raises if not supported by model mapping.
  - Structured outputs (json=true): text.format=json_schema with a permissive schema to keep provider compatible with tool usage.
  - Parsing and extraction: parse_response composes output_text; extract_reasoning walks top‑level and output blocks to return text explanation.

5) External Capabilities Research (Google and OpenAI)
- Google Gemini API (Grounding with Google Search)
  - With tools: [{google_search:{}}] enabled, Gemini should produce groundingMetadata with search queries, web results, and citations.
  - In practice, metadata presence is not 100% deterministic per request; intermittent omission has been observed (and is documented in our internal incident report).
  - Reference: https://ai.google.dev/gemini-api/docs/google-search
- Gemini Model Catalog
  - gemini‑2.5‑flash and gemini‑2.5‑flash‑lite both listed as stable variants; flash‑lite is optimized for low latency/cost and may have stricter budgets, potentially impacting consistency of search/citation surfacing.
  - Reference: https://ai.google.dev/gemini-api/docs/models and Vertex AI docs for 2.5 Flash.
- OpenAI Responses API, web_search tool, and reasoning
  - Web search tool is an agentic primitive; models decide whether to search, but the API includes fields and inline citations when search is used.
  - Reasoning models (gpt‑5/o‑series) support “reasoning” object (effort). Token usage is reported in usage fields.
  - References:
    - Web search tool: https://platform.openai.com/docs/guides/tools-web-search
    - Responses API migration/agentic loop: https://platform.openai.com/docs/guides/migrate-to-responses

6) Root Cause Analysis
- Symptom: gemini‑2.5‑flash‑lite single‑eval runs failed due to “missing grounding” while gemini‑2.5‑flash and OpenAI gpt‑5 runs succeeded.
- Contributing factors:
  1) Provider intermittency:
     - Even with google_search tool in the payload, the model may choose not to search or may not emit groundingMetadata/citation fields in the returned shape for certain prompts/contexts.
     - This behavior is likely more frequent under flash‑lite constraints (latency/token/cost budgets).
  2) Prompt determinism:
     - Current prompt preface (when json=false) requires evidence and references, but “must include citations” may still be treated as advisory by the model in some cases.
     - Single‑call policy (no two‑stage ELI5→evidence pipeline) reduces our ability to force retrieval pass + justification pass.
  3) Strict enforcement design:
     - The platform is intentionally strict (no human‑readable output without both grounding and reasoning), which trades off availability for quality/groundedness.
     - This is working as intended, making provider missignals visible rather than silently degrading quality.
- Non‑causes ruled out by evidence:
  - Endpoint drift: dynamic URL rewrite for Google is correct; logs show correct endpoint computation per model.
  - JSON/structured output mismatch: The failing cases happened in non‑json mode; successes show independence from JSON mode for grounding behavior.
  - Request transport failures: HTTP calls completed; enforcement failed at content validation, not HTTP layer.

7) Recommendations and Remediations
A) Prompt Hardening for Google Single‑Call
- Add a short, strong preface inserted only when provider==google and json==false:
  - “You must perform a fresh Google web search and ground every major claim. Use inline numeric citations like [1] [2] mapped to a final ‘Sources’ section listing full URLs. Provide at least 3 independent sources. If you cannot ground a claim, omit it. Do not answer if you cannot include grounded citations.”
- Rationale: Increases the probability that Gemini emits groundingMetadata and explicit citation patterns; raises perceived requirement to include citations in response content.

B) Targeted Retry on “Missing Grounding”
- When assert_grounding_and_reasoning raises “missing grounding”, retry up to R times with constrained jitter (observing QPS=0.2 minimum interval already in place).
- Track retry_reason=missing_grounding in metrics. Abort after R attempts to avoid runaway cost.

C) Prefer gemini‑2.5‑flash over flash‑lite for Evaluations
- For judge models that must consistently supply citations, prefer 2.5 Flash (or Pro), accepting slightly higher cost/latency.
- For throughput/cost‑sensitive runs, Flash‑Lite is still available but expect higher rate of grounding omissions.

D) Failure Artifacts and Diagnostics
- Keep minimal failure artifacts (implemented in Google adapter) on forensics:
  - provider, endpoint, timestamp, whether groundingMetadata present in candidates, any partial cues.
- Consider also logging which grounding_enforcer signals were missing (e.g., no tool_calls, no groundingMetadata, no URL‑like strings).

E) Enforcement Hygiene
- Do not relax the mandatory checks globally.
- Optional refinement: For Gemini, treat presence of groundingSupports with mapped chunks as sufficient even when inline numeric citations are missing, provided majority coverage exists. This maintains rigor while reducing false negatives on stylistic differences.

F) Operational Knobs
- Concurrency and timeout:
  - Maintain conservative qps and reasonable timeouts; some Google runs completed in ~3–30s; OpenAI ran 47–176s in our batch (depending on tool usage).
- OpenAI:
  - Set web_search.search_context_size for gpt‑5 variants that support it (already guarded in adapter).
  - Continue enforcing reasoning={"effort":"high"} to keep explanations in the record.

8) Operational Considerations and Cost
- The batch reported total_cost_usd=0.212696 across runs (single + pairwise). With retries for missing grounding and a shift to gemini‑2.5‑flash, expect:
  - Slightly higher unit cost per run (Flash vs Flash‑Lite).
  - Potentially lower overall re‑runs due to higher pass rates, which can partially offset added per‑call cost.
- Cost transparency:
  - Per‑run consolidated logs include usage normalization and calculated total_cost_usd.
  - Aggregation across grouped runs is printed as a final standardized line: “[EVAL COST] total_cost_usd=…”.

9) Risks of Relaxing Enforcement
- Allowing non‑grounded outputs would reduce quality guarantees and undermine downstream evaluation reliability (and any ELO/score comparisons).
- Accepting “reasoning” as any non‑empty text risks admitting generic prose as justification without actual thought process or evidence signals.

10) Appendix: Logs, Code References, and Links

Observed Run Excerpts (single eval)
- Failures (all gemini‑2.5‑flash‑lite), examples:
  - “…missing grounding (web_search/citations)…”
  - ids ending in: 2e5138fe, 04f45605, 9551d675
- Successes:
  - gemini‑2.5‑flash: multiple runs succeeded; consolidated logs written.
  - openai gpt‑5‑nano / gpt‑5‑mini: multiple runs succeeded; consolidated logs written.
- Pairwise batches: 3/3 succeeded across providers in each batch.

Code References
- Grounding/Reasoning Enforcement:
  - FilePromptForge/grounding_enforcer.py
- Core Runner and Consolidated Logs:
  - FilePromptForge/file_handler.py
    - Normalizes usage from OpenAI/Gemini responses
    - Loads pricing, computes total_cost_usd
    - Writes consolidated JSON per run (with run_group_id)
    - Final guard: refuses output write if detect_grounding returns False
- Provider Adapters:
  - Google: FilePromptForge/providers/google/fpf_google_main.py
  - OpenAI: FilePromptForge/providers/openai/fpf_openai_main.py
- Evaluation Orchestration and Cost Aggregation:
  - llm-doc-eval/llm_doc_eval/api.py (batch grouping, aggregation)
  - evaluate.py (prints final [EVAL COST] total line)

Internal Documentation
- api_cost_multiplier/docs/gemini_pro_grounding_failure_20251012.md
  - Intermittent provider omission for gemini‑2.5‑pro under single‑call policy; later success; enforcement behaved correctly.

External Documentation and References
- Google Gemini:
  - Grounding with Google Search: https://ai.google.dev/gemini-api/docs/google-search
  - Models (incl. 2.5 Flash/Flash‑Lite): https://ai.google.dev/gemini-api/docs/models
  - Vertex AI Gemini 2.5 Flash doc: https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash
  - Firebase AI Logic Grounding overview: https://firebase.google.com/docs/ai-logic/grounding-google-search
- OpenAI:
  - Web search tool (Responses API): https://platform.openai.com/docs/guides/tools-web-search
  - Migrate to Responses API (agentic loop, reasoning): https://platform.openai.com/docs/guides/migrate-to-responses

Proposed Next Steps (Actionable)
1) Implement Google‑specific prompt hardening in provider adapter or compose_input layer for json=false:
   - Require at least 3 independent sources; enforce [1][2] inline citations + Sources section; “no output if not grounded.”
2) Add retry path specifically for “missing grounding” exceptions with capped attempts and jitter; maintain qps.
3) Provide a configuration toggle to prefer gemini‑2.5‑flash for evaluation judges by default.
4) Enhance failure artifacts with a small “signals summary” (which detectors failed).
5) Keep strict enforcement; evaluate optional acceptance of groundingSupports‑heavy responses even if inline numeric citations are not present (when webSearchQueries/groundingSupports exist and map to majority of claims).

Conclusion
The enforcement pipeline is functioning as designed: it prevents ungrounded or non‑reasoned outputs from propagating. The observed failures are concentrated in gemini‑2.5‑flash‑lite and are best addressed via stronger single‑call prompt instructions, optional retries, and model preference adjustments. OpenAI gpt‑5 variants and gemini‑2.5‑flash performed as expected in this batch. With prompt and operational improvements, we should reduce the incidence of “missing grounding” failures without compromising evidence standards or reproducibility.
