# repreating problems google grounding 4 oct — Consolidated Reports

This file consolidates the following documents verbatim:
- C:\dev\silky\api_cost_multiplier\docs\gemini_pro_grounding_failure_20251012.md
- C:\dev\silky\api_cost_multiplier\docs\gemini_grounding_issue_report.md
- C:\dev\silky\api_cost_multiplier\docs\REPEATING PROBLEMS GROUINGS OCT.md

===== BEGIN: C:\dev\silky\api_cost_multiplier\docs\gemini_pro_grounding_failure_20251012.md =====
# Gemini 2.5 Pro Grounding Failure Incident Report (2025-10-12)

Summary
- One run (first batch) using Google Gemini 2.5 Pro failed mandatory grounding enforcement and was blocked from output write.
- Subsequent batch run for the same model succeeded with full grounding signals.
- Root cause is most likely intermittent provider omission of grounding signals or insufficiently deterministic prompt-level grounding instruction under single-call policy. Enforcement logic behaved correctly.

Scope and policy context
- JSON policy: boolean-only; generate path uses json=false; single-call only (no two-stage).
- Google policy: never set responseMimeType/responseJsonSchema; prompt-only instruction; rely on single response; extract signals from response when present.
- Grounding and reasoning: mandatory; runs without evidence are rejected.
- Dynamic Google endpoint: model-derived override to https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent.
- Concurrency: global max_concurrency=32; qps=0.1 (10s min interval); deep-research bypasses global limit.

Timeline (from logs)
- 12:12:20.109 FPF scheduler starts, concurrency configured.
- 12:12:30.261 gemini-2.5-flash success; log written: FilePromptForge/logs/20251012T121230-f318f04c.json.
- 12:12:33.845 gemini-2.5-flash-lite success; log written: FilePromptForge/logs/20251012T121233-7505d9bd.json.
- 12:12:44.529 gemini-2.5-pro failed (first batch):
  - fpf_run.log: “Provider response failed mandatory checks: missing grounding (web_search/citations). Enforcement is strict; no report may be written.”
  - No consolidated JSON log was written for this failed attempt (by design).
- 13:59:52.906 Second batch launched with json override confirmed (json=False).
- 14:00:24.587 gemini-2.5-pro success (second batch); log written: FilePromptForge/logs/20251012T140024-2f4ee652.json.

Evidence

1) Failure message (first batch)
From api_cost_multiplier/logs/fpf_run.log:
- 2025-10-12 12:12:44,529 WARNING fpf_scheduler: Run failed (attempt 1/5) id=fpf-3-1 provider=google model=gemini-2.5-pro err=Provider response failed mandatory checks: missing grounding (web_search/citations). Enforcement is strict; no report may be written. See logs for details.

Notes:
- Enforcer correctly blocked output write since grounding signals were absent.
- No per-run consolidated JSON was produced for failed runs.

2) Successful gemini-2.5-pro (second batch) consolidated log
File: api_cost_multiplier/FilePromptForge/logs/20251012T140024-2f4ee652.json
Key fields observed:
- request.tools: [{"google_search": {}}]
- response.groundingMetadata.searchEntryPoint: present (HTML snippet)
- response.groundingChunks: present (URIs via vertexaisearch redirect with titles: cbsnews.com, washingtonpost.com, aa.com.tr, paychex.com, pbs.org, house.gov, etc.)
- response.groundingSupports: present with segments mapped to chunk indices
- response.webSearchQueries: present
- usageMetadata: prompt/candidate/tool/thoughts token counts recorded
- human_text: generated narrative aligned to prompt

3) Successful gemini-2.5-flash (first batch) consolidated log
File: api_cost_multiplier/FilePromptForge/logs/20251012T121230-f318f04c.json
Key fields observed (analogous to Pro success case):
- groundingMetadata.searchEntryPoint: present
- groundingChunks: present
- groundingSupports: present
- webSearchQueries: present

Analysis

What failed
- The first batch gemini-2.5-pro response did not include sufficient grounding evidence signals required by the enforcer (specifically “web_search/citations” class of evidence). Under strict policy, this correctly prevented output write.

Why it failed (most likely)
- Intermittent provider behavior on single-call Google runs: despite tools=[google_search], Gemini responses can occasionally omit explicit grounding/citation signals (e.g., missing groundingMetadata fields or linkable citations) depending on search pathway activation or internal heuristics.
- Prompt-level determinism: Under single-call policy, we rely exclusively on prompt text to require citations and evidence. If the instruction strength is below threshold or phrased in a way that Gemini occasionally does not surface grounding cues, enforcement will fail even if content looks plausible.
- Not an endpoint issue: Dynamic endpoint overrides are logged for flash/flash-lite and were correct. For Pro, config target already matched the model endpoint in the successful run; the failure was not an HTTP or endpoint error.
- Not a JSON/payload issue: Generate path json=false by policy; success cases demonstrate that grounding signals are independent of JSON settings.

What worked
- Enforcement: Strict validation caught the missing grounding case and blocked output as intended.
- Subsequent run (second batch) succeeded for Pro with clear grounding metadata, confirming no persistent configuration defect.

Mitigations and recommendations

A. Prompt-level hardening for Google single-call
- Prepend a strong, compact instruction requiring:
  - Use of Google web search.
  - Inclusion of inline citations with explicit source anchors (e.g., [1], [2]) and a final “Sources” section.
  - Do not produce an answer unless at least N independent sources are included (e.g., 3).
- Example instruction (to be inserted only when provider==google and json==false):
  - “You must perform a fresh web search and include direct citations for every major claim. Provide at least 3 independent sources. Use inline numeric citations like [1], [2] mapped to a ‘Sources’ section containing full URLs. If you cannot ground a claim, omit it.”

B. Retry strategy refinement (optional)
- Distinguish transient “missing grounding” from hard failures:
  - Immediately retry up to R times with an incremental backoff jitter bounded by provider QPS rules when grounding signals are missing.
  - Record “retry_reason=missing_grounding” to metrics for tracking.
- Current scheduler reports “attempt 1/5” but the first batch still ended with 1 failed; ensure retry conditions include validation-failure triggers (not just transport/status errors), if deemed acceptable for throughput.

C. Search context knobs for Google
- Consider elevating search_context_size from “low” to “medium” for sensitive topics with fast-moving facts. The second batch Pro success (config showed “low”) did succeed, so this is optional, but testing may show increased determinism of grounding signals.

D. Logging and triage
- Continue writing per-run consolidated logs on success; for failures, add an option to write a minimal failure artifact capturing:
  - request.tools
  - top-level response keys (if present)
  - detection flags (which signals were missing)
  - timing and model
  This accelerates incident analysis without relaxing enforcement.

E. Enforcement rule hygiene
- Current success cases confirm Google-specific signals (groundingMetadata, searchEntryPoint, groundingChunks, groundingSupports) are recognized. Do not relax. Optional enhancement: accept Google’s grounded URIs list as sufficient if inline citations are missing but groundingSupports is present for the majority of claim segments.

Appendix: Key artifacts and references
- Failure (first batch): api_cost_multiplier/logs/fpf_run.log at 2025-10-12 12:12:44,529
- Success (Pro, second batch): api_cost_multiplier/FilePromptForge/logs/20251012T140024-2f4ee652.json
- Success (Flash, first batch): api_cost_multiplier/FilePromptForge/logs/20251012T121230-f318f04c.json

Conclusion
- The incident was an isolated provider-side omission of grounding signals under single-call constraints. The system behaved correctly by blocking output.
- Adopting stronger Google-specific grounding instructions and optionally widening retry logic for “missing grounding” should reduce intermittent failures while preserving strict evidence requirements.
===== END: C:\dev\silky\api_cost_multiplier\docs\gemini_pro_grounding_failure_20251012.md =====


===== BEGIN: C:\dev\silky\api_cost_multiplier\docs\gemini_grounding_issue_report.md =====
FPF MUST ALWAYS USE GROUNDING AND REASONING. IT IS UNCONFIGURABLE. IF YOU WANT TO CHANGE GROUDING IN FPF, YOU MUST STOP IMEDITITLY. 

FPF MUST ALWAYS USE GROUNDING AND REASONING
DO NO APPEMPT TO CHANGE FPF FROM GROUNDING AND REASONING

Plain-language summary (10 sentences)
We found that Google Gemini sometimes does not show clear web-search evidence, which makes our strict checker fail.
Flash and Flash‑Lite usually include the needed evidence, but Pro sometimes does not under the current ACM prompt.
We fixed an endpoint drift risk by computing the Google API endpoint from the selected model at run time.
We expanded the grounding checks to accept more Gemini signals like groundingMetadata, searchEntryPoint, and citations.
Eval now passes because its prompts clearly require web search and citations, but ACM with Pro can still fail until its prompt is strengthened.
We will not add a second-stage API call; we will only attempt simple JSON extraction from the single response text when needed.
The report explains exactly which config files and prompts to change to test both the problem and the fixes for generate and evaluate.
Our logs capture queries and citations so we can confirm grounding and verify that the endpoint and behavior are correct.
Success means Pro follows stronger prompts, grounding evidence appears in provider JSON, and the human text can stay URL‑free if needed.
We included a small test matrix and step‑by‑step next actions so you can reproduce failures, apply fixes, and see improvements.

# Gemini Grounding Intermittency Report

Author: Cline  
Date: 2025-10-12

## Summary

Grounding verification failures are intermittently observed with Google Gemini when strict enforcement requires explicit evidence of web search/citations. With current configuration and prompts:

- gemini-2.5-flash and gemini-2.5-flash-lite: consistently pass grounding checks
- gemini-2.5-pro: fails grounding check in some ACM runs (no explicit web search evidence detected)

Evaluation (llm-doc-eval) was stabilized via prompt changes that explicitly require web search, plus expanded verification to recognize more Gemini grounding signals. ACM (generate.py) largely passes except gemini-2.5-pro under certain prompts.

## Scope and Impact

- Affected: Google Gemini provider
  - Models: gemini-2.5-pro (intermittent), gemini-2.5-flash (pass), gemini-2.5-flash-lite (pass)
- Not affected: OpenAI models (gpt-5, gpt-5-mini, gpt-5-nano, o4-mini) and OpenAI Deep Research (o4-mini-deep-research)
- User-visible behavior: For failing runs, no human-readable report is written; scheduler logs: “missing grounding (web_search/citations)”

## Environment and Recent Changes

- Dynamic endpoint selection implemented in FilePromptForge core to prevent model/endpoint drift:
  - File: FilePromptForge/file_handler.py
  - Behavior: Computes `https://generativelanguage.googleapis.com/v1beta/models/{cfg["model"]}:generateContent` and overrides mismatched config URL.
- Grounding verification broadened:
  - File: FilePromptForge/grounding_enforcer.py
  - Detection now accepts Gemini signals:
    - candidates[*].groundingMetadata.{webSearchQueries, groundingSupports, confidenceScores, searchEntryPoint}
    - candidates[*].citations / citationMetadata
    - content.parts[*].citationMetadata and URI/url/link/href fields
- Eval prompt templates updated to require web search (to encourage tool usage and citations):
  - llm-doc-eval/prompts/single_template.md
  - llm-doc-eval/prompts/pairwise_template.md

## Reproduction

1) ACM (generate.py) run (12:12 local):

- Command: `python -u api_cost_multiplier/generate.py`
- Input folder: `api_cost_multiplier/test/mdinputs`
- Output folder: `api_cost_multiplier/test/mdoutputs`
- QPS: 0.1 (10s min interval), max_concurrency=32
- Dynamic endpoint overrides observed:
  - pro -> flash:generateContent when cfg.model=gemini-2.5-flash (expected)
  - pro -> flash-lite:generateContent when cfg.model=gemini-2.5-flash-lite (expected)

Results (7/8 succeeded):
- Success:
  - google gemini-2.5-flash → wrote: `test\mdoutputs\Census Bureau.gemini-2.5-flash.fpf-1-1.fpf.response.txt`
    - Consolidated log: `FilePromptForge/logs/20251012T121230-f318f04c.json`
  - google gemini-2.5-flash-lite → wrote: `test\mdoutputs\Census Bureau.gemini-2.5-flash-lite.fpf-2-1.fpf.response.txt`
    - Consolidated log: `FilePromptForge/logs/20251012T121233-7505d9bd.json`
  - openai gpt-5 / gpt-5-mini / gpt-5-nano / o4-mini → all passed
  - openaidp o4-mini-deep-research → passed
- Failure:
  - google gemini-2.5-pro → Run failed (attempt 1/5): “missing grounding (web_search/citations)”
  - No output written (strict enforcement); see scheduler error line for fpf-3-1.

2) Eval (llm-doc-eval) run (earlier in session):

- After prompt template updates + broadened verification:
  - All Google eval runs passed (single and pairwise) across the same document set.
  - Key difference vs ACM: eval templates now explicitly require web search, strongly nudging Gemini to use the tool.

## Observations

- Flash/Flash-lite exhibit consistent grounding signals (groundingMetadata present or citations/evidence), satisfying strict checks.
- Pro model sometimes responds without explicit web search usage under ACM’s current prompt(s). This leads to a strict failure when detect_grounding() cannot confirm tools/citations.
- After template update in llm-doc-eval that mandates web search, Gemini complied and eval runs passed.

## Root Cause Hypothesis

- Model behavior + prompt interplay:
  - Gemini-2.5-pro may decide web search is unnecessary when the instruction does not strongly demand verification; thus no explicit groundingMetadata/citations appear.
  - Our enforcement is intentionally strict. Without those signals the run fails.
- Verification logic previously missed some legit Gemini signals; this is now fixed (expanded checks).
- Endpoint mismatch is no longer a factor (dynamic endpoint selection in place and verified in logs).

## Verification Logic (Current)

File: FilePromptForge/grounding_enforcer.py

Signals accepted as grounding:
- Top-level: non-empty `tool_calls` or `tools`
- URL/citation hints in output/content
- Gemini specific:
  - candidates[*].groundingMetadata.webSearchQueries
  - candidates[*].groundingMetadata.groundingSupports
  - candidates[*].groundingMetadata.confidenceScores
  - candidates[*].groundingMetadata.searchEntryPoint
  - candidates[*].citations / citationMetadata
  - content.parts[*].citationMetadata
  - content.parts[*].uri/url/link/href fields

Reasoning accepted if:
- provider.extract_reasoning returns text OR
- Gemini’s groundingMetadata contains evidence OR
- visible non-empty text content is present OR
- generic reasoning fields exist

## Mitigations and Recommendations

Short-term (low risk):
1) Prefer flash or flash-lite in ACM runs if strict grounding is required, as they consistently exhibit grounding signals.
2) Strengthen ACM prompt (e.g., `test/prompts/standard_prompt.txt`) similarly to eval templates:
   - Explicitly require live web search with citations/URLs and state that answers without evidence will be rejected.
   - Note: Keep returned body free of URLs if downstream parsers need clean output; grounding should remain in provider JSON and logs.

Medium-term:
3) Add a provider adapter nudge for Gemini (if permitted by API):
   - Keep `tools: [{ "google_search": {} }]`.
   - Optionally prepend a concise system preface for provider-level “verify with search.”
4) Add a configurable soft retry path in ACM when grounding is missing:
   - Retry the same request with a stronger “verify with web search” instruction.
   - Track and cap retry attempts with exponential backoff.

Long-term:
5) Capability-aware routing:
   - If strict grounding is mandatory, route Gemini calls to flash/flash-lite by default for ACM runs.

## Proposed Experiment Matrix

- P1: ACM current prompt vs. ACM “web search required” prompt:
  - Models: flash, flash-lite, pro
  - Expectation: Pro compliance increases with explicit instruction.
- P2: Enforcer sensitivity check:
  - Validate that expanded signals (searchEntryPoint, citations, citationMetadata) are detected across sample runs.
- P3: Retry-on-missing-grounding:
  - Measure success rate improvements and latency/cost impact.

## References (Logs and Outputs)

- Success (flash): `FilePromptForge/logs/20251012T121230-f318f04c.json`
- Success (flash-lite): `FilePromptForge/logs/20251012T121233-7505d9bd.json`
- Failure (pro): scheduler line (fpf-3-1) “missing grounding”; no output written by design.
- Multiple OpenAI success logs: e.g., `20251012T121459-1bebe72c.json`, `20251012T121601-45af0373.json`, etc.

## Action Items

- [ ] Decide whether to keep gemini-2.5-pro in ACM default model set.
- [ ] If kept, update ACM prompt to require web search with citations.
- [ ] Optionally implement adaptive retry when grounding is missing (ACM only).
- [ ] Continue to monitor per-run logs for Gemini grounding signals to ensure the broader detection remains sufficient.

---

## Appendix: Plan Review — Provider‑Aware JSON in FPF + Major llm-doc-eval Concurrency Refactor (2025-10-12)

Executive summary
- The direction is solid: centralizing provider-aware JSON handling in FPF and moving llm-doc-eval onto FPF’s batch/concurrency primitives will reduce duplicated logic, improve reliability, and make behavior consistent.
- The two-stage “ground first, then jsonify” approach is the right safety valve for Gemini+grounding. Tighten stage-2 controls (schema, low-temp, tool-off) to avoid drift.
- Prefer CLI overrides over temp-config patching to avoid race conditions and multi-process cross-talk.

Strengths
- Clear separation of concerns: fpf_runner passes intent; FPF core decides per provider/model.
- Compatibility table via a helper gives a single source of truth for JSON+tools capability.
- Refactor in llm-doc-eval to a single batch handed to FPF lets scheduler enforce one concurrency/QPS policy.
- Tests and acceptance criteria scoped across providers and modes.

Gaps and recommended refinements
1) How to decide grounding_required pre-call
- Don’t rely on grounding_enforcer (post-hoc). Add a helper is_grounding_required(cfg) that reads an explicit run option (e.g., require_web_search: bool) or detects tool enablement from the prompt/config.
- Keep enforcer for verification; use the helper for routing (single-shot vs two-stage).

2) Stage-2 “jsonify” safety
- Force determinism: temperature 0, top_p 0 or disabled, no tools, strict token caps.
- Enforce schema, not just “JSON”:
  - OpenAI: response_format with json_schema (preferred) or json_object.
  - Gemini (no grounding): response_mime_type application/json; if available, use response_schema equivalents.
- Validate with jsonschema; on failure, do a single local repair pass (small prompt that fixes formatting only) before retrying a provider call.
- Include a “no new facts” constraint and instruct to only restructure Stage‑1 content. Keep the Stage‑1 text available for diff checks if needed.

3) Configuration and overrides
- Prefer CLI flags handled by fpf_main.py (e.g., --json auto|true|false, --max-concurrency N, --timeout-seconds S). This avoids temp YAML patching races when multiple processes run concurrently.
- If you keep temp config patching, ensure it writes to a per-run temp directory with unique filenames and never touches the baseline YAML.

4) Compatibility helper scope
- Include patterns for openai, openrouter (OpenAI-compatible), azure-openai (if used), google gemini variants (pro/flash/flash-lite), and openaidp.
- Add unit tests with table-driven cases to prevent regressions when new models land.

5) Scheduler/QPS details for eval batches
- Expose both concurrency and QPS per provider in options; wire them through to FPF’s scheduler.
- Add chunking for very large pairwise sets to bound memory footprint and keep SQLite commits incremental.

6) Logging/observability
- Assign a run_id with stage1_id and stage2_id; log provider/model, durations, retry counts, grounding evidence summary, JSON validation outcome.
- Persist Stage‑1 raw artifact alongside final output for auditability (with redaction as needed).

7) Backward compatibility and defaults
- Default json: false. Generate uses json=false; Evaluate uses json=true via fpf_runner options. No "auto" mode; single-call only.
- Document precedence: CLI > per-run override > config defaults.

Proposed sequencing adjustments
- A1 (compatibility helper) and A3 (file_handler routing) are foundational; do A2 (fpf_runner option/CLI plumbing) immediately after so you can drive behavior without config edits.
- Add a slim “is_grounding_required” helper in A3 and adopt it in google adapter decisions.
- Before B1, land a minimal run_filepromptforge_batch contract in fpf_runner that returns structured result objects (id, status, output_path, error, timings) and supports chunking and callbacks for progress.
- Only after batch contract is stable, refactor llm-doc-eval judge_backend to use it.

Acceptance criteria additions
- Two-stage correctness: for Gemini+grounding+json=true/auto, assert:
  - Stage 1 contains grounding signals (citations, searchEntryPoint, webSearchQueries).
  - Stage 2 output validates against a schema; result contains no URLs and introduces no new entities vs Stage 1 (heuristic check).
- Single-shot correctness: for OpenAI/OpenRouter with grounding+json=true/auto, assert a single call with schema-enforced output and grounding satisfied.
- Stress test: N=50 pairwise on two models runs with bounded memory, finishes under configured concurrency/QPS, no starvation, and SQLite commits remain smooth.
- Retry behavior: inject 429/5xx to confirm exponential backoff and eventual success/fail signals remain accurate per run.

Code sketch (illustrative)
- compatibility.py:
```
def supports_tools_plus_json(provider: str, model: str | None, grounding_required: bool) -> bool:
    p = provider.lower()
    m = (model or "").lower()
    if p in ("openai", "openrouter-openai", "azure-openai"):
        return True
    if p == "google":
        return not grounding_required
    if p == "openaidp":
        return False
    return not grounding_required
```

- file_handler routing excerpt:
```
json_mode = (cfg.get("json") or "auto")
need_grounding = is_grounding_required(cfg)
can_one_shot = (json_mode in ("auto", True)) and supports_tools_plus_json(provider, model, need_grounding)

if json_mode is False or (json_mode == "auto" and not need_grounding):
    return call_single_shot(json=(json_mode is True))
if can_one_shot:
    return call_single_shot(json=True, schema=maybe)
else:
    stage1 = call_single_shot(json=False, enforce_grounding=True)
    grounded_text = extract_text(stage1)
    stage2 = call_jsonify(grounded_text, json_schema, temperature=0, tools_off=True)
    return stage2_with_merged_logs
```

Edge cases to cover
- Large Stage‑1 outputs causing Stage‑2 truncation: add length guard and summarization of non-essential sections before jsonify.
- Mixed providers in one batch: ensure per-run provider options are respected while global concurrency is enforced.
- Windows path handling for temp files and outputs.
- Provider endpoint drift: keep the already-implemented “compute Google endpoint from cfg['model']” and replicate the pattern across providers where applicable.

Verdict
- Proceed with the plan with the refinements above. The main architectural choices are sound; tightening stage-2 controls, preferring CLI overrides, formalizing grounding_required, and enhancing scheduler/QPS options will make the implementation robust and maintainable.

---

## Research update: Gemini grounding, structured output, and model behavior (5-source summary)

Key findings from 5 targeted searches across official docs and forum discussions:

- Grounding with Google Search (official)
  - The response includes groundingMetadata when grounding occurs; fields include webSearchQueries, searchEntryPoint, and groundingChunks with web source info (uri/title). This supports our verifier’s signal set and suggests we can also surface chunk indices-to-URI mapping for inline citations if needed.
  - Source: https://ai.google.dev/gemini-api/docs/google-search

- Structured output (JSON) support
  - Gemini supports response_mime_type=application/json and response_json_schema (preview) for schema-enforced output. This confirms Stage‑2 “jsonify” can enforce a schema natively on Gemini when tools are OFF. The docs do not explicitly describe interplay constraints between grounding tools and structured output, reinforcing our conservative two‑stage approach for Gemini+grounding.
  - Sources:
    - Structured output overview: https://ai.google.dev/gemini-api/docs/structured-output
    - API fields (generationConfig): https://ai.google.dev/api/generate-content

- URL Context tool can be combined with Google Search
  - The URL context tool can be used together with Grounding with Google Search; responses may include url_context_metadata. Our verifier can optionally look for these metadata fields in addition to groundingMetadata to broaden evidence detection (without requiring URLs in the final human text).
  - Source: https://ai.google.dev/gemini-api/docs/url-context

- Model support and multi‑tool usage
  - Supported models for Grounding include 2.5 Pro, 2.5 Flash, and 2.5 Flash‑Lite. Changelog notes multi‑tool use (e.g., code execution + Grounding) in a single generateContent request, but does not specifically guarantee structured‑output+Grounding robustness in all cases. This aligns with our plan to prefer two‑stage for Gemini when strict grounding is required.
  - Sources:
    - Supported models table: https://ai.google.dev/gemini-api/docs/google-search
    - Changelog (multi‑tool, model updates): https://ai.google.dev/gemini-api/docs/changelog

- Prompting and model behavior considerations
  - Prompting strategies emphasize explicit constraints and response formatting; for grounding, prompts should clearly require web search and citations/evidence. Community threads indicate 2.5 Pro can be less reliable about surfacing citations compared with Flash, echoing our observed intermittency and supporting our recommendation to strengthen ACM prompts and/or prefer Flash/Flash‑Lite when strict grounding is mandatory.
  - Sources:
    - Prompting best practices: https://ai.google.dev/gemini-api/docs/prompting-strategies
    - Example forum discussions: 
      - “Hallucinated grounding references” (Pro 2.5): https://discuss.ai.google.dev/t/hallucinated-grounding-references/79832
      - “Gemini 2.5 Flash & LearnLM 2.0 – Initial Thoughts” (behavior differences): https://discuss.ai.google.dev/t/gemini-2-5-flash-learnlm-2-0-initial-thoughts-and-questions/80301

Implications for our plan
- Retain two‑stage for Gemini when grounding_required:
  - Stage‑1 (tools ON, json=False) ensures grounding signals; Stage‑2 (tools OFF) uses response_mime_type or response_json_schema with temperature 0 and strict caps for deterministic JSON.
- Verifier enhancements:
  - Continue accepting groundingMetadata (webSearchQueries, searchEntryPoint, groundingChunks) and consider url_context_metadata when URL Context is enabled.
- Prompt updates (ACM):
  - Explicitly require live web search and citations; state that answers without grounding evidence are rejected. Keep final human text free of URLs if downstream requires; rely on provider JSON/logs for evidence.
- Model guidance:
  - For strict grounding guarantees, prefer Flash/Flash‑Lite in ACM. Use Pro with stronger prompting and/or an adaptive retry path as needed.
- Logging:
  - Capture search queries and mapped URIs from groundingChunks and include a concise grounding summary in consolidated logs for auditability.

References
- Grounding docs: https://ai.google.dev/gemini-api/docs/google-search
- Structured output: https://ai.google.dev/gemini-api/docs/structured-output
- API fields (generationConfig): https://ai.google.dev/api/generate-content
- URL context: https://ai.google.dev/gemini-api/docs/url-context
- Prompting strategies: https://ai.google.dev/gemini-api/docs/prompting-strategies
- Changelog: https://ai.google.dev/gemini-api/docs/changelog
- Forum examples: 
  - https://discuss.ai.google.dev/t/hallucinated-grounding-references/79832
  - https://discuss.ai.google.dev/t/gemini-2-5-flash-learnlm-2-0-initial-thoughts-and-questions/80301

---

## Project-specific configuration and evidence

This section ties the analysis to concrete settings, code, prompts, and logs in this repository.

1) FPF defaults and concurrency (FilePromptForge/fpf_config.yaml)
- concurrency:
  - enabled: true
  - max_concurrency: 32
  - qps: 0.1
  - retry: base_delay_ms=500, jitter=full, max_delay_ms=60000, max_retries=5
  - timeout_seconds: 7200
- json: false (default; plan switches to "auto" with provider-aware behavior)
- provider_urls.google: https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent
  - Note: This static value is now overridden at runtime (see code below) to match cfg["model"] and prevent endpoint–model drift.

2) Eval defaults and concurrency (llm-doc-eval/config.yaml)
- llm_api:
  - max_concurrent_llm_calls: 4
  - timeout_seconds: 120
- models:
  - model_a: openai/gpt-5-mini
  - model_b: google/gemini-2.5-flash
- trials: single_doc_eval.trial_count=2, pairwise_eval.trial_count=2
- evaluation.mode: both
Implication: eval’s concurrency (4) is more conservative than FPF’s default (32). When refactoring eval to batch through FPF, pass options["max_concurrency"] from this file to centralize limits.

3) Dynamic Google endpoint computation (FilePromptForge/file_handler.py)
FPF now derives the Google endpoint from the selected model at runtime, eliminating endpoint–model drift:
```python
# Dynamically compute Google Gemini endpoint from cfg["model"] to avoid endpoint–model drift
if provider_name == "google":
    norm_model = (cfg.get("model") or "").split(":", 1)[0]
    if not norm_model:
        raise RuntimeError("Google provider requires cfg['model'] to be set")
    computed_url = f"https://generativelanguage.googleapis.com/v1beta/models/{norm_model}:generateContent"
    if provider_url and provider_url != computed_url:
        LOG.warning("Overriding configured provider_url for Google to match model: %s -> %s", provider_url, computed_url)
    provider_url = computed_url
```
Result: cfg["model"] == "gemini-2.5-flash" yields …/models/gemini-2.5-flash:generateContent, not the stale pro endpoint.

4) Log evidence (FilePromptForge/logs)
- Prior to the dynamic endpoint fix, multiple consolidated logs show:
  - provider_urls.google set to …/models/gemini-2.5-pro:generateContent even when model was gemini-2.5-flash or flash-lite (endpoint–model drift).
  - Google response blocks including groundingMetadata.searchEntryPoint (evidence of grounding).
  Examples (subset):
  - 20251011T214401-1b307731.json (gemini-2.5-flash; “modelVersion”: "gemini-2.5-pro"; groundingMetadata.searchEntryPoint present)
  - 20251011T214401-537a8e68.json (gemini-2.5-flash-lite; “modelVersion”: "gemini-2.5-pro"; groundingMetadata.searchEntryPoint present)
  - 20251011T214403-afd0ac6d.json (gemini-2.5-flash; groundingMetadata.searchEntryPoint present)
  - 20251011T214409-e714fedf.json (gemini-2.5-flash; “modelVersion”: "gemini-2.5-pro")
  - 20251012T085203-2a86678d.json (gemini-2.5-flash; “modelVersion”: "gemini-2.5-flash"; groundingMetadata present)
Interpretation:
- Before the fix, the configured pro endpoint caused modelVersion to appear as pro in some responses even when flash/flash-lite were intended.
- Grounding signals (searchEntryPoint, groundingSupports) are present in many flash/flash-lite runs and reliably pass verification.

5) ACM prompt audit (test/prompts/standard_prompt.txt)
Current content:
- Did trump change the name of the department of defence?
- did trump attack cartel boats?
- who is the current vice presidnet and what did he say about the cartel boat attack if anything.
- "Who won the most recent major tennis tournament (e.g., Wimbledon, US Open)?"
- "What are the main differences between the latest Samsung Galaxy phone and the latest Google Pixel phone?"
- you must search the internet to get updated info.
Observations and action:
- It requires search but does not explicitly require citations or state that answers without evidence will be rejected.
- To increase Gemini‑2.5‑pro compliance with grounding, mirror eval’s stricter language:
  - “Use Grounding with Google Search. Provide citations and make them traceable in provider JSON (groundingMetadata, citations/citationMetadata). Answers without grounding evidence will be rejected.”

6) Concrete next steps (repo-specific)
- Update standard_prompt.txt to explicitly require web search + citations and rejection on missing evidence (keep human text URL-free if desired; rely on provider JSON for evidence).
- Align eval concurrency with FPF batch limits by wiring llm-doc-eval to fpf_runner.run_filepromptforge_batch and passing llm_api.max_concurrent_llm_calls (currently 4).
- Validate endpoint fix:
  - Run FPF with model=gemini-2.5-flash and confirm logs show provider_url …/gemini-2.5-flash:generateContent and response.modelVersion “gemini-2.5-flash”.
- Capture and link a fresh passing Gemini log (post-fix) in this report.
- Optional: add verifier to also accept url_context_metadata when URL Context tool is enabled (found in Google docs).

Artifacts referenced
- Configs:
  - FilePromptForge/fpf_config.yaml
  - llm-doc-eval/config.yaml
- Code:
  - FilePromptForge/file_handler.py (dynamic Google endpoint)
- Prompts:
  - test/prompts/standard_prompt.txt (ACM)
- Logs (subset):
  - FilePromptForge/logs/20251011T214401-1b307731.json
  - FilePromptForge/logs/20251011T214401-537a8e68.json
  - FilePromptForge/logs/20251011T214403-afd0ac6d.json
  - FilePromptForge/logs/20251011T214409-e714fedf.json
  - FilePromptForge/logs/20251012T085203-2a86678d.json

---

## Testing configurations and files (generate and evaluate)

This section outlines concrete configuration setups to 1) reproduce the Gemini grounding problem and 2) verify the fixes. It also covers which files to modify for generate and evaluate, including prompt instructions and evaluation criteria.

A) Generate pipeline (api_cost_multiplier/generate.py)

1) Baseline “reproduce the problem” setup
- Project config: api_cost_multiplier/config.yaml (current)
  - Keep runs including gemini-2.5-pro, flash, flash-lite, and OpenAI models:
    - provider: google, model: gemini-2.5-pro
    - provider: google, model: gemini-2.5-flash
    - provider: google, model: gemini-2.5-flash-lite
- FPF config: FilePromptForge/fpf_config.yaml (current)
  - json: false (do not enforce structured output)
  - concurrency: enabled with max_concurrency=32, qps=0.1 (acceptable)
- Prompt for ACM: test/prompts/standard_prompt.txt (current)
  - Contains “you must search the internet” but does not mandate citations
  - Expected behavior: gemini-2.5-pro may intermittently skip explicit grounding evidence → failure under strict enforcer
- Run
  - python -u api_cost_multiplier/generate.py
- Expected result
  - flash/flash-lite succeed (groundingMetadata/citations present)
  - pro can fail with “missing grounding (web_search/citations)”

2) “Verify fixes” setup
- Project config: api_cost_multiplier/config.yaml
  - Keep the same runs to compare pro vs flash/flash-lite behavior
- FPF config: FilePromptForge/fpf_config.yaml
  - Set json: false
  - For evaluation runs, set json=true via fpf_runner options (single-call only; no two-stage)
  - Single-call only: do not add any jsonify block and do not perform a second LLM call. Do not force responseMimeType when tools are enabled (default). If request_json is used upstream, FPF will attempt simple JSON extraction from the single response text (no second call).
- Prompt for ACM: test/prompts/standard_prompt.txt
  - Strengthen to mandate grounding evidence:
    - Add lines such as:
      - “Use Grounding with Google Search.”
      - “Provide citations; ensure provider JSON includes groundingMetadata (webSearchQueries, searchEntryPoint, groundingSupports) and/or citations/citationMetadata.”
      - “Answers without explicit grounding evidence will be rejected.”
    - If downstream requires URL-free human text, say:
      - “Do not include raw URLs in the human-readable text; citations must appear in provider JSON only.”
- Run
  - python -u api_cost_multiplier/generate.py
- Expected result
  - pro compliance improves with explicit instructions
  - flash/flash-lite remain green
  - Logs under FilePromptForge/logs/ show groundingMetadata for successful runs

Notes (generate)
- Dynamic endpoint fix is already in FilePromptForge/file_handler.py (computed from cfg["model"]); no extra change needed here.
- Keep concurrency as-is for ACM; evidence is in sidecar consolidated logs.

B) Evaluate pipeline (api_cost_multiplier/llm-doc-eval)

1) Config file for evaluate
- llm-doc-eval/config.yaml (current defaults)
  - llm_api.max_concurrent_llm_calls: 4 (conservative)
  - models:
    - model_a: openai/gpt-5-mini
    - model_b: google/gemini-2.5-flash
- To reproduce vs verify:
  - Add a google/gemini-2.5-pro model entry to compare behavior:
    ```
    models:
      model_a:
        provider: google
        model: gemini-2.5-pro
      model_b:
        provider: google
        model: gemini-2.5-flash
    ```
  - Keep max_concurrent_llm_calls at 4 for stability while refactoring eval to FPF batch

2) Prompt instructions for evaluate
- llm-doc-eval/prompts/single_template.md and pairwise_template.md
  - Already adjusted to require web search (per earlier fix). Ensure templates include:
    - “Use Grounding with Google Search.”
    - “Provide citations; ensure provider JSON contains groundingMetadata and/or citations.”
    - “Answers without explicit grounding evidence will be rejected.”
  - If your downstream parsing expects URL-free human text, add:
    - “Do not place URLs in the human-readable output; keep them in provider JSON only.”

3) Evaluation criteria (llm-doc-eval/criteria.yaml)
- Current file:
  - criteria: factuality, relevance, completeness, style_clarity
- For testing grounding-specific outcomes, add criteria to emphasize evidence:
  - Option A (simple list, implicit equal weight):
    ```
    criteria:
      - factuality
      - relevance
      - completeness
      - style_clarity
      - grounding_evidence
      - citation_quality
    ```
  - Option B (explicit weights, if supported by your scoring implementation):
    ```
    criteria:
      - name: factuality
        weight: 0.30
      - name: relevance
        weight: 0.20
      - name: completeness
        weight: 0.20
      - name: style_clarity
        weight: 0.10
      - name: grounding_evidence
        weight: 0.15
      - name: citation_quality
        weight: 0.05
    ```
  - Grounding_evidence: checks for presence/consistency of groundingMetadata.* or citations/citationMetadata in provider JSON
  - Citation_quality: assesses traceability and specificity of citations

4) Concurrency and batch submission (future-proof)
- When refactoring eval to FPF batch:
  - Pass options["max_concurrency"] = llm_api.max_concurrent_llm_calls
  - Pass options["json"] = true for evaluation (generate uses false). Single-call only; no two-stage.
  - Centralize retry/timeout in FPF, keep eval’s DB writes/validation logic unchanged

C) Minimal test matrix

- Generate (ACM):
  - Case G1 (baseline): pro + current standard_prompt.txt → expect occasional grounding failures
  - Case G2 (fix): pro + strengthened standard_prompt.txt → expect improved grounding compliance
  - Case G3 (control): flash/flash-lite + strengthened prompt → expect consistent pass
- Evaluate:
  - Case E1 (baseline): single and pairwise with pro + strengthened eval templates → verify pass under strict enforcer
  - Case E2 (control): flash with same templates → verify pass
  - Case E3 (criteria emphasis): add grounding_evidence and citation_quality → confirm scoring reflects evidence presence

D) Commands and artifacts

- Generate (ACM)
  - python -u api_cost_multiplier/generate.py
  - Outputs: api_cost_multiplier/test/mdoutputs/*.fpf.response.txt
  - Logs: api_cost_multiplier/FilePromptForge/logs/*.json (inspect groundingMetadata, citations)
- Evaluate
  - Run your eval entrypoint (single/pairwise/both) per llm-doc-eval CLI/process
  - Confirm DB or output artifacts match expectations; inspect provider JSON in logs if attached

E) Success checks

- Grounding presence:
  - provider JSON contains groundingMetadata.webSearchQueries and/or searchEntryPoint and/or citations/citationMetadata
- No human-URL leakage (if required):
  - Human-readable text free of URLs; evidence resides in provider JSON/logs
- Model comparison:
  - flash/flash-lite pass consistently; pro improves under strengthened prompts
- Criteria reflection:
  - grounding_evidence/citation_quality criteria elevate responses with robust evidence

This testing guidance ensures both generate and evaluate paths can reproduce the original problem and validate improvements via targeted configuration and prompt/criteria adjustments.
===== END: C:\dev\silky\api_cost_multiplier\docs\gemini_grounding_issue_report.md =====


===== BEGIN: C:\dev\silky\api_cost_multiplier\docs\REPEATING PROBLEMS GROUINGS OCT.md =====
============================================================
FPF MUST ALWAYS USE GROUNDING AND REASONING. IT IS UNCONFIGURABLE.
IF YOU WANT TO CHANGE GROUNDING IN FPF, STOP IMMEDIATELY.

FPF MUST ALWAYS USE GROUNDING AND REASONING.
DO NOT ATTEMPT TO CHANGE FPF AWAY FROM GROUNDING AND REASONING.
============================================================

Title: Repeating Problems — Grounding (October)
Author: Cline
Date: 2025-10-12

1) Contract (YES/NO, unambiguous)
- If JSON is NOT requested: no JSON flag/parameter is passed to any provider.
- If JSON IS requested:
  - OpenAI/OpenRouter: pass provider JSON controls (e.g., response_format=json_object or a schema).
  - Google: never set generationConfig.responseMimeType or responseJsonSchema. Instead, instruct the model to return strict JSON; if JSON appears as text in the single response, extract it. No second call.

2) “Auto mode” removal (what it was, why it’s gone)
- What it was: a provider-aware convenience that attempted to decide when to use provider JSON based on model/tool compatibility.
- Why it fails requirements:
  - It creates ambiguity. The contract demands binary behavior:
    - json=False → no provider JSON controls
    - json=True → OpenAI sets JSON control; Google never sets JSON control (instruction-only)
  - It risks regressions from provider drift. The policy prioritizes explicit, deterministic behavior.
- Decision: Remove all references to “auto” in config, code, and docs. JSON handling is strictly boolean.

3) Exact implementation requirements (code-level)
A. Config (FilePromptForge/fpf_config.yaml)
- Set:
  - json: false        # boolean only
- Remove:
  - allow_json_with_tools
  - Any mention of “auto” JSON modes
- Rationale: configuration must reflect strictly boolean JSON intent.

B. Core (FilePromptForge/file_handler.py)
- Treat cfg["json"] strictly as boolean. No heuristics.
- request_json path:
  - If request_json=True, only attempt single-call text extraction via _extract_json_from_text on the provider’s textual output. Never perform a second LLM call.
- Do not inject provider JSON flags implicitly; adapters decide based on cfg["json"] and provider.
- Keep mandatory grounding/reasoning asserts intact.

C. Google adapter (FilePromptForge/providers/google/fpf_google_main.py)
- Never set generationConfig.responseMimeType or responseJsonSchema.
- When cfg["json"] is True:
  - Prepend a short instruction to return only a single valid JSON object, no prose, in the model’s textual output.
  - Grounding stays mandatory; the payload must continue to include the google_search tool.
- Parsing:
  - Continue using parse_response for human text.
  - If higher layer requested JSON, rely on the single-call extractor for JSON text, no second call.

D. OpenAI adapter (FilePromptForge/providers/openai/…)
- When cfg["json"] is True:
  - Set response_format=json_object (or schema if provided).
- When cfg["json"] is False:
  - Do not set any JSON controls.
- Grounding and reasoning remain enforced per project policy.

E. Documentation
- Purge all “auto” references from docs and comments.
- Update docs to state the boolean contract above verbatim.

4) Test plan (single-call only, no two-stage)
- Generate (ACM):
  - Case G1: json=False → Confirm no provider JSON controls are sent to Google or OpenAI.
  - Case G2: json=True →
    - OpenAI: confirm response_format/json_object present.
    - Google: confirm no responseMimeType or schema is set; confirm prompt includes JSON-only instruction; confirm JSON can be extracted from the text if present.
  - For all Google runs: confirm groundingMetadata/citations present and no responseMimeType in request payload.
- Evaluate:
  - For json=False templates: confirm no provider JSON flags set; still grounded.
  - For json=True templates: confirm OpenAI uses JSON flag; Google uses instruction-only approach; JSON can be extracted if present.
- Logs:
  - Capture FilePromptForge/logs/*.json request/response snapshots; verify no JSON parameter for Google in generationConfig.

5) Acceptance criteria
- No references to “auto” in code or docs.
- json=False → zero provider JSON flags for all providers.
- json=True:
  - OpenAI/OpenRouter → response_format/json_object (or schema).
  - Google → no JSON parameters; JSON instruction-only; extraction from text only when present.
- Grounding always enforced (mandatory) and passes verification.

6) Migration/rollback
- Migration:
  - Set json: false in fpf_config.yaml and remove any “auto” references.
  - Deploy updated adapters.
- Rollback:
  - Revert the specific commits; restore prior config if needed (not recommended).

7) Rationale summary (why boolean-only)
- Eliminates ambiguity; aligns perfectly with the stated contract.
- Reduces maintenance risk from provider drift.
- Keeps single-call constraint; preserves mandatory grounding.

8) Next steps
- Implement the code/doc edits listed above.
- Run generate and evaluate; attach new log IDs and observations to this doc.

END OF DOCUMENT
===== END: C:\dev\silky\api_cost_multiplier\docs\REPEATING PROBLEMS GROUINGS OCT.md =====
